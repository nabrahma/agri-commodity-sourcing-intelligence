"""Phase 5 -- analytics SQL, checked against hand-calculated answers."""

from __future__ import annotations

import statistics
from pathlib import Path

import pandas as pd
import pytest

from analytics.queries import (
    SQL_DIR,
    coverage_report,
    materialise_all,
    reporting_intensity,
    seasonal_index,
    spread_by_day,
    volatility_by_market,
)
from tests.conftest import (
    SEASONAL_BASE,
    SEASONAL_PEAK,
    SEASONAL_PEAK_MONTH,
    SPARSE_REPORTING_DAYS,
    SYNTH_DAYS,
)

# --- 5.1 / 5.2 -------------------------------------------------------------


def test_spread_matches_hand_calc(synthetic_con):
    """Markets at 1000 / 1200 / 1500 -> (1500-1000)/1000 = 50.0%."""
    spread = spread_by_day(synthetic_con, "Onion", min_markets=3)

    assert len(spread) == SYNTH_DAYS
    row = spread[spread["date_key"] == pd.Timestamp("2026-01-15")].iloc[0]
    assert row["min_modal_inr_qtl"] == 1000.0
    assert row["max_modal_inr_qtl"] == 1500.0
    assert row["spread_pct"] == pytest.approx(50.0)


def test_spread_identifies_cheapest_market(synthetic_con):
    spread = spread_by_day(synthetic_con, "Onion", min_markets=3)
    row = spread.iloc[10]

    assert row["cheapest_market"] == "Alpha"
    assert row["dearest_market"] == "Gamma"


# --- 5.3 -------------------------------------------------------------------


def test_spread_excludes_thin_days(synthetic_con):
    """Four included markets report; requiring ten leaves nothing."""
    assert spread_by_day(synthetic_con, "Onion", min_markets=10).empty
    assert not spread_by_day(synthetic_con, "Onion", min_markets=4).empty


# --- 5.4 -------------------------------------------------------------------


def test_spread_excludes_non_included_markets(synthetic_con):
    """Delta sits at 500 but is excluded, so the minimum stays 1000."""
    spread = spread_by_day(synthetic_con, "Onion", min_markets=3)

    assert spread["min_modal_inr_qtl"].min() == 1000.0
    assert "Delta" not in set(spread["cheapest_market"])

    synthetic_con.execute("UPDATE dim_market SET is_included = TRUE")
    with_delta = spread_by_day(synthetic_con, "Onion", min_markets=3)
    assert with_delta["min_modal_inr_qtl"].min() == 500.0


# --- 5.5 -------------------------------------------------------------------


def test_spread_empty_returns_empty_df(synthetic_con):
    empty = spread_by_day(synthetic_con, "Nonexistent Commodity", min_markets=1)

    assert empty.empty
    for column in ("date_key", "spread_pct", "cheapest_market", "markets_reporting"):
        assert column in empty.columns


# --- 5.15 ------------------------------------------------------------------


def test_outliers_excluded_from_spread(synthetic_con):
    """A flagged 100,000 print on day one must not set the maximum."""
    spread = spread_by_day(synthetic_con, "Onion", min_markets=3)
    day_one = spread[spread["date_key"] == pd.Timestamp("2026-01-01")].iloc[0]

    assert day_one["max_modal_inr_qtl"] == 1500.0
    assert day_one["spread_pct"] == pytest.approx(50.0)


# --- 5.6 / 5.7 / 5.8 -------------------------------------------------------


def test_seasonal_index_averages_to_100(seasonal_con):
    seasonal = seasonal_index(seasonal_con, "Onion")

    assert len(seasonal) == 12
    assert seasonal["seasonal_index"].mean() == pytest.approx(100.0, abs=0.5)


def test_seasonal_index_flat_prices_gives_100(seasonal_con):
    seasonal_con.execute(
        "UPDATE fct_price_daily SET modal_price_inr_qtl = ?", [SEASONAL_BASE]
    )
    seasonal = seasonal_index(seasonal_con, "Onion")

    assert seasonal["seasonal_index"].round(6).eq(100.0).all()


def test_seasonal_index_known_peak(seasonal_con):
    """Eleven months at 1000, July at 2200 -> baseline 1100, July = 200."""
    seasonal = seasonal_index(seasonal_con, "Onion")
    july = seasonal[seasonal["month"] == SEASONAL_PEAK_MONTH].iloc[0]

    assert july["month_avg_inr_qtl"] == pytest.approx(SEASONAL_PEAK)
    assert july["seasonal_index"] == pytest.approx(200.0)

    other = seasonal[seasonal["month"] != SEASONAL_PEAK_MONTH]
    assert other["seasonal_index"].round(4).eq(90.9091).all()


# --- 5.9 / 5.10 / 5.11 -----------------------------------------------------


def test_volatility_zero_for_constant(synthetic_con):
    """Every synthetic market holds a flat price, so cv is exactly zero."""
    volatility = volatility_by_market(synthetic_con, "Onion", min_obs=1)

    assert not volatility.empty
    assert volatility["cv"].abs().max() == pytest.approx(0.0)


def test_volatility_matches_hand_calc(synthetic_con):
    prices = [1000.0, 1100.0, 1500.0, 900.0, 1200.0]
    synthetic_con.execute("DELETE FROM fct_price_daily WHERE market_sk = 1")
    for i, price in enumerate(prices):
        synthetic_con.execute(
            """
            INSERT INTO fct_price_daily
            (date_key, market_sk, commodity_sk, variety, grade,
             min_price_inr_qtl, max_price_inr_qtl, modal_price_inr_qtl, is_outlier)
            VALUES (DATE '2026-01-01' + ?, 1, 1, 'Red', 'FAQ', 900, 1600, ?, FALSE)
            """,
            [i, price],
        )
    volatility = volatility_by_market(synthetic_con, "Onion", min_obs=1)
    alpha = volatility[volatility["market_canonical"] == "Alpha"].iloc[0]

    expected = statistics.stdev(prices) / statistics.fmean(prices)
    assert alpha["observations"] == len(prices)
    assert alpha["cv"] == pytest.approx(expected, abs=1e-9)


def test_volatility_respects_min_obs(synthetic_con):
    """Sparse reports on 45 days; a 100-observation floor excludes it."""
    included = volatility_by_market(synthetic_con, "Onion", min_obs=1)
    assert "Sparse" in set(included["market_canonical"])

    filtered = volatility_by_market(synthetic_con, "Onion", min_obs=100)
    assert "Sparse" not in set(filtered["market_canonical"])

    boundary = volatility_by_market(synthetic_con, "Onion", min_obs=46)
    assert "Sparse" not in set(boundary["market_canonical"])
    assert "Alpha" in set(
        volatility_by_market(synthetic_con, "Onion", min_obs=45)["market_canonical"]
    )


# --- 5.12 ------------------------------------------------------------------


def test_coverage_pct_matches_hand_calc(synthetic_con):
    """Sparse reports on 45 of a 60-day span -> 75.0%."""
    coverage = coverage_report(synthetic_con)
    sparse = coverage[coverage["market_canonical"] == "Sparse"].iloc[0]

    assert sparse["reporting_days"] == SPARSE_REPORTING_DAYS
    assert sparse["span_days"] == SYNTH_DAYS
    assert sparse["coverage_pct"] == pytest.approx(75.0)

    alpha = coverage[coverage["market_canonical"] == "Alpha"].iloc[0]
    assert alpha["coverage_pct"] == pytest.approx(100.0)


# --- 5.13 ------------------------------------------------------------------


def test_all_queries_have_grain_comment():
    files = sorted(SQL_DIR.glob("*.sql"))

    assert len(files) == 5
    for path in files:
        first = path.read_text(encoding="utf-8").splitlines()[0]
        assert first.startswith("-- GRAIN:"), f"{path.name}: {first!r}"
        assert len(first) > len("-- GRAIN:"), f"{path.name} declares an empty grain"


# --- 5.14 ------------------------------------------------------------------


def test_no_sql_injection_via_params(synthetic_con):
    hostile = "'; DROP TABLE fct_price_daily; --"

    result = spread_by_day(synthetic_con, hostile, min_markets=1)

    assert result.empty
    assert (
        synthetic_con.execute("SELECT COUNT(*) FROM fct_price_daily").fetchone()[0] > 0
    ), "the fact table was dropped"


# --- extras ----------------------------------------------------------------


def test_reporting_intensity_counts_markets(synthetic_con):
    intensity = reporting_intensity(synthetic_con, "Onion")

    assert len(intensity) == SYNTH_DAYS
    assert intensity["markets_reporting"].max() == 5


def test_materialise_all_writes_every_output(synthetic_con, tmp_path):
    written = materialise_all(
        synthetic_con, ["Onion"], tmp_path / "analytics", min_markets=3, min_obs=1
    )

    assert set(written) == {
        "spread",
        "seasonality",
        "volatility",
        "coverage",
        "reporting_intensity",
    }
    for path in written.values():
        assert Path(path).exists()
