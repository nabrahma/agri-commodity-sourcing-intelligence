"""Shared fixtures.

Nothing here touches the network or the real warehouse.  Anything that
looks like data lives under ``tests/fixtures/`` -- the only directory in
the project where hand-written records are permitted.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def settings() -> dict[str, Any]:
    """Parsed ``config/settings.yaml``."""
    with open(PROJECT_ROOT / "config" / "settings.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="session")
def assumptions() -> dict[str, Any]:
    """Parsed ``config/assumptions.yaml``."""
    with open(PROJECT_ROOT / "config" / "assumptions.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="session")
def api_response_ok() -> dict[str, Any]:
    """A well-formed API payload, shaped exactly as build-spec §1.2."""
    with open(FIXTURES_DIR / "api_response_ok.json", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def api_response_empty() -> dict[str, Any]:
    with open(FIXTURES_DIR / "api_response_empty.json", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def api_response_malformed() -> dict[str, Any]:
    """A payload with no ``records`` key -- must provoke SchemaError."""
    with open(FIXTURES_DIR / "api_response_malformed.json", encoding="utf-8") as fh:
        return json.load(fh)


# -- synthetic warehouses --------------------------------------------------
#
# Every number these fixtures produce is calculable by hand. That is the
# only way to know the SQL is right rather than merely runnable.

import duckdb  # noqa: E402
import pandas as pd  # noqa: E402

from transform.warehouse import (  # noqa: E402
    build_dim_date,
    create_schema,
    update_market_inclusion,
)

SYNTH_START = date(2026, 1, 1)
SYNTH_DAYS = 60

# Three included markets at flat, distinct prices: min 1000, max 1500.
# Spread against the cheapest is therefore exactly 50.0% on every day.
SYNTH_MARKETS = {
    "Alpha": 1000.0,
    "Beta": 1200.0,
    "Gamma": 1500.0,
}
EXCLUDED_MARKET = ("Delta", 500.0)
SPARSE_MARKET = ("Sparse", 1100.0)
SPARSE_REPORTING_DAYS = 45


def _insert(con, rows: list[dict]) -> None:
    frame = pd.DataFrame(rows)
    con.register("_rows", frame)
    con.execute(
        """
        INSERT INTO fct_price_daily
        SELECT date_key, market_sk, commodity_sk, variety, grade,
               min_price_inr_qtl, max_price_inr_qtl, modal_price_inr_qtl,
               intraday_spread_pct, source, fetched_at_utc, is_outlier
        FROM _rows
        """
    )
    con.unregister("_rows")


def _fact(date_key, market_sk, modal, variety="Red", is_outlier=False):
    return {
        "date_key": date_key,
        "market_sk": market_sk,
        "commodity_sk": 1,
        "variety": variety,
        "grade": "FAQ",
        "min_price_inr_qtl": modal * 0.9,
        "max_price_inr_qtl": modal * 1.1,
        "modal_price_inr_qtl": modal,
        "intraday_spread_pct": 20.0,
        "source": "fixture",
        "fetched_at_utc": pd.Timestamp("2026-08-19"),
        "is_outlier": is_outlier,
    }


@pytest.fixture
def synthetic_con():
    """3 included markets x 1 commodity x 60 days, plus one excluded market,
    one sparse market and one flagged outlier."""
    con = duckdb.connect(":memory:")
    create_schema(con)
    con.execute("INSERT INTO dim_commodity VALUES (1, 'Onion')")

    markets = [*SYNTH_MARKETS.items(), EXCLUDED_MARKET, SPARSE_MARKET]
    for sk, (name, _price) in enumerate(markets, start=1):
        con.execute(
            "INSERT INTO dim_market (market_sk, market_canonical, district, state, "
            "lat, lon) VALUES (?, ?, 'Nashik', 'Maharashtra', 20.0, 74.0)",
            [sk, name],
        )

    rows: list[dict] = []
    for day in range(SYNTH_DAYS):
        date_key = SYNTH_START + timedelta(days=day)
        for sk, (name, price) in enumerate(markets, start=1):
            if name == SPARSE_MARKET[0]:
                # Reports on 45 of 60 days, including the first and last.
                reports = day < SPARSE_REPORTING_DAYS - 1 or day == SYNTH_DAYS - 1
                if not reports:
                    continue
            rows.append(_fact(date_key, sk, price))

    # A flagged 100x print at the cheapest market: must never set the maximum.
    rows.append(_fact(SYNTH_START, 1, 100000.0, variety="Spike", is_outlier=True))
    _insert(con, rows)

    build_dim_date(con)
    # Thresholds chosen so Alpha/Beta/Gamma/Sparse are included and Delta is not.
    update_market_inclusion(con, min_coverage_pct=70.0, min_observations=40)
    con.execute(
        "UPDATE dim_market SET is_included = FALSE WHERE market_canonical = ?",
        [EXCLUDED_MARKET[0]],
    )

    yield con
    con.close()


# Eleven months at 1000 and July at 2200: the mean of the twelve monthly
# averages is exactly 1100, so July's index is exactly 200.
SEASONAL_BASE = 1000.0
SEASONAL_PEAK_MONTH = 7
SEASONAL_PEAK = 2200.0


@pytest.fixture
def seasonal_con():
    """One market, one commodity, twelve months of 2025."""
    con = duckdb.connect(":memory:")
    create_schema(con)
    con.execute("INSERT INTO dim_commodity VALUES (1, 'Onion')")
    con.execute(
        "INSERT INTO dim_market (market_sk, market_canonical, lat, lon, is_included) "
        "VALUES (1, 'Alpha', 20.0, 74.0, TRUE)"
    )

    rows = []
    for month in range(1, 13):
        price = SEASONAL_PEAK if month == SEASONAL_PEAK_MONTH else SEASONAL_BASE
        for day in (1, 10, 20):
            rows.append(_fact(date(2025, month, day), 1, price))
    _insert(con, rows)
    build_dim_date(con)
    update_market_inclusion(con, min_coverage_pct=0.0, min_observations=0)

    yield con
    con.close()


# -- golden simulation panel -----------------------------------------------
#
# Deterministic by construction: no randomness, no clock. The frozen
# expected output lives in tests/fixtures/golden_simulation.json.

import math  # noqa: E402

GOLDEN_START = date(2025, 1, 6)
GOLDEN_DAYS = 371
GOLDEN_BASE = {"Home": 1600.0, "Near": 1500.0, "Far": 1400.0}
GOLDEN_COORDS = {
    "Home": (20.1425, 74.2377),
    "Near": (20.1425, 75.1958),  # ~100 km east
    "Far": (20.1425, 78.0716),  # ~400 km east
}


def golden_price(market: str, day: int) -> float:
    """Annual swing plus a monthly ripple. Rounded so the golden file is exact."""
    annual = 400.0 * math.sin(2 * math.pi * day / 365.0)
    monthly = 50.0 * math.sin(2 * math.pi * day / 30.0)
    return round(GOLDEN_BASE[market] + annual + monthly, 4)


@pytest.fixture(scope="session")
def golden_prices() -> pd.DataFrame:
    rows = [
        {
            "date": GOLDEN_START + timedelta(days=day),
            "market": market,
            "modal_price_inr_qtl": golden_price(market, day),
        }
        for day in range(GOLDEN_DAYS)
        for market in GOLDEN_BASE
    ]
    return pd.DataFrame(rows)


@pytest.fixture(scope="session")
def golden_markets() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"market_canonical": name, "lat": lat, "lon": lon}
            for name, (lat, lon) in GOLDEN_COORDS.items()
        ]
    )


@pytest.fixture(scope="session")
def golden_assumptions(assumptions) -> dict[str, Any]:
    """Real assumptions, pointed at the synthetic panel's home market."""
    return {**assumptions, "buyer": {**assumptions["buyer"], "home_market": "Home"}}


# -- end-to-end landing zone ------------------------------------------------
#
# Raw-shaped records for a full pipeline run. Deterministic, landed under
# `source=fixture`, and never presented as observed data.

E2E_MARKETS = {
    # market: (district, state, base price)
    "Lasalgaon": ("Nashik", "Maharashtra", 1600.0),
    "Pimpalgaon": ("Nashik", "Maharashtra", 1560.0),
    "Yeola": ("Nashik", "Maharashtra", 1580.0),
    "Pune": ("Pune", "Maharashtra", 1720.0),
    "Ahmednagar": ("Ahmednagar", "Maharashtra", 1500.0),
    "Solapur": ("Solapur", "Maharashtra", 1440.0),
    "Jalgaon": ("Jalgaon", "Maharashtra", 1480.0),
    "Aurangabad": ("Aurangabad", "Maharashtra", 1520.0),
}
E2E_START = date(2025, 1, 6)
E2E_DAYS = 364


def e2e_raw_records(days: int = E2E_DAYS) -> list[dict]:
    """Raw API-shaped records: strings throughout, exactly as landed."""
    records = []
    for offset in range(days):
        day = E2E_START + timedelta(days=offset)
        annual = 400.0 * math.sin(2 * math.pi * offset / 365.0)
        for market, (district, state, base) in E2E_MARKETS.items():
            modal = round(
                base + annual + 30.0 * math.sin(2 * math.pi * offset / 30.0), 2
            )
            records.append(
                {
                    "state": state,
                    "district": district,
                    "market": market,
                    "commodity": "Onion",
                    "variety": "Red",
                    "grade": "FAQ",
                    "arrival_date": day.strftime("%d/%m/%Y"),
                    "min_price": f"{modal * 0.85:.2f}",
                    "max_price": f"{modal * 1.15:.2f}",
                    "modal_price": f"{modal:.2f}",
                }
            )
    return records


@pytest.fixture
def e2e_root(tmp_path):
    """A throwaway project root: real config and seeds, empty data tree."""
    import shutil

    root = tmp_path / "project"
    root.mkdir()
    for directory in ("config", "seeds"):
        shutil.copytree(PROJECT_ROOT / directory, root / directory)
    for directory in ("raw", "processed", "quarantine", "warehouse"):
        (root / "data" / directory).mkdir(parents=True)
    (root / "docs").mkdir()
    return root


# -- source tree walking ----------------------------------------------------

SKIP_TREE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "data",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".hypothesis",
    "htmlcov",
    ".mypy_cache",
    "node_modules",
}


def walk_source_files(root: Path, suffixes: set[str]):
    """Tracked source files, pruning heavy directories during the walk
    rather than filtering afterwards."""
    import os

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_TREE_DIRS]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix in suffixes:
                yield path
