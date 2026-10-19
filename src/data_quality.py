"""
data_quality.py
----------------
Controlli di qualità dati applicati nel passaggio Bronze -> Silver.

Ogni funzione restituisce un dict con:
  - "check": nome del controllo
  - "passed": bool
  - "details": informazioni utili per il report

L'obiettivo e' avere controlli ESPLICITI e TRACCIABILI, non una pulizia
"silenziosa": ogni riga scartata o corretta deve finire nel report di
data quality (vedi reports/data_quality_report.json dopo l'esecuzione
della pipeline).
"""

from __future__ import annotations
import pandas as pd


def check_nulls(df: pd.DataFrame, critical_columns: list[str]) -> dict:
    null_counts = df[critical_columns].isnull().sum().to_dict()
    total_nulls = sum(null_counts.values())
    return {
        "check": "null_values_in_critical_columns",
        "passed": total_nulls == 0,
        "details": {k: int(v) for k, v in null_counts.items() if v > 0},
    }


def check_duplicates(df: pd.DataFrame, subset: list[str]) -> dict:
    dup_count = int(df.duplicated(subset=subset).sum())
    return {
        "check": "exact_duplicate_rows",
        "passed": dup_count == 0,
        "details": {"duplicate_rows_found": dup_count},
    }


def check_price_range(df: pd.DataFrame, price_col: str, min_price: float = 0.01, max_price: float = 1000.0) -> dict:
    out_of_range = df[(df[price_col] < min_price) | (df[price_col] > max_price)]
    return {
        "check": "price_within_expected_range",
        "passed": out_of_range.empty,
        "details": {"rows_out_of_range": int(len(out_of_range))},
    }


def check_referential_category(df: pd.DataFrame, category_col: str, valid_categories: set[str]) -> dict:
    invalid = df[~df[category_col].isin(valid_categories)]
    return {
        "check": "category_in_allowed_values",
        "passed": invalid.empty,
        "details": {
            "invalid_values_found": sorted(invalid[category_col].unique().tolist())
        },
    }


def check_date_not_future(df: pd.DataFrame, date_col: str, as_of) -> dict:
    future_rows = df[df[date_col] > as_of]
    return {
        "check": "transaction_date_not_in_future",
        "passed": future_rows.empty,
        "details": {"future_rows_found": int(len(future_rows))},
    }


def run_all_checks(df: pd.DataFrame, as_of) -> list[dict]:
    """Esegue l'intero set di controlli e restituisce la lista dei risultati."""
    return [
        check_nulls(df, critical_columns=["transaction_id", "sku", "quantity", "unit_price", "transaction_date"]),
        check_duplicates(df, subset=["transaction_id"]),
        check_price_range(df, price_col="unit_price"),
        check_referential_category(df, category_col="category", valid_categories={"Scarpe", "Abbigliamento", "Accessori"}),
        check_date_not_future(df, date_col="transaction_date", as_of=as_of),
    ]
