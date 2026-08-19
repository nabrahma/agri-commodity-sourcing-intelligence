"""Phase 4 -- warehouse schema, grain, referential integrity and inclusion."""

from __future__ import annotations

from datetime import date, timedelta

import duckdb
import pandas as pd
import pytest

from transform.warehouse import (
    build_dim_date,
    connect,
    create_schema,
    load_clean,
    update_market_inclusion,
)

TABLES = {"dim_market", "dim_commodity", "dim_date", "fct_price_daily"}

GEO = {
    "Lasalgaon": {"lat": 20.1425, "lon": 74.2377},
    "Pune": {"lat": 18.5204, "lon": 73.8567},
    "Bangalore": {"lat": 12.9716, "lon": 77.5946},
}


def clean_frame(rows: int = 30, markets=("Lasalgaon", "Pune", "Bangalore")):
    start = date(2026, 6, 1)
    records = []
    for market in markets:
        for i in range(rows):
            records.append(
                {
                    "arrival_date": start + timedelta(days=i),
                    "state": "Maharashtra",
                    "district": "Nashik",
                    "market_canonical": market,
                    "commodity_canonical": "Onion",
                    "variety": "Red",
                    "grade": "FAQ",
                    "min_price_inr_qtl": 1200.0,
                    "max_price_inr_qtl": 1800.0,
                    "modal_price_inr_qtl": 1500.0 + i,
                    "intraday_spread_pct": 40.0,
                    "source": "api",
                    "fetched_at_utc": pd.Timestamp("2026-08-19", tz="UTC"),
                    "is_outlier": False,
                }
            )
    return pd.DataFrame(records)


@pytest.fixture
def con():
    connection = duckdb.connect(":memory:")
    yield connection
    connection.close()


@pytest.fixture
def loaded(con):
    clean = clean_frame()
    load_clean(con, clean, GEO)
    update_market_inclusion(con, min_coverage_pct=70.0, min_observations=10)
    return con, clean


def insert_market_facts(
    con, market_sk: int, name: str, obs: int, distinct_days: int, span_days: int
):
    """Insert `obs` rows over `distinct_days` distinct dates spanning
    `span_days` calendar days, so coverage is exactly known."""
    create_schema(con)
    con.execute(
        "INSERT INTO dim_market (market_sk, market_canonical, lat, lon) VALUES (?,?,?,?)",
        [market_sk, name, 20.0, 74.0],
    )
    con.execute(
        "INSERT INTO dim_commodity VALUES (?, ?) ON CONFLICT DO NOTHING",
        [1, "Onion"],
    )
    start = date(2026, 6, 1)
    rows = []
    per_day, extra = divmod(obs, distinct_days)
    for day in range(distinct_days):
        # Last distinct date is pushed out to make the span exact.
        offset = span_days - 1 if day == distinct_days - 1 else day
        count = per_day + (1 if day < extra else 0)
        for v in range(count):
            rows.append((start + timedelta(days=offset), market_sk, 1, f"V{v}", ""))

    con.executemany(
        """
        INSERT INTO fct_price_daily
        (date_key, market_sk, commodity_sk, variety, grade,
         min_price_inr_qtl, max_price_inr_qtl, modal_price_inr_qtl)
        VALUES (?,?,?,?,?, 1200, 1800, 1500)
        """,
        rows,
    )
    return len(rows)


# --- 4.1 / 4.2 -------------------------------------------------------------


def test_ddl_creates_all_tables(con):
    create_schema(con)
    tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    assert tables >= TABLES


def test_ddl_is_idempotent(con):
    create_schema(con)
    create_schema(con)
    tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
    assert sorted(tables) == sorted(set(tables))
    assert set(tables) >= TABLES


# --- 4.3 / 4.4 -------------------------------------------------------------


def test_load_row_count_matches_source(loaded):
    con, clean = loaded
    assert con.execute("SELECT COUNT(*) FROM fct_price_daily").fetchone()[0] == len(
        clean
    )


def test_fact_grain_unique(loaded):
    con, _ = loaded
    total, distinct = con.execute(
        """
        SELECT COUNT(*),
               COUNT(DISTINCT (date_key, market_sk, commodity_sk, variety, grade))
        FROM fct_price_daily
        """
    ).fetchone()
    assert total == distinct


# --- 4.5 / 4.6 / 4.7 -------------------------------------------------------


def test_no_orphan_market_fk(loaded):
    con, _ = loaded
    orphans = con.execute(
        "SELECT COUNT(*) FROM fct_price_daily f "
        "LEFT JOIN dim_market m USING (market_sk) WHERE m.market_sk IS NULL"
    ).fetchone()[0]
    assert orphans == 0


def test_no_orphan_commodity_fk(loaded):
    con, _ = loaded
    orphans = con.execute(
        "SELECT COUNT(*) FROM fct_price_daily f "
        "LEFT JOIN dim_commodity c USING (commodity_sk) WHERE c.commodity_sk IS NULL"
    ).fetchone()[0]
    assert orphans == 0


def test_no_orphan_date_fk(loaded):
    con, _ = loaded
    orphans = con.execute(
        "SELECT COUNT(*) FROM fct_price_daily f "
        "LEFT JOIN dim_date d USING (date_key) WHERE d.date_key IS NULL"
    ).fetchone()[0]
    assert orphans == 0


# --- 4.8 ------------------------------------------------------------------


def test_dim_date_covers_full_range(loaded):
    con, _ = loaded
    span, rows = con.execute(
        """
        SELECT DATE_DIFF('day', MIN(date_key), MAX(date_key)) + 1,
               (SELECT COUNT(*) FROM dim_date)
        FROM fct_price_daily
        """
    ).fetchone()
    assert rows == span, "dim_date has a gap"

    gaps = con.execute(
        "SELECT COUNT(*) FROM ("
        "  SELECT date_key, LAG(date_key) OVER (ORDER BY date_key) AS prev"
        "  FROM dim_date"
        ") WHERE prev IS NOT NULL AND DATE_DIFF('day', prev, date_key) <> 1"
    ).fetchone()[0]
    assert gaps == 0


# --- 4.9 ------------------------------------------------------------------


def test_included_markets_have_coordinates(loaded):
    con, _ = loaded
    missing = con.execute(
        "SELECT COUNT(*) FROM dim_market WHERE is_included AND (lat IS NULL OR lon IS NULL)"
    ).fetchone()[0]
    assert missing == 0
    assert (
        con.execute("SELECT COUNT(*) FROM dim_market WHERE is_included").fetchone()[0]
        == 3
    )


# --- 4.10 -----------------------------------------------------------------


def test_coverage_pct_computed_correctly(con):
    insert_market_facts(con, 1, "SevenOfTen", obs=70, distinct_days=7, span_days=10)
    update_market_inclusion(con, 70.0, 10)

    coverage = con.execute(
        "SELECT coverage_pct FROM dim_market WHERE market_sk = 1"
    ).fetchone()[0]
    assert coverage == pytest.approx(70.0)


# --- 4.11 / 4.12 / 4.13 ---------------------------------------------------


def test_inclusion_boundary_exactly_70(con):
    insert_market_facts(con, 1, "Exactly70", obs=200, distinct_days=7, span_days=10)
    update_market_inclusion(con, 70.0, 200)

    coverage, obs, included = con.execute(
        "SELECT coverage_pct, observations, is_included FROM dim_market WHERE market_sk = 1"
    ).fetchone()
    assert coverage == pytest.approx(70.0)
    assert obs == 200
    assert included is True, "the threshold is inclusive"


def test_inclusion_boundary_just_below(con):
    # 699 of 1000 days -> 69.9%
    insert_market_facts(con, 1, "JustBelow", obs=699, distinct_days=699, span_days=1000)
    update_market_inclusion(con, 70.0, 200)

    coverage, included = con.execute(
        "SELECT coverage_pct, is_included FROM dim_market WHERE market_sk = 1"
    ).fetchone()
    assert coverage == pytest.approx(69.9)
    assert included is False


def test_inclusion_boundary_obs_199(con):
    insert_market_facts(con, 1, "Obs199", obs=199, distinct_days=10, span_days=10)
    update_market_inclusion(con, 70.0, 200)

    coverage, obs, included = con.execute(
        "SELECT coverage_pct, observations, is_included FROM dim_market WHERE market_sk = 1"
    ).fetchone()
    assert coverage == pytest.approx(100.0)
    assert obs == 199
    assert included is False, "coverage alone is not enough"


# --- 4.14 -----------------------------------------------------------------


def test_fiscal_year_april_to_march(con):
    create_schema(con)
    build_dim_date(con, "2026-03-30", "2026-04-02")

    fiscal = dict(con.execute("SELECT date_key, fiscal_year FROM dim_date").fetchall())
    assert fiscal[date(2026, 3, 31)] == "FY2025-26"
    assert fiscal[date(2026, 4, 1)] == "FY2026-27"


# --- 4.15 -----------------------------------------------------------------


def test_reload_is_idempotent(con):
    clean = clean_frame()
    first = load_clean(con, clean, GEO)
    second = load_clean(con, clean, GEO)

    assert first == second == len(clean)
    assert con.execute("SELECT COUNT(*) FROM dim_market").fetchone()[0] == 3
    assert con.execute("SELECT COUNT(*) FROM dim_commodity").fetchone()[0] == 1


# --- 4.16 -----------------------------------------------------------------


def test_prices_positive_constraint(con):
    create_schema(con)
    con.execute("INSERT INTO dim_market (market_sk, market_canonical) VALUES (1, 'X')")
    con.execute("INSERT INTO dim_commodity VALUES (1, 'Onion')")

    with pytest.raises(duckdb.ConstraintException):
        con.execute(
            """
            INSERT INTO fct_price_daily
            (date_key, market_sk, commodity_sk, variety, grade,
             min_price_inr_qtl, max_price_inr_qtl, modal_price_inr_qtl)
            VALUES (DATE '2026-06-01', 1, 1, 'Red', 'FAQ', 1200, 1800, 0)
            """
        )


def test_connect_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "warehouse" / "sourcing.duckdb"
    connection = connect(path)
    create_schema(connection)
    connection.close()
    assert path.exists()
