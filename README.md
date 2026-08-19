# Agricultural Commodity Sourcing Intelligence

**Question:** for a buyer purchasing a fixed monthly tonnage of a perishable
agricultural commodity, how much of the purchase cost is decided by *where*
and *when* they buy, rather than by the market price itself?

The project answers that with observed daily wholesale prices across many
physical markets, a landed-cost model (price + transport + storage +
shrinkage), and a week-by-week simulation of three sourcing strategies:

| | Strategy | Rule |
|---|---|---|
| S1 | Baseline | always buy at the home market |
| S2 | Spatial | buy at the lowest **landed** cost within the radius |
| S3 | Spatial + timing | S2, plus buy ahead when price dips below its trailing mean |

**Data source:** the Government of India open-data platform
(`data.gov.in`), resource `9ef84268-d588-465a-a308-a864a43d0070` —
variety-wise daily wholesale prices from the national agricultural market
network. The method is source-agnostic; the feed is what happens to be
publicly available at daily granularity across hundreds of markets.

## Status

Built phase by phase against [`build-spec.md`](build-spec.md). Each phase
ends with an exit gate that must be green before the next begins.

| Phase | Scope | State |
|---|---|---|
| 0 | Scaffold, config, error model, record models | ✅ complete |
| 1 | API client | not started |
| 2 | Ingestion & immutable landing zone | not started |
| 3 | Cleaning & validation | not started |
| 4 | DuckDB warehouse | not started |
| 5 | Analytics SQL | not started |
| 6 | Simulation engine | not started |
| 7 | Sensitivity analysis | not started |
| 8 | Dashboard | not started |
| 9 | Automation & CI | not started |
| 10 | End-to-end integration | not started |
| 11 | Documentation & packaging | not started |

The headline number goes here once Phase 6 is green. It is deliberately
absent until then.

## Quick start

```bash
pip install -r requirements.txt   # or: make install
cp .env.example .env              # then paste your data.gov.in API key
make test                         # runs the suite; no network required
make lint
```

## Layout

```
config/      settings.yaml (thresholds) + assumptions.yaml (business inputs)
ingest/      API client, landing zone, daily + backfill entrypoints
transform/   parse -> validate -> canonicalise -> clean -> warehouse
analytics/   version-controlled SQL, one file per question
simulate/    geo, costs, strategies, week loop, sensitivity
dashboard/   Streamlit app, reads materialised parquet only
tests/       ~205 tests across unit, contract, property, golden and e2e
```

## Design rules that are not negotiable

- **No fabricated data.** If a fetch fails it raises. Missing market-days
  stay missing; they are never interpolated.
- **No look-ahead.** Strategies receive a `PriceView` constructed already
  filtered to the decision date, so seeing a future price is structurally
  impossible rather than merely discouraged.
- **Every rejected row has a reason** from a fixed enum, and every reason
  has a count in `docs/data_quality.md`.
- **All prices are ₹ per quintal (100 kg).** One tonne is ten quintals.
  There is a dedicated test guarding that conversion.
- **No magic numbers in code** — every threshold lives in `config/`.
