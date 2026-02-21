"""
BEAR-008: Database migration framework tests.

Tests the schema migration framework handles version upgrades correctly:
1. Create v1 schema, run migrate() — verify tables upgraded to current version.
2. Running migrate() on already-current schema is a no-op.
3. _current_version() returns correct version number.
4. Schema version table is created if missing.
5. All expected indexes exist after migration.
6. FTS5 content-sync triggers exist after migration.
"""
# DONE [Group: BEAR] BEAR-008: Add database migration framework tests (~2,500 tokens)

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from schema_design import (
    migrate,
    _current_version,
    _MIGRATIONS,
    create_normalized_db,
)


@pytest.fixture()
def fresh_db(tmp_path):
    """Return a fresh SQLite connection with no schema applied."""
    db_path = tmp_path / "migration_test.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture()
def migrated_db(tmp_path):
    """Return a fully migrated normalized database."""
    db_path = tmp_path / "migrated.sqlite"
    conn = create_normalized_db(db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _get_tables(conn):
    """Return set of table names in the database."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r[0] for r in rows}


def _get_triggers(conn):
    """Return set of trigger names in the database."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger'"
    ).fetchall()
    return {r[0] for r in rows}


def _get_indexes(conn):
    """Return set of index names in the database."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' "
        "AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r[0] for r in rows}


class TestMigrationFramework:
    """Tests for schema_design.py migrate() and version tracking."""

    def test_migrate_from_empty_applies_all(self, fresh_db):
        """migrate() on empty DB applies all migrations."""
        applied = migrate(fresh_db)
        assert applied == len(_MIGRATIONS)

        # Verify schema_version has entries
        versions = fresh_db.execute(
            "SELECT version, description FROM schema_version ORDER BY version"
        ).fetchall()
        assert len(versions) == len(_MIGRATIONS)
        assert versions[0]["version"] == 1

    def test_migrate_idempotent(self, fresh_db):
        """Running migrate() twice is a no-op on second call."""
        first = migrate(fresh_db)
        assert first == len(_MIGRATIONS)

        second = migrate(fresh_db)
        assert second == 0  # No new migrations applied

    def test_current_version_on_empty_db(self, fresh_db):
        """_current_version() returns 0 on empty database."""
        assert _current_version(fresh_db) == 0

    def test_current_version_after_migrate(self, fresh_db):
        """_current_version() returns highest version after migration."""
        migrate(fresh_db)
        version = _current_version(fresh_db)
        max_version = max(v for v, _, _ in _MIGRATIONS)
        assert version == max_version

    def test_schema_version_table_created(self, fresh_db):
        """schema_version table is created even if not already present."""
        tables_before = _get_tables(fresh_db)
        assert "schema_version" not in tables_before

        migrate(fresh_db)

        tables_after = _get_tables(fresh_db)
        assert "schema_version" in tables_after

    def test_expected_tables_after_migration(self, migrated_db):
        """All expected tables exist after full migration."""
        tables = _get_tables(migrated_db)
        expected = {
            "schema_version",
            "services_agencies",
            "appropriation_titles",
            "exhibit_types",
            "budget_cycles",
            "budget_line_items",
            "document_sources",
            "pdf_content",
        }
        for t in expected:
            assert t in tables, f"Missing table: {t}"

    def test_expected_indexes_after_migration(self, migrated_db):
        """Key indexes exist after full migration."""
        indexes = _get_indexes(migrated_db)
        expected = {
            "idx_bli_service",
            "idx_bli_exhibit",
            "idx_bli_fiscal_year",
            "idx_bli_pe_number",
            "idx_bli_source_file",
            "idx_pdf_source",
        }
        for idx in expected:
            assert idx in indexes, f"Missing index: {idx}"

    def test_fts5_triggers_after_migration(self, migrated_db):
        """FTS5 content-sync triggers exist after migration."""
        triggers = _get_triggers(migrated_db)
        expected = {
            "budget_line_items_fts_ai",  # AFTER INSERT
            "budget_line_items_fts_ad",  # AFTER DELETE
            "budget_line_items_fts_au",  # AFTER UPDATE
        }
        for trig in expected:
            assert trig in triggers, f"Missing trigger: {trig}"

    def test_reference_data_seeded(self, migrated_db):
        """Reference tables are populated with seed data after migration."""
        services = migrated_db.execute(
            "SELECT COUNT(*) FROM services_agencies"
        ).fetchone()[0]
        assert services > 0, "services_agencies should have seed data"

        exhibit_types = migrated_db.execute(
            "SELECT COUNT(*) FROM exhibit_types"
        ).fetchone()[0]
        assert exhibit_types > 0, "exhibit_types should have seed data"

        cycles = migrated_db.execute(
            "SELECT COUNT(*) FROM budget_cycles"
        ).fetchone()[0]
        assert cycles > 0, "budget_cycles should have seed data"

    def test_fts5_insert_trigger_works(self, migrated_db):
        """FTS5 insert trigger fires when data is added to budget_line_items."""
        migrated_db.execute(
            """INSERT INTO budget_line_items
               (source_file, organization_name, exhibit_type, fiscal_year,
                account, account_title, pe_number, line_item_title)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("test.xlsx", "Army", "p1", "2026", "2035",
             "Aircraft Procurement", "0205231A", "Apache Upgrade Program"),
        )
        migrated_db.commit()

        fts_results = migrated_db.execute(
            "SELECT rowid FROM budget_line_items_fts "
            "WHERE budget_line_items_fts MATCH 'Apache'"
        ).fetchall()
        assert len(fts_results) >= 1
