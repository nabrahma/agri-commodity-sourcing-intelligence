"""Phase 6 -- distance and radius filtering."""

from __future__ import annotations

import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulate.geo import haversine_km, markets_within_radius

MUMBAI = (19.0760, 72.8777)
DELHI = (28.7041, 77.1025)

coordinates = st.tuples(
    st.floats(min_value=-89.9, max_value=89.9, allow_nan=False),
    st.floats(min_value=-179.9, max_value=179.9, allow_nan=False),
)


def test_haversine_zero_distance():
    assert haversine_km(*MUMBAI, *MUMBAI) == 0.0


def test_haversine_known_pair():
    assert haversine_km(*MUMBAI, *DELHI) == pytest.approx(1150, abs=20)


def test_haversine_symmetric():
    assert haversine_km(*MUMBAI, *DELHI) == pytest.approx(haversine_km(*DELHI, *MUMBAI))


@settings(max_examples=100, deadline=None)
@given(a=coordinates, b=coordinates)
def test_haversine_never_negative(a, b):
    distance = haversine_km(*a, *b)
    assert distance >= 0.0
    assert distance <= 20100.0


def _markets_at(distances_km: list[float]) -> pd.DataFrame:
    """Markets due north of the origin at roughly the given distances."""
    return pd.DataFrame(
        {
            "market_canonical": [f"M{i}" for i in range(len(distances_km))],
            "lat": [d / 111.19492664455873 for d in distances_km],
            "lon": [0.0] * len(distances_km),
        }
    )


def test_radius_filter_inclusive_boundary():
    markets = _markets_at([500.0])
    result = markets_within_radius((0.0, 0.0), markets, radius_km=500.0)

    assert len(result) == 1
    assert result["distance_km"].iloc[0] == pytest.approx(500.0, abs=0.01)


def test_radius_filter_excludes_beyond():
    markets = _markets_at([501.0])
    assert markets_within_radius((0.0, 0.0), markets, radius_km=500.0).empty


def test_radius_filter_empty_result():
    markets = _markets_at([100.0, 200.0, 300.0])
    result = markets_within_radius((0.0, 0.0), markets, radius_km=1.0)

    assert result.empty
    assert "distance_km" in result.columns

    assert markets_within_radius((0.0, 0.0), markets.iloc[:0], 500.0).empty
