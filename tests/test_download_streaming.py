"""
TEST-003: Download endpoint streaming behavior tests.

Tests for GET /api/v1/download — CSV and NDJSON streaming output,
filter parameters, limit parameter, and empty result handling.
"""
import csv
import io
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from api.app import create_app


@pytest.fixture(autouse=True)
def clear_rate_counters():
    """Reset global rate-limit counters before each test (avoid 429 in test suite)."""
    import api.app as _app_mod
    _app_mod._rate_counters.clear()
    yield
    _app_mod._rate_counters.clear()


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """App client with a pre-populated test database for download tests."""
    tmp = tmp_path_factory.mktemp("download_test")
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
    """)

    # Insert 20 rows with mixed services and fiscal years
    for i in range(20):
        service = "Army" if i % 2 == 0 else "Navy"
        fy = "FY 2026" if i < 15 else "FY 2025"
        conn.execute("""
            INSERT INTO budget_lines
                (source_file, exhibit_type, fiscal_year, organization_name,
                 account_title, line_item_title, amount_fy2026_request)
            VALUES (?, 'p1', ?, ?, 'Account Title', ?, ?)
        """, (f"file_{i}.xlsx", fy, service, f"Line Item {i}", float(i * 1000)))
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    return TestClient(app)


# ── CSV format tests ───────────────────────────────────────────────────────────

class TestCSVDownload:
    def test_csv_returns_200(self, client):
        resp = client.get("/api/v1/download?fmt=csv")
        assert resp.status_code == 200

    def test_csv_content_type(self, client):
        resp = client.get("/api/v1/download?fmt=csv")
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_csv_has_content_disposition(self, client):
        resp = client.get("/api/v1/download?fmt=csv")
        assert "attachment" in resp.headers.get("content-disposition", "")

    def test_csv_has_correct_headers(self, client):
        resp = client.get("/api/v1/download?fmt=csv")
        reader = csv.DictReader(io.StringIO(resp.text))
        assert reader.fieldnames is not None
        assert "id" in reader.fieldnames
        assert "source_file" in reader.fieldnames
        assert "organization_name" in reader.fieldnames

    def test_csv_row_count_matches_data(self, client):
        resp = client.get("/api/v1/download?fmt=csv")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 20

    def test_csv_empty_result_has_header_only(self, client):
        resp = client.get("/api/v1/download?fmt=csv&service=NonExistentService")
        reader = csv.DictReader(io.StringIO(resp.text))
        assert reader.fieldnames is not None
        rows = list(reader)
        assert len(rows) == 0


# ── NDJSON format tests ───────────────────────────────────────────────────────

class TestNDJSONDownload:
    def test_ndjson_returns_200(self, client):
        resp = client.get("/api/v1/download?fmt=json")
        assert resp.status_code == 200

    def test_ndjson_content_type(self, client):
        resp = client.get("/api/v1/download?fmt=json")
        ct = resp.headers.get("content-type", "")
        assert "json" in ct or "ndjson" in ct

    def test_ndjson_valid_json_per_line(self, client):
        resp = client.get("/api/v1/download?fmt=json")
        lines = [l for l in resp.text.strip().split("\n") if l]
        assert len(lines) == 20
        for line in lines:
            obj = json.loads(line)  # must not raise
            assert isinstance(obj, dict)

    def test_ndjson_has_expected_fields(self, client):
        resp = client.get("/api/v1/download?fmt=json")
        first_line = resp.text.strip().split("\n")[0]
        obj = json.loads(first_line)
        assert "id" in obj
        assert "source_file" in obj

    def test_ndjson_empty_result_no_content(self, client):
        resp = client.get("/api/v1/download?fmt=json&service=NonExistentService")
        # Either empty body or valid empty response
        lines = [l for l in resp.text.strip().split("\n") if l]
        assert len(lines) == 0


# ── Filter parameter tests ────────────────────────────────────────────────────

class TestDownloadFilters:
    def test_service_filter_narrows_results(self, client):
        resp = client.get("/api/v1/download?fmt=csv&service=Army")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 10  # half of 20 rows are Army

    def test_fiscal_year_filter_narrows_results(self, client):
        resp = client.get("/api/v1/download?fmt=csv&fiscal_year=FY+2025")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 5  # rows 15-19

    def test_exhibit_type_filter(self, client):
        resp = client.get("/api/v1/download?fmt=csv&exhibit_type=p1")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 20  # all are p1

    def test_invalid_exhibit_type_returns_empty(self, client):
        resp = client.get("/api/v1/download?fmt=csv&exhibit_type=zzz")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 0


# ── Limit parameter tests ─────────────────────────────────────────────────────

class TestDownloadLimit:
    def test_limit_caps_output_rows(self, client):
        resp = client.get("/api/v1/download?fmt=csv&limit=5")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 5

    def test_limit_one(self, client):
        resp = client.get("/api/v1/download?fmt=csv&limit=1")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 1

    def test_large_limit_returns_all(self, client):
        resp = client.get("/api/v1/download?fmt=csv&limit=10000")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 20
