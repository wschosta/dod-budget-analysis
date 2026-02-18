"""
Tests for api/routes/download.py — _iter_rows and download endpoint logic

Verifies the streaming row iterator and download column list.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.routes.download import _iter_rows, _DOWNLOAD_COLUMNS, _ALLOWED_SORT


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


class TestAllowedSort:
    def test_has_common_sorts(self):
        assert "id" in _ALLOWED_SORT
        assert "source_file" in _ALLOWED_SORT
        assert "amount_fy2026_request" in _ALLOWED_SORT
