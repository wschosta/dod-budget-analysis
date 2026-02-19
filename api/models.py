"""
Pydantic request/response models for the API (Step 2.C5-a).

All models use strict validation.  Optional fields default to None so that
partial responses are valid when database rows have NULL columns.

3.C4-a: Field() descriptions and examples added for OpenAPI docs.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Reference data models ─────────────────────────────────────────────────────

class ServiceOut(BaseModel):
    """A military service or defense agency."""
    code: str = Field(..., description="Short code / abbreviation", examples=["ARMY"])
    full_name: str = Field(..., description="Full organization name", examples=["Department of the Army"])
    category: str = Field(..., description="Category: Military Department, Defense Agency, etc.", examples=["Military Department"])


class ExhibitTypeOut(BaseModel):
    """A budget exhibit type (e.g., P-1, R-2)."""
    code: str = Field(..., description="Exhibit type code", examples=["R-2"])
    display_name: str = Field(..., description="Human-readable name", examples=["RDT&E Program Summary"])
    exhibit_class: str = Field(..., description="procurement | rdte | om | milpers | construction | summary", examples=["rdte"])
    description: str | None = Field(None, description="Extended description of this exhibit type")


class FiscalYearOut(BaseModel):
    """A fiscal year present in the database."""
    fiscal_year: str = Field(..., description="Fiscal year string", examples=["FY2026"])
    row_count: int = Field(..., description="Number of budget lines for this fiscal year", examples=[12450])


# ── Budget line item models ───────────────────────────────────────────────────

class BudgetLineOut(BaseModel):
    """A single budget line item row (summary fields). Amounts are in $K."""
    id: int = Field(..., description="Unique row ID", examples=[1001])
    source_file: str = Field(..., description="Source XLSX or PDF filename", examples=["fy2026_army_rdtestimate.xlsx"])
    exhibit_type: str | None = Field(None, description="Exhibit type code (R-2, P-5, O-1, etc.)", examples=["R-2"])
    sheet_name: str | None = Field(None, description="Worksheet name within the source XLSX", examples=["RDT&E Programs"])
    fiscal_year: str | None = Field(None, description="Fiscal year this row belongs to", examples=["FY2026"])
    account: str | None = Field(None, description="Appropriation account code", examples=["2040A"])
    account_title: str | None = Field(None, description="Appropriation account title")
    organization_name: str | None = Field(None, description="Service or agency name", examples=["Army"])
    budget_activity_title: str | None = Field(None, description="Budget activity title", examples=["Applied Research"])
    sub_activity_title: str | None = Field(None, description="Sub-activity or program element group title")
    line_item: str | None = Field(None, description="Line item identifier", examples=["PE 0602120A"])
    line_item_title: str | None = Field(None, description="Program or line item title", examples=["Cybersecurity Initiative"])
    pe_number: str | None = Field(None, description="Program element number", examples=["0602120A"])
    amount_fy2024_actual: float | None = Field(None, description="FY2024 actual amount in $K", examples=[125400.0])
    amount_fy2025_enacted: float | None = Field(None, description="FY2025 enacted amount in $K", examples=[131200.0])
    amount_fy2026_request: float | None = Field(None, description="FY2026 President's Budget request in $K", examples=[145000.0])
    amount_fy2026_total: float | None = Field(None, description="FY2026 total (request + adjustments) in $K", examples=[145000.0])
    amount_type: str | None = Field(None, description="Amount type: BA (Budget Authority), O (Obligations), etc.", examples=["BA"])


class BudgetLineDetailOut(BudgetLineOut):
    """Full budget line item row including all amount and quantity columns."""
    appropriation_code: str | None = Field(None, description="Appropriation code (color of money)", examples=["RDT&E"])
    appropriation_title: str | None = Field(None, description="Full appropriation title")
    currency_year: str | None = Field(None, description="Currency year for constant-dollar conversions", examples=["FY2026"])
    amount_unit: str | None = Field(None, description="Unit for amount columns; default is $K", examples=["$K"])
    amount_fy2025_supplemental: float | None = Field(None, description="FY2025 supplemental appropriation in $K")
    amount_fy2025_total: float | None = Field(None, description="FY2025 total (enacted + supplemental) in $K")
    amount_fy2026_reconciliation: float | None = Field(None, description="FY2026 reconciliation adjustment in $K")
    quantity_fy2024: float | None = Field(None, description="Procurement quantity in FY2024 (P-5 exhibits)")
    quantity_fy2025: float | None = Field(None, description="Procurement quantity in FY2025 (P-5 exhibits)")
    quantity_fy2026_request: float | None = Field(None, description="Procurement quantity requested for FY2026")
    quantity_fy2026_total: float | None = Field(None, description="Total procurement quantity for FY2026")


# ── Search result models ──────────────────────────────────────────────────────

class SearchResultItem(BaseModel):
    """A single search result hit (either from budget lines or PDF pages)."""
    result_type: str = Field(..., description="'budget_line' or 'pdf_page'", examples=["budget_line"])
    id: int = Field(..., description="Row ID in the source table", examples=[1001])
    source_file: str = Field(..., description="Source XLSX or PDF filename")
    snippet: str | None = Field(None, description="Context snippet around the matching text")
    score: float | None = Field(None, description="BM25 relevance score (higher = more relevant)")
    data: dict[str, Any] = Field(..., description="Full row fields as key-value pairs")


class SearchResponse(BaseModel):
    """Response body for GET /api/v1/search."""
    query: str = Field(..., description="The original search query string", examples=["hypersonic missile"])
    total: int = Field(..., description="Total number of matching results returned", examples=[42])
    limit: int = Field(..., description="Maximum results per page", examples=[20])
    offset: int = Field(..., description="Pagination offset", examples=[0])
    results: list[SearchResultItem] = Field(..., description="List of search result items")


# ── Aggregation models ────────────────────────────────────────────────────────

class AggregationRow(BaseModel):
    """One row of a GROUP BY aggregation result."""
    group_value: str | None = Field(None, description="The grouped field value", examples=["Army"])
    row_count: int = Field(..., description="Number of budget lines in this group", examples=[4200])
    total_fy2026_request: float | None = Field(None, description="Sum of FY2026 request amounts in $K")
    total_fy2025_enacted: float | None = Field(None, description="Sum of FY2025 enacted amounts in $K")
    total_fy2024_actual: float | None = Field(None, description="Sum of FY2024 actual amounts in $K")
    # AGG-001: dynamic FY totals (includes all discovered FY columns)
    fy_totals: dict[str, Any] | None = Field(None, description="All FY amount sums keyed by column name")
    # AGG-002: percentage and YoY delta
    pct_of_total: float | None = Field(None, description="Percentage of grand total for latest FY")
    yoy_change_pct: float | None = Field(None, description="Year-over-year change percentage (latest vs prior FY)")


class AggregationResponse(BaseModel):
    """Response body for GET /api/v1/aggregations."""
    group_by: str = Field(..., description="Field used for grouping", examples=["service"])
    rows: list[AggregationRow] = Field(..., description="Aggregated rows, one per group value")


# ── Paginated list wrapper ────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    """Generic paginated list wrapper."""
    total: int = Field(..., description="Total matching rows (before pagination)", examples=[3842])
    limit: int = Field(..., description="Page size used", examples=[25])
    offset: int = Field(..., description="Offset of this page", examples=[0])
    items: list[BudgetLineOut] = Field(..., description="Budget line items for this page")


# ── Error model ───────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    """Standard error response body (2.C5-b)."""
    error: str = Field(..., description="Short error category", examples=["Bad request"])
    detail: str | None = Field(None, description="Extended error detail")
    status_code: int = Field(..., ge=400, le=599, description="HTTP status code", examples=[400])
