# Limitations

What this analysis does not capture, and what that does to the number.
Read this before quoting any figure from the dashboard or the brief.

---

## 1. Survivorship bias in the market set

Only markets clearing **70% coverage and 200 observations** enter any
headline metric. That threshold is not neutral: markets that report
patchily are disproportionately smaller and more remote, and those are
exactly the markets where prices are likeliest to diverge from the
well-covered ones.

**Effect on the number:** the spread is measured across a set of markets
that are, by construction, the best-behaved. The true spread across *all*
markets is probably wider, so the arbitrage opportunity may be understated.
Against that, the excluded markets may be thin for reasons that also make
them unusable in practice — a market reporting twice a month cannot supply
a weekly buyer.

**How to check it:** `min_coverage_pct` is swept at 60 / 70 / 80 in the
sensitivity grid. If the conclusion flips inside that range, it is not a
conclusion.

---

## 2. Transport cost is an assumption, not an observation

`transport_inr_per_qtl_per_100km = 4.0` is a flat, linear, assumed rate.
Real freight is none of those things: it is negotiated, varies by season,
lane and truck availability, has minimums, and does not scale linearly with
distance. The model also uses **great-circle distance**, which is shorter
than any real road — typically by 20–30% in this geography.

**Effect on the number:** both errors push the same way. Understated
freight makes distant markets look cheaper than they are, which
**overstates** the S2 saving.

This is the **binding assumption** — the sensitivity tornado ranks it
first. Before anyone acts on this analysis, the right next step is a real
freight quote on the two or three lanes that actually matter, not more
modelling.

---

## 3. Market commission and handling are excluded

`market_commission_pct` is set to **0.0** and no grading, loading,
weighment or handling loss is modelled. In practice a buyer pays commission
to the market, loses some weight to grading rejection, and pays for
loading.

**Effect on the number:** these costs are broadly proportional to the value
purchased and apply at *every* market, so they mostly cancel between
strategies. They do not cancel entirely — commission rates differ by state,
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

The honest summary: **the direction of the finding is robust, the
magnitude is not.** Spatial price dispersion between markets is large and
real, and it is visible at purchase time. Whether capturing it is worth the
freight is decided almost entirely by one number that this project assumes
rather than observes. The sensitivity analysis exists to make that
dependence explicit rather than to hide it.
