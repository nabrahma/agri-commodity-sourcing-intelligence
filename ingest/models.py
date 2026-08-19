"""Error hierarchy and record models shared by every stage of the pipeline.

Two ideas are load-bearing here:

1.  Every failure mode has its own exception type, all descending from
    ``SourcingError``.  Callers can therefore catch narrowly.  A bare
    ``except`` is forbidden project-wide (see build-spec §B.4).
2.  Records are modelled at three stages -- raw, clean, rejected -- so a
    row can never silently change meaning as it moves through the
    pipeline.  ``RawRecord`` is deliberately all-strings: parsing is a
    later, testable step, not an accident of ingestion.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class SourcingError(Exception):
    """Base for all project errors."""


class ConfigError(SourcingError):
    """Missing or invalid configuration/secret."""


class AuthError(SourcingError):
    """API rejected the key (401/403)."""


class FetchError(SourcingError):
    """Network/HTTP failure after all retries exhausted."""


class SchemaError(SourcingError):
    """API returned a payload that doesn't match the expected shape."""


class ValidationError(SourcingError):
    """A record failed a business rule; carries a reject_reason."""

    def __init__(self, reject_reason: str, message: str | None = None) -> None:
        self.reject_reason = reject_reason
        super().__init__(message or reject_reason)


class RejectReason(str, Enum):
    """Fixed vocabulary. Every quarantined row carries exactly one of these,
    and every one of them has a dedicated test."""

    UNPARSEABLE_DATE = "UNPARSEABLE_DATE"
    FUTURE_DATE = "FUTURE_DATE"
    UNPARSEABLE_PRICE = "UNPARSEABLE_PRICE"
    NON_POSITIVE_PRICE = "NON_POSITIVE_PRICE"
    MIN_GT_MAX = "MIN_GT_MAX"
    MODAL_OUT_OF_RANGE = "MODAL_OUT_OF_RANGE"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    UNKNOWN_COMMODITY = "UNKNOWN_COMMODITY"
    UNKNOWN_MARKET = "UNKNOWN_MARKET"
    DUPLICATE_GRAIN = "DUPLICATE_GRAIN"


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------


class RawRecord(BaseModel):
    """One record exactly as returned by the API. All strings, no casting."""

    state: str
    district: str | None = None
    market: str
    commodity: str
    variety: str | None = None
    grade: str | None = None
    arrival_date: str  # "DD/MM/YYYY" -- parsed later, deliberately
    min_price: str
    max_price: str
    modal_price: str


class CleanRecord(BaseModel):
    """A validated, typed, canonicalised observation."""

    arrival_date: date
    state: str
    district: str | None
    market_canonical: str
    commodity_canonical: str
    variety: str | None
    grade: str | None
    min_price_inr_qtl: float = Field(gt=0)
    max_price_inr_qtl: float = Field(gt=0)
    modal_price_inr_qtl: float = Field(gt=0)
    intraday_spread_pct: float
    source: str  # 'api' | 'backfill'
    fetched_at_utc: datetime


class RejectedRecord(BaseModel):
    raw: dict
    reject_reason: str
    rejected_at_utc: datetime
