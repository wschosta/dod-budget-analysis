"""
Tests for api/routes/frontend.py — helper functions

Tests _get_services, _get_exhibit_types, _get_fiscal_years, _parse_filters,
_query_results, and template initialization using in-memory SQLite databases.
"""
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.routes.frontend import (
    _get_services,
    _get_exhibit_types,
    _get_fiscal_years,
    _parse_filters,
    _query_results,
    set_templates,
    _tmpl,
    _services_cache,
    _exhibit_types_cache,
    _fiscal_years_cache,
)


@pytest.fixture(autouse=True)
def _clear_frontend_caches():
    """Clear module-level TTL caches between tests.

    The caches key on id(conn), which Python may reuse after close(),
    causing a later test to hit stale cached results from a different schema.
    """
    _services_cache.clear()
    _exhibit_types_cache.clear()
    _fiscal_years_cache.clear()
    yield
    _services_cache.clear()
    _exhibit_types_cache.clear()
    _fiscal_years_cache.clear()


@pytest.fixture()
def db():
    """In-memory database with budget_lines and reference tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT,
            exhibit_type TEXT,
            sheet_name TEXT,
            fiscal_year TEXT,
            account TEXT,
            account_title TEXT,
            organization_name TEXT,
            budget_activity_title TEXT,
            sub_activity_title TEXT,
            line_item TEXT,
            line_item_title TEXT,
            pe_number TEXT,
            appropriation_code TEXT,
            amount_fy2024_actual REAL,
            amount_fy2025_enacted REAL,
            amount_fy2025_total REAL,
            amount_fy2026_request REAL,
            amount_fy2026_total REAL,
            amount_type TEXT
        );

        CREATE TABLE services_agencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            category TEXT NOT NULL
        );

        CREATE TABLE exhibit_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            exhibit_class TEXT NOT NULL,
            description TEXT
        );

        INSERT INTO budget_lines (source_file, exhibit_type, fiscal_year,
            organization_name, amount_fy2026_request)
        VALUES
            ('army_p1.xlsx', 'p1', '2026', 'Army', 100000),
            ('army_r1.xlsx', 'r1', '2026', 'Army', 200000),
            ('navy_p1.xlsx', 'p1', '2026', 'Navy', 150000),
            ('navy_o1.xlsx', 'o1', '2025', 'Navy', 80000);

        INSERT INTO services_agencies (code, full_name, category)
        VALUES
            ('Army', 'Department of the Army', 'Military Department'),
            ('Navy', 'Department of the Navy', 'Military Department');

        INSERT INTO exhibit_types (code, display_name, exhibit_class)
        VALUES
            ('p1', 'P-1 Procurement Summary', 'procurement'),
            ('r1', 'R-1 RDT&E Summary', 'rdte');
    """)
    conn.commit()
    yield conn
    conn.close()


# ── _get_services ─────────────────────────────────────────────────────────────

class TestGetServices:
    def test_returns_from_reference_table(self, db):
        services = _get_services(db)
        assert len(services) == 2
        codes = {s["code"] for s in services}
        assert "Army" in codes
        assert "Navy" in codes

    def test_fallback_to_budget_lines(self):
        """Falls back to DISTINCT organization_name when reference table missing."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE budget_lines (
                id INTEGER PRIMARY KEY,
                organization_name TEXT
            )
        """)
        conn.execute("INSERT INTO budget_lines (organization_name) VALUES ('Army')")
        conn.execute("INSERT INTO budget_lines (organization_name) VALUES ('Navy')")
        conn.execute("INSERT INTO budget_lines (organization_name) VALUES ('Army')")
        conn.commit()
        services = _get_services(conn)
        codes = {s["code"] for s in services}
        assert "Army" in codes
        assert "Navy" in codes
        conn.close()


# ── _get_exhibit_types ────────────────────────────────────────────────────────

class TestGetExhibitTypes:
    def test_returns_from_reference_table(self, db):
        exhibits = _get_exhibit_types(db)
        assert len(exhibits) == 2
        codes = {e["code"] for e in exhibits}
        assert "p1" in codes
        assert "r1" in codes

    def test_fallback_to_budget_lines(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE budget_lines (
                id INTEGER PRIMARY KEY,
                exhibit_type TEXT
            )
        """)
        conn.execute("INSERT INTO budget_lines (exhibit_type) VALUES ('p1')")
        conn.execute("INSERT INTO budget_lines (exhibit_type) VALUES ('o1')")
        conn.commit()
        exhibits = _get_exhibit_types(conn)
        codes = {e["code"] for e in exhibits}
        assert "p1" in codes
        assert "o1" in codes
        conn.close()


# ── _get_fiscal_years ─────────────────────────────────────────────────────────

class TestGetFiscalYears:
    def test_returns_grouped_years(self, db):
        years = _get_fiscal_years(db)
        fy_values = {y["fiscal_year"] for y in years}
        assert "2026" in fy_values
        assert "2025" in fy_values

    def test_includes_row_count(self, db):
        years = _get_fiscal_years(db)
        fy2026 = next(y for y in years if y["fiscal_year"] == "2026")
        assert fy2026["row_count"] == 3


# ── _parse_filters ────────────────────────────────────────────────────────────

class TestParseFilters:
    def _mock_request(self, query_string=""):
        """Create a mock Request with the given query string."""
        from starlette.datastructures import QueryParams
        request = MagicMock()
        request.query_params = QueryParams(query_string)
        return request

    def test_defaults(self):
        req = self._mock_request("")
        filters = _parse_filters(req)
        assert filters["q"] == ""
        assert filters["sort_by"] == "id"
        assert filters["sort_dir"] == "asc"
        assert filters["page"] == 1

    def test_query_param(self):
        req = self._mock_request("q=missile+defense")
        filters = _parse_filters(req)
        assert filters["q"] == "missile defense"

    def test_sort_params(self):
        req = self._mock_request("sort_by=amount_fy2026_request&sort_dir=desc")
        filters = _parse_filters(req)
        assert filters["sort_by"] == "amount_fy2026_request"
        assert filters["sort_dir"] == "desc"

    def test_page_minimum(self):
        req = self._mock_request("page=0")
        filters = _parse_filters(req)
        assert filters["page"] == 1

    def test_fiscal_year_list(self):
        req = self._mock_request("fiscal_year=2025&fiscal_year=2026")
        filters = _parse_filters(req)
        assert filters["fiscal_year"] == ["2025", "2026"]


# ── _query_results ────────────────────────────────────────────────────────────

class TestQueryResults:
    def test_returns_items(self, db):
        filters = {
            "q": "", "fiscal_year": [], "service": [], "exhibit_type": [],
            "pe_number": [], "sort_by": "id", "sort_dir": "asc", "page": 1,
        }
        result = _query_results(filters, db)
        assert "items" in result
        assert "total" in result
        assert result["total"] == 4

    def test_pagination(self, db):
        filters = {
            "q": "", "fiscal_year": [], "service": [], "exhibit_type": [],
            "pe_number": [], "sort_by": "id", "sort_dir": "asc", "page": 1,
        }
        result = _query_results(filters, db, page_size=2)
        assert len(result["items"]) == 2
        assert result["total_pages"] == 2

    def test_filter_by_fiscal_year(self, db):
        filters = {
            "q": "", "fiscal_year": ["2025"], "service": [], "exhibit_type": [],
            "pe_number": [], "sort_by": "id", "sort_dir": "asc", "page": 1,
        }
        result = _query_results(filters, db)
        assert result["total"] == 1

    def test_sort_direction(self, db):
        filters = {
            "q": "", "fiscal_year": [], "service": [], "exhibit_type": [],
            "pe_number": [], "sort_by": "id", "sort_dir": "desc", "page": 1,
        }
        result = _query_results(filters, db)
        ids = [item["id"] for item in result["items"]]
        assert ids == sorted(ids, reverse=True)


# ── set_templates / _tmpl ─────────────────────────────────────────────────────

class TestTemplateInit:
    def test_tmpl_raises_when_not_set(self):
        set_templates(None)
        with pytest.raises(RuntimeError, match="Templates not initialised"):
            _tmpl()

    def test_set_and_get_templates(self):
        mock_templates = MagicMock()
        set_templates(mock_templates)
        assert _tmpl() is mock_templates
        # Clean up
        set_templates(None)
