"""Loads, parameterises and runs the version-controlled SQL.

Query text lives in ``analytics/sql/*.sql`` rather than in string literals
here, so a change to a metric shows up as a reviewable diff. Values are
always bound as parameters, never interpolated.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import structlog

log = structlog.get_logger(__name__)

SQL_DIR = Path(__file__).resolve().parent / "sql"

SPREAD = "01_spread.sql"
SEASONALITY = "02_seasonality.sql"
VOLATILITY = "03_volatility.sql"
COVERAGE = "04_coverage.sql"
ARRIVALS = "05_arrivals.sql"

GRAIN_PREFIX = "-- GRAIN:"


def load_sql(name: str) -> str:
    path = SQL_DIR / name
    text = path.read_text(encoding="utf-8")
    if not text.lstrip().startswith(GRAIN_PREFIX):
        raise ValueError(f"{name} does not declare its grain on line 1")
    return text


def _run(con, name: str, params: list) -> pd.DataFrame:
    frame = con.execute(load_sql(name), params).df()
    log.info("query.complete", query=name, rows=len(frame))
    return frame


def spread_by_day(con, commodity: str, min_markets: int = 10) -> pd.DataFrame:
    """GRAIN: one row per (date, commodity).
    Excludes days with fewer than `min_markets` reporting markets."""
    return _run(con, SPREAD, [commodity, min_markets])


def seasonal_index(con, commodity: str) -> pd.DataFrame:
    """GRAIN: one row per (commodity, month).
    Index = 100 * month_avg / mean of the twelve month averages."""
    return _run(con, SEASONALITY, [commodity])


def volatility_by_market(con, commodity: str, min_obs: int = 100) -> pd.DataFrame:
    """GRAIN: one row per (market, commodity, fiscal_year)."""
    return _run(con, VOLATILITY, [commodity, min_obs])


def coverage_report(con) -> pd.DataFrame:
    """GRAIN: one row per (market, commodity)."""
    return _run(con, COVERAGE, [])


def reporting_intensity(con, commodity: str) -> pd.DataFrame:
    """GRAIN: one row per (date, commodity). Market count, not tonnage."""
    return _run(con, ARRIVALS, [commodity])


def materialise_all(
    con,
    commodities: list[str],
    out_dir: Path,
    min_markets: int = 10,
    min_obs: int = 100,
) -> dict[str, Path]:
    """Write every analytical output to parquet for the dashboard to read."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    def stack(frames: list[pd.DataFrame]) -> pd.DataFrame:
        """Concatenate, ignoring empties. Concatenating an empty frame makes
        pandas resolve NA dtypes and changes column types under us."""
        populated = [f for f in frames if not f.empty]
        if not populated:
            return frames[0] if frames else pd.DataFrame()
        return pd.concat(populated, ignore_index=True)

    spread = stack([spread_by_day(con, c, min_markets) for c in commodities])
    seasonal = stack([seasonal_index(con, c) for c in commodities])
    volatility = stack([volatility_by_market(con, c, min_obs) for c in commodities])
    intensity = stack([reporting_intensity(con, c) for c in commodities])
    coverage = coverage_report(con)

    written: dict[str, Path] = {}
    for name, frame in (
        ("spread", spread),
        ("seasonality", seasonal),
        ("volatility", volatility),
        ("coverage", coverage),
        ("reporting_intensity", intensity),
    ):
        path = out_dir / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        written[name] = path
        log.info("materialise.write", output=name, rows=len(frame), path=str(path))

    return written


def main() -> int:
    from appconfig import load_settings, resolve_path

    settings = load_settings()
    warehouse = resolve_path("warehouse")
    if not warehouse.exists():
        log.error("analytics.no_warehouse", path=str(warehouse))
        return 1

    con = duckdb.connect(str(warehouse), read_only=True)
    try:
        written = materialise_all(
            con,
            settings["scope"]["commodities"],
            resolve_path("processed") / "analytics",
            min_markets=settings["quality"]["min_markets_for_spread"],
            min_obs=settings["quality"]["min_observations"],
        )
    finally:
        con.close()

    for name, path in written.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
