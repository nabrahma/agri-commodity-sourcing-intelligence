# Data quality

Generated 2026-08-19 from the current landing zone. Do not edit by hand.

## Conservation

| Stage | Rows |
|---|---|
| Raw records landed | 1,307,905 |
| Outside configured scope (state / commodity) | 512,553 |
| Records considered | 795,352 |
| Clean records kept | 535,547 |
| Records quarantined | 259,805 |
| Retention | 67.33% |

Scope exclusion is a deliberate filter, not a data-quality failure, so it is reported separately. Of the records considered, every one is either kept or quarantined with a reason, and the two counts always sum to the total; there is an assertion for it.

## Rejections by reason

| Reason | Rows | % of raw |
|---|---|---|
| `UNKNOWN_MARKET` | 248,382 | 31.23% |
| `DUPLICATE_GRAIN` | 8,624 | 1.08% |
| `NON_POSITIVE_PRICE` | 1,844 | 0.23% |
| `UNPARSEABLE_PRICE` | 955 | 0.12% |

## Coverage by market

| market_canonical     |   observations |   reporting_days | first_date   | last_date   |   outliers |   coverage_pct |
|:---------------------|---------------:|-----------------:|:-------------|:------------|-----------:|---------------:|
| Durgapur             |           3174 |              840 | 2019-01-01   | 2023-01-24  |          2 |          56.57 |
| Bangalore            |           3054 |              684 | 2019-01-01   | 2023-01-23  |          7 |          46.09 |
| Dadri                |           2940 |              748 | 2019-01-03   | 2023-01-24  |         11 |          50.44 |
| Faizabad             |           2844 |              883 | 2019-01-01   | 2023-01-24  |          0 |          59.46 |
| Hubli                |           2738 |              721 | 2019-01-01   | 2023-01-26  |          1 |          48.49 |
| Pune                 |           2700 |              822 | 2019-01-01   | 2023-01-26  |          3 |          55.28 |
| Habra                |           2601 |              920 | 2019-01-01   | 2023-01-24  |          0 |          61.95 |
| Sambhal              |           2560 |              928 | 2019-01-01   | 2023-01-26  |          5 |          62.41 |
| Pratapgarh           |           2549 |              911 | 2019-01-02   | 2023-01-25  |          0 |          61.35 |
| Uluberia             |           2517 |              894 | 2019-01-01   | 2023-01-22  |          0 |          60.28 |
| Sultanpur            |           2511 |              894 | 2019-01-01   | 2023-01-25  |          0 |          60.16 |
| Barasat              |           2503 |              884 | 2019-01-01   | 2023-01-26  |          1 |          59.45 |
| Muzzafarnagar        |           2503 |              887 | 2019-01-01   | 2023-01-25  |          7 |          59.69 |
| Anwala               |           2498 |              885 | 2019-01-01   | 2023-01-24  |          0 |          59.6  |
| Basti                |           2461 |              871 | 2019-01-01   | 2023-01-25  |          8 |          58.61 |
| Pilibhit             |           2445 |              877 | 2019-01-01   | 2023-01-25  |          9 |          59.02 |
| Chandoli             |           2442 |              864 | 2019-01-02   | 2023-01-26  |          9 |          58.14 |
| Lakhimpur            |           2440 |              876 | 2019-01-01   | 2023-01-25  |          0 |          58.95 |
| Badayoun             |           2428 |              861 | 2019-01-02   | 2023-01-25  |          0 |          57.98 |
| Puwaha               |           2425 |              882 | 2019-01-01   | 2023-01-26  |          3 |          59.31 |
| Ranaghat             |           2403 |              853 | 2019-01-01   | 2023-01-25  |          0 |          57.4  |
| Saharanpur           |           2396 |              849 | 2019-01-01   | 2023-01-25  |         13 |          57.13 |
| Muradabad            |           2395 |              843 | 2019-01-01   | 2023-01-25  |          5 |          56.73 |
| Lucknow              |           2394 |              851 | 2019-01-01   | 2023-01-25  |          0 |          57.27 |
| Puranpur             |           2389 |              874 | 2019-01-01   | 2023-01-26  |          7 |          58.78 |
| Bareilly             |           2381 |              864 | 2019-01-01   | 2023-01-25  |          1 |          58.14 |
| Dahod                |           2371 |              850 | 2019-01-01   | 2023-01-25  |          0 |          57.2  |
| Moth                 |           2369 |              848 | 2019-01-01   | 2023-01-25  |         17 |          57.07 |
| Siliguri             |           2368 |              563 | 2019-01-01   | 2023-01-24  |          4 |          37.91 |
| Purwa                |           2362 |              867 | 2019-01-01   | 2023-01-25  |          0 |          58.34 |
| Asansol              |           2358 |              844 | 2019-01-01   | 2023-01-24  |          0 |          56.84 |
| Ramkrishanpur        |           2354 |              837 | 2019-01-01   | 2023-01-24  |          0 |          56.36 |
| Wazirganj            |           2338 |              832 | 2019-01-12   | 2023-01-24  |          7 |          56.45 |
| Muskara              |           2330 |              831 | 2019-01-01   | 2023-01-22  |         26 |          56.04 |
| Tulsipur             |           2304 |              817 | 2020-01-01   | 2023-01-25  |          0 |          72.88 |
| Amroha               |           2302 |              814 | 2019-01-01   | 2023-01-24  |          2 |          54.81 |
| Thanabhawan          |           2297 |              855 | 2019-01-01   | 2023-01-24  |          0 |          57.58 |
| Madanganj Kishanganj |           2291 |              811 | 2020-01-01   | 2023-01-23  |          8 |          72.48 |
| Ahmedabad            |           2285 |              630 | 2019-01-01   | 2023-01-25  |          0 |          42.4  |
| Bilsi                |           2279 |              812 | 2019-01-01   | 2023-01-21  |          0 |          54.79 |
| Nawabganj            |           2272 |              817 | 2020-01-01   | 2023-01-23  |         18 |          73.01 |
| Mauranipur           |           2261 |              834 | 2019-01-01   | 2023-01-25  |         49 |          56.12 |
| Maudaha              |           2244 |              801 | 2019-01-01   | 2023-01-24  |         29 |          53.94 |
| Karvi                |           2236 |              799 | 2019-01-01   | 2023-01-22  |         21 |          53.88 |
| Ghaziabad            |           2235 |              793 | 2019-01-02   | 2023-01-24  |          5 |          53.44 |
| Chomu                |           2233 |              838 | 2019-01-01   | 2023-01-24  |          0 |          56.43 |
| Fatehpur             |           2231 |              789 | 2019-01-01   | 2023-01-25  |          1 |          53.1  |
| Anandnagar           |           2229 |              788 | 2019-01-01   | 2023-01-25  |          4 |          53.03 |
| Choubepur            |           2227 |              786 | 2019-01-01   | 2023-01-25  |          5 |          52.89 |
| Harda                |           2225 |              825 | 2019-01-02   | 2023-01-25  |         27 |          55.56 |

Coverage is reporting days as a share of the market's own observed span. Gaps are left as gaps; no missing day is interpolated.
