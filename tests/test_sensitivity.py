"""Phase 7 -- sensitivity sweep and the tornado ranking."""

from __future__ import annotations

import copy
from datetime import timedelta

import pandas as pd
import pytest

from simulate.engine import compare_strategies, saving_vs_baseline
from simulate.sensitivity import (
    DEFAULT_GRID,
    conclusion_stability,
    run_sensitivity,
    tornado_data,
)
from tests.conftest import GOLDEN_START

COMMODITY = "Onion"
START = GOLDEN_START
END = GOLDEN_START + timedelta(days=112)  # 16 weeks: enough to rank parameters


@pytest.fixture
def sweep(golden_prices, golden_markets, golden_assumptions):
    def _run(grid, **kwargs):
        return run_sensitivity(
            golden_assumptions,
            grid,
            COMMODITY,
            prices=golden_prices,
            markets=golden_markets,
            start=START,
            end=END,
            **kwargs,
        )

    return _run


# --- 7.1 -------------------------------------------------------------------


def test_base_case_reproduces_phase6(
    sweep, golden_prices, golden_markets, golden_assumptions
):
    """The base row of the sweep must equal the unswept Phase 6 run."""
    frame = sweep({"transport_inr_per_qtl_per_100km": [4.0]})
    row = frame.iloc[0]

    results = compare_strategies(
        golden_prices, golden_assumptions, COMMODITY, START, END, golden_markets
    )
    saving = saving_vs_baseline(results)

    assert row["is_base"] is True or bool(row["is_base"])
    assert row["s1_total_inr"] == pytest.approx(results["S1"].total_cost_inr)
    assert row["s2_total_inr"] == pytest.approx(results["S2"].total_cost_inr)
    assert row["s2_saving_pct"] == pytest.approx(saving["S2_saving_pct"])


# --- 7.2 -------------------------------------------------------------------


def test_grid_shape(sweep):
    grid = {
        "transport_inr_per_qtl_per_100km": [2.0, 4.0, 6.0],
        "max_radius_km": [300.0, 500.0],
    }
    frame = sweep(grid)

    assert len(frame) == sum(len(v) for v in grid.values()) == 5
    assert set(frame["parameter"]) == set(grid)


# --- 7.3 -------------------------------------------------------------------


def test_higher_transport_reduces_saving(sweep):
    """Freight is what a distant market costs you; more of it erodes the gain."""
    frame = sweep({"transport_inr_per_qtl_per_100km": [2.0, 4.0, 6.0]})
    savings = frame.sort_values("value")["s2_saving_pct"].tolist()

    assert savings == sorted(savings, reverse=True)
    assert savings[0] > savings[-1]


# --- 7.4 -------------------------------------------------------------------


def test_larger_radius_increases_or_holds_saving(sweep):
    """A wider radius can only add options, never remove them."""
    frame = sweep({"max_radius_km": [300.0, 500.0, 800.0]})
    savings = frame.sort_values("value")["s2_saving_pct"].tolist()

    assert savings == sorted(savings)


# --- 7.5 -------------------------------------------------------------------


def test_tornado_ranks_by_range(sweep):
    frame = sweep(
        {
            "transport_inr_per_qtl_per_100km": [2.0, 4.0, 6.0],
            "storage_inr_per_qtl_per_week": [7.5, 15.0, 30.0],
            "dip_trigger_ratio": [0.85, 0.90, 0.95],
        }
    )
    tornado = tornado_data(frame)

    assert list(tornado.columns) == [
        "parameter",
        "low_pct",
        "high_pct",
        "range_pct",
        "swing_pct",
    ]
    ranges = tornado["range_pct"].tolist()
    assert ranges == sorted(ranges, reverse=True)
    assert (tornado["high_pct"] >= tornado["low_pct"]).all()

    # On this panel transport dominates; it is the binding assumption.
    assert tornado.iloc[0]["parameter"] == "transport_inr_per_qtl_per_100km"


def test_tornado_empty_input():
    assert tornado_data(pd.DataFrame()).empty


# --- 7.6 -------------------------------------------------------------------


def test_sensitivity_no_mutation(sweep, golden_assumptions):
    before = copy.deepcopy(golden_assumptions)

    sweep(
        {
            "transport_inr_per_qtl_per_100km": [2.0, 6.0],
            "shrinkage_ratio_per_week": [0.5, 1.5],
            "dip_trigger_ratio": [0.85],
        }
    )

    assert golden_assumptions == before, "the base assumptions were mutated"


# --- 7.7 -------------------------------------------------------------------


def test_extreme_param_no_crash(sweep):
    """Freight at Rs 1,000/100km makes distance ruinous. The saving may go
    negative; it must not crash or silently clamp."""
    frame = sweep({"transport_inr_per_qtl_per_100km": [1000.0]})
    row = frame.iloc[0]

    assert len(frame) == 1
    assert row["s2_saving_pct"] <= 0.0
    assert not bool(row["s2_beats_s1"])


# --- 7.8 -------------------------------------------------------------------


def test_conclusion_stability_flag(sweep):
    stable = conclusion_stability(
        sweep({"transport_inr_per_qtl_per_100km": [2.0, 4.0, 6.0]})
    )
    assert stable["s2_beats_s1_always"] is True
    assert stable["runs"] == 3
    assert stable["runs_where_s2_loses"] == 0
    assert stable["min_saving_pct"] <= stable["max_saving_pct"]

    unstable = conclusion_stability(
        sweep({"transport_inr_per_qtl_per_100km": [4.0, 1000.0]})
    )
    assert unstable["s2_beats_s1_always"] is False
    assert unstable["runs_where_s2_loses"] == 1

    assert conclusion_stability(pd.DataFrame())["runs"] == 0


def test_default_grid_covers_every_spec_parameter():
    assert set(DEFAULT_GRID) == {
        "transport_inr_per_qtl_per_100km",
        "max_radius_km",
        "storage_inr_per_qtl_per_week",
        "shrinkage_ratio_per_week",
        "dip_trigger_ratio",
        "min_coverage_pct",
    }
    for values in DEFAULT_GRID.values():
        assert len(values) == 3
