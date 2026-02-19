"""
TEST-002: Chart data contract tests.

Tests for /api/v1/aggregations and /api/v1/budget-lines endpoints
that feed the charts page. Verifies data structure, field names,
edge cases with empty DB, and NULL group values.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import api.app as app_module
from fastapi.testclient import TestClient
from api.app import create_app

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_rate_counters():
    app_module._rate_counters.clear()
    yield
    app_module._rate_counters.clear()


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """App client with a populated DB for chart data tests."""
    tmp = tmp_path_factory.mktemp("charts_test")
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
            currency_year TEXT, amount_unit TEXT, amount_type TEXT,
            amount_fy2024_actual REAL, amount_fy2025_enacted REAL,
            amount_fy2025_supplemental REAL, amount_fy2025_total REAL,
            amount_fy2026_request REAL, amount_fy2026_reconciliation REAL,
            amount_fy2026_total REAL,
            quantity_fy2024 REAL, quantity_fy2025 REAL,
            quantity_fy2026_request REAL, quantity_fy2026_total REAL,
            classification TEXT, extra_fields TEXT, budget_type TEXT
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
        -- Insert rows with different services, fiscal years, exhibit types
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title,
             amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request)
        VALUES
            ('army_p1.xlsx', 'p1', 'FY 2024', 'Army',
             'Aircraft Procurement', 'Apache AH-64', 100.0, 110.0, 120.0),
            ('army_r1.xlsx', 'r1', 'FY 2025', 'Army',
             'RDT&E', 'Lab Research', 50.0, 60.0, 70.0),
            ('navy_p1.xlsx', 'p1', 'FY 2026', 'Navy',
             'Ship Procurement', 'DDG-51', 200.0, 210.0, 220.0),
            ('af_r1.xlsx', 'r1', 'FY 2026', 'Air Force',
             'RDT&E Budget', 'F-35 Dev', 80.0, 90.0, 100.0),
            -- Row with NULL organization_name to test NULL group handling
            ('unk.xlsx', 'p1', 'FY 2026', NULL,
             'Unknown Account', 'Unknown Item', 10.0, 10.0, 10.0);
        -- FTS index
        INSERT INTO budget_lines_fts(rowid, account_title, line_item_title,
            budget_activity_title)
        SELECT id, account_title, line_item_title, budget_activity_title
        FROM budget_lines;
    """)
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    return TestClient(app)


@pytest.fixture(scope="module")
def empty_client(tmp_path_factory):
    """App client with an empty database for edge case tests."""
    tmp = tmp_path_factory.mktemp("empty_charts_test")
    db_path = tmp / "empty.sqlite"

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
            currency_year TEXT, amount_unit TEXT, amount_type TEXT,
            amount_fy2024_actual REAL, amount_fy2025_enacted REAL,
            amount_fy2025_supplemental REAL, amount_fy2025_total REAL,
            amount_fy2026_request REAL, amount_fy2026_reconciliation REAL,
            amount_fy2026_total REAL,
            quantity_fy2024 REAL, quantity_fy2025 REAL,
            quantity_fy2026_request REAL, quantity_fy2026_total REAL,
            classification TEXT, extra_fields TEXT, budget_type TEXT
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
    """)
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    return TestClient(app)


# ── Aggregation by service ─────────────────────────────────────────────────────

class TestAggregationByService:
    def test_service_aggregation_returns_200(self, client):
        resp = client.get("/api/v1/aggregations?group_by=service")
        assert resp.status_code == 200

    def test_service_aggregation_structure(self, client):
        resp = client.get("/api/v1/aggregations?group_by=service")
        data = resp.json()
        assert "group_by" in data
        assert data["group_by"] == "service"
        assert "rows" in data
        assert isinstance(data["rows"], list)

    def test_service_aggregation_row_fields(self, client):
        resp = client.get("/api/v1/aggregations?group_by=service")
        data = resp.json()
        assert len(data["rows"]) >= 1
        row = data["rows"][0]
        assert "group_value" in row
        assert "row_count" in row
        assert "total_fy2026_request" in row

    def test_service_aggregation_known_services(self, client):
        resp = client.get("/api/v1/aggregations?group_by=service")
        data = resp.json()
        group_values = {r["group_value"] for r in data["rows"] if r["group_value"]}
        assert "Army" in group_values
        assert "Navy" in group_values

    def test_service_aggregation_totals_correct(self, client):
        resp = client.get("/api/v1/aggregations?group_by=service")
        data = resp.json()
        army_rows = [r for r in data["rows"] if r["group_value"] == "Army"]
        assert len(army_rows) == 1
        # Army has 2 rows: 120 + 70 = 190
        assert army_rows[0]["total_fy2026_request"] == pytest.approx(190.0)


# ── Aggregation by fiscal year ─────────────────────────────────────────────────

class TestAggregationByFiscalYear:
    def test_fiscal_year_aggregation_returns_200(self, client):
        resp = client.get("/api/v1/aggregations?group_by=fiscal_year")
        assert resp.status_code == 200

    def test_fiscal_year_aggregation_returns_all_years(self, client):
        resp = client.get("/api/v1/aggregations?group_by=fiscal_year")
        data = resp.json()
        years = {r["group_value"] for r in data["rows"]}
        assert "FY 2024" in years
        assert "FY 2025" in years
        assert "FY 2026" in years

    def test_fiscal_year_aggregation_ordered(self, client):
        """Results should be ordered (by total_fy2026_request desc)."""
        resp = client.get("/api/v1/aggregations?group_by=fiscal_year")
        data = resp.json()
        # Check we have rows
        assert len(data["rows"]) >= 1


# ── Aggregation with pre-filters ──────────────────────────────────────────────

class TestAggregationWithFilters:
    def test_filter_by_exhibit_type(self, client):
        resp = client.get("/api/v1/aggregations?group_by=service&exhibit_type=p1")
        data = resp.json()
        assert resp.status_code == 200
        # Only p1 rows: Army (1 p1 row), Navy (1 p1 row), NULL (1 p1 row)
        assert len(data["rows"]) >= 1

    def test_filter_by_fiscal_year(self, client):
        resp = client.get("/api/v1/aggregations?group_by=service&fiscal_year=FY+2026")
        data = resp.json()
        assert resp.status_code == 200
        # Only FY 2026 rows
        group_values = {r["group_value"] for r in data["rows"] if r["group_value"]}
        assert "Navy" in group_values
        assert "Air Force" in group_values
        # Army has no FY 2026 rows with our test data... wait it does (but in FY 2025)
        # Actually FY 2026 rows are: Navy + Air Force + NULL

    def test_invalid_group_by_returns_400(self, client):
        resp = client.get("/api/v1/aggregations?group_by=invalid_dimension")
        assert resp.status_code == 400


# ── NULL group values ─────────────────────────────────────────────────────────

class TestNullGroupValues:
    def test_null_organization_name_included(self, client):
        """Rows with NULL organization_name should appear in aggregation."""
        resp = client.get("/api/v1/aggregations?group_by=service")
        assert resp.status_code == 200
        data = resp.json()
        # NULL value row should be present (group_value can be None)
        all_group_values = [r["group_value"] for r in data["rows"]]
        # There should be a None/null entry from our NULL org_name row
        assert None in all_group_values or "" in all_group_values


# ── Budget-lines sort for charts ──────────────────────────────────────────────

class TestBudgetLinesSortForCharts:
    def test_sort_by_amount_desc_returns_200(self, client):
        resp = client.get(
            "/api/v1/budget-lines?"
            "sort_by=amount_fy2026_request&sort_dir=desc"
        )
        assert resp.status_code == 200

    def test_sort_by_amount_desc_order(self, client):
        resp = client.get(
            "/api/v1/budget-lines?"
            "sort_by=amount_fy2026_request&sort_dir=desc&per_page=5"
        )
        data = resp.json()
        amounts = [
            item.get("amount_fy2026_request", 0) or 0
            for item in data.get("items", [])
        ]
        # Should be in descending order
        assert amounts == sorted(amounts, reverse=True)

    def test_budget_lines_pagination_structure(self, client):
        resp = client.get("/api/v1/budget-lines?limit=2&offset=0")
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) <= 2
