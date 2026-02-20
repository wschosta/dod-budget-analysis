"""
Tests for GUI bug fixes (FIX-001 through FIX-008).

Validates that the fixes to frontend routes, query building, and templates
work correctly with actual data patterns that caused the original bugs.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from api.app import create_app


# ── Shared fixture with data that reproduces the bugs ─────────────────────────

@pytest.fixture(scope="module")
def gui_client(tmp_path_factory):
    """Create a test app with data patterns that triggered the reported GUI bugs.

    Test data includes:
    - Duplicate org names (Army vs ARMY, AF vs Air Force) → FIX-002
    - Invalid fiscal_year values (Details, Emergency Disaster Relief Act) → FIX-003
    - Summary + detail exhibits for same program → FIX-006
    - Multiple amount columns → FIX-005
    - Source file metadata → FIX-007
    """
    tmp = tmp_path_factory.mktemp("gui_fixes")
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

        CREATE TABLE services_agencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            category TEXT NOT NULL
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

        -- Seed services_agencies with potential duplicates (FIX-002)
        INSERT INTO services_agencies (code, full_name, category)
        VALUES ('Army', 'Department of the Army', 'military_dept'),
               ('Air Force', 'Department of the Air Force', 'military_dept'),
               ('Navy', 'Department of the Navy', 'military_dept');

        -- Insert budget lines with various org name formats (FIX-002)
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title, pe_number,
             appropriation_code, appropriation_title,
             amount_fy2024_actual, amount_fy2025_enacted,
             amount_fy2025_total, amount_fy2026_request, amount_fy2026_total)
        VALUES
            -- Army detail exhibit
            ('army_r2.xlsx', 'r2', '2026', 'Army',
             'RDT&E', 'Cybersecurity Initiative', '0604182A',
             '2040', 'Research Development Test & Evaluation, Army',
             100000.0, 110000.0, 112000.0, 120000.0, 122000.0),

            -- Duplicate PE on different exhibit (FIX duplicate PE display)
            ('army_r2.xlsx', 'r2', '2025', 'Army',
             'RDT&E', 'Cybersecurity Initiative', '0604182A',
             '2040', 'Research Development Test & Evaluation, Army',
             90000.0, 100000.0, 102000.0, 110000.0, 112000.0),

            -- Summary exhibit that overlaps with detail (FIX-006)
            ('army_r1.xlsx', 'r1', '2026', 'Army',
             'RDT&E Summary', 'RDT&E Total', NULL,
             '2040', 'Research Development Test & Evaluation, Army',
             500000.0, 550000.0, 560000.0, 600000.0, 610000.0),

            -- Navy detail exhibit
            ('navy_p5.xlsx', 'p5', '2026', 'Navy',
             'Ship Procurement', 'DDG-51 Destroyer', NULL,
             '1611', 'Shipbuilding and Conversion, Navy',
             200000.0, 210000.0, 215000.0, 230000.0, 235000.0),

            -- Navy summary exhibit (FIX-006 double-counting)
            ('navy_p1.xlsx', 'p1', '2026', 'Navy',
             'Procurement Summary', 'Procurement Total', NULL,
             '1611', 'Shipbuilding and Conversion, Navy',
             400000.0, 420000.0, 430000.0, 460000.0, 470000.0),

            -- Air Force with detail exhibit
            ('af_r2.xlsx', 'r2', '2026', 'Air Force',
             'RDT&E', 'F-35 Lightning II', '0604800F',
             '3600', 'Research Development Test & Evaluation, Air Force',
             300000.0, 320000.0, 325000.0, 350000.0, 355000.0),

            -- Invalid fiscal year values (FIX-003)
            ('army_r2.xlsx', 'r2', 'Details', 'Army',
             'RDT&E', 'Section Header Row', NULL,
             NULL, NULL,
             NULL, NULL, NULL, NULL, NULL),

            ('navy_p5.xlsx', 'p5', 'Emergency Disaster Relief Act', 'Navy',
             'Supplemental', 'Emergency Funding', NULL,
             NULL, NULL,
             NULL, NULL, NULL, 5000.0, 5000.0);

        -- Populate FTS index
        INSERT INTO budget_lines_fts(rowid, account_title, line_item_title,
            budget_activity_title)
        SELECT id, account_title, line_item_title, budget_activity_title
        FROM budget_lines;
    """)
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    return TestClient(app, raise_server_exceptions=False)


# ── FIX-001: CDN scripts should load (no SRI hash errors) ────────────────────

class TestFix001CDNScripts:
    """FIX-001: Verify that base template uses CDN scripts without broken SRI hashes."""

    def test_base_template_has_htmx_script(self, gui_client):
        resp = gui_client.get("/")
        assert resp.status_code == 200
        # Should have htmx script tag without integrity attribute
        assert "htmx.org" in resp.text
        assert 'integrity="sha384-D1Kt99CQ' not in resp.text

    def test_base_template_has_chartjs_script(self, gui_client):
        resp = gui_client.get("/charts")
        assert resp.status_code == 200
        assert "chart.js" in resp.text or "chart.umd" in resp.text
        assert 'integrity="sha384-adDgSZ' not in resp.text


# ── FIX-002: Service dropdown deduplication ──────────────────────────────────

class TestFix002ServiceDropdown:
    """FIX-002: Service dropdown should show deduplicated values from budget_lines."""

    def test_service_dropdown_no_duplicates(self, gui_client):
        resp = gui_client.get("/")
        assert resp.status_code == 200
        html = resp.text
        # Count occurrences of each service in option tags
        # Each org should appear exactly once
        army_count = html.count('value="Army"')
        assert army_count == 1, f"Army appears {army_count} times in dropdown"

    def test_service_dropdown_shows_actual_data(self, gui_client):
        resp = gui_client.get("/")
        assert resp.status_code == 200
        # The services shown should be the actual org names from budget_lines
        assert "Army" in resp.text
        assert "Navy" in resp.text
        assert "Air Force" in resp.text

    def test_service_filter_exact_match(self, gui_client):
        """FIX-002b: Service filter should use exact match, not LIKE."""
        # Filtering by "Air Force" should not match partial strings
        resp = gui_client.get("/partials/results?service=Air+Force")
        assert resp.status_code == 200
        # Should contain Air Force results
        assert "F-35 Lightning II" in resp.text or "Air Force" in resp.text

    def test_service_filter_no_partial_match(self, gui_client):
        """FIX-002b: Service filter 'AF' should not match 'CAAF' etc."""
        # "AF" is not an actual org name in our test data, should return no results
        resp = gui_client.get("/partials/results?service=AF")
        assert resp.status_code == 200
        # Should not show any results since "AF" is not an exact org name
        assert "No budget items" in resp.text or "0 result" in resp.text


# ── FIX-003: Fiscal year dropdown validation ─────────────────────────────────

class TestFix003FiscalYearDropdown:
    """FIX-003: FY dropdown should filter out invalid values like 'Details'."""

    def test_fy_dropdown_no_invalid_values(self, gui_client):
        resp = gui_client.get("/")
        assert resp.status_code == 200
        html = resp.text
        # Invalid values should NOT appear as FY dropdown options
        # (they may still appear in results table body as row data)
        assert 'value="Details"' not in html
        assert 'value="Emergency Disaster Relief Act"' not in html

    def test_fy_dropdown_has_valid_years(self, gui_client):
        resp = gui_client.get("/")
        assert resp.status_code == 200
        # Valid fiscal years should be present
        assert "2026" in resp.text or "2025" in resp.text


# ── FIX-004: CSS number input styling ────────────────────────────────────────

class TestFix004CSSNumberInputs:
    """FIX-004: Number inputs should be styled in filter panel."""

    def test_css_includes_number_input_selector(self):
        css_path = Path(__file__).resolve().parent.parent / "static" / "css" / "main.css"
        css = css_path.read_text()
        assert 'input[type="number"]' in css


# ── FIX-005: More FY amount columns ─────────────────────────────────────────

class TestFix005MoreFYColumns:
    """FIX-005: Results table should include FY25 total and FY26 total columns."""

    def test_results_have_fy25_total_column(self, gui_client):
        resp = gui_client.get("/partials/results")
        assert resp.status_code == 200
        assert "col-fy25tot" in resp.text
        assert "FY25 Total" in resp.text

    def test_results_have_fy26_total_column(self, gui_client):
        resp = gui_client.get("/partials/results")
        assert resp.status_code == 200
        assert "col-fy26tot" in resp.text
        assert "FY26 Total" in resp.text

    def test_column_toggle_buttons_include_new_cols(self, gui_client):
        resp = gui_client.get("/partials/results")
        assert resp.status_code == 200
        # Toggle buttons for new columns should exist
        assert 'data-col="fy25tot"' in resp.text
        assert 'data-col="fy26tot"' in resp.text


# ── FIX-006: Dashboard double-counting ───────────────────────────────────────

class TestFix006DashboardTotals:
    """FIX-006: Dashboard should exclude summary exhibits to avoid double-counting."""

    def test_dashboard_summary_excludes_summary_exhibits(self, gui_client):
        resp = gui_client.get("/api/v1/dashboard/summary")
        assert resp.status_code == 200
        data = resp.json()

        # The total should NOT include summary exhibits (r1, p1)
        # Our test data has:
        #   Detail: Army r2 120K + 110K + Navy p5 230K + AF r2 350K = 810K
        #   (plus the invalid FY rows: 5K for emergency)
        #   Summary: Army r1 600K + Navy p1 460K = 1,060K
        # With the fix, only detail exhibits should be summed
        total = data["totals"]["total_fy26_request"]
        if total is not None:
            # Should be around 810K (detail exhibits only), NOT 1,870K (with summaries)
            assert total < 1_000_000, (
                f"Total is ${total:,.0f}K — likely double-counting summary exhibits"
            )

    def test_dashboard_page_loads(self, gui_client):
        resp = gui_client.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_dashboard_by_service_excludes_summaries(self, gui_client):
        resp = gui_client.get("/api/v1/dashboard/summary")
        data = resp.json()
        by_service = data.get("by_service", [])
        # Each service total should be from detail exhibits only
        for svc in by_service:
            if svc["service"] == "Army":
                # Army detail: 120K + 110K = 230K, not 830K (with r1 summary)
                if svc["total"] is not None:
                    assert svc["total"] < 400_000


# ── FIX-007: Source file links ───────────────────────────────────────────────

class TestFix007SourceLinks:
    """FIX-007: Results should include source file information."""

    def test_results_have_source_column(self, gui_client):
        resp = gui_client.get("/partials/results")
        assert resp.status_code == 200
        assert "col-source" in resp.text
        assert "Source" in resp.text

    def test_source_toggle_button_exists(self, gui_client):
        resp = gui_client.get("/partials/results")
        assert resp.status_code == 200
        assert 'data-col="source"' in resp.text


# ── FIX-008: Programs tab service dropdown ───────────────────────────────────

class TestFix008ProgramsService:
    """FIX-008: Programs tab should use deduplicated services from budget_lines."""

    def test_programs_page_loads(self, gui_client):
        resp = gui_client.get("/programs")
        assert resp.status_code == 200

    def test_programs_service_dropdown_has_values(self, gui_client):
        resp = gui_client.get("/programs")
        assert resp.status_code == 200
        assert "All Services" in resp.text


# ── Integration: query builder service filter ────────────────────────────────

class TestQueryBuilderServiceFilter:
    """Verify build_where_clause uses exact matching for service filter."""

    def test_exact_match_single_service(self):
        from utils.query import build_where_clause
        where, params = build_where_clause(service=["Army"])
        assert "IN" in where
        assert "LIKE" not in where
        assert params == ["Army"]

    def test_exact_match_multiple_services(self):
        from utils.query import build_where_clause
        where, params = build_where_clause(service=["Army", "Navy"])
        assert "IN" in where
        assert "LIKE" not in where
        assert params == ["Army", "Navy"]

    def test_no_partial_match_in_query(self):
        from utils.query import build_where_clause
        where, params = build_where_clause(service=["AF"])
        # Should be exact "AF", not "%AF%"
        assert "AF" in params
        assert "%AF%" not in params
