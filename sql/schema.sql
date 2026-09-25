-- =====================================================================
-- schema.sql — star schema table definitions
--
-- One fact table (fact_order_items) in the middle, three dimension
-- tables (customers, products, dates) around it.
-- 02_build_warehouse.py runs this file, then fills the tables.
-- =====================================================================

-- Drop the fact table FIRST: it holds foreign keys pointing at the
-- dimensions, so the dimensions can't be dropped while it exists.
DROP TABLE IF EXISTS fact_order_items;
DROP TABLE IF EXISTS dim_customers;
DROP TABLE IF EXISTS dim_products;
DROP TABLE IF EXISTS dim_dates;


-- One row per real PERSON.
-- customer_key = customer_unique_id, NOT customer_id: in Olist, customer_id
-- is generated fresh for every order, so one person who ordered 3 times has
-- 3 different customer_ids. Using customer_id would make every customer look
-- like a one-time buyer.
CREATE TABLE dim_customers (
    customer_key    VARCHAR PRIMARY KEY,
    customer_city   VARCHAR,
    customer_state  VARCHAR
);


-- One row per product.
CREATE TABLE dim_products (
    product_key  VARCHAR PRIMARY KEY,   -- = product_id
    category_pt  VARCHAR,               -- original Portuguese category name
    category_en  VARCHAR                -- English name ('unknown' if no translation)
);


-- One row per calendar date that has at least one order.
-- Pre-computing year/month/quarter here means analysis queries can just
-- GROUP BY year_month instead of repeating date functions everywhere.
CREATE TABLE dim_dates (
    date_key     DATE PRIMARY KEY,
    year         INTEGER,
    month        INTEGER,
    month_name   VARCHAR,
    quarter      INTEGER,
    year_month   VARCHAR,               -- e.g. '2017-05'
    day_of_week  VARCHAR
);


-- GRAIN: one row per item within an order (one "order line").
-- An order with 3 items produces 3 rows. (order_id, order_item_id) is the
-- natural key. Every measure below (price, freight...) is for that one line.
CREATE TABLE fact_order_items (
    order_id        VARCHAR,
    order_item_id   INTEGER,
    customer_key    VARCHAR REFERENCES dim_customers (customer_key),
    product_key     VARCHAR REFERENCES dim_products (product_key),
    order_date_key  DATE    REFERENCES dim_dates (date_key),
    price           DECIMAL(10, 2),
    freight_value   DECIMAL(10, 2),
    item_total      DECIMAL(10, 2),     -- price + freight_value
    delivery_days   INTEGER,            -- order-level value, repeated on each line
    delivered_late  INTEGER,            -- 0 or 1, order-level value
    PRIMARY KEY (order_id, order_item_id)
);
