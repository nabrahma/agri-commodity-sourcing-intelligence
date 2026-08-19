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


def test_chart_breaks_the_line_at_reporting_gaps():
    """A line drawn straight through a month of missing days shows the
    viewer prices that were never observed. The series must break."""
    import importlib

    app = importlib.import_module("dashboard.app")
    frame = pd.DataFrame(
        {
            "date_key": pd.to_datetime(
                ["2022-01-01", "2022-01-02", "2022-06-01", "2022-06-02"]
            ),
            "spread_pct": [10.0, 11.0, 12.0, 13.0],
        }
    )

    out = app.break_at_gaps(frame, "date_key")

    assert len(out) == len(frame) + 1, "no spacer inserted across the gap"
    assert out["spread_pct"].isna().sum() == 1
    # The break sits inside the gap, not on top of a real observation.
    spacer_date = out.loc[out["spread_pct"].isna(), "date_key"].iloc[0]
    assert pd.Timestamp("2022-01-02") < spacer_date < pd.Timestamp("2022-06-01")

    # A continuous series is returned untouched.
    dense = pd.DataFrame(
        {
            "date_key": pd.date_range("2022-01-01", periods=5, freq="D"),
            "spread_pct": [1.0, 2.0, 3.0, 4.0, 5.0],
        }
    )
    assert len(app.break_at_gaps(dense, "date_key")) == 5


def test_every_dashboard_input_is_committed(project_root):
    """The hosted app has only what git tracks.

    If an input stops being committed the public dashboard renders empty,
    and nothing else in the suite would notice.
    """
    import importlib
    import subprocess

    app = importlib.import_module("dashboard.app")
    tracked = set(
        subprocess.run(
            ["git", "ls-files"], cwd=project_root, capture_output=True, text=True
        ).stdout.split()
    )

    expected = [
        path.relative_to(app.PROJECT_ROOT).as_posix()
        for path in {**app.REQUIRED_PARQUET, **app.OPTIONAL_PARQUET}.values()
    ]
    expected.append(
        (app.SIMULATION_DIR / "summary.json").relative_to(app.PROJECT_ROOT).as_posix()
    )

    missing = [rel for rel in expected if rel not in tracked]
    assert not missing, f"not committed, so the hosted app cannot read them: {missing}"


def test_bulk_archive_is_not_committed(project_root):
    """The daily pull accrues in git; the 25 MB backfill never does.

    Forward accrual is small (~75 KB a day) and is the only persistence
    this project has. The historical archive is bulk and rebuilds in one
    command, so letting it into git is a habit worth catching early.
    """
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files", "data/raw"],
        cwd=project_root,
        capture_output=True,
        text=True,
    ).stdout.split()

    backfill = [f for f in tracked if "source=backfill" in f]
    assert not backfill, f"the bulk archive must stay out of git: {backfill[:3]}"
