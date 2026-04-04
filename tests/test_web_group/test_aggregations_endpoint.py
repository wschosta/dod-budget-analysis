"""Tests for api/routes/aggregations.py — aggregation and hierarchy endpoints."""

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


# ── GET /api/v1/aggregations ─────────────────────────────────────────────────


class TestAggregate:
    def test_group_by_service(self, client):
        resp = client.get("/api/v1/aggregations", params={"group_by": "service"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["group_by"] == "service"
        assert isinstance(body["rows"], list)
        assert len(body["rows"]) > 0

    def test_group_by_fiscal_year(self, client):
        resp = client.get("/api/v1/aggregations", params={"group_by": "fiscal_year"})
        assert resp.status_code == 200
        assert len(resp.json()["rows"]) > 0

    def test_group_by_exhibit_type(self, client):
        resp = client.get("/api/v1/aggregations", params={"group_by": "exhibit_type"})
        assert resp.status_code == 200

    def test_group_by_budget_type(self, client):
        resp = client.get("/api/v1/aggregations", params={"group_by": "budget_type"})
        assert resp.status_code == 200

    def test_group_by_appropriation(self, client):
        resp = client.get("/api/v1/aggregations", params={"group_by": "appropriation"})
        assert resp.status_code == 200

    def test_group_by_budget_activity(self, client):
        resp = client.get("/api/v1/aggregations", params={"group_by": "budget_activity"})
        assert resp.status_code == 200

    def test_invalid_group_by_returns_400(self, client):
        resp = client.get("/api/v1/aggregations", params={"group_by": "invalid"})
        assert resp.status_code == 400

    def test_missing_group_by_returns_422(self, client):
        resp = client.get("/api/v1/aggregations")
        assert resp.status_code == 422


class TestAggregateRowFields:
    """Verify AGG-002: each row includes pct_of_total and yoy_change_pct."""

    def test_rows_have_pct_of_total(self, client):
        body = client.get(
            "/api/v1/aggregations", params={"group_by": "service"}
        ).json()
        for row in body["rows"]:
            assert "pct_of_total" in row

    def test_pct_of_total_sums_near_100(self, client):
        body = client.get(
            "/api/v1/aggregations", params={"group_by": "service"}
        ).json()
        pcts = [r["pct_of_total"] for r in body["rows"] if r["pct_of_total"] is not None]
        if pcts:
            total = sum(pcts)
            assert 99.0 <= total <= 101.0, f"pct_of_total sum: {total}"

    def test_rows_have_yoy_change(self, client):
        body = client.get(
            "/api/v1/aggregations", params={"group_by": "service"}
        ).json()
        for row in body["rows"]:
            assert "yoy_change_pct" in row

    def test_rows_have_row_count(self, client):
        body = client.get(
            "/api/v1/aggregations", params={"group_by": "service"}
        ).json()
        for row in body["rows"]:
            assert row["row_count"] > 0

    def test_rows_have_fy_totals(self, client):
        body = client.get(
            "/api/v1/aggregations", params={"group_by": "service"}
        ).json()
        for row in body["rows"]:
            assert "fy_totals" in row


class TestAggregateFilters:
    def test_filter_by_service(self, client):
        resp = client.get(
            "/api/v1/aggregations",
            params={"group_by": "exhibit_type", "service": "Army"},
        )
        assert resp.status_code == 200

    def test_filter_by_exhibit_type(self, client):
        resp = client.get(
            "/api/v1/aggregations",
            params={"group_by": "service", "exhibit_type": "r1"},
        )
        assert resp.status_code == 200

    def test_filter_by_nonexistent_service(self, client):
        body = client.get(
            "/api/v1/aggregations",
            params={"group_by": "service", "service": "NoSuchService"},
        ).json()
        assert len(body["rows"]) == 0

    def test_multiple_filters(self, client):
        resp = client.get(
            "/api/v1/aggregations",
            params={
                "group_by": "service",
                "exhibit_type": "r1",
            },
        )
        assert resp.status_code == 200


# ── Cache behavior ───────────────────────────────────────────────────────────


class TestAggregateCache:
    def test_repeated_calls_consistent(self, client):
        params = {"group_by": "service"}
        r1 = client.get("/api/v1/aggregations", params=params).json()
        r2 = client.get("/api/v1/aggregations", params=params).json()
        assert r1 == r2


# ── GET /api/v1/aggregations/hierarchy ───────────────────────────────────────


class TestHierarchy:
    def test_hierarchy_returns_200(self, client):
        resp = client.get("/api/v1/aggregations/hierarchy")
        assert resp.status_code == 200

    def test_hierarchy_structure(self, client):
        body = client.get("/api/v1/aggregations/hierarchy").json()
        assert "items" in body
        assert "grand_total" in body
        assert isinstance(body["items"], list)

    def test_hierarchy_items_have_fields(self, client):
        body = client.get("/api/v1/aggregations/hierarchy").json()
        if body["items"]:
            item = body["items"][0]
            assert "service" in item
            assert "amount" in item
            assert "pct_of_total" in item

    def test_hierarchy_filter_by_service(self, client):
        resp = client.get(
            "/api/v1/aggregations/hierarchy", params={"service": "Army"}
        )
        assert resp.status_code == 200

    def test_hierarchy_filter_nonexistent(self, client):
        body = client.get(
            "/api/v1/aggregations/hierarchy",
            params={"service": "NoSuchService"},
        ).json()
        assert body["items"] == []
        assert body["grand_total"] == 0
