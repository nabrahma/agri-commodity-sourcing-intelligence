"""Daily incremental pull. Cron entrypoint.

Lands one partition per commodity per day. Re-running on the same day adds
a new part file rather than overwriting; the duplicate is resolved by the
dedupe step in transform/clean.py, never by mutating the landing zone.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import structlog

from ingest.client import MarketPriceAPIClient
from ingest.land import land_records, new_run_id

log = structlog.get_logger(__name__)


def run_daily(
    client: MarketPriceAPIClient,
    commodities: list[str],
    root: Path,
    page_size: int = 1000,
    max_pages: int = 500,
    pulled_date: date | None = None,
) -> dict[str, int]:
    """Pull today's records for each commodity and land them."""
    pulled_date = pulled_date or datetime.now(UTC).date()
    run_id = new_run_id()
    landed: dict[str, int] = {}

    for commodity in commodities:
        records = client.fetch_all(
            filters={"commodity": commodity},
            page_size=page_size,
            max_pages=max_pages,
        )
        land_records(
            records,
            source="api",
            commodity=commodity,
            root=root,
            pulled_date=pulled_date,
            ingest_run_id=run_id,
        )
        landed[commodity] = len(records)

    log.info("daily.complete", pulled_date=pulled_date.isoformat(), landed=landed)
    return landed


def main() -> int:
    from appconfig import get_api_key, load_settings, resolve_path

    settings = load_settings()
    api = settings["api"]
    with MarketPriceAPIClient(
        api_key=get_api_key(),
        base_url=api["base_url"],
        resource_id=api["resource_id"],
        timeout_seconds=api["timeout_seconds"],
        max_retries=api["max_retries"],
        sleep_seconds=api["sleep_seconds"],
    ) as client:
        run_daily(
            client,
            settings["scope"]["commodities"],
            resolve_path("raw"),
            page_size=api["page_size"],
            max_pages=api["max_pages"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
