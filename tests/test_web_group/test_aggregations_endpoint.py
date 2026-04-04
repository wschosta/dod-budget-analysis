"""Tests for api/routes/aggregations.py — aggregation and hierarchy endpoints."""

import pytest


class TestAggregate:
    @pytest.mark.parametrize("group_by", [
        "service", "fiscal_year", "exhibit_type",
        "budget_type", "appropriation", "budget_activity",
    ])
    def test_valid_group_by(self, client, group_by):
        resp = client.get("/api/v1/aggregations", params={"group_by": group_by})
        assert resp.status_code == 200
        body = resp.json()
        assert body["group_by"] == group_by
        assert isinstance(body["rows"], list)

    def test_service_group_has_rows(self, client):
        body = client.get(
            "/api/v1/aggregations", params={"group_by": "service"}
        ).json()
        assert len(body["rows"]) > 0

    def test_invalid_group_by_returns_400(self, client):
        resp = client.get("/api/v1/aggregations", params={"group_by": "invalid"})
        assert resp.status_code == 400

    def test_missing_group_by_returns_422(self, client):
        resp = client.get("/api/v1/aggregations")
        assert resp.status_code == 422


class TestAggregateRowFields:
    @pytest.fixture()
    def service_rows(self, client):
        return client.get(
            "/api/v1/aggregations", params={"group_by": "service"}
        ).json()["rows"]

    def test_rows_have_pct_of_total(self, service_rows):
        for row in service_rows:
            assert "pct_of_total" in row

    def test_pct_of_total_sums_near_100(self, service_rows):
        pcts = [r["pct_of_total"] for r in service_rows if r["pct_of_total"] is not None]
        if pcts:
            total = sum(pcts)
            assert 99.0 <= total <= 101.0, f"pct_of_total sum: {total}"

    def test_rows_have_yoy_change(self, service_rows):
        for row in service_rows:
            assert "yoy_change_pct" in row

    def test_rows_have_row_count(self, service_rows):
        for row in service_rows:
            assert row["row_count"] > 0

    def test_rows_have_fy_totals(self, service_rows):
        for row in service_rows:
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
            params={"group_by": "service", "exhibit_type": "r1"},
        )
        assert resp.status_code == 200


class TestAggregateCache:
    def test_repeated_calls_consistent(self, client):
        params = {"group_by": "service"}
        r1 = client.get("/api/v1/aggregations", params=params).json()
        r2 = client.get("/api/v1/aggregations", params=params).json()
        assert r1 == r2


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
