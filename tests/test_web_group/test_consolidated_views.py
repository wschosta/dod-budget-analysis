"""Tests for api/routes/frontend.py — consolidated PE list and detail views.

Covers the /consolidated and /consolidated/{pe_number} endpoints that were
previously untested (lines 1095-1388 of frontend.py).
"""
import json
import sqlite3
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _mod in ("pdfplumber", "openpyxl", "pandas"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

from unittest.mock import patch  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def consolidated_db(tmp_path):
    """Create a database with the consolidated schema (line_items, line_item_amounts, etc.)."""
    db = tmp_path / "consolidated_test.sqlite"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE budget_lines (id INTEGER PRIMARY KEY, source_file TEXT);
        CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY);
        CREATE TABLE ingested_files (
            file_path TEXT PRIMARY KEY, file_type TEXT,
            file_size INTEGER, file_modified REAL, ingested_at TEXT,
            row_count INTEGER, status TEXT
        );

        CREATE TABLE line_items (
            id INTEGER PRIMARY KEY,
            pe_number TEXT NOT NULL,
            line_item_title TEXT,
            organization_name TEXT,
            budget_type TEXT,
            submission_count INTEGER DEFAULT 1,
            first_seen_fy TEXT,
            last_seen_fy TEXT
        );

        CREATE TABLE line_item_amounts (
            id INTEGER PRIMARY KEY,
            line_item_id INTEGER REFERENCES line_items(id),
            target_fy INTEGER,
            amount_type TEXT,
            amount REAL,
            quantity REAL,
            source_submission_fy TEXT,
            precedence_rank INTEGER DEFAULT 1
        );

        CREATE TABLE budget_submissions (
            id INTEGER PRIMARY KEY,
            line_item_id INTEGER REFERENCES line_items(id),
            fiscal_year TEXT,
            source_file TEXT,
            raw_amounts TEXT,
            raw_quantities TEXT
        );

        CREATE TABLE pe_projects (
            id INTEGER PRIMARY KEY,
            pe_number TEXT,
            project_number TEXT,
            project_title TEXT,
            fiscal_year TEXT,
            fy_columns TEXT,
            amounts TEXT,
            narrative_text TEXT
        );

        CREATE TABLE pe_descriptions (
            id INTEGER PRIMARY KEY,
            pe_number TEXT,
            fiscal_year TEXT,
            section_header TEXT,
            description_text TEXT
        );

        CREATE TABLE pe_tags (
            id INTEGER PRIMARY KEY,
            pe_number TEXT,
            tag TEXT,
            tag_source TEXT,
            confidence REAL DEFAULT 1.0,
            project_number TEXT
        );

        CREATE TABLE pe_mission_descriptions (
            id INTEGER PRIMARY KEY,
            pe_number TEXT,
            fiscal_year TEXT,
            description_text TEXT
        );

        -- Insert test data
        INSERT INTO line_items (id, pe_number, line_item_title, organization_name, budget_type, submission_count)
        VALUES
            (1, '0602120A', 'Cyber Research', 'Army', 'RDT&E', 3),
            (2, '0604030N', 'Tomahawk Weapon System', 'Navy', 'Procurement', 2),
            (3, '0305116BB', 'Space Fence', 'Air Force', 'RDT&E', 1);

        INSERT INTO line_item_amounts (line_item_id, target_fy, amount_type, amount, precedence_rank)
        VALUES
            (1, 2026, 'request', 150000.0, 1),
            (1, 2025, 'enacted', 125000.0, 1),
            (1, 2024, 'actual', 110000.0, 1),
            (2, 2026, 'request', 800000.0, 1),
            (2, 2025, 'enacted', 750000.0, 1),
            (3, 2026, 'request', 50000.0, 1);

        INSERT INTO budget_submissions (line_item_id, fiscal_year, source_file, raw_amounts)
        VALUES
            (1, 'FY 2026', 'fy2026_army.xlsx', '{"fy2026_request": 150000}'),
            (1, 'FY 2025', 'fy2025_army.xlsx', '{"fy2025_enacted": 125000}'),
            (2, 'FY 2026', 'fy2026_navy.xlsx', '{"fy2026_request": 800000}');

        INSERT INTO pe_projects (pe_number, project_number, project_title, fiscal_year, fy_columns, amounts)
        VALUES ('0602120A', 'BG1', 'Offensive Cyber', 'FY 2026',
                '["2024", "2025", "2026"]', '[110, 125, 150]');

        INSERT INTO pe_descriptions (pe_number, fiscal_year, section_header, description_text)
        VALUES ('0602120A', '2026', 'A. Mission Description',
                'Develops advanced cybersecurity capabilities for Army networks.');

        INSERT INTO pe_tags (pe_number, tag, tag_source, confidence, project_number)
        VALUES ('0602120A', 'cyber', 'keyword', 0.95, NULL);

        INSERT INTO pe_mission_descriptions (pe_number, fiscal_year, description_text)
        VALUES ('0602120A', '2026', 'Develops advanced cybersecurity capabilities for Army networks.');
    """)
    conn.close()
    return db


@pytest.fixture()
def client(consolidated_db):
    """TestClient with consolidated data.

    Patches _get_work_conn so the consolidated endpoints use our test DB
    instead of looking for the real dod_budget_work.sqlite file.
    """
    import api.routes.frontend as frontend_mod

    def _mock_work_conn():
        conn = sqlite3.connect(str(consolidated_db))
        conn.row_factory = sqlite3.Row
        return conn

    from api.app import create_app
    app = create_app(db_path=consolidated_db)
    with patch.object(frontend_mod, "_get_work_conn", _mock_work_conn):
        yield TestClient(app)


# ── GET /consolidated ────────────────────────────────────────────────────────


class TestConsolidatedList:
    def test_returns_200(self, client):
        resp = client.get("/consolidated")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_contains_pe_numbers(self, client):
        resp = client.get("/consolidated")
        html = resp.text
        assert "0602120A" in html
        assert "0604030N" in html

    def test_search_filter(self, client):
        resp = client.get("/consolidated?q=Cyber")
        assert resp.status_code == 200
        html = resp.text
        assert "0602120A" in html
        # Tomahawk should not appear when searching for "Cyber"
        assert "Tomahawk" not in html

    def test_service_filter(self, client):
        resp = client.get("/consolidated?service=Navy")
        assert resp.status_code == 200
        html = resp.text
        assert "0604030N" in html
        # Army PE should not appear
        assert "0602120A" not in html

    def test_budget_type_filter(self, client):
        resp = client.get("/consolidated?budget_type=Procurement")
        assert resp.status_code == 200
        html = resp.text
        assert "0604030N" in html

    def test_sort_by_pe_number(self, client):
        resp = client.get("/consolidated?sort_by=pe_number")
        assert resp.status_code == 200

    def test_sort_by_name(self, client):
        resp = client.get("/consolidated?sort_by=name")
        assert resp.status_code == 200

    def test_sort_by_funding_desc(self, client):
        resp = client.get("/consolidated?sort_by=funding_desc")
        assert resp.status_code == 200

    def test_sort_by_funding_asc(self, client):
        resp = client.get("/consolidated?sort_by=funding_asc")
        assert resp.status_code == 200

    def test_sort_by_submissions(self, client):
        resp = client.get("/consolidated?sort_by=submissions")
        assert resp.status_code == 200

    def test_sort_by_service(self, client):
        resp = client.get("/consolidated?sort_by=service")
        assert resp.status_code == 200

    def test_invalid_sort_defaults_to_pe_number(self, client):
        resp = client.get("/consolidated?sort_by=invalid_sort")
        assert resp.status_code == 200

    def test_pagination_page_1(self, client):
        resp = client.get("/consolidated?page=1")
        assert resp.status_code == 200

    def test_pagination_beyond_last_page(self, client):
        """Page beyond total should clamp to last page."""
        resp = client.get("/consolidated?page=999")
        assert resp.status_code == 200

    def test_negative_page_clamps_to_1(self, client):
        resp = client.get("/consolidated?page=-1")
        assert resp.status_code == 200

    def test_combined_filters(self, client):
        resp = client.get("/consolidated?q=Cyber&service=Army&budget_type=RDT%26E")
        assert resp.status_code == 200


# ── GET /consolidated/{pe_number} ────────────────────────────────────────────


class TestConsolidatedDetail:
    def test_returns_200_for_known_pe(self, client):
        resp = client.get("/consolidated/0602120A")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_contains_pe_title(self, client):
        resp = client.get("/consolidated/0602120A")
        assert "Cyber Research" in resp.text

    def test_contains_amounts(self, client):
        resp = client.get("/consolidated/0602120A")
        html = resp.text
        # Should show time series amounts
        assert "150" in html  # FY2026 request amount

    def test_contains_submissions(self, client):
        resp = client.get("/consolidated/0602120A")
        html = resp.text
        assert "fy2026_army.xlsx" in html or "FY 2026" in html

    def test_contains_projects(self, client):
        resp = client.get("/consolidated/0602120A")
        html = resp.text
        assert "Offensive Cyber" in html or "BG1" in html

    def test_contains_tags(self, client):
        resp = client.get("/consolidated/0602120A")
        html = resp.text
        assert "cyber" in html.lower()

    def test_404_for_unknown_pe(self, client):
        resp = client.get("/consolidated/9999999X")
        assert resp.status_code == 404

    def test_detail_with_no_submissions(self, client):
        """PE with amounts but no submissions should still render."""
        resp = client.get("/consolidated/0305116BB")
        assert resp.status_code == 200
        assert "Space Fence" in resp.text
