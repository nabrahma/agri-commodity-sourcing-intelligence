# Source reconciliation - API pull vs historical backfill

Generated 2026-08-19.

## Overlap

| Measure | Value |
|---|---|
| Overlap start | n/a |
| Overlap end | n/a |
| Rows in overlap (union of keys) | 0 |
| API rows in overlap | 1,892 |
| Backfill rows in overlap | 1,307,905 |

## Match rate

Join key: `arrival_date, market, commodity, variety`

| Measure | Value |
|---|---|
| Keys in both sources | 0 |
| Keys in API only | 0 |
| Keys in backfill only | 0 |
| **Match rate** | **0.00%** |

## Modal price divergence where both sources have the key

| Statistic | Absolute % difference |
|---|---|
| count | n/a |
| mean | n/a |
| 50% | n/a |
| 75% | n/a |
| max | n/a |

Rows diverging by more than 10%: **0**

## Verdict

**The two sources do not overlap at all, and that is the finding.**

The live resource (`9ef84268-...`) is a **current-day feed**: querying it for
any past `arrival_date` returns zero rows. It was pulled on 2026-08-19 and
holds 1,892 rows, all for that single date. The historical archives are
per-commodity, per-year datasets covering 2019-01-01 to 2023-01-27. There is
a three-and-a-half year gap between them, so there is no shared join key and
no match rate to compute.

**Consequence for the analysis:** the 1,307,905 archive rows the findings
rest on **have not been cross-validated against an independent measurement**
of the same market-days, because no such measurement is available. The
archive schema also differs from the live feed - `_state_` rather than
`state`, ISO timestamps rather than DD/MM/YYYY, and no `grade` field at all -
which is consistent with separately produced extracts rather than one series
split in two. Whether the two would agree on a shared date is unknown.

**What would close this:** run `make ingest` daily from here. The workflow in
`.github/workflows/daily-pull.yml` does exactly that. Once forward accrual
overlaps a re-published archive year, this report becomes a real
reconciliation and the match rate below becomes meaningful. Until then, treat
the archive as unverified against any second source.
