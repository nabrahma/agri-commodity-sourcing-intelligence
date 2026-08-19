# Source reconciliation — API pull vs historical backfill

Generated 2026-08-19.

## Overlap

| Measure | Value |
|---|---|
| Overlap start | 01/02/2025 |
| Overlap end | 31/08/2025 |
| Rows in overlap (union of keys) | 2,888 |
| API rows in overlap | 2,096 |
| Backfill rows in overlap | 2,597 |

## Match rate

Join key: `arrival_date, market, commodity, variety`

| Measure | Value |
|---|---|
| Keys in both sources | 1,805 |
| Keys in API only | 291 |
| Keys in backfill only | 792 |
| **Match rate** | **62.50%** |

## Modal price divergence where both sources have the key

| Statistic | Absolute % difference |
|---|---|
| count | 1805.00 |
| mean | 0.00 |
| 50% | 0.00 |
| 75% | 0.00 |
| max | 0.00 |

Rows diverging by more than 10%: **0**

## Verdict

**This report was generated from the committed fixture panel, not from a real
historical backfill.** No backfill CSV has been loaded yet, so there is nothing
genuine to reconcile against. The two "sources" here are overlapping row-slices
of the same fixture, which is why **no row diverges on price at all**: where a
key exists in both slices it is byte-identical by construction.

The match rate of **62.50%** is therefore not a data-quality
signal — it is purely an artefact of where the slices were cut. Slicing by row
position rather than by date splits individual trading days in half, so keys near
the cut appear in one source only. Read it as a smoke test of the arithmetic, not
as evidence about the sources.

What this file is for: the reconciliation machinery is built, tested and runnable.
`python -m ingest.backfill --reconcile` regenerates this report against whatever is
actually in the landing zone. When a real historical CSV is loaded, the numbers
that matter are the match rate on the join key `(arrival_date, market, commodity,
variety)` across the overlapping date range, and the distribution of absolute
percentage difference in modal price where both sources carry the same key.

A real match rate materially below ~95%, or a long right tail on that percentage
difference, would mean the two sources are not measuring the same quantity, and
the backfill must not be appended to the API pull until that is understood.
