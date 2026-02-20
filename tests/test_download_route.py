"""
Tests for api/routes/download.py — _iter_rows and download endpoint logic

Verifies the streaming row iterator and download column list.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.routes.download import _iter_rows, _DOWNLOAD_COLUMNS, _ALLOWED_SORT, _build_download_sql


@pytest.fixture()
def db():
    """In-memory database with budget_lines table for download testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Create a table with all columns the download route expects
    cols = ", ".join(f"{c} TEXT" for c in _DOWNLOAD_COLUMNS if c != "id")
    conn.execute(f"CREATE TABLE budget_lines (id INTEGER PRIMARY KEY, {cols})")

    # Insert test rows
    placeholders = ", ".join("?" * len(_DOWNLOAD_COLUMNS))
    for i in range(10):
        values = [i + 1] + [f"val_{c}_{i}" for c in _DOWNLOAD_COLUMNS[1:]]
        conn.execute(
            f"INSERT INTO budget_lines ({', '.join(_DOWNLOAD_COLUMNS)}) VALUES ({placeholders})",
            values,
        )
    conn.commit()
    yield conn
    conn.close()


class TestIterRows:
    def test_yields_all_rows(self, db):
        rows = list(_iter_rows(db, "SELECT * FROM budget_lines", []))
        assert len(rows) == 10

    def test_with_limit(self, db):
        rows = list(_iter_rows(db, "SELECT * FROM budget_lines LIMIT 3", []))
        assert len(rows) == 3

    def test_with_where_params(self, db):
        rows = list(_iter_rows(
            db, "SELECT * FROM budget_lines WHERE id = ?", [1]
        ))
        assert len(rows) == 1

    def test_empty_result(self, db):
        rows = list(_iter_rows(
            db, "SELECT * FROM budget_lines WHERE id = ?", [999]
        ))
        assert len(rows) == 0


class TestDownloadColumns:
    def test_has_essential_columns(self):
        assert "id" in _DOWNLOAD_COLUMNS
        assert "source_file" in _DOWNLOAD_COLUMNS
        assert "exhibit_type" in _DOWNLOAD_COLUMNS
        assert "organization_name" in _DOWNLOAD_COLUMNS
        assert "amount_fy2026_request" in _DOWNLOAD_COLUMNS

    def test_has_amount_columns(self):
        amount_cols = [c for c in _DOWNLOAD_COLUMNS if c.startswith("amount_")]
        assert len(amount_cols) >= 5


class TestBuildDownloadSql:
    def test_appropriation_code_filter(self, db):
        """appropriation_code filter restricts results."""
        # Set appropriation_code on one row
        db.execute("UPDATE budget_lines SET appropriation_code = '3010' WHERE id = 1")
        db.execute("UPDATE budget_lines SET appropriation_code = '1506' WHERE id = 2")
        db.commit()

        sql, params, total = _build_download_sql(
            fiscal_year=None, service=None, exhibit_type=None,
            pe_number=None, appropriation_code=["3010"], q=None,
            conn=db, limit=100, export_cols=_DOWNLOAD_COLUMNS,
        )
        assert total == 1
        rows = list(_iter_rows(db, sql, params))
        assert len(rows) == 1


    def test_min_max_amount_filter(self, db):
        """min_amount and max_amount restrict results."""
        # Set amounts on specific rows
        db.execute("UPDATE budget_lines SET amount_fy2026_request = 500 WHERE id = 1")
        db.execute("UPDATE budget_lines SET amount_fy2026_request = 1500 WHERE id = 2")
        db.execute("UPDATE budget_lines SET amount_fy2026_request = 3000 WHERE id = 3")
        db.commit()

        sql, params, total = _build_download_sql(
            fiscal_year=None, service=None, exhibit_type=None,
            pe_number=None, appropriation_code=None, q=None,
            conn=db, limit=100, export_cols=_DOWNLOAD_COLUMNS,
            min_amount=1000.0, max_amount=2000.0,
        )
        assert total == 1  # Only id=2 with amount=1500

    def test_sort_order_applied(self, db):
        """sort_by and sort_dir affect result ordering."""
        sql_asc, params_asc, _ = _build_download_sql(
            fiscal_year=None, service=None, exhibit_type=None,
            pe_number=None, appropriation_code=None, q=None,
            conn=db, limit=100, export_cols=_DOWNLOAD_COLUMNS,
            sort_by="id", sort_dir="desc",
        )
        rows = list(_iter_rows(db, sql_asc, params_asc))
        ids = [r[0] for r in rows]
        assert ids == sorted(ids, reverse=True)


class TestAllowedSort:
    def test_has_common_sorts(self):
        assert "id" in _ALLOWED_SORT
        assert "source_file" in _ALLOWED_SORT
        assert "amount_fy2026_request" in _ALLOWED_SORT
