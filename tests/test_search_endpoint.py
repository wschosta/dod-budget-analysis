"""
Tests for api/routes/search.py — search endpoint

Tests the search() function with FTS5 in-memory database.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.routes.search import search


@pytest.fixture()
def db():
    """In-memory database with FTS5 tables for search testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.execute("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            exhibit_type TEXT,
            sheet_name TEXT,
            fiscal_year TEXT,
            account TEXT,
            account_title TEXT,
            organization_name TEXT,
            budget_activity_title TEXT,
            sub_activity_title TEXT,
            line_item TEXT,
            line_item_title TEXT,
            pe_number TEXT,
            amount_type TEXT,
            amount_fy2024_actual REAL,
            amount_fy2025_enacted REAL,
            amount_fy2026_request REAL,
            amount_fy2026_total REAL
        )
    """)

    conn.execute("""
        CREATE VIRTUAL TABLE budget_lines_fts USING fts5(
            account_title, line_item_title, organization_name,
            content='budget_lines', content_rowid='id',
            tokenize='unicode61'
        )
    """)

    # Insert test data
    rows = [
        (1, "army.xlsx", "p1", "S1", "FY 2026", "3010", "Aircraft Procurement",
         "Army", "Tactical", None, "AH-64", "Apache Helicopter", "0207449A",
         "budget_authority", 1000, 900, 1100, 1100),
        (2, "navy.xlsx", "p1", "S1", "FY 2026", "1506", "Shipbuilding",
         "Navy", "Combat", None, "DDG-51", "Missile Defense Destroyer", "0204311N",
         "budget_authority", 5000, 4500, 5500, 5500),
    ]

    for r in rows:
        conn.execute(
            "INSERT INTO budget_lines VALUES ("
            + ",".join("?" * len(r))
            + ")",
            r,
        )
        # Manually insert into FTS: account_title=r[6], line_item_title=r[11], organization_name=r[7]
        conn.execute(
            "INSERT INTO budget_lines_fts(rowid, account_title, line_item_title, "
            "organization_name) VALUES (?, ?, ?, ?)",
            (r[0], r[6], r[11], r[7]),
        )

    # PDF pages table (LION-100: includes fiscal_year and exhibit_type)
    conn.execute("""
        CREATE TABLE pdf_pages (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            source_category TEXT,
            fiscal_year TEXT,
            exhibit_type TEXT,
            page_number INTEGER,
            page_text TEXT,
            has_tables INTEGER,
            table_data TEXT
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE pdf_pages_fts USING fts5(
            page_text,
            content='pdf_pages', content_rowid='id',
            tokenize='unicode61'
        )
    """)

    conn.execute(
        "INSERT INTO pdf_pages VALUES (1, 'budget.pdf', 'Army', 'FY 2026', 'r2', 5, "
        "'The Apache helicopter program received additional funding.', 0, NULL)"
    )
    conn.execute(
        "INSERT INTO pdf_pages_fts(rowid, page_text) VALUES "
        "(1, 'The Apache helicopter program received additional funding.')"
    )

    conn.commit()
    yield conn
    conn.close()


def _search(db, q, **kwargs):
    """Call search with all required defaults."""
    defaults = dict(type="both", limit=20, offset=0, conn=db)
    defaults.update(kwargs)
    return search(q=q, **defaults)


class TestSearch:
    def test_search_budget_lines(self, db):
        result = _search(db, "Apache", type="excel")
        assert result.total >= 1
        assert result.results[0].result_type == "budget_line"

    def test_search_pdf(self, db):
        result = _search(db, "Apache", type="pdf")
        assert result.total >= 1
        assert result.results[0].result_type == "pdf_page"

    def test_search_both(self, db):
        result = _search(db, "Apache")
        types = {r.result_type for r in result.results}
        assert "budget_line" in types
        assert "pdf_page" in types

    def test_no_results(self, db):
        result = _search(db, "nonexistentterm")
        assert result.total == 0

    def test_limit_respected(self, db):
        # Limit is per-type; search a single type to verify
        result = _search(db, "Apache", type="excel", limit=1)
        budget_results = [r for r in result.results if r.result_type == "budget_line"]
        assert len(budget_results) <= 1

    def test_empty_query_rejected(self, db):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _search(db, "AND OR NOT")
        assert exc_info.value.status_code == 400

    def test_snippets_present(self, db):
        result = _search(db, "Apache", type="excel")
        if result.results:
            assert result.results[0].snippet is not None or result.results[0].data is not None

    def test_response_metadata(self, db):
        result = _search(db, "Army", type="excel")
        assert result.query == "Army"
        assert result.limit == 20
        assert result.offset == 0
