"""Phase 6 -- strategies, and the tests that prove the look-ahead firewall."""

from __future__ import annotations

import inspect
from datetime import date, timedelta

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulate.strategies import (
    NoCandidateMarketsError,
    PriceView,
    S3Params,
    decide_s1,
    decide_s2,
    decide_s3,
)

START = date(2026, 1, 1)
AS_OF = date(2026, 3, 1)


def price_panel(prices: dict[str, float], days: int = 90, start: date = START):
    """A flat price panel: one row per (day, market)."""
    rows = []
    for day in range(days):
        for market, price in prices.items():
            rows.append(
                {
                    "date": start + timedelta(days=day),
                    "market": market,
                    "modal_price_inr_qtl": price,
                }
            )
    return pd.DataFrame(rows)


def candidates(**transport: float) -> pd.DataFrame:
    return pd.DataFrame(
        [{"market": m, "transport_inr_qtl": t} for m, t in transport.items()]
    )


# --- 6.19 / 6.20 / 6.21 : the firewall -------------------------------------


def test_price_view_excludes_future():
    """Even handed a full panel, the view holds nothing after as_of."""
    panel = price_panel({"Home": 1000.0}, days=90)
    view = PriceView(as_of_date=AS_OF, _frame=panel)

    assert panel["date"].max() > AS_OF, "the fixture must contain future rows"
    assert view._frame["date"].max() <= AS_OF
    assert len(view._frame) < len(panel)


def test_price_view_has_no_future_accessor():
    """No public accessor can return a row after as_of, whatever it is called."""
    panel = price_panel({"Home": 1000.0, "Far": 900.0}, days=90)
    view = PriceView(as_of_date=AS_OF, _frame=panel)

    public = [
        name
        for name, _ in inspect.getmembers(view, callable)
        if not name.startswith("_")
    ]
    assert set(public) == {"current_prices", "latest_prices", "trailing_mean"}

    for name in public:
        method = getattr(view, name)
        signature = inspect.signature(method)
        args = []
        for parameter in signature.parameters.values():
            if parameter.default is not inspect.Parameter.empty:
                continue
            args.append("Home" if parameter.name == "market" else 20)

        result = method(*args)
        if isinstance(result, pd.DataFrame) and not result.empty:
            assert result["date"].max() <= AS_OF, name


def test_trailing_mean_excludes_as_of_day():
    """The mean is strictly backward-looking: today's price is not in it."""
    panel = price_panel({"Home": 1000.0}, days=90)
    panel.loc[panel["date"] == AS_OF, "modal_price_inr_qtl"] = 99999.0
    view = PriceView(as_of_date=AS_OF, _frame=panel)

    assert view.trailing_mean("Home", 20) == pytest.approx(1000.0)
    assert view.current_prices()["modal_price_inr_qtl"].iloc[0] == 99999.0


def test_trailing_mean_insufficient_data():
    panel = price_panel({"Home": 1000.0}, days=3, start=AS_OF - timedelta(days=3))
    view = PriceView(as_of_date=AS_OF, _frame=panel)

    assert view.trailing_mean("Home", 20) is None
    assert view.trailing_mean("Home", 4) == pytest.approx(1000.0)


# --- 6.23 / 6.24 : S1 ------------------------------------------------------


def test_s1_always_buys_home_market():
    panel = price_panel({"Home": 1000.0, "Cheaper": 500.0}, days=380)

    markets = set()
    for week in range(52):
        view = PriceView(as_of_date=START + timedelta(weeks=week), _frame=panel)
        markets.add(decide_s1(view, 1000.0, "Home").market)

    assert markets == {"Home"}


def test_s1_buys_exact_need():
    panel = price_panel({"Home": 1000.0}, days=90)
    view = PriceView(as_of_date=AS_OF, _frame=panel)

    purchase = decide_s1(view, 1153.85, "Home")
    assert purchase.quantity_qtl == pytest.approx(1153.85)
    assert purchase.transport_inr_qtl == 0.0
    assert purchase.landed_inr_qtl == 1000.0
    assert purchase.total_inr == pytest.approx(1153.85 * 1000.0)


# --- 6.25 - 6.28 : S2 ------------------------------------------------------


def test_s2_picks_lowest_landed_not_lowest_modal():
    """Cheap but far (900 + 200 freight) loses to dear but near (1000 + 10)."""
    panel = price_panel({"Near": 1000.0, "Far": 900.0}, days=90)
    view = PriceView(as_of_date=AS_OF, _frame=panel)

    purchase = decide_s2(view, 1000.0, candidates(Near=10.0, Far=200.0))

    assert purchase.market == "Near"
    assert purchase.landed_inr_qtl == 1010.0


def test_s2_equals_s1_when_only_home_in_radius():
    panel = price_panel({"Home": 1000.0, "Far": 500.0}, days=90)
    view = PriceView(as_of_date=AS_OF, _frame=panel)

    s1 = decide_s1(view, 1000.0, "Home")
    s2 = decide_s2(view, 1000.0, candidates(Home=0.0))

    assert s2 == s1


@settings(max_examples=50, deadline=None)
@given(
    prices=st.lists(
        st.floats(min_value=100.0, max_value=5000.0), min_size=2, max_size=6
    )
)
def test_s2_never_costlier_when_transport_zero(prices):
    """With free freight, S2 can never pay more than S1 at the home market."""
    panel = price_panel(
        {f"M{i}": p for i, p in enumerate(prices)},
        days=40,
        start=AS_OF - timedelta(days=30),
    )
    view = PriceView(as_of_date=AS_OF, _frame=panel)
    free = candidates(**{f"M{i}": 0.0 for i in range(len(prices))})

    s1 = decide_s1(view, 1000.0, "M0")
    s2 = decide_s2(view, 1000.0, free)

    assert s2.total_inr <= s1.total_inr + 1e-6


def test_s2_no_candidates_raises():
    panel = price_panel({"Home": 1000.0}, days=90)
    view = PriceView(as_of_date=AS_OF, _frame=panel)

    with pytest.raises(NoCandidateMarketsError):
        decide_s2(view, 1000.0, pd.DataFrame(columns=["market", "transport_inr_qtl"]))

    # A candidate that has never quoted is also an explicit error, not a zero.
    with pytest.raises(NoCandidateMarketsError):
        decide_s2(view, 1000.0, candidates(Unknown=0.0))


# --- 6.29 - 6.34 : S3 ------------------------------------------------------

PARAMS = S3Params(
    dip_trigger_ratio=0.90, moving_average_days=20, max_multiple_of_need=2.0
)
NEED = 1000.0
CAP = 11_000.0


def dipping_panel(dip_factor: float, base: float = 1000.0) -> pd.DataFrame:
    """Flat at `base` for 60 days, then `base * dip_factor` on the decision day."""
    panel = price_panel({"Home": base}, days=61, start=AS_OF - timedelta(days=60))
    panel.loc[panel["date"] == AS_OF, "modal_price_inr_qtl"] = base * dip_factor
    return panel


def test_s3_buys_extra_below_trigger():
    view = PriceView(as_of_date=AS_OF, _frame=dipping_panel(0.85))

    purchase = decide_s3(view, NEED, candidates(Home=0.0), 0.0, CAP, PARAMS)

    assert purchase.modal_price_inr_qtl == pytest.approx(850.0)
    assert purchase.quantity_qtl == pytest.approx(2 * NEED)


def test_s3_buys_normal_above_trigger():
    view = PriceView(as_of_date=AS_OF, _frame=dipping_panel(0.95))

    purchase = decide_s3(view, NEED, candidates(Home=0.0), 0.0, CAP, PARAMS)

    assert purchase.quantity_qtl == pytest.approx(NEED)


def test_s3_respects_storage_cap():
    """Carry-out after delivery may not exceed the store."""
    view = PriceView(as_of_date=AS_OF, _frame=dipping_panel(0.85))
    inventory, cap = 900.0, 1000.0

    purchase = decide_s3(view, NEED, candidates(Home=0.0), inventory, cap, PARAMS)

    carried = inventory + purchase.quantity_qtl - NEED
    assert carried <= cap + 1e-9
    assert purchase.quantity_qtl == pytest.approx(cap - inventory + NEED)


def test_s3_tomato_cannot_stockpile():
    """max_storage_weeks = 1 means a cap of zero, so never more than need."""
    view = PriceView(as_of_date=AS_OF, _frame=dipping_panel(0.50))

    purchase = decide_s3(view, NEED, candidates(Home=0.0), 0.0, 0.0, PARAMS)

    assert purchase.quantity_qtl == pytest.approx(NEED)


def test_s3_uses_inventory_before_buying():
    view = PriceView(as_of_date=AS_OF, _frame=dipping_panel(1.0))

    purchase = decide_s3(view, 1250.0, candidates(Home=0.0), 1250.0, CAP, PARAMS)

    assert purchase.quantity_qtl == 0.0
    assert purchase.total_inr == 0.0


def test_s3_no_ma_available_falls_back_to_s2():
    """Inside the first 20 days there is no usable average, so S3 is S2."""
    panel = price_panel(
        {"Near": 1000.0, "Far": 900.0}, days=3, start=AS_OF - timedelta(days=2)
    )
    view = PriceView(as_of_date=AS_OF, _frame=panel)
    market_set = candidates(Near=10.0, Far=200.0)

    assert view.trailing_mean("Near", 20) is None

    s3 = decide_s3(view, NEED, market_set, 0.0, CAP, PARAMS)
    s2 = decide_s2(view, NEED, market_set)
    assert s3 == s2
