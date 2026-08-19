"""Business rules on a parsed price triple."""

from __future__ import annotations

from ingest.models import RejectReason, ValidationError


def validate_price_triple(min_p: float, max_p: float, modal_p: float) -> None:
    """Raise ValidationError with the matching reason if the triple is
    inconsistent. Boundary values (modal == min, modal == max) are valid."""
    if min_p > max_p:
        raise ValidationError(
            RejectReason.MIN_GT_MAX, f"min {min_p} exceeds max {max_p}"
        )
    if modal_p < min_p or modal_p > max_p:
        raise ValidationError(
            RejectReason.MODAL_OUT_OF_RANGE,
            f"modal {modal_p} outside [{min_p}, {max_p}]",
        )
