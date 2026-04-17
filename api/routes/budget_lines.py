"""
GET /api/v1/budget-lines endpoint (Step 2.C3-b).

Supports filtering by fiscal_year, service, exhibit_type, pe_number,
appropriation_code; plus sorting and pagination.  Also handles the
GET /api/v1/budget-lines/{id} single-item endpoint.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from api.database import get_db
from api.models import (
    BudgetLineDetailOut,
    BudgetLineOut,
    FilterParams,
    PaginatedResponse,
    RelatedPE,
)
from utils.query import (
    ALLOWED_SORT_COLUMNS,
    build_where_clause,
    compute_pagination,
    fetch_bli_related_pes,
)
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


@router.get("", response_model=PaginatedResponse, summary="List budget lines")
def list_budget_lines(
    filters: FilterParams = Depends(),
    sort_by: str = Query("id", description="Column to sort by"),
    sort_dir: str = Query("asc", pattern="^(asc|desc)$", description="Sort direction"),
    limit: int = Query(25, ge=1, le=500, description="Max items per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    conn: sqlite3.Connection = Depends(get_db),
) -> PaginatedResponse:
    """Return a paginated, filtered list of budget line items."""
    if sort_by not in ALLOWED_SORT_COLUMNS:
        raise HTTPException(
            status_code=400,
            detail=f"sort_by must be one of: {sorted(ALLOWED_SORT_COLUMNS)}",
        )

    # FTS5 free-text search: resolve matching row IDs first
    fts_ids: list[int] | None = None
    if filters.q:
        safe_q = sanitize_fts5_query(filters.q)
        if safe_q:
            try:
                fts_rows = conn.execute(
                    "SELECT rowid FROM budget_lines_fts WHERE budget_lines_fts MATCH ?",
                    (safe_q,),
                ).fetchall()
                fts_ids = [r[0] for r in fts_rows]
            except (sqlite3.OperationalError, sqlite3.DatabaseError):
                fts_ids = []  # FTS table missing → no matches

    where, params = build_where_clause(**filters.where_kwargs(fts_ids=fts_ids))

    direction = "DESC" if sort_dir == "desc" else "ASC"

    count_sql = f"SELECT COUNT(*) FROM budget_lines {where}"
    total = conn.execute(count_sql, params).fetchone()[0]

    data_sql = (
        f"SELECT {_SELECT_COLUMNS} FROM budget_lines {where} "
        f"ORDER BY {sort_by} {direction} LIMIT ? OFFSET ?"
    )
    rows = conn.execute(data_sql, params + [limit, offset]).fetchall()
    items = [BudgetLineOut(**dict(row)) for row in rows]

    pag = compute_pagination(offset, limit, total)

    return PaginatedResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=items,
        **pag,
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

    data = dict(row)
    data["related_pes"] = _fetch_related_pes(
        conn, data.get("exhibit_type"), data.get("account"), data.get("line_item")
    )
    return BudgetLineDetailOut(**data)


def _fetch_related_pes(
    conn: sqlite3.Connection,
    exhibit_type: str | None,
    account: str | None,
    line_item: str | None,
) -> list[RelatedPE]:
    """Look up Phase-11 BLI→PE mappings for procurement rows."""
    if exhibit_type not in ("p1", "p1r") or not account:
        return []
    bli_key = f"{account}:{line_item or ''}"
    return [RelatedPE(**r) for r in fetch_bli_related_pes(conn, bli_key)]
