"""
TEST-001: End-to-end frontend route tests (tests/test_frontend_routes.py)

Tests for the Jinja2 frontend routes served by api/routes/frontend.py:
    GET /                       — search + filter sidebar
    GET /charts                 — Chart.js visualisations
    GET /partials/results       — HTMX swap target (filter results)
    GET /partials/detail/{id}   — HTMX swap target (row detail)

All tests use FastAPI TestClient with the test_db fixture from conftest.py.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from api.app import create_app


# ── Shared DB fixture with enough data to exercise all routes ─────────────────

@pytest.fixture(scope="module")
def app_client(tmp_path_factory):
    """Create a test app with a pre-populated in-memory-like database."""
    tmp = tmp_path_factory.mktemp("frontend_test")
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
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title, amount_fy2026_request, pe_number)
        VALUES
            ('army_p1.xlsx', 'p1', 'FY 2026', 'Army',
             'Aircraft Procurement', 'Apache AH-64', 150000.0, '0604131A'),
            ('navy_r1.xlsx', 'r1', 'FY 2026', 'Navy',
             'RDT&E Budget', 'F-35 Development', 250000.0, '0603292N'),
            ('af_p1.xlsx', 'p1', 'FY 2025', 'Air Force',
             'Aircraft Procurement', 'F-22A', 100000.0, '0604800F');
        INSERT INTO budget_lines_fts(rowid, account_title, line_item_title,
            budget_activity_title)
        SELECT id, account_title, line_item_title, budget_activity_title
        FROM budget_lines;
    """)
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    return TestClient(app, raise_server_exceptions=False)


# ── GET / — index page ────────────────────────────────────────────────────────

class TestIndexRoute:
    def test_index_returns_200(self, app_client):
        resp = app_client.get("/")
        assert resp.status_code == 200

    def test_index_returns_html(self, app_client):
        resp = app_client.get("/")
        assert "text/html" in resp.headers.get("content-type", "")

    def test_index_contains_form(self, app_client):
        resp = app_client.get("/")
        assert "<form" in resp.text.lower() or "hx-get" in resp.text.lower()

    def test_index_with_query_param(self, app_client):
        resp = app_client.get("/?q=apache")
        assert resp.status_code == 200

    def test_index_with_service_filter(self, app_client):
        resp = app_client.get("/?service=Army")
        assert resp.status_code == 200

    def test_index_with_fiscal_year_filter(self, app_client):
        resp = app_client.get("/?fiscal_year=FY+2026")
        assert resp.status_code == 200


# ── GET /charts — charts page ─────────────────────────────────────────────────

class TestChartsRoute:
    def test_charts_returns_200(self, app_client):
        resp = app_client.get("/charts")
        assert resp.status_code == 200

    def test_charts_returns_html(self, app_client):
        resp = app_client.get("/charts")
        assert "text/html" in resp.headers.get("content-type", "")

    def test_charts_contains_canvas_or_chart(self, app_client):
        resp = app_client.get("/charts")
        # Charts page should reference Chart.js or canvas elements
        html = resp.text.lower()
        assert "chart" in html or "canvas" in html


# ── GET /partials/results — HTMX partial ──────────────────────────────────────

class TestResultsPartialRoute:
    # FIX-010: Results partial requires HX-Request header (non-HTMX requests redirect to /)
    HX = {"HX-Request": "true"}

    def test_results_partial_returns_200(self, app_client):
        resp = app_client.get("/partials/results", headers=self.HX)
        assert resp.status_code == 200

    def test_results_partial_with_query(self, app_client):
        resp = app_client.get("/partials/results?q=apache", headers=self.HX)
        assert resp.status_code == 200

    def test_results_partial_with_service_filter(self, app_client):
        resp = app_client.get("/partials/results?service=Army", headers=self.HX)
        assert resp.status_code == 200

    def test_results_partial_with_exhibit_filter(self, app_client):
        resp = app_client.get("/partials/results?exhibit_type=p1", headers=self.HX)
        assert resp.status_code == 200

    def test_results_partial_with_combined_filters(self, app_client):
        resp = app_client.get("/partials/results?service=Army&exhibit_type=p1", headers=self.HX)
        assert resp.status_code == 200

    def test_results_partial_with_fiscal_year(self, app_client):
        resp = app_client.get("/partials/results?fiscal_year=FY+2026", headers=self.HX)
        assert resp.status_code == 200

    def test_results_partial_with_sort(self, app_client):
        resp = app_client.get(
            "/partials/results?sort_by=amount_fy2026_request&sort_dir=desc",
            headers=self.HX,
        )
        assert resp.status_code == 200

    def test_results_partial_with_pagination(self, app_client):
        resp = app_client.get("/partials/results?page=1&per_page=10", headers=self.HX)
        assert resp.status_code == 200

    def test_results_partial_empty_query_returns_results(self, app_client):
        resp = app_client.get("/partials/results", headers=self.HX)
        assert resp.status_code == 200
        # Should show at least something (our test data)
        assert resp.text

    def test_results_partial_non_htmx_redirects_to_home(self, app_client):
        """FIX-010: Non-HTMX requests to partials redirect to full page."""
        resp = app_client.get("/partials/results?q=test", follow_redirects=False)
        assert resp.status_code == 302
        assert "/?q=test" in resp.headers.get("location", "")

    def test_results_partial_pushes_root_url(self, app_client):
        """FIX-010: HTMX response includes HX-Push-Url with / prefix."""
        resp = app_client.get("/partials/results?service=Army", headers=self.HX)
        push_url = resp.headers.get("hx-push-url", "")
        assert push_url.startswith("/?")
        assert "service=Army" in push_url


# ── GET /partials/detail/{id} — HTMX detail panel ────────────────────────────

class TestDetailPartialRoute:
    # FIX-010: Detail partial requires HX-Request header (non-HTMX requests redirect to /)
    HX = {"HX-Request": "true"}

    def test_detail_returns_200_for_valid_id(self, app_client):
        resp = app_client.get("/partials/detail/1", headers=self.HX)
        assert resp.status_code == 200

    def test_detail_returns_html(self, app_client):
        resp = app_client.get("/partials/detail/1", headers=self.HX)
        assert "text/html" in resp.headers.get("content-type", "")

    def test_detail_contains_row_data(self, app_client):
        resp = app_client.get("/partials/detail/1", headers=self.HX)
        # Should contain some data from our test row
        assert resp.text

    def test_detail_returns_404_for_nonexistent_id(self, app_client):
        resp = app_client.get("/partials/detail/99999", headers=self.HX)
        assert resp.status_code == 404

    def test_detail_returns_404_for_id_zero(self, app_client):
        resp = app_client.get("/partials/detail/0", headers=self.HX)
        assert resp.status_code in (404, 422)

    def test_detail_second_row(self, app_client):
        resp = app_client.get("/partials/detail/2", headers=self.HX)
        assert resp.status_code == 200

    def test_detail_non_htmx_redirects_to_home(self, app_client):
        """FIX-010: Non-HTMX requests to partials redirect to full page."""
        resp = app_client.get("/partials/detail/1", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers.get("location") == "/"


class TestBliDetailRoute:
    """/bli/{bli_key} — procurement detail page (analog of /programs/{pe})."""

    @pytest.fixture(scope="class")
    def bli_client(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("bli_test")
        db_path = tmp / "bli.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            """
            CREATE TABLE bli_index (
                bli_key TEXT PRIMARY KEY, account TEXT NOT NULL, line_item TEXT,
                display_title TEXT, organization_name TEXT, budget_type TEXT,
                budget_activity_title TEXT, appropriation_code TEXT,
                appropriation_title TEXT, fiscal_years TEXT, exhibit_types TEXT,
                row_count INTEGER
            );
            CREATE TABLE bli_tags (
                bli_key TEXT, tag TEXT, tag_source TEXT, confidence REAL
            );
            CREATE TABLE pe_index (pe_number TEXT PRIMARY KEY, display_title TEXT);
            CREATE TABLE bli_pe_map (
                bli_key TEXT, pe_number TEXT, confidence REAL,
                source_file TEXT, page_number INTEGER,
                PRIMARY KEY (bli_key, pe_number)
            );
            CREATE TABLE bli_descriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, bli_key TEXT NOT NULL,
                fiscal_year TEXT, source_file TEXT,
                page_start INTEGER, page_end INTEGER,
                section_header TEXT, description_text TEXT
            );
            INSERT INTO bli_index VALUES
                ('1506N:0577', '1506N', '0577', 'EP-3 Series Mods', 'Navy',
                 'investment', 'Combat Aircraft', 'APN',
                 'Aircraft Procurement, Navy', '["FY2024","FY2025"]', '["p1"]', 3);
            INSERT INTO bli_tags VALUES ('1506N:0577', 'aviation', 'keyword', 0.8);
            INSERT INTO pe_index VALUES ('0305206N', 'Navy ISR Program');
            INSERT INTO bli_pe_map VALUES
                ('1506N:0577', '0305206N', 0.9, 'APN.pdf', 42);
            INSERT INTO bli_descriptions
                (bli_key, fiscal_year, source_file, page_start, page_end,
                 section_header, description_text)
            VALUES ('1506N:0577', 'FY2025', 'APN.pdf', 42, 42,
                    'P-5 Justification',
                    'Modifications to the EP-3 Series aircraft provide signals intelligence upgrades.');
            """
        )
        conn.commit()
        conn.close()
        app = create_app(db_path=db_path)
        return TestClient(app, raise_server_exceptions=False)

    def test_returns_200_for_known_bli(self, bli_client):
        resp = bli_client.get("/bli/1506N:0577")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_renders_bli_title_and_pe_link(self, bli_client):
        resp = bli_client.get("/bli/1506N:0577")
        body = resp.text
        assert "EP-3 Series Mods" in body
        assert "1506N:0577" in body
        # Related PE is surfaced and links to the PE page.
        assert "0305206N" in body
        assert '/programs/0305206N' in body

    def test_renders_description_snippet(self, bli_client):
        resp = bli_client.get("/bli/1506N:0577")
        assert "signals intelligence" in resp.text

    def test_unknown_bli_returns_404(self, bli_client):
        resp = bli_client.get("/bli/BOGUS:99999")
        assert resp.status_code == 404

    def test_missing_bli_index_returns_503(self, tmp_path_factory):
        """Pre-enrichment DB: no bli_index table at all → 503, not 500."""
        tmp = tmp_path_factory.mktemp("bli_pre_enrich")
        db_path = tmp / "empty.sqlite"
        conn = sqlite3.connect(str(db_path))
        # Minimal schema so create_app + startup doesn't explode.
        conn.executescript(
            "CREATE TABLE budget_lines (id INTEGER PRIMARY KEY);"
            "CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY);"
            "CREATE TABLE ingested_files (id INTEGER PRIMARY KEY);"
        )
        conn.commit()
        conn.close()
        app = create_app(db_path=db_path)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/bli/any:thing")
        assert resp.status_code == 503
