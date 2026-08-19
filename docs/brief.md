# Your sourcing cost is set by which mandi you stand in

**Onion sourcing intelligence for a fixed-volume buyer — one page.**

> **Data:** 1,307,905 observed price records from India's national mandi
> archive (data.gov.in), 2019–2023, across 8 states. Simulation run on
> calendar 2022. All figures reproducible with `make all`.

---

## Question

For a buyer purchasing 500 tonnes of onion a month, how much of the annual
cost is decided by **which market** they buy from, rather than by the market
price itself?

## Method

- 1.31M archive records cleaned to a validated panel; every rejected row
  carries a reason and a count. Missing market-days are left missing.
- 254 markets geocoded and filtered to 54 that report often enough to be a
  reliable weekly source.
- 52 weekly purchase decisions over 2022, each taken through a price view
  filtered to the decision date — so no strategy can see a future price.

## Finding 1 — the same variety, the same day, very different prices

Across 25 qualifying markets within 500 km, **Red onion traded at ₹1,040 a
quintal at the cheapest reachable market against ₹1,611 at Sambhal** — a
55% premium, sustained across the year rather than on isolated days.

## Finding 2 — the saving is a property of where you already buy

This is the result that matters, and it is not a single number:

| Your current market | Its own price | Best reachable | Saving |
|---|---|---|---|
| Siyana | ₹1,169/qtl | ₹1,039/qtl | **11.1%** |
| Bahedi | ₹1,238/qtl | ₹1,040/qtl | **16.0%** |
| Muradabad | ₹1,561/qtl | ₹1,045/qtl | **33.0%** |
| Sambhal | ₹1,611/qtl | ₹1,040/qtl | **35.5%** |
| Nawabganj | ₹1,719/qtl | ₹1,065/qtl | **38.0%** |

Across all 25 candidate home markets the saving runs **11% to 38%, median
33%**. The striking part is the third column: the best reachable landed cost
is ₹1,039–1,065 almost regardless of where you start. **The opportunity is
not that some markets are cheap — it is that some buyers are anchored to an
expensive one.**

## Finding 3 — the timing strategy destroyed value

S3 (buy ahead on price dips) cost **₹1,111/qtl against S2's ₹1,040** — 7%
worse. Onion shrinks at 3% a week and storage costs ₹15/quintal/week;
together those consumed more than the dips returned. Reported as found.

## Recommendation

**Move weekly onion purchasing to a lowest-landed-cost rule across
qualifying markets within 500 km.** For a buyer currently anchored at
Sambhal that is **₹3.4 crore a year on a 6,000-tonne programme** (₹9.66
crore → ₹6.24 crore). For a buyer already at a competitive market it is
closer to 11%, and may not be worth the operational change.

**The first question to ask is not "where is cheapest" but "how expensive is
where I already buy".** That is answerable in an afternoon from this data.

## Limitations — two of these are large

- **Grade mixing was the single biggest error found, and it is only
  partly fixed.** Markets quote different grades under one commodity name.
  Comparing across them produced a **50.4% saving that collapsed to 35.5%**
  once the panel was pinned to a single variety. Residual within-grade
  quality differences are not observable in this data and would push the
  number down further.
- **The binding assumption is which markets you count**, not freight. At a
  45% coverage bar the saving is 22.2%; at 65% it is 35.5%. Freight barely
  matters — doubling it moves the answer by 0.3 points — because the price
  gap dwarfs the haulage.
- **Unlimited quantity is assumed.** The model buys 115 tonnes a week at the
  cheapest market's modal price. No market depth data exists in this feed,
  and a real buyer would move the price they are transacting against.

---

*Method and every threshold in [METHOD.md](../METHOD.md); full caveats in
[LIMITATIONS.md](../LIMITATIONS.md). The week-by-week audit trail is in
[weekly_log_sample.csv](weekly_log_sample.csv) — every rupee traces to a
market, a date and a price that existed on the decision day.*
