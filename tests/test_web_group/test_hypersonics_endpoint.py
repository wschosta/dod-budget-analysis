"""Tests for api/routes/hypersonics.py — hypersonics PE lines endpoints.

These tests exercise the HTTP layer. The keyword_search pipeline is complex
and tested indirectly via the cache rebuild endpoint.
"""

import csv
import io

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def client(test_db_excel_only):
    from api.app import create_app
    app = create_app(db_path=test_db_excel_only)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ── POST /api/v1/hypersonics/rebuild ─────────────────────────────────────────


class TestRebuildCache:
    def test_rebuild_returns_200(self, client):
        resp = client.post("/api/v1/hypersonics/rebuild")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "rows" in body


# ── GET /api/v1/hypersonics ──────────────────────────────────────────────────


class TestGetHypersonics:
    def test_get_returns_200(self, client):
        # Rebuild first to ensure cache exists
        client.post("/api/v1/hypersonics/rebuild")
        resp = client.get("/api/v1/hypersonics")
        assert resp.status_code == 200

    def test_response_structure(self, client):
        client.post("/api/v1/hypersonics/rebuild")
        body = client.get("/api/v1/hypersonics").json()
        assert "count" in body
        assert "fiscal_years" in body
        assert "keywords" in body
        assert "rows" in body
        assert isinstance(body["rows"], list)
        assert isinstance(body["fiscal_years"], list)
        assert isinstance(body["keywords"], list)

    def test_filter_by_service(self, client):
        client.post("/api/v1/hypersonics/rebuild")
        resp = client.get("/api/v1/hypersonics", params={"service": "Army"})
        assert resp.status_code == 200

    def test_filter_by_exhibit(self, client):
        client.post("/api/v1/hypersonics/rebuild")
        resp = client.get("/api/v1/hypersonics", params={"exhibit": "r1"})
        assert resp.status_code == 200


# ── GET /api/v1/hypersonics/download ─────────────────────────────────────────


class TestDownloadCSV:
    def test_csv_download(self, client):
        client.post("/api/v1/hypersonics/rebuild")
        resp = client.get("/api/v1/hypersonics/download")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_csv_has_content_disposition(self, client):
        client.post("/api/v1/hypersonics/rebuild")
        resp = client.get("/api/v1/hypersonics/download")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "csv" in resp.headers.get("content-disposition", "")

    def test_csv_parseable(self, client):
        client.post("/api/v1/hypersonics/rebuild")
        resp = client.get("/api/v1/hypersonics/download")
        # CSV is UTF-8-BOM encoded
        text = resp.content.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        headers = next(reader)
        assert "PE Number" in headers
        assert "Service/Org" in headers


# ── GET /api/v1/hypersonics/desc/{pe_number} ────────────────────────────────


class TestGetDescription:
    def test_desc_existing_pe(self, client):
        client.post("/api/v1/hypersonics/rebuild")
        # Use a PE that exists in the test fixture data
        resp = client.get("/api/v1/hypersonics/desc/0602702E")
        assert resp.status_code == 200
        body = resp.json()
        assert "description" in body

    def test_desc_nonexistent_pe(self, client):
        resp = client.get("/api/v1/hypersonics/desc/ZZZZZZZZ")
        assert resp.status_code == 200
        body = resp.json()
        assert body["description"] is None


# ── GET /api/v1/hypersonics/debug ────────────────────────────────────────────


class TestDebug:
    def test_debug_returns_200(self, client):
        resp = client.get("/api/v1/hypersonics/debug")
        assert resp.status_code == 200
        body = resp.json()
        assert "cache" in body

    def test_debug_cache_status(self, client):
        client.post("/api/v1/hypersonics/rebuild")
        body = client.get("/api/v1/hypersonics/debug").json()
        cache = body["cache"]
        assert "table_exists" in cache
        assert "row_count" in cache


# ── POST /api/v1/hypersonics/download/xlsx ───────────────────────────────────


class TestDownloadXLSX:
    def test_no_rows_selected_returns_400(self, client):
        client.post("/api/v1/hypersonics/rebuild")
        resp = client.post(
            "/api/v1/hypersonics/download/xlsx",
            json={"show_ids": [], "total_ids": []},
        )
        assert resp.status_code == 400
