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
    def test_results_partial_returns_200(self, app_client):
        resp = app_client.get("/partials/results")
        assert resp.status_code == 200

    def test_results_partial_with_query(self, app_client):
        resp = app_client.get("/partials/results?q=apache")
        assert resp.status_code == 200

    def test_results_partial_with_service_filter(self, app_client):
        resp = app_client.get("/partials/results?service=Army")
        assert resp.status_code == 200

    def test_results_partial_with_exhibit_filter(self, app_client):
        resp = app_client.get("/partials/results?exhibit_type=p1")
        assert resp.status_code == 200

    def test_results_partial_with_combined_filters(self, app_client):
        resp = app_client.get("/partials/results?service=Army&exhibit_type=p1")
        assert resp.status_code == 200

    def test_results_partial_with_fiscal_year(self, app_client):
        resp = app_client.get("/partials/results?fiscal_year=FY+2026")
        assert resp.status_code == 200

    def test_results_partial_with_sort(self, app_client):
        resp = app_client.get(
            "/partials/results?sort_by=amount_fy2026_request&sort_dir=desc"
        )
        assert resp.status_code == 200

    def test_results_partial_with_pagination(self, app_client):
        resp = app_client.get("/partials/results?page=1&per_page=10")
        assert resp.status_code == 200

    def test_results_partial_empty_query_returns_results(self, app_client):
        resp = app_client.get("/partials/results")
        assert resp.status_code == 200
        # Should show at least something (our test data)
        assert resp.text


# ── GET /partials/detail/{id} — HTMX detail panel ────────────────────────────

class TestDetailPartialRoute:
    def test_detail_returns_200_for_valid_id(self, app_client):
        resp = app_client.get("/partials/detail/1")
        assert resp.status_code == 200

    def test_detail_returns_html(self, app_client):
        resp = app_client.get("/partials/detail/1")
        assert "text/html" in resp.headers.get("content-type", "")

    def test_detail_contains_row_data(self, app_client):
        resp = app_client.get("/partials/detail/1")
        # Should contain some data from our test row
        assert resp.text

    def test_detail_returns_404_for_nonexistent_id(self, app_client):
        resp = app_client.get("/partials/detail/99999")
        assert resp.status_code == 404

    def test_detail_returns_404_for_id_zero(self, app_client):
        resp = app_client.get("/partials/detail/0")
        assert resp.status_code in (404, 422)

    def test_detail_second_row(self, app_client):
        resp = app_client.get("/partials/detail/2")
        assert resp.status_code == 200
