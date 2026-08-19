# Agricultural Commodity Sourcing Intelligence — Agent Build Specification

**A phase-gated, test-driven implementation plan designed to be executed by an AI coding agent.**

| Field | Value |
|---|---|
| Version | 2.0 (agent-executable) |
| Owner | Nabaskar Brahma |
| Target | Data Analyst / Business Analyst portfolio project |
| Language | Python 3.12 |
| Phases | 12 (Phase 0 → Phase 11) |
| Test target | ≥ 85% line coverage on `ingest/`, `transform/`, `simulate/` |
| Build model | One phase per agent session. No phase starts until the previous phase's exit gate is green. |

---

# PART A — HOW TO USE THIS DOCUMENT

## A.1 The working agreement with your AI agent

Paste this block at the start of **every** agent session. It is the single most important thing in this document, because the failure mode with agent-built projects is not bad code — it is a plausible-looking pipeline that silently produces wrong numbers.

```
WORKING AGREEMENT — read before writing any code.

1. You are implementing exactly ONE phase from the build spec. Do not
   start the next phase. Do not "helpfully" scaffold future phases.
2. Write the tests FIRST, from the test case list in the phase. Show me
   the failing tests before you write the implementation.
3. Every function you write must match the signature in the spec exactly.
   If a signature seems wrong, STOP and tell me why. Do not change it
   silently.
4. NEVER invent, synthesise, mock, or fabricate real data outside of
   tests/fixtures/. If an API call fails, surface the error. A pipeline
   that silently produces plausible numbers is the worst possible outcome.
5. NEVER swallow an exception with a bare `except: pass`. Every caught
   exception is logged with context and either re-raised or recorded as
   a rejected record with a reason.
6. Do not proceed past a failing test. Do not comment out, skip, or
   xfail a test to make the suite green. If a test is genuinely wrong,
   explain why and ask.
7. Log every count: rows fetched, rows kept, rows rejected by reason.
   Unexplained row-count changes are bugs.
8. No secrets in code or committed files. Read from environment only.
9. At the end of the phase, run the phase's Exit Gate checklist and
   report each item as PASS or FAIL. Do not claim PASS without running it.
```

## A.2 Phase gate discipline

Every phase ends with an **Exit Gate**: a numbered checklist of commands to run and expected outputs. The rule is absolute:

> If any Exit Gate item fails, the phase is not done. Do not begin the next phase.

This is what makes an agent-built project error-free rather than merely finished.

## A.3 Test philosophy for this project

| Layer | What it tests | Speed | Count target |
|---|---|---|---|
| **Unit** | Pure functions: parsing, validation, maths, conversions | ms | ~70 tests |
| **Contract** | API client behaviour against mocked HTTP | ms | ~15 tests |
| **Property** | Invariants that must hold for any input (Hypothesis) | fast | ~8 tests |
| **Integration** | Phase-to-phase handoff on fixture data | seconds | ~12 tests |
| **Golden** | Full pipeline on a frozen fixture → known exact output | seconds | ~4 tests |
| **Smoke** | Real API, 10 records, run manually not in CI | seconds | 1 |

**Rules:**
- No test in CI touches the network. All HTTP is mocked with `respx`.
- Golden tests pin exact numbers. If a golden test breaks, either you introduced a bug or you deliberately changed the method — and if the latter, you update the golden file *in its own commit* with a message explaining why.
- Every reject reason in the cleaning layer has a dedicated test.

---

# PART B — GLOBAL SPECIFICATIONS

## B.1 Environment

```
Python 3.12
```

`requirements.txt` (pin exact versions at install time):

```
httpx
tenacity
pandas
pyarrow
duckdb
pydantic
python-dotenv
pyyaml
structlog
streamlit
plotly
pytest
pytest-cov
respx
hypothesis
freezegun
ruff
```

## B.2 Repository layout (create in full in Phase 0)

```
agri-commodity-sourcing-intelligence/
├── README.md
├── METHOD.md
├── LIMITATIONS.md
├── requirements.txt
├── pyproject.toml
├── Makefile
├── .env.example
├── .gitignore
├── config/
│   ├── settings.yaml
│   └── assumptions.yaml
├── ingest/
│   ├── __init__.py
│   ├── client.py
│   ├── models.py
│   ├── backfill.py
│   ├── daily.py
│   └── land.py
├── transform/
│   ├── __init__.py
│   ├── parse.py
│   ├── validate.py
│   ├── canonicalise.py
│   ├── clean.py
│   └── warehouse.py
├── analytics/
│   ├── __init__.py
│   ├── queries.py
│   └── sql/
│       ├── 01_spread.sql
│       ├── 02_seasonality.sql
│       ├── 03_volatility.sql
│       ├── 04_coverage.sql
│       └── 05_arrivals.sql
├── simulate/
│   ├── __init__.py
│   ├── geo.py
│   ├── costs.py
│   ├── strategies.py
│   ├── engine.py
│   └── sensitivity.py
├── dashboard/
│   └── app.py
├── seeds/
│   ├── commodity_map.csv
│   ├── market_map.csv
│   └── festivals.csv
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── api_response_ok.json
│   │   ├── api_response_empty.json
│   │   ├── api_response_malformed.json
│   │   ├── raw_dirty_sample.csv
│   │   ├── clean_expected.csv
│   │   └── golden_simulation.json
│   ├── test_client.py
│   ├── test_parse.py
│   ├── test_validate.py
│   ├── test_canonicalise.py
│   ├── test_clean.py
│   ├── test_warehouse.py
│   ├── test_queries.py
│   ├── test_geo.py
│   ├── test_costs.py
│   ├── test_strategies.py
│   ├── test_engine.py
│   ├── test_sensitivity.py
│   ├── test_properties.py
│   └── test_integration_e2e.py
├── data/
│   ├── raw/
│   ├── processed/
│   ├── quarantine/
│   └── warehouse/
├── docs/
│   ├── data_quality.md
│   ├── source_reconciliation.md
│   └── brief.md
└── .github/workflows/
    ├── ci.yml
    └── daily-pull.yml
```

## B.3 Naming and typing conventions

| Rule | Example |
|---|---|
| Money columns carry unit | `modal_price_inr_qtl` |
| Booleans prefix `is_` / `has_` | `is_included`, `has_valid_price` |
| Dates suffix `_date`, timestamps `_at_utc` | `arrival_date`, `fetched_at_utc` |
| Percentages suffix `_pct`, expressed 0–100 | `coverage_pct` |
| Ratios suffix `_ratio`, expressed 0–1 | `shrinkage_ratio` |
| Every SQL file line 1 is a `-- GRAIN:` comment | `-- GRAIN: one row per (date, commodity)` |
| No abbreviations except `qtl`, `pct`, `sk`, `fk` | |

**Critical unit rule:** all prices are **₹ per quintal (100 kg)**. 1 tonne = 10 quintals. This appears in a dedicated test module (`test_costs.py::test_tonnes_to_quintals`) because a 10× or 100× error here invalidates the entire headline finding.

## B.4 Error handling contract

```python
# ingest/models.py
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
```

Rules:
1. No bare `except`. Ever.
2. Catch narrowly, log with structured context, re-raise or quarantine.
3. Every quarantined record gets a machine-readable `reject_reason` from a fixed enum (§Phase 3).
4. The API key is redacted in every log line. There is a test for this.

## B.5 Logging

`structlog`, JSON output, one line per meaningful event with counts attached:

```python
log.info("fetch.page.complete", commodity="Onion", offset=3000,
         rows=1000, elapsed_ms=812)
log.warning("clean.reject", reason="MIN_GT_MAX", count=17)
```

## B.6 Configuration

`config/settings.yaml` — no magic numbers in code, ever:

```yaml
api:
  base_url: "https://api.data.gov.in/resource"
  resource_id: "9ef84268-d588-465a-a308-a864a43d0070"
  page_size: 1000
  max_pages: 500
  sleep_seconds: 1.0
  timeout_seconds: 30
  max_retries: 5

scope:
  commodities: ["Onion", "Potato", "Tomato"]
  states: ["Maharashtra", "Uttar Pradesh", "Karnataka",
           "Gujarat", "Madhya Pradesh", "Rajasthan",
           "West Bengal", "Bihar"]

quality:
  min_coverage_pct: 70.0
  min_observations: 200
  min_markets_for_spread: 10
  outlier_z_threshold: 4.0

paths:
  raw: "data/raw"
  processed: "data/processed"
  quarantine: "data/quarantine"
  warehouse: "data/warehouse/sourcing.duckdb"
```

`config/assumptions.yaml` — every business assumption in one auditable place:

```yaml
buyer:
  monthly_requirement_tonnes: 500
  purchase_frequency: "weekly"
  max_radius_km: 500
  home_market: "Lasalgaon"

costs:
  transport_inr_per_qtl_per_100km: 4.0
  storage_inr_per_qtl_per_week: 15.0
  market_commission_pct: 0.0        # explicitly excluded; see LIMITATIONS.md

commodities:
  Onion:
    max_storage_weeks: 12
    shrinkage_ratio_per_week: 0.03
  Potato:
    max_storage_weeks: 8
    shrinkage_ratio_per_week: 0.02
  Tomato:
    max_storage_weeks: 1
    shrinkage_ratio_per_week: 0.08

strategy_s3:
  dip_trigger_ratio: 0.90     # buy extra when price < 0.90 * MA20
  moving_average_days: 20
  max_multiple_of_need: 2.0
```

---

# PHASE 0 — SCAFFOLD & ENVIRONMENT

## 0.1 Objective

Create the complete repository skeleton, configuration, tooling, and a green (trivially passing) test suite. **No data logic yet.** This phase exists so that every later phase has somewhere correct to put its code.

## 0.2 Deliverables

- Full directory tree from §B.2 with `__init__.py` in every package
- `requirements.txt`, `pyproject.toml` (ruff + pytest config)
- `.env.example`, `.gitignore` (must include `.env`, `data/`, `*.duckdb`)
- `config/settings.yaml`, `config/assumptions.yaml` populated as above
- `Makefile` with: `install`, `test`, `lint`, `ingest`, `clean`, `build`, `analyse`, `simulate`, `dashboard`, `all`
- `ingest/models.py` with the exception hierarchy and Pydantic models
- `tests/conftest.py` with shared fixtures
- `.github/workflows/ci.yml` running ruff + pytest

## 0.3 Detailed spec

**`ingest/models.py`**

```python
from pydantic import BaseModel, Field
from datetime import date, datetime

class RawRecord(BaseModel):
    """One record exactly as returned by the API. All strings, no casting."""
    state: str
    district: str | None = None
    market: str
    commodity: str
    variety: str | None = None
    grade: str | None = None
    arrival_date: str          # "DD/MM/YYYY" — parsed later, deliberately
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
    source: str                # 'api' | 'backfill'
    fetched_at_utc: datetime

class RejectedRecord(BaseModel):
    raw: dict
    reject_reason: str
    rejected_at_utc: datetime
```

**`Makefile`**

```makefile
.PHONY: install test lint ingest clean build analyse simulate dashboard all

install:      ; pip install -r requirements.txt
lint:         ; ruff check . && ruff format --check .
test:         ; pytest -v --cov=ingest --cov=transform --cov=simulate --cov-report=term-missing
test-fast:    ; pytest -v -m "not slow"
ingest:       ; python -m ingest.daily
backfill:     ; python -m ingest.backfill
clean:        ; python -m transform.clean
build:        ; python -m transform.warehouse
analyse:      ; python -m analytics.queries
simulate:     ; python -m simulate.engine
sensitivity:  ; python -m simulate.sensitivity
dashboard:    ; streamlit run dashboard/app.py
all:          ; make clean build analyse simulate
```

## 0.4 Unit tests for this phase

| # | Test | Assertion |
|---|---|---|
| 0.1 | `test_settings_loads` | `settings.yaml` parses; all required keys present |
| 0.2 | `test_assumptions_loads` | `assumptions.yaml` parses; every commodity in `scope.commodities` has an entry in `commodities` |
| 0.3 | `test_assumptions_are_sane` | All shrinkage ratios in (0, 1); all storage weeks ≥ 1; costs > 0 |
| 0.4 | `test_exception_hierarchy` | Every custom exception subclasses `SourcingError` |
| 0.5 | `test_raw_record_accepts_valid` | `RawRecord` builds from the fixture payload |
| 0.6 | `test_clean_record_rejects_zero_price` | Pydantic raises on `modal_price_inr_qtl=0` |
| 0.7 | `test_directories_exist` | All paths in `settings.paths` exist or are creatable |
| 0.8 | `test_gitignore_blocks_secrets` | `.gitignore` contains `.env` |

## 0.5 Exit Gate

```
[ ] make install         → completes with no errors
[ ] make lint            → zero ruff violations
[ ] make test            → 8 passed
[ ] tree                 → matches §B.2 exactly
[ ] git status           → .env NOT listed as untracked-and-stageable
[ ] cat .env.example     → shows DATA_GOV_API_KEY= with no value
```

---

# PHASE 1 — API CLIENT

## 1.1 Objective

A robust, fully-tested HTTP client for the data.gov.in resource. **No cleaning, no storage, no business logic.** Fetch and return raw dicts.

## 1.2 Endpoint contract (verified)

```
GET https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070
  ?api-key=<KEY>
  &format=json
  &limit=1000
  &offset=0
  &filters[commodity.keyword]=Onion
  &filters[state.keyword]=Maharashtra
```

Response shape:

```json
{
  "index_name": "9ef84268-...",
  "total": 45231,
  "count": 1000,
  "limit": "1000",
  "offset": "0",
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
      "modal_price": "1600"
    }
  ]
}
```

Note: keyword-type fields require the `.keyword` suffix in filters. Prices arrive as **strings** and may contain thousands separators.

## 1.3 Detailed spec — `ingest/client.py`

```python
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
        """Raise ConfigError if api_key is empty or None."""

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

    def fetch_all(
        self,
        filters: dict[str, str] | None = None,
        page_size: int = 1000,
        max_pages: int = 500,
    ) -> list[dict]:
        """Paginate until an empty page, `total` reached, or max_pages.

        Sleeps `sleep_seconds` between pages. Logs every page with counts.
        """
```

**Retry policy** (use `tenacity`):
- Retry on: `httpx.TimeoutException`, `httpx.ConnectError`, HTTP 429, HTTP 5xx
- Do NOT retry on: 400, 401, 403, 404
- Exponential backoff: 1s, 2s, 4s, 8s, 16s
- After `max_retries`, raise `FetchError` with the last status and URL (key redacted)

**Key redaction** — implement and test:

```python
def _redact(url: str) -> str:
    """Replace the api-key query value with '***REDACTED***'."""
```

## 1.4 Unit tests — `tests/test_client.py`

All HTTP mocked via `respx`. **No network in CI.**

| # | Test name | Setup | Assertion |
|---|---|---|---|
| 1.1 | `test_init_raises_on_empty_key` | key=`""` | raises `ConfigError` |
| 1.2 | `test_init_raises_on_none_key` | key=`None` | raises `ConfigError` |
| 1.3 | `test_builds_correct_url` | mock 200 | request URL contains resource_id, `format=json` |
| 1.4 | `test_filters_use_keyword_suffix` | filters `{"commodity":"Onion"}` | URL contains `filters[commodity.keyword]=Onion` |
| 1.5 | `test_fetch_page_returns_records_and_total` | fixture `api_response_ok.json` | returns 2-tuple; len(records)==N; total==45231 |
| 1.6 | `test_fetch_page_raises_auth_on_401` | mock 401 | raises `AuthError` |
| 1.7 | `test_fetch_page_raises_auth_on_403` | mock 403 | raises `AuthError` |
| 1.8 | `test_no_retry_on_400` | mock 400 | exactly 1 request made |
| 1.9 | `test_retries_on_429_then_succeeds` | 429, 429, 200 | 3 requests; returns records |
| 1.10 | `test_retries_on_500_then_succeeds` | 500, 200 | 2 requests; returns records |
| 1.11 | `test_raises_fetch_error_after_max_retries` | always 500 | raises `FetchError`; request count == max_retries |
| 1.12 | `test_raises_schema_error_on_missing_records_key` | `{"total": 5}` | raises `SchemaError` |
| 1.13 | `test_raises_schema_error_on_malformed_json` | body = `"not json"` | raises `SchemaError` |
| 1.14 | `test_fetch_all_paginates_until_empty` | page1=1000 rows, page2=0 rows | 2 requests; 1000 records returned |
| 1.15 | `test_fetch_all_stops_at_max_pages` | always full pages | requests == max_pages |
| 1.16 | `test_fetch_all_increments_offset` | 3 pages | offsets are 0, 1000, 2000 |
| 1.17 | `test_fetch_all_sleeps_between_pages` | patch `time.sleep` | sleep called (pages-1) times |
| 1.18 | `test_api_key_redacted_in_error_message` | force `FetchError` | key string NOT in `str(exc)` |
| 1.19 | `test_api_key_redacted_in_logs` | capture logs | key string NOT in any log line |
| 1.20 | `test_timeout_is_applied` | inspect client | `timeout == settings.timeout_seconds` |

## 1.5 Manual smoke test (run once, not in CI)

```bash
python -c "
from ingest.client import MarketPriceAPIClient
import os
c = MarketPriceAPIClient(os.environ['DATA_GOV_API_KEY'],
                   'https://api.data.gov.in/resource',
                   '9ef84268-d588-465a-a308-a864a43d0070')
recs, total = c.fetch_page(offset=0, limit=10,
                           filters={'commodity': 'Onion'})
print('total available:', total)
print(recs[0])
"
```

**Expected:** a non-zero total and one record with the ten fields from §1.2. If field names differ from this spec, **stop and update the spec before writing any more code.** This is the single highest-value five minutes in the whole project.

## 1.6 Exit Gate

```
[ ] pytest tests/test_client.py -v   → 20 passed
[ ] Manual smoke test prints a real record
[ ] Field names in the live response match §1.2 exactly (or spec updated)
[ ] grep -r "DATA_GOV_API_KEY" --include=*.py  → only os.environ reads
[ ] make lint → clean
```

---

# PHASE 2 — INGESTION & LANDING

## 2.1 Objective

Pull data at scale, land it immutably, support resume-after-crash, and reconcile the API pull against a historical backfill.

## 2.2 Deliverables

- `ingest/land.py` — immutable partitioned parquet writer
- `ingest/daily.py` — incremental daily pull (cron entrypoint)
- `ingest/backfill.py` — one-time historical load + checkpointing
- `docs/source_reconciliation.md` — generated report

## 2.3 Landing zone contract

```
data/raw/
  source=api/pulled_date=2026-08-20/commodity=Onion/part-000.parquet
  source=backfill/pulled_date=2026-08-20/commodity=Onion/part-000.parquet
```

Every landed row carries three lineage columns appended to the raw fields:

| Column | Value |
|---|---|
| `fetched_at_utc` | ISO timestamp of the fetch |
| `source` | `api` or `backfill` |
| `ingest_run_id` | UUID4 per run |

**Immutability rule:** a partition path is written once. If it exists, either skip or write a new `part-NNN` — never overwrite. There is a test for this.

## 2.4 Checkpointing

`data/raw/_checkpoint.json`:

```json
{
  "runs": {
    "Onion": {"last_offset": 12000, "last_success_at_utc": "...",
              "status": "in_progress"}
  }
}
```

`backfill.py` reads the checkpoint on start and resumes from `last_offset`.

## 2.5 The history problem — implementation

This resource is a *current* daily price feed, so multi-year history must come from elsewhere. Implement all three paths:

| Path | Module | Behaviour |
|---|---|---|
| Forward accrual | `daily.py` | Runs daily via cron from day 1 of the build |
| Historical backfill | `backfill.py --from-csv <path>` | Loads a downloaded historical CSV, maps its columns to the API schema via `seeds/backfill_column_map.yaml` |
| Reconciliation | `backfill.py --reconcile` | Compares overlapping dates between sources |

**Reconciliation report** (`docs/source_reconciliation.md`) must contain:
- Overlapping date range and row counts per source
- Match rate on the join key `(arrival_date, market, commodity, variety)`
- Distribution of absolute % difference in `modal_price` where both exist
- Count of rows present in exactly one source
- A one-paragraph verdict you write yourself

## 2.6 Unit tests — `tests/test_land.py`, `tests/test_ingest.py`

| # | Test | Assertion |
|---|---|---|
| 2.1 | `test_land_writes_parquet` | file exists at expected partition path |
| 2.2 | `test_land_adds_lineage_columns` | `fetched_at_utc`, `source`, `ingest_run_id` present |
| 2.3 | `test_land_never_overwrites` | writing twice → two `part-` files, first unchanged (byte-compare) |
| 2.4 | `test_land_partition_path_format` | path matches `source=*/pulled_date=*/commodity=*` |
| 2.5 | `test_land_empty_input_writes_nothing` | no file created; warning logged |
| 2.6 | `test_checkpoint_created_on_first_run` | `_checkpoint.json` exists with status |
| 2.7 | `test_checkpoint_resumes_from_offset` | mock client; assert first request offset == checkpoint value |
| 2.8 | `test_checkpoint_marks_complete` | status becomes `complete` after empty page |
| 2.9 | `test_crash_midrun_leaves_resumable_checkpoint` | raise after page 2; checkpoint offset == 2000, status `in_progress` |
| 2.10 | `test_daily_pull_is_idempotent_per_day` | running twice same day → no duplicate rows after dedupe key |
| 2.11 | `test_backfill_column_mapping` | CSV with different headers maps to canonical schema |
| 2.12 | `test_backfill_rejects_unmapped_columns` | unknown header → `SchemaError` with the column named |
| 2.13 | `test_reconcile_computes_match_rate` | synthetic 10-row overlap, 8 matching → 80.0 |
| 2.14 | `test_reconcile_handles_zero_overlap` | returns report with `overlap_rows=0`, no crash, no divide-by-zero |
| 2.15 | `test_reconcile_flags_price_divergence` | one row differs 50% → appears in divergence table |

## 2.7 Exit Gate

```
[ ] pytest tests/test_land.py tests/test_ingest.py -v → 15 passed
[ ] make backfill runs end-to-end on real data
[ ] ls data/raw/ shows partitioned parquet
[ ] python -c "import duckdb; print(duckdb.sql(\"SELECT COUNT(*) FROM 'data/raw/**/*.parquet'\"))"
    → ≥ 50,000 rows
[ ] docs/source_reconciliation.md exists with a written verdict
[ ] Re-running backfill after Ctrl-C resumes rather than restarts
```

---

# PHASE 3 — CLEANING & VALIDATION

## 3.1 Objective

Turn raw strings into a validated, canonical, typed dataset — with **every rejection logged and reasoned**. This is the phase where analyst credibility is won or lost.

## 3.2 Reject reason enum (fixed — do not extend without updating tests)

```python
class RejectReason(str, Enum):
    UNPARSEABLE_DATE       = "UNPARSEABLE_DATE"
    FUTURE_DATE            = "FUTURE_DATE"
    UNPARSEABLE_PRICE      = "UNPARSEABLE_PRICE"
    NON_POSITIVE_PRICE     = "NON_POSITIVE_PRICE"
    MIN_GT_MAX             = "MIN_GT_MAX"
    MODAL_OUT_OF_RANGE     = "MODAL_OUT_OF_RANGE"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    UNKNOWN_COMMODITY      = "UNKNOWN_COMMODITY"
    UNKNOWN_MARKET         = "UNKNOWN_MARKET"
    DUPLICATE_GRAIN        = "DUPLICATE_GRAIN"
```

## 3.3 Function specs

**`transform/parse.py`**

```python
def parse_arrival_date(value: str, today: date | None = None) -> date:
    """Parse 'DD/MM/YYYY'. Also accept 'DD-MM-YYYY' and ISO 'YYYY-MM-DD'.

    Raises ValidationError(UNPARSEABLE_DATE) on failure.
    Raises ValidationError(FUTURE_DATE) if value > today.
    Never uses pandas' format inference — ambiguity between DD/MM and
    MM/DD would silently corrupt the entire seasonality analysis.
    """

def parse_price(value: str) -> float:
    """Parse a price string to float ₹/quintal.

    Handles: '1200', '1,200', ' 1200 ', '1200.00', '1200.0'
    Rejects: '', None, 'NR', 'N/A', '-', 'nan', non-numeric
    Raises ValidationError(UNPARSEABLE_PRICE) / (NON_POSITIVE_PRICE).
    """
```

**`transform/validate.py`**

```python
def validate_price_triple(
    min_p: float, max_p: float, modal_p: float
) -> None:
    """Raise ValidationError with the correct reason if:
       min > max              -> MIN_GT_MAX
       modal < min or > max   -> MODAL_OUT_OF_RANGE
    Boundary values (modal == min, modal == max) are VALID.
    """
```

**`transform/canonicalise.py`**

```python
def normalise_text(value: str) -> str:
    """Strip, collapse internal whitespace, title-case, NFKC-normalise
    unicode, remove trailing punctuation."""

def canonical_commodity(raw: str, mapping: dict[str, str]) -> str:
    """Map variants to canonical name. 'Onion Green' -> 'Onion Green'
    (distinct), 'ONION' / ' onion ' / 'Onion(Big)' -> 'Onion'.
    Raise ValidationError(UNKNOWN_COMMODITY) if unmapped."""

def canonical_market(raw: str, district: str, mapping) -> str:
    """Markets are only unique within a district — key on both."""
```

**`transform/clean.py`**

```python
def clean_dataframe(
    raw: pd.DataFrame,
    commodity_map: dict,
    market_map: dict,
    outlier_z: float = 4.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (clean_df, rejected_df).

    Order of operations (matters):
      1. Drop rows missing required fields
      2. Parse dates
      3. Parse prices
      4. Validate price triple
      5. Canonicalise commodity + market
      6. Deduplicate on grain, keeping max(fetched_at_utc)
      7. Compute intraday_spread_pct
      8. FLAG (never drop) outliers via robust z-score on log price
         within (market, commodity)

    INVARIANTS (assert before returning):
      - len(clean) + len(rejected) == len(raw)
      - clean has no nulls in required columns
      - clean has no min > max
      - clean grain is unique
    """
```

**Missing days are never interpolated.** If a market didn't report, the row simply does not exist. Silent interpolation would fabricate the very prices the analysis depends on.

## 3.4 Unit tests — `tests/test_parse.py`

| # | Test | Input | Expected |
|---|---|---|---|
| 3.1 | `test_parse_date_ddmmyyyy` | `"18/08/2026"` | `date(2026,8,18)` |
| 3.2 | `test_parse_date_dashes` | `"18-08-2026"` | `date(2026,8,18)` |
| 3.3 | `test_parse_date_iso` | `"2026-08-18"` | `date(2026,8,18)` |
| 3.4 | `test_parse_date_ambiguous_is_ddmm` | `"05/06/2026"` | `date(2026,6,5)` — **not** June 5 US-style |
| 3.5 | `test_parse_date_invalid_raises` | `"32/13/2026"` | `ValidationError(UNPARSEABLE_DATE)` |
| 3.6 | `test_parse_date_empty_raises` | `""` | `ValidationError` |
| 3.7 | `test_parse_date_future_raises` | tomorrow (freezegun) | `ValidationError(FUTURE_DATE)` |
| 3.8 | `test_parse_price_plain` | `"1200"` | `1200.0` |
| 3.9 | `test_parse_price_with_comma` | `"1,200"` | `1200.0` |
| 3.10 | `test_parse_price_with_spaces` | `" 1200 "` | `1200.0` |
| 3.11 | `test_parse_price_decimal` | `"1200.50"` | `1200.5` |
| 3.12 | `test_parse_price_zero_raises` | `"0"` | `NON_POSITIVE_PRICE` |
| 3.13 | `test_parse_price_negative_raises` | `"-50"` | `NON_POSITIVE_PRICE` |
| 3.14 | `test_parse_price_nr_raises` | `"NR"` | `UNPARSEABLE_PRICE` |
| 3.15 | `test_parse_price_none_raises` | `None` | `UNPARSEABLE_PRICE` |
| 3.16 | `test_parse_price_alpha_raises` | `"abc"` | `UNPARSEABLE_PRICE` |

## 3.5 Unit tests — `tests/test_validate.py`

| # | Test | Input (min,max,modal) | Expected |
|---|---|---|---|
| 3.17 | `test_valid_triple` | 1000, 2000, 1500 | no raise |
| 3.18 | `test_modal_equals_min_is_valid` | 1000, 2000, 1000 | no raise |
| 3.19 | `test_modal_equals_max_is_valid` | 1000, 2000, 2000 | no raise |
| 3.20 | `test_all_equal_is_valid` | 1500, 1500, 1500 | no raise |
| 3.21 | `test_min_gt_max_raises` | 2000, 1000, 1500 | `MIN_GT_MAX` |
| 3.22 | `test_modal_below_min_raises` | 1000, 2000, 900 | `MODAL_OUT_OF_RANGE` |
| 3.23 | `test_modal_above_max_raises` | 1000, 2000, 2100 | `MODAL_OUT_OF_RANGE` |

## 3.6 Unit tests — `tests/test_canonicalise.py`

| # | Test | Assertion |
|---|---|---|
| 3.24 | `test_normalise_strips_and_collapses` | `"  Lasal  gaon "` → `"Lasal Gaon"` |
| 3.25 | `test_normalise_unicode` | non-breaking space → normal space |
| 3.26 | `test_commodity_case_insensitive` | `"ONION"`, `"onion"` → `"Onion"` |
| 3.27 | `test_commodity_parenthetical` | `"Onion(Big)"` → `"Onion"` |
| 3.28 | `test_commodity_distinct_variant_preserved` | `"Onion Green"` stays distinct |
| 3.29 | `test_unknown_commodity_raises` | `"Dragonfruit"` → `UNKNOWN_COMMODITY` |
| 3.30 | `test_market_keyed_on_district` | same market name, two districts → two canonical keys |
| 3.31 | `test_unknown_market_raises` | unmapped → `UNKNOWN_MARKET` |

## 3.7 Unit tests — `tests/test_clean.py`

| # | Test | Assertion |
|---|---|---|
| 3.32 | `test_conservation_invariant` | `len(clean) + len(rejected) == len(raw)` on the dirty fixture |
| 3.33 | `test_every_reject_has_reason` | no null/empty `reject_reason` |
| 3.34 | `test_reject_reasons_are_enum_members` | all values ∈ `RejectReason` |
| 3.35 | `test_dedupe_keeps_latest_fetch` | two rows same grain → survivor has max `fetched_at_utc` |
| 3.36 | `test_dedupe_counts_rejected` | the loser appears in rejected with `DUPLICATE_GRAIN` |
| 3.37 | `test_clean_grain_is_unique` | no duplicate (date, market, commodity, variety, grade) |
| 3.38 | `test_intraday_spread_computed` | (1000,2000,1500) → 66.67% ±0.01 |
| 3.39 | `test_outliers_flagged_not_dropped` | 10× price row present in clean with `is_outlier=True` |
| 3.40 | `test_missing_days_not_interpolated` | gap in dates stays a gap; row count unchanged |
| 3.41 | `test_idempotent` | `clean(clean(x)) == clean(x)` |
| 3.42 | `test_empty_input` | returns two empty frames with correct columns, no crash |
| 3.43 | `test_all_rows_rejected` | fully-dirty input → clean is empty, no crash, invariant holds |
| 3.44 | `test_quarantine_file_written` | `data/quarantine/` has a file with the rejects |
| 3.45 | `test_data_quality_report_generated` | `docs/data_quality.md` contains counts per reason |

## 3.8 Property tests — `tests/test_properties.py`

Using Hypothesis:

| # | Property |
|---|---|
| P1 | For any generated raw frame: `len(clean) + len(rejected) == len(raw)` |
| P2 | For any clean output: `min_price ≤ modal_price ≤ max_price` |
| P3 | For any clean output: all prices > 0 |
| P4 | For any clean output: grain is unique |
| P5 | `parse_price` never returns NaN or inf |
| P6 | `parse_arrival_date` never returns a future date |
| P7 | Cleaning is idempotent for any input |
| P8 | `normalise_text` is idempotent |

## 3.9 Exit Gate

```
[ ] pytest tests/test_parse.py tests/test_validate.py tests/test_canonicalise.py
    tests/test_clean.py tests/test_properties.py -v  → 53 passed
[ ] make clean → produces data/processed/*.parquet
[ ] Conservation check on real data: raw_rows == clean_rows + reject_rows
[ ] docs/data_quality.md written, with a table of rejects by reason
[ ] Manually eyeball 20 random clean rows — do the prices look plausible
    for ₹/quintal? (Onion typically ~₹800–4,000/qtl)
[ ] coverage on transform/ ≥ 90%
```

> That last manual check is not optional. An agent can produce a fully green test suite over numbers that are off by 100×. Look at the data yourself.

---

# PHASE 4 — WAREHOUSE

## 4.1 Objective

Load clean data into a DuckDB star schema with enforced grain, referential integrity, and computed market-inclusion flags.

## 4.2 Deliverables

- `transform/warehouse.py` — DDL execution + loading + dim building
- `data/warehouse/sourcing.duckdb`
- `seeds/market_map.csv` with lat/lon for the top 40 markets
- `seeds/commodity_map.csv`
- `seeds/festivals.csv`

## 4.3 Schema

Exactly as specified in the previous PRD (§4.2 there): `dim_market`, `dim_commodity`, `dim_date`, `fct_price_daily`. Add:

```sql
ALTER TABLE fct_price_daily ADD COLUMN is_outlier BOOLEAN DEFAULT FALSE;
```

## 4.4 Market inclusion rule (implement exactly)

```sql
UPDATE dim_market SET
  coverage_pct = sub.coverage_pct,
  is_included  = (sub.coverage_pct >= 70.0 AND sub.obs >= 200)
FROM (
  SELECT market_sk,
         100.0 * COUNT(DISTINCT date_key)
              / (DATE_DIFF('day', MIN(date_key), MAX(date_key)) + 1) AS coverage_pct,
         COUNT(*) AS obs
  FROM fct_price_daily GROUP BY market_sk
) sub
WHERE dim_market.market_sk = sub.market_sk;
```

## 4.5 Geocoding step (manual, one afternoon)

The agent **cannot** reliably geocode. Human task:

1. Run `SELECT market_name, district, state, COUNT(*) FROM ... GROUP BY 1,2,3 ORDER BY 4 DESC LIMIT 50`
2. Look up lat/lon for each (Google Maps → right-click → copy coordinates)
3. Fill `seeds/market_map.csv`
4. Test 4.9 below will fail loudly until every included market has coordinates

## 4.6 Unit tests — `tests/test_warehouse.py`

| # | Test | Assertion |
|---|---|---|
| 4.1 | `test_ddl_creates_all_tables` | 4 tables exist |
| 4.2 | `test_ddl_is_idempotent` | running twice doesn't error or duplicate |
| 4.3 | `test_load_row_count_matches_source` | fct rows == clean parquet rows |
| 4.4 | `test_fact_grain_unique` | `COUNT(*) == COUNT(DISTINCT grain)` |
| 4.5 | `test_no_orphan_market_fk` | every `market_sk` in `dim_market` |
| 4.6 | `test_no_orphan_commodity_fk` | every `commodity_sk` in `dim_commodity` |
| 4.7 | `test_no_orphan_date_fk` | every `date_key` in `dim_date` |
| 4.8 | `test_dim_date_covers_full_range` | no gaps between min and max fact date |
| 4.9 | `test_included_markets_have_coordinates` | `is_included AND lat IS NULL` → 0 rows |
| 4.10 | `test_coverage_pct_computed_correctly` | synthetic: 7 of 10 days → 70.0 |
| 4.11 | `test_inclusion_boundary_exactly_70` | coverage 70.0, obs 200 → included |
| 4.12 | `test_inclusion_boundary_just_below` | coverage 69.9 → excluded |
| 4.13 | `test_inclusion_boundary_obs_199` | obs 199 → excluded |
| 4.14 | `test_fiscal_year_april_to_march` | 2026-03-31 → FY2025-26; 2026-04-01 → FY2026-27 |
| 4.15 | `test_reload_is_idempotent` | loading twice → same row count |
| 4.16 | `test_prices_positive_constraint` | inserting price 0 fails |

## 4.7 Exit Gate

```
[ ] pytest tests/test_warehouse.py -v → 16 passed
[ ] make build succeeds
[ ] duckdb data/warehouse/sourcing.duckdb "SELECT COUNT(*) FROM fct_price_daily"
    → ≥ 100,000
[ ] duckdb ... "SELECT COUNT(*) FROM dim_market WHERE is_included" → ≥ 30
[ ] Every included market has lat/lon (test 4.9 green)
[ ] Row-count reconciliation logged: raw → clean → warehouse
```

---

# PHASE 5 — ANALYTICS LAYER

## 5.1 Objective

Implement the five analytical queries as tested, parameterised, version-controlled SQL.

## 5.2 Deliverables

- `analytics/sql/*.sql` — five files, each with a `-- GRAIN:` line 1
- `analytics/queries.py` — loads, parameterises, executes, returns DataFrames
- `data/processed/analytics/*.parquet` — materialised outputs for the dashboard

## 5.3 Query specs

Use the SQL bodies from the previous PRD (Part 5) as the starting point. Each becomes a function:

```python
def spread_by_day(con, commodity: str, min_markets: int = 10) -> pd.DataFrame:
    """GRAIN: one row per (date, commodity).
    Excludes days with fewer than `min_markets` reporting markets."""

def seasonal_index(con, commodity: str) -> pd.DataFrame:
    """GRAIN: one row per (commodity, month). Index = 100 * month_avg / year_avg."""

def volatility_by_market(con, commodity: str, min_obs: int = 100) -> pd.DataFrame:
    """GRAIN: one row per (market, commodity, fiscal_year)."""

def coverage_report(con) -> pd.DataFrame:
    """GRAIN: one row per (market, commodity)."""
```

## 5.4 Unit tests — `tests/test_queries.py`

Build a **synthetic in-memory DuckDB** in `conftest.py` with hand-computed expected answers. This is the only way to know the SQL is right.

Fixture: 3 markets × 1 commodity × 60 days, with prices constructed so every answer is calculable by hand.

| # | Test | Assertion |
|---|---|---|
| 5.1 | `test_spread_matches_hand_calc` | known day: markets at 1000/1200/1500 → spread_pct == 50.0 |
| 5.2 | `test_spread_identifies_cheapest_market` | `cheapest_market` == the 1000 one |
| 5.3 | `test_spread_excludes_thin_days` | day with 3 markets and min_markets=10 → absent |
| 5.4 | `test_spread_excludes_non_included_markets` | excluded market's price doesn't affect result |
| 5.5 | `test_spread_empty_returns_empty_df` | no crash, correct columns |
| 5.6 | `test_seasonal_index_averages_to_100` | mean of 12 monthly indices ≈ 100 ± 0.5 |
| 5.7 | `test_seasonal_index_flat_prices_gives_100` | constant prices → every month == 100.0 |
| 5.8 | `test_seasonal_index_known_peak` | double price in July → July index == 200 (single-year synthetic) |
| 5.9 | `test_volatility_zero_for_constant` | constant price → cv == 0.0 |
| 5.10 | `test_volatility_matches_hand_calc` | known series → cv within 1e-6 |
| 5.11 | `test_volatility_respects_min_obs` | market with 99 obs excluded |
| 5.12 | `test_coverage_pct_matches_hand_calc` | 45 reporting days of 60 → 75.0 |
| 5.13 | `test_all_queries_have_grain_comment` | every `.sql` file line 1 starts `-- GRAIN:` |
| 5.14 | `test_no_sql_injection_via_params` | commodity `"'; DROP TABLE"` → parameterised, table survives |
| 5.15 | `test_outliers_excluded_from_spread` | flagged outlier doesn't set the max |

## 5.5 Exit Gate

```
[ ] pytest tests/test_queries.py -v → 15 passed
[ ] make analyse → writes parquet for all five outputs
[ ] Sanity read: median onion spread is between 5% and 200%
    (outside that range, something is wrong — investigate before proceeding)
[ ] Every SQL file starts with a GRAIN comment
```

---

# PHASE 6 — SIMULATION ENGINE

## 6.1 Objective

The headline deliverable. Three sourcing strategies, twelve months, one rupee number — with **no look-ahead bias**.

## 6.2 Deliverables

- `simulate/geo.py` — haversine distance
- `simulate/costs.py` — transport, storage, shrinkage, unit conversion
- `simulate/strategies.py` — S1, S2, S3 as pure decision functions
- `simulate/engine.py` — the week loop
- `tests/fixtures/golden_simulation.json` — frozen expected output

## 6.3 `simulate/geo.py`

```python
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km. Earth radius 6371.0 km."""

def markets_within_radius(
    home: tuple[float, float],
    markets: pd.DataFrame,
    radius_km: float,
) -> pd.DataFrame:
    """Filter to markets within radius. Includes a distance_km column."""
```

## 6.4 `simulate/costs.py`

```python
TONNES_TO_QUINTALS = 10.0   # 1 tonne = 10 quintals. Tested.

def tonnes_to_quintals(t: float) -> float: ...

def transport_cost_inr_per_qtl(distance_km: float, rate_per_100km: float) -> float:
    """Linear in distance. Zero at zero distance."""

def landed_cost_inr_per_qtl(modal_price, distance_km, rate_per_100km) -> float:
    """modal + transport."""

def apply_shrinkage(inventory_qtl: float, shrinkage_ratio: float) -> float:
    """Returns surviving inventory after one week. Never negative."""

def storage_cost_inr(inventory_qtl: float, rate_per_qtl_per_week: float) -> float: ...
```

## 6.5 `simulate/strategies.py` — the look-ahead firewall

**This is the most important design decision in the project.** Every strategy receives a `PriceView` object that structurally cannot expose future data:

```python
@dataclass(frozen=True)
class PriceView:
    """Prices available to a decision-maker AS OF `as_of_date`.

    The constructor filters the underlying frame to date <= as_of_date.
    There is no method that returns anything after as_of_date.
    This is a structural guarantee, not a convention.
    """
    as_of_date: date
    _frame: pd.DataFrame   # already filtered, private

    def current_prices(self) -> pd.DataFrame:
        """Prices on as_of_date only."""

    def trailing_mean(self, market: str, days: int) -> float | None:
        """Mean modal price over the `days` before as_of_date.
        Returns None if fewer than days//2 observations exist."""
```

Strategy signatures:

```python
def decide_s1(view: PriceView, need_qtl: float, home_market: str) -> Purchase: ...
def decide_s2(view: PriceView, need_qtl: float, candidates: pd.DataFrame) -> Purchase: ...
def decide_s3(view: PriceView, need_qtl: float, candidates: pd.DataFrame,
              inventory_qtl: float, storage_cap_qtl: float,
              params: S3Params) -> Purchase: ...
```

```python
@dataclass(frozen=True)
class Purchase:
    market: str
    quantity_qtl: float
    modal_price_inr_qtl: float
    transport_inr_qtl: float
    landed_inr_qtl: float
    total_inr: float
```

## 6.6 `simulate/engine.py`

```python
def run_simulation(
    prices: pd.DataFrame,
    strategy: str,               # 'S1' | 'S2' | 'S3'
    assumptions: dict,
    commodity: str,
    start: date, end: date,
) -> SimulationResult:
    """Week-by-week loop.

    INVARIANTS asserted every week:
      - inventory_qtl >= 0
      - inventory_qtl <= storage_cap_qtl
      - purchased_qtl >= 0
      - cumulative_delivered_qtl >= cumulative_required_qtl  (no shortfall)
      - every decision used only PriceView(as_of=week_start)
    """

@dataclass
class SimulationResult:
    strategy: str
    commodity: str
    weekly_log: pd.DataFrame        # audit trail, one row per week
    total_purchase_cost_inr: float
    total_transport_cost_inr: float
    total_storage_cost_inr: float
    total_shrinkage_loss_qtl: float
    total_cost_inr: float
    cost_per_qtl_delivered_inr: float
    weeks_with_shortfall: int
```

**The weekly log is a deliverable, not a debug artefact.** It goes in the repo. An interviewer who can trace week 23's decision to a specific price on a specific date will trust the headline number.

## 6.7 Unit tests — `tests/test_geo.py`

| # | Test | Assertion |
|---|---|---|
| 6.1 | `test_haversine_zero_distance` | same point → 0.0 |
| 6.2 | `test_haversine_known_pair` | Mumbai–Delhi ≈ 1150 km ± 20 |
| 6.3 | `test_haversine_symmetric` | d(a,b) == d(b,a) |
| 6.4 | `test_haversine_never_negative` | property test over random coords |
| 6.5 | `test_radius_filter_inclusive_boundary` | market at exactly 500 km with radius 500 → included |
| 6.6 | `test_radius_filter_excludes_beyond` | 501 km → excluded |
| 6.7 | `test_radius_filter_empty_result` | tiny radius → empty frame, no crash |

## 6.8 Unit tests — `tests/test_costs.py`

| # | Test | Assertion |
|---|---|---|
| 6.8 | `test_tonnes_to_quintals` | 500 t → 5000 qtl **(the 100× guard)** |
| 6.9 | `test_transport_zero_distance` | 0 km → ₹0 |
| 6.10 | `test_transport_linear` | 200 km at ₹4/100km → ₹8/qtl |
| 6.11 | `test_transport_monotonic` | property: longer distance → cost never decreases |
| 6.12 | `test_landed_equals_modal_plus_transport` | exact arithmetic |
| 6.13 | `test_shrinkage_reduces_inventory` | 100 qtl at 3% → 97.0 |
| 6.14 | `test_shrinkage_never_negative` | property over random inputs |
| 6.15 | `test_shrinkage_zero_inventory` | 0 → 0, no crash |
| 6.16 | `test_shrinkage_full_loss_boundary` | ratio 1.0 → 0.0 |
| 6.17 | `test_storage_cost_zero_inventory` | ₹0 |
| 6.18 | `test_storage_cost_linear` | 100 qtl at ₹15 → ₹1500 |

## 6.9 Unit tests — `tests/test_strategies.py` (the critical ones)

| # | Test | Assertion |
|---|---|---|
| 6.19 | **`test_price_view_excludes_future`** | `PriceView(as_of=D)._frame.date.max() <= D` |
| 6.20 | **`test_price_view_has_no_future_accessor`** | no public method returns date > as_of (introspect) |
| 6.21 | **`test_trailing_mean_excludes_as_of_day`** | strictly before as_of |
| 6.22 | `test_trailing_mean_insufficient_data` | 3 obs, window 20 → returns None |
| 6.23 | `test_s1_always_buys_home_market` | 52 weeks → market constant |
| 6.24 | `test_s1_buys_exact_need` | quantity == need every week |
| 6.25 | `test_s2_picks_lowest_landed_not_lowest_modal` | cheap-but-far vs dear-but-near → correct pick |
| 6.26 | `test_s2_equals_s1_when_only_home_in_radius` | radius 1 km → identical to S1 |
| 6.27 | `test_s2_never_costlier_when_transport_zero` | property over random price grids |
| 6.28 | `test_s2_no_candidates_raises` | empty candidate set → explicit error, not silent zero |
| 6.29 | `test_s3_buys_extra_below_trigger` | price 0.85 × MA20 → quantity == 2× need |
| 6.30 | `test_s3_buys_normal_above_trigger` | price 0.95 × MA20 → quantity == need |
| 6.31 | `test_s3_respects_storage_cap` | near-full inventory → buys only to cap |
| 6.32 | `test_s3_tomato_cannot_stockpile` | max_storage_weeks=1 → never exceeds need |
| 6.33 | `test_s3_uses_inventory_before_buying` | inventory 1250, need 1250 → buys 0 |
| 6.34 | `test_s3_no_ma_available_falls_back_to_s2` | first 20 days → behaves as S2 |

## 6.10 Unit tests — `tests/test_engine.py`

| # | Test | Assertion |
|---|---|---|
| 6.35 | `test_inventory_never_negative` | assert over all weeks |
| 6.36 | `test_inventory_never_exceeds_cap` | assert over all weeks |
| 6.37 | `test_no_shortfall_weeks` | `weeks_with_shortfall == 0` |
| 6.38 | `test_total_cost_equals_component_sum` | purchase + transport + storage == total |
| 6.39 | `test_weekly_log_row_count` | == number of weeks in range |
| 6.40 | `test_weekly_log_has_audit_columns` | date, market, price, qty, inventory, cost |
| 6.41 | `test_s1_deterministic` | two runs → byte-identical result |
| 6.42 | `test_missing_price_week_handled` | market silent that week → documented rule applied, no crash |
| 6.43 | `test_all_prices_missing_raises` | explicit error, never a fabricated number |
| 6.44 | **`test_golden_simulation`** | full run on frozen fixture == `golden_simulation.json` exactly |
| 6.45 | `test_zero_length_period` | start == end → empty result, no crash |
| 6.46 | `test_single_week_period` | works correctly |
| 6.47 | `test_cost_per_qtl_reasonable` | between ₹500 and ₹10,000 for onion — a sanity tripwire |

## 6.11 Exit Gate

```
[ ] pytest tests/test_geo.py tests/test_costs.py tests/test_strategies.py
    tests/test_engine.py -v  → 47 passed
[ ] make simulate → prints three totals and the saving
[ ] The saving is between 0% and 30%. If it's 60%, you have a bug —
    almost certainly the look-ahead firewall or a unit error. Investigate
    before proceeding.
[ ] Open the weekly log. Pick week 20. Manually verify that week's
    decision against the raw price data. Do this by hand, once.
[ ] tests/fixtures/golden_simulation.json committed
```

> The manual week-20 trace is worth more than any test. Do it.

---

# PHASE 7 — SENSITIVITY ANALYSIS

## 7.1 Objective

Convert a point estimate into a defensible range. This is what turns "I found ₹X" into "I found ₹X, and here is the assumption it depends on."

## 7.2 Spec

```python
def run_sensitivity(
    base_assumptions: dict,
    parameter_grid: dict[str, list[float]],
    commodity: str,
) -> pd.DataFrame:
    """One-at-a-time sensitivity. Returns one row per (parameter, value)
    with the resulting saving vs S1.

    Default grid:
      transport_inr_per_qtl_per_100km : [2, 4, 6]
      max_radius_km                   : [300, 500, 800]
      storage_inr_per_qtl_per_week    : [7.5, 15, 30]
      shrinkage_ratio_per_week        : [0.5x, 1x, 1.5x of base]
      dip_trigger_ratio               : [0.85, 0.90, 0.95]
      min_coverage_pct                : [60, 70, 80]
    """

def tornado_data(sensitivity_df: pd.DataFrame) -> pd.DataFrame:
    """Rank parameters by the range of outcomes they produce.
    The top row is your 'binding assumption'."""
```

## 7.3 Unit tests — `tests/test_sensitivity.py`

| # | Test | Assertion |
|---|---|---|
| 7.1 | `test_base_case_reproduces_phase6` | base params → identical to Phase 6 result |
| 7.2 | `test_grid_shape` | rows == sum of grid lengths |
| 7.3 | `test_higher_transport_reduces_saving` | monotonic decrease |
| 7.4 | `test_larger_radius_increases_or_holds_saving` | monotonic non-decrease |
| 7.5 | `test_tornado_ranks_by_range` | descending order verified |
| 7.6 | `test_sensitivity_no_mutation` | `base_assumptions` unchanged after run |
| 7.7 | `test_extreme_param_no_crash` | transport ₹1000/100km → saving may be negative, must not crash |
| 7.8 | `test_conclusion_stability_flag` | reports whether S2 > S1 across the whole grid |

## 7.4 Exit Gate

```
[ ] pytest tests/test_sensitivity.py -v → 8 passed
[ ] make sensitivity → tornado chart data written
[ ] You can state in one sentence which assumption is binding
[ ] You can state the saving as a RANGE, not a point
```

---

# PHASE 8 — DASHBOARD

## 8.1 Objective

A public, clickable Streamlit app plus a Power BI file. The Streamlit link is what you put in your resume; the `.pbix` is what puts "Power BI" on your skills line honestly.

## 8.2 Streamlit spec — `dashboard/app.py`

Five tabs matching the pages in the product PRD. Requirements:

- Reads **only** from materialised parquet in `data/processed/analytics/` — never recomputes, never hits the API
- Every ₹ figure labelled `₹/quintal` or `₹ lakh`
- Low-coverage markets rendered in grey with a tooltip explaining why
- An "Assumptions" expander on the simulation tab showing the full `assumptions.yaml`
- A permanent footer: data source, last refresh date, link to LIMITATIONS.md

## 8.3 Tests — `tests/test_dashboard.py`

Dashboards are hard to unit-test; test the data layer feeding them.

| # | Test | Assertion |
|---|---|---|
| 8.1 | `test_all_required_parquet_exist` | every file `app.py` loads is present |
| 8.2 | `test_loaded_frames_non_empty` | each has > 0 rows |
| 8.3 | `test_loaded_frames_have_expected_columns` | schema contract per file |
| 8.4 | `test_no_nulls_in_display_columns` | display columns have no nulls |
| 8.5 | `test_currency_columns_are_numeric` | dtype check |
| 8.6 | `test_app_imports_without_error` | `import dashboard.app` doesn't raise |
| 8.7 | `test_no_api_calls_in_dashboard` | grep: no `httpx`/`requests` in `dashboard/` |

## 8.4 Exit Gate

```
[ ] pytest tests/test_dashboard.py -v → 7 passed
[ ] streamlit run dashboard/app.py → loads, all 5 tabs render
[ ] Every interaction < 3 seconds
[ ] Deployed to Streamlit Community Cloud, public URL works in incognito
[ ] Screenshots saved to docs/screenshots/
```

---

# PHASE 9 — AUTOMATION & CI

## 9.1 Deliverables

- `.github/workflows/ci.yml` — lint + full test suite on every push
- `.github/workflows/daily-pull.yml` — scheduled ingestion, commits data
- Repo secret `DATA_GOV_API_KEY` configured
- Coverage badge in README

## 9.2 `ci.yml`

```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - run: ruff check .
      - run: ruff format --check .
      - run: pytest -v --cov=ingest --cov=transform --cov=simulate
                    --cov-report=term-missing --cov-fail-under=85
```

## 9.3 Tests

| # | Test | Assertion |
|---|---|---|
| 9.1 | `test_ci_workflow_valid_yaml` | parses |
| 9.2 | `test_daily_workflow_valid_yaml` | parses |
| 9.3 | `test_no_secrets_in_workflows` | no literal key strings |
| 9.4 | `test_ci_runs_full_suite` | workflow invokes pytest without `-k` filters |

## 9.4 Exit Gate

```
[ ] Push to GitHub → CI green
[ ] Coverage ≥ 85%
[ ] Manually trigger daily-pull → new commit with data appears
[ ] No secrets anywhere in git history (check with git log -p | grep)
```

---

# PHASE 10 — END-TO-END INTEGRATION

## 10.1 Objective

Prove the whole thing runs from a clean clone.

## 10.2 `tests/test_integration_e2e.py`

| # | Test | Assertion |
|---|---|---|
| 10.1 | `test_full_pipeline_on_fixtures` | mocked API → land → clean → warehouse → analyse → simulate, all in tmpdir |
| 10.2 | `test_row_counts_reconcile_across_stages` | raw == clean + rejected; warehouse == clean |
| 10.3 | `test_pipeline_idempotent` | running twice → identical warehouse row count |
| 10.4 | `test_pipeline_resumes_after_failure` | kill after clean; rerun completes |
| 10.5 | `test_no_network_calls_in_pipeline` | respx asserts zero unmocked requests |
| 10.6 | `test_headline_number_stable` | e2e on fixtures → matches golden ± 0.01 |
| 10.7 | `test_clean_clone_simulation` | fresh tmpdir + `make all` → exit 0 |

## 10.3 Exit Gate

```
[ ] pytest tests/test_integration_e2e.py -v → 7 passed
[ ] git clone into a fresh directory, make install && make all → works
[ ] Total test count ≥ 190
[ ] Full suite runs in < 90 seconds
```

---

# PHASE 11 — DOCUMENTATION & PACKAGING

## 11.1 Deliverables

| File | Content |
|---|---|
| `README.md` | Question → answer with the number → screenshot → links. Stack at the bottom. |
| `METHOD.md` | Every metric definition, every assumption, every threshold, the market inclusion rule |
| `LIMITATIONS.md` | The five limitations from the product PRD, verbatim |
| `docs/data_quality.md` | Generated: rejects by reason, coverage by market/month |
| `docs/source_reconciliation.md` | Generated: API vs backfill match rate |
| `docs/brief.md` → `brief.pdf` | The one-page recommendation |
| `docs/weekly_log_sample.csv` | Simulation audit trail |

## 11.2 The brief (write this yourself — do not let the agent write it)

The agent can generate the numbers. **You** write the interpretation. Structure:

1. **Question** (1 sentence)
2. **Method** (3 bullets)
3. **Finding 1** — spread, with the number
4. **Finding 2** — seasonality, with the number
5. **Finding 3** — strategy saving, with the range and the binding assumption
6. **Recommendation** — one action, one number
7. **Limitations** — 3 bullets

One page. PDF. Attach it to applications.

## 11.3 Tests

| # | Test | Assertion |
|---|---|---|
| 11.1 | `test_readme_has_headline_number` | README contains a `₹` figure |
| 11.2 | `test_all_docs_exist` | every file in §11.1 present |
| 11.3 | `test_no_todo_markers` | no `TODO`/`FIXME`/`XXX` in tracked files |
| 11.4 | `test_no_placeholder_values` | no `XX`, `TBD`, `<insert>` in README/METHOD |
| 11.5 | `test_assumptions_documented` | every key in `assumptions.yaml` appears in METHOD.md |

## 11.4 Final Exit Gate

```
[ ] pytest → all ≥ 190 tests pass
[ ] Coverage ≥ 85%
[ ] make lint → clean
[ ] CI green on main
[ ] Streamlit URL live
[ ] brief.pdf exists and is one page
[ ] README understandable in 60 seconds by a non-technical reader
[ ] You can explain every number in the brief without looking anything up
```

---

# PART C — TEST INVENTORY SUMMARY

| Phase | Module | Tests |
|---|---|---|
| 0 | Scaffold | 8 |
| 1 | API client | 20 |
| 2 | Ingestion & landing | 15 |
| 3 | Parse / validate / canonicalise / clean / properties | 53 |
| 4 | Warehouse | 16 |
| 5 | Analytics SQL | 15 |
| 6 | Geo / costs / strategies / engine | 47 |
| 7 | Sensitivity | 8 |
| 8 | Dashboard data | 7 |
| 9 | CI config | 4 |
| 10 | End-to-end | 7 |
| 11 | Documentation | 5 |
| **Total** | | **205** |

---

# PART D — AGENT PROMPT TEMPLATES

## D.1 Starting a phase

```
Read PHASE <N> of the build spec (attached).

Implement ONLY that phase. Follow the WORKING AGREEMENT.

Steps:
1. Restate the phase objective in one sentence.
2. List the files you will create or modify.
3. Write the tests from the phase's test table FIRST. Run them.
   Show me the failures.
4. Implement until green.
5. Run the Exit Gate checklist and report PASS/FAIL per line.

Do not start Phase <N+1>.
```

## D.2 When a test fails

```
Test <name> is failing. Before changing anything:
1. Tell me whether the TEST is wrong or the CODE is wrong, and why.
2. If the code is wrong, show me the minimal fix.
3. If the test is wrong, explain what the spec actually requires
   and wait for my confirmation before editing it.

Do not weaken, skip, or delete the test to make the suite green.
```

## D.3 Reviewing a phase (run this yourself every time)

```
Review your own Phase <N> work against the spec:
1. Does every function signature match the spec exactly?
2. Is there any `except` without a specific exception type?
3. Is there anywhere a number could be silently fabricated when data
   is missing?
4. Are all magic numbers in config, not code?
5. Could the API key leak into any log, error, or committed file?
6. Show me the three lines of code you are least confident about.
```

Question 6 is the most useful thing you can ask an agent. Ask it every phase.

---

# PART E — FAILURE MODES TO WATCH FOR

These are the specific ways this project goes wrong. Check each before you ship.

| # | Failure mode | Detection |
|---|---|---|
| 1 | **Unit error (100×)** — quintal/tonne confusion | Onion landed cost should be ~₹1,000–3,000/qtl. If it's ₹150,000, you have it. Test 6.8 guards this. |
| 2 | **Look-ahead leak** — strategy sees future prices | Saving looks implausibly large (> 30%). Tests 6.19–6.21 guard this. |
| 3 | **Date ambiguity** — DD/MM parsed as MM/DD | Seasonality peaks in the wrong month. Test 3.4 guards this. |
| 4 | **Silent interpolation** — agent fills missing days | Coverage % is suspiciously 100%. Test 3.40 guards this. |
| 5 | **Survivorship bias** — only well-reporting markets, unacknowledged | Named in LIMITATIONS.md; sensitivity on `min_coverage_pct` |
| 6 | **Row loss in a join** — records vanish between stages | Test 10.2 reconciles counts across all stages |
| 7 | **Fabricated data on API failure** | Working agreement rule 4; test 6.43 |
| 8 | **Outliers driving the spread metric** | Test 5.15; outliers flagged, excluded from spread |
| 9 | **Green tests over wrong numbers** | The mandatory manual checks: Phase 3 eyeball, Phase 6 week-20 trace |

> Failure mode 9 is the reason this document mandates two manual inspections. An AI agent will produce 205 passing tests over a dataset that is off by a factor of 100 and report complete success. Your eyes are the last line of defence, and using them is also exactly the analyst skill the project is meant to demonstrate.

---

# PART F — WHAT TO SAY IN THE INTERVIEW

Because none of this matters if you can't narrate it.

**On the architecture:** "Raw landing zone is immutable, so a parser bug is a re-parse rather than a re-crawl. Cleaning is separate from ingestion, so every rejection has a reason and a count. That's how I could tell you the missing-day rate without guessing."

**On the look-ahead firewall:** "The strategies take a PriceView object that's constructed filtered to the decision date. It's not a convention I followed — it's structurally impossible for a strategy to see a future price. There are three tests asserting it."

**On the number:** "₹X lakh, but the binding assumption is transport cost. At +50% it falls to ₹Y, and the strategy ranking holds. I'd want observed freight rates before I'd take this to a CFO."

**On what you didn't build:** "No forecasting model. The saving comes from spatial arbitrage observable at purchase time — a forecast would add error without changing the decision. I'd build one only if the buyer had to commit volume in advance."

**On what you'd do next:** "Add market commission and grading loss, which I've excluded and flagged. Then validate the transport assumption against a real freight quote, because it's the parameter everything hinges on."
