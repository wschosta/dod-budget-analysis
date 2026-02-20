"""
GET /api/v1/budget-lines endpoint (Step 2.C3-b).

Supports filtering by fiscal_year, service, exhibit_type, pe_number,
appropriation_code; plus sorting and pagination.  Also handles the
GET /api/v1/budget-lines/{id} single-item endpoint.
"""

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.database import get_db
from api.models import BudgetLineDetailOut, BudgetLineOut, PaginatedResponse
from utils.query import build_where_clause
from utils.strings import sanitize_fts5_query

router = APIRouter(prefix="/budget-lines", tags=["budget-lines"])

_SELECT_COLUMNS = """
    id, source_file, exhibit_type, sheet_name, fiscal_year,
    account, account_title, organization_name,
    budget_activity_title, sub_activity_title,
    line_item, line_item_title, pe_number,
    amount_fy2024_actual, amount_fy2025_enacted,
    amount_fy2026_request, amount_fy2026_total, amount_type
"""

_SELECT_ALL_COLUMNS = """
    id, source_file, exhibit_type, sheet_name, fiscal_year,
    account, account_title, organization_name,
    budget_activity_title, sub_activity_title,
    line_item, line_item_title, pe_number, amount_type,
    appropriation_code, appropriation_title, currency_year, amount_unit,
    amount_fy2024_actual, amount_fy2025_enacted, amount_fy2025_supplemental,
    amount_fy2025_total, amount_fy2026_request, amount_fy2026_reconciliation,
    amount_fy2026_total, quantity_fy2024, quantity_fy2025,
    quantity_fy2026_request, quantity_fy2026_total
"""

_ALLOWED_SORT = {
    "id", "source_file", "exhibit_type", "fiscal_year",
    "organization_name", "account", "account_title", "pe_number",
    "amount_fy2026_request", "amount_fy2025_enacted", "amount_fy2024_actual",
}


def _build_where(
    fiscal_year: list[str] | None,
    service: list[str] | None,
    exhibit_type: list[str] | None,
    pe_number: list[str] | None,
    appropriation_code: list[str] | None,
) -> tuple[str, list[Any]]:
    """Build WHERE clause — delegates to shared utils/query.py builder."""
    return build_where_clause(
        fiscal_year=fiscal_year,
        service=service,
        exhibit_type=exhibit_type,
        pe_number=pe_number,
        appropriation_code=appropriation_code,
    )


@router.get("", response_model=PaginatedResponse, summary="List budget lines")
def list_budget_lines(
    fiscal_year: list[str] | None = Query(None, description="Filter by fiscal year(s)"),
    service: list[str] | None = Query(None, description="Filter by service/org name"),
    exhibit_type: list[str] | None = Query(None, description="Filter by exhibit type(s)"),
    pe_number: list[str] | None = Query(None, description="Filter by PE number(s)"),
    appropriation_code: list[str] | None = Query(None, description="Filter by appropriation"),
    budget_type: list[str] | None = Query(None, description="Filter by budget type (RDT&E, Procurement, etc.)"),
    q: str | None = Query(None, description="Free-text search across account/line-item titles"),
    min_amount: float | None = Query(None, description="Min FY2026 request amount (thousands)"),
    max_amount: float | None = Query(None, description="Max FY2026 request amount (thousands)"),
    sort_by: str = Query("id", description="Column to sort by"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$", description="Sort direction"),
    limit: int = Query(25, ge=1, le=500, description="Max items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    conn: sqlite3.Connection = Depends(get_db),
) -> PaginatedResponse:
    """Return a paginated, filtered list of budget line items."""
    if sort_by not in _ALLOWED_SORT:
        raise HTTPException(
            status_code=400,
            detail=f"sort_by must be one of: {sorted(_ALLOWED_SORT)}",
        )

    # FTS5 free-text search: resolve matching row IDs first
    fts_ids: list[int] | None = None
    if q:
        safe_q = sanitize_fts5_query(q)
        if safe_q:
            try:
                fts_rows = conn.execute(
                    "SELECT rowid FROM budget_lines_fts WHERE budget_lines_fts MATCH ?",
                    (safe_q,),
                ).fetchall()
                fts_ids = [r[0] for r in fts_rows]
            except Exception:
                fts_ids = []  # FTS table missing → no matches

    where, params = build_where_clause(
        fiscal_year=fiscal_year,
        service=service,
        exhibit_type=exhibit_type,
        pe_number=pe_number,
        appropriation_code=appropriation_code,
        budget_type=budget_type,
        min_amount=min_amount,
        max_amount=max_amount,
        fts_ids=fts_ids,
    )
    direction = "DESC" if sort_dir == "desc" else "ASC"

    count_sql = f"SELECT COUNT(*) FROM budget_lines {where}"
    total = conn.execute(count_sql, params).fetchone()[0]

    data_sql = (
        f"SELECT {_SELECT_COLUMNS} FROM budget_lines {where} "
        f"ORDER BY {sort_by} {direction} LIMIT ? OFFSET ?"
    )
    rows = conn.execute(data_sql, params + [limit, offset]).fetchall()
    items = [BudgetLineOut(**dict(row)) for row in rows]

    page = offset // limit if limit > 0 else 0
    page_count = max(1, (total + limit - 1) // limit) if limit > 0 else 1
    has_next = offset + limit < total

    return PaginatedResponse(
        total=total, limit=limit, offset=offset,
        page=page, page_count=page_count, has_next=has_next,
        items=items,
    )


@router.get(
    "/{item_id}",
    response_model=BudgetLineDetailOut,
    summary="Get single budget line",
)
def get_budget_line(
    item_id: int,
    conn: sqlite3.Connection = Depends(get_db),
) -> BudgetLineDetailOut:
    """Return a single budget line item by ID (full detail)."""
    row = conn.execute(
        f"SELECT {_SELECT_ALL_COLUMNS} FROM budget_lines WHERE id = ?",
        (item_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Budget line {item_id} not found")
    return BudgetLineDetailOut(**dict(row))
