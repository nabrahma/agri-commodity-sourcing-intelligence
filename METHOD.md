# Method

Every metric definition, threshold and assumption used anywhere in this
project. If a number appears in the dashboard or the brief, its definition
is here, and the value it depends on is in `config/`.

---

## 1. Units and conventions

| Rule | Value |
|---|---|
| All prices | ₹ per **quintal** (100 kg) |
| Tonne to quintal | 1 tonne = **10 quintals** (`simulate/costs.py::TONNES_TO_QUINTALS`) |
| Percentages | suffix `_pct`, expressed 0–100 |
| Ratios | suffix `_ratio`, expressed 0–1 |
| Dates | suffix `_date`; timestamps `_at_utc`, always UTC |
| Fiscal year | April to March. 2026-03-31 is FY2025-26; 2026-04-01 is FY2026-27 |

The tonne/quintal conversion has its own test (`test_costs.py::test_tonnes_to_quintals`)
because a 10× error there would invalidate every rupee figure in the project.

---

## 2. Source and ingestion

**Source:** `data.gov.in` resource `9ef84268-d588-465a-a308-a864a43d0070` —
variety-wise daily wholesale prices from India's agricultural market
network. Prices arrive as strings; keyword fields require a `.keyword`
suffix in filters.

**Landing zone** (`data/raw/`) is append-only and partitioned:

```
source={api|backfill}/pulled_date=YYYY-MM-DD/commodity=<name>/part-NNN.parquet
```

A partition file is written once and never rewritten. Re-running on the
same day adds `part-001`, so a parsing bug is a re-parse, not a re-crawl.
Every landed row carries `fetched_at_utc`, `source` and `ingest_run_id`.

**Checkpointing:** `data/raw/_checkpoint.json` records the next offset per
commodity. A crash costs one page, not one crawl.

---

## 3. Cleaning and validation

Order of operations in `transform/clean.py::clean_dataframe`, chosen so a
row's reject reason names the real cause:

1. Required fields present (`state, market, commodity, arrival_date, min_price, max_price, modal_price`)
2. Parse `arrival_date`
3. Parse the three prices
4. Validate the price triple
5. Canonicalise commodity and market
6. Deduplicate on grain, keeping `max(fetched_at_utc)`
7. Compute `intraday_spread_pct`
8. Flag outliers

### 3.1 Date parsing

Accepted formats, tried in order: `DD/MM/YYYY`, `DD-MM-YYYY`, `YYYY-MM-DD`.
**Format inference is never used.** `05/06/2026` is 5 June, not 6 May;
guessing wrong would move every seasonal peak by up to eleven months.
A date after today is rejected as `FUTURE_DATE`.

### 3.2 Price parsing

Accepts `1200`, `1,200`, ` 1200 `, `1200.00`. Rejects the empty string,
`-`, `NA`, `N/A`, `NR`, `nan`, `null`, `nil`, `?` and anything non-numeric.
Zero and negative values are rejected as `NON_POSITIVE_PRICE`.

### 3.3 Price triple rule

Rejects `min > max` (`MIN_GT_MAX`) and `modal` outside `[min, max]`
(`MODAL_OUT_OF_RANGE`). Boundary values — `modal == min`, `modal == max` —
are **valid**.

### 3.4 Reject reasons

A fixed enum. Every one has a dedicated test and a count in
`docs/data_quality.md`:

`UNPARSEABLE_DATE`, `FUTURE_DATE`, `UNPARSEABLE_PRICE`, `NON_POSITIVE_PRICE`,
`MIN_GT_MAX`, `MODAL_OUT_OF_RANGE`, `MISSING_REQUIRED_FIELD`,
`UNKNOWN_COMMODITY`, `UNKNOWN_MARKET`, `DUPLICATE_GRAIN`.

**Conservation invariant:** `len(clean) + len(rejected) == len(raw)`,
asserted before the function returns and property-tested over generated
inputs.

### 3.5 Grain

`(arrival_date, market_canonical, commodity_canonical, variety, grade)` —
unique in the clean output and enforced as a primary key in the warehouse.

### 3.6 Intraday spread

```
intraday_spread_pct = 100 * (max_price - min_price) / modal_price
```

Measured against the modal price, which is the price actually transacted at
most often.

### 3.7 Outliers

Robust z-score on the **log** modal price within each
`(market, commodity)` group:

```
z = 0.6745 * (log_price - median) / MAD
is_outlier = |z| > outlier_z_threshold        # default 4.0
```

Outliers are **flagged, never dropped**. A genuine price spike is data;
removing it would understate volatility. They are excluded from the spread
metric so one bad print cannot set the maximum.

### 3.8 Missing days

**Never interpolated.** A market that did not report simply has no row.
Filling those gaps would fabricate the exact prices the analysis rests on.
This is why coverage is reported explicitly rather than assumed to be 100%.

---

## 4. Warehouse

Star schema in DuckDB: `dim_market`, `dim_commodity`, `dim_date`,
`fct_price_daily`.

- Fact grain enforced by primary key, not convention
- `CHECK (price > 0)` on all three price columns
- `dim_date` is generated as a complete calendar series, so a gap can never
  silently drop days from a date-joined query

### 4.1 Market inclusion rule

```sql
coverage_pct = 100.0 * COUNT(DISTINCT date_key)
             / (DATE_DIFF('day', MIN(date_key), MAX(date_key)) + 1)

is_included  = (coverage_pct >= 55.0 AND observations >= 200
                AND lat IS NOT NULL AND lon IS NOT NULL)
```

Coverage is measured against the market's **own observed span**, so a
market that started reporting late is not penalised for the period before
it existed. Both thresholds are inclusive.

A market with no coordinates is **never included**, whatever its coverage:
without a position there is no computable freight cost, so it cannot be a
sourcing candidate.

**On the 55% threshold.** The build spec proposed 70%, calibrated for a
true daily feed. The historical archives are not that: mandis trade on
market days, so median market coverage is 50.7% and the best market over
five years reaches 88.3%. At 70% only **4 markets** qualified — fewer than
`min_markets_for_spread`, so no spread could be computed at all. 55%
corresponds to a market trading roughly four days a week consistently and
yields a 54-market panel. This is a judgement call, which is why it is
swept in the sensitivity grid — where it turns out to be the **binding
assumption**.

| Threshold | Value | Config key |
|---|---|---|
| Minimum coverage | 55.0% | `quality.min_coverage_pct` |
| Minimum observations | 200 | `quality.min_observations` |
| Minimum markets for a spread day | 10 | `quality.min_markets_for_spread` |
| Outlier z threshold | 4.0 | `quality.outlier_z_threshold` |

---

## 5. Analytics

Each query is a version-controlled `.sql` file whose first line declares its
grain. Values are always bound as parameters, never interpolated.

### 5.1 Spread — `01_spread.sql`

GRAIN: one row per (date, commodity).

```
spread_pct = 100 * (max_modal - min_modal) / min_modal
```

Measured against the **cheapest** market, because that is the price a buyer
could actually have paid. Excludes flagged outliers, excludes non-included
markets, and drops days with fewer than `min_markets_for_spread` reporting
markets.

### 5.2 Seasonality — `02_seasonality.sql`

GRAIN: one row per (commodity, month).

```
seasonal_index = 100 * month_avg / mean(the twelve month averages)
```

The baseline is the **unweighted mean of the twelve monthly averages**, not
the mean of all daily prices, so a 31-day month does not carry more weight
than a 28-day one purely because of the calendar.

### 5.3 Volatility — `03_volatility.sql`

GRAIN: one row per (market, commodity, fiscal_year).

```
cv = STDDEV_SAMP(modal_price) / AVG(modal_price)
```

Sample standard deviation, so a market with a single observation yields
NULL rather than a misleading zero.

### 5.4 Coverage — `04_coverage.sql`

GRAIN: one row per (market, commodity). Same definition as the inclusion
rule in §4.1, so the dashboard and the warehouse can never disagree.

### 5.5 Reporting intensity — `05_arrivals.sql`

GRAIN: one row per (date, commodity). **This is a count of reporting
markets, not arrival tonnage.** The feed carries prices only; it has no
quantity field. It is labelled as reporting intensity everywhere it is
shown.

---

## 6. Simulation

### 6.1 The look-ahead firewall

Every strategy receives a `PriceView`, which filters its frame to
`as_of_date` on construction and exposes exactly three accessors —
`current_prices`, `latest_prices`, `trailing_mean` — none of which can
return a later row. This is a structural guarantee, not a convention.
Three tests assert it, including one that introspects every public method
and checks the maximum date it returns.

`trailing_mean` is strictly backward-looking: the decision day itself is
excluded, and it returns `None` when fewer than `days // 2` observations
exist, so a thin history never masquerades as a trend.

### 6.2 Requirement and capacity

```
weekly_need_qtl   = monthly_tonnes * 12 / 52 * 10        = 1,153.85 qtl
storage_cap_qtl   = weekly_need_qtl * (max_storage_weeks - 1)
```

A commodity with a one-week shelf life has a cap of zero, which is why
tomato can never stockpile.

### 6.3 Strategies

| | Rule |
|---|---|
| **S1** | Buy the exact weekly requirement at the home market, every week. |
| **S2** | Buy the requirement at whichever reachable market has the lowest **landed** cost (modal + freight) — not the lowest modal price. |
| **S3** | S2, plus: when the chosen market's price is below `dip_trigger_ratio × MA20`, buy up to `max_multiple_of_need × need`, limited by storage headroom. Inventory is always drawn down before buying. Falls back to S2 behaviour whenever the moving average is unavailable. |

### 6.4 Weekly sequence

Buy → deliver the requirement → store the remainder → pay storage →
apply shrinkage. Asserted every week: inventory ≥ 0, inventory ≤ cap,
purchase ≥ 0, no shortfall.

### 6.5 Silent markets

If a market does not quote on the decision day, its most recent quote
within **7 days** is used. Beyond that it is treated as unavailable. If no
candidate market has a usable price, the run raises `NoCandidateMarketsError`
— it never fabricates a number.

### 6.6 Costs

```
transport_inr_per_qtl = distance_km / 100 * transport_inr_per_qtl_per_100km
landed_inr_per_qtl    = modal_price + transport_inr_per_qtl
storage_inr           = inventory_qtl * storage_inr_per_qtl_per_week
surviving_inventory   = inventory_qtl * (1 - shrinkage_ratio_per_week)
```

Distance is great-circle (haversine, Earth radius 6371.0 km) — road
distance is longer, so freight is understated; see LIMITATIONS.md.

---

## 7. Assumptions

Every value below lives in `config/assumptions.yaml` and is swept in the
Phase 7 sensitivity grid.

### 7.1 Buyer

| Key | Value | Note |
|---|---|---|
| `monthly_requirement_tonnes` | 500 | fixed monthly volume |
| `purchase_frequency` | weekly | one decision per week |
| `max_radius_km` | 500 | how far the buyer will source |
| `home_market` | Lasalgaon | the S1 baseline market |

### 7.2 Costs

| Key | Value | Note |
|---|---|---|
| `transport_inr_per_qtl_per_100km` | 4.0 | **the binding assumption** |
| `storage_inr_per_qtl_per_week` | 15.0 | cold/controlled storage |
| `market_commission_pct` | 0.0 | deliberately excluded; see LIMITATIONS.md |

### 7.3 Per commodity

| Commodity | `max_storage_weeks` | `shrinkage_ratio_per_week` |
|---|---|---|
| Onion | 12 | 0.03 |
| Potato | 8 | 0.02 |
| Tomato | 1 | 0.08 |

### 7.4 Strategy S3

| Key | Value | Note |
|---|---|---|
| `dip_trigger_ratio` | 0.90 | buy ahead below 0.90 × MA20 |
| `moving_average_days` | 20 | the trailing window |
| `max_multiple_of_need` | 2.0 | never buy more than 2× the week's need |

### 7.5 Simulation window and variety

| Key | Value | Note |
|---|---|---|
| `simulation.start_date` | 2022-01-03 | first Monday of 2022 |
| `simulation.end_date` | 2023-01-02 | 52 weeks later |
| `simulation.varieties.Onion` | Red | 26 qualifying markets |
| `simulation.varieties.Potato` | Desi | 22 qualifying markets |
| `simulation.varieties.Tomato` | Deshi | 22 qualifying markets |

**Why the window is pinned.** Calendar 2022 is the one full year in which
the home market quotes almost every day (361 reporting days). 2019 and 2023
are part-years in the archive and 2021 has a 309-day gap, so simulating
across them would mean buying on stale quotes rather than observed prices.

**Why the variety is pinned — this one changes the answer.** Markets quote
different grades of the same commodity: Sambhal lists Red onion at ~₹1,608
a quintal, Sikar lists 1st Sort at ~₹978, Harda lists Medium at ~₹830. The
two markets never quote the same variety on the same day. Comparing across
grades turns a quality difference into a phantom spatial arbitrage: doing so
produced a **50.4% "saving"**, which fell to **35.5%** once the panel was
pinned to a single variety. The spread that survives is a like-for-like
comparison; the rest was composition.

---

## 8. Sensitivity

One-at-a-time sweep. `base_assumptions` is deep-copied for every run and
never mutated. Default grid:

| Parameter | Values |
|---|---|
| `transport_inr_per_qtl_per_100km` | 2, 4, 6 |
| `max_radius_km` | 300, 500, 800 |
| `storage_inr_per_qtl_per_week` | 7.5, 15, 30 |
| `shrinkage_ratio_per_week` | 0.5×, 1×, 1.5× of base |
| `dip_trigger_ratio` | 0.85, 0.90, 0.95 |
| `min_coverage_pct` | 45, 55, 65 |

The home market is always retained when `min_coverage_pct` is swept: the
buyer already sources there, so raising the bar on everyone else must not
leave the S1 baseline undefined.

`tornado_data` ranks parameters by the spread of outcomes they produce.
The top row is the **binding assumption**. `conclusion_stability` reports
whether S2 beats S1 across the entire grid, not just the base case.

---

## 9. What is deliberately not modelled

Listed in full in [LIMITATIONS.md](LIMITATIONS.md). In short: market
commission, grading and handling loss, road versus great-circle distance,
truck-load granularity, and any form of price forecasting.
