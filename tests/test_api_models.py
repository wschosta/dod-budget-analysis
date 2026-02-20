"""
Tests for api/models.py — Pydantic model validation

Verifies that Pydantic models correctly validate, serialize, and handle
optional fields and edge cases.
"""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.models import (
    ServiceOut,
    ExhibitTypeOut,
    FiscalYearOut,
    BudgetLineOut,
    BudgetLineDetailOut,
    SearchResultItem,
    SearchResponse,
    AggregationRow,
    AggregationResponse,
    PaginatedResponse,
    ErrorResponse,
)


class TestServiceOut:
    def test_valid(self):
        s = ServiceOut(code="ARMY", full_name="Department of the Army", category="Military Department")
        assert s.code == "ARMY"

    def test_serialization(self):
        s = ServiceOut(code="NAVY", full_name="Department of the Navy", category="Military Department")
        d = s.model_dump()
        assert d["code"] == "NAVY"
        assert "full_name" in d


class TestExhibitTypeOut:
    def test_with_description(self):
        e = ExhibitTypeOut(code="R-2", display_name="RDT&E Program Summary",
                           exhibit_class="rdte", description="Detailed R&D justification")
        assert e.description == "Detailed R&D justification"

    def test_without_description(self):
        e = ExhibitTypeOut(code="P-1", display_name="Procurement Summary",
                           exhibit_class="procurement", description=None)
        assert e.description is None


class TestFiscalYearOut:
    def test_valid(self):
        fy = FiscalYearOut(fiscal_year="FY2026", row_count=12450)
        assert fy.row_count == 12450


class TestBudgetLineOut:
    def test_minimal(self):
        b = BudgetLineOut(id=1, source_file="test.xlsx")
        assert b.id == 1
        assert b.exhibit_type is None
        assert b.amount_fy2026_request is None

    def test_full(self):
        b = BudgetLineOut(
            id=1, source_file="army_p1.xlsx", exhibit_type="p1",
            fiscal_year="FY 2026", organization_name="Army",
            amount_fy2026_request=145000.0,
        )
        assert b.organization_name == "Army"
        assert b.amount_fy2026_request == 145000.0


class TestBudgetLineDetailOut:
    def test_inherits_base_fields(self):
        d = BudgetLineDetailOut(id=1, source_file="test.xlsx")
        assert d.id == 1
        assert d.appropriation_code is None
        assert d.quantity_fy2026_request is None

    def test_extra_fields(self):
        d = BudgetLineDetailOut(
            id=1, source_file="test.xlsx",
            appropriation_code="RDT&E",
            quantity_fy2026_request=42.0,
        )
        assert d.appropriation_code == "RDT&E"
        assert d.quantity_fy2026_request == 42.0


class TestSearchResultItem:
    def test_budget_line_result(self):
        item = SearchResultItem(
            result_type="budget_line", id=100,
            source_file="army_r1.xlsx", snippet="missile defense",
            data={"id": 100, "account": "2035"},
        )
        assert item.result_type == "budget_line"
        assert item.data["account"] == "2035"

    def test_pdf_result_no_snippet(self):
        item = SearchResultItem(
            result_type="pdf_page", id=200,
            source_file="justification.pdf", snippet=None,
            data={"page_number": 5},
        )
        assert item.snippet is None


class TestSearchResponse:
    def test_empty_results(self):
        resp = SearchResponse(query="test", total=0, limit=20, offset=0, results=[])
        assert resp.total == 0
        assert resp.results == []

    def test_with_results(self):
        item = SearchResultItem(
            result_type="budget_line", id=1,
            source_file="f.xlsx", data={},
        )
        resp = SearchResponse(query="cyber", total=1, limit=20, offset=0, results=[item])
        assert resp.total == 1
        assert len(resp.results) == 1


class TestAggregationRow:
    def test_with_nulls(self):
        row = AggregationRow(group_value=None, row_count=10)
        assert row.group_value is None
        assert row.total_fy2026_request is None

    def test_with_values(self):
        row = AggregationRow(
            group_value="Army", row_count=4200,
            total_fy2026_request=5000000.0,
        )
        assert row.row_count == 4200


class TestAggregationResponse:
    def test_valid(self):
        resp = AggregationResponse(group_by="service", rows=[])
        assert resp.group_by == "service"


class TestPaginatedResponse:
    def test_empty(self):
        resp = PaginatedResponse(total=0, limit=25, offset=0,
                                  page=0, page_count=1, has_next=False,
                                  items=[])
        assert resp.total == 0

    def test_with_items(self):
        item = BudgetLineOut(id=1, source_file="test.xlsx")
        resp = PaginatedResponse(total=1, limit=25, offset=0,
                                  page=0, page_count=1, has_next=False,
                                  items=[item])
        assert len(resp.items) == 1


class TestErrorResponse:
    def test_valid(self):
        err = ErrorResponse(error="Bad request", detail="Missing query parameter", status_code=400)
        assert err.status_code == 400
        assert err.error == "Bad request"

    def test_no_detail(self):
        err = ErrorResponse(error="Not found", status_code=404)
        assert err.detail is None
