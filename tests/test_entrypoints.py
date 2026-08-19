"""The `python -m ...` entrypoints, run in-process against a throwaway root.

These are the commands a human actually types, so they are worth testing
directly rather than only through the subprocess end-to-end check.
"""

from __future__ import annotations

import httpx
import pandas as pd
import pytest
import respx

import analytics.queries
import appconfig
import ingest.backfill
import ingest.daily
import simulate.engine
import simulate.sensitivity
import transform.clean
import transform.warehouse
from ingest.land import land_records
from ingest.models import ConfigError
from tests.conftest import e2e_raw_records

ENDPOINT = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
COMMODITY = "Onion"


@pytest.fixture
def rooted(e2e_root, monkeypatch):
    """Point every module's config lookup at the throwaway root."""
    monkeypatch.setattr(appconfig, "PROJECT_ROOT", e2e_root)
    monkeypatch.setattr(appconfig, "CONFIG_DIR", e2e_root / "config")
    appconfig.load_settings.cache_clear()
    appconfig.load_assumptions.cache_clear()
    yield e2e_root
    appconfig.load_settings.cache_clear()
    appconfig.load_assumptions.cache_clear()


@pytest.fixture
def landed(rooted):
    # 250 days clears the 200-observation inclusion floor in settings.yaml,
    # so markets actually qualify and the simulation has prices to use.
    land_records(
        e2e_raw_records(days=250),
        "fixture",
        COMMODITY,
        rooted / "data" / "raw",
    )
    return rooted


def test_clean_main_writes_outputs(landed, capsys):
    assert transform.clean.main() == 0

    clean_path = landed / "data" / "processed" / "clean.parquet"
    assert clean_path.exists()
    assert len(pd.read_parquet(clean_path)) > 0
    assert (landed / "docs" / "data_quality.md").exists()


def test_clean_main_reports_missing_input(rooted):
    """No landed data is an error with a message, not a silent empty run."""
    assert transform.clean.main() == 1


def test_warehouse_main_builds_and_reconciles(landed, capsys):
    assert transform.clean.main() == 0
    assert transform.warehouse.main() == 0

    assert (landed / "data" / "warehouse" / "sourcing.duckdb").exists()
    printed = capsys.readouterr().out
    assert "fact rows" in printed
    assert "dim_market_included" in printed


def test_warehouse_main_reports_missing_input(rooted):
    assert transform.warehouse.main() == 1


def test_analytics_main_materialises(landed):
    transform.clean.main()
    transform.warehouse.main()

    assert analytics.queries.main() == 0
    analytics_dir = landed / "data" / "processed" / "analytics"
    for name in ("spread", "seasonality", "volatility", "coverage"):
        assert (analytics_dir / f"{name}.parquet").exists()


def test_analytics_main_reports_missing_warehouse(rooted):
    assert analytics.queries.main() == 1


def test_simulate_main_prints_three_totals(landed, capsys):
    transform.clean.main()
    transform.warehouse.main()

    assert simulate.engine.main() == 0
    printed = capsys.readouterr().out
    for strategy in ("S1:", "S2:", "S3:"):
        assert strategy in printed
    assert "saving vs S1" in printed

    simulation = landed / "data" / "processed" / "simulation"
    assert (simulation / "summary.json").exists()
    for strategy in ("S1", "S2", "S3"):
        assert (simulation / f"weekly_log_{strategy}.parquet").exists()


def test_simulate_main_reports_missing_warehouse(rooted):
    assert simulate.engine.main() == 1


def test_sensitivity_main_writes_tornado(landed, capsys, monkeypatch):
    transform.clean.main()
    transform.warehouse.main()

    # Two parameters exercise every path through main(); the full six-way
    # grid is covered by test_sensitivity.py and just costs wall clock here.
    monkeypatch.setattr(
        simulate.sensitivity,
        "DEFAULT_GRID",
        {
            "transport_inr_per_qtl_per_100km": [2.0, 4.0, 6.0],
            "max_radius_km": [300.0, 500.0],
        },
    )

    assert simulate.sensitivity.main() == 0
    printed = capsys.readouterr().out
    assert "binding assumption" in printed
    assert "saving range across the grid" in printed

    analytics_dir = landed / "data" / "processed" / "analytics"
    assert (analytics_dir / "sensitivity.parquet").exists()
    assert (analytics_dir / "tornado.parquet").exists()


def test_sensitivity_main_reports_missing_warehouse(rooted):
    assert simulate.sensitivity.main() == 1


@respx.mock
def test_daily_main_lands_a_partition(rooted, monkeypatch):
    records = e2e_raw_records(days=2)
    respx.get(url__startswith=ENDPOINT).mock(
        side_effect=[
            httpx.Response(200, json={"total": len(records), "records": records}),
            httpx.Response(200, json={"total": len(records), "records": []}),
        ]
        * 3
    )
    monkeypatch.setenv("DATA_GOV_API_KEY", "test-key")

    assert ingest.daily.main() == 0
    assert list((rooted / "data" / "raw").rglob("*.parquet"))


@respx.mock
def test_backfill_main_lands_and_checkpoints(rooted, monkeypatch):
    records = e2e_raw_records(days=2)
    respx.get(url__startswith=ENDPOINT).mock(
        side_effect=[
            httpx.Response(200, json={"total": len(records), "records": records}),
            httpx.Response(200, json={"total": len(records), "records": []}),
        ]
        * 3
    )
    monkeypatch.setenv("DATA_GOV_API_KEY", "test-key")

    assert ingest.backfill.main([]) == 0
    assert (rooted / "data" / "raw" / "_checkpoint.json").exists()


def test_backfill_main_reconcile_writes_report(rooted, monkeypatch):
    land_records(e2e_raw_records(days=5), "api", COMMODITY, rooted / "data" / "raw")
    land_records(
        e2e_raw_records(days=5), "backfill", COMMODITY, rooted / "data" / "raw"
    )
    monkeypatch.chdir(rooted)

    assert ingest.backfill.main(["--reconcile"]) == 0
    assert (rooted / "docs" / "source_reconciliation.md").exists()


def test_backfill_main_from_csv(rooted, monkeypatch):
    csv = rooted / "history.csv"
    csv.write_text(
        "State,District,Market,Commodity,Variety,Grade,Arrival_Date,"
        "Min_Price,Max_Price,Modal_Price\n"
        "Maharashtra,Nashik,Lasalgaon,Onion,Red,FAQ,18/08/2026,1200,1850,1600\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(rooted)

    assert (
        ingest.backfill.main(
            [
                "--from-csv",
                str(csv),
                "--column-map",
                str(rooted / "seeds" / "backfill_column_map.yaml"),
            ]
        )
        == 0
    )
    assert list((rooted / "data" / "raw").rglob("*.parquet"))


def test_get_api_key_requires_the_environment(rooted, monkeypatch):
    monkeypatch.delenv("DATA_GOV_API_KEY", raising=False)
    monkeypatch.setattr(appconfig, "PROJECT_ROOT", rooted)

    with pytest.raises(ConfigError):
        appconfig.get_api_key()


def test_resolve_path_rejects_unknown_key(rooted):
    with pytest.raises(ConfigError):
        appconfig.resolve_path("nowhere")

    assert appconfig.resolve_path("raw") == rooted / "data" / "raw"
