"""
Tests for api/routes/budget_lines.py — _build_where() SQL builder

Verifies that the WHERE clause builder produces correct SQL fragments
and parameter lists for various filter combinations.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.routes.budget_lines import _build_where


class TestBuildWhereNoFilters:
    def test_all_none(self):
        where, params = _build_where(None, None, None, None, None)
        assert where == ""
        assert params == []

    def test_all_empty_lists(self):
        where, params = _build_where([], [], [], [], [])
        assert where == ""
        assert params == []


class TestBuildWhereFiscalYear:
    def test_single_fiscal_year(self):
        where, params = _build_where(["FY 2026"], None, None, None, None)
        assert "fiscal_year IN (?)" in where
        assert params == ["FY 2026"]

    def test_multiple_fiscal_years(self):
        where, params = _build_where(["FY 2025", "FY 2026"], None, None, None, None)
        assert "fiscal_year IN (?,?)" in where
        assert params == ["FY 2025", "FY 2026"]


class TestBuildWhereService:
    def test_single_service(self):
        where, params = _build_where(None, ["Army"], None, None, None)
        assert "organization_name IN (?)" in where
        assert params == ["Army"]

    def test_multiple_services(self):
        where, params = _build_where(None, ["Army", "Navy"], None, None, None)
        assert "organization_name IN (?,?)" in where
        assert len(params) == 2
        assert "Army" in params
        assert "Navy" in params


class TestBuildWhereExhibitType:
    def test_single_exhibit(self):
        where, params = _build_where(None, None, ["p1"], None, None)
        assert "exhibit_type IN (?)" in where
        assert params == ["p1"]


class TestBuildWherePeNumber:
    def test_single_pe(self):
        where, params = _build_where(None, None, None, ["0602145A"], None)
        assert "pe_number IN (?)" in where
        assert params == ["0602145A"]


class TestBuildWhereAppropriationCode:
    def test_single_code(self):
        where, params = _build_where(None, None, None, None, ["2035"])
        assert "appropriation_code IN (?)" in where
        assert params == ["2035"]


class TestBuildWhereCombined:
    def test_two_filters(self):
        where, params = _build_where(["FY 2026"], ["Army"], None, None, None)
        assert "WHERE" in where
        assert "AND" in where
        assert len(params) == 2

    def test_all_filters(self):
        where, params = _build_where(
            ["FY 2026"], ["Army"], ["p1"], ["0602145A"], ["2035"]
        )
        assert where.count("AND") == 4
        assert len(params) == 5
