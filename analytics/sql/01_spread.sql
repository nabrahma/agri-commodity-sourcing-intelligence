-- GRAIN: one row per (date, commodity)
-- Spatial price spread across reporting markets on a single day.
-- Outliers and low-coverage markets are excluded: one flagged 10x print
-- would otherwise set the maximum and drive the whole headline number.
-- spread_pct is measured against the cheapest market, because that is the
-- price a buyer could actually have paid.
WITH included AS (
    SELECT f.date_key,
           c.commodity_canonical,
           m.market_canonical,
           f.modal_price_inr_qtl
    FROM fct_price_daily f
    JOIN dim_market    m USING (market_sk)
    JOIN dim_commodity c USING (commodity_sk)
    WHERE m.is_included
      AND NOT COALESCE(f.is_outlier, FALSE)
      AND c.commodity_canonical = ?
)
SELECT date_key,
       commodity_canonical,
       COUNT(DISTINCT market_canonical)                    AS markets_reporting,
       MIN(modal_price_inr_qtl)                            AS min_modal_inr_qtl,
       MAX(modal_price_inr_qtl)                            AS max_modal_inr_qtl,
       AVG(modal_price_inr_qtl)                            AS avg_modal_inr_qtl,
       MEDIAN(modal_price_inr_qtl)                         AS median_modal_inr_qtl,
       100.0 * (MAX(modal_price_inr_qtl) - MIN(modal_price_inr_qtl))
             / MIN(modal_price_inr_qtl)                    AS spread_pct,
       ARG_MIN(market_canonical, modal_price_inr_qtl)      AS cheapest_market,
       ARG_MAX(market_canonical, modal_price_inr_qtl)      AS dearest_market
FROM included
GROUP BY date_key, commodity_canonical
HAVING COUNT(DISTINCT market_canonical) >= ?
ORDER BY date_key
