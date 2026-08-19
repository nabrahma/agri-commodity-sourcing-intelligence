"""Regressions for defects the live API exposed that the spec did not predict.

Each of these cost a real debugging session against the running service, so
each has a test that fails loudly if the fix is ever reverted.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from ingest.backfill import (
    API_COLUMNS,
    load_historical_resources,
    normalise_history_record,
)
from ingest.client import DEFAULT_HEADERS, MarketPriceAPIClient
from ingest.land import land_records
from ingest.models import RawRecord
from transform.parse import parse_arrival_date

ENDPOINT = "https://api.data.gov.in/resource/RID"


def client(**kw):
    return MarketPriceAPIClient(
        "k", "https://api.data.gov.in/resource", "RID", sleep_seconds=0.0, **kw
    )


# --- the User-Agent defect -------------------------------------------------


def test_client_sends_a_user_agent():
    """Without a conventional User-Agent the API accepts the request and
    then never responds, so every call dies on read timeout."""
    assert "User-Agent" in DEFAULT_HEADERS
    assert DEFAULT_HEADERS["User-Agent"]
    assert "httpx" not in DEFAULT_HEADERS["User-Agent"].lower()
    assert client()._client.headers["user-agent"] == DEFAULT_HEADERS["User-Agent"]


@respx.mock
def test_user_agent_is_on_the_wire():
    route = respx.get(ENDPOINT).mock(
        return_value=httpx.Response(200, json={"total": 0, "records": []})
    )
    client().fetch_page(0, 10)

    sent = route.calls[0].request.headers["user-agent"]
    assert sent == DEFAULT_HEADERS["User-Agent"]


# --- numeric prices --------------------------------------------------------


def test_raw_record_accepts_numeric_prices():
    """The live feed sends prices as JSON numbers, not the strings the build
    spec assumed, and is inconsistent between rows."""
    record = RawRecord(
        state="Tamil Nadu",
        market="Madhuranthagam",
        commodity="Onion",
        arrival_date="19/08/2026",
        min_price=3000,
        max_price=3000.5,
        modal_price="3,000",
    )
    assert record.min_price == "3000"
    assert record.max_price == "3000.5"
    assert record.modal_price == "3,000", "strings pass through untouched"


def test_landing_zone_stores_mixed_types_as_text(tmp_path):
    """One column arriving as int in some rows and str in others cannot be
    written to parquet unless it is landed as text."""
    import pandas as pd

    records = [
        {"market": "A", "commodity": "Onion", "min_price": 1200, "grade": None},
        {"market": "B", "commodity": "Onion", "min_price": "0", "grade": "FAQ"},
    ]
    path = land_records(records, "backfill", "Onion", tmp_path)

    frame = pd.read_parquet(path)
    assert frame["min_price"].tolist() == ["1200", "0"]
    assert frame["grade"].isna().iloc[0], "null stays null, not the text 'None'"
    assert frame["grade"].iloc[1] == "FAQ"


# --- historical archive schema ---------------------------------------------


def test_parse_accepts_archive_iso_timestamp():
    """Archive years carry an ISO timestamp; only the date part is real."""
    from datetime import date

    assert parse_arrival_date("2023-01-06T13:38:19Z", today=date(2026, 8, 19)) == date(
        2023, 1, 6
    )
    assert parse_arrival_date("2022-05-06T13:38:19", today=date(2026, 8, 19)) == date(
        2022, 5, 6
    )


def test_normalise_history_record_maps_to_live_schema():
    record = {
        "_state_": "Maharashtra",
        "district": "Nashik",
        "market": "Lasalgaon",
        "commodity": "Onion",
        "variety": "Red",
        "arrival_date": "2022-05-06T13:38:19Z",
        "min_price": 1200,
        "max_price": 1850,
        "modal_price": 1600,
        "update_date": "2022-05-07T00:00:00Z",
    }
    out = normalise_history_record(record)

    assert tuple(out) == API_COLUMNS
    assert out["state"] == "Maharashtra"
    assert "update_date" not in out
    assert out["grade"] is None, "absent grade stays null, never invented"


def test_historical_registry_is_complete(project_root, settings):
    """Every in-scope commodity needs archive coverage, or the simulation
    silently runs on a shorter panel than the method claims."""
    resources = load_historical_resources(
        project_root / "seeds" / "historical_resources.yaml"
    )
    for commodity in settings["scope"]["commodities"]:
        assert commodity in resources, f"no historical archive listed for {commodity}"
        years = resources[commodity]
        assert len(years) >= 3, f"{commodity} has only {len(years)} archive years"
        assert all(isinstance(y, int) for y in years)


# --- rate limiting ---------------------------------------------------------


def test_crawl_loops_sleep_between_pages(monkeypatch, tmp_path):
    """The archive crawl is ~1,300 requests. Without pacing the API returns
    429 after roughly sixty of them."""
    import ingest.backfill as backfill

    slept: list[float] = []
    monkeypatch.setattr(backfill.time, "sleep", slept.append)

    class Pages:
        sleep_seconds = 1.5

        def __init__(self):
            self.calls = 0

        def fetch_page(self, offset, limit, filters=None):
            self.calls += 1
            return (
                [{"market": "A", "commodity": "Onion"}] if self.calls <= 3 else []
            ), 0

    backfill.run_history_backfill(
        Pages(), {"Onion": {2022: "RID"}}, tmp_path, page_size=1
    )
    assert slept, "the crawl never slept between pages"
    assert all(s == 1.5 for s in slept)


def test_retry_ceiling_is_long_enough_for_rate_limits():
    """A 429 needs a longer ceiling than a transient 5xx."""
    import inspect

    from ingest import client as client_module

    source = inspect.getsource(client_module.MarketPriceAPIClient.fetch_page)
    assert "wait_exponential" in source
    assert "max=120" in source, "429 backoff ceiling was lowered"


@respx.mock
def test_429_is_retried_not_fatal():
    route = respx.get(ENDPOINT).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, json={"total": 1, "records": [{"market": "A"}]}),
        ]
    )
    import tenacity

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(tenacity.nap.time, "sleep", lambda _s: None)
        records, _ = client().fetch_page(0, 10)

    assert route.call_count == 2
    assert len(records) == 1
