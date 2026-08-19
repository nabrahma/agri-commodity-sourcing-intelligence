"""Phase 8 -- the data contract behind the dashboard.

The app itself is thin; what matters is that every file it reads exists,
is non-empty, and carries the columns the app names.
"""

from __future__ import annotations

import importlib

import pandas as pd
import pytest

from analytics.queries import materialise_all

CURRENCY_SUFFIXES = ("_inr", "_inr_qtl", "_pct")


@pytest.fixture
def app_with_data(synthetic_con, tmp_path, monkeypatch):
    """The dashboard module pointed at freshly materialised outputs."""
    app = importlib.import_module("dashboard.app")
    analytics_dir = tmp_path / "analytics"
    materialise_all(synthetic_con, ["Onion"], analytics_dir, min_markets=3, min_obs=1)

    monkeypatch.setattr(app, "ANALYTICS_DIR", analytics_dir)
    monkeypatch.setattr(
        app,
        "REQUIRED_PARQUET",
        {name: analytics_dir / f"{name}.parquet" for name in app.REQUIRED_PARQUET},
    )
    monkeypatch.setattr(
        app,
        "OPTIONAL_PARQUET",
        {name: analytics_dir / f"{name}.parquet" for name in app.OPTIONAL_PARQUET},
    )
    return app


# --- 8.1 -------------------------------------------------------------------


def test_all_required_parquet_exist(app_with_data):
    for name, path in app_with_data.REQUIRED_PARQUET.items():
        assert path.exists(), f"{name} is missing at {path}"


# --- 8.2 -------------------------------------------------------------------


def test_loaded_frames_non_empty(app_with_data):
    for name in app_with_data.REQUIRED_PARQUET:
        frame = app_with_data.load_frame(name)
        assert not frame.empty, f"{name} loaded empty"


# --- 8.3 -------------------------------------------------------------------


def test_loaded_frames_have_expected_columns(app_with_data):
    for name, columns in app_with_data.EXPECTED_COLUMNS.items():
        frame = app_with_data.load_frame(name)
        missing = [c for c in columns if c not in frame.columns]
        assert not missing, f"{name} is missing {missing}"


# --- 8.4 -------------------------------------------------------------------


def test_no_nulls_in_display_columns(app_with_data):
    for name, columns in app_with_data.EXPECTED_COLUMNS.items():
        frame = app_with_data.load_frame(name)
        for column in columns:
            assert frame[column].notna().all(), f"{name}.{column} has nulls"


# --- 8.5 -------------------------------------------------------------------


def test_currency_columns_are_numeric(app_with_data):
    for name in app_with_data.REQUIRED_PARQUET:
        frame = app_with_data.load_frame(name)
        for column in frame.columns:
            if column.endswith(CURRENCY_SUFFIXES):
                assert pd.api.types.is_numeric_dtype(frame[column]), f"{name}.{column}"


# --- 8.6 -------------------------------------------------------------------


def test_app_imports_without_error():
    module = importlib.import_module("dashboard.app")
    assert hasattr(module, "main")
    for name in (
        "tab_spread",
        "tab_seasonality",
        "tab_markets",
        "tab_simulation",
        "tab_sensitivity",
    ):
        assert callable(getattr(module, name)), name


# --- 8.7 -------------------------------------------------------------------


def test_no_api_calls_in_dashboard(project_root):
    """The dashboard reads parquet. It must never reach the network."""
    banned = ("httpx", "requests", "urllib", "socket", "ingest.client")
    for path in (project_root / "dashboard").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for token in banned:
            assert f"import {token}" not in source, f"{path.name} imports {token}"
            assert f"from {token}" not in source, f"{path.name} imports from {token}"


def test_missing_data_is_reported_not_faked(tmp_path, monkeypatch):
    """With no parquet at all, loaders return empty frames rather than
    inventing plausible numbers."""
    app = importlib.import_module("dashboard.app")
    monkeypatch.setattr(
        app,
        "REQUIRED_PARQUET",
        {n: tmp_path / f"{n}.parquet" for n in app.REQUIRED_PARQUET},
    )
    monkeypatch.setattr(app, "OPTIONAL_PARQUET", {})
    monkeypatch.setattr(app, "SIMULATION_DIR", tmp_path / "simulation")

    assert app.load_frame("spread").empty
    assert app.load_simulation_summary() == {}
    assert app.last_refreshed() == "no data yet"


def test_footer_names_source_and_units(project_root):
    source = (project_root / "dashboard" / "app.py").read_text(encoding="utf-8")
    assert "data.gov.in" in source
    assert "quintal" in source
    assert "LIMITATIONS.md" in source
