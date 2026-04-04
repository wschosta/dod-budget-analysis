"""Tests for api/routes/dashboard.py — dashboard summary endpoint."""

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


# ── GET /api/v1/dashboard/summary ────────────────────────────────────────────


class TestDashboardSummary:
    def test_summary_returns_200(self, client):
        resp = client.get("/api/v1/dashboard/summary")
        assert resp.status_code == 200

    def test_summary_has_required_sections(self, client):
        body = client.get("/api/v1/dashboard/summary").json()
        required = {"totals", "by_service", "top_programs", "by_fiscal_year",
                     "by_budget_type", "by_exhibit_type"}
        assert required.issubset(body.keys())

    def test_totals_section(self, client):
        body = client.get("/api/v1/dashboard/summary").json()
        totals = body["totals"]
        assert "total_lines" in totals
        assert totals["total_lines"] > 0
        assert "distinct_pes" in totals

    def test_by_service_is_list(self, client):
        body = client.get("/api/v1/dashboard/summary").json()
        assert isinstance(body["by_service"], list)

    def test_by_service_has_fields(self, client):
        body = client.get("/api/v1/dashboard/summary").json()
        services = body["by_service"]
        if services:
            svc = services[0]
            assert "service" in svc
            assert "total" in svc
            assert "line_count" in svc

    def test_by_service_limited_to_six(self, client):
        body = client.get("/api/v1/dashboard/summary").json()
        assert len(body["by_service"]) <= 6

    def test_top_programs_is_list(self, client):
        body = client.get("/api/v1/dashboard/summary").json()
        assert isinstance(body["top_programs"], list)

    def test_top_programs_limited_to_ten(self, client):
        body = client.get("/api/v1/dashboard/summary").json()
        assert len(body["top_programs"]) <= 10

    def test_top_programs_have_pe_number(self, client):
        body = client.get("/api/v1/dashboard/summary").json()
        for prog in body["top_programs"]:
            assert "pe_number" in prog

    def test_by_fiscal_year(self, client):
        body = client.get("/api/v1/dashboard/summary").json()
        assert isinstance(body["by_fiscal_year"], list)

    def test_by_budget_type(self, client):
        body = client.get("/api/v1/dashboard/summary").json()
        assert isinstance(body["by_budget_type"], list)

    def test_by_exhibit_type(self, client):
        body = client.get("/api/v1/dashboard/summary").json()
        assert isinstance(body["by_exhibit_type"], list)


# ── Filters ──────────────────────────────────────────────────────────────────


class TestDashboardFilters:
    def test_filter_by_service(self, client):
        resp = client.get("/api/v1/dashboard/summary", params={"service": "Army"})
        assert resp.status_code == 200

    def test_filter_by_exhibit_type(self, client):
        resp = client.get("/api/v1/dashboard/summary", params={"exhibit_type": "r1"})
        assert resp.status_code == 200

    def test_filter_by_nonexistent_service(self, client):
        body = client.get(
            "/api/v1/dashboard/summary", params={"service": "NoSuchService"}
        ).json()
        assert body["totals"]["total_lines"] == 0

    def test_combined_filters(self, client):
        resp = client.get(
            "/api/v1/dashboard/summary",
            params={"service": "Army", "exhibit_type": "r1"},
        )
        assert resp.status_code == 200


# ── Cache ────────────────────────────────────────────────────────────────────


class TestDashboardCache:
    def test_cache_clear(self, client):
        resp = client.post("/api/v1/dashboard/cache-clear")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"

    def test_second_call_uses_cache(self, client):
        """Two identical calls should both succeed (second hits cache)."""
        r1 = client.get("/api/v1/dashboard/summary")
        r2 = client.get("/api/v1/dashboard/summary")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["totals"] == r2.json()["totals"]
