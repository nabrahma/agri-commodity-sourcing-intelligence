"""Phase 3 -- invariants that must hold for any input, not just the fixture."""

from __future__ import annotations

import math
from datetime import date

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from ingest.models import ValidationError
from transform.canonicalise import normalise_text
from transform.clean import GRAIN, clean_dataframe
from transform.parse import parse_arrival_date, parse_price

TODAY = date(2026, 8, 19)

COMMODITY_MAP = {"Onion": "Onion", "Potato": "Potato"}
MARKET_MAP = {
    ("Lasalgaon", "Nashik"): "Lasalgaon",
    ("Pune", "Pune"): "Pune",
}

SLOW = settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
)

# Deliberately messy: valid values, near-misses and outright junk.
prices = st.one_of(
    st.integers(min_value=-500, max_value=50000).map(str),
    st.floats(allow_nan=False, allow_infinity=False, width=32).map(
        lambda f: f"{f:.2f}"
    ),
    st.sampled_from(["", " ", "NR", "N/A", "-", "nan", "abc", "1,200", " 1200 ", None]),
)

dates = st.one_of(
    st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 1, 1)).map(
        lambda d: d.strftime("%d/%m/%Y")
    ),
    st.sampled_from(["", "32/13/2026", "2026-08-18", "18-08-2026", "not-a-date", None]),
)

names = st.sampled_from(
    ["Onion", "ONION", " onion ", "Potato", "Dragonfruit", "", None]
)
markets = st.sampled_from(["Lasalgaon", "lasalgaon", "Pune", "Nowhere", "", None])
districts = st.sampled_from(["Nashik", "Pune", "Agra", ""])
optional = st.sampled_from(["Red", "Local", "FAQ", "", None])


raw_rows = st.fixed_dictionaries(
    {
        "state": st.sampled_from(["Maharashtra", "Karnataka", ""]),
        "district": districts,
        "market": markets,
        "commodity": names,
        "variety": optional,
        "grade": optional,
        "arrival_date": dates,
        "min_price": prices,
        "max_price": prices,
        "modal_price": prices,
    }
)

raw_frames = st.lists(raw_rows, min_size=0, max_size=12).map(pd.DataFrame)


def _clean(frame):
    return clean_dataframe(frame, COMMODITY_MAP, MARKET_MAP, outlier_z=4.0)


# --- P1 --------------------------------------------------------------------


@SLOW
@given(raw=raw_frames)
def test_p1_conservation_holds_for_any_frame(raw):
    clean, rejected = _clean(raw)
    assert len(clean) + len(rejected) == len(raw)


# --- P2 / P3 ---------------------------------------------------------------


@SLOW
@given(raw=raw_frames)
def test_p2_price_ordering_holds(raw):
    clean, _ = _clean(raw)
    if clean.empty:
        return
    assert (clean["min_price_inr_qtl"] <= clean["modal_price_inr_qtl"]).all()
    assert (clean["modal_price_inr_qtl"] <= clean["max_price_inr_qtl"]).all()


@SLOW
@given(raw=raw_frames)
def test_p3_all_clean_prices_positive(raw):
    clean, _ = _clean(raw)
    if clean.empty:
        return
    for column in ("min_price_inr_qtl", "max_price_inr_qtl", "modal_price_inr_qtl"):
        assert (clean[column] > 0).all()


# --- P4 --------------------------------------------------------------------


@SLOW
@given(raw=raw_frames)
def test_p4_grain_is_unique(raw):
    clean, _ = _clean(raw)
    if clean.empty:
        return
    keys = pd.concat([clean[c].astype("string").fillna("") for c in GRAIN], axis=1)
    assert not keys.duplicated().any()


# --- P5 --------------------------------------------------------------------


@given(value=prices)
def test_p5_parse_price_never_nan_or_inf(value):
    try:
        result = parse_price(value)
    except ValidationError:
        return
    assert not math.isnan(result)
    assert not math.isinf(result)
    assert result > 0


# --- P6 --------------------------------------------------------------------


@given(value=dates)
def test_p6_parse_date_never_returns_future(value):
    try:
        result = parse_arrival_date(value, today=TODAY)
    except ValidationError:
        return
    assert result <= TODAY


# --- P7 --------------------------------------------------------------------


@SLOW
@given(raw=raw_frames)
def test_p7_cleaning_is_idempotent(raw):
    clean, _ = _clean(raw)
    again, rejected_again = _clean(clean)

    assert rejected_again.empty
    pd.testing.assert_frame_equal(
        clean.reset_index(drop=True), again.reset_index(drop=True)
    )


# --- P8 --------------------------------------------------------------------


@given(
    value=st.text(max_size=40)
    | st.sampled_from(["  Lasal  gaon ", "Nashik.", "Ｏｎｉｏｎ", "a b"])
)
def test_p8_normalise_text_is_idempotent(value):
    once = normalise_text(value)
    assert normalise_text(once) == once


def test_all_eight_properties_are_present():
    """Guards against a property being deleted rather than fixed."""
    for n in range(1, 9):
        prefix = f"test_p{n}_"
        assert any(name.startswith(prefix) for name in globals()), f"P{n} is missing"
