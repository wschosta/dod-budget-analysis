"""
Tests for api/app.py — create_app() factory

Verifies the FastAPI app is created with correct configuration,
routers are registered, and middleware is functional.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.app import create_app


@pytest.fixture()
def test_db(tmp_path):
    """Create a minimal test database."""
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT, exhibit_type TEXT, sheet_name TEXT,
            fiscal_year TEXT, account TEXT, account_title TEXT,
            organization_name TEXT, budget_activity_title TEXT,
            sub_activity_title TEXT, line_item TEXT, line_item_title TEXT,
            pe_number TEXT, appropriation_code TEXT, appropriation_title TEXT,
            currency_year TEXT, amount_unit TEXT, amount_type TEXT,
            amount_fy2024_actual REAL, amount_fy2025_enacted REAL,
            amount_fy2025_supplemental REAL, amount_fy2025_total REAL,
            amount_fy2026_request REAL, amount_fy2026_reconciliation REAL,
            amount_fy2026_total REAL,
            quantity_fy2024 REAL, quantity_fy2025 REAL,
            quantity_fy2026_request REAL, quantity_fy2026_total REAL
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
        INSERT INTO budget_lines (source_file, exhibit_type, fiscal_year,
            organization_name, amount_fy2026_request)
        VALUES ('army_p1.xlsx', 'p1', 'FY 2026', 'Army', 100000);
    """)
    conn.commit()
    conn.close()
    return db_path


class TestCreateApp:
    def test_creates_fastapi_instance(self, test_db):
        app = create_app(db_path=test_db)
        assert app.title == "DoD Budget API"
        assert app.version == "1.0.0"

    def test_registers_api_routes(self, test_db):
        app = create_app(db_path=test_db)
        route_paths = {r.path for r in app.routes}
        assert "/api/v1/search" in route_paths or any(
            "/api/v1/search" in str(getattr(r, "path", "")) for r in app.routes
        )

    def test_health_endpoint_exists(self, test_db):
        app = create_app(db_path=test_db)
        route_paths = {getattr(r, "path", "") for r in app.routes}
        assert "/health" in route_paths


class TestHealthEndpoint:
    def test_health_ok(self, test_db):
        from fastapi.testclient import TestClient
        app = create_app(db_path=test_db)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["budget_lines"] >= 1

    def test_health_no_db(self, tmp_path):
        from fastapi.testclient import TestClient
        app = create_app(db_path=tmp_path / "nonexistent.sqlite")
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 503
