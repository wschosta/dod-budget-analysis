"""
Tests for download functionality.

Covers both unit tests (row iterator, column list) and integration tests
(CSV/NDJSON streaming via TestClient, filters, limit).

Consolidated from test_download_route.py and test_download_streaming.py.
"""
import csv
import io
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.routes.download import _iter_rows, _DOWNLOAD_COLUMNS, _ALLOWED_SORT, _build_download_sql
from fastapi.testclient import TestClient
from api.app import create_app


# ═══════════════════════════════════════════════════════════════════════════════
# Unit tests — download internals
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture()
def dl_db():
    """In-memory database with budget_lines table for download unit testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    cols = ", ".join(f"{c} TEXT" for c in _DOWNLOAD_COLUMNS if c != "id")
    conn.execute(f"CREATE TABLE budget_lines (id INTEGER PRIMARY KEY, {cols})")

    placeholders = ", ".join("?" * len(_DOWNLOAD_COLUMNS))
    for i in range(10):
        values = [i + 1] + [f"val_{c}_{i}" for c in _DOWNLOAD_COLUMNS[1:]]
        conn.execute(
            f"INSERT INTO budget_lines ({', '.join(_DOWNLOAD_COLUMNS)}) VALUES ({placeholders})",
            values,
        )
    conn.commit()
    yield conn
    conn.close()


class TestIterRows:
    def test_yields_all_rows(self, dl_db):
        rows = list(_iter_rows(dl_db, "SELECT * FROM budget_lines", []))
        assert len(rows) == 10

    def test_with_limit(self, dl_db):
        rows = list(_iter_rows(dl_db, "SELECT * FROM budget_lines LIMIT 3", []))
        assert len(rows) == 3

    def test_with_where_params(self, dl_db):
        rows = list(_iter_rows(
            dl_db, "SELECT * FROM budget_lines WHERE id = ?", [1]
        ))
        assert len(rows) == 1

    def test_empty_result(self, dl_db):
        rows = list(_iter_rows(
            dl_db, "SELECT * FROM budget_lines WHERE id = ?", [999]
        ))
        assert len(rows) == 0


class TestDownloadColumns:
    def test_has_essential_columns(self):
        assert "id" in _DOWNLOAD_COLUMNS
        assert "source_file" in _DOWNLOAD_COLUMNS
        assert "exhibit_type" in _DOWNLOAD_COLUMNS
        assert "organization_name" in _DOWNLOAD_COLUMNS
        assert "amount_fy2026_request" in _DOWNLOAD_COLUMNS

    def test_has_amount_columns(self):
        amount_cols = [c for c in _DOWNLOAD_COLUMNS if c.startswith("amount_")]
        assert len(amount_cols) >= 5


class TestDownloadAllowedSort:
    def test_has_common_sorts(self):
        assert "id" in _ALLOWED_SORT
        assert "source_file" in _ALLOWED_SORT
        assert "amount_fy2026_request" in _ALLOWED_SORT


class TestBuildDownloadSql:
    def test_appropriation_code_filter(self, dl_db):
        """appropriation_code filter restricts results."""
        dl_db.execute("UPDATE budget_lines SET appropriation_code = '3010' WHERE id = 1")
        dl_db.execute("UPDATE budget_lines SET appropriation_code = '1506' WHERE id = 2")
        dl_db.commit()

        sql, params, total = _build_download_sql(
            fiscal_year=None, service=None, exhibit_type=None,
            pe_number=None, appropriation_code=["3010"], q=None,
            conn=dl_db, limit=100, export_cols=_DOWNLOAD_COLUMNS,
        )
        assert total == 1
        rows = list(_iter_rows(dl_db, sql, params))
        assert len(rows) == 1

    def test_min_max_amount_filter(self, dl_db):
        """min_amount and max_amount restrict results."""
        dl_db.execute("UPDATE budget_lines SET amount_fy2026_request = 500 WHERE id = 1")
        dl_db.execute("UPDATE budget_lines SET amount_fy2026_request = 1500 WHERE id = 2")
        dl_db.execute("UPDATE budget_lines SET amount_fy2026_request = 3000 WHERE id = 3")
        dl_db.commit()

        sql, params, total = _build_download_sql(
            fiscal_year=None, service=None, exhibit_type=None,
            pe_number=None, appropriation_code=None, q=None,
            conn=dl_db, limit=100, export_cols=_DOWNLOAD_COLUMNS,
            min_amount=1000.0, max_amount=2000.0,
        )
        assert total == 1  # Only id=2 with amount=1500

    def test_sort_order_applied(self, dl_db):
        """sort_by and sort_dir affect result ordering."""
        sql_desc, params_desc, _ = _build_download_sql(
            fiscal_year=None, service=None, exhibit_type=None,
            pe_number=None, appropriation_code=None, q=None,
            conn=dl_db, limit=100, export_cols=_DOWNLOAD_COLUMNS,
            sort_by="id", sort_dir="desc",
        )
        rows = list(_iter_rows(dl_db, sql_desc, params_desc))
        ids = [r[0] for r in rows]
        assert ids == sorted(ids, reverse=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Integration tests — download endpoint streaming via TestClient
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def clear_rate_counters():
    """Reset global rate-limit counters before each test (avoid 429 in test suite)."""
    import api.app as _app_mod
    _app_mod._rate_counters.clear()
    yield
    _app_mod._rate_counters.clear()


@pytest.fixture(scope="module")
def dl_client(tmp_path_factory):
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


# ── CSV format tests ─────────────────────────────────────────────────────────

class TestCSVDownload:
    def test_csv_returns_200(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=csv")
        assert resp.status_code == 200

    def test_csv_content_type(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=csv")
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_csv_has_content_disposition(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=csv")
        assert "attachment" in resp.headers.get("content-disposition", "")

    def test_csv_has_correct_headers(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=csv")
        reader = csv.DictReader(io.StringIO(resp.text))
        assert reader.fieldnames is not None
        assert "id" in reader.fieldnames
        assert "source_file" in reader.fieldnames
        assert "organization_name" in reader.fieldnames

    def test_csv_row_count_matches_data(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=csv")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 20

    def test_csv_empty_result_has_header_only(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=csv&service=NonExistentService")
        reader = csv.DictReader(io.StringIO(resp.text))
        assert reader.fieldnames is not None
        rows = list(reader)
        assert len(rows) == 0


# ── NDJSON format tests ──────────────────────────────────────────────────────

class TestNDJSONDownload:
    def test_ndjson_returns_200(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=json")
        assert resp.status_code == 200

    def test_ndjson_content_type(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=json")
        ct = resp.headers.get("content-type", "")
        assert "json" in ct or "ndjson" in ct

    def test_ndjson_valid_json_per_line(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=json")
        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) == 20
        for line in lines:
            obj = json.loads(line)
            assert isinstance(obj, dict)

    def test_ndjson_has_expected_fields(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=json")
        first_line = resp.text.strip().split("\n")[0]
        obj = json.loads(first_line)
        assert "id" in obj
        assert "source_file" in obj

    def test_ndjson_empty_result_no_content(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=json&service=NonExistentService")
        lines = [line for line in resp.text.strip().split("\n") if line]
        assert len(lines) == 0


# ── Filter parameter tests ───────────────────────────────────────────────────

class TestDownloadFilters:
    def test_service_filter_narrows_results(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=csv&service=Army")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 10

    def test_fiscal_year_filter_narrows_results(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=csv&fiscal_year=FY+2025")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 5

    def test_exhibit_type_filter(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=csv&exhibit_type=p1")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 20

    def test_invalid_exhibit_type_returns_empty(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=csv&exhibit_type=zzz")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 0


# ── Limit parameter tests ───────────────────────────────────────────────────

class TestDownloadLimit:
    def test_limit_caps_output_rows(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=csv&limit=5")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 5

    def test_limit_one(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=csv&limit=1")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 1

    def test_large_limit_returns_all(self, dl_client):
        resp = dl_client.get("/api/v1/download?fmt=csv&limit=10000")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 20
