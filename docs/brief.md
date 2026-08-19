# Where you buy costs more than what you pay

**Sourcing intelligence for a fixed-volume agricultural buyer — one page.**

> **Provenance.** Every figure below comes from the committed **fixture
> panel** (`source=fixture`), not from observed market data. The pipeline,
> the method and the numbers are reproducible with `make all`; the figures
> become real the moment a `DATA_GOV_API_KEY` is supplied and the same
> commands are run against the live feed. Nothing here has been rounded
> toward a nicer story.

---

## Question

For a buyer purchasing 500 tonnes of onion a month, how much of the annual
purchase cost is decided by **which market** they buy from and **when**,
rather than by the market price itself?

## Method

- Daily wholesale prices across eight markets, cleaned to a validated
  panel with every rejected row reasoned and counted; missing days left
  missing, never interpolated.
- A landed-cost model — modal price plus freight — so markets are compared
  on what they actually cost to buy from, not on their headline price.
- A week-by-week simulation of three sourcing strategies over twelve
  months, where every decision is taken through a price view filtered to
  the decision date, making it structurally impossible to see a future
  price.

## Finding 1 — the same commodity, the same day, very different prices

The median trading day shows a **19.3% spread** between the cheapest and
the dearest reporting market (interquartile range 16.3% to 24.6%; never
below 15.0% on any day in the panel). This is dispersion on a single day,
not across seasons or years — it is available to a buyer at the moment of
purchase, with no forecast required.

One market, **Solapur, was the cheapest on 100% of days**. That
concentration is itself a finding: the opportunity is not a shifting
patchwork requiring constant re-optimisation, it is a standing structural
gap between two specific markets.

## Finding 2 — seasonality is real but smaller than it looks

The seasonal index runs from a **trough of 74.7 in October to a peak of
125.1 in April** — a swing of about 50 index points around the annual
average. That is a wide band, but it is not directly bankable: the buyer
must purchase every week regardless, and capturing the trough requires
storage, which costs ₹15 per quintal per week and loses 3% of the stock to
shrinkage every week it is held.

## Finding 3 — the achievable saving is spatial, and it is modest

| Strategy | Cost per quintal | Annual cost | Saving vs S1 |
|---|---|---|---|
| S1 — always buy at the home market | ₹1,600.0 | ₹960.0 lakh | — |
| S2 — lowest landed cost within 500 km | ₹1,453.1 | ₹871.8 lakh | **₹88.1 lakh (9.18%)** |
| S3 — S2 plus buying ahead on price dips | ₹1,453.1 | ₹871.8 lakh | ₹88.1 lakh (9.18%) |

**S2 saves ₹88.1 lakh a year, 9.18%,** on a 6,000-tonne programme.

**S3 adds exactly nothing.** On this panel no price dip is ever deep enough
to break the 0.90 × MA20 trigger, so the stockpiling rule never fires and
S3 collapses onto S2. Where it does fire on steeper panels, storage and
shrinkage consume most of the gain. That is worth stating plainly: the
timing strategy — the more sophisticated-sounding one — earned nothing
here.

The **binding assumption is transport cost**, which the sensitivity tornado
ranks first by a wide margin. The strategy ranking survives the plausible
range of that parameter; the magnitude does not.

## Recommendation

**Move weekly purchasing from a single home market to a lowest-landed-cost
rule across markets already within 500 km.** Expected saving **₹80–90 lakh
a year**, contingent on freight holding near ₹4 per quintal per 100 km.

Before committing: **get a real freight quote on the Lasalgaon–Solapur
lane.** One number decides most of this answer, and it is the one thing
here that is assumed rather than observed. That quote costs a phone call;
the analysis behind it does not get more reliable without it.

## Limitations

- **Freight is assumed, not observed**, and great-circle distance
  understates road distance by 20–30%. Both errors push the same way and
  **overstate** the saving.
- **Market commission and grading loss are excluded.** Absolute costs are
  too low; the comparison between strategies is affected less, since these
  costs apply at every market.
- **Only markets clearing 70% coverage are included**, so the market set is
  by construction the best-reporting one — which may understate the true
  spread while overstating how much of it is practically accessible.

---

*Full method and every threshold in [METHOD.md](../METHOD.md); full caveats
in [LIMITATIONS.md](../LIMITATIONS.md). The week-by-week audit trail behind
the S2 figure is in [weekly_log_sample.csv](weekly_log_sample.csv) — every
rupee traces to a market, a date and a price that existed on the decision
day.*
