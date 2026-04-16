"""Tests for utils/database.py — QueryBuilder and batch_upsert.

Covers the untested portions of utils/database.py: the QueryBuilder fluent
API, batch_upsert with conflict resolution, get_quantity_columns, and
_validate_identifier error paths.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.database import (
    QueryBuilder,
    batch_upsert,
    get_quantity_columns,
    _validate_identifier,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db():
    """In-memory SQLite database with a sample table."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY,
            pe_number TEXT NOT NULL,
            source_file TEXT,
            amount REAL,
            UNIQUE(pe_number, source_file)
        )
    """)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture()
def qty_db():
    """Database with quantity_fy columns for schema introspection tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY,
            pe_number TEXT,
            quantity_fy2024 REAL,
            quantity_fy2025 REAL,
            quantity_fy2026 REAL,
            amount_fy2026_request REAL
        )
    """)
    conn.commit()
    yield conn
    conn.close()


# ── _validate_identifier ─────────────────────────────────────────────────────


class TestValidateIdentifier:
    def test_valid_identifiers(self):
        # Should not raise
        _validate_identifier("budget_lines", "table")
        _validate_identifier("amount_fy2026_request", "column")
        _validate_identifier("pe_number", "column")

    def test_invalid_semicolon(self):
        with pytest.raises(ValueError, match="table name"):
            _validate_identifier("budget_lines; DROP TABLE", "table name")

    def test_invalid_spaces(self):
        with pytest.raises(ValueError, match="column"):
            _validate_identifier("bad column", "column")

    def test_invalid_quotes(self):
        with pytest.raises(ValueError, match="column"):
            _validate_identifier("col'umn", "column")

    def test_invalid_parentheses(self):
        with pytest.raises(ValueError, match="table"):
            _validate_identifier("tbl()", "table")


# ── QueryBuilder ─────────────────────────────────────────────────────────────


class TestQueryBuilder:
    def test_minimal_query(self):
        sql, params = QueryBuilder().from_table("items").build()
        assert sql == "SELECT * FROM items"
        assert params == []

    def test_select_specific_columns(self):
        sql, params = (
            QueryBuilder()
            .from_table("budget_lines")
            .select(["id", "pe_number", "amount"])
            .build()
        )
        assert "SELECT id, pe_number, amount FROM budget_lines" == sql
        assert params == []

    def test_where_single_condition(self):
        sql, params = (
            QueryBuilder()
            .from_table("budget_lines")
            .where("fiscal_year = ?", "FY2026")
            .build()
        )
        assert "WHERE fiscal_year = ?" in sql
        assert params == ["FY2026"]

    def test_where_multiple_conditions(self):
        sql, params = (
            QueryBuilder()
            .from_table("budget_lines")
            .where("fiscal_year = ?", "FY2026")
            .where("organization_name LIKE ?", "%Army%")
            .build()
        )
        assert "WHERE fiscal_year = ? AND organization_name LIKE ?" in sql
        assert params == ["FY2026", "%Army%"]

    def test_order_by_asc(self):
        sql, _ = (
            QueryBuilder()
            .from_table("budget_lines")
            .order_by("pe_number", "ASC")
            .build()
        )
        assert "ORDER BY pe_number ASC" in sql

    def test_order_by_desc(self):
        sql, _ = (
            QueryBuilder()
            .from_table("budget_lines")
            .order_by("amount", "DESC")
            .build()
        )
        assert "ORDER BY amount DESC" in sql

    def test_order_by_normalizes_direction(self):
        sql, _ = (
            QueryBuilder()
            .from_table("budget_lines")
            .order_by("amount", "invalid_dir")
            .build()
        )
        # Invalid direction should default to ASC
        assert "ORDER BY amount ASC" in sql

    def test_limit(self):
        sql, _ = (
            QueryBuilder()
            .from_table("budget_lines")
            .limit(25)
            .build()
        )
        assert "LIMIT 25" in sql

    def test_offset(self):
        sql, _ = (
            QueryBuilder()
            .from_table("budget_lines")
            .offset(50)
            .build()
        )
        assert "OFFSET 50" in sql

    def test_full_query_chain(self):
        sql, params = (
            QueryBuilder()
            .from_table("budget_lines")
            .select(["id", "pe_number"])
            .where("fiscal_year = ?", "FY2026")
            .where("amount > ?", 1000)
            .order_by("amount", "DESC")
            .limit(25)
            .offset(0)
            .build()
        )
        assert sql == (
            "SELECT id, pe_number FROM budget_lines "
            "WHERE fiscal_year = ? AND amount > ? "
            "ORDER BY amount DESC "
            "LIMIT 25 "
            "OFFSET 0"
        )
        assert params == ["FY2026", 1000]

    def test_no_table_raises(self):
        with pytest.raises(ValueError, match="no table set"):
            QueryBuilder().select(["id"]).build()

    def test_wildcard_select(self):
        sql, _ = QueryBuilder().from_table("t").select(["*"]).build()
        assert "SELECT * FROM t" == sql

    def test_query_executes_against_db(self, db):
        """Verify built query actually runs against SQLite."""
        db.execute(
            "INSERT INTO budget_lines (pe_number, source_file, amount) VALUES (?, ?, ?)",
            ("0602120A", "test.xlsx", 100.0),
        )
        db.commit()

        sql, params = (
            QueryBuilder()
            .from_table("budget_lines")
            .select(["pe_number", "amount"])
            .where("pe_number = ?", "0602120A")
            .build()
        )
        row = db.execute(sql, params).fetchone()
        assert row["pe_number"] == "0602120A"
        assert row["amount"] == 100.0


# ── batch_upsert ─────────────────────────────────────────────────────────────


class TestBatchUpsert:
    def test_empty_rows(self, db):
        count = batch_upsert(
            db, "budget_lines",
            ["pe_number", "source_file", "amount"],
            [],
            ["pe_number", "source_file"],
        )
        assert count == 0

    def test_basic_insert(self, db):
        rows = [
            ("0602120A", "fy2026.xlsx", 100.0),
            ("0603285E", "fy2026.xlsx", 200.0),
        ]
        count = batch_upsert(
            db, "budget_lines",
            ["pe_number", "source_file", "amount"],
            rows,
            ["pe_number", "source_file"],
        )
        assert count == 2
        total = db.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0]
        assert total == 2

    def test_upsert_updates_on_conflict(self, db):
        """Re-inserting same conflict key should update the amount."""
        rows1 = [("0602120A", "fy2026.xlsx", 100.0)]
        batch_upsert(
            db, "budget_lines",
            ["pe_number", "source_file", "amount"],
            rows1,
            ["pe_number", "source_file"],
        )

        # Upsert with new amount
        rows2 = [("0602120A", "fy2026.xlsx", 999.0)]
        batch_upsert(
            db, "budget_lines",
            ["pe_number", "source_file", "amount"],
            rows2,
            ["pe_number", "source_file"],
        )

        total = db.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0]
        assert total == 1
        amount = db.execute(
            "SELECT amount FROM budget_lines WHERE pe_number = '0602120A'"
        ).fetchone()[0]
        assert amount == 999.0

    def test_multi_batch(self, db):
        """Rows exceeding batch_size are split across multiple batches."""
        rows = [(f"PE{i:04d}X", f"file{i}.xlsx", float(i)) for i in range(25)]
        count = batch_upsert(
            db, "budget_lines",
            ["pe_number", "source_file", "amount"],
            rows,
            ["pe_number", "source_file"],
            batch_size=7,
        )
        assert count == 25
        total = db.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0]
        assert total == 25

    def test_validates_identifiers(self, db):
        with pytest.raises(ValueError):
            batch_upsert(
                db, "budget_lines; DROP TABLE",
                ["pe_number"], [("x",)], ["pe_number"],
            )

    def test_validates_column_names(self, db):
        with pytest.raises(ValueError):
            batch_upsert(
                db, "budget_lines",
                ["bad column"], [("x",)], ["bad column"],
            )


# ── get_quantity_columns ─────────────────────────────────────────────────────


class TestGetQuantityColumns:
    def test_finds_quantity_columns(self, qty_db):
        cols = get_quantity_columns(qty_db)
        assert cols == ["quantity_fy2024", "quantity_fy2025", "quantity_fy2026"]

    def test_excludes_non_quantity_columns(self, qty_db):
        cols = get_quantity_columns(qty_db)
        assert "amount_fy2026_request" not in cols
        assert "pe_number" not in cols

    def test_empty_when_no_quantity_columns(self, db):
        cols = get_quantity_columns(db)
        assert cols == []

    def test_returns_sorted(self, qty_db):
        cols = get_quantity_columns(qty_db)
        assert cols == sorted(cols)
