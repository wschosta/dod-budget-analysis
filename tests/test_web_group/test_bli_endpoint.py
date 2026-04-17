"""Tests for GET /api/v1/bli/{bli_key}."""
from __future__ import annotations

import sqlite3

import pytest
from fastapi import HTTPException

from api.routes.bli import get_bli


@pytest.fixture()
def db() -> sqlite3.Connection:
    """In-memory DB with the tables the BLI endpoint reads from."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE bli_index (
            bli_key TEXT PRIMARY KEY,
            account TEXT NOT NULL,
            line_item TEXT,
            display_title TEXT,
            organization_name TEXT,
            budget_type TEXT,
            budget_activity_title TEXT,
            appropriation_code TEXT,
            appropriation_title TEXT,
            fiscal_years TEXT,
            exhibit_types TEXT,
            row_count INTEGER
        );
        CREATE TABLE bli_tags (
            bli_key TEXT, tag TEXT, tag_source TEXT, confidence REAL
        );
        CREATE TABLE bli_pe_map (
            bli_key TEXT, pe_number TEXT, confidence REAL,
            source_file TEXT, page_number INTEGER,
            PRIMARY KEY (bli_key, pe_number)
        );
        CREATE TABLE pe_index (pe_number TEXT PRIMARY KEY, display_title TEXT);
        CREATE TABLE bli_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bli_key TEXT NOT NULL, fiscal_year TEXT, source_file TEXT,
            page_start INTEGER, page_end INTEGER,
            section_header TEXT, description_text TEXT
        );
        INSERT INTO bli_index VALUES (
            '1506N:0577', '1506N', '0577', 'EP-3 Series Mods', 'Navy',
            'investment', 'Combat Aircraft', 'APN', 'Aircraft Procurement, Navy',
            '["FY2024","FY2025"]', '["p1"]', 3
        );
        INSERT INTO bli_tags VALUES
            ('1506N:0577', 'aviation', 'keyword', 0.8),
            ('1506N:0577', 'isr', 'keyword', 0.7);
        INSERT INTO pe_index VALUES ('0305206N', 'Navy ISR Program');
        INSERT INTO bli_pe_map VALUES
            ('1506N:0577', '0305206N', 0.9, 'APN.pdf', 42);
        INSERT INTO bli_descriptions
            (bli_key, fiscal_year, source_file, page_start, page_end, section_header, description_text)
        VALUES
            ('1506N:0577', 'FY2025', 'APN.pdf', 42, 42, 'P-5 Justification',
             'Modifications to the EP-3 Series aircraft provide signals intelligence upgrades.');
        """
    )
    return conn


def test_returns_full_payload(db):
    result = get_bli("1506N:0577", conn=db)
    assert result["bli_key"] == "1506N:0577"
    assert result["display_title"] == "EP-3 Series Mods"
    assert result["fiscal_years"] == ["FY2024", "FY2025"]
    assert result["exhibit_types"] == ["p1"]
    assert len(result["tags"]) == 2
    assert result["related_pes"][0]["pe_number"] == "0305206N"
    assert result["related_pes"][0]["pe_title"] == "Navy ISR Program"
    assert len(result["descriptions"]) == 1
    assert "signals intelligence" in result["descriptions"][0]["snippet"]


def test_returns_404_for_unknown_bli(db):
    with pytest.raises(HTTPException) as exc:
        get_bli("9999X:12345", conn=db)
    assert exc.value.status_code == 404


def test_partial_enrichment_omits_missing_tables():
    """If bli_tags / bli_pe_map / bli_descriptions haven't been built yet,
    the endpoint should still return the bli_index entry with empty arrays."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE bli_index (
            bli_key TEXT PRIMARY KEY, account TEXT NOT NULL, line_item TEXT,
            display_title TEXT, organization_name TEXT, budget_type TEXT,
            budget_activity_title TEXT, appropriation_code TEXT,
            appropriation_title TEXT, fiscal_years TEXT, exhibit_types TEXT,
            row_count INTEGER
        );
        INSERT INTO bli_index VALUES
            ('3010:AH-64', '3010', 'AH-64', 'Apache', 'Army',
             'investment', 'Aircraft', 'AA', 'Aircraft Procurement, Army',
             '[]', '["p1"]', 1);
        """
    )
    result = get_bli("3010:AH-64", conn=conn)
    assert result["display_title"] == "Apache"
    assert result["tags"] == []
    assert result["related_pes"] == []
    assert result["descriptions"] == []


def test_missing_bli_index_returns_503():
    """DB with no bli_index at all (e.g. fresh build, pre-enrichment) — 503 not 500."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    with pytest.raises(HTTPException) as exc:
        get_bli("any:thing", conn=conn)
    assert exc.value.status_code == 503


def test_malformed_json_fiscal_years_degrades_gracefully(db):
    db.execute("UPDATE bli_index SET fiscal_years = 'not json' WHERE bli_key = '1506N:0577'")
    result = get_bli("1506N:0577", conn=db)
    assert result["fiscal_years"] == []
