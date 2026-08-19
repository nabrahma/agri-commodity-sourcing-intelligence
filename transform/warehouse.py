"""DuckDB star schema: three dimensions and one fact.

The fact grain is enforced by a primary key rather than by convention, and
prices carry positivity checks, so a loader bug fails at load time instead
of surfacing as a wrong number six steps downstream.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import structlog

log = structlog.get_logger(__name__)

FACT_GRAIN = ("date_key", "market_sk", "commodity_sk", "variety", "grade")

DDL = """
CREATE TABLE IF NOT EXISTS dim_market (
    market_sk        INTEGER PRIMARY KEY,
    market_canonical VARCHAR NOT NULL,
    district         VARCHAR,
    state            VARCHAR,
    lat              DOUBLE,
    lon              DOUBLE,
    observations     BIGINT  DEFAULT 0,
    coverage_pct     DOUBLE  DEFAULT 0.0,
    is_included      BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS dim_commodity (
    commodity_sk        INTEGER PRIMARY KEY,
    commodity_canonical VARCHAR NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dim_date (
    date_key    DATE PRIMARY KEY,
    year        SMALLINT NOT NULL,
    month       TINYINT  NOT NULL,
    day         TINYINT  NOT NULL,
    month_name  VARCHAR  NOT NULL,
    quarter     TINYINT  NOT NULL,
    week_of_year TINYINT NOT NULL,
    day_of_week TINYINT  NOT NULL,
    is_weekend  BOOLEAN  NOT NULL,
    fiscal_year VARCHAR  NOT NULL
);

CREATE TABLE IF NOT EXISTS fct_price_daily (
    date_key            DATE    NOT NULL,
    market_sk           INTEGER NOT NULL,
    commodity_sk        INTEGER NOT NULL,
    variety             VARCHAR NOT NULL DEFAULT '',
    grade               VARCHAR NOT NULL DEFAULT '',
    min_price_inr_qtl   DOUBLE  NOT NULL CHECK (min_price_inr_qtl > 0),
    max_price_inr_qtl   DOUBLE  NOT NULL CHECK (max_price_inr_qtl > 0),
    modal_price_inr_qtl DOUBLE  NOT NULL CHECK (modal_price_inr_qtl > 0),
    intraday_spread_pct DOUBLE,
    source              VARCHAR,
    fetched_at_utc      TIMESTAMP,
    is_outlier          BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (date_key, market_sk, commodity_sk, variety, grade)
);
"""

# Fiscal year runs April to March: 2026-03-31 is FY2025-26, 2026-04-01 is
# FY2026-27.
FISCAL_YEAR_SQL = """
    'FY' || CAST(fy_start AS VARCHAR) || '-' ||
    RIGHT('0' || CAST((fy_start + 1) % 100 AS VARCHAR), 2)
"""

# Market inclusion. Coverage is reporting days over the market's own observed
# span, so a market that started reporting late is not penalised for the
# period before it existed.
INCLUSION_SQL = """
UPDATE dim_market SET
    coverage_pct = sub.coverage_pct,
    observations = sub.obs,
    -- Coordinates are part of the rule, not a nicety: a market whose
    -- position is unknown has no computable freight cost, so it can never
    -- be a sourcing candidate however well it reports.
    is_included  = (sub.coverage_pct >= ? AND sub.obs >= ?
                    AND dim_market.lat IS NOT NULL
                    AND dim_market.lon IS NOT NULL)
FROM (
    SELECT market_sk,
           100.0 * COUNT(DISTINCT date_key)
                / (DATE_DIFF('day', MIN(date_key), MAX(date_key)) + 1) AS coverage_pct,
           COUNT(*) AS obs
    FROM fct_price_daily
    GROUP BY market_sk
) sub
WHERE dim_market.market_sk = sub.market_sk
"""


def connect(path: Path | str) -> duckdb.DuckDBPyConnection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def create_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Idempotent DDL."""
    con.execute(DDL)
    log.info("warehouse.schema.ready")


def _build_dim_market(
    con: duckdb.DuckDBPyConnection, clean: pd.DataFrame, geo: dict[str, dict]
) -> pd.DataFrame:
    markets = (
        clean[["market_canonical", "district", "state"]]
        .drop_duplicates(subset=["market_canonical"])
        .sort_values("market_canonical")
        .reset_index(drop=True)
    )
    markets["market_sk"] = markets.index + 1
    markets["lat"] = markets["market_canonical"].map(
        lambda m: (geo.get(m) or {}).get("lat")
    )
    markets["lon"] = markets["market_canonical"].map(
        lambda m: (geo.get(m) or {}).get("lon")
    )
    markets["observations"] = 0
    markets["coverage_pct"] = 0.0
    markets["is_included"] = False

    missing = markets.loc[markets["lat"].isna(), "market_canonical"].tolist()
    if missing:
        log.warning("warehouse.market.no_coordinates", markets=missing)

    con.execute("DELETE FROM dim_market")
    con.register("_markets", markets)
    con.execute(
        """
        INSERT INTO dim_market
        SELECT market_sk, market_canonical, district, state, lat, lon,
               observations, coverage_pct, is_included
        FROM _markets
        """
    )
    con.unregister("_markets")
    return markets


def _build_dim_commodity(
    con: duckdb.DuckDBPyConnection, clean: pd.DataFrame
) -> pd.DataFrame:
    commodities = (
        clean[["commodity_canonical"]]
        .drop_duplicates()
        .sort_values("commodity_canonical")
        .reset_index(drop=True)
    )
    commodities["commodity_sk"] = commodities.index + 1

    con.execute("DELETE FROM dim_commodity")
    con.register("_commodities", commodities)
    con.execute(
        "INSERT INTO dim_commodity SELECT commodity_sk, commodity_canonical "
        "FROM _commodities"
    )
    con.unregister("_commodities")
    return commodities


def build_dim_date(
    con: duckdb.DuckDBPyConnection, start: str | None = None, end: str | None = None
) -> int:
    """Fill dim_date with every calendar day between the fact range bounds.

    A gap here would silently drop days from any date-joined query, so the
    series is generated rather than derived from observed dates.
    """
    if start is None or end is None:
        bounds = con.execute(
            "SELECT MIN(date_key), MAX(date_key) FROM fct_price_daily"
        ).fetchone()
        if not bounds or bounds[0] is None:
            log.warning("warehouse.dim_date.no_facts")
            return 0
        start, end = bounds[0], bounds[1]

    con.execute("DELETE FROM dim_date")
    con.execute(
        f"""
        INSERT INTO dim_date
        WITH days AS (
            SELECT UNNEST(GENERATE_SERIES(
                       CAST(? AS DATE), CAST(? AS DATE), INTERVAL 1 DAY
                   ))::DATE AS d
        ), enriched AS (
            SELECT d,
                   CASE WHEN MONTH(d) >= 4 THEN YEAR(d) ELSE YEAR(d) - 1 END AS fy_start
            FROM days
        )
        SELECT d,
               YEAR(d), MONTH(d), DAY(d), MONTHNAME(d), QUARTER(d),
               WEEKOFYEAR(d), DAYOFWEEK(d), DAYOFWEEK(d) IN (0, 6),
               {FISCAL_YEAR_SQL}
        FROM enriched
        ORDER BY d
        """,
        [str(start), str(end)],
    )
    rows = con.execute("SELECT COUNT(*) FROM dim_date").fetchone()[0]
    log.info("warehouse.dim_date.built", start=str(start), end=str(end), rows=rows)
    return int(rows)


def load_clean(
    con: duckdb.DuckDBPyConnection,
    clean: pd.DataFrame,
    market_geo: dict[str, dict] | None = None,
) -> int:
    """Full refresh of dims and facts from a clean frame. Idempotent."""
    create_schema(con)
    if clean.empty:
        log.warning("warehouse.load.empty")
        return 0

    markets = _build_dim_market(con, clean, market_geo or {})
    commodities = _build_dim_commodity(con, clean)

    facts = clean.copy()
    facts["variety"] = facts["variety"].fillna("").astype(str)
    facts["grade"] = facts["grade"].fillna("").astype(str)
    facts = facts.merge(
        markets[["market_canonical", "market_sk"]], on="market_canonical", how="left"
    ).merge(
        commodities[["commodity_canonical", "commodity_sk"]],
        on="commodity_canonical",
        how="left",
    )
    facts = facts.rename(columns={"arrival_date": "date_key"})
    facts["fetched_at_utc"] = pd.to_datetime(
        facts["fetched_at_utc"], utc=True, format="mixed"
    ).dt.tz_localize(None)

    orphans = int(facts["market_sk"].isna().sum() + facts["commodity_sk"].isna().sum())
    if orphans:
        raise ValueError(f"{orphans} fact rows have no dimension key")

    con.execute("DELETE FROM fct_price_daily")
    con.register("_facts", facts)
    con.execute(
        """
        INSERT INTO fct_price_daily
        SELECT date_key, market_sk, commodity_sk, variety, grade,
               min_price_inr_qtl, max_price_inr_qtl, modal_price_inr_qtl,
               intraday_spread_pct, source, fetched_at_utc, is_outlier
        FROM _facts
        """
    )
    con.unregister("_facts")

    build_dim_date(con)
    rows = con.execute("SELECT COUNT(*) FROM fct_price_daily").fetchone()[0]
    log.info(
        "warehouse.load.complete",
        facts=rows,
        markets=len(markets),
        commodities=len(commodities),
    )
    return int(rows)


def update_market_inclusion(
    con: duckdb.DuckDBPyConnection,
    min_coverage_pct: float = 70.0,
    min_observations: int = 200,
) -> int:
    con.execute(INCLUSION_SQL, [min_coverage_pct, min_observations])
    included = con.execute(
        "SELECT COUNT(*) FROM dim_market WHERE is_included"
    ).fetchone()[0]
    log.info(
        "warehouse.inclusion.updated",
        included=included,
        min_coverage_pct=min_coverage_pct,
        min_observations=min_observations,
    )
    return int(included)


def reconciliation_counts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Row counts per stage, logged so a vanished row is always visible."""
    return {
        "fct_price_daily": con.execute(
            "SELECT COUNT(*) FROM fct_price_daily"
        ).fetchone()[0],
        "dim_market": con.execute("SELECT COUNT(*) FROM dim_market").fetchone()[0],
        "dim_market_included": con.execute(
            "SELECT COUNT(*) FROM dim_market WHERE is_included"
        ).fetchone()[0],
        "dim_commodity": con.execute("SELECT COUNT(*) FROM dim_commodity").fetchone()[
            0
        ],
        "dim_date": con.execute("SELECT COUNT(*) FROM dim_date").fetchone()[0],
    }


def main() -> int:
    from appconfig import PROJECT_ROOT, load_settings, resolve_path
    from transform.canonicalise import load_market_geo

    settings = load_settings()
    clean_path = resolve_path("processed") / "clean.parquet"
    if not clean_path.exists():
        log.error("warehouse.no_clean_input", path=str(clean_path))
        return 1

    clean = pd.read_parquet(clean_path)
    geo = load_market_geo(PROJECT_ROOT / "seeds" / "market_map.csv")

    con = connect(resolve_path("warehouse"))
    try:
        rows = load_clean(con, clean, geo)
        update_market_inclusion(
            con,
            settings["quality"]["min_coverage_pct"],
            settings["quality"]["min_observations"],
        )
        counts = reconciliation_counts(con)
        log.info("warehouse.reconciliation", clean_rows=len(clean), **counts)
        print(f"clean rows {len(clean):,} -> fact rows {rows:,}")
        for name, count in counts.items():
            print(f"  {name}: {count:,}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
