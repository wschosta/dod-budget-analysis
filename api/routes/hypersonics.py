"""
Hypersonics PE lines endpoints.

Returns a pivoted view of all budget lines related to hypersonics programs,
FY2015 onward. Each row represents a unique PE + sub-element (line item), with
one column per fiscal year showing the primary requested/enacted amount from
that year's budget document.

Endpoints:
  GET /api/v1/hypersonics          — JSON, pivoted table data
  GET /api/v1/hypersonics/download — streaming CSV of pivoted table
"""

from __future__ import annotations

import csv
import io
import logging
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from api.database import get_db
from utils.database import get_amount_columns

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hypersonics", tags=["hypersonics"])

# ── Keywords ──────────────────────────────────────────────────────────────────

_HYPERSONICS_KEYWORDS = [
    "hypersonic",
    "ARRW",
    "LRHW",
    "C-HGB",
    "CHGB",
    "glide body",
    "scramjet",
    "HACM",
    "HCSW",
    "AGM-183",
]

# Columns to search for keyword matches
_SEARCH_COLS = ["line_item_title", "account_title", "budget_activity_title"]

# Fiscal year range to cover
_FY_START = 2015
_FY_END = 2026


def _build_keyword_where() -> tuple[str, list[str]]:
    """Build the WHERE clause for hypersonics keyword matching."""
    clauses: list[str] = []
    params: list[str] = []
    for col in _SEARCH_COLS:
        for kw in _HYPERSONICS_KEYWORDS:
            clauses.append(f"{col} LIKE ?")
            params.append(f"%{kw}%")
    where = "(" + " OR ".join(clauses) + ")"
    return where, params


def _build_pivot_query(
    all_amount_cols: set[str],
    extra_where: str = "",
    extra_params: list[Any] | None = None,
) -> tuple[str, list[Any]]:
    """Build the pivoted SELECT query.

    For each fiscal year N in [_FY_START, _FY_END], emits a column:
      SUM(CASE WHEN fiscal_year = 'FY N' THEN COALESCE(<best available col>) END)

    The 'best available' priority is: request → total → enacted → actual.
    """
    kw_where, kw_params = _build_keyword_where()

    # Build per-year pivot columns
    year_select_parts: list[str] = []
    for yr in range(_FY_START, _FY_END + 1):
        priority = [
            f"amount_fy{yr}_request",
            f"amount_fy{yr}_total",
            f"amount_fy{yr}_enacted",
            f"amount_fy{yr}_actual",
        ]
        available = [c for c in priority if c in all_amount_cols]
        if available:
            coalesce_expr = f"COALESCE({', '.join(available)})"
        else:
            coalesce_expr = "NULL"
        year_select_parts.append(
            f"SUM(CASE WHEN fiscal_year = 'FY {yr}' THEN {coalesce_expr} END) AS fy{yr}"
        )

    year_cols_sql = ",\n    ".join(year_select_parts)

    where_parts = [kw_where, "fiscal_year >= 'FY 2015'"]
    all_params: list[Any] = list(kw_params)

    if extra_where:
        where_parts.append(extra_where)
    if extra_params:
        all_params.extend(extra_params)

    full_where = " AND ".join(where_parts)

    sql = f"""
        SELECT
            pe_number,
            MAX(organization_name)        AS organization_name,
            exhibit_type,
            line_item_title,
            MAX(budget_activity_title)    AS budget_activity_title,
            {year_cols_sql}
        FROM budget_lines
        WHERE {full_where}
        GROUP BY pe_number, exhibit_type, line_item_title
        HAVING COUNT(*) > 0
        ORDER BY pe_number, exhibit_type, line_item_title
    """
    return sql, all_params


def _apply_filters(
    service: str | None,
    exhibit: str | None,
    fy_from: int | None,
    fy_to: int | None,
) -> tuple[str, list[Any]]:
    """Build additional WHERE fragments from optional user filters."""
    parts: list[str] = []
    params: list[Any] = []

    if service:
        parts.append("organization_name LIKE ?")
        params.append(f"%{service}%")
    if exhibit:
        parts.append("exhibit_type = ?")
        params.append(exhibit)
    if fy_from:
        parts.append("fiscal_year >= ?")
        params.append(f"FY {fy_from}")
    if fy_to:
        parts.append("fiscal_year <= ?")
        params.append(f"FY {fy_to}")

    return (" AND ".join(parts), params) if parts else ("", [])


# ── GET /api/v1/hypersonics ───────────────────────────────────────────────────

@router.get(
    "",
    summary="Pivoted hypersonics PE lines: one row per sub-element, one column per FY",
)
def get_hypersonics(
    service: str | None = Query(None, description="Filter by service/org name (substring)"),
    exhibit: str | None = Query(None, description="Filter by exhibit type (exact, e.g. 'r2')"),
    fy_from: int | None = Query(None, ge=2015, le=2030, description="Start fiscal year (e.g. 2020)"),
    fy_to: int | None = Query(None, ge=2015, le=2030, description="End fiscal year (e.g. 2026)"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return all hypersonics-related budget line sub-elements as a pivoted table.

    Each row is a unique (pe_number, exhibit_type, line_item_title) combination.
    Columns fy2015 … fy2026 show the primary requested/enacted amount ($K) from
    that fiscal year's budget document (NULL if no data for that year).
    """
    all_cols = set(get_amount_columns(conn))

    extra_where, extra_params = _apply_filters(service, exhibit, fy_from, fy_to)
    sql, params = _build_pivot_query(all_cols, extra_where, extra_params)

    rows = conn.execute(sql, params).fetchall()

    # Build the list of fiscal year column names that have any non-NULL data
    year_range = list(range(_FY_START, _FY_END + 1))
    active_years: list[int] = []
    if rows:
        for yr in year_range:
            col = f"fy{yr}"
            if any(r[col] is not None for r in rows):
                active_years.append(yr)
    else:
        active_years = year_range

    items = [dict(r) for r in rows]

    return {
        "count": len(items),
        "fiscal_years": active_years,
        "fy_start": _FY_START,
        "fy_end": _FY_END,
        "keywords": _HYPERSONICS_KEYWORDS,
        "rows": items,
    }


# ── GET /api/v1/hypersonics/download ─────────────────────────────────────────

@router.get(
    "/download",
    summary="Download hypersonics PE lines as CSV",
    response_class=Response,
)
def download_hypersonics(
    service: str | None = Query(None),
    exhibit: str | None = Query(None),
    fy_from: int | None = Query(None, ge=2015, le=2030),
    fy_to: int | None = Query(None, ge=2015, le=2030),
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """Download hypersonics PE lines as a pivoted CSV.

    Same filters as GET /api/v1/hypersonics. Each row is a unique
    (pe_number, exhibit_type, line_item_title); columns span FY2015–FY2026.
    """
    all_cols = set(get_amount_columns(conn))
    extra_where, extra_params = _apply_filters(service, exhibit, fy_from, fy_to)
    sql, params = _build_pivot_query(all_cols, extra_where, extra_params)

    rows = conn.execute(sql, params).fetchall()

    year_range = list(range(_FY_START, _FY_END + 1))

    buf = io.StringIO()
    writer = csv.writer(buf)

    # Header
    writer.writerow([
        "PE Number", "Service/Org", "Exhibit Type", "Line Item Title", "Budget Activity",
        *[f"FY{yr} ($K)" for yr in year_range],
    ])

    for r in rows:
        writer.writerow([
            r["pe_number"],
            r["organization_name"],
            r["exhibit_type"],
            r["line_item_title"],
            r["budget_activity_title"],
            *[r[f"fy{yr}"] for yr in year_range],
        ])

    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM for Excel
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="hypersonics_pe_lines.csv"'},
    )
