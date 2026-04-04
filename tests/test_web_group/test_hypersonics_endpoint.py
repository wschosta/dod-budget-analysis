"""Tests for api/routes/hypersonics.py — hypersonics PE lines endpoints."""

import csv
import io

import pytest


@pytest.fixture(scope="module", autouse=True)
def _rebuild_hypersonics_cache(client):
    """Rebuild the hypersonics cache once for the entire module."""
    client.post("/api/v1/hypersonics/rebuild")


class TestRebuildCache:
    def test_rebuild_returns_200(self, client):
        resp = client.post("/api/v1/hypersonics/rebuild")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "rows" in body


class TestGetHypersonics:
    def test_get_returns_200(self, client):
        resp = client.get("/api/v1/hypersonics")
        assert resp.status_code == 200

    def test_response_structure(self, client):
        body = client.get("/api/v1/hypersonics").json()
        assert "count" in body
        assert "fiscal_years" in body
        assert "keywords" in body
        assert "rows" in body
        assert isinstance(body["rows"], list)
        assert isinstance(body["fiscal_years"], list)
        assert isinstance(body["keywords"], list)

    def test_filter_by_service(self, client):
        resp = client.get("/api/v1/hypersonics", params={"service": "Army"})
        assert resp.status_code == 200

    def test_filter_by_exhibit(self, client):
        resp = client.get("/api/v1/hypersonics", params={"exhibit": "r1"})
        assert resp.status_code == 200


class TestDownloadCSV:
    def test_csv_download(self, client):
        resp = client.get("/api/v1/hypersonics/download")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_csv_has_content_disposition(self, client):
        resp = client.get("/api/v1/hypersonics/download")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "csv" in resp.headers.get("content-disposition", "")

    def test_csv_parseable(self, client):
        resp = client.get("/api/v1/hypersonics/download")
        text = resp.content.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        headers = next(reader)
        assert "PE Number" in headers
        assert "Service/Org" in headers


class TestGetDescription:
    def test_desc_existing_pe(self, client):
        resp = client.get("/api/v1/hypersonics/desc/0602702E")
        assert resp.status_code == 200
        body = resp.json()
        assert "description" in body

    def test_desc_nonexistent_pe(self, client):
        resp = client.get("/api/v1/hypersonics/desc/ZZZZZZZZ")
        assert resp.status_code == 200
        assert resp.json()["description"] is None


class TestDebug:
    def test_debug_returns_200(self, client):
        body = client.get("/api/v1/hypersonics/debug").json()
        assert "cache" in body

    def test_debug_cache_status(self, client):
        cache = client.get("/api/v1/hypersonics/debug").json()["cache"]
        assert "table_exists" in cache
        assert "row_count" in cache


class TestDownloadXLSX:
    def test_no_rows_selected_returns_400(self, client):
        resp = client.post(
            "/api/v1/hypersonics/download/xlsx",
            json={"show_ids": [], "total_ids": []},
        )
        assert resp.status_code == 400
