"""
Tests for api/routes/reference.py and api/routes/aggregations.py

Tests reference data endpoints and aggregation logic with in-memory databases.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.routes.reference import list_services, list_exhibit_types, list_fiscal_years
from api.routes.aggregations import aggregate, _ALLOWED_GROUPS


@pytest.fixture(autouse=True)
def _clear_column_cache():
    """No-op: column cache was removed in favor of direct PRAGMA table_info.

    Kept as autouse fixture placeholder so test ordering stays consistent.
    """
    yield


@pytest.fixture()
def db_with_ref_tables():
    """Database with reference tables populated."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE services_agencies (
            code TEXT PRIMARY KEY,
            full_name TEXT,
            category TEXT
        );
        INSERT INTO services_agencies VALUES ('A', 'Army', 'military');
        INSERT INTO services_agencies VALUES ('N', 'Navy', 'military');

        CREATE TABLE exhibit_types (
            code TEXT PRIMARY KEY,
            display_name TEXT,
            exhibit_class TEXT,
            description TEXT
        );
        INSERT INTO exhibit_types VALUES ('p1', 'Procurement (P-1)', 'procurement', 'P-1 exhibit');
        INSERT INTO exhibit_types VALUES ('r1', 'R&D (R-1)', 'rdte', 'R-1 exhibit');

        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY,
            fiscal_year TEXT,
            organization_name TEXT,
            exhibit_type TEXT,
            amount_fy2024_actual REAL,
            amount_fy2025_enacted REAL,
            amount_fy2026_request REAL,
            appropriation_code TEXT,
            budget_activity_title TEXT
        );
        INSERT INTO budget_lines VALUES (1, 'FY 2026', 'Army', 'p1', 800, 900, 1000, '3010', 'Aircraft');
        INSERT INTO budget_lines VALUES (2, 'FY 2026', 'Army', 'r1', 1600, 1800, 2000, '3600', 'Missiles');
        INSERT INTO budget_lines VALUES (3, 'FY 2026', 'Navy', 'p1', 300, 400, 500, '3010', 'Ships');
        INSERT INTO budget_lines VALUES (4, 'FY 2025', 'Army', 'p1', 1300, 1400, 1500, '3010', 'Aircraft');
    """)
    yield conn
    conn.close()


@pytest.fixture()
def db_no_ref_tables():
    """Database without reference tables — tests fallback paths."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY,
            fiscal_year TEXT,
            organization_name TEXT,
            exhibit_type TEXT,
            amount_fy2026_request REAL,
            amount_fy2025_enacted REAL,
            amount_fy2024_actual REAL,
            appropriation_code TEXT,
            budget_activity_title TEXT
        );
        INSERT INTO budget_lines VALUES (1, 'FY 2026', 'Army', 'p1', 1000, 900, 800, '3010', 'Aircraft');
        INSERT INTO budget_lines VALUES (2, 'FY 2026', 'Navy', 'r1', 2000, 1800, 1600, '3600', 'R&D');
    """)
    yield conn
    conn.close()


class TestListServices:
    def test_with_ref_table(self, db_with_ref_tables):
        resp = list_services(db_with_ref_tables)
        data = resp.body
        import json
        items = json.loads(data)
        assert len(items) == 2
        codes = {r["code"] for r in items}
        assert "A" in codes
        assert "N" in codes

    def test_fallback_without_ref_table(self, db_no_ref_tables):
        resp = list_services(db_no_ref_tables)
        import json
        items = json.loads(resp.body)
        assert len(items) == 2
        codes = {r["code"] for r in items}
        assert "Army" in codes
        assert "Navy" in codes

    def test_cache_header(self, db_with_ref_tables):
        resp = list_services(db_with_ref_tables)
        assert resp.headers.get("cache-control") == "max-age=3600"


class TestListExhibitTypes:
    def test_with_ref_table(self, db_with_ref_tables):
        import json
        resp = list_exhibit_types(db_with_ref_tables)
        items = json.loads(resp.body)
        assert len(items) == 2
        codes = {r["code"] for r in items}
        assert "p1" in codes
        assert "r1" in codes

    def test_fallback_without_ref_table(self, db_no_ref_tables):
        import json
        resp = list_exhibit_types(db_no_ref_tables)
        items = json.loads(resp.body)
        assert len(items) == 2

    def test_has_description_field(self, db_with_ref_tables):
        import json
        items = json.loads(list_exhibit_types(db_with_ref_tables).body)
        assert items[0]["description"] is not None


class TestListFiscalYears:
    def test_returns_years_with_counts(self, db_with_ref_tables):
        import json
        resp = list_fiscal_years(db_with_ref_tables)
        items = json.loads(resp.body)
        assert len(items) == 2  # FY 2025 and FY 2026
        fy26 = next(r for r in items if r["fiscal_year"] == "FY 2026")
        assert fy26["row_count"] == 3

    def test_empty_table(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE budget_lines (
                id INTEGER PRIMARY KEY,
                fiscal_year TEXT,
                organization_name TEXT,
                exhibit_type TEXT,
                amount_fy2026_request REAL,
                amount_fy2025_enacted REAL,
                amount_fy2024_actual REAL
            )
        """)
        import json
        resp = list_fiscal_years(conn)
        items = json.loads(resp.body)
        assert items == []
        conn.close()


class TestAllowedGroups:
    def test_has_expected_keys(self):
        assert "service" in _ALLOWED_GROUPS
        assert "fiscal_year" in _ALLOWED_GROUPS
        assert "exhibit_type" in _ALLOWED_GROUPS
        assert "appropriation" in _ALLOWED_GROUPS
        assert "budget_activity" in _ALLOWED_GROUPS


class TestAggregate:
    def test_group_by_service(self, db_with_ref_tables):
        result = aggregate(
            group_by="service", fiscal_year=None, service=None,
            exhibit_type=None, conn=db_with_ref_tables,
        )
        assert result.group_by == "service"
        assert len(result.rows) == 2  # Army and Navy

    def test_group_by_fiscal_year(self, db_with_ref_tables):
        result = aggregate(
            group_by="fiscal_year", fiscal_year=None, service=None,
            exhibit_type=None, conn=db_with_ref_tables,
        )
        assert len(result.rows) == 2  # FY 2025 and FY 2026

    def test_group_by_exhibit_type(self, db_with_ref_tables):
        result = aggregate(
            group_by="exhibit_type", fiscal_year=None, service=None,
            exhibit_type=None, conn=db_with_ref_tables,
        )
        assert len(result.rows) == 2  # p1 and r1

    def test_filter_by_fiscal_year(self, db_with_ref_tables):
        result = aggregate(
            group_by="service", fiscal_year=["FY 2026"], service=None,
            exhibit_type=None, conn=db_with_ref_tables,
        )
        # Only FY 2026 rows: Army (2) and Navy (1)
        assert len(result.rows) == 2

    def test_filter_by_service(self, db_with_ref_tables):
        result = aggregate(
            group_by="exhibit_type", fiscal_year=None, service=["Army"],
            exhibit_type=None, conn=db_with_ref_tables,
        )
        # Army has p1 and r1
        assert len(result.rows) == 2

    def test_filter_by_exhibit_type(self, db_with_ref_tables):
        result = aggregate(
            group_by="service", fiscal_year=None, service=None,
            exhibit_type=["p1"], conn=db_with_ref_tables,
        )
        # p1: Army and Navy
        assert len(result.rows) == 2

    def test_combined_filters(self, db_with_ref_tables):
        result = aggregate(
            group_by="service", fiscal_year=["FY 2026"],
            service=["Army"], exhibit_type=["p1"],
            conn=db_with_ref_tables,
        )
        assert len(result.rows) == 1
        assert result.rows[0].group_value == "Army"
        assert result.rows[0].total_fy2026_request == 1000

    def test_invalid_group_by(self, db_with_ref_tables):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            aggregate(
                group_by="invalid", fiscal_year=None, service=None,
                exhibit_type=None, conn=db_with_ref_tables,
            )
        assert exc_info.value.status_code == 400

    def test_empty_result(self, db_with_ref_tables):
        result = aggregate(
            group_by="service", fiscal_year=["FY 2030"], service=None,
            exhibit_type=None, conn=db_with_ref_tables,
        )
        assert len(result.rows) == 0
