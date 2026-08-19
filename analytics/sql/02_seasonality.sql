-- GRAIN: one row per (commodity, month)
-- Seasonal index, 100 = the commodity's typical month.
-- The baseline is the unweighted mean of the twelve monthly averages, not
-- the mean of all daily prices, so a 31-day month does not carry more
-- weight than a 28-day one purely because of the calendar.
WITH observations AS (
    SELECT c.commodity_canonical,
           d.month,
           d.month_name,
           f.modal_price_inr_qtl
    FROM fct_price_daily f
    JOIN dim_market    m USING (market_sk)
    JOIN dim_commodity c USING (commodity_sk)
    JOIN dim_date      d USING (date_key)
    WHERE m.is_included
      AND NOT COALESCE(f.is_outlier, FALSE)
      AND c.commodity_canonical = ?
),
monthly AS (
    SELECT commodity_canonical,
           month,
           ANY_VALUE(month_name)          AS month_name,
           AVG(modal_price_inr_qtl)       AS month_avg_inr_qtl,
           COUNT(*)                       AS observations
    FROM observations
    GROUP BY commodity_canonical, month
)
SELECT commodity_canonical,
       month,
       month_name,
       month_avg_inr_qtl,
       observations,
       100.0 * month_avg_inr_qtl / AVG(month_avg_inr_qtl) OVER ()
           AS seasonal_index
FROM monthly
ORDER BY month
