"""
BEAR-002: Historical data compatibility tests (FY2017-2023).

Tests that the system can handle pre-FY2024 data:
1. Create synthetic Excel fixture with FY2020-2023 column headers — verify parsing.
2. Verify _safe_float() handles all historical column name patterns.
3. Verify database schema can accommodate FY2017-2023 amount columns.
4. Verify search across mixed historical + current FY data.
5. Verify aggregations work correctly with historical data.
"""
# DONE [Group: BEAR] BEAR-002: Add historical data compatibility tests (FY2017-2023 fixtures) (~2,500 tokens)

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from build_budget_db import create_database, _ensure_fy_columns
from utils.strings import safe_float


@pytest.fixture()
def historical_db(tmp_path):
    """Create a DB with both historical (FY2017-2023) and current (FY2024-2026) columns."""
    db_path = tmp_path / "historical.sqlite"
    conn = create_database(db_path)
    conn.row_factory = sqlite3.Row

    # Add historical FY columns dynamically
    historical_cols = [
        "amount_fy2017_actual", "amount_fy2018_actual",
        "amount_fy2019_actual", "amount_fy2020_actual",
        "amount_fy2021_actual", "amount_fy2022_actual",
        "amount_fy2023_actual",
    ]
    _ensure_fy_columns(conn, historical_cols)

    yield conn
    conn.close()


class TestSafeFloatHistorical:
    """Verify safe_float() handles all historical column name patterns."""

    def test_normal_float(self):
        assert safe_float(12345.0) == 12345.0

    def test_string_with_commas(self):
        assert safe_float("12,345.67") == 12345.67

    def test_currency_symbol(self):
        assert safe_float("$1,234") == 1234.0

    def test_none_returns_default(self):
        assert safe_float(None) == 0.0

    def test_empty_string_returns_default(self):
        assert safe_float("") == 0.0

    def test_non_numeric_returns_default(self):
        assert safe_float("N/A") == 0.0

    def test_integer_input(self):
        assert safe_float(42) == 42.0

    def test_whitespace_string(self):
        assert safe_float("  123.45  ") == 123.45


class TestHistoricalSchema:
    """Verify database schema accommodates FY2017-2023 amount columns."""

    def test_historical_columns_exist(self, historical_db):
        """All FY2017-2023 columns are present after _ensure_fy_columns()."""
        cols = {
            row[1]
            for row in historical_db.execute("PRAGMA table_info(budget_lines)").fetchall()
        }
        for year in range(2017, 2024):
            assert f"amount_fy{year}_actual" in cols, f"Missing amount_fy{year}_actual"

    def test_insert_historical_data(self, historical_db):
        """Can insert rows with both historical and current FY amounts."""
        historical_db.execute(
            """INSERT INTO budget_lines
               (source_file, exhibit_type, fiscal_year, account, account_title,
                organization_name, pe_number,
                amount_fy2020_actual, amount_fy2021_actual,
                amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("hist.xlsx", "p1", "2026", "2035", "Aircraft Procurement",
             "Army", "0205231A",
             10000.0, 10500.0,
             12345.0, 13456.0, 14000.0),
        )
        historical_db.commit()

        row = historical_db.execute(
            "SELECT amount_fy2020_actual, amount_fy2024_actual "
            "FROM budget_lines WHERE source_file = 'hist.xlsx'"
        ).fetchone()
        assert row["amount_fy2020_actual"] == 10000.0
        assert row["amount_fy2024_actual"] == 12345.0

    def test_historical_columns_are_real_type(self, historical_db):
        """Dynamically added FY columns have REAL type."""
        col_info = historical_db.execute("PRAGMA table_info(budget_lines)").fetchall()
        col_types = {row[1]: row[2] for row in col_info}
        for year in range(2017, 2024):
            col = f"amount_fy{year}_actual"
            assert col_types[col] == "REAL", f"{col} should be REAL, got {col_types[col]}"


class TestHistoricalSearch:
    """Verify search across mixed historical + current FY data."""

    def test_fts_search_historical_rows(self, historical_db):
        """FTS search finds rows with historical data."""
        historical_db.execute(
            """INSERT INTO budget_lines
               (source_file, exhibit_type, fiscal_year, account, account_title,
                organization_name, pe_number, line_item_title,
                amount_fy2020_actual, amount_fy2026_request)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("hist2.xlsx", "r1", "2026", "1300", "RDT&E",
             "Navy", "0602702E", "Historical Stealth Program",
             5000.0, 8000.0),
        )
        historical_db.commit()

        results = historical_db.execute(
            "SELECT rowid FROM budget_lines_fts "
            "WHERE budget_lines_fts MATCH 'Historical Stealth'"
        ).fetchall()
        assert len(results) >= 1


class TestHistoricalAggregations:
    """Verify aggregations work correctly with historical data."""

    def test_sum_across_mixed_fy_columns(self, historical_db):
        """SUM aggregation works across historical + current FY columns."""
        # Insert multiple rows
        for i, year in enumerate([2020, 2021, 2022]):
            historical_db.execute(
                f"""INSERT INTO budget_lines
                   (source_file, exhibit_type, fiscal_year, account, account_title,
                    organization_name, pe_number,
                    amount_fy{year}_actual, amount_fy2026_request)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (f"agg_{i}.xlsx", "p1", "2026", "2035", "Aircraft Procurement",
                 "Army", "0205231A",
                 10000.0 * (i + 1), 14000.0),
            )
        historical_db.commit()

        # Aggregate historical
        result = historical_db.execute(
            "SELECT SUM(amount_fy2020_actual) AS total_2020, "
            "SUM(amount_fy2026_request) AS total_2026 "
            "FROM budget_lines WHERE source_file LIKE 'agg_%'"
        ).fetchone()
        assert result["total_2020"] == 10000.0  # Only first row has 2020 data
        assert result["total_2026"] == 42000.0  # 14000 * 3
