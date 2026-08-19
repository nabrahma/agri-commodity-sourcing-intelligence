# Limitations

What this analysis does not capture, and what that does to the number.
Read this before quoting any figure from the dashboard or the brief.

---

## 0. Grade mixing - the largest error found, and only partly fixed

Markets quote different grades under a single commodity name. Sambhal lists
Red onion at ~₹1,608 a quintal; Sikar lists 1st Sort at ~₹978; Harda lists
Medium at ~₹830. The two never quote the same variety on the same day.

Comparing across grades turns a quality difference into a phantom spatial
arbitrage. Doing exactly that produced a **50.4% saving**, which fell to
**35.5%** once the panel was pinned to one variety per commodity. The build
spec's "a saving above 30% means you have a bug" tripwire is what caught it.

**What is still wrong:** pinning to a named variety removes the gross error
but not the residual one. "Red" onion in Sambhal and "Red" onion 400 km away
are not guaranteed to be the same size, dryness or keeping quality, and the
feed carries nothing that would let anyone check. Whatever quality gap
remains is being counted as a saving, so **35.5% should be read as an upper
bound, not an estimate.**

---

## 1. Survivorship bias in the market set

Only markets clearing **55% coverage and 200 observations**, and having
known coordinates, enter any headline metric. That threshold is not neutral: markets that report
patchily are disproportionately smaller and more remote, and those are
exactly the markets where prices are likeliest to diverge from the
well-covered ones.

**Effect on the number:** the spread is measured across a set of markets
that are, by construction, the best-behaved. The true spread across *all*
markets is probably wider, so the arbitrage opportunity may be understated.
Against that, the excluded markets may be thin for reasons that also make
them unusable in practice - a market reporting twice a month cannot supply
a weekly buyer.

**This is the binding assumption.** Swept at 45 / 55 / 65, the saving moves
from **22.2% to 35.5%** - a 13-point swing, far larger than any other
parameter. The direction survives (S2 beats S1 in every run) but the
magnitude does not.

The 55% threshold is itself a judgement made against this data: the archive
is not a true daily series (median market coverage 50.7%), and at the build
spec's original 70% only **4 markets** qualified - too few to compute a
spread at all.

---

## 2. Transport cost is an assumption, not an observation

`transport_inr_per_qtl_per_100km = 4.0` is a flat, linear, assumed rate.
Real freight is none of those things: it is negotiated, varies by season,
lane and truck availability, has minimums, and does not scale linearly with
distance. The model also uses **great-circle distance**, which is shorter
than any real road - typically by 20-30% in this geography.

**Effect on the number: far smaller than expected.** Doubling freight from
₹4 to ₹6 per quintal per 100 km moves the saving by **0.3 percentage
points**. The price gap between markets (₹500+/quintal) dwarfs the haulage
(₹5-15/quintal at these distances).

That is worth stating plainly because it inverts the prior: on synthetic
data transport ranked first in the tornado; on real data it ranks second to
last. Freight is not what this conclusion hangs on - market selection is.

---

## 3. Market commission and handling are excluded

`market_commission_pct` is set to **0.0** and no grading, loading,
weighment or handling loss is modelled. In practice a buyer pays commission
to the market, loses some weight to grading rejection, and pays for
loading.

**Effect on the number:** these costs are broadly proportional to the value
purchased and apply at *every* market, so they mostly cancel between
strategies. They do not cancel entirely - commission rates differ by state,
and a distant market may have a different rate than the home market. The
absolute cost figures are therefore too low; the *relative* comparison
between S1, S2 and S3 is affected less.

---

## 4. The price panel is thinner than a real buyer's information

Three specific gaps:

- **No arrival quantity.** The feed carries prices only. A market may be
  quoting ₹1,400 on a volume no real buyer could lift. Everything labelled
  "reporting intensity" is a count of reporting markets, not tonnage.
- **Modal price is not a transacted price.** It is the most common price
  reported for the day, not a price anyone actually paid for this specific
  lot, quality and quantity.
- **Missing days stay missing.** Coverage is genuinely below 100% for most
  markets. Nothing is interpolated, which is correct, but it means the
  simulation sometimes works from a quote up to seven days old.

**Effect on the number:** the simulation assumes any listed price is
available in unlimited quantity, which is optimistic. Real execution would
capture less of the modelled saving.

---

## 5. No forecasting, and that is deliberate

The saving here comes from **spatial arbitrage observable at the moment of
purchase**, not from predicting where prices will go. S3's timing rule uses
only a trailing average and buys ahead when today's price is already low
relative to its own recent history.

This is a limitation only if you wanted a forecast. A forecasting model
would add estimation error without changing the weekly decision, because
the buyer must purchase every week regardless. A forecast would only earn
its keep if the buyer had to commit volume in advance.

---

## 6. Scope and horizon

- One commodity at a time; no substitution between commodities is modelled.
- One home market as the S1 baseline. A buyer with several depots would
  face a different, easier problem.
- Storage is modelled as a simple weekly cap with a flat cost and a flat
  shrinkage rate. Real cold storage has step costs, minimum contract terms,
  and shrinkage that varies with how long the stock has already been held.
- Purchases are continuous quantities. Real freight comes in truck-loads,
  which would make small optimisations unrealisable.

---

## How much of this matters

The honest summary: **the direction is robust, the magnitude is not.** S2
beat S1 in every one of the 18 sensitivity runs, and the price dispersion
between markets is large, persistent and visible at purchase time.

But the headline percentage is soft in three specific ways, in descending
order of size: residual grade differences that this data cannot resolve
(§0), the coverage threshold that decides which markets count (§1), and the
assumption that unlimited quantity is available at the quoted price (§4).
Read the finding as *"a buyer anchored to an expensive market is probably
leaving 20-35% on the table"* - not as a number to put in a budget.
