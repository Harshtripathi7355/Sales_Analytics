"""
Stage 1 — Ingest & clean.

Reads the 5 raw Olist CSVs, prints a data-quality report for each,
cleans them with pandas/numpy, adds a few engineered columns, and loads
the results into DuckDB as staging tables (stg_*).

Staging = "raw data, cleaned up, but not yet reshaped". Stage 2 turns
these staging tables into the star schema.
"""

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# Build paths from this file's location so the script works no matter
# which folder you run it from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
DB_PATH = PROJECT_ROOT / "data" / "warehouse.duckdb"

# file name -> primary key column(s). The PK is what we check for duplicates on.
RAW_FILES = {
    "orders": ("olist_orders_dataset.csv", ["order_id"]),
    # An order can have several items, so an item is identified by
    # order_id + order_item_id together (a composite key).
    "order_items": ("olist_order_items_dataset.csv", ["order_id", "order_item_id"]),
    # NOTE: customer_id is one per ORDER, not one per person. We keep it as the
    # PK here because that is what's unique in this file; the person-level key
    # (customer_unique_id) is used in the star schema in Stage 2.
    "customers": ("olist_customers_dataset.csv", ["customer_id"]),
    "products": ("olist_products_dataset.csv", ["product_id"]),
    "category_translation": ("product_category_name_translation.csv", ["product_category_name"]),
}

ORDER_DATE_COLS = [
    "order_purchase_timestamp",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]


def load_csv(name):
    """Read one raw CSV. Fail loudly if the file isn't there."""
    file_name, _ = RAW_FILES[name]
    path = RAW_DIR / file_name
    if not path.exists():
        raise FileNotFoundError(
            f"Missing raw file: {path}\n"
            "Download the Olist dataset from "
            "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce "
            "and unzip it into data/raw/"
        )

    # Only the orders file has dates we need to parse.
    parse_dates = ORDER_DATE_COLS if name == "orders" else None
    df = pd.read_csv(path, parse_dates=parse_dates)

    if len(df) == 0:
        raise ValueError(f"{file_name} was read but has 0 rows.")
    return df


def quality_report(name, df):
    """Print row count, nulls per column, and duplicate count on the PK."""
    _, pk = RAW_FILES[name]
    print(f"\n--- QA report: {name} ---")
    print(f"Rows: {len(df):,}")

    nulls = df.isnull().sum()
    nulls = nulls[nulls > 0]
    if nulls.empty:
        print("Nulls: none")
    else:
        print("Nulls per column:")
        for col, n in nulls.items():
            print(f"  {col:<35} {n:>8,}")

    dupes = df.duplicated(subset=pk).sum()
    print(f"Duplicates on PK {pk}: {dupes:,}")


def clean(dfs):
    """Apply the cleaning rules and engineered fields. Returns a new dict."""
    # Rule 1: drop duplicate rows on each table's primary key (keep the first).
    for name, df in dfs.items():
        _, pk = RAW_FILES[name]
        dfs[name] = df.drop_duplicates(subset=pk, keep="first")

    # --- orders ---
    orders = dfs["orders"]
    before = len(orders)
    # Keep only delivered orders: cancelled / unavailable orders never became
    # real revenue, so including them would overstate sales.
    orders = orders[orders["order_status"] == "delivered"]
    print(f"\norders: removed {before - len(orders):,} non-delivered rows "
          f"({before:,} -> {len(orders):,})")

    before = len(orders)
    orders = orders.dropna(subset=["order_purchase_timestamp"])
    print(f"orders: removed {before - len(orders):,} rows with null purchase timestamp")

    # Engineered field: how many whole days from purchase to delivery.
    orders = orders.copy()
    orders["delivery_days"] = (
        orders["order_delivered_customer_date"] - orders["order_purchase_timestamp"]
    ).dt.days

    # Engineered field: 1 if delivered after the promised date, else 0.
    # np.where is a vectorised if/else over the whole column at once.
    # (If the delivered date is missing, the comparison is False -> 0.)
    orders["delivered_late"] = np.where(
        orders["order_delivered_customer_date"] > orders["order_estimated_delivery_date"], 1, 0
    )
    dfs["orders"] = orders

    # --- order_items ---
    items = dfs["order_items"].copy()
    # What the customer actually paid for this line: item price + shipping.
    items["item_total"] = items["price"] + items["freight_value"]
    dfs["order_items"] = items

    # --- products ---
    products = dfs["products"].copy()
    missing = products["product_category_name"].isnull().sum()
    products["product_category_name"] = products["product_category_name"].fillna("unknown")
    print(f"products: filled {missing:,} null categories with 'unknown'")
    dfs["products"] = products

    return dfs


def load_to_duckdb(dfs):
    """Write each cleaned DataFrame to DuckDB as stg_<name>."""
    con = duckdb.connect(str(DB_PATH))
    try:
        for name, df in dfs.items():
            table = f"stg_{name}"
            # DuckDB can query a pandas DataFrame directly. register() gives it
            # a fixed name so the SQL below can refer to it.
            con.register("tmp_df", df)
            con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM tmp_df")
            con.unregister("tmp_df")

            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if count == 0:
                raise ValueError(f"{table} was created but has 0 rows.")
            print(f"  {table:<28} {count:>8,} rows")
    finally:
        con.close()


def main():
    dfs = {name: load_csv(name) for name in RAW_FILES}

    for name, df in dfs.items():
        quality_report(name, df)

    print("\n=== Cleaning ===")
    dfs = clean(dfs)

    print(f"\n=== Loading staging tables into {DB_PATH.name} ===")
    load_to_duckdb(dfs)


if __name__ == "__main__":
    main()
