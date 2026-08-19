-- GRAIN: one row per (market, commodity)
-- Reporting days as a share of the market's own observed span, matching
-- the inclusion rule applied to dim_market. Gaps stay gaps: a day with no
-- report contributes nothing and is never interpolated.
SELECT m.market_canonical,
       c.commodity_canonical,
       m.state,
       m.district,
       m.is_included,
       COUNT(*)                                            AS observations,
       COUNT(DISTINCT f.date_key)                          AS reporting_days,
       MIN(f.date_key)                                     AS first_date,
       MAX(f.date_key)                                     AS last_date,
       DATE_DIFF('day', MIN(f.date_key), MAX(f.date_key)) + 1
                                                           AS span_days,
       100.0 * COUNT(DISTINCT f.date_key)
             / (DATE_DIFF('day', MIN(f.date_key), MAX(f.date_key)) + 1)
                                                           AS coverage_pct,
       SUM(CASE WHEN f.is_outlier THEN 1 ELSE 0 END)       AS outliers
FROM fct_price_daily f
JOIN dim_market    m USING (market_sk)
JOIN dim_commodity c USING (commodity_sk)
GROUP BY m.market_canonical, c.commodity_canonical, m.state, m.district,
         m.is_included
ORDER BY observations DESC
