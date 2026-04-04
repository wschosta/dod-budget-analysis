"""
Tests for api/routes/reference.py and api/routes/aggregations.py

Tests reference data endpoints and aggregation logic with in-memory databases.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.routes.reference import (
    list_services,
    list_exhibit_types,
    list_fiscal_years,
    list_appropriations,
    list_budget_types,
)
from api.models import FilterParams
from api.routes.aggregations import (
    aggregate,
    hierarchy,
    warm_caches,
    _ALLOWED_GROUPS,
    _agg_cache,
    _hierarchy_cache,
)


@pytest.fixture(autouse=True)
def _clear_caches():
    """Clear aggregation caches before each test to prevent cross-test pollution."""
    _agg_cache.clear()
    _hierarchy_cache.clear()
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
            appropriation_title TEXT,
            budget_activity_title TEXT,
            budget_type TEXT
        );
        INSERT INTO budget_lines VALUES (1, 'FY 2026', 'Army', 'p1', 800, 900, 1000, '3010', 'Aircraft Procurement', 'Aircraft', 'Procurement');
        INSERT INTO budget_lines VALUES (2, 'FY 2026', 'Army', 'r1', 1600, 1800, 2000, '3600', 'RDT&E', 'Missiles', 'RDT&E');
        INSERT INTO budget_lines VALUES (3, 'FY 2026', 'Navy', 'p1', 300, 400, 500, '3010', 'Aircraft Procurement', 'Ships', 'Procurement');
        INSERT INTO budget_lines VALUES (4, 'FY 2025', 'Army', 'p1', 1300, 1400, 1500, '3010', 'Aircraft Procurement', 'Aircraft', 'Procurement');
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


class TestListAppropriations:
    def test_returns_codes_with_counts(self, db_with_ref_tables):
        import json

        resp = list_appropriations(db_with_ref_tables)
        items = json.loads(resp.body)
        assert len(items) >= 1
        assert all("code" in item for item in items)
        assert all("row_count" in item for item in items)

    def test_has_title(self, db_with_ref_tables):
        import json

        resp = list_appropriations(db_with_ref_tables)
        items = json.loads(resp.body)
        assert any(item.get("title") is not None for item in items)


class TestListBudgetTypes:
    def test_returns_types_with_counts(self, db_with_ref_tables):
        import json

        resp = list_budget_types(db_with_ref_tables)
        items = json.loads(resp.body)
        assert len(items) >= 1
        types = {item["budget_type"] for item in items}
        assert "Procurement" in types


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
            group_by="service",
            filters=FilterParams(),
            conn=db_with_ref_tables,
        )
        assert result.group_by == "service"
        assert len(result.rows) == 2  # Army and Navy

    def test_group_by_fiscal_year(self, db_with_ref_tables):
        result = aggregate(
            group_by="fiscal_year",
            filters=FilterParams(),
            conn=db_with_ref_tables,
        )
        assert len(result.rows) == 2  # FY 2025 and FY 2026

    def test_group_by_exhibit_type(self, db_with_ref_tables):
        result = aggregate(
            group_by="exhibit_type",
            filters=FilterParams(),
            conn=db_with_ref_tables,
        )
        assert len(result.rows) == 2  # p1 and r1

    def test_filter_by_fiscal_year(self, db_with_ref_tables):
        result = aggregate(
            group_by="service",
            filters=FilterParams(fiscal_year=["FY 2026"]),
            conn=db_with_ref_tables,
        )
        # Only FY 2026 rows: Army (2) and Navy (1)
        assert len(result.rows) == 2

    def test_filter_by_service(self, db_with_ref_tables):
        result = aggregate(
            group_by="exhibit_type",
            filters=FilterParams(service=["Army"]),
            conn=db_with_ref_tables,
        )
        # Army has p1 and r1
        assert len(result.rows) == 2

    def test_filter_by_exhibit_type(self, db_with_ref_tables):
        result = aggregate(
            group_by="service",
            filters=FilterParams(exhibit_type=["p1"]),
            conn=db_with_ref_tables,
        )
        # p1: Army and Navy
        assert len(result.rows) == 2

    def test_combined_filters(self, db_with_ref_tables):
        result = aggregate(
            group_by="service",
            filters=FilterParams(
                fiscal_year=["FY 2026"], service=["Army"], exhibit_type=["p1"]
            ),
            conn=db_with_ref_tables,
        )
        assert len(result.rows) == 1
        assert result.rows[0].group_value == "Army"
        assert result.rows[0].total_fy2026_request == 1000

    def test_invalid_group_by(self, db_with_ref_tables):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            aggregate(
                group_by="invalid",
                filters=FilterParams(),
                conn=db_with_ref_tables,
            )
        assert exc_info.value.status_code == 400

    def test_empty_result(self, db_with_ref_tables):
        result = aggregate(
            group_by="service",
            filters=FilterParams(fiscal_year=["FY 2030"]),
            conn=db_with_ref_tables,
        )
        assert len(result.rows) == 0

    def test_rows_with_amount_present(self, db_with_ref_tables):
        """Each aggregation row includes rows_with_amount count."""
        result = aggregate(
            group_by="service",
            filters=FilterParams(),
            conn=db_with_ref_tables,
        )
        for row in result.rows:
            assert row.rows_with_amount is not None
            assert row.rows_with_amount <= row.row_count

    def test_rows_with_amount_excludes_nulls(self, db_with_ref_tables):
        """rows_with_amount excludes rows with NULL latest-FY amount."""
        # Add a row with NULL amount_fy2026_request
        db_with_ref_tables.execute(
            "INSERT INTO budget_lines VALUES (99, 'FY 2026', 'Army', 'p1',"
            " 100, 200, NULL, '3010', 'Test Approp', 'Test', 'Procurement')"
        )
        result = aggregate(
            group_by="service",
            filters=FilterParams(),
            conn=db_with_ref_tables,
        )
        army_row = next(r for r in result.rows if r.group_value == "Army")
        # Army now has 4 rows (3 original + 1 NULL) but only 3 with amount
        assert army_row.row_count == 4
        assert army_row.rows_with_amount == 3

    def test_group_by_budget_type(self, db_with_ref_tables):
        """group_by=budget_type returns groups per budget type."""
        result = aggregate(
            group_by="budget_type",
            filters=FilterParams(),
            conn=db_with_ref_tables,
        )
        types = {r.group_value for r in result.rows}
        assert "Procurement" in types
        assert "RDT&E" in types

    def test_filter_by_appropriation_code(self, db_with_ref_tables):
        """appropriation_code filter narrows to matching budget lines."""
        result = aggregate(
            group_by="service",
            filters=FilterParams(appropriation_code=["3010"]),
            conn=db_with_ref_tables,
        )
        # Only rows with appropriation_code=3010 (3 of 4 rows)
        total_rows = sum(r.row_count for r in result.rows)
        assert total_rows == 3


# ---------------------------------------------------------------------------
# OPT-AGG-002: Hierarchy endpoint — dynamic latest-column tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_hierarchy():
    """DB with budget_lines, org, approp, and two FY amount columns."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY,
            fiscal_year TEXT,
            organization_name TEXT,
            exhibit_type TEXT,
            line_item_title TEXT,
            pe_number TEXT,
            appropriation_code TEXT,
            appropriation_title TEXT,
            budget_type TEXT,
            amount_fy2025_enacted REAL,
            amount_fy2026_request REAL
        );
        INSERT INTO budget_lines VALUES
          (1, 'FY 2026', 'Army', 'p1', 'Program A', 'PE0001', '3010', 'Aircraft Proc', 'Procurement', 900, 1000),
          (2, 'FY 2026', 'Navy', 'p1', 'Program B', 'PE0002', '3415', 'Ship Proc',     'Procurement', 400, 500),
          (3, 'FY 2026', 'Army', 'r1', 'Program C', 'PE0003', '3600', 'RDT&E',         'RDT&E',       1800, 2000),
          (4, 'FY 2026', 'Army', 'p1', 'Program D', NULL,     NULL,   NULL,            NULL,          NULL,  NULL);
    """)
    yield conn
    conn.close()


@pytest.fixture()
def db_hierarchy_fy2027():
    """DB that only has FY2027 data — no fy2026 column at all."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY,
            fiscal_year TEXT,
            organization_name TEXT,
            exhibit_type TEXT,
            line_item_title TEXT,
            pe_number TEXT,
            appropriation_code TEXT,
            appropriation_title TEXT,
            budget_type TEXT,
            amount_fy2026_enacted REAL,
            amount_fy2027_request REAL
        );
        INSERT INTO budget_lines VALUES
          (1, 'FY 2027', 'Army', 'p1', 'Program A', 'PE0001', '3010', 'Aircraft Proc', 'Procurement', 950, 1100),
          (2, 'FY 2027', 'Navy', 'p1', 'Program B', 'PE0002', '3415', 'Ship Proc',     'Procurement', 420, 550);
    """)
    yield conn
    conn.close()


class TestHierarchyDynamicColumns:
    """OPT-AGG-002: hierarchy endpoint uses latest available FY column."""

    def test_returns_items_with_amount(self, db_hierarchy):
        result = hierarchy(
            fiscal_year=None, service=None, exhibit_type=None, conn=db_hierarchy
        )
        assert result["grand_total"] > 0
        assert len(result["items"]) >= 1

    def test_excludes_null_amount_rows(self, db_hierarchy):
        """Rows with NULL latest-FY amount are excluded (HAVING > 0)."""
        result = hierarchy(
            fiscal_year=None, service=None, exhibit_type=None, conn=db_hierarchy
        )
        # Program D has NULL amount_fy2026_request — should not appear
        titles = [item["program"] for item in result["items"]]
        assert "Program D" not in titles

    def test_uses_latest_column_for_fy2027_db(self, db_hierarchy_fy2027):
        """When only fy2027 column exists, hierarchy uses it instead of fy2026."""
        result = hierarchy(
            fiscal_year=None, service=None, exhibit_type=None, conn=db_hierarchy_fy2027
        )
        # Should succeed and return items using amount_fy2027_request
        assert result["grand_total"] > 0
        assert len(result["items"]) == 2
        # Totals should reflect fy2027 amounts (1100 + 550)
        assert result["grand_total"] == pytest.approx(1650.0)

    def test_prior_column_used_for_prev_amount(self, db_hierarchy):
        """prev_amount reflects the prior FY column (not NULL)."""
        result = hierarchy(
            fiscal_year=None, service=None, exhibit_type=None, conn=db_hierarchy
        )
        items = {item["program"]: item for item in result["items"]}
        assert items["Program A"]["prev_amount"] == pytest.approx(900.0)
        assert items["Program B"]["prev_amount"] == pytest.approx(400.0)

    def test_filter_by_service(self, db_hierarchy):
        result = hierarchy(
            fiscal_year=None, service="Army", exhibit_type=None, conn=db_hierarchy
        )
        services = {item["service"] for item in result["items"]}
        assert services == {"Army"}

    def test_filter_by_fiscal_year(self, db_hierarchy):
        result = hierarchy(
            fiscal_year="FY 2026", service=None, exhibit_type=None, conn=db_hierarchy
        )
        assert len(result["items"]) >= 1

    def test_pct_of_total_sums_to_100(self, db_hierarchy):
        result = hierarchy(
            fiscal_year=None, service=None, exhibit_type=None, conn=db_hierarchy
        )
        total_pct = sum(
            item["pct_of_total"]
            for item in result["items"]
            if item["pct_of_total"] is not None
        )
        assert abs(total_pct - 100.0) < 0.1

    def test_empty_table(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE budget_lines (
                id INTEGER PRIMARY KEY,
                organization_name TEXT,
                fiscal_year TEXT,
                exhibit_type TEXT,
                line_item_title TEXT,
                pe_number TEXT,
                appropriation_code TEXT,
                appropriation_title TEXT,
                amount_fy2026_request REAL
            )
        """)
        result = hierarchy(fiscal_year=None, service=None, exhibit_type=None, conn=conn)
        assert result["grand_total"] == 0
        assert result["items"] == []
        conn.close()


class TestWarmCaches:
    """OPT-AGG-002: warm_caches helper."""

    def test_nonexistent_db_is_safe(self, tmp_path):
        """warm_caches does nothing when DB file doesn't exist."""
        warm_caches(tmp_path / "nonexistent.sqlite")  # must not raise

    def test_valid_db_populates_agg_cache(self, tmp_path):
        """warm_caches pre-populates the aggregation cache."""
        from api.routes.aggregations import _agg_cache

        db_file = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_file))
        conn.execute("""
            CREATE TABLE budget_lines (
                id INTEGER PRIMARY KEY,
                fiscal_year TEXT,
                organization_name TEXT,
                exhibit_type TEXT,
                appropriation_code TEXT,
                budget_activity_title TEXT,
                budget_type TEXT,
                amount_fy2026_request REAL
            )
        """)
        conn.execute(
            "INSERT INTO budget_lines VALUES (1, 'FY 2026', 'Army', 'p1', '3010', 'Aircraft', 'Procurement', 1000)"
        )
        conn.commit()
        conn.close()

        _agg_cache.clear()
        warm_caches(db_file)

        # At least one cache entry should have been added
        assert _agg_cache.stats()["size"] > 0

    def test_corrupt_db_is_safe(self, tmp_path):
        """warm_caches logs a warning and returns if DB is unreadable."""
        bad_db = tmp_path / "corrupt.sqlite"
        bad_db.write_bytes(b"not a real sqlite db")
        warm_caches(bad_db)  # must not raise
