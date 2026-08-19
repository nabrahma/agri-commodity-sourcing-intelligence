"""One-at-a-time sensitivity analysis.

Turns a point estimate into a range, and names the assumption the
conclusion actually hangs on.
"""

from __future__ import annotations

import copy
from datetime import date
from pathlib import Path

import pandas as pd
import structlog

from ingest.models import ConfigError
from simulate.engine import compare_strategies, saving_vs_baseline

log = structlog.get_logger(__name__)

# Where each swept parameter lives. min_coverage_pct is not an assumption:
# it changes which markets qualify, so it is applied to the market table.
COST_PARAMS = ("transport_inr_per_qtl_per_100km", "storage_inr_per_qtl_per_week")
BUYER_PARAMS = ("max_radius_km",)
COMMODITY_PARAMS = ("shrinkage_ratio_per_week",)
S3_PARAMS = ("dip_trigger_ratio", "moving_average_days", "max_multiple_of_need")
MARKET_PARAMS = ("min_coverage_pct",)

DEFAULT_GRID: dict[str, list[float]] = {
    "transport_inr_per_qtl_per_100km": [2.0, 4.0, 6.0],
    "max_radius_km": [300.0, 500.0, 800.0],
    "storage_inr_per_qtl_per_week": [7.5, 15.0, 30.0],
    "shrinkage_ratio_per_week": [0.5, 1.0, 1.5],  # multiples of base
    "dip_trigger_ratio": [0.85, 0.90, 0.95],
    "min_coverage_pct": [60.0, 70.0, 80.0],
}

RESULT_COLUMNS = (
    "parameter",
    "value",
    "is_base",
    "s1_total_inr",
    "s2_total_inr",
    "s3_total_inr",
    "s2_saving_inr",
    "s2_saving_pct",
    "s3_saving_inr",
    "s3_saving_pct",
    "best_saving_pct",
    "s2_beats_s1",
)


def apply_parameter(
    base_assumptions: dict, parameter: str, value: float, commodity: str
) -> dict:
    """Deep copy of the assumptions with one parameter replaced.

    Always a copy: a swept run must never leak back into the base case.
    """
    modified = copy.deepcopy(base_assumptions)

    if parameter in COST_PARAMS:
        modified["costs"][parameter] = value
    elif parameter in BUYER_PARAMS:
        modified["buyer"][parameter] = value
    elif parameter in S3_PARAMS:
        modified["strategy_s3"][parameter] = value
    elif parameter in COMMODITY_PARAMS:
        # Swept as a multiple of the commodity's own base rate.
        base = base_assumptions["commodities"][commodity][parameter]
        modified["commodities"][commodity][parameter] = min(0.999, base * value)
    elif parameter in MARKET_PARAMS:
        pass  # handled against the market table, not the assumptions
    else:
        raise ConfigError(f"unknown sensitivity parameter: {parameter!r}")

    return modified


def _filter_markets(markets: pd.DataFrame, min_coverage_pct: float) -> pd.DataFrame:
    if "coverage_pct" not in markets.columns:
        return markets
    return markets[markets["coverage_pct"] >= min_coverage_pct].reset_index(drop=True)


def run_sensitivity(
    base_assumptions: dict,
    parameter_grid: dict[str, list[float]],
    commodity: str,
    prices: pd.DataFrame | None = None,
    markets: pd.DataFrame | None = None,
    start: date | None = None,
    end: date | None = None,
    base_min_coverage_pct: float = 70.0,
) -> pd.DataFrame:
    """One-at-a-time sweep. One row per (parameter, value).

    `base_assumptions` is never mutated; every run works on a deep copy.
    """
    if prices is None or prices.empty:
        raise ConfigError("run_sensitivity needs a price panel")

    grid = parameter_grid or DEFAULT_GRID
    start = start or pd.to_datetime(prices["date"]).min().date()
    end = end or pd.to_datetime(prices["date"]).max().date()

    rows: list[dict] = []
    for parameter, values in grid.items():
        for value in values:
            assumptions = apply_parameter(base_assumptions, parameter, value, commodity)
            market_table = markets
            if parameter in MARKET_PARAMS and markets is not None:
                market_table = _filter_markets(markets, value)

            results = compare_strategies(
                prices, assumptions, commodity, start, end, market_table
            )
            saving = saving_vs_baseline(results)
            is_base = _is_base_value(
                base_assumptions, parameter, value, commodity, base_min_coverage_pct
            )

            rows.append(
                {
                    "parameter": parameter,
                    "value": value,
                    "is_base": is_base,
                    "s1_total_inr": results["S1"].total_cost_inr,
                    "s2_total_inr": results["S2"].total_cost_inr,
                    "s3_total_inr": results["S3"].total_cost_inr,
                    "s2_saving_inr": saving["S2_saving_inr"],
                    "s2_saving_pct": saving["S2_saving_pct"],
                    "s3_saving_inr": saving["S3_saving_inr"],
                    "s3_saving_pct": saving["S3_saving_pct"],
                    "best_saving_pct": max(
                        saving["S2_saving_pct"], saving["S3_saving_pct"]
                    ),
                    "s2_beats_s1": saving["S2_saving_inr"] > 0,
                }
            )

    frame = pd.DataFrame(rows, columns=list(RESULT_COLUMNS))
    log.info("sensitivity.complete", runs=len(frame), parameters=len(grid))
    return frame


def _is_base_value(
    base_assumptions: dict,
    parameter: str,
    value: float,
    commodity: str,
    base_min_coverage_pct: float,
) -> bool:
    if parameter in COST_PARAMS:
        return base_assumptions["costs"][parameter] == value
    if parameter in BUYER_PARAMS:
        return base_assumptions["buyer"][parameter] == value
    if parameter in S3_PARAMS:
        return base_assumptions["strategy_s3"][parameter] == value
    if parameter in COMMODITY_PARAMS:
        return value == 1.0
    if parameter in MARKET_PARAMS:
        return value == base_min_coverage_pct
    return False


def tornado_data(sensitivity_df: pd.DataFrame) -> pd.DataFrame:
    """Rank parameters by the spread of outcomes they produce.

    The top row is the binding assumption: the one worth spending money to
    measure before anyone acts on the number.
    """
    if sensitivity_df.empty:
        return pd.DataFrame(
            columns=["parameter", "low_pct", "high_pct", "range_pct", "swing_pct"]
        )

    grouped = sensitivity_df.groupby("parameter")["best_saving_pct"]
    tornado = pd.DataFrame(
        {
            "low_pct": grouped.min(),
            "high_pct": grouped.max(),
        }
    ).reset_index()
    tornado["range_pct"] = tornado["high_pct"] - tornado["low_pct"]
    tornado["swing_pct"] = tornado["range_pct"]
    return tornado.sort_values(
        ["range_pct", "parameter"], ascending=[False, True]
    ).reset_index(drop=True)


def conclusion_stability(sensitivity_df: pd.DataFrame) -> dict:
    """Does the recommendation survive the whole grid, or only the base case?"""
    if sensitivity_df.empty:
        return {
            "s2_beats_s1_always": False,
            "runs": 0,
            "min_saving_pct": 0.0,
            "max_saving_pct": 0.0,
            "runs_where_s2_loses": 0,
        }

    return {
        "s2_beats_s1_always": bool(sensitivity_df["s2_beats_s1"].all()),
        "runs": int(len(sensitivity_df)),
        "min_saving_pct": float(sensitivity_df["s2_saving_pct"].min()),
        "max_saving_pct": float(sensitivity_df["s2_saving_pct"].max()),
        "runs_where_s2_loses": int((~sensitivity_df["s2_beats_s1"]).sum()),
    }


def main() -> int:
    import duckdb

    from appconfig import load_assumptions, load_settings, resolve_path
    from simulate.engine import markets_from_warehouse, prices_from_warehouse

    settings = load_settings()
    warehouse = resolve_path("warehouse")
    if not warehouse.exists():
        log.error("sensitivity.no_warehouse", path=str(warehouse))
        return 1

    commodity = settings["scope"]["commodities"][0]
    con = duckdb.connect(str(warehouse), read_only=True)
    try:
        prices = prices_from_warehouse(con, commodity)
        markets = markets_from_warehouse(con)
    finally:
        con.close()

    frame = run_sensitivity(
        load_assumptions(),
        DEFAULT_GRID,
        commodity,
        prices,
        markets,
        base_min_coverage_pct=settings["quality"]["min_coverage_pct"],
    )
    tornado = tornado_data(frame)
    stability = conclusion_stability(frame)

    out_dir = resolve_path("processed") / "analytics"
    out_dir.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out_dir / "sensitivity.parquet", index=False)
    tornado.to_parquet(out_dir / "tornado.parquet", index=False)

    print(tornado.to_string(index=False))
    print(f"\nbinding assumption: {tornado.iloc[0]['parameter']}")
    print(
        f"saving range across the grid: {stability['min_saving_pct']:.2f}% to "
        f"{stability['max_saving_pct']:.2f}%"
    )
    print(f"S2 beats S1 in every run: {stability['s2_beats_s1_always']}")
    return 0


def write_tornado(tornado: pd.DataFrame, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tornado.to_parquet(path, index=False)
    return path


if __name__ == "__main__":
    raise SystemExit(main())
