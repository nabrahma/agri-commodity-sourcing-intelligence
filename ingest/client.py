"""HTTP client for the data.gov.in daily market price resource.

Fetches and returns raw dicts. No parsing, no cleaning, no storage — a
transport bug and a parsing bug should never be able to look alike.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx
import structlog
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ingest.models import AuthError, ConfigError, FetchError, SchemaError

log = structlog.get_logger(__name__)

RETRYABLE_STATUS = {429}
REDACTED = "***REDACTED***"

_API_KEY_QS = re.compile(r"(api-key=)[^&\s]*", re.IGNORECASE)


def _redact(url: str) -> str:
    """Replace the api-key query value with a placeholder."""
    return _API_KEY_QS.sub(rf"\1{REDACTED}", str(url))


class _RetryableHTTPError(Exception):
    """Internal: a status worth retrying. Never escapes the client."""

    def __init__(self, status_code: int, url: str) -> None:
        self.status_code = status_code
        self.url = _redact(url)
        super().__init__(f"HTTP {status_code} for {self.url}")


class MarketPriceAPIClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        resource_id: str,
        timeout_seconds: int = 30,
        max_retries: int = 5,
        sleep_seconds: float = 1.0,
    ) -> None:
        if not api_key or not str(api_key).strip():
            raise ConfigError("api_key is empty or None")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.resource_id = resource_id
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.sleep_seconds = sleep_seconds
        self._client = httpx.Client(timeout=float(timeout_seconds))

    # -- internals ---------------------------------------------------------

    @property
    def url(self) -> str:
        return f"{self.base_url}/{self.resource_id}"

    def _params(
        self, offset: int, limit: int, filters: dict[str, str] | None
    ) -> dict[str, str]:
        params = {
            "api-key": self.api_key,
            "format": "json",
            "limit": str(limit),
            "offset": str(offset),
        }
        # Keyword-type fields need the .keyword suffix or the filter is ignored.
        for field, value in (filters or {}).items():
            params[f"filters[{field}.keyword]"] = value
        return params

    def _request(self, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = self._client.get(self.url, params=params)
        except (httpx.TimeoutException, httpx.ConnectError):
            log.warning("fetch.transport_error", url=_redact(self.url))
            raise

        status = response.status_code
        if status in (401, 403):
            raise AuthError(f"API rejected the key (HTTP {status})")
        if status in RETRYABLE_STATUS or status >= 500:
            raise _RetryableHTTPError(status, str(response.request.url))
        if status >= 400:
            raise FetchError(
                f"HTTP {status} for {_redact(str(response.request.url))} (not retried)"
            )

        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise SchemaError(
                f"response body is not valid JSON: {_redact(str(response.request.url))}"
            ) from exc

        if not isinstance(payload, dict) or "records" not in payload:
            raise SchemaError(
                "payload has no 'records' key: "
                f"{sorted(payload) if isinstance(payload, dict) else type(payload)}"
            )
        return payload

    def _log_retry(self, state: RetryCallState) -> None:
        exc = state.outcome.exception() if state.outcome else None
        log.warning(
            "fetch.retry",
            attempt=state.attempt_number,
            error=type(exc).__name__ if exc else None,
            status=getattr(exc, "status_code", None),
        )

    # -- public API --------------------------------------------------------

    def fetch_page(
        self,
        offset: int,
        limit: int,
        filters: dict[str, str] | None = None,
    ) -> tuple[list[dict], int]:
        """Fetch one page.

        Returns (records, total_available).

        Raises:
            AuthError   on 401/403
            FetchError  on network failure after max_retries
            SchemaError if the payload lacks a 'records' key
        """
        params = self._params(offset, limit, filters)

        @retry(
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.ConnectError, _RetryableHTTPError)
            ),
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=16),
            before_sleep=self._log_retry,
            reraise=True,
        )
        def _attempt() -> dict[str, Any]:
            return self._request(params)

        started = time.monotonic()
        try:
            payload = _attempt()
        except _RetryableHTTPError as exc:
            raise FetchError(
                f"giving up after {self.max_retries} attempts: "
                f"HTTP {exc.status_code} for {exc.url}"
            ) from exc
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise FetchError(
                f"giving up after {self.max_retries} attempts: "
                f"{type(exc).__name__} for {_redact(self.url)}"
            ) from exc

        records = payload.get("records") or []
        if not isinstance(records, list):
            raise SchemaError(f"'records' is {type(records).__name__}, expected list")
        total = int(payload.get("total") or 0)

        log.info(
            "fetch.page.complete",
            offset=offset,
            limit=limit,
            rows=len(records),
            total=total,
            elapsed_ms=round((time.monotonic() - started) * 1000),
            **{f"filter_{k}": v for k, v in (filters or {}).items()},
        )
        return records, total

    def fetch_all(
        self,
        filters: dict[str, str] | None = None,
        page_size: int = 1000,
        max_pages: int = 500,
    ) -> list[dict]:
        """Paginate until an empty page, `total` reached, or max_pages."""
        collected: list[dict] = []
        pages = 0

        for page in range(max_pages):
            if page > 0:
                time.sleep(self.sleep_seconds)
            offset = page * page_size
            records, total = self.fetch_page(offset, page_size, filters)
            pages += 1
            if not records:
                break
            collected.extend(records)
            if total and len(collected) >= total:
                break

        log.info(
            "fetch.all.complete",
            pages=pages,
            rows=len(collected),
            **{f"filter_{k}": v for k, v in (filters or {}).items()},
        )
        return collected

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> MarketPriceAPIClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
