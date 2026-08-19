"""Phase 3 -- canonical commodity and market names."""

from __future__ import annotations

import pytest

from ingest.models import RejectReason, ValidationError
from transform.canonicalise import (
    canonical_commodity,
    canonical_market,
    normalise_text,
)

COMMODITY_MAP = {
    "Onion": "Onion",
    "Onion Big": "Onion",
    "Onion Green": "Onion Green",
    "Potato": "Potato",
}

MARKET_MAP = {
    ("Lasalgaon", "Nashik"): "Lasalgaon",
    ("Pune", "Pune"): "Pune",
    # Same market name, two districts -- two distinct canonical markets.
    ("Rampur", "Nashik"): "Rampur (Nashik)",
    ("Rampur", "Agra"): "Rampur (Agra)",
}


def test_normalise_strips_and_collapses():
    assert normalise_text("  Lasal  gaon ") == "Lasal Gaon"


def test_normalise_unicode():
    """A non-breaking space must collapse like an ordinary one."""
    assert normalise_text("Lasal gaon") == "Lasal Gaon"
    assert normalise_text("Ｏｎｉｏｎ") == "Onion"


def test_normalise_drops_trailing_punctuation():
    assert normalise_text("Nashik.") == "Nashik"
    assert normalise_text("Pune , ") == "Pune"


def test_commodity_case_insensitive():
    for raw in ("ONION", "onion", " Onion ", "oNiOn"):
        assert canonical_commodity(raw, COMMODITY_MAP) == "Onion", raw


def test_commodity_parenthetical():
    assert canonical_commodity("Onion(Big)", COMMODITY_MAP) == "Onion"
    assert canonical_commodity("Onion (Big)", COMMODITY_MAP) == "Onion"


def test_commodity_distinct_variant_preserved():
    """'Onion Green' is a different commodity, not a spelling of 'Onion'."""
    assert canonical_commodity("Onion Green", COMMODITY_MAP) == "Onion Green"
    assert canonical_commodity("onion green", COMMODITY_MAP) == "Onion Green"
    assert canonical_commodity("Onion", COMMODITY_MAP) == "Onion"


def test_unknown_commodity_raises():
    with pytest.raises(ValidationError) as excinfo:
        canonical_commodity("Dragonfruit", COMMODITY_MAP)
    assert excinfo.value.reject_reason == RejectReason.UNKNOWN_COMMODITY


def test_market_keyed_on_district():
    assert canonical_market("Rampur", "Nashik", MARKET_MAP) == "Rampur (Nashik)"
    assert canonical_market("Rampur", "Agra", MARKET_MAP) == "Rampur (Agra)"
    assert canonical_market("Lasalgaon", "Nashik", MARKET_MAP) == "Lasalgaon"


def test_unknown_market_raises():
    with pytest.raises(ValidationError) as excinfo:
        canonical_market("Nowhere", "Nashik", MARKET_MAP)
    assert excinfo.value.reject_reason == RejectReason.UNKNOWN_MARKET

    # A known market in the wrong district is also unknown.
    with pytest.raises(ValidationError):
        canonical_market("Lasalgaon", "Pune", MARKET_MAP)
