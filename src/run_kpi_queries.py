"""
run_kpi_queries.py
--------------------
Esegue query SQL di business sul modello dimensionale GOLD e produce:
  - reports/kpi_summary.json
  - reports/daily_revenue.png (grafico)

Le query sono scritte in SQL puro (SQLite) sul modello a stella
fact_sales / dim_product / dim_store / dim_date, per dimostrare
l'interrogazione di un data model dimensionale, non solo pandas.
"""

from __future__ import annotations
import json
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
GOLD_DB_PATH = BASE_DIR / "data" / "gold" / "retail.db"
REPORTS_DIR = BASE_DIR / "reports"

QUERIES = {
    "total_net_revenue": """
        SELECT ROUND(SUM(net_revenue), 2) AS total_net_revenue
        FROM fact_sales;
    """,
    "revenue_by_store": """
        SELECT s.store_name, ROUND(SUM(f.net_revenue), 2) AS net_revenue
        FROM fact_sales f
        JOIN dim_store s ON f.store_key = s.store_key
        GROUP BY s.store_name
        ORDER BY net_revenue DESC;
    """,
    "top_5_products_by_revenue": """
        SELECT p.product_name, p.category, ROUND(SUM(f.net_revenue), 2) AS net_revenue,
               SUM(f.quantity) AS units_sold
        FROM fact_sales f
        JOIN dim_product p ON f.product_key = p.product_key
        GROUP BY p.product_name, p.category
        ORDER BY net_revenue DESC
        LIMIT 5;
    """,
    "revenue_by_category": """
        SELECT p.category, ROUND(SUM(f.net_revenue), 2) AS net_revenue
        FROM fact_sales f
        JOIN dim_product p ON f.product_key = p.product_key
        GROUP BY p.category
        ORDER BY net_revenue DESC;
    """,
    "weekend_vs_weekday_avg_daily_revenue": """
        SELECT d.is_weekend,
               ROUND(SUM(f.net_revenue) * 1.0 / COUNT(DISTINCT d.date_key), 2) AS avg_daily_revenue
        FROM fact_sales f
        JOIN dim_date d ON f.date_key = d.date_key
        GROUP BY d.is_weekend;
    """,
    "return_rate": """
        SELECT
            ROUND(100.0 * SUM(CASE WHEN quantity < 0 THEN 1 ELSE 0 END) / COUNT(*), 2) AS return_rate_pct
        FROM fact_sales;
    """,
}

DAILY_REVENUE_QUERY = """
    SELECT d.full_date_str AS sale_date, ROUND(SUM(f.net_revenue), 2) AS net_revenue
    FROM fact_sales f
    JOIN (
        SELECT date_key, year || '-' || printf('%02d', month) || '-' || printf('%02d', 1) AS full_date_str,
               date_key AS dk
        FROM dim_date
    ) d ON f.date_key = d.dk
    GROUP BY d.full_date_str
    ORDER BY d.full_date_str;
"""


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(GOLD_DB_PATH)

    results = {}
    for name, query in QUERIES.items():
        df = pd.read_sql_query(query, conn)
        results[name] = df.to_dict(orient="records")
        print(f"\n--- {name} ---")
        print(df.to_string(index=False))

    with open(REPORTS_DIR / "kpi_summary.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Grafico: fatturato giornaliero reale (usa dim_date correttamente)
    daily_query = """
        SELECT d.full_date, ROUND(SUM(f.net_revenue), 2) AS net_revenue
        FROM fact_sales f
        JOIN dim_date_full d ON f.date_key = d.date_key
        GROUP BY d.full_date
        ORDER BY d.full_date;
    """
    # dim_date non espone full_date (rimosso prima del salvataggio): lo ricostruiamo
    # qui per il solo scopo del grafico, leggendo year/month/day_of_week non basta
    # per il giorno esatto, quindi aggreghiamo a livello mensile invece.
    monthly_query = """
        SELECT d.year || '-' || printf('%02d', d.month) AS year_month,
               ROUND(SUM(f.net_revenue), 2) AS net_revenue
        FROM fact_sales f
        JOIN dim_date d ON f.date_key = d.date_key
        GROUP BY year_month
        ORDER BY year_month;
    """
    monthly_df = pd.read_sql_query(monthly_query, conn)

    plt.figure(figsize=(9, 5))
    plt.bar(monthly_df["year_month"], monthly_df["net_revenue"], color="#2a6f97")
    plt.title("Fatturato netto mensile — tutti i punti vendita")
    plt.xlabel("Mese")
    plt.ylabel("Fatturato netto (€)")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(REPORTS_DIR / "monthly_revenue.png", dpi=150)
    print(f"\nGrafico salvato in {REPORTS_DIR / 'monthly_revenue.png'}")

    conn.close()


if __name__ == "__main__":
    main()
