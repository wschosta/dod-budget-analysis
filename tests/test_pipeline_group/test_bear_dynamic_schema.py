"""
BEAR-001: Dynamic FY schema tests — ALTER TABLE, idempotency, FTS triggers.

Tests that the schema auto-ALTER TABLE works for new fiscal years:
1. Create a test DB with FY2024-2026 columns, call _ensure_fy_columns() with
   FY2027 data — verify column is added.
2. Verify existing data is preserved after ALTER TABLE.
3. Verify INSERT with new FY column values works.
4. Verify _ensure_fy_columns() is idempotent (calling twice doesn't error).
5. Verify FTS5 triggers still work after ALTER TABLE.
"""
# DONE [Group: BEAR] BEAR-001: Add dynamic FY schema tests — ALTER TABLE, idempotency, FTS triggers (~2,500 tokens)

import sqlite3

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from build_budget_db import create_database, _ensure_fy_columns


@pytest.fixture()
def schema_db(tmp_path):
    """Create a test DB with the baseline FY2024-2026 schema and sample data."""
    db_path = tmp_path / "dynamic_schema.sqlite"
    conn = create_database(db_path)
    conn.row_factory = sqlite3.Row
    # Insert a baseline row so we can verify data preservation
    conn.execute(
        """INSERT INTO budget_lines
           (source_file, exhibit_type, fiscal_year, account, account_title,
            organization_name, pe_number, amount_fy2024_actual,
            amount_fy2025_enacted, amount_fy2026_request)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("test.xlsx", "p1", "2026", "2035", "Aircraft Procurement",
         "Army", "0205231A", 12345.0, 13456.0, 14000.0),
    )
    conn.commit()
    yield conn
    conn.close()


def _get_column_names(conn):
    """Return the set of column names for budget_lines."""
    return {
        row[1]
        for row in conn.execute("PRAGMA table_info(budget_lines)").fetchall()
    }


class TestDynamicFYSchema:
    """Tests for BUILD-002: _ensure_fy_columns() dynamic column addition."""

    def test_new_fy_column_added(self, schema_db):
        """Calling _ensure_fy_columns() with FY2027 data adds the column."""
        cols_before = _get_column_names(schema_db)
        assert "amount_fy2027_request" not in cols_before

        _ensure_fy_columns(schema_db, ["amount_fy2027_request"])

        cols_after = _get_column_names(schema_db)
        assert "amount_fy2027_request" in cols_after

    def test_existing_data_preserved_after_alter(self, schema_db):
        """Existing row data is unchanged after ALTER TABLE adds a column."""
        row_before = schema_db.execute(
            "SELECT amount_fy2024_actual, amount_fy2025_enacted, "
            "amount_fy2026_request FROM budget_lines WHERE id = 1"
        ).fetchone()
        assert row_before["amount_fy2024_actual"] == 12345.0

        _ensure_fy_columns(schema_db, ["amount_fy2027_request", "quantity_fy2027_total"])

        row_after = schema_db.execute(
            "SELECT amount_fy2024_actual, amount_fy2025_enacted, "
            "amount_fy2026_request, amount_fy2027_request "
            "FROM budget_lines WHERE id = 1"
        ).fetchone()
        assert row_after["amount_fy2024_actual"] == 12345.0
        assert row_after["amount_fy2025_enacted"] == 13456.0
        assert row_after["amount_fy2026_request"] == 14000.0
        # New column should be NULL for existing rows
        assert row_after["amount_fy2027_request"] is None

    def test_insert_with_new_fy_column(self, schema_db):
        """INSERT works with the dynamically added FY column."""
        _ensure_fy_columns(schema_db, ["amount_fy2027_request"])

        schema_db.execute(
            """INSERT INTO budget_lines
               (source_file, exhibit_type, fiscal_year, account, account_title,
                organization_name, pe_number, amount_fy2027_request)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("test2.xlsx", "p1", "2027", "2035", "Aircraft Procurement",
             "Army", "0205231A", 15000.0),
        )
        schema_db.commit()

        row = schema_db.execute(
            "SELECT amount_fy2027_request FROM budget_lines WHERE source_file = 'test2.xlsx'"
        ).fetchone()
        assert row["amount_fy2027_request"] == 15000.0

    def test_ensure_fy_columns_idempotent(self, schema_db):
        """Calling _ensure_fy_columns() twice with the same columns does not error."""
        _ensure_fy_columns(schema_db, ["amount_fy2027_request", "quantity_fy2027_total"])
        # Second call should be a no-op
        _ensure_fy_columns(schema_db, ["amount_fy2027_request", "quantity_fy2027_total"])

        cols = _get_column_names(schema_db)
        assert "amount_fy2027_request" in cols
        assert "quantity_fy2027_total" in cols

    def test_fts5_triggers_work_after_alter(self, schema_db):
        """FTS5 insert trigger fires correctly after ALTER TABLE adds columns."""
        _ensure_fy_columns(schema_db, ["amount_fy2027_request"])

        schema_db.execute(
            """INSERT INTO budget_lines
               (source_file, exhibit_type, fiscal_year, account, account_title,
                organization_name, pe_number, line_item_title, amount_fy2027_request)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("test3.xlsx", "r1", "2027", "1300", "RDT&E",
             "Navy", "0602702E", "Advanced Stealth Research", 99000.0),
        )
        schema_db.commit()

        # Verify FTS index was updated (trigger fired)
        fts_rows = schema_db.execute(
            "SELECT rowid FROM budget_lines_fts "
            "WHERE budget_lines_fts MATCH 'Stealth'"
        ).fetchall()
        assert len(fts_rows) >= 1

        # Verify budget_lines and FTS row counts match
        bl_count = schema_db.execute(
            "SELECT COUNT(*) FROM budget_lines"
        ).fetchone()[0]
        fts_count = schema_db.execute(
            "SELECT COUNT(*) FROM budget_lines_fts"
        ).fetchone()[0]
        assert bl_count == fts_count
