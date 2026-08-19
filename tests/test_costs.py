"""Phase 6 -- unit conversion and cost model. Test 6.8 is the 100x guard."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulate.costs import (
    TONNES_TO_QUINTALS,
    apply_shrinkage,
    landed_cost_inr_per_qtl,
    quintals_to_tonnes,
    storage_cost_inr,
    tonnes_to_quintals,
    transport_cost_inr_per_qtl,
)

positive = st.floats(
    min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False
)
ratios = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)


def test_tonnes_to_quintals():
    """500 tonnes is 5,000 quintals. A slip here is a 10x error in the
    headline number, which is why it has its own test."""
    assert TONNES_TO_QUINTALS == 10.0
    assert tonnes_to_quintals(500) == 5000.0
    assert tonnes_to_quintals(1) == 10.0
    assert quintals_to_tonnes(tonnes_to_quintals(500)) == 500.0


def test_transport_zero_distance():
    assert transport_cost_inr_per_qtl(0.0, 4.0) == 0.0


def test_transport_linear():
    assert transport_cost_inr_per_qtl(200.0, 4.0) == 8.0
    assert transport_cost_inr_per_qtl(100.0, 4.0) == 4.0
    assert transport_cost_inr_per_qtl(50.0, 4.0) == 2.0


@settings(max_examples=100, deadline=None)
@given(a=positive, b=positive, rate=st.floats(min_value=0.0, max_value=100.0))
def test_transport_monotonic(a, b, rate):
    near, far = sorted((a, b))
    assert transport_cost_inr_per_qtl(far, rate) >= transport_cost_inr_per_qtl(
        near, rate
    )


def test_transport_rejects_negative_distance():
    with pytest.raises(ValueError):
        transport_cost_inr_per_qtl(-1.0, 4.0)


def test_landed_equals_modal_plus_transport():
    assert landed_cost_inr_per_qtl(1600.0, 200.0, 4.0) == 1608.0
    assert landed_cost_inr_per_qtl(1600.0, 0.0, 4.0) == 1600.0


def test_shrinkage_reduces_inventory():
    assert apply_shrinkage(100.0, 0.03) == pytest.approx(97.0)


@settings(max_examples=100, deadline=None)
@given(inventory=positive, ratio=ratios)
def test_shrinkage_never_negative(inventory, ratio):
    survived = apply_shrinkage(inventory, ratio)
    assert survived >= 0.0
    assert survived <= inventory + 1e-9


def test_shrinkage_zero_inventory():
    assert apply_shrinkage(0.0, 0.03) == 0.0


def test_shrinkage_full_loss_boundary():
    assert apply_shrinkage(100.0, 1.0) == 0.0
    assert apply_shrinkage(100.0, 0.0) == 100.0

    with pytest.raises(ValueError):
        apply_shrinkage(100.0, 1.5)


def test_storage_cost_zero_inventory():
    assert storage_cost_inr(0.0, 15.0) == 0.0


def test_storage_cost_linear():
    assert storage_cost_inr(100.0, 15.0) == 1500.0
    assert storage_cost_inr(200.0, 15.0) == 3000.0
