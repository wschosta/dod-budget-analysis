"""Tests for api/routes/facets.py — cross-filtered facet counts."""

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


# ── GET /api/v1/facets ───────────────────────────────────────────────────────


class TestFacetsBasic:
    def test_facets_returns_200(self, client):
        resp = client.get("/api/v1/facets")
        assert resp.status_code == 200

    def test_facets_has_all_dimensions(self, client):
        body = client.get("/api/v1/facets").json()
        expected_dims = {"fiscal_year", "service", "exhibit_type", "budget_type"}
        assert expected_dims.issubset(body.keys())

    def test_fiscal_year_facet_not_empty(self, client):
        body = client.get("/api/v1/facets").json()
        assert len(body["fiscal_year"]) > 0

    def test_service_facet_not_empty(self, client):
        body = client.get("/api/v1/facets").json()
        assert len(body["service"]) > 0

    def test_facet_items_have_value_and_count(self, client):
        body = client.get("/api/v1/facets").json()
        for dim in ("fiscal_year", "service", "exhibit_type", "budget_type"):
            for item in body[dim]:
                assert "value" in item
                assert "count" in item
                assert item["count"] > 0


class TestFacetsCrossFiltering:
    """Cross-filtering: each dimension excludes its own filter."""

    def test_filter_by_service(self, client):
        body = client.get("/api/v1/facets", params={"service": "Army"}).json()
        # Service facet should still show all services (not filtered by itself)
        assert len(body["service"]) >= 1

    def test_service_filter_reduces_other_dims(self, client):
        unfiltered = client.get("/api/v1/facets").json()
        filtered = client.get("/api/v1/facets", params={"service": "Army"}).json()
        # Exhibit type counts may be reduced when filtered by service
        unfiltered_total = sum(f["count"] for f in unfiltered["exhibit_type"])
        filtered_total = sum(f["count"] for f in filtered["exhibit_type"])
        assert filtered_total <= unfiltered_total

    def test_filter_by_exhibit_type(self, client):
        resp = client.get("/api/v1/facets", params={"exhibit_type": "r1"})
        assert resp.status_code == 200

    def test_combined_filters(self, client):
        resp = client.get(
            "/api/v1/facets",
            params={"service": "Army", "exhibit_type": "r1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "fiscal_year" in body

    def test_nonexistent_filter_zeroes(self, client):
        body = client.get(
            "/api/v1/facets", params={"service": "NoSuchService"}
        ).json()
        # Other dimensions may have empty results
        for dim in ("fiscal_year", "exhibit_type", "budget_type"):
            total = sum(f["count"] for f in body[dim])
            assert total == 0


class TestFacetsCache:
    def test_repeated_calls_consistent(self, client):
        r1 = client.get("/api/v1/facets").json()
        r2 = client.get("/api/v1/facets").json()
        assert r1 == r2
