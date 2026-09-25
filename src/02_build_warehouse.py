"""
Stage 2 — Build the star schema.

Takes the flat stg_* tables from Stage 1 and reshapes them into:
    - dim_customers, dim_products, dim_dates   (descriptive context)
    - fact_order_items                         (the measurements)

Table definitions live in sql/schema.sql. This script runs that file to
create empty tables, then fills each one with an INSERT ... SELECT.
Dimensions are filled before the fact table because the fact table's
foreign keys must point at rows that already exist.
"""

from pathlib import Path

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "warehouse.duckdb"
SCHEMA_PATH = PROJECT_ROOT / "sql" / "schema.sql"


LOAD_DIM_CUSTOMERS = """
INSERT INTO dim_customers
-- CTE: first rank each person's customer rows by order date, then keep the top one.
WITH ranked AS (
    SELECT
        c.customer_unique_id,
        c.customer_city,
        c.customer_state,
        -- One person can appear many times (one customer_id per order).
        -- ROW_NUMBER numbers their rows newest-first, so row 1 = most recent
        -- city/state. PARTITION BY restarts the numbering for each person.
        ROW_NUMBER() OVER (
            PARTITION BY c.customer_unique_id
            ORDER BY o.order_purchase_timestamp DESC NULLS LAST
        ) AS rn
    FROM stg_customers c
    -- LEFT JOIN (not INNER): keep customers whose orders were filtered out in
    -- Stage 1 too; they just sort last because their timestamp is NULL.
    LEFT JOIN stg_orders o ON o.customer_id = c.customer_id
)
SELECT customer_unique_id, customer_city, customer_state
FROM ranked
WHERE rn = 1;   -- exactly one row per person -> safe for the PRIMARY KEY
"""

LOAD_DIM_PRODUCTS = """
INSERT INTO dim_products
SELECT
    p.product_id,
    p.product_category_name,
    -- COALESCE picks the first non-NULL value: the English name if the
    -- translation exists, otherwise 'unknown'.
    COALESCE(t.product_category_name_english, 'unknown')
FROM stg_products p
-- LEFT JOIN so a product with no translation is kept (not silently dropped).
LEFT JOIN stg_category_translation t
    ON p.product_category_name = t.product_category_name;
"""

LOAD_DIM_DATES = """
INSERT INTO dim_dates
SELECT
    d                          AS date_key,
    EXTRACT(year FROM d)       AS year,
    EXTRACT(month FROM d)      AS month,
    STRFTIME(d, '%B')          AS month_name,    -- 'January', 'February', ...
    EXTRACT(quarter FROM d)    AS quarter,
    STRFTIME(d, '%Y-%m')       AS year_month,    -- '2017-05'
    STRFTIME(d, '%A')          AS day_of_week    -- 'Monday', ...
FROM (
    -- Timestamps include the time of day; casting to DATE drops it, and
    -- DISTINCT leaves one row per calendar day.
    SELECT DISTINCT CAST(order_purchase_timestamp AS DATE) AS d
    FROM stg_orders
);
"""

LOAD_FACT = """
INSERT INTO fact_order_items
SELECT
    oi.order_id,
    oi.order_item_id,
    c.customer_unique_id                          AS customer_key,
    oi.product_id                                 AS product_key,
    CAST(o.order_purchase_timestamp AS DATE)      AS order_date_key,
    oi.price,
    oi.freight_value,
    oi.item_total,
    o.delivery_days,
    o.delivered_late
FROM stg_order_items oi
-- INNER JOIN: only keep items whose order survived cleaning (delivered orders).
-- Items belonging to cancelled/undelivered orders are dropped here.
INNER JOIN stg_orders o    ON oi.order_id = o.order_id
-- INNER JOIN: every fact row is guaranteed a valid customer.
INNER JOIN stg_customers c ON o.customer_id = c.customer_id;
"""

# Sanity check: join the fact to ALL three dimensions. If the keys line up,
# this returns rows; if a key were wrong, the joins would return nothing.
TEST_QUERY = """
SELECT
    d.year_month,
    p.category_en,
    c.customer_state,
    f.item_total
FROM fact_order_items f
JOIN dim_customers c ON f.customer_key   = c.customer_key
JOIN dim_products  p ON f.product_key    = p.product_key
JOIN dim_dates     d ON f.order_date_key = d.date_key
LIMIT 5;
"""


def count(con, table):
    return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found. Run src/01_ingest_clean.py first.")

    con = duckdb.connect(str(DB_PATH))
    try:
        # 1. Create the empty star-schema tables.
        con.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        print("Created star-schema tables from sql/schema.sql")

        # 2. Fill the dimensions first (the fact table's foreign keys need them).
        for table, sql in [
            ("dim_customers", LOAD_DIM_CUSTOMERS),
            ("dim_products", LOAD_DIM_PRODUCTS),
            ("dim_dates", LOAD_DIM_DATES),
        ]:
            con.execute(sql)
            n = count(con, table)
            if n == 0:
                raise ValueError(f"{table} has 0 rows after loading.")
            print(f"  {table:<20} {n:>8,} rows")

        # 3. Fill the fact table, reporting how many rows the INNER JOINs dropped.
        before = count(con, "stg_order_items")
        con.execute(LOAD_FACT)
        after = count(con, "fact_order_items")
        if after == 0:
            raise ValueError("fact_order_items has 0 rows after loading.")

        print(f"\nfact_order_items (grain: one row per item within an order)")
        print(f"  rows before join (stg_order_items): {before:>8,}")
        print(f"  rows after join  (fact_order_items): {after:>8,}")
        print(f"  dropped: {before - after:,} items whose order was not 'delivered'")

        # 4. Prove the star joins work end to end.
        result = con.execute(TEST_QUERY).df()
        if result.empty:
            raise ValueError("Test join of fact to all dimensions returned 0 rows.")
        print("\nTest query (fact joined to all 3 dimensions):")
        print(result.to_string(index=False))
    finally:
        con.close()


if __name__ == "__main__":
    main()
