"""
Tests for API response caching headers (TIGER-009).
"""
import sqlite3
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Stub optional dependencies
for _mod in ("pdfplumber", "openpyxl", "pandas"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    """TestClient with a temporary database containing reference tables."""
    db = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT, exhibit_type TEXT, fiscal_year TEXT,
            account TEXT, account_title TEXT, organization TEXT,
            organization_name TEXT, budget_activity_title TEXT,
            line_item TEXT, line_item_title TEXT,
            amount_fy2024_actual REAL,
            amount_fy2025_enacted REAL,
            amount_fy2026_request REAL,
            amount_fy2026_total REAL,
            amount_type TEXT, pe_number TEXT,
            appropriation_code TEXT, sheet_name TEXT,
            sub_activity_title TEXT, budget_activity TEXT,
            classification TEXT, sub_activity TEXT,
            amount_fy2025_supplemental REAL,
            amount_fy2025_total REAL,
            amount_fy2026_reconciliation REAL,
            quantity_fy2024 REAL, quantity_fy2025 REAL,
            quantity_fy2026_request REAL, quantity_fy2026_total REAL,
            extra_fields TEXT, currency_year TEXT,
            appropriation_title TEXT, amount_unit TEXT, budget_type TEXT
        );
        CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY, source_file TEXT,
            source_category TEXT, page_number INTEGER, page_text TEXT,
            has_tables INTEGER DEFAULT 0, table_data TEXT);
        CREATE TABLE ingested_files (file_path TEXT PRIMARY KEY, file_type TEXT,
            file_size INTEGER, file_modified REAL, ingested_at TEXT,
            row_count INTEGER, status TEXT);

        CREATE TABLE services_agencies (
            id INTEGER PRIMARY KEY, code TEXT UNIQUE, full_name TEXT, category TEXT
        );
        INSERT INTO services_agencies (code, full_name, category)
        VALUES ('Army', 'Department of the Army', 'Military Department');

        CREATE TABLE exhibit_types (
            id INTEGER PRIMARY KEY, code TEXT UNIQUE, display_name TEXT,
            exhibit_class TEXT, description TEXT
        );
        INSERT INTO exhibit_types (code, display_name, exhibit_class)
        VALUES ('p1', 'Procurement (P-1)', 'procurement');

        INSERT INTO budget_lines (source_file, exhibit_type, organization_name,
            fiscal_year, account, account_title, amount_fy2026_request)
        VALUES ('test.xlsx', 'p1', 'Army', 'FY2026', '2035',
                'Aircraft Procurement', 500.0);
    """)
    conn.close()

    from api.app import create_app
    app = create_app(db_path=db)
    return TestClient(app)


class TestCacheHeaders:
    def test_reference_endpoint_has_cache_control(self, client):
        """Reference endpoints return Cache-Control: public, max-age=3600."""
        response = client.get("/api/v1/reference/services")
        assert response.status_code == 200
        cc = response.headers.get("Cache-Control", "")
        assert "max-age=3600" in cc

    def test_reference_exhibit_types_has_cache_control(self, client):
        """Exhibit types endpoint returns Cache-Control header."""
        response = client.get("/api/v1/reference/exhibit-types")
        assert response.status_code == 200
        cc = response.headers.get("Cache-Control", "")
        assert "max-age" in cc

    def test_aggregations_endpoint_has_cache_control(self, client):
        """Aggregation endpoints return Cache-Control: public, max-age=300."""
        response = client.get("/api/v1/aggregations?group_by=service")
        assert response.status_code == 200
        cc = response.headers.get("Cache-Control", "")
        assert "max-age=300" in cc

    def test_search_endpoint_has_no_cache(self, client):
        """Search endpoints return Cache-Control: private, no-cache."""
        response = client.get("/api/v1/search?q=test")
        assert response.status_code == 200
        cc = response.headers.get("Cache-Control", "")
        assert "no-cache" in cc

    def test_etag_present(self, client):
        """API responses include ETag header."""
        response = client.get("/api/v1/reference/services")
        assert response.status_code == 200
        assert "ETag" in response.headers

    def test_etag_304_not_modified(self, client):
        """If-None-Match with matching ETag returns 304."""
        response1 = client.get("/api/v1/reference/services")
        etag = response1.headers.get("ETag")
        assert etag is not None

        response2 = client.get(
            "/api/v1/reference/services",
            headers={"If-None-Match": etag},
        )
        assert response2.status_code == 304

    def test_etag_mismatch_returns_200(self, client):
        """If-None-Match with wrong ETag returns normal 200."""
        response = client.get(
            "/api/v1/reference/services",
            headers={"If-None-Match": '"wrong-etag"'},
        )
        assert response.status_code == 200
