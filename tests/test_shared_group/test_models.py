"""Tests for api/models.py — Pydantic request/response model validation."""

import pytest
from pydantic import ValidationError

from api.models import (
    AggregationResponse,
    AggregationRow,
    BudgetLineDetailOut,
    BudgetLineOut,
    ErrorResponse,
    ExhibitTypeOut,
    FeedbackSubmission,
    FeedbackType,
    FiscalYearOut,
    PaginatedResponse,
    SearchResponse,
    SearchResultItem,
    ServiceOut,
)



class TestFeedbackType:
    def test_valid_values(self):
        assert FeedbackType.bug == "bug"
        assert FeedbackType.feature == "feature"
        assert FeedbackType.data_issue == "data-issue"

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            FeedbackType("invalid")



class TestFeedbackSubmission:
    def test_valid_submission(self):
        fb = FeedbackSubmission(
            type=FeedbackType.bug,
            description="This is a valid bug report with enough characters.",
        )
        assert fb.type == FeedbackType.bug
        assert fb.email is None
        assert fb.page_url is None

    def test_with_optional_fields(self):
        fb = FeedbackSubmission(
            type="feature",
            description="Please add export to PDF functionality to the dashboard.",
            email="user@example.com",
            page_url="/dashboard",
        )
        assert fb.email == "user@example.com"
        assert fb.page_url == "/dashboard"

    def test_description_too_short(self):
        with pytest.raises(ValidationError):
            FeedbackSubmission(type="bug", description="short")

    def test_description_min_boundary(self):
        fb = FeedbackSubmission(type="bug", description="a" * 10)
        assert len(fb.description) == 10

    def test_description_max_boundary(self):
        fb = FeedbackSubmission(type="bug", description="a" * 5000)
        assert len(fb.description) == 5000

    def test_description_over_max(self):
        with pytest.raises(ValidationError):
            FeedbackSubmission(type="bug", description="a" * 5001)

    def test_missing_required_type(self):
        with pytest.raises(ValidationError):
            FeedbackSubmission(description="valid description text here")

    def test_missing_required_description(self):
        with pytest.raises(ValidationError):
            FeedbackSubmission(type="bug")



class TestErrorResponse:
    def test_valid_error(self):
        err = ErrorResponse(error="Bad request", detail="Missing param", status_code=400)
        assert err.status_code == 400

    def test_status_code_min_boundary(self):
        err = ErrorResponse(error="Error", status_code=400)
        assert err.status_code == 400

    def test_status_code_max_boundary(self):
        err = ErrorResponse(error="Error", status_code=599)
        assert err.status_code == 599

    def test_status_code_below_min(self):
        with pytest.raises(ValidationError):
            ErrorResponse(error="Error", status_code=399)

    def test_status_code_above_max(self):
        with pytest.raises(ValidationError):
            ErrorResponse(error="Error", status_code=600)

    def test_detail_is_optional(self):
        err = ErrorResponse(error="Error", status_code=500)
        assert err.detail is None



class TestAggregationModels:
    def test_aggregation_row_minimal(self):
        row = AggregationRow(row_count=100)
        assert row.group_value is None
        assert row.pct_of_total is None
        assert row.yoy_change_pct is None

    def test_aggregation_row_full(self):
        row = AggregationRow(
            group_value="Army",
            row_count=4200,
            rows_with_amount=3800,
            total_fy2026_request=178456000.0,
            total_fy2025_enacted=171234000.0,
            total_fy2024_actual=165000000.0,
            fy_totals={"amount_fy2026_request": 178456000.0},
            pct_of_total=23.5,
            yoy_change_pct=4.2,
        )
        assert row.group_value == "Army"
        assert row.pct_of_total == 23.5

    def test_aggregation_response(self):
        resp = AggregationResponse(
            group_by="service",
            rows=[AggregationRow(group_value="Army", row_count=100)],
        )
        assert resp.group_by == "service"
        assert len(resp.rows) == 1



class TestSearchModels:
    def test_search_result_item(self):
        item = SearchResultItem(
            result_type="budget_line",
            id=1001,
            source_file="test.xlsx",
            data={"pe_number": "0602120A"},
        )
        assert item.result_type == "budget_line"
        assert item.snippet is None

    def test_search_response(self):
        resp = SearchResponse(
            query="hypersonic",
            total=1,
            limit=20,
            offset=0,
            results=[
                SearchResultItem(
                    result_type="budget_line",
                    id=1,
                    source_file="test.xlsx",
                    data={},
                )
            ],
        )
        assert resp.total == 1
        assert resp.has_more is False

    def test_search_response_has_more(self):
        resp = SearchResponse(
            query="test", total=100, limit=20, offset=0,
            has_more=True, results=[],
        )
        assert resp.has_more is True



class TestBudgetLineModels:
    def test_budget_line_out_minimal(self):
        line = BudgetLineOut(id=1, source_file="test.xlsx")
        assert line.fiscal_year is None
        assert line.pe_number is None

    def test_budget_line_detail_inherits(self):
        detail = BudgetLineDetailOut(id=1, source_file="test.xlsx")
        assert detail.appropriation_code is None
        assert hasattr(detail, "id")
        assert hasattr(detail, "source_file")



class TestReferenceModels:
    def test_service_out(self):
        s = ServiceOut(code="ARMY", full_name="Department of the Army", category="Military Department")
        assert s.code == "ARMY"

    def test_exhibit_type_out(self):
        e = ExhibitTypeOut(code="R-2", display_name="RDT&E Program Summary", exhibit_class="rdte")
        assert e.description is None

    def test_fiscal_year_out(self):
        fy = FiscalYearOut(fiscal_year="FY2026", row_count=12450)
        assert fy.row_count == 12450



class TestPaginatedResponse:
    def test_paginated_response(self):
        resp = PaginatedResponse(
            total=100, limit=25, offset=0, page=0, page_count=4,
            has_next=True,
            items=[BudgetLineOut(id=1, source_file="test.xlsx")],
        )
        assert resp.page_count == 4
        assert resp.has_next is True
        assert len(resp.items) == 1
