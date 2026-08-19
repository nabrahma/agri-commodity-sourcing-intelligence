"""Phase 1 -- API client. All HTTP mocked; nothing here touches the network."""

from __future__ import annotations

import httpx
import pytest
import respx

from ingest.client import MarketPriceAPIClient, _redact
from ingest.models import AuthError, ConfigError, FetchError, SchemaError

BASE_URL = "https://api.data.gov.in/resource"
RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
ENDPOINT = f"{BASE_URL}/{RESOURCE_ID}"
KEY = "test-key-abc123"


@pytest.fixture(autouse=True)
def _no_backoff_delay(monkeypatch):
    """Exercise the retry policy without paying its wall-clock backoff."""
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _seconds: None)


def make_client(**overrides) -> MarketPriceAPIClient:
    kwargs = {
        "api_key": KEY,
        "base_url": BASE_URL,
        "resource_id": RESOURCE_ID,
        "max_retries": 5,
        "sleep_seconds": 0.0,
    }
    kwargs.update(overrides)
    return MarketPriceAPIClient(**kwargs)


def page_payload(n_records: int, total: int = 45231, offset: int = 0) -> dict:
    return {
        "total": total,
        "count": n_records,
        "limit": "1000",
        "offset": str(offset),
        "records": [
            {
                "state": "Maharashtra",
                "district": "Nashik",
                "market": "Lasalgaon",
                "commodity": "Onion",
                "variety": "Red",
                "grade": "FAQ",
                "arrival_date": "18/08/2026",
                "min_price": "1200",
                "max_price": "1850",
                "modal_price": "1600",
            }
            for _ in range(n_records)
        ],
    }


# --- 1.1 / 1.2 -------------------------------------------------------------


def test_init_raises_on_empty_key():
    with pytest.raises(ConfigError):
        make_client(api_key="")


def test_init_raises_on_none_key():
    with pytest.raises(ConfigError):
        make_client(api_key=None)


# --- 1.3 / 1.4 -------------------------------------------------------------


@respx.mock
def test_builds_correct_url():
    route = respx.get(ENDPOINT).mock(
        return_value=httpx.Response(200, json=page_payload(1))
    )
    make_client().fetch_page(offset=0, limit=10)

    url = str(route.calls[0].request.url)
    assert RESOURCE_ID in url
    assert "format=json" in url
    assert "limit=10" in url
    assert "offset=0" in url


@respx.mock
def test_filters_use_keyword_suffix():
    route = respx.get(ENDPOINT).mock(
        return_value=httpx.Response(200, json=page_payload(1))
    )
    make_client().fetch_page(offset=0, limit=10, filters={"commodity": "Onion"})

    params = route.calls[0].request.url.params
    assert params["filters[commodity.keyword]"] == "Onion"
    assert "filters[commodity]" not in params


# --- 1.5 -------------------------------------------------------------------


@respx.mock
def test_fetch_page_returns_records_and_total(api_response_ok):
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=api_response_ok))

    result = make_client().fetch_page(offset=0, limit=1000)
    assert isinstance(result, tuple) and len(result) == 2

    records, total = result
    assert len(records) == len(api_response_ok["records"])
    assert total == 45231


# --- 1.6 / 1.7 -------------------------------------------------------------


@respx.mock
def test_fetch_page_raises_auth_on_401():
    respx.get(ENDPOINT).mock(return_value=httpx.Response(401))
    with pytest.raises(AuthError):
        make_client().fetch_page(offset=0, limit=10)


@respx.mock
def test_fetch_page_raises_auth_on_403():
    respx.get(ENDPOINT).mock(return_value=httpx.Response(403))
    with pytest.raises(AuthError):
        make_client().fetch_page(offset=0, limit=10)


# --- 1.8 -------------------------------------------------------------------


@respx.mock
def test_no_retry_on_400():
    route = respx.get(ENDPOINT).mock(return_value=httpx.Response(400))
    with pytest.raises(FetchError):
        make_client().fetch_page(offset=0, limit=10)
    assert route.call_count == 1


# --- 1.9 / 1.10 ------------------------------------------------------------


@respx.mock
def test_retries_on_429_then_succeeds():
    route = respx.get(ENDPOINT).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(429),
            httpx.Response(200, json=page_payload(2)),
        ]
    )
    records, _ = make_client().fetch_page(offset=0, limit=10)
    assert route.call_count == 3
    assert len(records) == 2


@respx.mock
def test_retries_on_500_then_succeeds():
    route = respx.get(ENDPOINT).mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(200, json=page_payload(2)),
        ]
    )
    records, _ = make_client().fetch_page(offset=0, limit=10)
    assert route.call_count == 2
    assert len(records) == 2


# --- 1.11 ------------------------------------------------------------------


@respx.mock
def test_raises_fetch_error_after_max_retries():
    route = respx.get(ENDPOINT).mock(return_value=httpx.Response(500))
    client = make_client(max_retries=3)
    with pytest.raises(FetchError):
        client.fetch_page(offset=0, limit=10)
    assert route.call_count == client.max_retries


# --- 1.12 / 1.13 -----------------------------------------------------------


@respx.mock
def test_raises_schema_error_on_missing_records_key():
    respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"total": 5}))
    with pytest.raises(SchemaError):
        make_client().fetch_page(offset=0, limit=10)


@respx.mock
def test_raises_schema_error_on_malformed_json():
    respx.get(ENDPOINT).mock(
        return_value=httpx.Response(
            200, content=b"not json", headers={"content-type": "application/json"}
        )
    )
    with pytest.raises(SchemaError):
        make_client().fetch_page(offset=0, limit=10)


# --- 1.14 / 1.15 / 1.16 ----------------------------------------------------


@respx.mock
def test_fetch_all_paginates_until_empty():
    route = respx.get(ENDPOINT).mock(
        side_effect=[
            httpx.Response(200, json=page_payload(1000, total=999999)),
            httpx.Response(200, json=page_payload(0, total=999999)),
        ]
    )
    records = make_client().fetch_all(page_size=1000)
    assert route.call_count == 2
    assert len(records) == 1000


@respx.mock
def test_fetch_all_stops_at_max_pages():
    respx.get(ENDPOINT).mock(
        return_value=httpx.Response(200, json=page_payload(1000, total=999999))
    )
    route = respx.routes[0]
    records = make_client().fetch_all(page_size=1000, max_pages=3)
    assert route.call_count == 3
    assert len(records) == 3000


@respx.mock
def test_fetch_all_increments_offset():
    route = respx.get(ENDPOINT).mock(
        side_effect=[
            httpx.Response(200, json=page_payload(1000, total=999999)),
            httpx.Response(200, json=page_payload(1000, total=999999)),
            httpx.Response(200, json=page_payload(0, total=999999)),
        ]
    )
    make_client().fetch_all(page_size=1000)
    offsets = [int(call.request.url.params["offset"]) for call in route.calls]
    assert offsets == [0, 1000, 2000]


# --- 1.17 ------------------------------------------------------------------


@respx.mock
def test_fetch_all_sleeps_between_pages(monkeypatch):
    respx.get(ENDPOINT).mock(
        side_effect=[
            httpx.Response(200, json=page_payload(1000, total=999999)),
            httpx.Response(200, json=page_payload(1000, total=999999)),
            httpx.Response(200, json=page_payload(0, total=999999)),
        ]
    )
    calls: list[float] = []
    monkeypatch.setattr("ingest.client.time.sleep", calls.append)

    make_client(sleep_seconds=1.0).fetch_all(page_size=1000)
    assert len(calls) == 2  # pages - 1
    assert all(seconds == 1.0 for seconds in calls)


# --- 1.18 / 1.19 -----------------------------------------------------------


@respx.mock
def test_api_key_redacted_in_error_message():
    respx.get(ENDPOINT).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchError) as excinfo:
        make_client(max_retries=2).fetch_page(offset=0, limit=10)
    assert KEY not in str(excinfo.value)
    assert "***REDACTED***" in str(excinfo.value)


@respx.mock
def test_api_key_redacted_in_logs(capsys):
    respx.get(ENDPOINT).mock(return_value=httpx.Response(500))
    with pytest.raises(FetchError):
        make_client(max_retries=2).fetch_page(offset=0, limit=10)

    captured = capsys.readouterr()
    assert KEY not in captured.out
    assert KEY not in captured.err


def test_redact_helper_removes_key():
    url = f"{ENDPOINT}?api-key={KEY}&format=json"
    assert KEY not in _redact(url)
    assert "format=json" in _redact(url)


# --- 1.20 ------------------------------------------------------------------


def test_timeout_is_applied(settings):
    client = make_client(timeout_seconds=settings["api"]["timeout_seconds"])
    assert client._client.timeout.read == float(settings["api"]["timeout_seconds"])
    assert client.timeout_seconds == settings["api"]["timeout_seconds"]
