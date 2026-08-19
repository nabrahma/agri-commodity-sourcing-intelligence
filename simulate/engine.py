"""Week-by-week sourcing simulation.

The weekly log is a deliverable, not a debug artefact: every rupee in the
headline number traces to a market, a date and a price that existed on the
decision day.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import structlog

from ingest.models import ConfigError
from simulate.costs import (
    apply_shrinkage,
    storage_cost_inr,
    tonnes_to_quintals,
    transport_cost_inr_per_qtl,
)
from simulate.geo import markets_within_radius
from simulate.strategies import (
    PriceView,
    S3Params,
    decide_s1,
    decide_s2,
    decide_s3,
)

log = structlog.get_logger(__name__)

STRATEGIES = ("S1", "S2", "S3")
WEEKS_PER_YEAR = 52.0
MONTHS_PER_YEAR = 12.0

WEEKLY_LOG_COLUMNS = (
    "week_index",
    "week_start",
    "strategy",
    "commodity",
    "market",
    "modal_price_inr_qtl",
    "transport_inr_qtl",
    "landed_inr_qtl",
    "purchased_qtl",
    "required_qtl",
    "delivered_qtl",
    "opening_inventory_qtl",
    "closing_inventory_qtl",
    "shrinkage_loss_qtl",
    "purchase_cost_inr",
    "transport_cost_inr",
    "storage_cost_inr",
    "week_cost_inr",
)


@dataclass
class SimulationResult:
    strategy: str
    commodity: str
    weekly_log: pd.DataFrame
    total_purchase_cost_inr: float
    total_transport_cost_inr: float
    total_storage_cost_inr: float
    total_shrinkage_loss_qtl: float
    total_cost_inr: float
    cost_per_qtl_delivered_inr: float
    weeks_with_shortfall: int

    def summary(self) -> dict:
        return {
            "strategy": self.strategy,
            "commodity": self.commodity,
            "weeks": int(len(self.weekly_log)),
            "total_purchase_cost_inr": round(self.total_purchase_cost_inr, 2),
            "total_transport_cost_inr": round(self.total_transport_cost_inr, 2),
            "total_storage_cost_inr": round(self.total_storage_cost_inr, 2),
            "total_shrinkage_loss_qtl": round(self.total_shrinkage_loss_qtl, 4),
            "total_cost_inr": round(self.total_cost_inr, 2),
            "cost_per_qtl_delivered_inr": round(self.cost_per_qtl_delivered_inr, 4),
            "weeks_with_shortfall": int(self.weeks_with_shortfall),
        }


def weekly_requirement_qtl(monthly_requirement_tonnes: float) -> float:
    """Weekly requirement in quintals, annualised so no month is special."""
    annual_tonnes = float(monthly_requirement_tonnes) * MONTHS_PER_YEAR
    return tonnes_to_quintals(annual_tonnes / WEEKS_PER_YEAR)


def storage_capacity_qtl(weekly_need_qtl: float, max_storage_weeks: int) -> float:
    """How much may be carried between weeks.

    A commodity that keeps for one week can hold nothing over, which is why
    tomato can never stockpile.
    """
    return max(0.0, weekly_need_qtl * (float(max_storage_weeks) - 1.0))


def build_candidates(
    markets: pd.DataFrame,
    home_market: str,
    max_radius_km: float,
    transport_rate_per_100km: float,
) -> pd.DataFrame:
    """Markets reachable from home, with freight priced per quintal.

    `markets` carries market_canonical, lat and lon.
    """
    home_rows = markets[markets["market_canonical"] == home_market]
    if home_rows.empty:
        raise ConfigError(f"home market {home_market!r} is not in the market table")

    home = (float(home_rows.iloc[0]["lat"]), float(home_rows.iloc[0]["lon"]))
    reachable = markets_within_radius(home, markets, max_radius_km)

    out = reachable.rename(columns={"market_canonical": "market"})[
        ["market", "distance_km"]
    ].copy()
    out["transport_inr_qtl"] = [
        transport_cost_inr_per_qtl(d, transport_rate_per_100km)
        for d in out["distance_km"]
    ]
    return out


def _week_starts(start: date, end: date) -> list[date]:
    """Week start dates in [start, end). A zero-length period has no weeks."""
    weeks: list[date] = []
    cursor = start
    while cursor < end:
        weeks.append(cursor)
        cursor += timedelta(days=7)
    return weeks


def run_simulation(
    prices: pd.DataFrame,
    strategy: str,
    assumptions: dict,
    commodity: str,
    start: date,
    end: date,
    markets: pd.DataFrame | None = None,
) -> SimulationResult:
    """Week-by-week loop over one strategy.

    Every decision is taken through a PriceView built at the week start, so
    no strategy can consult a price it could not have known.
    """
    if strategy not in STRATEGIES:
        raise ConfigError(
            f"unknown strategy {strategy!r}; expected one of {STRATEGIES}"
        )

    buyer = assumptions["buyer"]
    costs = assumptions["costs"]
    commodity_rules = assumptions["commodities"].get(commodity)
    if commodity_rules is None:
        raise ConfigError(f"no assumptions entry for commodity {commodity!r}")

    need_qtl = weekly_requirement_qtl(buyer["monthly_requirement_tonnes"])
    cap_qtl = storage_capacity_qtl(need_qtl, commodity_rules["max_storage_weeks"])
    shrinkage = float(commodity_rules["shrinkage_ratio_per_week"])
    storage_rate = float(costs["storage_inr_per_qtl_per_week"])
    s3_params = S3Params(
        dip_trigger_ratio=assumptions["strategy_s3"]["dip_trigger_ratio"],
        moving_average_days=assumptions["strategy_s3"]["moving_average_days"],
        max_multiple_of_need=assumptions["strategy_s3"]["max_multiple_of_need"],
    )

    if markets is None:
        candidates = pd.DataFrame(
            [
                {
                    "market": buyer["home_market"],
                    "distance_km": 0.0,
                    "transport_inr_qtl": 0.0,
                }
            ]
        )
    else:
        candidates = build_candidates(
            markets,
            buyer["home_market"],
            buyer["max_radius_km"],
            costs["transport_inr_per_qtl_per_100km"],
        )

    rows: list[dict] = []
    inventory = 0.0
    shortfall_weeks = 0

    for index, week_start in enumerate(_week_starts(start, end)):
        view = PriceView(as_of_date=week_start, _frame=prices)
        opening = inventory

        if strategy == "S1":
            purchase = decide_s1(view, need_qtl, buyer["home_market"])
        elif strategy == "S2":
            purchase = decide_s2(view, need_qtl, candidates)
        else:
            purchase = decide_s3(
                view, need_qtl, candidates, inventory, cap_qtl, s3_params
            )

        available = opening + purchase.quantity_qtl
        delivered = min(need_qtl, available)
        if delivered + 1e-9 < need_qtl:
            shortfall_weeks += 1

        carried = available - delivered
        weekly_storage_cost = storage_cost_inr(carried, storage_rate)
        after_shrinkage = apply_shrinkage(carried, shrinkage)
        shrinkage_loss = carried - after_shrinkage
        inventory = after_shrinkage

        purchase_cost = purchase.quantity_qtl * purchase.modal_price_inr_qtl
        transport_cost = purchase.quantity_qtl * purchase.transport_inr_qtl

        assert inventory >= 0.0, f"week {index}: negative inventory"
        assert (
            inventory <= cap_qtl + 1e-6
        ), f"week {index}: inventory {inventory} exceeds cap {cap_qtl}"
        assert purchase.quantity_qtl >= 0.0, f"week {index}: negative purchase"

        rows.append(
            {
                "week_index": index,
                "week_start": week_start,
                "strategy": strategy,
                "commodity": commodity,
                "market": purchase.market,
                "modal_price_inr_qtl": purchase.modal_price_inr_qtl,
                "transport_inr_qtl": purchase.transport_inr_qtl,
                "landed_inr_qtl": purchase.landed_inr_qtl,
                "purchased_qtl": purchase.quantity_qtl,
                "required_qtl": need_qtl,
                "delivered_qtl": delivered,
                "opening_inventory_qtl": opening,
                "closing_inventory_qtl": inventory,
                "shrinkage_loss_qtl": shrinkage_loss,
                "purchase_cost_inr": purchase_cost,
                "transport_cost_inr": transport_cost,
                "storage_cost_inr": weekly_storage_cost,
                "week_cost_inr": purchase_cost + transport_cost + weekly_storage_cost,
            }
        )

    weekly_log = pd.DataFrame(rows, columns=list(WEEKLY_LOG_COLUMNS))
    if weekly_log.empty:
        return SimulationResult(
            strategy, commodity, weekly_log, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0
        )

    total_purchase = float(weekly_log["purchase_cost_inr"].sum())
    total_transport = float(weekly_log["transport_cost_inr"].sum())
    total_storage = float(weekly_log["storage_cost_inr"].sum())
    total_cost = total_purchase + total_transport + total_storage
    delivered_total = float(weekly_log["delivered_qtl"].sum())

    result = SimulationResult(
        strategy=strategy,
        commodity=commodity,
        weekly_log=weekly_log,
        total_purchase_cost_inr=total_purchase,
        total_transport_cost_inr=total_transport,
        total_storage_cost_inr=total_storage,
        total_shrinkage_loss_qtl=float(weekly_log["shrinkage_loss_qtl"].sum()),
        total_cost_inr=total_cost,
        cost_per_qtl_delivered_inr=(
            total_cost / delivered_total if delivered_total else 0.0
        ),
        weeks_with_shortfall=shortfall_weeks,
    )
    log.info("simulate.complete", **result.summary())
    return result


def compare_strategies(
    prices: pd.DataFrame,
    assumptions: dict,
    commodity: str,
    start: date,
    end: date,
    markets: pd.DataFrame | None = None,
) -> dict[str, SimulationResult]:
    return {
        strategy: run_simulation(
            prices, strategy, assumptions, commodity, start, end, markets
        )
        for strategy in STRATEGIES
    }


def saving_vs_baseline(results: dict[str, SimulationResult]) -> dict[str, float]:
    """Saving of each strategy against S1, in rupees and percent."""
    baseline = results["S1"].total_cost_inr
    out: dict[str, float] = {"baseline_total_inr": baseline}
    for strategy, result in results.items():
        if strategy == "S1":
            continue
        saving = baseline - result.total_cost_inr
        out[f"{strategy}_saving_inr"] = saving
        out[f"{strategy}_saving_pct"] = 100.0 * saving / baseline if baseline else 0.0
    return out


def prices_from_warehouse(con, commodity: str, included_only: bool = True):
    """Decision-ready price panel: one modal price per (date, market)."""
    clause = "AND m.is_included" if included_only else ""
    return con.execute(
        f"""
        SELECT f.date_key            AS date,
               m.market_canonical    AS market,
               AVG(f.modal_price_inr_qtl) AS modal_price_inr_qtl
        FROM fct_price_daily f
        JOIN dim_market    m USING (market_sk)
        JOIN dim_commodity c USING (commodity_sk)
        WHERE c.commodity_canonical = ?
          AND NOT COALESCE(f.is_outlier, FALSE)
          {clause}
        GROUP BY f.date_key, m.market_canonical
        ORDER BY f.date_key, m.market_canonical
        """,
        [commodity],
    ).df()


def markets_from_warehouse(con):
    return con.execute(
        "SELECT market_canonical, lat, lon FROM dim_market "
        "WHERE is_included AND lat IS NOT NULL AND lon IS NOT NULL"
    ).df()


def main() -> int:
    import duckdb

    from appconfig import load_assumptions, load_settings, resolve_path

    settings = load_settings()
    assumptions = load_assumptions()
    warehouse = resolve_path("warehouse")
    if not warehouse.exists():
        log.error("simulate.no_warehouse", path=str(warehouse))
        return 1

    commodity = settings["scope"]["commodities"][0]
    con = duckdb.connect(str(warehouse), read_only=True)
    try:
        prices = prices_from_warehouse(con, commodity)
        markets = markets_from_warehouse(con)
    finally:
        con.close()

    if prices.empty:
        log.error("simulate.no_prices", commodity=commodity)
        return 1

    start = pd.to_datetime(prices["date"]).min().date()
    end = pd.to_datetime(prices["date"]).max().date()
    results = compare_strategies(prices, assumptions, commodity, start, end, markets)
    saving = saving_vs_baseline(results)

    out_dir = resolve_path("processed") / "simulation"
    out_dir.mkdir(parents=True, exist_ok=True)
    for strategy, result in results.items():
        result.weekly_log.to_parquet(
            out_dir / f"weekly_log_{strategy}.parquet", index=False
        )
    summary = {s: r.summary() for s, r in results.items()} | {"saving": saving}
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    for strategy, result in results.items():
        print(
            f"{strategy}: total Rs {result.total_cost_inr:,.0f} "
            f"({result.cost_per_qtl_delivered_inr:,.0f}/qtl)"
        )
    print(
        f"S2 saving vs S1: Rs {saving['S2_saving_inr']:,.0f} "
        f"({saving['S2_saving_pct']:.2f}%)"
    )
    print(
        f"S3 saving vs S1: Rs {saving['S3_saving_inr']:,.0f} "
        f"({saving['S3_saving_pct']:.2f}%)"
    )
    return 0


def save_golden(result: SimulationResult, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.summary(), indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
