"""Historical backfill and source reconciliation.

The API resource is a current daily feed, so multi-year history has to come
from a downloaded CSV. This module loads that CSV against an explicit column
map, and reconciles it against the API pull where the two overlap.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import structlog
import yaml

from ingest.client import MarketPriceAPIClient
from ingest.land import (
    STATUS_COMPLETE,
    STATUS_IN_PROGRESS,
    land_records,
    new_run_id,
    read_landed,
    resume_offset,
    write_checkpoint,
)
from ingest.models import SchemaError

log = structlog.get_logger(__name__)

API_COLUMNS = (
    "state",
    "district",
    "market",
    "commodity",
    "variety",
    "grade",
    "arrival_date",
    "min_price",
    "max_price",
    "modal_price",
)

JOIN_KEY = ["arrival_date", "market", "commodity", "variety"]
DIVERGENCE_THRESHOLD_PCT = 10.0


def run_backfill(
    client: MarketPriceAPIClient,
    commodities: list[str],
    root: Path,
    page_size: int = 1000,
    max_pages: int = 500,
    source: str = "backfill",
    pulled_date: date | None = None,
) -> dict[str, int]:
    """Paginate each commodity, landing every page and checkpointing after it.

    Resumes from the checkpoint, so a crash costs one page, not one crawl.
    """
    root = Path(root)
    run_id = new_run_id()
    landed: dict[str, int] = {}

    for commodity in commodities:
        offset = resume_offset(root, commodity)
        rows = 0
        page = 0
        log.info("backfill.start", commodity=commodity, resume_offset=offset)

        while page < max_pages:
            records, total = client.fetch_page(
                offset=offset, limit=page_size, filters={"commodity": commodity}
            )
            if not records:
                write_checkpoint(root, commodity, offset, STATUS_COMPLETE)
                break

            land_records(
                records,
                source=source,
                commodity=commodity,
                root=root,
                pulled_date=pulled_date,
                ingest_run_id=run_id,
            )
            rows += len(records)
            offset += page_size
            page += 1
            write_checkpoint(root, commodity, offset, STATUS_IN_PROGRESS)

            if total and offset >= total:
                write_checkpoint(root, commodity, offset, STATUS_COMPLETE)
                break
        else:
            log.warning("backfill.max_pages", commodity=commodity, pages=page)

        landed[commodity] = rows
        log.info("backfill.complete", commodity=commodity, rows=rows)

    return landed


# -- CSV backfill ----------------------------------------------------------


def load_column_map(path: Path) -> dict[str, str]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    mapping = data.get("columns", data)
    if not isinstance(mapping, dict):
        raise SchemaError(f"column map is not a mapping: {path}")
    return {str(k): str(v) for k, v in mapping.items()}


def map_backfill_columns(frame: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """Rename a downloaded CSV's headers to the API schema.

    Any header absent from the map is an error: silently dropping a column
    is how a price ends up in the wrong field.
    """
    unmapped = [c for c in frame.columns if c not in mapping]
    if unmapped:
        raise SchemaError(f"unmapped columns in backfill CSV: {sorted(unmapped)}")

    renamed = frame.rename(columns=mapping)
    missing = [c for c in API_COLUMNS if c not in renamed.columns]
    if missing:
        raise SchemaError(f"backfill CSV is missing required columns: {missing}")

    return renamed[list(API_COLUMNS)]


def backfill_from_csv(
    csv_path: Path,
    column_map_path: Path,
    root: Path,
    commodity_column: str = "commodity",
    pulled_date: date | None = None,
) -> dict[str, int]:
    frame = pd.read_csv(csv_path, dtype=str).fillna("")
    mapped = map_backfill_columns(frame, load_column_map(column_map_path))
    run_id = new_run_id()

    landed: dict[str, int] = {}
    for commodity, group in mapped.groupby(commodity_column):
        land_records(
            group.to_dict("records"),
            source="backfill",
            commodity=str(commodity),
            root=root,
            pulled_date=pulled_date,
            ingest_run_id=run_id,
        )
        landed[str(commodity)] = len(group)

    log.info("backfill.csv.complete", file=str(csv_path), rows=len(mapped))
    return landed


# -- reconciliation --------------------------------------------------------


def _normalise_for_join(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in JOIN_KEY:
        out[column] = out.get(column, "").astype(str).str.strip().str.casefold()
    out["modal_price"] = pd.to_numeric(out["modal_price"], errors="coerce")
    return out


def reconcile(api_frame: pd.DataFrame, backfill_frame: pd.DataFrame) -> dict:
    """Compare the two sources where their date ranges overlap."""
    empty = {
        "overlap_start": None,
        "overlap_end": None,
        "overlap_rows": 0,
        "api_rows": int(len(api_frame)),
        "backfill_rows": int(len(backfill_frame)),
        "matched_keys": 0,
        "api_only_keys": 0,
        "backfill_only_keys": 0,
        "match_rate_pct": 0.0,
        "divergence": pd.DataFrame(
            columns=[
                *JOIN_KEY,
                "modal_price_api",
                "modal_price_backfill",
                "abs_diff_pct",
            ]
        ),
        "abs_diff_pct_describe": {},
    }
    if api_frame.empty or backfill_frame.empty:
        return empty

    api = _normalise_for_join(api_frame)
    back = _normalise_for_join(backfill_frame)

    start = max(api["arrival_date"].min(), back["arrival_date"].min())
    end = min(api["arrival_date"].max(), back["arrival_date"].max())
    api = api[(api["arrival_date"] >= start) & (api["arrival_date"] <= end)]
    back = back[(back["arrival_date"] >= start) & (back["arrival_date"] <= end)]
    if api.empty or back.empty:
        return empty

    merged = api.merge(
        back, on=JOIN_KEY, how="outer", suffixes=("_api", "_backfill"), indicator=True
    )
    matched = merged[merged["_merge"] == "both"].copy()
    api_only = int((merged["_merge"] == "left_only").sum())
    back_only = int((merged["_merge"] == "right_only").sum())
    union = len(merged)

    matched["abs_diff_pct"] = (
        (matched["modal_price_api"] - matched["modal_price_backfill"]).abs()
        / matched["modal_price_backfill"].replace(0, pd.NA)
        * 100.0
    )
    divergence = matched.loc[
        matched["abs_diff_pct"] > DIVERGENCE_THRESHOLD_PCT,
        [*JOIN_KEY, "modal_price_api", "modal_price_backfill", "abs_diff_pct"],
    ].sort_values("abs_diff_pct", ascending=False)

    report = {
        "overlap_start": start,
        "overlap_end": end,
        "overlap_rows": union,
        "api_rows": int(len(api)),
        "backfill_rows": int(len(back)),
        "matched_keys": int(len(matched)),
        "api_only_keys": api_only,
        "backfill_only_keys": back_only,
        "match_rate_pct": round(100.0 * len(matched) / union, 4) if union else 0.0,
        "divergence": divergence,
        "abs_diff_pct_describe": matched["abs_diff_pct"].describe().to_dict(),
    }
    log.info(
        "reconcile.complete",
        overlap_rows=union,
        match_rate_pct=report["match_rate_pct"],
        divergent=len(divergence),
    )
    return report


def write_reconciliation_report(report: dict, path: Path, verdict: str = "") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    describe = report.get("abs_diff_pct_describe") or {}
    divergence = report["divergence"]

    lines = [
        "# Source reconciliation — API pull vs historical backfill",
        "",
        f"Generated {datetime.now().date().isoformat()}.",
        "",
        "## Overlap",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Overlap start | {report['overlap_start'] or 'n/a'} |",
        f"| Overlap end | {report['overlap_end'] or 'n/a'} |",
        f"| Rows in overlap (union of keys) | {report['overlap_rows']:,} |",
        f"| API rows in overlap | {report['api_rows']:,} |",
        f"| Backfill rows in overlap | {report['backfill_rows']:,} |",
        "",
        "## Match rate",
        "",
        f"Join key: `{', '.join(JOIN_KEY)}`",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Keys in both sources | {report['matched_keys']:,} |",
        f"| Keys in API only | {report['api_only_keys']:,} |",
        f"| Keys in backfill only | {report['backfill_only_keys']:,} |",
        f"| **Match rate** | **{report['match_rate_pct']:.2f}%** |",
        "",
        "## Modal price divergence where both sources have the key",
        "",
        "| Statistic | Absolute % difference |",
        "|---|---|",
    ]
    for stat in ("count", "mean", "50%", "75%", "max"):
        value = describe.get(stat)
        lines.append(
            f"| {stat} | {value:.2f} |" if pd.notna(value) else f"| {stat} | n/a |"
        )

    lines += [
        "",
        f"Rows diverging by more than {DIVERGENCE_THRESHOLD_PCT:.0f}%: "
        f"**{len(divergence):,}**",
        "",
    ]
    if len(divergence):
        lines.append(divergence.head(20).to_markdown(index=False))
        lines.append("")

    lines += ["## Verdict", "", verdict or "_Not yet written._", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("reconcile.report", path=str(path))
    return path


# -- entrypoint ------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    from appconfig import get_api_key, load_settings, resolve_path

    parser = argparse.ArgumentParser(description="Historical backfill")
    parser.add_argument("--from-csv", type=Path, help="load a downloaded history CSV")
    parser.add_argument(
        "--column-map",
        type=Path,
        default=Path("seeds/backfill_column_map.yaml"),
    )
    parser.add_argument("--reconcile", action="store_true")
    args = parser.parse_args(argv)

    settings = load_settings()
    raw_root = resolve_path("raw")

    if args.from_csv:
        backfill_from_csv(args.from_csv, args.column_map, raw_root)
        return 0

    if args.reconcile:
        report = reconcile(
            read_landed(raw_root, source="api"),
            read_landed(raw_root, source="backfill"),
        )
        write_reconciliation_report(report, Path("docs/source_reconciliation.md"))
        return 0

    api = settings["api"]
    with MarketPriceAPIClient(
        api_key=get_api_key(),
        base_url=api["base_url"],
        resource_id=api["resource_id"],
        timeout_seconds=api["timeout_seconds"],
        max_retries=api["max_retries"],
        sleep_seconds=api["sleep_seconds"],
    ) as client:
        run_backfill(
            client,
            settings["scope"]["commodities"],
            raw_root,
            page_size=api["page_size"],
            max_pages=api["max_pages"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
