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
    conditions: list[str] = []
    params: list[Any] = []

    if fiscal_year:
        placeholders = ",".join("?" * len(fiscal_year))
        conditions.append(f"fiscal_year IN ({placeholders})")
        params.extend(fiscal_year)

    if service:
        sub = " OR ".join("organization_name LIKE ?" for _ in service)
        conditions.append(f"({sub})")
        params.extend(f"%{s}%" for s in service)

    if exhibit_type:
        placeholders = ",".join("?" * len(exhibit_type))
        conditions.append(f"exhibit_type IN ({placeholders})")
        params.extend(exhibit_type)

    if pe_number:
        placeholders = ",".join("?" * len(pe_number))
        conditions.append(f"pe_number IN ({placeholders})")
        params.extend(pe_number)

    if appropriation_code:
        placeholders = ",".join("?" * len(appropriation_code))
        conditions.append(f"appropriation_code IN ({placeholders})")
        params.extend(appropriation_code)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    return where, params


@router.get("", response_model=PaginatedResponse, summary="List budget lines")
def list_budget_lines(
    fiscal_year: list[str] | None = Query(None, description="Filter by fiscal year(s)"),
    service: list[str] | None = Query(None, description="Filter by service/org name"),
    exhibit_type: list[str] | None = Query(None, description="Filter by exhibit type(s)"),
    pe_number: list[str] | None = Query(None, description="Filter by PE number(s)"),
    appropriation_code: list[str] | None = Query(None, description="Filter by appropriation"),
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

    where, params = _build_where(fiscal_year, service, exhibit_type, pe_number, appropriation_code)
    direction = "DESC" if sort_dir == "desc" else "ASC"

    count_sql = f"SELECT COUNT(*) FROM budget_lines {where}"
    total = conn.execute(count_sql, params).fetchone()[0]

    data_sql = (
        f"SELECT {_SELECT_COLUMNS} FROM budget_lines {where} "
        f"ORDER BY {sort_by} {direction} LIMIT ? OFFSET ?"
    )
    rows = conn.execute(data_sql, params + [limit, offset]).fetchall()
    items = [BudgetLineOut(**dict(row)) for row in rows]

    return PaginatedResponse(total=total, limit=limit, offset=offset, items=items)


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
