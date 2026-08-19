"""Raw strings to a validated, canonical, typed dataset.

Every row that does not survive is kept, with a reason from a fixed enum.
Missing market-days are never interpolated: a market that did not report
simply has no row, and inventing one would fabricate the exact prices the
analysis rests on.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import structlog

from ingest.models import RejectReason, ValidationError
from transform.canonicalise import canonical_commodity, canonical_market
from transform.parse import parse_arrival_date, parse_price
from transform.validate import validate_price_triple

log = structlog.get_logger(__name__)

REQUIRED_RAW_FIELDS = (
    "state",
    "market",
    "commodity",
    "arrival_date",
    "min_price",
    "max_price",
    "modal_price",
)

GRAIN = (
    "arrival_date",
    "market_canonical",
    "commodity_canonical",
    "variety",
    "grade",
)

CLEAN_COLUMNS = (
    "arrival_date",
    "state",
    "district",
    "market_canonical",
    "commodity_canonical",
    "variety",
    "grade",
    "min_price_inr_qtl",
    "max_price_inr_qtl",
    "modal_price_inr_qtl",
    "intraday_spread_pct",
    "source",
    "fetched_at_utc",
    "is_outlier",
)

REJECTED_COLUMNS = ("raw", "reject_reason", "rejected_at_utc")

# Deterministic stand-in when a row carries no fetch timestamp, so dedupe
# never depends on wall-clock time.
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

_MAD_TO_SIGMA = 0.6745

_CANONICAL_TO_RAW = {
    "market_canonical": "market",
    "commodity_canonical": "commodity",
    "min_price_inr_qtl": "min_price",
    "max_price_inr_qtl": "max_price",
    "modal_price_inr_qtl": "modal_price",
}


def _to_raw_shape(frame: pd.DataFrame) -> pd.DataFrame:
    """Accept either a raw frame or this function's own output.

    Cleaning has to be idempotent, so a clean frame is mapped back to raw
    column names rather than rejected as unrecognised.
    """
    if "market_canonical" not in frame.columns:
        return frame

    out = frame.rename(columns=_CANONICAL_TO_RAW)
    return out.drop(columns=["intraday_spread_pct", "is_outlier"], errors="ignore")


def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == ""


def _empty_pair() -> tuple[pd.DataFrame, pd.DataFrame]:
    return (
        pd.DataFrame(columns=list(CLEAN_COLUMNS)),
        pd.DataFrame(columns=list(REJECTED_COLUMNS)),
    )


def _flag_outliers(frame: pd.DataFrame, outlier_z: float) -> pd.Series:
    """Robust z-score on log modal price within (market, commodity).

    Outliers are flagged, never dropped. A genuine price spike is data;
    silently removing it would understate volatility.
    """
    if frame.empty:
        return pd.Series(dtype=bool)

    logged = np.log(frame["modal_price_inr_qtl"].astype(float))
    grouped = logged.groupby(
        [frame["market_canonical"], frame["commodity_canonical"]], observed=True
    )
    median = grouped.transform("median")
    mad = (
        (logged - median)
        .abs()
        .groupby(
            [frame["market_canonical"], frame["commodity_canonical"]], observed=True
        )
        .transform("median")
    )

    z = pd.Series(0.0, index=frame.index)
    usable = mad > 0
    z[usable] = _MAD_TO_SIGMA * (logged[usable] - median[usable]) / mad[usable]
    return z.abs() > outlier_z


def clean_dataframe(
    raw: pd.DataFrame,
    commodity_map: dict,
    market_map: dict,
    outlier_z: float = 4.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (clean_df, rejected_df).

    Order of operations matters: a row is tested against the cheapest and
    most fundamental rule first, so its reject reason names the real cause.
    """
    if raw is None or len(raw) == 0:
        return _empty_pair()

    source_frame = _to_raw_shape(raw)
    total_in = len(source_frame)
    kept: list[dict] = []
    rejected: list[dict] = []
    rejected_at = datetime.now(UTC)

    def reject(row: dict, reason: RejectReason) -> None:
        rejected.append(
            {
                "raw": json.dumps(row, default=str, sort_keys=True),
                "reject_reason": str(getattr(reason, "value", reason)),
                "rejected_at_utc": rejected_at,
            }
        )

    for row in source_frame.to_dict("records"):
        # 1. required fields
        if any(_blank(row.get(field)) for field in REQUIRED_RAW_FIELDS):
            reject(row, RejectReason.MISSING_REQUIRED_FIELD)
            continue

        try:
            # 2. dates, 3. prices, 4. price triple
            arrival_date = parse_arrival_date(row["arrival_date"])
            min_p = parse_price(row["min_price"])
            max_p = parse_price(row["max_price"])
            modal_p = parse_price(row["modal_price"])
            validate_price_triple(min_p, max_p, modal_p)

            # 5. canonical names
            commodity = canonical_commodity(row["commodity"], commodity_map)
            market = canonical_market(
                row["market"], row.get("district") or "", market_map
            )
        except ValidationError as exc:
            reject(row, exc.reject_reason)
            continue

        fetched = row.get("fetched_at_utc")
        kept.append(
            {
                "arrival_date": arrival_date,
                "state": str(row["state"]).strip(),
                "district": (
                    None
                    if _blank(row.get("district"))
                    else str(row["district"]).strip()
                ),
                "market_canonical": market,
                "commodity_canonical": commodity,
                "variety": (
                    None if _blank(row.get("variety")) else str(row["variety"]).strip()
                ),
                "grade": None
                if _blank(row.get("grade"))
                else str(row["grade"]).strip(),
                "min_price_inr_qtl": min_p,
                "max_price_inr_qtl": max_p,
                "modal_price_inr_qtl": modal_p,
                "source": str(row.get("source") or "api"),
                "fetched_at_utc": EPOCH if _blank(fetched) else fetched,
                "_raw": row,
            }
        )

    clean = pd.DataFrame(kept)
    if clean.empty:
        rejected_df = pd.DataFrame(rejected, columns=list(REJECTED_COLUMNS))
        _assert_invariants(
            pd.DataFrame(columns=list(CLEAN_COLUMNS)), rejected_df, total_in
        )
        return pd.DataFrame(columns=list(CLEAN_COLUMNS)), rejected_df

    clean["fetched_at_utc"] = pd.to_datetime(
        clean["fetched_at_utc"], utc=True, format="mixed"
    )

    # 6. dedupe on grain, keeping the most recent fetch
    grain_keys = [clean[c].astype("string").fillna("") for c in GRAIN]
    clean = clean.assign(_grain=pd.MultiIndex.from_arrays(grain_keys).to_flat_index())
    clean = clean.sort_values("fetched_at_utc", kind="mergesort")
    duplicates = clean.duplicated(subset="_grain", keep="last")
    for row in clean.loc[duplicates, "_raw"]:
        reject(row, RejectReason.DUPLICATE_GRAIN)
    clean = clean.loc[~duplicates].drop(columns=["_grain", "_raw"])

    # 7. intraday spread, expressed against the modal price
    clean["intraday_spread_pct"] = (
        100.0
        * (clean["max_price_inr_qtl"] - clean["min_price_inr_qtl"])
        / clean["modal_price_inr_qtl"]
    )

    # 8. flag outliers
    clean = clean.sort_values(list(GRAIN), kind="mergesort").reset_index(drop=True)
    clean["is_outlier"] = _flag_outliers(clean, outlier_z)

    clean = clean[list(CLEAN_COLUMNS)]
    rejected_df = pd.DataFrame(rejected, columns=list(REJECTED_COLUMNS))

    _assert_invariants(clean, rejected_df, total_in)
    log.info(
        "clean.complete",
        rows_in=total_in,
        rows_clean=len(clean),
        rows_rejected=len(rejected_df),
        outliers=int(clean["is_outlier"].sum()),
    )
    return clean, rejected_df


def _assert_invariants(
    clean: pd.DataFrame, rejected: pd.DataFrame, total_in: int
) -> None:
    assert (
        len(clean) + len(rejected) == total_in
    ), f"conservation broken: {len(clean)} + {len(rejected)} != {total_in}"
    if clean.empty:
        return

    required = [
        "arrival_date",
        "market_canonical",
        "commodity_canonical",
        "min_price_inr_qtl",
        "max_price_inr_qtl",
        "modal_price_inr_qtl",
    ]
    assert not clean[required].isna().any().any(), "null in a required clean column"
    assert (clean["min_price_inr_qtl"] <= clean["max_price_inr_qtl"]).all()
    assert (clean["min_price_inr_qtl"] > 0).all()
    grain = [clean[c].astype("string").fillna("") for c in GRAIN]
    duplicate_count = int(pd.concat(grain, axis=1).duplicated().sum())
    assert duplicate_count == 0, f"grain not unique: {duplicate_count} duplicates"


# -- outputs ---------------------------------------------------------------


def write_quarantine(
    rejected: pd.DataFrame, directory: Path, run_id: str = ""
) -> Path | None:
    if rejected.empty:
        log.info("quarantine.empty")
        return None
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    path = directory / f"rejects-{stamp}{('-' + run_id) if run_id else ''}.parquet"
    rejected.to_parquet(path, index=False)
    log.info("quarantine.write", path=str(path), rows=len(rejected))
    return path


def write_data_quality_report(
    clean: pd.DataFrame,
    rejected: pd.DataFrame,
    path: Path,
    out_of_scope_rows: int = 0,
) -> Path:
    """Counts by reject reason, plus coverage by market. Regenerated on every
    clean run so the numbers in the docs can never drift from the data."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    total = len(clean) + len(rejected)

    lines = [
        "# Data quality",
        "",
        f"Generated {datetime.now(UTC).date().isoformat()} from the current "
        "landing zone. Do not edit by hand.",
        "",
        "## Conservation",
        "",
        "| Stage | Rows |",
        "|---|---|",
        f"| Raw records landed | {total + out_of_scope_rows:,} |",
        f"| Outside configured scope (state / commodity) | {out_of_scope_rows:,} |",
        f"| Records considered | {total:,} |",
        f"| Clean records kept | {len(clean):,} |",
        f"| Records quarantined | {len(rejected):,} |",
        f"| Retention | {(100.0 * len(clean) / total if total else 0):.2f}% |",
        "",
        "Scope exclusion is a deliberate filter, not a data-quality failure, "
        "so it is reported separately. Of the records considered, every one is "
        "either kept or quarantined with a reason, and the two counts always "
        "sum to the total; there is an assertion for it.",
        "",
        "## Rejections by reason",
        "",
        "| Reason | Rows | % of raw |",
        "|---|---|---|",
    ]

    if rejected.empty:
        lines.append("| _none_ | 0 | 0.00% |")
    else:
        counts = rejected["reject_reason"].value_counts()
        for reason, count in counts.items():
            share = 100.0 * count / total if total else 0.0
            lines.append(f"| `{reason}` | {count:,} | {share:.2f}% |")

    lines += ["", "## Coverage by market", ""]
    if clean.empty:
        lines.append("_No clean rows._")
    else:
        coverage = (
            clean.groupby("market_canonical")
            .agg(
                observations=("modal_price_inr_qtl", "size"),
                reporting_days=("arrival_date", "nunique"),
                first_date=("arrival_date", "min"),
                last_date=("arrival_date", "max"),
                outliers=("is_outlier", "sum"),
            )
            .sort_values("observations", ascending=False)
        )
        span = (coverage["last_date"] - coverage["first_date"]).apply(
            lambda d: d.days + 1
        )
        coverage["coverage_pct"] = (100.0 * coverage["reporting_days"] / span).round(2)
        lines.append(coverage.head(50).to_markdown())
        lines += [
            "",
            "Coverage is reporting days as a share of the market's own observed "
            "span. Gaps are left as gaps; no missing day is interpolated.",
        ]

    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("data_quality.report", path=str(path))
    return path


def apply_scope(raw: pd.DataFrame, states: list[str], commodities: list[str]):
    """Restrict to the configured analytical scope.

    Rows for other states or commodities are OUT OF SCOPE, not rejects.
    Counting them as UNKNOWN_MARKET would bury the real data-quality signal
    under a filter the analyst chose deliberately.
    """
    if raw.empty:
        return raw, 0

    before = len(raw)
    in_scope = raw[
        raw["state"].isin(states) & raw["commodity"].isin(commodities)
    ].reset_index(drop=True)
    dropped = before - len(in_scope)
    log.info(
        "clean.scope_filter",
        rows_in=before,
        rows_in_scope=len(in_scope),
        rows_out_of_scope=dropped,
    )
    return in_scope, dropped


def main() -> int:
    from appconfig import PROJECT_ROOT, load_settings, resolve_path
    from ingest.land import read_landed
    from transform.canonicalise import load_commodity_map, load_market_map

    settings = load_settings()
    raw = read_landed(resolve_path("raw"))
    if raw.empty:
        log.error("clean.no_input", path=str(resolve_path("raw")))
        return 1

    raw, out_of_scope = apply_scope(
        raw, settings["scope"]["states"], settings["scope"]["commodities"]
    )

    clean, rejected = clean_dataframe(
        raw,
        load_commodity_map(PROJECT_ROOT / "seeds" / "commodity_map.csv"),
        load_market_map(PROJECT_ROOT / "seeds" / "market_map.csv"),
        outlier_z=settings["quality"]["outlier_z_threshold"],
    )

    processed = resolve_path("processed")
    processed.mkdir(parents=True, exist_ok=True)
    clean.to_parquet(processed / "clean.parquet", index=False)
    write_quarantine(rejected, resolve_path("quarantine"))
    write_data_quality_report(
        clean, rejected, PROJECT_ROOT / "docs" / "data_quality.md", out_of_scope
    )

    log.info("clean.written", rows=len(clean), rejected=len(rejected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
