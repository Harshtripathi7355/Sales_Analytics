"""
Stage 5 — Generate the 4 EDA charts into outputs/charts/.

Each chart pulls a small result from the warehouse (usually a mart) into
pandas, then plots it with seaborn/matplotlib.
"""

from pathlib import Path

import duckdb
import matplotlib

# "Agg" = draw straight to image files, no pop-up window. Needed so the
# script also works on machines/terminals with no display.
matplotlib.use("Agg")

import matplotlib.pyplot as plt   # noqa: E402  (must come after matplotlib.use)
import seaborn as sns             # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "warehouse.duckdb"
CHART_DIR = PROJECT_ROOT / "outputs" / "charts"

DPI = 120
BAR_COLOR = "#4C72B0"

sns.set_theme(style="whitegrid")


def save(fig, file_name):
    """Save a figure and fail loudly if the file didn't get written."""
    path = CHART_DIR / file_name
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    if not path.exists() or path.stat().st_size == 0:
        raise IOError(f"Chart was not written: {path}")
    print(f"  saved {path.relative_to(PROJECT_ROOT)}")


def chart_revenue_by_category(con):
    df = con.execute("""
        SELECT category_en, total_revenue
        FROM mart_sales_by_category
        ORDER BY total_revenue DESC
        LIMIT 10
    """).df()
    df["revenue_k"] = df["total_revenue"] / 1000   # thousands of R$, easier to read

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(data=df, x="revenue_k", y="category_en", color=BAR_COLOR, ax=ax)
    ax.set_title("Top 10 Product Categories by Revenue")
    ax.set_xlabel("Revenue (R$ thousands)")
    ax.set_ylabel("Product category")
    save(fig, "01_revenue_by_category.png")


def chart_monthly_trend(con):
    df = con.execute("""
        SELECT year_month, total_revenue
        FROM mart_monthly_sales
        ORDER BY year_month
    """).df()
    df["revenue_k"] = df["total_revenue"] / 1000

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(df["year_month"], df["revenue_k"], marker="o", color=BAR_COLOR)
    ax.set_title("Monthly Revenue (delivered orders)")
    ax.set_xlabel("Month (year-month)")
    ax.set_ylabel("Revenue (R$ thousands)")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    save(fig, "02_monthly_revenue_trend.png")


def chart_value_tiers(con):
    df = con.execute("""
        SELECT
            value_tier,
            COUNT(*)          AS customers,
            AVG(total_spent)  AS avg_spent
        FROM mart_customer_value
        GROUP BY value_tier
    """).df()
    order = ["Low", "Medium", "High"]

    # Two side-by-side panels: how many customers, and how much they spend.
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    sns.barplot(data=df, x="value_tier", y="customers", order=order, color=BAR_COLOR, ax=ax1)
    ax1.set_title("Customers per Value Tier")
    # "\$" = literal dollar sign; two bare "$" would make matplotlib render math.
    ax1.set_xlabel(r"Value tier (Low < R\$150 <= Medium < R\$500 <= High)")
    ax1.set_ylabel("Number of customers")

    sns.barplot(data=df, x="value_tier", y="avg_spent", order=order, color="#DD8452", ax=ax2)
    ax2.set_title("Average Lifetime Spend per Value Tier")
    ax2.set_xlabel("Value tier")
    ax2.set_ylabel("Average spend per customer (R$)")

    save(fig, "03_customer_value_tiers.png")


def chart_correlation(con):
    df = con.execute("""
        SELECT price, freight_value, item_total, delivery_days
        FROM fact_order_items
    """).df().astype(float)   # one numeric type for all; NULLs become NaN

    # Pearson correlation. Rows with a NULL delivery_days are skipped
    # pair-by-pair by pandas. Note: item_total = price + freight, so it
    # correlates almost perfectly with price by construction.
    corr = df.corr()

    fig, ax = plt.subplots(figsize=(7, 6))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", vmin=-1, vmax=1, ax=ax)
    ax.set_title("Correlation of Order-Line Measures (Pearson r)")
    ax.set_xlabel("Measure")
    ax.set_ylabel("Measure")
    save(fig, "04_correlation_heatmap.png")


def main():
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found. Run stages 1-3 first.")
    CHART_DIR.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        chart_revenue_by_category(con)
        chart_monthly_trend(con)
        chart_value_tiers(con)
        chart_correlation(con)
    finally:
        con.close()


if __name__ == "__main__":
    main()
