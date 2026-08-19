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
(`data.gov.in`), resource `9ef84268-d588-465a-a308-a864a43d0070` -
variety-wise daily wholesale prices from the national agricultural market
network. The method is source-agnostic; the feed is what happens to be
publicly available at daily granularity across hundreds of markets.

## The answer

Built on **1,307,905 observed price records** from India's national mandi
archive (2019-2023, 8 states), simulating 52 weekly purchase decisions over
calendar 2022 for a 500 tonne/month onion buyer.

> ### The saving is 11%-38%, median 33% - and which number you get depends on where you buy today, not on where you could buy.
> Best reachable landed cost is **₹1,039-1,065/quintal** almost regardless of
> starting market. A buyer anchored at Sambhal (₹1,611/qtl) saves **₹3.4
> crore a year**; one already at Siyana (₹1,169/qtl) saves 11%.

**The binding assumption is which markets you count** - at a 45% coverage
bar the saving is 22.2%, at 65% it is 35.5%. Freight barely matters:
doubling it moves the answer 0.3 points, because the price gap dwarfs the
haulage.

**The timing strategy lost money.** S3 (buy ahead on dips) came in 7% worse
than S2: shrinkage at 3%/week and storage at ₹15/qtl/week ate more than the
dips returned. Reported as found.

### Two errors this project caught in itself

1. **Grade mixing.** Markets quote different grades under one commodity
   name. Comparing across them showed a **50.4% saving that collapsed to
   35.5%** once the panel was pinned to a single variety. The build spec's
   ">30% means you have a bug" tripwire is what caught it.
2. **A silent-failure geocoder.** The first market-mapping run reported 173
   markets "not found" that plainly exist; it was treating rate-limit
   responses as absence. Fixed, then 208 of 260 located and every one
   validated against its own state's bounding box.

See [docs/brief.md](docs/brief.md) for the one-page version.

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
- **No magic numbers in code** - every threshold lives in `config/`.
