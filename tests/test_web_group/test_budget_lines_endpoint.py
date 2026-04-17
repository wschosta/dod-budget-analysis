"""
Tests for api/routes/budget_lines.py — list and detail endpoints

Tests list_budget_lines and get_budget_line with in-memory database.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.models import FilterParams
from api.routes.budget_lines import list_budget_lines, get_budget_line
from utils.query import ALLOWED_SORT_COLUMNS as _ALLOWED_SORT


@pytest.fixture()
def db():
    """In-memory database with budget_lines table and sample data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY,
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
            amount_type TEXT,
            appropriation_code TEXT,
            appropriation_title TEXT,
            currency_year TEXT,
            amount_unit TEXT,
            amount_fy2024_actual REAL,
            amount_fy2025_enacted REAL,
            amount_fy2025_supplemental REAL,
            amount_fy2025_total REAL,
            amount_fy2026_request REAL,
            amount_fy2026_reconciliation REAL,
            amount_fy2026_total REAL,
            quantity_fy2024 REAL,
            quantity_fy2025 REAL,
            quantity_fy2026_request REAL,
            quantity_fy2026_total REAL
        )
    """)

    rows = [
        (
            1,
            "army_p1.xlsx",
            "p1",
            "Sheet1",
            "FY 2026",
            "3010",
            "Aircraft",
            "Army",
            "Tactical",
            None,
            "AH-64",
            "Apache Helicopter",
            "0207449A",
            "budget_authority",
            "3010",
            "Aircraft Procurement, Army",
            "then-year",
            "thousands",
            1000,
            900,
            0,
            900,
            1100,
            0,
            1100,
            10,
            12,
            15,
            15,
        ),
        (
            2,
            "navy_p1.xlsx",
            "p1",
            "Sheet1",
            "FY 2026",
            "1506",
            "Ships",
            "Navy",
            "Combat",
            None,
            "DDG-51",
            "Destroyer",
            "0204311N",
            "budget_authority",
            "1506",
            "Shipbuilding, Navy",
            "then-year",
            "thousands",
            5000,
            4500,
            0,
            4500,
            5500,
            0,
            5500,
            2,
            3,
            4,
            4,
        ),
        (
            3,
            "army_r1.xlsx",
            "r1",
            "Sheet1",
            "FY 2026",
            "3600",
            "RDT&E",
            "Army",
            "Research",
            None,
            None,
            None,
            "0602145A",
            "budget_authority",
            "3600",
            "RDT&E, Army",
            "then-year",
            "thousands",
            2000,
            1800,
            0,
            1800,
            2200,
            0,
            2200,
            None,
            None,
            None,
            None,
        ),
        (
            4,
            "army_p1.xlsx",
            "p1",
            "Sheet1",
            "FY 2025",
            "3010",
            "Aircraft",
            "Army",
            "Tactical",
            None,
            "UH-60",
            "Black Hawk",
            "0207452A",
            "budget_authority",
            "3010",
            "Aircraft Procurement, Army",
            "then-year",
            "thousands",
            800,
            750,
            0,
            750,
            0,
            0,
            0,
            5,
            6,
            0,
            0,
        ),
    ]

    conn.executemany(
        "INSERT INTO budget_lines VALUES (" + ",".join("?" * 29) + ")",
        rows,
    )

    # FTS5 virtual table for text search
    conn.execute("""
        CREATE VIRTUAL TABLE budget_lines_fts USING fts5(
            account_title, line_item_title, budget_activity_title,
            content='budget_lines', content_rowid='id',
            tokenize='unicode61'
        )
    """)
    conn.execute("""
        INSERT INTO budget_lines_fts(rowid, account_title, line_item_title,
            budget_activity_title)
        SELECT id, account_title, line_item_title, budget_activity_title
        FROM budget_lines
    """)

    conn.commit()
    yield conn
    conn.close()


def _list(db, **kwargs):
    """Call list_budget_lines with all required defaults."""
    filter_keys = {
        "fiscal_year",
        "service",
        "exhibit_type",
        "pe_number",
        "appropriation_code",
        "budget_type",
        "exclude_summary",
        "q",
        "min_amount",
        "max_amount",
    }
    filter_kw = {k: kwargs.pop(k, None) for k in list(kwargs) if k in filter_keys}
    if "exclude_summary" not in filter_kw:
        filter_kw["exclude_summary"] = False
    defaults = dict(
        filters=FilterParams(**filter_kw),
        sort_by="id",
        sort_dir="asc",
        limit=25,
        offset=0,
        conn=db,
    )
    defaults.update(kwargs)
    return list_budget_lines(**defaults)


class TestListBudgetLines:
    def test_default_returns_all(self, db):
        result = _list(db)
        assert result.total == 4
        assert len(result.items) == 4

    def test_limit(self, db):
        result = _list(db, limit=2)
        assert result.total == 4
        assert len(result.items) == 2

    def test_offset(self, db):
        result = _list(db, limit=2, offset=2)
        assert len(result.items) == 2
        assert result.offset == 2

    def test_filter_fiscal_year(self, db):
        result = _list(db, fiscal_year=["FY 2026"])
        assert result.total == 3
        for item in result.items:
            assert item.fiscal_year == "FY 2026"

    def test_filter_service(self, db):
        result = _list(db, service=["Army"])
        assert result.total == 3

    def test_filter_exhibit_type(self, db):
        result = _list(db, exhibit_type=["r1"])
        assert result.total == 1
        assert result.items[0].exhibit_type == "r1"

    def test_filter_pe_number(self, db):
        result = _list(db, pe_number=["0207449A"])
        assert result.total == 1

    def test_filter_appropriation_code(self, db):
        result = _list(db, appropriation_code=["1506"])
        assert result.total == 1

    def test_sort_by_amount(self, db):
        result = _list(db, sort_by="amount_fy2026_request", sort_dir="desc")
        amounts = [item.amount_fy2026_request for item in result.items]
        assert amounts == sorted(amounts, reverse=True)

    def test_invalid_sort_by(self, db):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _list(db, sort_by="invalid_column")
        assert exc_info.value.status_code == 400

    def test_combined_filters(self, db):
        result = _list(
            db,
            fiscal_year=["FY 2026"],
            service=["Army"],
            exhibit_type=["p1"],
        )
        assert result.total == 1
        assert result.items[0].line_item_title == "Apache Helicopter"

    def test_min_amount_filter(self, db):
        # Only rows with fy2026_request >= 2200 (RDT&E=2200, DDG=5500)
        result = _list(db, min_amount=2200.0)
        assert result.total == 2
        amounts = {item.amount_fy2026_request for item in result.items}
        assert all(a >= 2200 for a in amounts)

    def test_max_amount_filter(self, db):
        # Only rows with fy2026_request <= 1100 (Apache=1100, Black Hawk=0)
        result = _list(db, max_amount=1100.0)
        assert result.total == 2

    def test_min_max_range_filter(self, db):
        # Between 1000 and 3000 → Apache(1100) and RDT&E(2200)
        result = _list(db, min_amount=1000.0, max_amount=3000.0)
        assert result.total == 2
        for item in result.items:
            assert 1000 <= item.amount_fy2026_request <= 3000

    def test_pagination_metadata_first_page(self, db):
        """First page has correct page, page_count, has_next."""
        result = _list(db, limit=2, offset=0)
        assert result.page == 0
        assert result.page_count == 2  # 4 items / 2 per page
        assert result.has_next is True

    def test_pagination_metadata_last_page(self, db):
        """Last page has has_next=False."""
        result = _list(db, limit=2, offset=2)
        assert result.page == 1
        assert result.page_count == 2
        assert result.has_next is False

    def test_pagination_metadata_single_page(self, db):
        """When all items fit, page_count=1 and has_next=False."""
        result = _list(db, limit=25, offset=0)
        assert result.page == 0
        assert result.page_count == 1
        assert result.has_next is False

    def test_text_search(self, db):
        """q parameter searches FTS5 index for matching terms."""
        result = _list(db, q="Apache")
        assert result.total >= 1
        titles = [item.line_item_title for item in result.items]
        assert "Apache Helicopter" in titles

    def test_text_search_no_match(self, db):
        """Non-matching text search returns zero results."""
        result = _list(db, q="nonexistentterm")
        assert result.total == 0

    def test_text_search_combined_with_filter(self, db):
        """q works alongside other filters."""
        result = _list(db, q="Aircraft", fiscal_year=["FY 2026"])
        assert result.total >= 1


class TestGetBudgetLine:
    def test_existing_item(self, db):
        item = get_budget_line(1, conn=db)
        assert item.id == 1
        assert item.organization_name == "Army"
        assert item.line_item_title == "Apache Helicopter"
        assert item.amount_fy2026_request == 1100

    def test_not_found(self, db):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            get_budget_line(999, conn=db)
        assert exc_info.value.status_code == 404

    def test_detail_has_all_columns(self, db):
        item = get_budget_line(2, conn=db)
        assert item.appropriation_code == "1506"
        assert item.appropriation_title == "Shipbuilding, Navy"
        assert item.currency_year == "then-year"
        assert item.amount_unit == "thousands"


class TestRelatedPEs:
    """Phase 11 BLI→PE mappings surfaced on the detail endpoint."""

    def _with_bli_pe_map(self, db):
        db.executescript(
            """
            CREATE TABLE bli_pe_map (
                bli_key TEXT, pe_number TEXT, confidence REAL,
                source_file TEXT, page_number INTEGER,
                PRIMARY KEY (bli_key, pe_number)
            );
            CREATE TABLE pe_index (
                pe_number TEXT PRIMARY KEY,
                display_title TEXT
            );
            """
        )
        db.execute(
            "INSERT INTO pe_index (pe_number, display_title) VALUES (?, ?)",
            ("0305206N", "Navy ISR Program"),
        )
        return db

    def test_procurement_row_includes_related_pes(self, db):
        self._with_bli_pe_map(db)
        # Row id=1 is a P-1 row with account='3010', line_item='AH-64'.
        db.execute(
            "INSERT INTO bli_pe_map VALUES ('3010:AH-64', '0305206N', 0.9, 'p5.pdf', 42)"
        )
        item = get_budget_line(1, conn=db)
        assert len(item.related_pes) == 1
        rp = item.related_pes[0]
        assert rp.pe_number == "0305206N"
        assert rp.pe_title == "Navy ISR Program"
        assert rp.confidence == 0.9

    def test_non_procurement_row_has_no_related_pes(self, db):
        self._with_bli_pe_map(db)
        # Row id=3 is an R-1 row with account='3600'.  Insert a mapping that
        # would match on bli_key if we weren't filtering by exhibit_type.
        db.execute(
            "INSERT INTO bli_pe_map VALUES ('3600:', '0305206N', 0.9, 'p5.pdf', 1)"
        )
        item = get_budget_line(3, conn=db)
        assert item.related_pes == []

    def test_missing_bli_pe_map_is_not_an_error(self, db):
        """DBs enriched before Phase 11 don't have bli_pe_map — endpoint must still work."""
        item = get_budget_line(1, conn=db)
        assert item.related_pes == []


class TestAllowedSort:
    def test_includes_common_columns(self):
        assert "id" in _ALLOWED_SORT
        assert "amount_fy2026_request" in _ALLOWED_SORT
        assert "organization_name" in _ALLOWED_SORT
        assert "fiscal_year" in _ALLOWED_SORT
        assert "pe_number" in _ALLOWED_SORT
