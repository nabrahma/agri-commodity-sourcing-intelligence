"""Canonical names for commodities and markets.

Free-text names arrive with inconsistent case, spacing, unicode and
parentheticals. Unmapped names are rejected rather than passed through:
an unrecognised spelling silently becomes a separate market otherwise,
which deflates every coverage and spread figure that depends on it.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

from ingest.models import RejectReason, ValidationError

_WHITESPACE = re.compile(r"\s+")
_PARENTHETICAL = re.compile(r"\s*\([^)]*\)")
_TRAILING_PUNCT = re.compile(r"[\s.,;:\-_/]+$")


def normalise_text(value: str) -> str:
    """Strip, collapse internal whitespace, NFKC-normalise, title-case and
    drop trailing punctuation. Idempotent."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value))
    text = text.replace(" ", " ")
    text = _WHITESPACE.sub(" ", text).strip()
    text = _TRAILING_PUNCT.sub("", text)
    return text.title()


def _lookup_key(value: str) -> str:
    """Match key: normalised, parentheticals removed, case-folded."""
    return _PARENTHETICAL.sub("", normalise_text(value)).strip().casefold()


def canonical_commodity(raw: str, mapping: dict[str, str]) -> str:
    """Map a commodity variant onto its canonical name.

    Distinct commodities that merely share a prefix ('Onion Green') stay
    distinct: they are separate keys in the mapping.
    """
    folded = {str(k).casefold(): v for k, v in mapping.items()}

    direct = normalise_text(raw).casefold()
    if direct in folded:
        return folded[direct]

    stripped = _lookup_key(raw)
    if stripped in folded:
        return folded[stripped]

    raise ValidationError(
        RejectReason.UNKNOWN_COMMODITY, f"unmapped commodity: {raw!r}"
    )


def canonical_market(raw: str, district: str, mapping) -> str:
    """Map a market onto its canonical name.

    Market names are only unique within a district, so the lookup is keyed
    on both.
    """
    folded = {
        (str(market).casefold(), str(dist).casefold()): canonical
        for (market, dist), canonical in dict(mapping).items()
    }
    district_key = normalise_text(district).casefold()

    for market_key in (normalise_text(raw).casefold(), _lookup_key(raw)):
        if (market_key, district_key) in folded:
            return folded[(market_key, district_key)]

    raise ValidationError(
        RejectReason.UNKNOWN_MARKET,
        f"unmapped market: {raw!r} in district {district!r}",
    )


# -- seed loading ----------------------------------------------------------


def load_commodity_map(path: Path) -> dict[str, str]:
    """Read seeds/commodity_map.csv -> {raw_variant: canonical}."""
    mapping: dict[str, str] = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            mapping[row["raw_commodity"].strip()] = row["commodity_canonical"].strip()
    return mapping


def load_market_map(path: Path) -> dict[tuple[str, str], str]:
    """Read seeds/market_map.csv -> {(raw_market, district): canonical}."""
    mapping: dict[tuple[str, str], str] = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            key = (row["raw_market"].strip(), row["district"].strip())
            mapping[key] = row["market_canonical"].strip()
    return mapping


def load_market_geo(path: Path) -> dict[str, dict]:
    """Read seeds/market_map.csv -> {canonical: {state, district, lat, lon}}."""
    geo: dict[str, dict] = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            canonical = row["market_canonical"].strip()
            geo[canonical] = {
                "state": row.get("state", "").strip(),
                "district": row.get("district", "").strip(),
                "lat": float(row["lat"]) if row.get("lat", "").strip() else None,
                "lon": float(row["lon"]) if row.get("lon", "").strip() else None,
            }
    return geo
