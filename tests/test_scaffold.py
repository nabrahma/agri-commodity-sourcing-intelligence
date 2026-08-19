"""Phase 0 -- scaffold, configuration and record models.

These eight tests exist so that a later phase can never be built on a
config file that quietly lost a key, or on assumptions that are
arithmetically impossible.
"""

from __future__ import annotations

import inspect
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError as PydanticValidationError

from ingest import models
from ingest.models import (
    AuthError,
    CleanRecord,
    ConfigError,
    FetchError,
    RawRecord,
    SchemaError,
    SourcingError,
    ValidationError,
)

# --- 0.1 -------------------------------------------------------------------

REQUIRED_SETTINGS = {
    "api": [
        "base_url",
        "resource_id",
        "page_size",
        "max_pages",
        "sleep_seconds",
        "timeout_seconds",
        "max_retries",
    ],
    "scope": ["commodities", "states"],
    "quality": [
        "min_coverage_pct",
        "min_observations",
        "min_markets_for_spread",
        "outlier_z_threshold",
    ],
    "paths": ["raw", "processed", "quarantine", "warehouse"],
}


def test_settings_loads(settings):
    """settings.yaml parses and every key the pipeline reads is present."""
    assert isinstance(settings, dict)
    for section, keys in REQUIRED_SETTINGS.items():
        assert section in settings, f"missing settings section: {section}"
        for key in keys:
            assert key in settings[section], f"missing settings key: {section}.{key}"

    assert settings["api"]["page_size"] > 0
    assert settings["api"]["max_retries"] >= 1
    assert settings["api"]["timeout_seconds"] > 0
    assert settings["scope"]["commodities"], "scope.commodities must not be empty"
    assert settings["scope"]["states"], "scope.states must not be empty"


# --- 0.2 -------------------------------------------------------------------


def test_assumptions_loads(settings, assumptions):
    """Every commodity in scope has a matching assumptions entry.

    A commodity in scope but absent here would be simulated against
    defaults invented at runtime -- exactly the silent fabrication the
    project forbids.
    """
    assert "commodities" in assumptions
    for commodity in settings["scope"]["commodities"]:
        assert commodity in assumptions["commodities"], (
            f"{commodity} is in scope.commodities but has no entry in "
            f"assumptions.commodities"
        )
        entry = assumptions["commodities"][commodity]
        assert "max_storage_weeks" in entry
        assert "shrinkage_ratio_per_week" in entry

    for section in ("buyer", "costs", "strategy_s3"):
        assert section in assumptions, f"missing assumptions section: {section}"


# --- 0.3 -------------------------------------------------------------------


def test_assumptions_are_sane(assumptions):
    """Arithmetically impossible assumptions fail here, not in Phase 6."""
    for commodity, entry in assumptions["commodities"].items():
        shrinkage = entry["shrinkage_ratio_per_week"]
        assert 0 < shrinkage < 1, f"{commodity}: shrinkage {shrinkage} not in (0, 1)"
        weeks = entry["max_storage_weeks"]
        assert weeks >= 1, f"{commodity}: max_storage_weeks {weeks} < 1"

    costs = assumptions["costs"]
    assert costs["transport_inr_per_qtl_per_100km"] > 0
    assert costs["storage_inr_per_qtl_per_week"] > 0
    # Commission is deliberately zero and excluded; see LIMITATIONS.md.
    assert costs["market_commission_pct"] >= 0

    buyer = assumptions["buyer"]
    assert buyer["monthly_requirement_tonnes"] > 0
    assert buyer["max_radius_km"] > 0
    assert buyer["home_market"]

    s3 = assumptions["strategy_s3"]
    assert 0 < s3["dip_trigger_ratio"] < 1
    assert s3["moving_average_days"] >= 1
    assert s3["max_multiple_of_need"] >= 1


# --- 0.4 -------------------------------------------------------------------


def test_exception_hierarchy():
    """Every project error descends from SourcingError, so callers can catch
    narrowly and never need a bare except."""
    for err in (ConfigError, AuthError, FetchError, SchemaError, ValidationError):
        assert issubclass(err, SourcingError), f"{err.__name__} is not a SourcingError"
    assert issubclass(SourcingError, Exception)

    # And no project error sneaks in outside that hierarchy.
    declared = {
        obj
        for _, obj in inspect.getmembers(models, inspect.isclass)
        if issubclass(obj, Exception) and obj.__module__ == models.__name__
    }
    assert declared == {
        SourcingError,
        ConfigError,
        AuthError,
        FetchError,
        SchemaError,
        ValidationError,
    }

    # ValidationError carries a machine-readable reason (Phase 3 depends on it).
    exc = ValidationError("UNPARSEABLE_PRICE")
    assert exc.reject_reason == "UNPARSEABLE_PRICE"


# --- 0.5 -------------------------------------------------------------------


def test_raw_record_accepts_valid(api_response_ok):
    """RawRecord builds from the fixture payload without casting anything."""
    records = api_response_ok["records"]
    assert records, "fixture must contain at least one record"

    for raw in records:
        rec = RawRecord(**raw)
        assert rec.market
        assert rec.commodity
        # Raw stays raw: prices are strings until transform/parse.py runs.
        assert isinstance(rec.min_price, str)
        assert isinstance(rec.modal_price, str)
        assert isinstance(rec.arrival_date, str)

    # Optional fields really are optional.
    minimal = RawRecord(
        state="Maharashtra",
        market="Lasalgaon",
        commodity="Onion",
        arrival_date="18/08/2026",
        min_price="1200",
        max_price="1850",
        modal_price="1600",
    )
    assert minimal.district is None
    assert minimal.variety is None
    assert minimal.grade is None


# --- 0.6 -------------------------------------------------------------------


def test_clean_record_rejects_zero_price():
    """A zero or negative price must never reach the warehouse."""
    base = {
        "arrival_date": date(2026, 8, 18),
        "state": "Maharashtra",
        "district": "Nashik",
        "market_canonical": "Lasalgaon",
        "commodity_canonical": "Onion",
        "variety": "Red",
        "grade": "FAQ",
        "min_price_inr_qtl": 1200.0,
        "max_price_inr_qtl": 1850.0,
        "modal_price_inr_qtl": 1600.0,
        "intraday_spread_pct": 54.17,
        "source": "api",
        "fetched_at_utc": datetime(2026, 8, 18, 6, 0, tzinfo=UTC),
    }
    assert CleanRecord(**base).modal_price_inr_qtl == 1600.0

    for field in ("min_price_inr_qtl", "max_price_inr_qtl", "modal_price_inr_qtl"):
        for bad in (0, -1.0):
            with pytest.raises(PydanticValidationError):
                CleanRecord(**{**base, field: bad})


# --- 0.7 -------------------------------------------------------------------


def test_directories_exist(project_root, settings):
    """Every path the pipeline writes to exists or can be created."""
    for name, rel in settings["paths"].items():
        path = project_root / rel
        # `warehouse` names a database file; the rest name directories.
        target = path.parent if name == "warehouse" else path
        assert (
            target.exists() and target.is_dir()
        ), f"settings.paths.{name} -> {target} is not an existing directory"

    for pkg in ("ingest", "transform", "analytics", "simulate"):
        assert (project_root / pkg / "__init__.py").exists(), f"{pkg} is not a package"


# --- 0.8 -------------------------------------------------------------------


def test_gitignore_blocks_secrets(project_root):
    """The API key must be impossible to commit by accident."""
    gitignore = (project_root / ".gitignore").read_text(encoding="utf-8")
    lines = {line.strip() for line in gitignore.splitlines()}
    assert ".env" in lines, ".gitignore must ignore .env"
    assert any(line.startswith("data/") for line in lines)
    assert "*.duckdb" in lines

    example = (project_root / ".env.example").read_text(encoding="utf-8")
    key_lines = [
        line for line in example.splitlines() if line.startswith("DATA_GOV_API_KEY=")
    ]
    assert len(key_lines) == 1, ".env.example must declare DATA_GOV_API_KEY once"
    assert key_lines[0].strip() == "DATA_GOV_API_KEY=", "the example carries no value"
