"""
Tests for the database browser fix plan (plan.md).

Validates fixes for:
  - P1-2: Fiscal year GLOB filter now matches "FY YYYY" format
  - P1-3: CSS overflow on results-panel
  - P2-1: Deduplicated services reference fallback
  - P2-3: Budget_lines duplicate prevention
  - P3-2: Removed dead /glossary nav condition
  - Fiscal year dropdown includes all valid formats
  - Dashboard fiscal year filter works with "FY YYYY" format
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from api.app import create_app


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def browser_fix_client(tmp_path_factory):
    """Create a test app with data in multiple fiscal year formats."""
    tmp = tmp_path_factory.mktemp("browser_fix_test")
    db_path = tmp / "test.sqlite"

    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            exhibit_type TEXT, sheet_name TEXT,
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
        CREATE VIRTUAL TABLE pdf_pages_fts USING fts5(
            page_text, content=pdf_pages
        );

        -- Insert data with "FY YYYY" format (matches pipeline output)
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title, amount_fy2026_request, pe_number,
             amount_type)
        VALUES
            ('army_p1.xlsx', 'p5', 'FY 2026', 'Army',
             'Aircraft Procurement', 'Apache AH-64', 150000.0, '0604131A',
             'budget_authority'),
            ('navy_r1.xlsx', 'r2', 'FY 2026', 'Navy',
             'RDT&E Budget', 'F-35 Development', 250000.0, '0603292N',
             'budget_authority'),
            ('af_p1.xlsx', 'p5', 'FY 2025', 'Air Force',
             'Aircraft Procurement', 'F-22A', 100000.0, '0604800F',
             'budget_authority'),
            ('army_r2.xlsx', 'r2', 'FY 2024', 'Army',
             'RDT&E Budget', 'Stryker Upgrade', 75000.0, '0604100A',
             'budget_authority');

        INSERT INTO budget_lines_fts(rowid, account_title, line_item_title,
            budget_activity_title)
        SELECT id, account_title, line_item_title, budget_activity_title
        FROM budget_lines;
    """)
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def fy_format_client(tmp_path_factory):
    """Client with multiple fiscal year formats to test GLOB matching."""
    tmp = tmp_path_factory.mktemp("fy_format_test")
    db_path = tmp / "test.sqlite"

    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            exhibit_type TEXT, sheet_name TEXT,
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
        CREATE VIRTUAL TABLE pdf_pages_fts USING fts5(
            page_text, content=pdf_pages
        );

        -- Various fiscal year formats
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title, amount_fy2026_request, pe_number,
             amount_type)
        VALUES
            ('a.xlsx', 'p5', 'FY 2026', 'Army',
             'Procurement', 'Item A', 100.0, '0601001A', 'budget_authority'),
            ('b.xlsx', 'p5', 'FY 2025', 'Navy',
             'Procurement', 'Item B', 200.0, '0601002N', 'budget_authority'),
            ('c.xlsx', 'r2', '2024', 'Army',
             'RDT&E', 'Item C', 300.0, '0601003A', 'budget_authority'),
            ('d.xlsx', 'r2', 'FY2023', 'Air Force',
             'RDT&E', 'Item D', 400.0, '0601004F', 'budget_authority');

        INSERT INTO budget_lines_fts(rowid, account_title, line_item_title,
            budget_activity_title)
        SELECT id, account_title, line_item_title, budget_activity_title
        FROM budget_lines;
    """)
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    return TestClient(app, raise_server_exceptions=False)


# ── P1-2: Fiscal year GLOB filter tests ──────────────────────────────────────

class TestFiscalYearGlobFix:
    """The GLOB pattern must match 'FY YYYY' (with space) — the canonical format."""

    def test_index_shows_fy_space_format(self, browser_fix_client):
        """The home page should list FY 2024/2025/2026 from 'FY YYYY' data."""
        resp = browser_fix_client.get("/home")
        assert resp.status_code == 200
        # The fiscal year dropdown should contain the values
        assert "FY 2026" in resp.text
        assert "FY 2025" in resp.text

    def test_results_filter_by_fy_space_format(self, browser_fix_client):
        """Filtering by 'FY 2026' should return matching results."""
        resp = browser_fix_client.get(
            "/partials/results?fiscal_year=FY+2026",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "Apache" in resp.text or "F-35" in resp.text

    def test_all_fy_formats_appear_in_dropdown(self, fy_format_client):
        """All valid FY formats should appear: 'FY 2026', 'FY 2025', '2024', 'FY2023'."""
        resp = fy_format_client.get("/")
        assert resp.status_code == 200
        # "FY YYYY" (with space) must match
        assert "FY 2026" in resp.text
        assert "FY 2025" in resp.text
        # "YYYY" (bare 4-digit) must match
        assert "2024" in resp.text
        # "FYYYYY" (no space) must match
        assert "FY2023" in resp.text

    def test_results_for_bare_year(self, fy_format_client):
        """Filtering by bare 4-digit year '2024' should return results."""
        resp = fy_format_client.get(
            "/partials/results?fiscal_year=2024",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "Item C" in resp.text

    def test_results_for_fy_no_space(self, fy_format_client):
        """Filtering by 'FY2023' (no space) should return results."""
        resp = fy_format_client.get(
            "/partials/results?fiscal_year=FY2023",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        assert "Item D" in resp.text


# ── P1-3: Results panel overflow ──────────────────────────────────────────────

class TestResultsPanelCSS:
    """Verify the CSS file has overflow: visible on .results-panel."""

    def test_results_panel_not_overflow_hidden(self):
        css_path = Path(__file__).resolve().parent.parent.parent / "static" / "css" / "main.css"
        css = css_path.read_text()
        # Find the .results-panel block
        import re
        match = re.search(r"\.results-panel\s*\{([^}]+)\}", css)
        assert match, ".results-panel rule not found in CSS"
        block = match.group(1)
        assert "overflow: visible" in block or "overflow:visible" in block, (
            f".results-panel should have overflow: visible, got: {block.strip()}"
        )

    def test_checkbox_dropdown_high_z_index(self):
        css_path = Path(__file__).resolve().parent.parent.parent / "static" / "css" / "main.css"
        css = css_path.read_text()
        import re
        match = re.search(r"\.checkbox-select-dropdown\s*\{([^}]+)\}", css)
        assert match, ".checkbox-select-dropdown rule not found in CSS"
        block = match.group(1)
        z_match = re.search(r"z-index:\s*(\d+)", block)
        assert z_match, "z-index not found in .checkbox-select-dropdown"
        assert int(z_match.group(1)) >= 100, (
            f"z-index should be >= 100, got {z_match.group(1)}"
        )


# ── P2-1: Deduplicated services reference ────────────────────────────────────

class TestServicesDeduplication:
    """Reference endpoint should not return duplicate services."""

    def test_services_no_duplicates_with_ref_table(self):
        """Even if services_agencies has duplicates, DISTINCT prevents them."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE services_agencies (
                code TEXT, full_name TEXT, category TEXT
            );
            -- Intentional duplicates
            INSERT INTO services_agencies VALUES ('A', 'Army', 'military');
            INSERT INTO services_agencies VALUES ('A', 'Army', 'military');
            INSERT INTO services_agencies VALUES ('N', 'Navy', 'military');
        """)
        from api.routes.reference import list_services
        resp = list_services(conn)
        items = json.loads(resp.body)
        codes = [r["code"] for r in items]
        assert codes == sorted(set(codes)), f"Duplicate codes found: {codes}"
        conn.close()

    def test_services_fallback_trims_whitespace(self):
        """Fallback path should TRIM org names to avoid near-duplicates."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE budget_lines (
                id INTEGER PRIMARY KEY,
                organization_name TEXT,
                fiscal_year TEXT
            );
            INSERT INTO budget_lines VALUES (1, 'Army', 'FY 2026');
            INSERT INTO budget_lines VALUES (2, 'Army ', 'FY 2025');
            INSERT INTO budget_lines VALUES (3, ' Navy', 'FY 2026');
        """)
        from api.routes.reference import list_services
        resp = list_services(conn)
        items = json.loads(resp.body)
        codes = [r["code"] for r in items]
        # Should be exactly 2 distinct services after trim
        assert len(codes) == 2, f"Expected 2 services, got {codes}"
        conn.close()


# ── P2-3: Budget_lines duplicate prevention ──────────────────────────────────

class TestBudgetLineDeduplication:
    """Verify the deduplication logic works."""

    def test_no_duplicates_in_test_data(self, browser_fix_client):
        """Results should not contain duplicate rows."""
        resp = browser_fix_client.get(
            "/partials/results",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200
        # Count occurrences of each unique item
        text = resp.text
        assert text.count("Apache AH-64") <= 1 or "Apache AH-64" not in text


# ── P3-2: Dead /glossary condition removed ───────────────────────────────────

class TestNavGlossaryCondition:
    """The nav bar should not reference /glossary as a path condition."""

    def test_about_link_no_glossary_condition(self):
        tmpl_path = (
            Path(__file__).resolve().parent.parent.parent / "templates" / "base.html"
        )
        content = tmpl_path.read_text()
        assert '/glossary' not in content, (
            "base.html should not reference /glossary path"
        )

    def test_about_page_loads(self, browser_fix_client):
        resp = browser_fix_client.get("/about")
        assert resp.status_code == 200


# ── Dashboard fiscal year fix ─────────────────────────────────────────────────

class TestDashboardFiscalYear:
    """Dashboard should show data for FY YYYY format."""

    def test_dashboard_loads(self, browser_fix_client):
        resp = browser_fix_client.get("/dashboard")
        assert resp.status_code == 200

    def test_dashboard_with_fy_filter(self, browser_fix_client):
        resp = browser_fix_client.get("/dashboard?fiscal_year=FY+2026")
        assert resp.status_code == 200


# ── Checkbox-select JS component ─────────────────────────────────────────────

class TestCheckboxSelectComponent:
    """Verify the checkbox-select JS has the refresh API."""

    def test_refresh_method_exists(self):
        js_path = (
            Path(__file__).resolve().parent.parent.parent
            / "static" / "js" / "checkbox-select.js"
        )
        content = js_path.read_text()
        assert "_checkboxSelectRefresh" in content, (
            "checkbox-select.js should expose _checkboxSelectRefresh on wrapper"
        )
        assert "function refresh()" in content, (
            "checkbox-select.js should define a refresh() function"
        )

    def test_htmx_afterswap_handler(self):
        js_path = (
            Path(__file__).resolve().parent.parent.parent
            / "static" / "js" / "checkbox-select.js"
        )
        content = js_path.read_text()
        assert "htmx:afterSwap" in content, (
            "checkbox-select.js should handle htmx:afterSwap events"
        )


# ── App.js URL restore ───────────────────────────────────────────────────────

class TestAppJsUrlRestore:
    """Verify app.js has the checkbox-select sync in restoreFiltersFromURL."""

    def test_restore_syncs_checkbox_select(self):
        js_path = (
            Path(__file__).resolve().parent.parent.parent / "static" / "js" / "app.js"
        )
        content = js_path.read_text()
        assert "_checkboxSelectRefresh" in content, (
            "app.js should call _checkboxSelectRefresh in restoreFiltersFromURL"
        )

    def test_debounce_checks_dropdown_open(self):
        js_path = (
            Path(__file__).resolve().parent.parent.parent / "static" / "js" / "app.js"
        )
        content = js_path.read_text()
        assert "checkbox-select.open" in content, (
            "app.js debounce should check for open dropdowns"
        )
