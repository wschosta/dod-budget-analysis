"""
Pydantic request/response models for the API (Step 2.C5-a).

All models use strict validation.  Optional fields default to None so that
partial responses are valid when database rows have NULL columns.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Reference data models ─────────────────────────────────────────────────────

class ServiceOut(BaseModel):
    """A military service or defense agency."""
    code: str
    full_name: str
    category: str


class ExhibitTypeOut(BaseModel):
    """A budget exhibit type (e.g., P-1, R-2)."""
    code: str
    display_name: str
    exhibit_class: str
    description: str | None = None


class FiscalYearOut(BaseModel):
    """A fiscal year present in the database."""
    fiscal_year: str
    row_count: int


# ── Budget line item models ───────────────────────────────────────────────────

class BudgetLineOut(BaseModel):
    """A single budget line item row."""
    id: int
    source_file: str
    exhibit_type: str | None = None
    sheet_name: str | None = None
    fiscal_year: str | None = None
    account: str | None = None
    account_title: str | None = None
    organization_name: str | None = None
    budget_activity_title: str | None = None
    sub_activity_title: str | None = None
    line_item: str | None = None
    line_item_title: str | None = None
    pe_number: str | None = None
    amount_fy2024_actual: float | None = None
    amount_fy2025_enacted: float | None = None
    amount_fy2026_request: float | None = None
    amount_fy2026_total: float | None = None
    amount_type: str | None = None


class BudgetLineDetailOut(BudgetLineOut):
    """Full budget line item row including all amount columns."""
    appropriation_code: str | None = None
    appropriation_title: str | None = None
    currency_year: str | None = None
    amount_unit: str | None = None
    amount_fy2025_supplemental: float | None = None
    amount_fy2025_total: float | None = None
    amount_fy2026_reconciliation: float | None = None
    quantity_fy2024: float | None = None
    quantity_fy2025: float | None = None
    quantity_fy2026_request: float | None = None
    quantity_fy2026_total: float | None = None


# ── Search result models ──────────────────────────────────────────────────────

class SearchResultItem(BaseModel):
    """A single search result hit (either from budget lines or PDF pages)."""
    result_type: str                    # "budget_line" or "pdf_page"
    id: int
    source_file: str
    snippet: str | None = None          # extracted context around the match
    score: float | None = None          # BM25 rank if available
    data: dict[str, Any]                # full row as dict


class SearchResponse(BaseModel):
    """Response body for GET /api/v1/search."""
    query: str
    total: int
    limit: int
    offset: int
    results: list[SearchResultItem]


# ── Aggregation models ────────────────────────────────────────────────────────

class AggregationRow(BaseModel):
    """One row of a GROUP BY aggregation result."""
    group_value: str | None = None
    row_count: int
    total_fy2026_request: float | None = None
    total_fy2025_enacted: float | None = None
    total_fy2024_actual: float | None = None


class AggregationResponse(BaseModel):
    """Response body for GET /api/v1/aggregations."""
    group_by: str
    rows: list[AggregationRow]


# ── Paginated list wrapper ────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    """Generic paginated list wrapper."""
    total: int
    limit: int
    offset: int
    items: list[BudgetLineOut]


# ── Error model ───────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Standard error response body (2.C5-b)."""
    error: str
    detail: str | None = None
    status_code: int = Field(..., ge=400, le=599)
