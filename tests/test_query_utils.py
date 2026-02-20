"""Tests for utils/query.py — shared SQL query builder."""
import pytest
from utils.query import build_where_clause, build_order_clause


class TestBuildWhereClause:
    def test_no_filters(self):
        where, params = build_where_clause()
        assert where == ""
        assert params == []

    def test_fiscal_year_single(self):
        where, params = build_where_clause(fiscal_year=["FY2026"])
        assert "fiscal_year IN (?)" in where
        assert params == ["FY2026"]

    def test_fiscal_year_multiple(self):
        where, params = build_where_clause(fiscal_year=["FY2025", "FY2026"])
        assert "fiscal_year IN (?,?)" in where
        assert "FY2025" in params and "FY2026" in params

    def test_service_filter(self):
        where, params = build_where_clause(service=["Army"])
        assert "organization_name IN (?)" in where
        assert "Army" in params

    def test_exhibit_type_filter(self):
        where, params = build_where_clause(exhibit_type=["p1"])
        assert "exhibit_type IN (?)" in where
        assert "p1" in params

    def test_pe_number_filter(self):
        where, params = build_where_clause(pe_number=["0207449A"])
        assert "pe_number IN (?)" in where
        assert "0207449A" in params

    def test_appropriation_code_filter(self):
        where, params = build_where_clause(appropriation_code=["3010"])
        assert "appropriation_code IN (?)" in where
        assert "3010" in params

    def test_min_amount(self):
        where, params = build_where_clause(min_amount=1000.0)
        assert "amount_fy2026_request >= ?" in where
        assert 1000.0 in params

    def test_max_amount(self):
        where, params = build_where_clause(max_amount=5000.0)
        assert "amount_fy2026_request <= ?" in where
        assert 5000.0 in params

    def test_fts_ids_empty(self):
        where, params = build_where_clause(fts_ids=[])
        assert "1=0" in where

    def test_fts_ids_nonempty(self):
        where, params = build_where_clause(fts_ids=[1, 2, 3])
        assert "id IN (?,?,?)" in where
        assert [1, 2, 3] == params

    def test_combined_filters(self):
        where, params = build_where_clause(
            fiscal_year=["FY2026"],
            service=["Army"],
            exhibit_type=["p1"],
        )
        assert "fiscal_year IN" in where
        assert "organization_name IN" in where
        assert "exhibit_type IN" in where
        assert "FY2026" in params
        assert "Army" in params
        assert "p1" in params

    def test_where_prefix(self):
        where, _ = build_where_clause(fiscal_year=["FY2026"])
        assert where.startswith("WHERE ")

    def test_none_filters_ignored(self):
        where, params = build_where_clause(
            fiscal_year=None,
            service=None,
            exhibit_type=None,
        )
        assert where == ""
        assert params == []


class TestBuildOrderClause:
    def test_default_asc(self):
        order = build_order_clause("id", "asc")
        assert order == "ORDER BY id ASC"

    def test_desc(self):
        order = build_order_clause("id", "desc")
        assert order == "ORDER BY id DESC"

    def test_invalid_sort_uses_default(self):
        order = build_order_clause("malicious; DROP TABLE", "asc")
        assert "ORDER BY id ASC" == order

    def test_custom_allowed_sorts(self):
        order = build_order_clause("name", "asc", allowed_sorts={"name", "age"})
        assert order == "ORDER BY name ASC"

    def test_custom_default_sort(self):
        order = build_order_clause("invalid", "asc", default_sort="fiscal_year")
        assert "fiscal_year" in order
