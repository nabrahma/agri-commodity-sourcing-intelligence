"""Great-circle distance and radius filtering."""

from __future__ import annotations

import math

import pandas as pd

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, a)))


def markets_within_radius(
    home: tuple[float, float],
    markets: pd.DataFrame,
    radius_km: float,
) -> pd.DataFrame:
    """Markets no further than `radius_km` from home, with distance attached.

    The boundary is inclusive: a market at exactly the radius is reachable.
    """
    if markets.empty:
        return markets.assign(distance_km=pd.Series(dtype=float))

    lat, lon = home
    out = markets.copy()
    out["distance_km"] = [
        haversine_km(lat, lon, row_lat, row_lon)
        for row_lat, row_lon in zip(out["lat"], out["lon"], strict=True)
    ]
    return out[out["distance_km"] <= radius_km].reset_index(drop=True)
