"""
API endpoint tests (Step 2.C6-a).

Uses FastAPI TestClient (backed by httpx) with the excel-only test database
fixture.  Each test group covers one endpoint: happy path, empty results,
invalid parameters, and pagination.
"""

import pytest

# FastAPI TestClient requires fastapi + httpx; skip the entire module if not installed
pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def client(test_db_excel_only):
    """Create a FastAPI TestClient wired to the excel-only test database."""
    from api.app import create_app
    app = create_app(db_path=test_db_excel_only)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "budget_lines" in body


# ── /api/v1/search ────────────────────────────────────────────────────────────

class TestSearch:
    def test_search_returns_200(self, client):
        resp = client.get("/api/v1/search", params={"q": "army"})
        assert resp.status_code == 200
        body = resp.json()
        assert "results" in body
        assert "query" in body
        assert body["query"] == "army"

    def test_search_missing_q_returns_422(self, client):
        resp = client.get("/api/v1/search")
        assert resp.status_code == 422

    def test_search_type_excel(self, client):
        resp = client.get("/api/v1/search", params={"q": "army", "type": "excel"})
        assert resp.status_code == 200

    def test_search_type_pdf(self, client):
        resp = client.get("/api/v1/search", params={"q": "army", "type": "pdf"})
        assert resp.status_code == 200

    def test_search_invalid_type_returns_422(self, client):
        resp = client.get("/api/v1/search", params={"q": "army", "type": "invalid"})
        assert resp.status_code == 422

    def test_search_limit_enforced(self, client):
        resp = client.get("/api/v1/search", params={"q": "army", "limit": 5})
        assert resp.status_code == 200

    def test_search_limit_over_max_returns_422(self, client):
        resp = client.get("/api/v1/search", params={"q": "army", "limit": 999})
        assert resp.status_code == 422


# ── /api/v1/budget-lines ──────────────────────────────────────────────────────

class TestBudgetLines:
    def test_list_returns_200(self, client):
        resp = client.get("/api/v1/budget-lines")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "limit" in body
        assert "offset" in body

    def test_list_pagination(self, client):
        resp = client.get("/api/v1/budget-lines", params={"limit": 2, "offset": 0})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) <= 2

    def test_list_invalid_sort_returns_400(self, client):
        resp = client.get("/api/v1/budget-lines", params={"sort_by": "not_a_column"})
        assert resp.status_code == 400

    def test_list_invalid_sort_dir_returns_422(self, client):
        resp = client.get("/api/v1/budget-lines", params={"sort_dir": "sideways"})
        assert resp.status_code == 422

    def test_list_filter_fiscal_year(self, client):
        resp = client.get("/api/v1/budget-lines", params={"fiscal_year": "FY 2026"})
        assert resp.status_code == 200

    def test_detail_not_found(self, client):
        resp = client.get("/api/v1/budget-lines/999999999")
        assert resp.status_code == 404

    def test_detail_returns_200_for_valid_id(self, client):
        # Get the first id from the list
        list_resp = client.get("/api/v1/budget-lines", params={"limit": 1})
        if list_resp.status_code != 200:
            pytest.skip("No budget lines in test db")
        items = list_resp.json()["items"]
        if not items:
            pytest.skip("No budget lines in test db")
        item_id = items[0]["id"]
        resp = client.get(f"/api/v1/budget-lines/{item_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == item_id


# ── /api/v1/aggregations ──────────────────────────────────────────────────────

class TestAggregations:
    def test_group_by_service(self, client):
        resp = client.get("/api/v1/aggregations", params={"group_by": "service"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["group_by"] == "service"
        assert "rows" in body

    def test_group_by_fiscal_year(self, client):
        resp = client.get("/api/v1/aggregations", params={"group_by": "fiscal_year"})
        assert resp.status_code == 200

    def test_group_by_exhibit_type(self, client):
        resp = client.get("/api/v1/aggregations", params={"group_by": "exhibit_type"})
        assert resp.status_code == 200

    def test_invalid_group_by_returns_400(self, client):
        resp = client.get("/api/v1/aggregations", params={"group_by": "not_valid"})
        assert resp.status_code == 400

    def test_missing_group_by_returns_422(self, client):
        resp = client.get("/api/v1/aggregations")
        assert resp.status_code == 422


# ── /api/v1/reference ─────────────────────────────────────────────────────────

class TestReference:
    def test_services_returns_200(self, client):
        resp = client.get("/api/v1/reference/services")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_exhibit_types_returns_200(self, client):
        resp = client.get("/api/v1/reference/exhibit-types")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_fiscal_years_returns_200(self, client):
        resp = client.get("/api/v1/reference/fiscal-years")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        for item in data:
            assert "fiscal_year" in item
            assert "row_count" in item


# ── /api/v1/download ──────────────────────────────────────────────────────────

class TestDownload:
    def test_download_csv(self, client):
        resp = client.get("/api/v1/download", params={"fmt": "csv"})
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "budget_lines.csv" in resp.headers.get("content-disposition", "")

    def test_download_json(self, client):
        resp = client.get("/api/v1/download", params={"fmt": "json"})
        assert resp.status_code == 200
        ct = resp.headers.get("content-type", "")
        assert "ndjson" in ct or "json" in ct

    def test_download_invalid_fmt_returns_422(self, client):
        resp = client.get("/api/v1/download", params={"fmt": "xml"})
        assert resp.status_code == 422

    def test_download_limit_respected(self, client):
        resp = client.get("/api/v1/download", params={"fmt": "csv", "limit": 5})
        assert resp.status_code == 200
        lines = resp.text.splitlines()
        # EAGLE-6: Skip source attribution comment rows (start with "# or #)
        data_lines = [ln for ln in lines if not ln.startswith('"#') and not ln.startswith("#")]
        # header + up to 5 data rows = at most 6 lines
        assert len(data_lines) <= 6
