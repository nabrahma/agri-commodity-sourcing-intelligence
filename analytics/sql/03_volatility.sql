-- GRAIN: one row per (market, commodity, fiscal_year)
-- Coefficient of variation of the modal price. Sample standard deviation,
-- so a market with a single observation yields NULL rather than a
-- misleading zero.
SELECT m.market_canonical,
       c.commodity_canonical,
       d.fiscal_year,
       COUNT(*)                                       AS observations,
       AVG(f.modal_price_inr_qtl)                     AS mean_inr_qtl,
       COALESCE(STDDEV_SAMP(f.modal_price_inr_qtl), 0.0)
                                                      AS stddev_inr_qtl,
       COALESCE(STDDEV_SAMP(f.modal_price_inr_qtl), 0.0)
           / NULLIF(AVG(f.modal_price_inr_qtl), 0)    AS cv,
       MIN(f.modal_price_inr_qtl)                     AS min_inr_qtl,
       MAX(f.modal_price_inr_qtl)                     AS max_inr_qtl
FROM fct_price_daily f
JOIN dim_market    m USING (market_sk)
JOIN dim_commodity c USING (commodity_sk)
JOIN dim_date      d USING (date_key)
WHERE m.is_included
  AND NOT COALESCE(f.is_outlier, FALSE)
  AND c.commodity_canonical = ?
GROUP BY m.market_canonical, c.commodity_canonical, d.fiscal_year
HAVING COUNT(*) >= ?
ORDER BY cv DESC
