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

## The answer

On the committed fixture panel — eight markets, 364 days, 2,912 observations
— switching from *always buy at the home market* to *buy wherever landed
cost is lowest within 500 km* saves:

> ### ₹88.1 lakh a year — 9.18% of a ₹960 lakh programme
> ₹1,600.0 → ₹1,453.1 per quintal delivered, 500 tonnes a month.

The median trading day shows a **19.3% price spread** between the cheapest
and dearest reporting market. The **binding assumption is transport cost**;
at ₹6 per quintal per 100 km instead of ₹4 the saving shrinks materially,
though S2 still beats S1 across the whole plausible range.

The timing strategy (S3) added **nothing** on this panel — no dip was ever
deep enough to trigger stockpiling, and where it does, storage and
shrinkage eat the gain. Reported as found.

> **These figures come from the committed fixture panel, not observed
> market data.** The pipeline is complete and reproducible; supply a
> `DATA_GOV_API_KEY` and run the same commands to produce the live numbers.
> See [docs/brief.md](docs/brief.md) for the one-page version.

## Build status

Built phase by phase against [`build-spec.md`](build-spec.md). Each phase
ends with an exit gate that must be green before the next begins.

| Phase | Scope | State |
|---|---|---|
| 0 | Scaffold, config, error model, record models | complete |
| 1 | API client | complete |
| 2 | Ingestion & immutable landing zone | complete |
| 3 | Cleaning & validation | complete |
| 4 | DuckDB warehouse | complete |
| 5 | Analytics SQL | complete |
| 6 | Simulation engine | complete |
| 7 | Sensitivity analysis | complete |
| 8 | Dashboard | complete |
| 9 | Automation & CI | complete |
| 10 | End-to-end integration | complete |
| 11 | Documentation & packaging | complete |

## Quick start

```bash
python -m venv .venv && make install
cp .env.example .env              # then paste your data.gov.in API key
make test                         # full suite; no network required
make lint

make backfill                     # needs the API key
make all                          # clean -> build -> analyse -> simulate
make dashboard                    # streamlit
```

Every target runs against `.venv` if one exists, so the pipeline can never
install itself over a global interpreter.

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
