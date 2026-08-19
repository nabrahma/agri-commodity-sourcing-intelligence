"""String to typed value. Explicit formats only.

Date format inference is never used: DD/MM and MM/DD are indistinguishable
for the first twelve days of a month, and guessing wrong silently moves
every seasonal peak.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime

from ingest.models import RejectReason, ValidationError

DATE_FORMATS = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
    # The historical per-year archives carry an ISO timestamp rather than a
    # date. The time component is a bulk-upload artefact, not a trading time,
    # so only the date part is meaningful and only it is kept.
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
)

NULL_PRICE_TOKENS = frozenset(
    {"", "-", "--", "na", "n/a", "nr", "nan", "none", "null", "nil", "?"}
)

_THOUSANDS = re.compile(r"(?<=\d),(?=\d)")


def parse_arrival_date(value: str, today: date | None = None) -> date:
    """Parse 'DD/MM/YYYY', 'DD-MM-YYYY' or ISO 'YYYY-MM-DD'.

    Raises ValidationError(UNPARSEABLE_DATE) on failure, or (FUTURE_DATE)
    if the date is after `today`.
    """
    today = today or date.today()

    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        if value is None:
            raise ValidationError(RejectReason.UNPARSEABLE_DATE, "date is None")
        text = str(value).strip()
        if not text:
            raise ValidationError(RejectReason.UNPARSEABLE_DATE, "date is empty")

        parsed = None
        for fmt in DATE_FORMATS:
            try:
                parsed = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValidationError(
                RejectReason.UNPARSEABLE_DATE, f"unparseable date: {text!r}"
            )

    if parsed > today:
        raise ValidationError(
            RejectReason.FUTURE_DATE, f"date {parsed.isoformat()} is after {today}"
        )
    return parsed


def parse_price(value: str) -> float:
    """Parse a price string to float rupees per quintal.

    Raises ValidationError(UNPARSEABLE_PRICE) or (NON_POSITIVE_PRICE).
    """
    if value is None:
        raise ValidationError(RejectReason.UNPARSEABLE_PRICE, "price is None")

    if isinstance(value, bool):
        raise ValidationError(RejectReason.UNPARSEABLE_PRICE, "price is a boolean")

    if isinstance(value, int | float):
        number = float(value)
    else:
        text = _THOUSANDS.sub("", str(value).strip())
        if text.casefold() in NULL_PRICE_TOKENS:
            raise ValidationError(
                RejectReason.UNPARSEABLE_PRICE, f"null price token: {value!r}"
            )
        try:
            number = float(text)
        except ValueError as exc:
            raise ValidationError(
                RejectReason.UNPARSEABLE_PRICE, f"unparseable price: {value!r}"
            ) from exc

    if math.isnan(number) or math.isinf(number):
        raise ValidationError(
            RejectReason.UNPARSEABLE_PRICE, f"non-finite price: {value!r}"
        )
    if number <= 0:
        raise ValidationError(
            RejectReason.NON_POSITIVE_PRICE, f"non-positive price: {number}"
        )
    return number
