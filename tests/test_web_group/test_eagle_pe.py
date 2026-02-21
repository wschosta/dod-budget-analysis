"""
Tests for EAGLE PE route changes:
  EAGLE-3: Project-level detail in PE routes (project_descriptions integration)
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from api.app import create_app


@pytest.fixture(scope="module")
def app_client(tmp_path_factory):
    """Create a test app with project_descriptions table for EAGLE-3 tests."""
    tmp = tmp_path_factory.mktemp("eagle_pe_test")
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
            page_text TEXT, has_tables INTEGER, table_data TEXT
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
            exhibit_types TEXT
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

        -- HAWK-1: Project-level descriptions table
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

        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title, pe_number,
             appropriation_code, appropriation_title,
             amount_fy2024_actual, amount_fy2025_enacted,
             amount_fy2026_request)
        VALUES
            ('army_r2.xlsx', 'r2', '2026', 'Army',
             'RDT&E Budget', 'Apache AH-64 Block III', '0604131A',
             'RDTE', 'RDT&E', 120000.0, 140000.0, 150000.0),
            ('navy_r2.xlsx', 'r2', '2026', 'Navy',
             'RDT&E Budget', 'F-35 Development', '0603292N',
             'RDTE', 'RDT&E', 200000.0, 230000.0, 250000.0);

        INSERT INTO budget_lines_fts(rowid, account_title, line_item_title,
            budget_activity_title)
        SELECT id, account_title, line_item_title, budget_activity_title
        FROM budget_lines;

        INSERT INTO pe_index VALUES
            ('0604131A', 'Apache AH-64 Block III', 'Army', 'RDT&E',
             '["2026"]', '["r2"]'),
            ('0603292N', 'F-35 Lightning II', 'Navy', 'RDT&E',
             '["2026"]', '["r2"]');

        INSERT INTO pe_tags VALUES
            (NULL, '0604131A', 'aviation', 'structured', 1.0, '["army_r1.xlsx"]');
        INSERT INTO pe_tags VALUES
            (NULL, '0603292N', 'aviation', 'structured', 1.0, '["navy_r1.xlsx"]');

        INSERT INTO pe_lineage VALUES
            (NULL, '0604131A', '0603292N', 'name_match', 0.6, '2026', 'aviation');

        INSERT INTO pe_descriptions VALUES
            (NULL, '0604131A', '2026', 'army_r2.pdf', 1, 3, 'Mission Description',
             'The Apache AH-64 Block III program...');

        -- EAGLE-3: Project-level description data
        INSERT INTO project_descriptions
            (pe_number, project_number, project_title, fiscal_year,
             section_header, description_text, source_file)
        VALUES
            ('0604131A', '1234', 'Advanced Targeting System', '2025',
             'Accomplishments', 'Completed integration testing for targeting pod.',
             'army_r2.pdf'),
            ('0604131A', '1234', 'Advanced Targeting System', '2026',
             'Plans', 'Begin operational testing of targeting pod upgrade.',
             'army_r2.pdf'),
            ('0604131A', '5678', 'Sensor Fusion Package', '2026',
             'Plans', 'Develop next-gen sensor fusion for Apache fleet.',
             'army_r2.pdf'),
            -- PE-level fallback (no project number)
            ('0604131A', NULL, NULL, '2026',
             'Mission Description', 'Overall PE-level description for Apache.',
             'army_r2.pdf');
    """)
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def app_client_no_projects(tmp_path_factory):
    """Create a test app WITHOUT project_descriptions table."""
    tmp = tmp_path_factory.mktemp("eagle_pe_no_projects_test")
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
            page_text TEXT, has_tables INTEGER, table_data TEXT
        );
        CREATE TABLE ingested_files (
            id INTEGER PRIMARY KEY, file_path TEXT, file_type TEXT,
            row_count INTEGER, ingested_at TEXT, status TEXT
        );
        CREATE VIRTUAL TABLE budget_lines_fts USING fts5(
            account_title, line_item_title, budget_activity_title,
            content=budget_lines
        );

        CREATE TABLE pe_index (
            pe_number TEXT PRIMARY KEY,
            display_title TEXT,
            organization_name TEXT,
            budget_type TEXT,
            fiscal_years TEXT,
            exhibit_types TEXT
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
        CREATE TABLE pdf_pe_numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT, pdf_page_id INTEGER,
            page_number INTEGER, source_file TEXT, fiscal_year TEXT
        );

        CREATE TABLE services_agencies (
            code TEXT PRIMARY KEY, full_name TEXT
        );

        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title, pe_number,
             amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request)
        VALUES
            ('army_r2.xlsx', 'r2', '2026', 'Army',
             'RDT&E Budget', 'Apache AH-64', '0604131A',
             120000.0, 140000.0, 150000.0);

        INSERT INTO budget_lines_fts(rowid, account_title, line_item_title,
            budget_activity_title)
        SELECT id, account_title, line_item_title, budget_activity_title
        FROM budget_lines;

        INSERT INTO pe_index VALUES
            ('0604131A', 'Apache AH-64 Block III', 'Army', 'RDT&E',
             '["2026"]', '["r2"]');
        INSERT INTO pe_tags VALUES
            (NULL, '0604131A', 'aviation', 'structured', 1.0, NULL);
        INSERT INTO pe_descriptions VALUES
            (NULL, '0604131A', '2026', 'army_r2.pdf', 1, 3, 'Mission',
             'Apache program description');
    """)
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    return TestClient(app, raise_server_exceptions=False)


# ── EAGLE-3: Project-Level Detail Tests ─────────────────────────────────────

class TestProjectLevelDetail:
    def test_pe_detail_includes_projects(self, app_client):
        """PE detail endpoint includes project-level data."""
        resp = app_client.get("/api/v1/pe/0604131A")
        assert resp.status_code == 200
        data = resp.json()
        assert "projects" in data
        assert "has_project_data" in data
        assert data["has_project_data"] is True

    def test_pe_detail_project_structure(self, app_client):
        """Projects are grouped by project_number with nested descriptions."""
        resp = app_client.get("/api/v1/pe/0604131A")
        data = resp.json()
        projects = data["projects"]
        assert len(projects) >= 2  # project 1234, 5678, and PE-level (NULL)

        # Find project 1234
        proj_1234 = [p for p in projects if p["project_number"] == "1234"]
        assert len(proj_1234) == 1
        proj = proj_1234[0]
        assert proj["project_title"] == "Advanced Targeting System"
        assert len(proj["descriptions"]) == 2  # FY2025 + FY2026

    def test_pe_detail_project_descriptions_have_fy(self, app_client):
        """Each description has fiscal_year, header, and text."""
        resp = app_client.get("/api/v1/pe/0604131A")
        data = resp.json()
        projects = data["projects"]
        proj_1234 = [p for p in projects if p["project_number"] == "1234"][0]
        for desc in proj_1234["descriptions"]:
            assert "fiscal_year" in desc
            assert "header" in desc
            assert "text" in desc

    def test_pe_detail_pe_level_fallback(self, app_client):
        """PE-level descriptions (NULL project_number) are included."""
        resp = app_client.get("/api/v1/pe/0604131A")
        data = resp.json()
        projects = data["projects"]
        pe_level = [p for p in projects if p["project_number"] is None]
        assert len(pe_level) == 1
        assert "Mission Description" in pe_level[0]["descriptions"][0]["header"]

    def test_pe_detail_summary_includes_project_count(self, app_client):
        """Summary stats include project_count."""
        resp = app_client.get("/api/v1/pe/0604131A")
        data = resp.json()
        assert "project_count" in data["summary"]
        assert data["summary"]["project_count"] >= 2

    def test_pe_without_projects_returns_empty(self, app_client):
        """PE with no project data returns empty projects list."""
        resp = app_client.get("/api/v1/pe/0603292N")
        assert resp.status_code == 200
        data = resp.json()
        assert data["projects"] == []
        assert data["has_project_data"] is False

    def test_pe_detail_without_project_table(self, app_client_no_projects):
        """PE detail works when project_descriptions table doesn't exist."""
        resp = app_client_no_projects.get("/api/v1/pe/0604131A")
        assert resp.status_code == 200
        data = resp.json()
        assert data["projects"] == []
        assert data["has_project_data"] is False

    def test_program_detail_page_has_projects(self, app_client):
        """Frontend program detail page includes project data via pe_data."""
        resp = app_client.get("/programs/0604131A")
        assert resp.status_code == 200

    def test_pe_404_for_invalid_format(self, app_client):
        """Invalid PE format returns 400."""
        resp = app_client.get("/api/v1/pe/INVALID")
        assert resp.status_code == 400

    def test_pe_404_for_missing_pe(self, app_client):
        """Non-existent PE returns 404."""
        resp = app_client.get("/api/v1/pe/0000000Z")
        assert resp.status_code == 404
