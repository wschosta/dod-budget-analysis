"""
Tests for new GUI features: Dashboard, Program Explorer, About page,
navigation, and new API endpoints.
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
    """Create a test app with a pre-populated database including PE tables."""
    tmp = tmp_path_factory.mktemp("gui_features_test")
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
        CREATE VIRTUAL TABLE pdf_pages_fts USING fts5(
            page_text, content=pdf_pages
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

        CREATE TABLE services_agencies (
            code TEXT PRIMARY KEY, full_name TEXT
        );
        CREATE TABLE exhibit_types (
            code TEXT PRIMARY KEY, display_name TEXT
        );

        INSERT INTO services_agencies VALUES ('Army', 'U.S. Army');
        INSERT INTO services_agencies VALUES ('Navy', 'U.S. Navy');
        INSERT INTO services_agencies VALUES ('Air Force', 'U.S. Air Force');

        INSERT INTO exhibit_types VALUES ('p1', 'Procurement Summary');
        INSERT INTO exhibit_types VALUES ('r1', 'RDT&E Summary');

        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title, pe_number,
             appropriation_code, appropriation_title,
             amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request)
        VALUES
            ('army_p1.xlsx', 'p1', '2026', 'Army',
             'Aircraft Procurement', 'Apache AH-64', '0604131A',
             'PROC', 'Procurement', 120000.0, 140000.0, 150000.0),
            ('navy_r1.xlsx', 'r1', '2026', 'Navy',
             'RDT&E Budget', 'F-35 Development', '0603292N',
             'RDTE', 'RDT&E', 200000.0, 230000.0, 250000.0),
            ('af_p1.xlsx', 'p1', '2025', 'Air Force',
             'Aircraft Procurement', 'F-22A', '0604800F',
             'PROC', 'Procurement', 80000.0, 90000.0, 100000.0);

        INSERT INTO budget_lines_fts(rowid, account_title, line_item_title,
            budget_activity_title)
        SELECT id, account_title, line_item_title, budget_activity_title
        FROM budget_lines;

        INSERT INTO pe_index VALUES
            ('0604131A', 'Apache AH-64 Block III', 'Army', 'Procurement',
             '["2026"]', '["p1"]'),
            ('0603292N', 'F-35 Lightning II', 'Navy', 'RDT&E',
             '["2026"]', '["r1"]'),
            ('0604800F', 'F-22A Raptor', 'Air Force', 'Procurement',
             '["2025"]', '["p1"]');

        INSERT INTO pe_tags VALUES (NULL, '0604131A', 'aviation', 'structured', 1.0, '["army_r1.xlsx"]');
        INSERT INTO pe_tags VALUES (NULL, '0604131A', 'rotary-wing', 'keyword', 0.9, '["army_r2.pdf"]');
        INSERT INTO pe_tags VALUES (NULL, '0603292N', 'aviation', 'structured', 1.0, '["navy_r1.xlsx"]');
        INSERT INTO pe_tags VALUES (NULL, '0603292N', 'stealth', 'keyword', 0.8, '["navy_r2.pdf"]');

        INSERT INTO pe_lineage VALUES
            (NULL, '0604131A', '0603292N', 'name_match', 0.6, '2026', 'aviation context');

        INSERT INTO pe_descriptions VALUES
            (NULL, '0604131A', '2026', 'army_r2.pdf', 1, 3, 'Mission Description',
             'The Apache AH-64 Block III program continues modernization...');
    """)
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    return TestClient(app, raise_server_exceptions=False)


# ── About page ────────────────────────────────────────────────────────────────

class TestAboutPage:
    def test_about_returns_200(self, app_client):
        resp = app_client.get("/about")
        assert resp.status_code == 200

    def test_about_contains_title(self, app_client):
        resp = app_client.get("/about")
        assert "About" in resp.text
        assert "DoD Budget Explorer" in resp.text

    def test_about_has_disclaimer(self, app_client):
        resp = app_client.get("/about")
        assert "not affiliated" in resp.text.lower()


# ── Dashboard ─────────────────────────────────────────────────────────────────

class TestDashboardPage:
    def test_dashboard_returns_200(self, app_client):
        resp = app_client.get("/dashboard")
        assert resp.status_code == 200

    def test_dashboard_contains_overview(self, app_client):
        resp = app_client.get("/dashboard")
        assert "DoD Budget Overview" in resp.text

    def test_dashboard_loads_js(self, app_client):
        resp = app_client.get("/dashboard")
        assert "dashboard.js" in resp.text


class TestDashboardAPI:
    def test_summary_returns_200(self, app_client):
        resp = app_client.get("/api/v1/dashboard/summary")
        assert resp.status_code == 200

    def test_summary_has_totals(self, app_client):
        resp = app_client.get("/api/v1/dashboard/summary")
        data = resp.json()
        assert "totals" in data
        assert "total_lines" in data["totals"]
        assert data["totals"]["total_lines"] == 3

    def test_summary_has_by_service(self, app_client):
        resp = app_client.get("/api/v1/dashboard/summary")
        data = resp.json()
        assert "by_service" in data
        assert len(data["by_service"]) > 0
        assert "service" in data["by_service"][0]

    def test_summary_has_top_programs(self, app_client):
        resp = app_client.get("/api/v1/dashboard/summary")
        data = resp.json()
        assert "top_programs" in data
        assert len(data["top_programs"]) > 0

    def test_summary_has_by_appropriation(self, app_client):
        resp = app_client.get("/api/v1/dashboard/summary")
        data = resp.json()
        assert "by_appropriation" in data
        assert len(data["by_appropriation"]) > 0

    def test_summary_has_by_budget_type(self, app_client):
        resp = app_client.get("/api/v1/dashboard/summary")
        data = resp.json()
        assert "by_budget_type" in data
        assert isinstance(data["by_budget_type"], list)

    def test_summary_has_freshness(self, app_client):
        resp = app_client.get("/api/v1/dashboard/summary")
        data = resp.json()
        assert "freshness" in data
        assert isinstance(data["freshness"], dict)

    def test_summary_has_source_stats(self, app_client):
        resp = app_client.get("/api/v1/dashboard/summary")
        data = resp.json()
        assert "source_stats" in data
        assert isinstance(data["source_stats"], dict)

    def test_summary_is_cached(self, app_client):
        """Second call should use cache (both should return same data)."""
        resp1 = app_client.get("/api/v1/dashboard/summary")
        resp2 = app_client.get("/api/v1/dashboard/summary")
        assert resp1.json()["totals"] == resp2.json()["totals"]

    def test_summary_fiscal_year_filter(self, app_client):
        """fiscal_year filter restricts to matching rows only."""
        resp = app_client.get("/api/v1/dashboard/summary?fiscal_year=2026")
        assert resp.status_code == 200
        data = resp.json()
        # Test data has 2 rows with FY 2026 and 1 with FY 2025
        assert data["totals"]["total_lines"] == 2

    def test_summary_fiscal_year_no_match(self, app_client):
        """Non-existent fiscal year returns zero totals."""
        resp = app_client.get("/api/v1/dashboard/summary?fiscal_year=2099")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"]["total_lines"] == 0

    def test_summary_service_filter(self, app_client):
        """service filter restricts to matching organization rows."""
        resp = app_client.get("/api/v1/dashboard/summary?service=Army")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"]["total_lines"] == 1  # Only Army row

    def test_summary_service_and_fiscal_year_combined(self, app_client):
        """Both service and fiscal_year filters narrow results."""
        resp = app_client.get(
            "/api/v1/dashboard/summary?service=Navy&fiscal_year=2026"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"]["total_lines"] == 1  # Navy + FY2026


# ── Hierarchy endpoint ────────────────────────────────────────────────────────

class TestHierarchyEndpoint:
    def test_hierarchy_returns_200(self, app_client):
        resp = app_client.get("/api/v1/aggregations/hierarchy")
        assert resp.status_code == 200

    def test_hierarchy_has_items(self, app_client):
        resp = app_client.get("/api/v1/aggregations/hierarchy")
        data = resp.json()
        assert "items" in data
        assert len(data["items"]) > 0

    def test_hierarchy_item_structure(self, app_client):
        resp = app_client.get("/api/v1/aggregations/hierarchy")
        item = resp.json()["items"][0]
        assert "service" in item
        assert "amount" in item
        assert "prev_amount" in item
        assert "pct_of_total" in item

    def test_hierarchy_has_grand_total(self, app_client):
        resp = app_client.get("/api/v1/aggregations/hierarchy")
        data = resp.json()
        assert "grand_total" in data
        assert data["grand_total"] > 0

    def test_hierarchy_with_fiscal_year_filter(self, app_client):
        resp = app_client.get("/api/v1/aggregations/hierarchy?fiscal_year=2026")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data

    def test_hierarchy_with_service_filter(self, app_client):
        resp = app_client.get("/api/v1/aggregations/hierarchy?service=Army")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["service"] == "Army"

    def test_hierarchy_with_exhibit_type_filter(self, app_client):
        resp = app_client.get("/api/v1/aggregations/hierarchy?exhibit_type=p1")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data


# ── Navigation ────────────────────────────────────────────────────────────────

class TestNavigation:
    def test_nav_has_dashboard_link(self, app_client):
        resp = app_client.get("/")
        assert 'href="/dashboard"' in resp.text

    def test_nav_has_programs_link(self, app_client):
        resp = app_client.get("/")
        assert 'href="/programs"' in resp.text

    def test_nav_has_about_link(self, app_client):
        resp = app_client.get("/")
        assert 'href="/about"' in resp.text

    def test_nav_has_hamburger_button(self, app_client):
        resp = app_client.get("/")
        assert 'class="hamburger"' in resp.text

    def test_nav_has_treemap_cdn(self, app_client):
        resp = app_client.get("/")
        assert "chartjs-chart-treemap" in resp.text

    def test_nav_has_checkbox_select_js(self, app_client):
        resp = app_client.get("/")
        assert "checkbox-select.js" in resp.text


# ── Program Explorer ──────────────────────────────────────────────────────────

class TestProgramExplorer:
    def test_programs_returns_200(self, app_client):
        resp = app_client.get("/programs")
        assert resp.status_code == 200

    def test_programs_contains_title(self, app_client):
        resp = app_client.get("/programs")
        assert "Program Explorer" in resp.text

    def test_programs_shows_pe_cards(self, app_client):
        resp = app_client.get("/programs")
        assert "0604131A" in resp.text

    def test_program_detail_returns_200(self, app_client):
        resp = app_client.get("/programs/0604131A")
        assert resp.status_code == 200

    def test_program_detail_shows_pe_info(self, app_client):
        resp = app_client.get("/programs/0604131A")
        assert "0604131A" in resp.text
        assert "Apache" in resp.text

    def test_program_detail_shows_funding_table(self, app_client):
        resp = app_client.get("/programs/0604131A")
        assert "Funding History" in resp.text

    def test_program_detail_shows_tags(self, app_client):
        resp = app_client.get("/programs/0604131A")
        assert "aviation" in resp.text

    def test_program_detail_shows_related(self, app_client):
        resp = app_client.get("/programs/0604131A")
        assert "Related Programs" in resp.text
        assert "0603292N" in resp.text

    def test_program_detail_loads_js(self, app_client):
        resp = app_client.get("/programs/0604131A")
        assert "program-detail.js" in resp.text

    def test_program_detail_nonexistent_returns_404(self, app_client):
        resp = app_client.get("/programs/NONEXIST")
        assert resp.status_code == 404

    def test_program_list_partial(self, app_client):
        resp = app_client.get("/partials/program-list")
        assert resp.status_code == 200

    def test_program_list_partial_with_filter(self, app_client):
        resp = app_client.get("/partials/program-list?service=Army")
        assert resp.status_code == 200

    def test_program_descriptions_partial(self, app_client):
        resp = app_client.get("/partials/program-descriptions/0604131A")
        assert resp.status_code == 200
        assert "Apache" in resp.text or "Mission Description" in resp.text

    def test_program_descriptions_empty_pe(self, app_client):
        resp = app_client.get("/partials/program-descriptions/0604800F")
        assert resp.status_code == 200
        assert "No narrative descriptions" in resp.text


# ── Search page enhancements ──────────────────────────────────────────────────

class TestSearchEnhancements:
    def test_search_has_save_button(self, app_client):
        resp = app_client.get("/")
        assert "Save" in resp.text

    def test_search_has_saved_searches_container(self, app_client):
        resp = app_client.get("/")
        assert "saved-searches-list" in resp.text

    def test_search_has_autocomplete_js(self, app_client):
        resp = app_client.get("/")
        assert "autocomplete" in resp.text.lower() or "app.js" in resp.text
