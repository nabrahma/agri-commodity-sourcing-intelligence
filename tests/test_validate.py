"""Phase 3 -- price triple validation. Boundaries are valid."""

from __future__ import annotations

import pytest

from ingest.models import RejectReason, ValidationError
from transform.validate import validate_price_triple


def test_valid_triple():
    assert validate_price_triple(1000, 2000, 1500) is None


def test_modal_equals_min_is_valid():
    assert validate_price_triple(1000, 2000, 1000) is None


def test_modal_equals_max_is_valid():
    assert validate_price_triple(1000, 2000, 2000) is None


def test_all_equal_is_valid():
    assert validate_price_triple(1500, 1500, 1500) is None


def test_min_gt_max_raises():
    with pytest.raises(ValidationError) as excinfo:
        validate_price_triple(2000, 1000, 1500)
    assert excinfo.value.reject_reason == RejectReason.MIN_GT_MAX


def test_modal_below_min_raises():
    with pytest.raises(ValidationError) as excinfo:
        validate_price_triple(1000, 2000, 900)
    assert excinfo.value.reject_reason == RejectReason.MODAL_OUT_OF_RANGE


def test_modal_above_max_raises():
    with pytest.raises(ValidationError) as excinfo:
        validate_price_triple(1000, 2000, 2100)
    assert excinfo.value.reject_reason == RejectReason.MODAL_OUT_OF_RANGE
