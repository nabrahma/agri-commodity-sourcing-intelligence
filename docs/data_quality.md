# Data quality

Generated 2026-08-19 from the current landing zone. Do not edit by hand.

## Conservation

| Stage | Rows |
|---|---|
| Raw records landed | 1,936 |
| Outside configured scope (state / commodity) | 1,214 |
| Records considered | 722 |
| Clean records kept | 0 |
| Records quarantined | 722 |
| Retention | 0.00% |

Scope exclusion is a deliberate filter, not a data-quality failure, so it is reported separately. Of the records considered, every one is either kept or quarantined with a reason, and the two counts always sum to the total; there is an assertion for it.

## Rejections by reason

| Reason | Rows | % of raw |
|---|---|---|
| `UNKNOWN_MARKET` | 722 | 100.00% |

## Coverage by market

_No clean rows._
