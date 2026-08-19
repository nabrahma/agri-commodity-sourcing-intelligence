"""Phase 10 -- the whole pipeline, end to end, on fixture data.

Nothing here reaches the network: the API is mocked with respx and every
byte written lands in a throwaway root.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date

import duckdb
import httpx
import pandas as pd
import pytest
import respx

from analytics.queries import materialise_all, spread_by_day
from ingest.client import MarketPriceAPIClient
from ingest.land import land_records, read_landed
from simulate.engine import (
    compare_strategies,
    markets_from_warehouse,
    prices_from_warehouse,
    saving_vs_baseline,
)
from tests.conftest import E2E_MARKETS, e2e_raw_records
from transform.canonicalise import (
    load_commodity_map,
    load_market_geo,
    load_market_map,
)
from transform.clean import clean_dataframe, write_data_quality_report, write_quarantine
from transform.warehouse import connect, load_clean, update_market_inclusion

ENDPOINT = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
PULLED = date(2026, 8, 20)
COMMODITY = "Onion"


def run_pipeline(root, records, outlier_z=4.0, min_coverage=70.0, min_obs=200):
    """land -> clean -> warehouse -> analyse -> simulate, all under `root`."""
    stages: dict[str, int] = {}

    land_records(
        records, "fixture", COMMODITY, root / "data" / "raw", pulled_date=PULLED
    )
    raw = read_landed(root / "data" / "raw")
    stages["raw"] = len(raw)

    clean, rejected = clean_dataframe(
        raw,
        load_commodity_map(root / "seeds" / "commodity_map.csv"),
        load_market_map(root / "seeds" / "market_map.csv"),
        outlier_z=outlier_z,
    )
    stages["clean"] = len(clean)
    stages["rejected"] = len(rejected)

    processed = root / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    clean.to_parquet(processed / "clean.parquet", index=False)
    write_quarantine(rejected, root / "data" / "quarantine")
    write_data_quality_report(clean, rejected, root / "docs" / "data_quality.md")

    con = connect(root / "data" / "warehouse" / "sourcing.duckdb")
    try:
        stages["warehouse"] = load_clean(
            con, clean, load_market_geo(root / "seeds" / "market_map.csv")
        )
        update_market_inclusion(con, min_coverage, min_obs)
        stages["included_markets"] = con.execute(
            "SELECT COUNT(*) FROM dim_market WHERE is_included"
        ).fetchone()[0]

        materialise_all(
            con, [COMMODITY], processed / "analytics", min_markets=3, min_obs=50
        )
        prices = prices_from_warehouse(con, COMMODITY)
        markets = markets_from_warehouse(con)
    finally:
        con.close()

    stages["price_rows"] = len(prices)
    # The window comes from the data, never from a constant that could
    # silently run past the end of the panel.
    start = pd.to_datetime(prices["date"]).min().date()
    end = pd.to_datetime(prices["date"]).max().date()
    results = compare_strategies(
        prices, _assumptions(root), COMMODITY, start, end, markets
    )
    saving = saving_vs_baseline(results)

    simulation = processed / "simulation"
    simulation.mkdir(parents=True, exist_ok=True)
    (simulation / "summary.json").write_text(
        json.dumps(
            {s: r.summary() for s, r in results.items()} | {"saving": saving},
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return stages, results, saving


def _assumptions(root):
    import yaml

    with open(root / "config" / "assumptions.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@pytest.fixture
def pipeline(e2e_root):
    return run_pipeline(e2e_root, e2e_raw_records())


# --- 10.1 / 10.5 -----------------------------------------------------------


@respx.mock(assert_all_mocked=True)
def test_full_pipeline_on_fixtures(respx_mock, e2e_root):
    """Fetch through a mocked API, then every downstream stage."""
    records = e2e_raw_records(days=30)
    respx_mock.get(url__startswith=ENDPOINT).mock(
        side_effect=[
            httpx.Response(200, json={"total": len(records), "records": records}),
            httpx.Response(200, json={"total": len(records), "records": []}),
        ]
    )

    client = MarketPriceAPIClient(
        "k",
        "https://api.data.gov.in/resource",
        "9ef84268-d588-465a-a308-a864a43d0070",
        sleep_seconds=0.0,
    )
    fetched = client.fetch_all(filters={"commodity": COMMODITY}, page_size=len(records))
    assert len(fetched) == len(records)

    stages, results, saving = run_pipeline(
        e2e_root, fetched, min_coverage=70.0, min_obs=20
    )

    assert stages["raw"] == len(records)
    assert stages["clean"] > 0
    assert stages["warehouse"] == stages["clean"]
    assert (e2e_root / "data" / "processed" / "analytics" / "spread.parquet").exists()
    assert (e2e_root / "docs" / "data_quality.md").exists()
    assert results["S1"].total_cost_inr > 0


def test_no_network_calls_in_pipeline(e2e_root):
    """With no mock installed at all, the pipeline must still complete --
    proving nothing downstream of ingestion touches the network."""
    with respx.mock(assert_all_called=False) as router:
        run_pipeline(e2e_root, e2e_raw_records(days=60), min_obs=20)
        assert len(router.calls) == 0


# --- 10.2 ------------------------------------------------------------------


def test_row_counts_reconcile_across_stages(pipeline):
    stages, _, _ = pipeline

    assert stages["raw"] == stages["clean"] + stages["rejected"]
    assert stages["warehouse"] == stages["clean"]
    assert stages["rejected"] == 0, "the fixture is clean by construction"
    assert stages["included_markets"] == len(E2E_MARKETS)


# --- 10.3 ------------------------------------------------------------------


def test_pipeline_idempotent(e2e_root):
    records = e2e_raw_records(days=120)
    first, _, first_saving = run_pipeline(e2e_root, records, min_obs=20)
    second, _, second_saving = run_pipeline(e2e_root, records, min_obs=20)

    # The landing zone is append-only, so raw doubles ...
    assert second["raw"] == 2 * first["raw"]
    # ... but the grain dedupe means the warehouse does not.
    assert second["warehouse"] == first["warehouse"]
    assert second["clean"] == first["clean"]
    assert second_saving["S2_saving_pct"] == pytest.approx(
        first_saving["S2_saving_pct"]
    )


# --- 10.4 ------------------------------------------------------------------


def test_pipeline_resumes_after_failure(e2e_root):
    """Kill the run after cleaning; a rerun completes from what is on disk."""
    records = e2e_raw_records(days=90)
    land_records(
        records, "fixture", COMMODITY, e2e_root / "data" / "raw", pulled_date=PULLED
    )
    raw = read_landed(e2e_root / "data" / "raw")
    clean, _ = clean_dataframe(
        raw,
        load_commodity_map(e2e_root / "seeds" / "commodity_map.csv"),
        load_market_map(e2e_root / "seeds" / "market_map.csv"),
    )
    processed = e2e_root / "data" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    clean.to_parquet(processed / "clean.parquet", index=False)

    # Simulated crash: nothing after this point ran. Now rerun from disk.
    reloaded = pd.read_parquet(processed / "clean.parquet")
    con = connect(e2e_root / "data" / "warehouse" / "sourcing.duckdb")
    try:
        rows = load_clean(
            con, reloaded, load_market_geo(e2e_root / "seeds" / "market_map.csv")
        )
        update_market_inclusion(con, 70.0, 20)
        spread = spread_by_day(con, COMMODITY, min_markets=3)
    finally:
        con.close()

    assert rows == len(clean)
    assert not spread.empty


# --- 10.6 ------------------------------------------------------------------


def test_headline_number_stable(pipeline):
    """The end-to-end headline must be reproducible to the paisa."""
    _, results, saving = pipeline

    assert saving["S2_saving_pct"] == pytest.approx(9.1824, abs=0.001)
    assert results["S1"].cost_per_qtl_delivered_inr == pytest.approx(
        1599.9677, abs=0.001
    )
    assert results["S2"].cost_per_qtl_delivered_inr == pytest.approx(
        1453.0529, abs=0.001
    )
    # On this smooth panel no dip ever breaks the 0.90 x MA20 trigger, so S3
    # never stockpiles and lands exactly on S2. That is a result, not a bug.
    assert results["S3"].total_cost_inr == pytest.approx(results["S2"].total_cost_inr)
    assert 0.0 < saving["S2_saving_pct"] < 30.0
    for result in results.values():
        assert result.weeks_with_shortfall == 0
        assert 500.0 < result.cost_per_qtl_delivered_inr < 10_000.0


# --- 10.7 ------------------------------------------------------------------


@pytest.mark.slow
def test_clean_clone_simulation(e2e_root, project_root):
    """Every pipeline entrypoint runs to exit 0 against a throwaway root."""
    import shutil

    for name in ("appconfig.py",):
        shutil.copy(project_root / name, e2e_root / name)
    for package in ("ingest", "transform", "analytics", "simulate"):
        shutil.copytree(project_root / package, e2e_root / package)

    land_records(
        e2e_raw_records(days=120),
        "fixture",
        COMMODITY,
        e2e_root / "data" / "raw",
        pulled_date=PULLED,
    )

    # This test asserts exit codes, not coverage. Without stripping the
    # pytest-cov hooks the subprocess would report a second, much lower
    # measurement of the same modules under their temp-root paths.
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COV_CORE", "COVERAGE"))
    }
    env.update(
        SOURCING_PROJECT_ROOT=str(e2e_root),
        PYTHONPATH=str(e2e_root),
    )
    for module in ("transform.clean", "transform.warehouse", "analytics.queries"):
        completed = subprocess.run(
            [sys.executable, "-m", module],
            cwd=e2e_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert (
            completed.returncode == 0
        ), f"{module} failed:\n{completed.stderr[-2000:]}"

    warehouse = e2e_root / "data" / "warehouse" / "sourcing.duckdb"
    assert warehouse.exists()
    con = duckdb.connect(str(warehouse), read_only=True)
    try:
        assert con.execute("SELECT COUNT(*) FROM fct_price_daily").fetchone()[0] > 0
    finally:
        con.close()


def test_makefile_defines_every_pipeline_target(project_root):
    makefile = (project_root / "Makefile").read_text(encoding="utf-8")
    for target in (
        "install",
        "test",
        "lint",
        "ingest",
        "backfill",
        "clean",
        "build",
        "analyse",
        "simulate",
        "sensitivity",
        "dashboard",
        "all",
    ):
        assert f"\n{target}:" in makefile, f"Makefile has no {target} target"
