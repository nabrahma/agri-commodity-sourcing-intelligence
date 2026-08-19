"""Phase 3 -- date and price parsing."""

from __future__ import annotations

from datetime import date

import pytest
from freezegun import freeze_time

from ingest.models import RejectReason, ValidationError
from transform.parse import parse_arrival_date, parse_price

TODAY = date(2026, 8, 19)


# --- 3.1 - 3.7 : dates -----------------------------------------------------


def test_parse_date_ddmmyyyy():
    assert parse_arrival_date("18/08/2026", today=TODAY) == date(2026, 8, 18)


def test_parse_date_dashes():
    assert parse_arrival_date("18-08-2026", today=TODAY) == date(2026, 8, 18)


def test_parse_date_iso():
    assert parse_arrival_date("2026-08-18", today=TODAY) == date(2026, 8, 18)


def test_parse_date_ambiguous_is_ddmm():
    """05/06/2026 is 5 June, not 6 May. Getting this backwards would move
    every seasonal peak by up to eleven months."""
    assert parse_arrival_date("05/06/2026", today=TODAY) == date(2026, 6, 5)


def test_parse_date_invalid_raises():
    with pytest.raises(ValidationError) as excinfo:
        parse_arrival_date("32/13/2026", today=TODAY)
    assert excinfo.value.reject_reason == RejectReason.UNPARSEABLE_DATE


def test_parse_date_empty_raises():
    for value in ("", "   ", None):
        with pytest.raises(ValidationError) as excinfo:
            parse_arrival_date(value, today=TODAY)
        assert excinfo.value.reject_reason == RejectReason.UNPARSEABLE_DATE


@freeze_time("2026-08-19")
def test_parse_date_future_raises():
    with pytest.raises(ValidationError) as excinfo:
        parse_arrival_date("20/08/2026")
    assert excinfo.value.reject_reason == RejectReason.FUTURE_DATE

    # Today itself is fine, and the default `today` comes from the clock.
    assert parse_arrival_date("19/08/2026") == date(2026, 8, 19)


# --- 3.8 - 3.16 : prices ---------------------------------------------------


def test_parse_price_plain():
    assert parse_price("1200") == 1200.0


def test_parse_price_with_comma():
    assert parse_price("1,200") == 1200.0
    assert parse_price("1,20,000") == 120000.0


def test_parse_price_with_spaces():
    assert parse_price(" 1200 ") == 1200.0


def test_parse_price_decimal():
    assert parse_price("1200.50") == 1200.5
    assert parse_price("1200.00") == 1200.0


def test_parse_price_zero_raises():
    with pytest.raises(ValidationError) as excinfo:
        parse_price("0")
    assert excinfo.value.reject_reason == RejectReason.NON_POSITIVE_PRICE


def test_parse_price_negative_raises():
    with pytest.raises(ValidationError) as excinfo:
        parse_price("-50")
    assert excinfo.value.reject_reason == RejectReason.NON_POSITIVE_PRICE


def test_parse_price_nr_raises():
    for token in ("NR", "N/A", "-", "nan", "NA", "null", ""):
        with pytest.raises(ValidationError) as excinfo:
            parse_price(token)
        assert excinfo.value.reject_reason == RejectReason.UNPARSEABLE_PRICE, token


def test_parse_price_none_raises():
    with pytest.raises(ValidationError) as excinfo:
        parse_price(None)
    assert excinfo.value.reject_reason == RejectReason.UNPARSEABLE_PRICE


def test_parse_price_alpha_raises():
    with pytest.raises(ValidationError) as excinfo:
        parse_price("abc")
    assert excinfo.value.reject_reason == RejectReason.UNPARSEABLE_PRICE
