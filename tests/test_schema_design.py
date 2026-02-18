"""
Tests for schema_design.py — migration framework and normalized schema creation.

Tests _current_version, migrate, and create_normalized_db.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schema_design import _current_version, migrate, create_normalized_db


class TestCurrentVersion:
    def test_no_schema_version_table(self):
        conn = sqlite3.connect(":memory:")
        assert _current_version(conn) == 0
        conn.close()

    def test_empty_schema_version_table(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE schema_version (version INTEGER, description TEXT, applied_at TEXT)"
        )
        assert _current_version(conn) == 0
        conn.close()

    def test_returns_max_version(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            "CREATE TABLE schema_version (version INTEGER, description TEXT, applied_at TEXT)"
        )
        conn.execute("INSERT INTO schema_version (version, description) VALUES (1, 'v1')")
        conn.execute("INSERT INTO schema_version (version, description) VALUES (2, 'v2')")
        conn.commit()
        assert _current_version(conn) == 2
        conn.close()


class TestMigrate:
    def test_applies_all_migrations(self):
        conn = sqlite3.connect(":memory:")
        applied = migrate(conn)
        assert applied >= 1  # At least migration 1

        # Schema version table should now exist with entries
        version = _current_version(conn)
        assert version >= 1

        conn.close()

    def test_idempotent(self):
        conn = sqlite3.connect(":memory:")
        first = migrate(conn)
        second = migrate(conn)
        assert first >= 1
        assert second == 0  # Already applied
        conn.close()

    def test_creates_reference_tables(self):
        conn = sqlite3.connect(":memory:")
        migrate(conn)

        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {r[0] for r in tables}

        assert "services_agencies" in table_names
        assert "appropriation_titles" in table_names
        assert "exhibit_types" in table_names
        assert "budget_cycles" in table_names
        assert "budget_line_items" in table_names

        conn.close()

    def test_seeds_services(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        migrate(conn)

        rows = conn.execute("SELECT * FROM services_agencies").fetchall()
        codes = {r["code"] for r in rows}
        assert "Army" in codes
        assert "Navy" in codes
        assert "Air Force" in codes
        assert len(rows) >= 15  # At least 15 agencies seeded

        conn.close()

    def test_seeds_exhibit_types(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        migrate(conn)

        rows = conn.execute("SELECT * FROM exhibit_types").fetchall()
        codes = {r["code"] for r in rows}
        assert "p1" in codes
        assert "r1" in codes
        assert "o1" in codes
        assert "m1" in codes

        conn.close()

    def test_seeds_budget_cycles(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        migrate(conn)

        rows = conn.execute("SELECT * FROM budget_cycles").fetchall()
        codes = {r["code"] for r in rows}
        assert "PB" in codes
        assert "ENACTED" in codes

        conn.close()

    def test_creates_indexes(self):
        conn = sqlite3.connect(":memory:")
        migrate(conn)

        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        idx_names = {r[0] for r in indexes}
        assert "idx_bli_fiscal_year" in idx_names
        assert "idx_bli_pe_number" in idx_names

        conn.close()


class TestCreateNormalizedDb:
    def test_creates_file(self, tmp_path):
        db_path = tmp_path / "test.sqlite"
        conn = create_normalized_db(db_path)
        assert db_path.exists()

        # Check WAL mode
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

        # Check foreign keys enabled
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1

        conn.close()

    def test_migrations_applied(self, tmp_path):
        db_path = tmp_path / "test.sqlite"
        conn = create_normalized_db(db_path)
        version = _current_version(conn)
        assert version >= 1
        conn.close()

    def test_idempotent_reopen(self, tmp_path):
        db_path = tmp_path / "test.sqlite"
        conn1 = create_normalized_db(db_path)
        v1 = _current_version(conn1)
        conn1.close()

        conn2 = create_normalized_db(db_path)
        v2 = _current_version(conn2)
        conn2.close()

        assert v1 == v2
