-- =====================================================================
-- analysis_queries.sql — 6 business questions
--
-- Each query starts with a header line "-- Qn: <question>".
-- src/04_analysis.py splits this file on those headers and runs each one.
-- Revenue = item_total = price + freight_value.
-- =====================================================================


-- Q1: What are the top 10 product categories by revenue, and what share of total revenue does each hold?
-- CTE computes the grand total ONCE, so each row can be divided by it.
WITH total AS (
    SELECT SUM(total_revenue) AS all_revenue
    FROM mart_sales_by_category
)
SELECT
    c.revenue_rank,
    c.category_en,
    c.total_revenue,
    ROUND(c.total_revenue / t.all_revenue * 100, 2) AS pct_of_total_revenue
FROM mart_sales_by_category c
-- CROSS JOIN with a 1-row table = "attach the total to every row".
CROSS JOIN total t
ORDER BY c.total_revenue DESC
LIMIT 10;


-- Q2: How did monthly revenue change month over month? (3 best and 3 worst growth months)
-- Months are only ranked if the PREVIOUS month had at least R$100k revenue.
-- Late 2016 has only a handful of orders (1 order in Sep, 1 in Dec), so
-- "growth" against those months is meaningless (e.g. +649,657%).
WITH eligible AS (
    SELECT year_month, total_revenue, prev_month_revenue, mom_growth_pct
    FROM mart_monthly_sales
    WHERE prev_month_revenue >= 100000
),
best AS (
    SELECT 'best' AS kind, * FROM eligible ORDER BY mom_growth_pct DESC LIMIT 3
),
worst AS (
    SELECT 'worst' AS kind, * FROM eligible ORDER BY mom_growth_pct ASC LIMIT 3
)
-- UNION ALL stacks the two result sets (ALL = don't bother removing duplicates).
SELECT * FROM best
UNION ALL
SELECT * FROM worst;


-- Q3: Who are the top 10 customers by lifetime spend?
WITH ranked AS (
    SELECT
        -- ROW_NUMBER gives a unique 1, 2, 3... even on ties (unlike RANK),
        -- so "top 10" is always exactly 10 rows.
        ROW_NUMBER() OVER (ORDER BY total_spent DESC) AS spend_rank,
        customer_key,
        total_spent,
        order_count,
        value_tier
    FROM mart_customer_value
)
SELECT *
FROM ranked
WHERE spend_rank <= 10     -- filtering on the window result needs the CTE (see Q5)
ORDER BY spend_rank;


-- Q4: What proportion of customers ordered more than once, and do repeat customers spend more per order?
-- Uses customer_key (= customer_unique_id, a real person). With customer_id
-- every customer would have exactly 1 order and "repeat" would be 0%.
WITH labeled AS (
    SELECT
        CASE WHEN order_count > 1 THEN 'repeat' ELSE 'one-time' END AS customer_type,
        total_spent,
        order_count
    FROM mart_customer_value
)
SELECT
    customer_type,
    COUNT(*) AS customers,
    -- SUM(COUNT(*)) OVER () = total customers across ALL groups. The window
    -- runs after GROUP BY, so it sees both groups and can add them up.
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct_of_customers,
    -- Total money / total orders = true average order value for the group.
    ROUND(SUM(total_spent) / SUM(order_count), 2)      AS avg_spend_per_order,
    ROUND(AVG(total_spent), 2)                         AS avg_lifetime_spend
FROM labeled
GROUP BY customer_type
ORDER BY customer_type;


-- Q5: Within each product category, what are the top 3 products by revenue?
-- Why a CTE: SQL evaluates WHERE *before* window functions are computed,
-- so "WHERE RANK() OVER (...) <= 3" is not allowed. We compute the rank in
-- a CTE first, then filter on it in the outer query.
WITH product_revenue AS (
    SELECT
        p.category_en,
        f.product_key,
        SUM(f.item_total) AS revenue,
        COUNT(*)          AS items_sold
    FROM fact_order_items f
    JOIN dim_products p ON f.product_key = p.product_key
    GROUP BY p.category_en, f.product_key
),
ranked AS (
    SELECT
        *,
        -- PARTITION BY = restart the ranking for each category.
        RANK() OVER (PARTITION BY category_en ORDER BY revenue DESC) AS rank_in_category
    FROM product_revenue
)
SELECT category_en, rank_in_category, product_key, ROUND(revenue, 2) AS revenue, items_sold
FROM ranked
WHERE rank_in_category <= 3
ORDER BY category_en, rank_in_category;


-- Q6: Which 10 states have the worst late-delivery rate (minimum 100 orders)?
-- delivered_late is an ORDER-level fact repeated on every item row, so we
-- first collapse to one row per order; otherwise orders with many items
-- would count several times.
WITH orders AS (
    SELECT DISTINCT order_id, customer_key, delivered_late
    FROM fact_order_items
)
SELECT
    c.customer_state,
    COUNT(*)                              AS orders,
    CAST(SUM(o.delivered_late) AS INTEGER) AS late_orders,   -- cast: SUM returns a 128-bit int pandas shows as float
    -- delivered_late is 0/1, so its average IS the fraction late.
    ROUND(AVG(o.delivered_late) * 100, 2) AS late_rate_pct
FROM orders o
JOIN dim_customers c ON o.customer_key = c.customer_key
GROUP BY c.customer_state
-- HAVING filters GROUPS after aggregation (WHERE filters rows before it).
-- COUNT(*) only exists after grouping, so this condition must be in HAVING.
HAVING COUNT(*) >= 100
ORDER BY late_rate_pct DESC
LIMIT 10;
