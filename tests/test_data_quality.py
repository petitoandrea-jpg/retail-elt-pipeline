"""
test_data_quality.py
----------------------
Test automatici sui controlli di data quality (src/data_quality.py).

Esecuzione: pytest tests/
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from data_quality import (
    check_nulls,
    check_duplicates,
    check_price_range,
    check_referential_category,
    check_date_not_future,
)


def test_check_nulls_passes_on_clean_data():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    result = check_nulls(df, critical_columns=["a", "b"])
    assert result["passed"] is True


def test_check_nulls_fails_on_missing_values():
    df = pd.DataFrame({"a": [1, None, 3], "b": [4, 5, 6]})
    result = check_nulls(df, critical_columns=["a", "b"])
    assert result["passed"] is False
    assert result["details"]["a"] == 1


def test_check_duplicates_detects_exact_duplicates():
    df = pd.DataFrame({"id": [1, 1, 2], "val": ["x", "x", "y"]})
    result = check_duplicates(df, subset=["id"])
    assert result["passed"] is False
    assert result["details"]["duplicate_rows_found"] == 1


def test_check_price_range_flags_out_of_range_values():
    df = pd.DataFrame({"unit_price": [10.0, -5.0, 2000.0, 49.99]})
    result = check_price_range(df, price_col="unit_price")
    assert result["passed"] is False
    assert result["details"]["rows_out_of_range"] == 2


def test_check_referential_category_flags_invalid_values():
    df = pd.DataFrame({"category": ["Scarpe", "scarpe", "Abbigliamento"]})
    result = check_referential_category(df, category_col="category", valid_categories={"Scarpe", "Abbigliamento"})
    assert result["passed"] is False
    assert "scarpe" in result["details"]["invalid_values_found"]


def test_check_date_not_future_flags_future_dates():
    as_of = pd.Timestamp("2026-06-01")
    df = pd.DataFrame({"d": pd.to_datetime(["2026-05-01", "2026-12-25"])})
    result = check_date_not_future(df, date_col="d", as_of=as_of)
    assert result["passed"] is False
    assert result["details"]["future_rows_found"] == 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
