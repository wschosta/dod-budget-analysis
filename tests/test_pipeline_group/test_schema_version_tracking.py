"""Ensure prod entry points populate schema_version.

Before this test's corresponding fix, `pipeline.builder.create_database()`
and `pipeline.enricher.enrich()` both ran inline DDL that duplicated the
migration-owned schema but never called ``migrate()``. As a result,
``schema_version`` on prod DBs was empty, which defeats the whole purpose
of the migration system (future migrations can't tell what's applied).

These tests guard against regressions: every prod entry point that opens
a DB connection must leave ``schema_version`` at the latest migration.
"""
from __future__ import annotations

import sqlite3
import sys
import types

# Stub pdfplumber/openpyxl early so pipeline.builder imports cleanly.
for _mod in ("pdfplumber", "openpyxl", "pandas"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

from pipeline.builder import create_database  # noqa: E402
from pipeline.schema import _MIGRATIONS, _current_version  # noqa: E402


def test_create_database_populates_schema_version(tmp_path):
    db = tmp_path / "fresh.sqlite"
    conn = create_database(db)
    try:
        assert _current_version(conn) == _MIGRATIONS[-1][0]
    finally:
        conn.close()


def test_create_database_is_idempotent(tmp_path):
    """Re-opening an existing DB mustn't re-apply migrations or alter version."""
    db = tmp_path / "idempotent.sqlite"
    first = create_database(db)
    first_version = _current_version(first)
    first.close()

    second = create_database(db)
    try:
        assert _current_version(second) == first_version
        # And exactly one row per migration — no duplicates.
        counts = second.execute(
            "SELECT version, COUNT(*) FROM schema_version GROUP BY version"
        ).fetchall()
        assert all(c == 1 for _, c in counts)
    finally:
        second.close()


def test_create_database_catches_up_legacy_db(tmp_path):
    """A DB missing schema_version entirely still gets migrated on open."""
    db = tmp_path / "legacy.sqlite"
    # Simulate a pre-migration-system DB: create only budget_lines, no
    # schema_version, and verify create_database brings it up to current.
    raw = sqlite3.connect(str(db))
    raw.execute(
        "CREATE TABLE budget_lines (id INTEGER PRIMARY KEY, source_file TEXT)"
    )
    raw.commit()
    raw.close()

    conn = create_database(db)
    try:
        assert _current_version(conn) == _MIGRATIONS[-1][0]
    finally:
        conn.close()


def test_enrich_brings_schema_to_current(tmp_path):
    """enrich() must migrate on DBs that predate the migration system."""
    from pipeline.enricher import enrich

    db = tmp_path / "legacy_enrich.sqlite"
    # Build a minimal DB with just budget_lines (no schema_version, no
    # enrichment tables).  enrich() should bring schema_version to latest
    # even if no phases do meaningful work.
    raw = sqlite3.connect(str(db))
    raw.execute(
        "CREATE TABLE budget_lines (id INTEGER PRIMARY KEY, source_file TEXT, "
        "exhibit_type TEXT, pe_number TEXT, fiscal_year TEXT)"
    )
    raw.execute(
        "CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY, source_file TEXT, "
        "exhibit_type TEXT, fiscal_year TEXT, page_number INTEGER, page_text TEXT)"
    )
    raw.commit()
    raw.close()

    # Run a no-op phase set — enrich() should still migrate before returning.
    enrich(db, phases=set(), rebuild=False)

    final = sqlite3.connect(str(db))
    try:
        assert _current_version(final) == _MIGRATIONS[-1][0]
    finally:
        final.close()
