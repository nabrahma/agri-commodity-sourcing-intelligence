# Data quality

Generated 2026-08-19 from the current landing zone. Do not edit by hand.

## Conservation

| Stage | Rows |
|---|---|
| Raw records read | 2,930 |
| Clean records kept | 2,920 |
| Records quarantined | 10 |
| Retention | 99.66% |

Every raw row is either kept or quarantined with a reason. The two counts always sum to the first; there is an assertion for it.

## Rejections by reason

| Reason | Rows | % of raw |
|---|---|---|
| `MISSING_REQUIRED_FIELD` | 1 | 0.03% |
| `UNPARSEABLE_DATE` | 1 | 0.03% |
| `FUTURE_DATE` | 1 | 0.03% |
| `UNPARSEABLE_PRICE` | 1 | 0.03% |
| `NON_POSITIVE_PRICE` | 1 | 0.03% |
| `MIN_GT_MAX` | 1 | 0.03% |
| `MODAL_OUT_OF_RANGE` | 1 | 0.03% |
| `UNKNOWN_COMMODITY` | 1 | 0.03% |
| `UNKNOWN_MARKET` | 1 | 0.03% |
| `DUPLICATE_GRAIN` | 1 | 0.03% |

## Coverage by market

| market_canonical   |   observations |   reporting_days | first_date   | last_date   |   outliers |   coverage_pct |
|:-------------------|---------------:|-----------------:|:-------------|:------------|-----------:|---------------:|
| Lasalgaon          |            370 |              370 | 2025-01-06   | 2026-08-16  |          1 |          62.93 |
| Pune               |            365 |              365 | 2025-01-06   | 2026-08-18  |          0 |          61.86 |
| Ahmednagar         |            364 |              364 | 2025-01-06   | 2026-01-04  |          0 |         100    |
| Jalgaon            |            364 |              364 | 2025-01-06   | 2026-01-04  |          0 |         100    |
| Aurangabad         |            364 |              364 | 2025-01-06   | 2026-01-04  |          0 |         100    |
| Solapur            |            364 |              364 | 2025-01-06   | 2026-01-04  |          0 |         100    |
| Pimpalgaon         |            364 |              364 | 2025-01-06   | 2026-01-04  |          0 |         100    |
| Yeola              |            364 |              364 | 2025-01-06   | 2026-01-04  |          0 |         100    |
| Bangalore          |              1 |                1 | 2026-08-18   | 2026-08-18  |          0 |         100    |

Coverage is reporting days as a share of the market's own observed span. Gaps are left as gaps; no missing day is interpolated.
