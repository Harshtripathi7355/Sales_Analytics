"""
Stage 4 — Run the 6 business-question queries.

Reads sql/analysis_queries.sql, splits it into individual queries using the
"-- Qn: <question>" header lines, runs each against the warehouse and prints
the result as a pandas DataFrame.
"""

import re
from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "warehouse.duckdb"
QUERIES_PATH = PROJECT_ROOT / "sql" / "analysis_queries.sql"

MAX_ROWS_PRINTED = 30   # Q5 returns ~200 rows; show the first 30 to keep output readable

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)


def load_queries():
    """Return a list of (label, question, sql) from the .sql file."""
    text = QUERIES_PATH.read_text(encoding="utf-8")

    # Split on lines like "-- Q1: What are ...". Because the pattern has two
    # capture groups, re.split returns: [preamble, 'Q1', question, sql, 'Q2', ...]
    parts = re.split(r"^-- (Q\d+): (.+)$", text, flags=re.MULTILINE)

    queries = []
    for i in range(1, len(parts), 3):
        label, question, sql = parts[i], parts[i + 1].strip(), parts[i + 2].strip()
        queries.append((label, question, sql))

    if len(queries) != 6:
        raise ValueError(f"Expected 6 queries in {QUERIES_PATH.name}, found {len(queries)}.")
    return queries


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found. Run stages 1-3 first.")

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        for label, question, sql in load_queries():
            df = con.execute(sql).df()
            if df.empty:
                raise ValueError(f"{label} returned no rows: {question}")

            print("\n" + "-" * 70)
            print(f"{label}: {question}")
            print("-" * 70)
            print(df.head(MAX_ROWS_PRINTED).to_string(index=False))
            if len(df) > MAX_ROWS_PRINTED:
                print(f"... ({len(df):,} rows total, first {MAX_ROWS_PRINTED} shown)")
    finally:
        con.close()


if __name__ == "__main__":
    main()
