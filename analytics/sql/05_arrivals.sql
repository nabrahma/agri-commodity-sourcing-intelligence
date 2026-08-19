-- GRAIN: one row per (date, commodity)
-- Reporting intensity, NOT arrival tonnage. This feed carries prices only;
-- it has no quantity field. The count of reporting markets is the closest
-- honest proxy for market activity, and is labelled as such everywhere it
-- is displayed.
SELECT f.date_key,
       c.commodity_canonical,
       COUNT(DISTINCT m.market_canonical)                  AS markets_reporting,
       COUNT(*)                                            AS observations,
       SUM(CASE WHEN m.is_included THEN 1 ELSE 0 END)      AS observations_included,
       AVG(f.modal_price_inr_qtl)                          AS avg_modal_inr_qtl
FROM fct_price_daily f
JOIN dim_market    m USING (market_sk)
JOIN dim_commodity c USING (commodity_sk)
WHERE c.commodity_canonical = ?
GROUP BY f.date_key, c.commodity_canonical
ORDER BY f.date_key
