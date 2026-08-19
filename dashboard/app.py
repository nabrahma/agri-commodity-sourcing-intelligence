"""Streamlit dashboard.

Reads materialised parquet only. It never recomputes a metric and never
touches the API, so what is on screen is exactly what the pipeline
produced and can be traced back to a run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYTICS_DIR = PROJECT_ROOT / "data" / "processed" / "analytics"
SIMULATION_DIR = PROJECT_ROOT / "data" / "processed" / "simulation"
ASSUMPTIONS_PATH = PROJECT_ROOT / "config" / "assumptions.yaml"

DATA_SOURCE = "data.gov.in — daily wholesale market prices"

REQUIRED_PARQUET = {
    "spread": ANALYTICS_DIR / "spread.parquet",
    "seasonality": ANALYTICS_DIR / "seasonality.parquet",
    "volatility": ANALYTICS_DIR / "volatility.parquet",
    "coverage": ANALYTICS_DIR / "coverage.parquet",
    "reporting_intensity": ANALYTICS_DIR / "reporting_intensity.parquet",
}

OPTIONAL_PARQUET = {
    "sensitivity": ANALYTICS_DIR / "sensitivity.parquet",
    "tornado": ANALYTICS_DIR / "tornado.parquet",
}

EXPECTED_COLUMNS = {
    "spread": ["date_key", "commodity_canonical", "spread_pct", "cheapest_market"],
    "seasonality": ["commodity_canonical", "month", "seasonal_index"],
    "volatility": ["market_canonical", "commodity_canonical", "cv"],
    "coverage": ["market_canonical", "coverage_pct", "is_included"],
    "reporting_intensity": ["date_key", "commodity_canonical", "markets_reporting"],
}

GREY = "#9aa0a6"


def load_frame(name: str) -> pd.DataFrame:
    path = REQUIRED_PARQUET.get(name) or OPTIONAL_PARQUET.get(name)
    if path is None or not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def load_assumptions_text() -> str:
    if not ASSUMPTIONS_PATH.exists():
        return "assumptions.yaml not found"
    return ASSUMPTIONS_PATH.read_text(encoding="utf-8")


def load_simulation_summary() -> dict:
    path = SIMULATION_DIR / "summary.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def last_refreshed() -> str:
    stamps = [p.stat().st_mtime for p in REQUIRED_PARQUET.values() if p.exists()]
    if not stamps:
        return "no data yet"
    return pd.Timestamp(max(stamps), unit="s").strftime("%Y-%m-%d %H:%M")


def _missing_data_notice() -> None:
    st.warning(
        "No materialised outputs found. Run `make clean build analyse simulate` "
        "with a `DATA_GOV_API_KEY` in `.env` to populate this dashboard."
    )


def tab_spread(commodity: str) -> None:
    st.subheader("Spatial price spread")
    st.caption(
        "How much cheaper the cheapest reporting market was than the dearest, "
        "on the same day. Flagged outliers and low-coverage markets excluded."
    )
    spread = load_frame("spread")
    if spread.empty:
        _missing_data_notice()
        return

    frame = spread[spread["commodity_canonical"] == commodity]
    if frame.empty:
        st.info(f"No spread data for {commodity}.")
        return

    left, middle, right = st.columns(3)
    left.metric("Median spread", f"{frame['spread_pct'].median():.1f}%")
    middle.metric("Days covered", f"{len(frame):,}")
    right.metric("Most often cheapest", frame["cheapest_market"].mode().iloc[0])

    st.plotly_chart(
        px.line(
            frame.sort_values("date_key"),
            x="date_key",
            y="spread_pct",
            title=f"{commodity}: daily spread (%)",
            labels={"spread_pct": "spread (%)", "date_key": "date"},
        ),
        use_container_width=True,
    )
    st.dataframe(
        frame.tail(30)[
            [
                "date_key",
                "markets_reporting",
                "min_modal_inr_qtl",
                "max_modal_inr_qtl",
                "spread_pct",
                "cheapest_market",
            ]
        ],
        use_container_width=True,
    )


def tab_seasonality(commodity: str) -> None:
    st.subheader("Seasonality")
    st.caption(
        "Index where 100 is the commodity's typical month. Baseline is the "
        "unweighted mean of the twelve monthly averages."
    )
    seasonal = load_frame("seasonality")
    if seasonal.empty:
        _missing_data_notice()
        return

    frame = seasonal[seasonal["commodity_canonical"] == commodity].sort_values("month")
    if frame.empty:
        st.info(f"No seasonality data for {commodity}.")
        return

    st.plotly_chart(
        px.bar(
            frame,
            x="month_name" if "month_name" in frame.columns else "month",
            y="seasonal_index",
            title=f"{commodity}: seasonal index (100 = typical month)",
            labels={"seasonal_index": "index"},
        ),
        use_container_width=True,
    )
    peak = frame.loc[frame["seasonal_index"].idxmax()]
    trough = frame.loc[frame["seasonal_index"].idxmin()]
    st.markdown(
        f"Peak month **{int(peak['month'])}** at index "
        f"**{peak['seasonal_index']:.0f}**; trough month "
        f"**{int(trough['month'])}** at **{trough['seasonal_index']:.0f}**."
    )


def tab_markets(commodity: str) -> None:
    st.subheader("Markets and coverage")
    st.caption(
        "Markets below the coverage threshold are shown in grey. They are "
        "excluded from every headline metric because a thin market's prices "
        "are not comparable with a market that reports daily."
    )
    coverage = load_frame("coverage")
    volatility = load_frame("volatility")
    if coverage.empty:
        _missing_data_notice()
        return

    frame = coverage[coverage["commodity_canonical"] == commodity]
    if frame.empty:
        st.info(f"No coverage data for {commodity}.")
        return

    st.plotly_chart(
        px.bar(
            frame.sort_values("coverage_pct", ascending=False).head(40),
            x="market_canonical",
            y="coverage_pct",
            color="is_included",
            color_discrete_map={True: "#1f77b4", False: GREY},
            title=f"{commodity}: reporting coverage by market (%)",
            labels={"coverage_pct": "coverage (%)", "market_canonical": "market"},
        ),
        use_container_width=True,
    )

    if not volatility.empty:
        st.markdown("**Price volatility (coefficient of variation)**")
        st.dataframe(
            volatility[volatility["commodity_canonical"] == commodity].head(25),
            use_container_width=True,
        )


def tab_simulation(commodity: str) -> None:
    st.subheader("Sourcing strategy simulation")
    st.caption(
        "Twelve months, week by week. Every decision used only prices "
        "available on the decision date."
    )
    summary = load_simulation_summary()
    if not summary:
        _missing_data_notice()
        return

    labels = {
        "S1": "S1 — always buy at home market",
        "S2": "S2 — lowest landed cost in radius",
        "S3": "S3 — S2 plus buy ahead on dips",
    }
    columns = st.columns(3)
    for column, strategy in zip(columns, ("S1", "S2", "S3"), strict=False):
        entry = summary.get(strategy, {})
        column.metric(
            labels[strategy],
            f"₹{entry.get('total_cost_inr', 0) / 1e5:,.1f} lakh",
            f"₹{entry.get('cost_per_qtl_delivered_inr', 0):,.0f}/quintal",
        )

    saving = summary.get("saving", {})
    if saving:
        st.success(
            f"S2 saves **₹{saving.get('S2_saving_inr', 0) / 1e5:,.1f} lakh** "
            f"({saving.get('S2_saving_pct', 0):.1f}%) against the S1 baseline."
        )

    for strategy in ("S1", "S2", "S3"):
        path = SIMULATION_DIR / f"weekly_log_{strategy}.parquet"
        if path.exists():
            with st.expander(f"{strategy} weekly audit log"):
                st.dataframe(pd.read_parquet(path), use_container_width=True)

    with st.expander("Assumptions used (config/assumptions.yaml)"):
        st.code(load_assumptions_text(), language="yaml")


def tab_sensitivity(commodity: str) -> None:
    st.subheader("Sensitivity")
    st.caption(
        "One-at-a-time sweep. The widest bar is the binding assumption: the "
        "number worth measuring before anyone acts on this."
    )
    tornado = load_frame("tornado")
    sensitivity = load_frame("sensitivity")
    if tornado.empty:
        st.info("Run `make sensitivity` to populate this tab.")
        return

    st.plotly_chart(
        px.bar(
            tornado.sort_values("range_pct"),
            x="range_pct",
            y="parameter",
            orientation="h",
            title="Swing in saving (%) across each parameter's range",
            labels={"range_pct": "swing in saving (percentage points)"},
        ),
        use_container_width=True,
    )
    st.markdown(f"**Binding assumption:** `{tornado.iloc[0]['parameter']}`")
    if not sensitivity.empty:
        st.dataframe(sensitivity, use_container_width=True)


def main() -> None:
    st.set_page_config(
        page_title="Agricultural Commodity Sourcing Intelligence", layout="wide"
    )
    st.title("Agricultural Commodity Sourcing Intelligence")
    st.markdown(
        "How much of a buyer's cost is decided by **where** and **when** they "
        "buy, rather than by the market price itself. All prices are "
        "**₹ per quintal (100 kg)**."
    )

    spread = load_frame("spread")
    commodities = (
        sorted(spread["commodity_canonical"].unique())
        if not spread.empty
        else ["Onion"]
    )
    commodity = st.sidebar.selectbox("Commodity", commodities)
    st.sidebar.markdown(f"**Source**\n\n{DATA_SOURCE}")
    st.sidebar.markdown(f"**Last refreshed**\n\n{last_refreshed()}")

    tabs = st.tabs(["Spread", "Seasonality", "Markets", "Simulation", "Sensitivity"])
    with tabs[0]:
        tab_spread(commodity)
    with tabs[1]:
        tab_seasonality(commodity)
    with tabs[2]:
        tab_markets(commodity)
    with tabs[3]:
        tab_simulation(commodity)
    with tabs[4]:
        tab_sensitivity(commodity)

    st.divider()
    st.caption(
        f"Data source: {DATA_SOURCE}. Last refreshed: {last_refreshed()}. "
        "Prices in ₹ per quintal (100 kg). Known limitations are documented "
        "in LIMITATIONS.md; method and every threshold in METHOD.md."
    )


if __name__ == "__main__":
    main()
