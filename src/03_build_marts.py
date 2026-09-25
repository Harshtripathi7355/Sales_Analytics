"""
Stage 3 — Build the marts.

Runs sql/marts.sql, which creates three summary tables from the star schema:
    mart_sales_by_category, mart_monthly_sales, mart_customer_value
Then prints the first 5 rows of each so you can eyeball the results.
"""

from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "warehouse.duckdb"
MARTS_PATH = PROJECT_ROOT / "sql" / "marts.sql"

MARTS = ["mart_sales_by_category", "mart_monthly_sales", "mart_customer_value"]

# Show all columns side by side instead of wrapping them.
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found. Run stages 1 and 2 first.")

    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(MARTS_PATH.read_text(encoding="utf-8"))

        for mart in MARTS:
            n = con.execute(f"SELECT COUNT(*) FROM {mart}").fetchone()[0]
            if n == 0:
                raise ValueError(f"{mart} has 0 rows.")
            print(f"\n=== {mart} ({n:,} rows) — first 5 ===")
            print(con.execute(f"SELECT * FROM {mart} LIMIT 5").df().to_string(index=False))
    finally:
        con.close()


if __name__ == "__main__":
    main()
