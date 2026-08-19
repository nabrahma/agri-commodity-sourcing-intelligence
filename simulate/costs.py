"""Unit conversion and the landed-cost model.

All prices are rupees per quintal. One tonne is ten quintals; a 10x slip
here would invalidate the headline number, so the constant is named and
tested rather than inlined.
"""

from __future__ import annotations

TONNES_TO_QUINTALS = 10.0
KM_PER_RATE_UNIT = 100.0


def tonnes_to_quintals(t: float) -> float:
    return float(t) * TONNES_TO_QUINTALS


def quintals_to_tonnes(qtl: float) -> float:
    return float(qtl) / TONNES_TO_QUINTALS


def transport_cost_inr_per_qtl(distance_km: float, rate_per_100km: float) -> float:
    """Linear in distance, zero at zero distance."""
    if distance_km < 0:
        raise ValueError(f"distance_km must not be negative: {distance_km}")
    return float(distance_km) / KM_PER_RATE_UNIT * float(rate_per_100km)


def landed_cost_inr_per_qtl(
    modal_price_inr_qtl: float, distance_km: float, rate_per_100km: float
) -> float:
    """Modal price plus transport."""
    return float(modal_price_inr_qtl) + transport_cost_inr_per_qtl(
        distance_km, rate_per_100km
    )


def apply_shrinkage(inventory_qtl: float, shrinkage_ratio: float) -> float:
    """Surviving inventory after one week in store. Never negative."""
    if not 0.0 <= shrinkage_ratio <= 1.0:
        raise ValueError(f"shrinkage_ratio must be in [0, 1]: {shrinkage_ratio}")
    return max(0.0, float(inventory_qtl) * (1.0 - float(shrinkage_ratio)))


def storage_cost_inr(inventory_qtl: float, rate_per_qtl_per_week: float) -> float:
    """Cost of holding `inventory_qtl` for one week."""
    return max(0.0, float(inventory_qtl)) * float(rate_per_qtl_per_week)
