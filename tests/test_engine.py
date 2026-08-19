"""Phase 6 -- the week loop, its invariants, and the golden run."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import pytest

from ingest.models import ConfigError
from simulate.engine import (
    WEEKLY_LOG_COLUMNS,
    compare_strategies,
    run_simulation,
    saving_vs_baseline,
    storage_capacity_qtl,
    weekly_requirement_qtl,
)
from simulate.strategies import NoCandidateMarketsError
from tests.conftest import GOLDEN_DAYS, GOLDEN_START

COMMODITY = "Onion"
SIM_START = GOLDEN_START
SIM_END = GOLDEN_START + timedelta(days=364)


@pytest.fixture
def sim(golden_prices, golden_markets, golden_assumptions):
    def _run(strategy: str, **overrides):
        return run_simulation(
            golden_prices,
            strategy,
            {**golden_assumptions, **overrides},
            COMMODITY,
            SIM_START,
            SIM_END,
            golden_markets,
        )

    return _run


# --- 6.35 / 6.36 -----------------------------------------------------------


@pytest.mark.parametrize("strategy", ["S1", "S2", "S3"])
def test_inventory_never_negative(sim, strategy):
    log = sim(strategy).weekly_log
    assert (log["closing_inventory_qtl"] >= 0).all()
    assert (log["opening_inventory_qtl"] >= 0).all()


@pytest.mark.parametrize("strategy", ["S1", "S2", "S3"])
def test_inventory_never_exceeds_cap(sim, strategy, golden_assumptions):
    need = weekly_requirement_qtl(
        golden_assumptions["buyer"]["monthly_requirement_tonnes"]
    )
    cap = storage_capacity_qtl(
        need, golden_assumptions["commodities"][COMMODITY]["max_storage_weeks"]
    )
    log = sim(strategy).weekly_log
    assert (log["closing_inventory_qtl"] <= cap + 1e-6).all()


# --- 6.37 ------------------------------------------------------------------


@pytest.mark.parametrize("strategy", ["S1", "S2", "S3"])
def test_no_shortfall_weeks(sim, strategy):
    result = sim(strategy)
    assert result.weeks_with_shortfall == 0
    assert (
        result.weekly_log["delivered_qtl"] >= result.weekly_log["required_qtl"] - 1e-6
    ).all()


# --- 6.38 ------------------------------------------------------------------


@pytest.mark.parametrize("strategy", ["S1", "S2", "S3"])
def test_total_cost_equals_component_sum(sim, strategy):
    result = sim(strategy)
    components = (
        result.total_purchase_cost_inr
        + result.total_transport_cost_inr
        + result.total_storage_cost_inr
    )
    assert result.total_cost_inr == pytest.approx(components)
    assert result.total_cost_inr == pytest.approx(
        result.weekly_log["week_cost_inr"].sum()
    )


# --- 6.39 / 6.40 -----------------------------------------------------------


def test_weekly_log_row_count(sim):
    expected_weeks = ((SIM_END - SIM_START).days + 6) // 7
    assert len(sim("S1").weekly_log) == expected_weeks == 52


def test_weekly_log_has_audit_columns(sim):
    log = sim("S2").weekly_log
    assert list(log.columns) == list(WEEKLY_LOG_COLUMNS)
    for column in (
        "week_start",
        "market",
        "modal_price_inr_qtl",
        "purchased_qtl",
        "closing_inventory_qtl",
        "week_cost_inr",
    ):
        assert column in log.columns
        assert log[column].notna().all()


# --- 6.41 ------------------------------------------------------------------


def test_s1_deterministic(sim):
    first, second = sim("S1"), sim("S1")
    pd.testing.assert_frame_equal(first.weekly_log, second.weekly_log)
    assert first.summary() == second.summary()


# --- 6.42 / 6.43 -----------------------------------------------------------


def test_missing_price_week_handled(golden_prices, golden_markets, golden_assumptions):
    """A market silent on the decision day falls back to its last quote
    within the staleness window -- never to a fabricated number."""
    silent_day = SIM_START + timedelta(days=7)
    panel = golden_prices[
        ~((golden_prices["date"] == silent_day) & (golden_prices["market"] == "Far"))
    ]

    result = run_simulation(
        panel, "S2", golden_assumptions, COMMODITY, SIM_START, SIM_END, golden_markets
    )

    week = result.weekly_log[result.weekly_log["week_start"] == silent_day].iloc[0]
    assert week["market"] == "Far", "the stale-but-recent quote is still usable"
    assert result.weeks_with_shortfall == 0


def test_all_prices_missing_raises(golden_markets, golden_assumptions):
    empty = pd.DataFrame(columns=["date", "market", "modal_price_inr_qtl"])

    with pytest.raises(NoCandidateMarketsError):
        run_simulation(
            empty,
            "S2",
            golden_assumptions,
            COMMODITY,
            SIM_START,
            SIM_END,
            golden_markets,
        )


def test_unknown_strategy_raises(golden_prices, golden_assumptions):
    with pytest.raises(ConfigError):
        run_simulation(
            golden_prices, "S9", golden_assumptions, COMMODITY, SIM_START, SIM_END
        )


def test_unknown_commodity_raises(golden_prices, golden_assumptions):
    with pytest.raises(ConfigError):
        run_simulation(
            golden_prices, "S1", golden_assumptions, "Dragonfruit", SIM_START, SIM_END
        )


# --- 6.44 : the golden run -------------------------------------------------


def test_golden_simulation(
    golden_prices, golden_markets, golden_assumptions, fixtures_dir
):
    """Full run on the frozen panel must match the committed golden file.

    If this breaks, either a bug was introduced or the method changed
    deliberately -- and if the latter, the golden file is regenerated in its
    own commit with an explanation.
    """
    results = compare_strategies(
        golden_prices, golden_assumptions, COMMODITY, SIM_START, SIM_END, golden_markets
    )
    actual = {strategy: result.summary() for strategy, result in results.items()}
    actual["saving"] = {
        key: round(value, 4) for key, value in saving_vs_baseline(results).items()
    }

    golden_path = fixtures_dir / "golden_simulation.json"
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert actual == expected


def test_golden_saving_is_plausible(golden_prices, golden_markets, golden_assumptions):
    """A saving above 30% almost always means a look-ahead leak or a unit
    error, so the range itself is a tripwire."""
    results = compare_strategies(
        golden_prices, golden_assumptions, COMMODITY, SIM_START, SIM_END, golden_markets
    )
    saving = saving_vs_baseline(results)

    assert 0.0 < saving["S2_saving_pct"] < 30.0
    assert 0.0 < saving["S3_saving_pct"] < 30.0


# --- 6.45 / 6.46 -----------------------------------------------------------


def test_zero_length_period(golden_prices, golden_markets, golden_assumptions):
    result = run_simulation(
        golden_prices,
        "S1",
        golden_assumptions,
        COMMODITY,
        SIM_START,
        SIM_START,
        golden_markets,
    )

    assert result.weekly_log.empty
    assert result.total_cost_inr == 0.0
    assert result.cost_per_qtl_delivered_inr == 0.0
    assert result.weeks_with_shortfall == 0


def test_single_week_period(golden_prices, golden_markets, golden_assumptions):
    result = run_simulation(
        golden_prices,
        "S2",
        golden_assumptions,
        COMMODITY,
        SIM_START,
        SIM_START + timedelta(days=7),
        golden_markets,
    )

    assert len(result.weekly_log) == 1
    assert result.weeks_with_shortfall == 0
    assert result.total_cost_inr > 0


# --- 6.47 ------------------------------------------------------------------


@pytest.mark.parametrize("strategy", ["S1", "S2", "S3"])
def test_cost_per_qtl_reasonable(sim, strategy):
    """Onion lands somewhere between Rs 500 and Rs 10,000 per quintal. A
    result outside that band is a unit error, not a finding."""
    cost = sim(strategy).cost_per_qtl_delivered_inr
    assert 500.0 < cost < 10_000.0, f"{strategy}: Rs {cost:,.0f}/qtl"


def test_s2_beats_s1_on_this_panel(sim):
    assert sim("S2").total_cost_inr < sim("S1").total_cost_inr


def test_golden_panel_spans_a_year(golden_prices):
    assert golden_prices["date"].nunique() == GOLDEN_DAYS
    assert set(golden_prices["market"]) == {"Home", "Near", "Far"}


def test_weekly_requirement_conversion(golden_assumptions):
    """500 t/month annualised is 6,000 t/yr, 115.38 t/week, 1153.85 qtl."""
    need = weekly_requirement_qtl(
        golden_assumptions["buyer"]["monthly_requirement_tonnes"]
    )
    assert need == pytest.approx(1153.8462, abs=1e-3)


def test_storage_capacity_rules(golden_assumptions):
    need = weekly_requirement_qtl(
        golden_assumptions["buyer"]["monthly_requirement_tonnes"]
    )
    assert storage_capacity_qtl(need, 1) == 0.0, "one-week shelf life carries nothing"
    assert storage_capacity_qtl(need, 12) == pytest.approx(need * 11)


def test_week_starts_are_seven_days_apart(sim):
    starts = pd.to_datetime(sim("S1").weekly_log["week_start"])
    assert (starts.diff().dropna().dt.days == 7).all()
    assert starts.iloc[0].date() == date(2025, 1, 6)
