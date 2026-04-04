"""Tests for api/routes/dashboard.py — dashboard summary endpoint."""

import pytest


@pytest.fixture(scope="module")
def summary(client):
    """Fetch the unfiltered dashboard summary once for the module."""
    return client.get("/api/v1/dashboard/summary").json()


class TestDashboardSummary:
    def test_summary_returns_200(self, client):
        assert client.get("/api/v1/dashboard/summary").status_code == 200

    def test_summary_has_required_sections(self, summary):
        required = {"totals", "by_service", "top_programs", "by_fiscal_year",
                     "by_budget_type", "by_exhibit_type"}
        assert required.issubset(summary.keys())

    def test_totals_section(self, summary):
        totals = summary["totals"]
        assert "total_lines" in totals
        assert totals["total_lines"] > 0
        assert "distinct_pes" in totals

    def test_by_service_has_fields(self, summary):
        assert isinstance(summary["by_service"], list)
        services = summary["by_service"]
        if services:
            svc = services[0]
            assert "service" in svc
            assert "total" in svc
            assert "line_count" in svc

    def test_by_service_limited_to_six(self, summary):
        assert len(summary["by_service"]) <= 6

    def test_top_programs(self, summary):
        assert isinstance(summary["top_programs"], list)
        assert len(summary["top_programs"]) <= 10
        for prog in summary["top_programs"]:
            assert "pe_number" in prog

    def test_by_fiscal_year(self, summary):
        assert isinstance(summary["by_fiscal_year"], list)

    def test_by_budget_type(self, summary):
        assert isinstance(summary["by_budget_type"], list)

    def test_by_exhibit_type(self, summary):
        assert isinstance(summary["by_exhibit_type"], list)


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


class TestDashboardCache:
    def test_cache_clear(self, client):
        resp = client.post("/api/v1/dashboard/cache-clear")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_second_call_uses_cache(self, client):
        """Two identical calls should both succeed (second hits cache)."""
        r1 = client.get("/api/v1/dashboard/summary")
        r2 = client.get("/api/v1/dashboard/summary")
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["totals"] == r2.json()["totals"]
