"""
GET /api/v1/aggregations endpoint (Step 2.C3-c).

Groups budget lines by a dimension and sums the amount columns.
Supports optional pre-filter by fiscal_year, service, or exhibit_type.

AGG-001: Dynamic FY columns discovered from schema at runtime.
AGG-002: pct_of_total and yoy_change_pct added to each row.
OPT-AGG-001: Server-side TTL cache (60 seconds) for aggregation queries.
"""

import json
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query as FQuery
from fastapi.responses import JSONResponse

from api.database import get_db
from api.models import AggregationResponse, AggregationRow
from utils.cache import TTLCache
from utils.database import get_amount_columns
from utils.query import build_where_clause

router = APIRouter(prefix="/aggregations", tags=["aggregations"])

_ALLOWED_GROUPS = {
    "service":        "organization_name",
    "fiscal_year":    "fiscal_year",
    "appropriation":  "appropriation_code",
    "exhibit_type":   "exhibit_type",
    "budget_activity": "budget_activity_title",
    "budget_type":    "budget_type",
}

# OPT-AGG-001: 300-second TTL cache (matches dashboard) keyed on filter params
_agg_cache: TTLCache = TTLCache(maxsize=128, ttl_seconds=300)


def _cache_key(
    group_by: str,
    fiscal_year: list[str] | None,
    service: list[str] | None,
    exhibit_type: list[str] | None,
    appropriation_code: list[str] | None = None,
) -> tuple:
    return (
        group_by,
        tuple(sorted(fiscal_year or [])),
        tuple(sorted(service or [])),
        tuple(sorted(exhibit_type or [])),
        tuple(sorted(appropriation_code or [])),
    )


@router.get(
    "",
    response_model=AggregationResponse,
    summary="Aggregate budget data",
    responses={
        400: {"description": "Invalid group_by parameter", "content": {"application/json": {"example": {"error": "Bad request", "detail": "group_by must be one of: ['appropriation', 'budget_activity', 'exhibit_type', 'fiscal_year', 'service']", "status_code": 400}}}},
        429: {"description": "Rate limit exceeded", "content": {"application/json": {"example": {"error": "Too many requests", "status_code": 429}}}},
    },
)
def aggregate(
    group_by: str = FQuery(
        ...,
        description=(
            "Dimension to group by: service, fiscal_year, "
            "appropriation, exhibit_type, budget_activity"
        ),
    ),
    fiscal_year: list[str] | None = FQuery(None, description="Pre-filter by fiscal year(s)"),
    service: list[str] | None = FQuery(None, description="Pre-filter by service name"),
    exhibit_type: list[str] | None = FQuery(None, description="Pre-filter by exhibit type"),
    appropriation_code: list[str] | None = FQuery(None, description="Pre-filter by appropriation code(s)"),
    conn: sqlite3.Connection = Depends(get_db),
) -> AggregationResponse:
    """Aggregate budget totals grouped by the specified dimension.

    AGG-001: Amount columns are discovered dynamically from the schema so new
    fiscal year columns (FY2027+) are included automatically.
    AGG-002: Each row includes pct_of_total and yoy_change_pct.
    OPT-AGG-001: Results are cached for 300 seconds per unique filter combination.
    """
    if group_by not in _ALLOWED_GROUPS:
        raise HTTPException(
            status_code=400,
            detail=f"group_by must be one of: {sorted(_ALLOWED_GROUPS.keys())}",
        )

    # OPT-AGG-001: Check cache before querying
    key = _cache_key(group_by, fiscal_year, service, exhibit_type,
                     appropriation_code=appropriation_code)
    cached = _agg_cache.get(key)
    if cached is not None:
        return cached

    col = _ALLOWED_GROUPS[group_by]
    where, params = build_where_clause(
        fiscal_year=fiscal_year,
        service=service,
        exhibit_type=exhibit_type,
        appropriation_code=appropriation_code,
    )

    # AGG-001: Discover FY amount columns dynamically
    amount_cols = get_amount_columns(conn)
    if not amount_cols:
        amount_cols = ["amount_fy2024_actual", "amount_fy2025_enacted", "amount_fy2026_request"]

    sum_exprs = ",\n            ".join(
        f"SUM({c}) AS {c}" for c in amount_cols
    )

    latest_count_expr = f"COUNT({amount_cols[-1]}) AS rows_with_amount"
    sql = f"""
        SELECT
            {col} AS group_value,
            COUNT(*) AS row_count,
            {latest_count_expr},
            {sum_exprs}
        FROM budget_lines
        {where}
        GROUP BY {col}
        ORDER BY COALESCE({amount_cols[-1]}, 0) DESC
    """
    rows = conn.execute(sql, params).fetchall()
    raw_rows = [dict(r) for r in rows]

    # AGG-002: Compute totals and percentages
    latest_col = amount_cols[-1] if amount_cols else None
    prev_col = amount_cols[-2] if len(amount_cols) >= 2 else None

    # Map canonical column names to AggregationRow fields
    fy26_col = next((c for c in amount_cols if "fy2026_request" in c), None)
    fy25_col = next((c for c in amount_cols if "fy2025_enacted" in c), None)
    fy24_col = next((c for c in amount_cols if "fy2024_actual" in c), None)

    grand_total = sum(
        (r.get(latest_col) or 0) for r in raw_rows
    ) if latest_col else 0

    enriched: list[AggregationRow] = []
    for r in raw_rows:
        latest_val = r.get(latest_col) if latest_col else None
        prev_val = r.get(prev_col) if prev_col else None

        pct_of_total = None
        if grand_total and latest_val is not None:
            pct_of_total = round(latest_val / grand_total * 100, 2)

        yoy_change_pct = None
        if prev_val and latest_val is not None:
            yoy_change_pct = round(
                (latest_val - prev_val) / abs(prev_val) * 100, 2
            )

        fy_totals = {c: r.get(c) for c in amount_cols}

        enriched.append(AggregationRow(
            group_value=r.get("group_value"),
            row_count=r.get("row_count", 0),
            rows_with_amount=r.get("rows_with_amount"),
            total_fy2026_request=r.get(fy26_col) if fy26_col else latest_val,
            total_fy2025_enacted=r.get(fy25_col),
            total_fy2024_actual=r.get(fy24_col),
            fy_totals=fy_totals,
            pct_of_total=pct_of_total,
            yoy_change_pct=yoy_change_pct,
        ))

    result = AggregationResponse(group_by=group_by, rows=enriched)
    _agg_cache.set(key, result)
    return result


_hierarchy_cache: TTLCache = TTLCache(maxsize=16, ttl_seconds=300)


@router.get("/hierarchy", summary="Hierarchical budget breakdown for treemap")
def hierarchy(
    fiscal_year: str | None = FQuery(None, description="Filter by fiscal year"),
    service: str | None = FQuery(None, description="Filter by service/organization name"),
    exhibit_type: str | None = FQuery(None, description="Filter by exhibit type"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return Service > Appropriation > Program hierarchy for treemap visualization.

    Returns items with service, appropriation, program title, PE number, and amount.
    Results are cached for 300 seconds per unique filter combination.
    """
    cache_key = ("hierarchy", fiscal_year, service, exhibit_type)
    cached = _hierarchy_cache.get(cache_key)
    if cached is not None:
        return cached

    # Use dynamic FY column detection (consistent with main aggregation endpoint)
    amount_cols = get_amount_columns(conn)
    fy26_col = next((c for c in amount_cols if "fy2026_request" in c),
                    "amount_fy2026_request")
    fy25_col = next((c for c in amount_cols if "fy2025_enacted" in c),
                    "amount_fy2025_enacted")

    conditions: list[str] = [
        f"{fy26_col} IS NOT NULL",
        "organization_name IS NOT NULL",
    ]
    params: list[Any] = []

    if fiscal_year:
        conditions.append("fiscal_year = ?")
        params.append(fiscal_year)
    if service:
        conditions.append("organization_name = ?")
        params.append(service)
    if exhibit_type:
        conditions.append("exhibit_type = ?")
        params.append(exhibit_type)

    where = "WHERE " + " AND ".join(conditions)

    rows = conn.execute(
        f"SELECT organization_name AS service, "
        f"appropriation_code AS approp, "
        f"appropriation_title AS approp_title, "
        f"line_item_title AS program, "
        f"pe_number, "
        f"SUM({fy26_col}) AS amount, "
        f"SUM(COALESCE({fy25_col}, 0)) AS prev_amount "
        f"FROM budget_lines "
        f"{where} "
        f"GROUP BY organization_name, appropriation_code, line_item_title "
        f"HAVING SUM({fy26_col}) > 0 "
        f"ORDER BY SUM({fy26_col}) DESC",
        params,
    ).fetchall()

    grand_total = sum(r["amount"] or 0 for r in rows) if rows else 0
    items = []
    for r in rows:
        d = dict(r)
        d["pct_of_total"] = (
            round(d["amount"] / grand_total * 100, 2)
            if grand_total and d["amount"] else None
        )
        items.append(d)

    result = {"items": items, "grand_total": grand_total}
    _hierarchy_cache.set(cache_key, result)
    return result
