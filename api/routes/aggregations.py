"""
GET /api/v1/aggregations endpoint (Step 2.C3-c).

Groups budget lines by a dimension and sums the amount columns.
Supports optional pre-filter by fiscal_year, service, or exhibit_type.

──────────────────────────────────────────────────────────────────────────────
TODOs for this file
──────────────────────────────────────────────────────────────────────────────

TODO AGG-001 [Group: TIGER] [Complexity: MEDIUM] [Tokens: ~2500] [User: NO]
    Make aggregation amount columns dynamic instead of hardcoded.
    Currently the SQL hardcodes SUM(amount_fy2026_request), etc. When FY2027
    columns are added, this endpoint breaks. Steps:
      1. Query budget_lines table schema to discover amount_fy* columns
      2. Build SUM() expressions dynamically for all found FY columns
      3. Update AggregationRow model to use a dict for dynamic FY sums:
         fy_totals: dict[str, float | None] instead of named fields
      4. Cache the column discovery result (schema changes rarely)
    Acceptance: Aggregations auto-include new FY columns without code changes.

TODO AGG-002 [Group: TIGER] [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Add percentage and delta calculations to aggregation output.
    Users want to see year-over-year change and share-of-total. Steps:
      1. Calculate total across all groups for each FY column
      2. Add pct_of_total (float, 0-100) to each AggregationRow
      3. Add yoy_change_pct (float, percent change from prior FY) if both
         FY columns are present
    Acceptance: Aggregation rows include percentage and YoY delta fields.

TODO OPT-AGG-001 [Group: TIGER] [Complexity: LOW] [Tokens: ~1000] [User: NO]
    Add server-side caching for expensive aggregation queries.
    Aggregations over the full budget_lines table are slow on large datasets.
    Steps:
      1. Add in-memory cache keyed on (group_by, fiscal_year, service,
         exhibit_type) tuple with 60-second TTL
      2. Return cached result if available; run query and cache if not
      3. Add Cache-Control: max-age=60 response header
    Acceptance: Repeated aggregation queries return in <10ms after first hit.
"""

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.database import get_db
from api.models import AggregationResponse, AggregationRow

router = APIRouter(prefix="/aggregations", tags=["aggregations"])

_ALLOWED_GROUPS = {
    "service": "organization_name",
    "fiscal_year": "fiscal_year",
    "appropriation": "appropriation_code",
    "exhibit_type": "exhibit_type",
    "budget_activity": "budget_activity_title",
}


@router.get("", response_model=AggregationResponse, summary="Aggregate budget data")
def aggregate(
    group_by: str = Query(
        ...,
        description=(
            "Dimension to group by: service, fiscal_year, "
            "appropriation, exhibit_type, budget_activity"
        ),
    ),
    fiscal_year: list[str] | None = Query(None, description="Pre-filter by fiscal year(s)"),
    service: list[str] | None = Query(None, description="Pre-filter by service name"),
    exhibit_type: list[str] | None = Query(None, description="Pre-filter by exhibit type"),
    conn: sqlite3.Connection = Depends(get_db),
) -> AggregationResponse:
    """Aggregate budget totals grouped by the specified dimension."""
    if group_by not in _ALLOWED_GROUPS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"group_by must be one of: {sorted(_ALLOWED_GROUPS.keys())}"
            ),
        )

    col = _ALLOWED_GROUPS[group_by]
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

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    sql = f"""
        SELECT
            {col} AS group_value,
            COUNT(*) AS row_count,
            SUM(amount_fy2026_request) AS total_fy2026_request,
            SUM(amount_fy2025_enacted) AS total_fy2025_enacted,
            SUM(amount_fy2024_actual)  AS total_fy2024_actual
        FROM budget_lines
        {where}
        GROUP BY {col}
        ORDER BY total_fy2026_request DESC NULLS LAST
    """
    rows = conn.execute(sql, params).fetchall()
    agg_rows = [AggregationRow(**dict(row)) for row in rows]

    return AggregationResponse(group_by=group_by, rows=agg_rows)
