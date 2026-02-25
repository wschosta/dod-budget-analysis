"""
Tests for dynamic fiscal year column support.

Verifies that:
- validate_amount_column accepts any amount_fy{YYYY}_{type} pattern
- validate_amount_column rejects malformed column names (SQL injection guard)
- amount_col_to_label produces human-readable labels
- make_fiscal_year_column_labels builds sorted label list from column names
- build_where_clause works with dynamic amount columns
- _AMOUNT_COL_RE matches the expected patterns
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from utils.query import (
    _AMOUNT_COL_RE,
    amount_col_to_label,
    build_where_clause,
    make_fiscal_year_column_labels,
    validate_amount_column,
    DEFAULT_AMOUNT_COLUMN,
)


# ═══════════════════════════════════════════════════════════════════════════════
# _AMOUNT_COL_RE — pattern matching
# ═══════════════════════════════════════════════════════════════════════════════


class TestAmountColRegex:
    """Ensure the column name regex accepts valid names and rejects bad ones."""

    @pytest.mark.parametrize("col", [
        "amount_fy2024_actual",
        "amount_fy2025_enacted",
        "amount_fy2026_request",
        "amount_fy2026_total",
        "amount_fy2025_supplemental",
        "amount_fy2026_reconciliation",
        "amount_fy1998_actual",
        "amount_fy2010_request",
    ])
    def test_valid_columns_accepted(self, col):
        assert _AMOUNT_COL_RE.match(col), f"{col} should match"

    @pytest.mark.parametrize("col", [
        "bobby_tables",
        "amount_fy2024",          # missing type suffix
        "amount_fy20242_request",  # 5-digit year
        "amount_fynot_valid",
        "amount_fy2024_",          # trailing underscore only
        "AMOUNT_FY2024_ACTUAL",    # uppercase
        "amount_fy2024_actual; DROP TABLE budget_lines",  # SQL injection
        "",
    ])
    def test_invalid_columns_rejected(self, col):
        assert not _AMOUNT_COL_RE.match(col), f"{col} should NOT match"


# ═══════════════════════════════════════════════════════════════════════════════
# validate_amount_column
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidateAmountColumn:
    """Pattern-based validation for dynamic FY amount columns."""

    def test_none_returns_default(self):
        assert validate_amount_column(None) == DEFAULT_AMOUNT_COLUMN

    def test_valid_column_returned(self):
        assert validate_amount_column("amount_fy2024_actual") == "amount_fy2024_actual"

    def test_historical_year_accepted(self):
        assert validate_amount_column("amount_fy2010_request") == "amount_fy2010_request"

    def test_future_year_accepted(self):
        assert validate_amount_column("amount_fy2030_enacted") == "amount_fy2030_enacted"

    def test_invalid_raises_valueerror(self):
        with pytest.raises(ValueError, match="Invalid amount column"):
            validate_amount_column("bobby_tables")

    def test_sql_injection_rejected(self):
        with pytest.raises(ValueError):
            validate_amount_column("amount_fy2024_actual; DROP TABLE x")

    def test_empty_string_rejected(self):
        with pytest.raises(ValueError):
            validate_amount_column("")


# ═══════════════════════════════════════════════════════════════════════════════
# amount_col_to_label
# ═══════════════════════════════════════════════════════════════════════════════


class TestAmountColToLabel:
    """Human-readable label generation from column names."""

    @pytest.mark.parametrize("col,expected", [
        ("amount_fy2024_actual", "FY2024 Actual"),
        ("amount_fy2025_enacted", "FY2025 Enacted"),
        ("amount_fy2026_request", "FY2026 Request"),
        ("amount_fy2025_total", "FY2025 Total"),
        ("amount_fy2025_supplemental", "FY2025 Supplemental"),
        ("amount_fy2026_reconciliation", "FY2026 Reconciliation"),
    ])
    def test_known_suffixes(self, col, expected):
        assert amount_col_to_label(col) == expected

    def test_unknown_suffix_passthrough(self):
        # Unknown suffixes should still be partially formatted
        label = amount_col_to_label("amount_fy2024_custom")
        assert label.startswith("FY2024")


# ═══════════════════════════════════════════════════════════════════════════════
# make_fiscal_year_column_labels
# ═══════════════════════════════════════════════════════════════════════════════


class TestMakeFiscalYearColumnLabels:
    """Build sorted column-label dicts from discovered column lists."""

    def test_empty_list(self):
        assert make_fiscal_year_column_labels([]) == []

    def test_single_column(self):
        result = make_fiscal_year_column_labels(["amount_fy2026_request"])
        assert len(result) == 1
        assert result[0] == {"column": "amount_fy2026_request", "label": "FY2026 Request"}

    def test_sorted_output(self):
        cols = ["amount_fy2026_request", "amount_fy2024_actual", "amount_fy2025_enacted"]
        result = make_fiscal_year_column_labels(cols)
        assert [r["column"] for r in result] == [
            "amount_fy2024_actual",
            "amount_fy2025_enacted",
            "amount_fy2026_request",
        ]

    def test_all_known_columns(self):
        cols = [
            "amount_fy2024_actual", "amount_fy2025_enacted", "amount_fy2025_total",
            "amount_fy2026_request", "amount_fy2026_total",
        ]
        result = make_fiscal_year_column_labels(cols)
        assert len(result) == 5
        assert all("column" in r and "label" in r for r in result)


# ═══════════════════════════════════════════════════════════════════════════════
# build_where_clause with dynamic amount columns
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildWhereClauseDynamicAmount:
    """Ensure amount filters work with any valid FY column."""

    def test_min_amount_with_default_column(self):
        where, params = build_where_clause(min_amount=1000.0)
        assert f"{DEFAULT_AMOUNT_COLUMN} >= ?" in where
        assert 1000.0 in params

    def test_min_amount_with_custom_column(self):
        where, params = build_where_clause(
            min_amount=500.0, amount_column="amount_fy2010_request"
        )
        assert "amount_fy2010_request >= ?" in where
        assert 500.0 in params

    def test_max_amount_with_custom_column(self):
        where, params = build_where_clause(
            max_amount=10000.0, amount_column="amount_fy2024_actual"
        )
        assert "amount_fy2024_actual <= ?" in where
        assert 10000.0 in params

    def test_range_with_custom_column(self):
        where, params = build_where_clause(
            min_amount=100.0, max_amount=5000.0,
            amount_column="amount_fy2025_enacted"
        )
        assert "amount_fy2025_enacted >= ?" in where
        assert "amount_fy2025_enacted <= ?" in where
        assert 100.0 in params
        assert 5000.0 in params

    def test_invalid_column_raises(self):
        with pytest.raises(ValueError):
            build_where_clause(min_amount=100.0, amount_column="evil_column")
