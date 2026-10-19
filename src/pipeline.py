"""
pipeline.py
------------
Pipeline ELT a tre livelli (architettura Medallion):

  BRONZE  ->  dati grezzi, as-is, cosi' come arrivano dalla fonte (POS).
  SILVER  ->  dati puliti, validati, deduplicati, con tipi corretti.
  GOLD    ->  modello dimensionale (fact + dimensioni) pronto per il
              reporting e il calcolo dei KPI di business.

Esecuzione:
    python src/pipeline.py

Il risultato e':
  - data/silver/pos_transactions_clean.parquet-like (CSV per semplicita')
  - data/gold/retail.db (SQLite) con tabelle dimensionali
  - reports/data_quality_report.json
  - reports/pipeline_run.log
"""

from __future__ import annotations
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from data_quality import run_all_checks

BASE_DIR = Path(__file__).resolve().parent.parent
BRONZE_PATH = BASE_DIR / "data" / "bronze" / "pos_transactions_raw.csv"
SILVER_PATH = BASE_DIR / "data" / "silver" / "pos_transactions_clean.csv"
GOLD_DB_PATH = BASE_DIR / "data" / "gold" / "retail.db"
REPORTS_DIR = BASE_DIR / "reports"

CATEGORY_MAP = {
    "scarpe": "Scarpe",
    "scarpe ": "Scarpe",
    "SCARPE": "Scarpe",
    "Scarpe": "Scarpe",
    "Abbigliamento": "Abbigliamento",
    "Accessori": "Accessori",
}

PAYMENT_MAP = {
    "carta": "Carta",
    "Carta": "Carta",
    "bancomat": "Carta",
    "contanti": "Contanti",
    "CONTANTI": "Contanti",
    "": "Sconosciuto",
}


def setup_logging() -> logging.Logger:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = REPORTS_DIR / "pipeline_run.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.FileHandler(log_path, mode="w"), logging.StreamHandler()],
    )
    return logging.getLogger("elt_pipeline")


def parse_messy_date(value: str) -> pd.Timestamp:
    """Normalizza le tre varianti di data iniettate nei dati grezzi
    (ISO, europeo, timestamp unix) in un unico formato datetime."""
    value = str(value).strip()
    if value.isdigit() and len(value) == 10:
        return pd.to_datetime(int(value), unit="s")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return pd.to_datetime(value, format=fmt)
        except ValueError:
            continue
    return pd.NaT


def parse_messy_price(value) -> float:
    """Normalizza i formati di prezzo sporchi ("49,99€", "49.99", "")
    in un float, o NaN se mancante/non interpretabile."""
    if value is None:
        return float("nan")
    s = str(value).strip().replace("€", "").replace(",", ".")
    if s == "" or s.lower() == "nan":
        return float("nan")
    try:
        return float(s)
    except ValueError:
        return float("nan")


# --------------------------------------------------------------------------- #
# BRONZE -> SILVER
# --------------------------------------------------------------------------- #

def bronze_to_silver(logger: logging.Logger) -> pd.DataFrame:
    logger.info("Lettura livello BRONZE da %s", BRONZE_PATH)
    df = pd.read_csv(BRONZE_PATH, dtype=str)
    rows_in = len(df)
    logger.info("Righe grezze lette: %d", rows_in)

    # Normalizzazione tipi e formati
    df["unit_price"] = df["unit_price"].apply(parse_messy_price)
    df["transaction_date"] = df["transaction_date"].apply(parse_messy_date)
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["category"] = df["category"].map(CATEGORY_MAP).fillna(df["category"])
    df["payment_method"] = df["payment_method"].fillna("").map(PAYMENT_MAP).fillna("Sconosciuto")
    df["customer_email"] = df["customer_email"].astype(str).str.strip().str.lower().replace({"none": None, "nan": None, "": None})

    # Rimozione duplicati esatti su transaction_id
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["transaction_id"])
    logger.info("Duplicati rimossi: %d", before_dedup - len(df))

    # Scarto righe con dati critici mancanti o non validi
    before_na = len(df)
    df = df.dropna(subset=["transaction_id", "sku", "quantity", "unit_price", "transaction_date"])
    logger.info("Righe scartate per dati critici mancanti: %d", before_na - len(df))

    # Esecuzione controlli di data quality sul dataset ripulito
    checks = run_all_checks(df, as_of=pd.Timestamp.now())
    report = {
        "run_timestamp": datetime.now().isoformat(),
        "rows_in_bronze": rows_in,
        "rows_in_silver": len(df),
        "rows_dropped": rows_in - len(df),
        "checks": checks,
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(REPORTS_DIR / "data_quality_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)

    failed_checks = [c["check"] for c in checks if not c["passed"]]
    if failed_checks:
        logger.warning("Controlli di data quality falliti: %s", failed_checks)
    else:
        logger.info("Tutti i controlli di data quality superati.")

    SILVER_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SILVER_PATH, index=False)
    logger.info("Livello SILVER scritto in %s (%d righe)", SILVER_PATH, len(df))
    return df


# --------------------------------------------------------------------------- #
# SILVER -> GOLD (modello dimensionale)
# --------------------------------------------------------------------------- #

def silver_to_gold(df: pd.DataFrame, logger: logging.Logger) -> None:
    GOLD_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(GOLD_DB_PATH)

    # dim_product
    dim_product = (
        df[["sku", "product_name", "category"]]
        .drop_duplicates(subset=["sku"])
        .reset_index(drop=True)
    )
    dim_product.insert(0, "product_key", range(1, len(dim_product) + 1))

    # dim_store
    dim_store = pd.DataFrame({"store_name": sorted(df["store"].unique())})
    dim_store.insert(0, "store_key", range(1, len(dim_store) + 1))

    # dim_date
    dates = pd.DataFrame({"full_date": pd.to_datetime(df["transaction_date"].dt.date.unique())})
    dates = dates.sort_values("full_date").reset_index(drop=True)
    dates.insert(0, "date_key", range(1, len(dates) + 1))
    dates["year"] = dates["full_date"].dt.year
    dates["month"] = dates["full_date"].dt.month
    dates["day_of_week"] = dates["full_date"].dt.day_name()
    dates["is_weekend"] = dates["full_date"].dt.dayofweek >= 5

    # fact_sales
    fact = df.merge(dim_product, on=["sku", "product_name", "category"], how="left")
    fact = fact.merge(dim_store, left_on="store", right_on="store_name", how="left")
    fact["sale_date"] = fact["transaction_date"].dt.date.astype("datetime64[ns]")
    fact = fact.merge(dates, left_on="sale_date", right_on="full_date", how="left")
    fact["net_revenue"] = fact["quantity"] * fact["unit_price"]

    fact_sales = fact[[
        "transaction_id", "product_key", "store_key", "date_key",
        "quantity", "unit_price", "net_revenue", "payment_method", "customer_email",
    ]].rename(columns={"transaction_id": "sale_id"})

    dim_product.to_sql("dim_product", conn, if_exists="replace", index=False)
    dim_store.to_sql("dim_store", conn, if_exists="replace", index=False)
    dates.drop(columns=["full_date"]).assign(date_key=dates["date_key"]).to_sql(
        "dim_date", conn, if_exists="replace", index=False
    )
    fact_sales.to_sql("fact_sales", conn, if_exists="replace", index=False)

    conn.commit()
    conn.close()
    logger.info(
        "Livello GOLD scritto in %s: dim_product(%d), dim_store(%d), dim_date(%d), fact_sales(%d)",
        GOLD_DB_PATH, len(dim_product), len(dim_store), len(dates), len(fact_sales),
    )


def main() -> None:
    logger = setup_logging()
    logger.info("=== Avvio pipeline ELT (Bronze -> Silver -> Gold) ===")
    silver_df = bronze_to_silver(logger)
    silver_to_gold(silver_df, logger)
    logger.info("=== Pipeline completata con successo ===")


if __name__ == "__main__":
    main()
