"""
Tests for Phase 2 Stream B API changes:
  B2.1: Program changes partial route
  B2.2: Program PDF pages partial route
  B2.3: Sort parameters on program-list partial
  B2.4: Top changes partial route
  B2.5: PE changes edge cases (has_budget_lines flag)
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from api.app import create_app
from api.database import get_db


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Create a test app with full schema for Phase 2 tests."""
    tmp = tmp_path_factory.mktemp("phase2_api_test")
    db_path = tmp / "test.sqlite"

    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT, exhibit_type TEXT, sheet_name TEXT,
            fiscal_year TEXT, account TEXT, account_title TEXT,
            organization TEXT, organization_name TEXT,
            budget_activity TEXT, budget_activity_title TEXT,
            sub_activity TEXT, sub_activity_title TEXT,
            line_item TEXT, line_item_title TEXT,
            pe_number TEXT, appropriation_code TEXT, appropriation_title TEXT,
            currency_year TEXT, amount_unit TEXT DEFAULT 'thousands',
            amount_type TEXT DEFAULT 'budget_authority', budget_type TEXT,
            amount_fy2024_actual REAL, amount_fy2025_enacted REAL,
            amount_fy2025_supplemental REAL, amount_fy2025_total REAL,
            amount_fy2026_request REAL, amount_fy2026_reconciliation REAL,
            amount_fy2026_total REAL,
            quantity_fy2024 REAL, quantity_fy2025 REAL,
            quantity_fy2026_request REAL, quantity_fy2026_total REAL,
            classification TEXT, extra_fields TEXT
        );
        CREATE TABLE pdf_pages (
            id INTEGER PRIMARY KEY, source_file TEXT,
            source_category TEXT, page_number INTEGER,
            page_text TEXT, has_tables INTEGER, table_data TEXT,
            fiscal_year TEXT, exhibit_type TEXT
        );
        CREATE TABLE ingested_files (
            id INTEGER PRIMARY KEY, file_path TEXT, file_type TEXT,
            row_count INTEGER, ingested_at TEXT, status TEXT
        );
        CREATE VIRTUAL TABLE budget_lines_fts USING fts5(
            account_title, line_item_title, budget_activity_title,
            content=budget_lines
        );

        -- PE enrichment tables
        CREATE TABLE pe_index (
            pe_number TEXT PRIMARY KEY,
            display_title TEXT,
            organization_name TEXT,
            budget_type TEXT,
            fiscal_years TEXT,
            exhibit_types TEXT,
            source TEXT NOT NULL DEFAULT 'budget_lines',
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE pe_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT,
            tag TEXT,
            tag_source TEXT,
            confidence REAL DEFAULT 1.0,
            source_files TEXT
        );
        CREATE TABLE pe_lineage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_pe TEXT,
            referenced_pe TEXT,
            link_type TEXT,
            confidence REAL DEFAULT 0.9,
            fiscal_year TEXT,
            context_snippet TEXT
        );
        CREATE TABLE pe_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT,
            fiscal_year TEXT,
            source_file TEXT,
            page_start INTEGER,
            page_end INTEGER,
            section_header TEXT,
            description_text TEXT
        );
        CREATE TABLE project_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT NOT NULL,
            project_number TEXT,
            project_title TEXT,
            fiscal_year TEXT,
            section_header TEXT NOT NULL,
            description_text TEXT NOT NULL,
            source_file TEXT,
            page_start INTEGER,
            page_end INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE pdf_pe_numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT, pdf_page_id INTEGER,
            page_number INTEGER, source_file TEXT, fiscal_year TEXT
        );
        CREATE TABLE services_agencies (
            code TEXT PRIMARY KEY, full_name TEXT
        );
        CREATE TABLE exhibit_types (
            code TEXT PRIMARY KEY, display_name TEXT
        );

        INSERT INTO services_agencies VALUES ('Army', 'U.S. Army');
        INSERT INTO services_agencies VALUES ('Navy', 'U.S. Navy');
        INSERT INTO exhibit_types VALUES ('r1', 'RDT&E Summary');
        INSERT INTO exhibit_types VALUES ('r2', 'RDT&E Detail');

        -- PE with both FY2025 and FY2026 data (increase)
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title, pe_number,
             appropriation_code, appropriation_title,
             amount_fy2024_actual, amount_fy2025_enacted,
             amount_fy2025_total, amount_fy2026_request)
        VALUES
            ('army_r2.xlsx', 'r2', '2026', 'Army',
             'RDT&E Budget', 'Apache AH-64 Block III', '0604131A',
             'RDTE', 'RDT&E', 120000.0, 140000.0, 140000.0, 150000.0);

        -- PE with only FY2026 data (new program, no prior year)
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title, pe_number,
             appropriation_code, appropriation_title,
             amount_fy2024_actual, amount_fy2025_enacted,
             amount_fy2025_total, amount_fy2026_request)
        VALUES
            ('navy_r2.xlsx', 'r2', '2026', 'Navy',
             'RDT&E Budget', 'New Sensor Program', '0603292N',
             'RDTE', 'RDT&E', 0.0, 0.0, 0.0, 250000.0);

        -- PE with decrease
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title, pe_number,
             appropriation_code, appropriation_title,
             amount_fy2024_actual, amount_fy2025_enacted,
             amount_fy2025_total, amount_fy2026_request)
        VALUES
            ('af_r2.xlsx', 'r2', '2026', 'Air Force',
             'RDT&E Budget', 'Legacy Fighter Upgrade', '0604230F',
             'RDTE', 'RDT&E', 300000.0, 280000.0, 280000.0, 180000.0);

        INSERT INTO budget_lines_fts(rowid, account_title, line_item_title,
            budget_activity_title)
        SELECT id, account_title, line_item_title, budget_activity_title
        FROM budget_lines;

        INSERT INTO pe_index (pe_number, display_title, organization_name,
            budget_type, fiscal_years, exhibit_types) VALUES
            ('0604131A', 'Apache AH-64 Block III', 'Army', 'RDT&E',
             '["2026"]', '["r2"]'),
            ('0603292N', 'New Sensor Program', 'Navy', 'RDT&E',
             '["2026"]', '["r2"]'),
            ('0604230F', 'Legacy Fighter Upgrade', 'Air Force', 'RDT&E',
             '["2026"]', '["r2"]'),
            -- PE with only PDF data, no budget_lines
            ('0601234X', 'PDF-Only Program', 'Army', 'RDT&E',
             '["2026"]', '["r2"]');

        INSERT INTO pe_tags VALUES
            (NULL, '0604131A', 'aviation', 'structured', 1.0, '["army_r1.xlsx"]'),
            (NULL, '0603292N', 'sensors', 'structured', 1.0, '["navy_r1.xlsx"]'),
            (NULL, '0604230F', 'aviation', 'structured', 1.0, '["af_r1.xlsx"]');

        INSERT INTO pe_lineage VALUES
            (NULL, '0604131A', '0603292N', 'name_match', 0.6, '2026', 'aviation');

        INSERT INTO pe_descriptions VALUES
            (NULL, '0604131A', '2026', 'army_r2.pdf', 1, 3, 'Mission Description',
             'The Apache AH-64 Block III program...');

        -- PDF pages data
        INSERT INTO pdf_pages (id, source_file, page_number, page_text, has_tables,
            fiscal_year, exhibit_type)
        VALUES
            (1, 'army_r2.pdf', 5, 'Apache AH-64 Block III details...', 0,
             '2026', 'r2'),
            (2, 'army_r2.pdf', 6, 'More Apache details...', 1,
             '2026', 'r2');

        INSERT INTO pdf_pe_numbers (pe_number, pdf_page_id, page_number,
            source_file, fiscal_year)
        VALUES
            ('0604131A', 1, 5, 'army_r2.pdf', '2026'),
            ('0604131A', 2, 6, 'army_r2.pdf', '2026');
    """)
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)

    def _get_db_override():
        c = sqlite3.connect(str(db_path), check_same_thread=False)
        c.row_factory = sqlite3.Row
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_db] = _get_db_override
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def client_no_budget_lines(tmp_path_factory):
    """Create a test app with pe_index but NO budget_lines table."""
    tmp = tmp_path_factory.mktemp("phase2_no_bl_test")
    db_path = tmp / "test.sqlite"

    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE pe_index (
            pe_number TEXT PRIMARY KEY,
            display_title TEXT,
            organization_name TEXT,
            budget_type TEXT,
            fiscal_years TEXT,
            exhibit_types TEXT,
            source TEXT NOT NULL DEFAULT 'budget_lines',
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE pe_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT,
            tag TEXT,
            tag_source TEXT,
            confidence REAL DEFAULT 1.0,
            source_files TEXT
        );
        CREATE TABLE pe_lineage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_pe TEXT,
            referenced_pe TEXT,
            link_type TEXT,
            confidence REAL DEFAULT 0.9,
            fiscal_year TEXT,
            context_snippet TEXT
        );
        CREATE TABLE pe_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT,
            fiscal_year TEXT,
            source_file TEXT,
            page_start INTEGER,
            page_end INTEGER,
            section_header TEXT,
            description_text TEXT
        );
        CREATE TABLE pdf_pages (
            id INTEGER PRIMARY KEY, source_file TEXT,
            source_category TEXT, page_number INTEGER,
            page_text TEXT, has_tables INTEGER, table_data TEXT,
            fiscal_year TEXT, exhibit_type TEXT
        );
        CREATE TABLE pdf_pe_numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT, pdf_page_id INTEGER,
            page_number INTEGER, source_file TEXT, fiscal_year TEXT
        );
        CREATE TABLE services_agencies (
            code TEXT PRIMARY KEY, full_name TEXT
        );

        INSERT INTO pe_index VALUES
            ('0601234X', 'PDF-Only Program', 'Army', 'RDT&E',
             '["2026"]', '["r2"]', 'budget_lines', datetime('now'));
    """)
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)

    def _get_db_override():
        c = sqlite3.connect(str(db_path), check_same_thread=False)
        c.row_factory = sqlite3.Row
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_db] = _get_db_override
    return TestClient(app, raise_server_exceptions=False)


# ── B2.1: Program Changes Partial Tests ──────────────────────────────────────

class TestProgramChangesPartial:
    """Tests for GET /partials/program-changes/{pe_number}."""

    def test_changes_partial_returns_200(self, client):
        """Changes partial returns 200 for a valid PE with budget data."""
        resp = client.get(
            "/partials/program-changes/0604131A",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_changes_partial_shows_line_items(self, client):
        """Changes partial includes line item data."""
        resp = client.get(
            "/partials/program-changes/0604131A",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "Apache AH-64 Block III" in resp.text

    def test_changes_partial_shows_summary(self, client):
        """Changes partial includes summary totals."""
        resp = client.get(
            "/partials/program-changes/0604131A",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        # FY2025 total should be 140000.0 -> "140,000.0", FY2026 -> "150,000.0"
        assert "140,000.0" in resp.text
        assert "150,000.0" in resp.text

    def test_changes_partial_new_program(self, client):
        """Changes partial labels new programs correctly."""
        resp = client.get(
            "/partials/program-changes/0603292N",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        # Template uses change-badge with "New" text for new programs
        assert "New" in resp.text

    def test_changes_partial_invalid_pe(self, client):
        """Changes partial handles invalid PE gracefully (returns 200 with empty)."""
        resp = client.get(
            "/partials/program-changes/0000000Z",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        # Should show empty state since PE has no budget lines
        assert "No funding changes found" in resp.text

    def test_changes_partial_bad_format_pe(self, client):
        """Changes partial handles bad PE format gracefully."""
        resp = client.get(
            "/partials/program-changes/INVALID",
            headers={"HX-Request": "true"},
        )
        # Should either return 200 with empty data (caught exception) or 400
        assert resp.status_code in (200, 400)


# ── B2.2: Program PDF Pages Partial Tests ────────────────────────────────────

class TestProgramPdfPagesPartial:
    """Tests for GET /partials/program-pdf-pages/{pe_number}."""

    def test_pdf_pages_partial_returns_200(self, client):
        """PDF pages partial returns 200 for PE with PDF data."""
        resp = client.get(
            "/partials/program-pdf-pages/0604131A",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_pdf_pages_partial_shows_pages(self, client):
        """PDF pages partial shows PDF page data."""
        resp = client.get(
            "/partials/program-pdf-pages/0604131A",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "army_r2.pdf" in resp.text

    def test_pdf_pages_partial_shows_total(self, client):
        """PDF pages partial includes total count."""
        resp = client.get(
            "/partials/program-pdf-pages/0604131A",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "2" in resp.text  # 2 PDF pages

    def test_pdf_pages_partial_fy_filter(self, client):
        """PDF pages partial supports fiscal year filter."""
        resp = client.get(
            "/partials/program-pdf-pages/0604131A?fy=2026",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "army_r2.pdf" in resp.text

    def test_pdf_pages_partial_limit_offset(self, client):
        """PDF pages partial supports limit and offset params."""
        resp = client.get(
            "/partials/program-pdf-pages/0604131A?limit=1&offset=0",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200

    def test_pdf_pages_partial_no_data(self, client):
        """PDF pages partial handles PE with no PDF pages gracefully."""
        resp = client.get(
            "/partials/program-pdf-pages/0603292N",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "No PDF pages" in resp.text


# ── B2.3: Sort Parameters on Program List Partial ────────────────────────────

class TestProgramListPartialSort:
    """Tests for sort_by/sort_dir parameters on /partials/program-list."""

    def test_program_list_default_sort(self, client):
        """Program list partial returns 200 with default sort."""
        resp = client.get(
            "/partials/program-list",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_program_list_sort_by_funding(self, client):
        """Program list partial accepts sort_by=funding."""
        resp = client.get(
            "/partials/program-list?sort_by=funding&sort_dir=desc",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200

    def test_program_list_sort_by_name(self, client):
        """Program list partial accepts sort_by=name."""
        resp = client.get(
            "/partials/program-list?sort_by=name&sort_dir=asc",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200

    def test_program_list_sort_by_pe_number(self, client):
        """Program list partial accepts sort_by=pe_number."""
        resp = client.get(
            "/partials/program-list?sort_by=pe_number&sort_dir=desc",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200

    def test_program_list_sort_with_filters(self, client):
        """Program list partial accepts sort params combined with filters."""
        resp = client.get(
            "/partials/program-list?sort_by=funding&sort_dir=desc&service=Army",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200


# ── B2.4: Top Changes Partial Tests ──────────────────────────────────────────

class TestTopChangesPartial:
    """Tests for GET /partials/top-changes."""

    def test_top_changes_returns_200(self, client):
        """Top changes partial returns 200."""
        resp = client.get(
            "/partials/top-changes",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_top_changes_shows_increases(self, client):
        """Top changes partial includes increase items."""
        resp = client.get(
            "/partials/top-changes",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "Top Increases" in resp.text

    def test_top_changes_shows_decreases(self, client):
        """Top changes partial includes decrease items."""
        resp = client.get(
            "/partials/top-changes",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "Top Decreases" in resp.text

    def test_top_changes_includes_pe_numbers(self, client):
        """Top changes partial includes PE numbers in the output."""
        resp = client.get(
            "/partials/top-changes",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        # At least one PE number should appear
        text = resp.text
        assert any(pe in text for pe in ["0604131A", "0603292N", "0604230F"])


# ── B2.5: PE Changes Edge Cases (API) ────────────────────────────────────────

class TestPeChangesEdgeCases:
    """Tests for get_pe_changes() edge cases and has_budget_lines flag."""

    def test_changes_has_budget_lines_true(self, client):
        """PE with budget data returns has_budget_lines=True."""
        resp = client.get("/api/v1/pe/0604131A/changes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_budget_lines"] is True

    def test_changes_has_budget_lines_false(self, client):
        """PE with no budget data returns has_budget_lines=False."""
        resp = client.get("/api/v1/pe/0601234X/changes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_budget_lines"] is False
        assert data["line_items"] == []
        assert "note" in data

    def test_changes_new_program_no_fy2025(self, client):
        """PE with no FY2025 data labels items as 'new'."""
        resp = client.get("/api/v1/pe/0603292N/changes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_budget_lines"] is True
        assert len(data["line_items"]) > 0
        # All lines should be 'new' since FY2025 total is 0
        for item in data["line_items"]:
            assert item["change_type"] == "new"

    def test_changes_increase_program(self, client):
        """PE with funding increase returns correct change_type."""
        resp = client.get("/api/v1/pe/0604131A/changes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["line_items"]) > 0
        item = data["line_items"][0]
        assert item["change_type"] == "increase"

    def test_changes_decrease_program(self, client):
        """PE with funding decrease returns correct change_type."""
        resp = client.get("/api/v1/pe/0604230F/changes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["line_items"]) > 0
        item = data["line_items"][0]
        assert item["change_type"] == "decrease"

    def test_changes_pct_change_calculation(self, client):
        """PE changes correctly calculates pct_change."""
        resp = client.get("/api/v1/pe/0604131A/changes")
        assert resp.status_code == 200
        data = resp.json()
        # (150000 - 140000) / 140000 * 100 = 7.1%
        assert data["pct_change"] is not None
        assert abs(data["pct_change"] - 7.1) < 0.2

    def test_changes_pct_change_none_for_new(self, client):
        """PE with no FY2025 data returns pct_change=None."""
        resp = client.get("/api/v1/pe/0603292N/changes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pct_change"] is None

    def test_changes_totals(self, client):
        """PE changes returns correct total_fy2025 and total_fy2026_request."""
        resp = client.get("/api/v1/pe/0604131A/changes")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_fy2025"] == 140000.0
        assert data["total_fy2026_request"] == 150000.0
        assert data["total_delta"] == 10000.0

    def test_changes_invalid_pe_format(self, client):
        """Invalid PE format returns 400."""
        resp = client.get("/api/v1/pe/INVALID/changes")
        assert resp.status_code == 400

    def test_changes_missing_tables_graceful(self, client_no_budget_lines):
        """When budget_lines table doesn't exist, changes partial handles gracefully."""
        resp = client_no_budget_lines.get(
            "/partials/program-changes/0601234X",
            headers={"HX-Request": "true"},
        )
        # Should return 200 with empty data (exception caught in the partial route)
        assert resp.status_code == 200
