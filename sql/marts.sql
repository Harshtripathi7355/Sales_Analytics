-- =====================================================================
-- marts.sql — pre-aggregated summary tables ("marts")
--
-- A mart is a saved query result: the joins and GROUP BYs are done once
-- here, so later analysis can read a small ready-made table instead of
-- re-joining ~110k fact rows every time.
--
-- "Revenue" throughout = item_total = price + freight_value, i.e. what
-- the customer actually paid for each order line.
-- =====================================================================


-- ---------------------------------------------------------------------
-- mart_sales_by_category: one row per English product category
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE mart_sales_by_category AS
SELECT
    p.category_en,
    ROUND(SUM(f.item_total), 2)          AS total_revenue,
    -- DISTINCT: one order can contain several items from the same category,
    -- and we want to count that order once.
    COUNT(DISTINCT f.order_id)           AS order_count,
    COUNT(*)                             AS items_sold,     -- 1 fact row = 1 item
    ROUND(AVG(f.price), 2)               AS avg_item_price,
    -- Window function: runs AFTER the GROUP BY, over the grouped rows, so it
    -- can rank categories by their totals. RANK gives ties the same number.
    RANK() OVER (ORDER BY SUM(f.item_total) DESC) AS revenue_rank
FROM fact_order_items f
-- INNER JOIN is safe: every fact row has a product (enforced by the FK).
JOIN dim_products p ON f.product_key = p.product_key
GROUP BY p.category_en
ORDER BY revenue_rank;


-- ---------------------------------------------------------------------
-- mart_monthly_sales: one row per year_month, with month-over-month growth
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE mart_monthly_sales AS
-- CTE 1: plain monthly totals.
WITH monthly AS (
    SELECT
        d.year_month,
        SUM(f.item_total)              AS total_revenue,
        COUNT(DISTINCT f.order_id)     AS order_count,
        COUNT(DISTINCT f.customer_key) AS unique_customers   -- real people (unique_id)
    FROM fact_order_items f
    -- Join the date dimension to get year_month without date functions here.
    JOIN dim_dates d ON f.order_date_key = d.date_key
    GROUP BY d.year_month
),
-- CTE 2: attach the previous month's revenue to each row.
-- LAG(x) = "the value of x from the previous row", in year_month order.
-- Kept in its own CTE so the growth formula below can use the name
-- prev_month_revenue. Most databases (PostgreSQL, SQL Server, MySQL) do NOT
-- allow reusing an alias in the same SELECT that creates it; DuckDB happens
-- to allow it, but the CTE version is portable and easier to read.
with_prev AS (
    SELECT
        *,
        LAG(total_revenue) OVER (ORDER BY year_month) AS prev_month_revenue
    FROM monthly
)
SELECT
    year_month,
    ROUND(total_revenue, 2)       AS total_revenue,
    order_count,
    unique_customers,
    ROUND(prev_month_revenue, 2)  AS prev_month_revenue,
    -- NULLIF(prev, 0) turns a 0 into NULL, so dividing gives NULL instead of
    -- a divide-by-zero problem (an error in most databases, 'inf' in DuckDB).
    -- The first month has no previous month -> NULL.
    ROUND((total_revenue - prev_month_revenue)
          / NULLIF(prev_month_revenue, 0) * 100, 2) AS mom_growth_pct
FROM with_prev
ORDER BY year_month;


-- ---------------------------------------------------------------------
-- mart_customer_value: one row per real customer (customer_unique_id)
-- ---------------------------------------------------------------------
CREATE OR REPLACE TABLE mart_customer_value AS
-- CTE: aggregate first, so the CASE below can refer to total_spent by name.
WITH per_customer AS (
    SELECT
        customer_key,
        SUM(item_total)            AS total_spent,
        COUNT(DISTINCT order_id)   AS order_count,
        MIN(order_date_key)        AS first_order_date,
        MAX(order_date_key)        AS last_order_date
    FROM fact_order_items
    GROUP BY customer_key
)
SELECT
    customer_key,
    ROUND(total_spent, 2)                                    AS total_spent,
    order_count,
    first_order_date,
    last_order_date,
    -- Date arithmetic: days between first and last purchase (0 = bought once).
    DATE_DIFF('day', first_order_date, last_order_date)      AS customer_tenure_days,
    -- CASE checks conditions top-down and stops at the first match,
    -- so the >= 150 branch only sees customers who are already < 500.
    CASE
        WHEN total_spent >= 500 THEN 'High'
        WHEN total_spent >= 150 THEN 'Medium'
        ELSE 'Low'
    END                                                      AS value_tier
FROM per_customer;
