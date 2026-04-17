"""Tests for BLI description FTS5 search (migration 6, api.routes.search).

Phase 9 of enrichment populates ``bli_descriptions`` from P-5 justification
PDF pages; migration 6 adds a ``bli_descriptions_fts`` virtual table and
``_bli_description_select`` surfaces those matches via /api/v1/search when
``source`` is "descriptions" or "both".
"""
from __future__ import annotations

import sqlite3

import pytest

from api.routes.search import _bli_description_select
from pipeline.schema import migrate


@pytest.fixture()
def db() -> sqlite3.Connection:
    """Fresh in-memory DB with all migrations applied and a few bli_descriptions."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    migrate(conn)
    conn.execute(
        "INSERT INTO bli_descriptions "
        "(bli_key, fiscal_year, source_file, page_start, page_end, "
        " section_header, description_text) "
        "VALUES "
        "('1506N:0577', 'FY2025', 'APN.pdf', 42, 42, 'P-5 Justification', "
        " 'This funds satellite communications terminals for the fleet.'),"
        "('1109N:2038', 'FY2024', 'PMC.pdf', 11, 11, 'P-5 Justification', "
        " 'Light armored vehicle product improvement program.'),"
        "('1810N:3107', 'FY2010', 'OPN.pdf', 1006, 1006, 'P-5 Justification', "
        " 'Submarine broadcast support via satellite relay.')"
    )
    conn.commit()
    return conn


def test_fts_matches_single_term(db):
    results = _bli_description_select("satellite", "satellite", limit=10, offset=0, conn=db)
    assert len(results) == 2
    bli_keys = {r["data"]["bli_key"] for r in results}
    assert bli_keys == {"1506N:0577", "1810N:3107"}
    assert all(r["result_type"] == "bli_description" for r in results)


def test_fts_snippet_highlights_match(db):
    results = _bli_description_select("armored", "armored", limit=10, offset=0, conn=db)
    assert len(results) == 1
    assert "<mark" in results[0]["snippet"].lower()


def test_fts_no_matches_returns_empty(db):
    results = _bli_description_select("quantum", "quantum", limit=10, offset=0, conn=db)
    assert results == []


def test_like_fallback_when_fts_missing():
    """Pre-migration-6 DBs without bli_descriptions_fts fall back to LIKE scan."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Recreate only the base table (no FTS virtual table, no triggers).
    conn.executescript(
        """
        CREATE TABLE bli_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bli_key TEXT NOT NULL, fiscal_year TEXT, source_file TEXT,
            page_start INTEGER, page_end INTEGER,
            section_header TEXT, description_text TEXT
        );
        INSERT INTO bli_descriptions (bli_key, fiscal_year, description_text)
        VALUES ('X:1', 'FY2025', 'satellite constellation procurement');
        """
    )
    results = _bli_description_select("satellite", "satellite", limit=10, offset=0, conn=conn)
    assert len(results) == 1
    assert results[0]["score"] is None  # LIKE path doesn't produce bm25 scores


def test_migration_006_rebuilds_fts_from_existing_rows():
    """bli_descriptions rows present before migration 6 should be searchable after."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Apply migrations 1-5 first by temporarily truncating the list.
    from pipeline import schema as schema_module

    orig = schema_module._MIGRATIONS
    try:
        schema_module._MIGRATIONS = [m for m in orig if m[0] <= 5]
        migrate(conn)
        # The bli_descriptions base table is created by enricher.Phase 9, not
        # by any earlier migration — simulate that state here.
        conn.executescript(
            """
            CREATE TABLE bli_descriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bli_key TEXT NOT NULL, fiscal_year TEXT, source_file TEXT,
                page_start INTEGER, page_end INTEGER,
                section_header TEXT, description_text TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO bli_descriptions (bli_key, description_text) "
            "VALUES ('pre:1', 'hypersonic glide vehicle funding')"
        )
        conn.commit()
        # Now apply the remaining migrations (6+) which should rebuild the FTS index.
        schema_module._MIGRATIONS = orig
        migrate(conn)
    finally:
        schema_module._MIGRATIONS = orig

    results = _bli_description_select("hypersonic", "hypersonic", limit=10, offset=0, conn=conn)
    assert len(results) == 1
    assert results[0]["data"]["bli_key"] == "pre:1"
