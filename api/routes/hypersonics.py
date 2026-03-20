"""
Hypersonics PE lines endpoints.

Returns a pivoted view of all budget lines related to hypersonics programs,
FY2015 onward. Sources: budget_lines keyword search + pe_descriptions narrative search.

Each row is a unique (pe_number, exhibit_type, line_item_title) combination.
Columns fy2015–fy2026 show the primary requested/enacted amount ($K) from
that fiscal year's budget document.

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

# Searched across line_item_title, account_title, budget_activity_title.
# '%hypersonic%' covers both "hypersonic" and "hypersonics" via LIKE.
_HYPERSONICS_KEYWORDS = [
    "hypersonic",   # catches hypersonics, hypersonic glide, etc.
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

# Subset used for pe_descriptions narrative search (broader text, fewer terms needed)
_DESC_KEYWORDS = [
    "hypersonic",
    "ARRW",
    "LRHW",
    "C-HGB",
    "CHGB",
    "HACM",
    "HCSW",
]

_SEARCH_COLS = ["line_item_title", "account_title", "budget_activity_title"]

_FY_START = 2015
_FY_END = 2026


# ── Color-of-money normalization ──────────────────────────────────────────────

def _color_of_money(approp_title: str | None) -> str:
    """Map appropriation title to a standard color-of-money category."""
    if not approp_title:
        return "Unknown"
    t = approp_title.upper()
    if any(k in t for k in ("RDT", "RESEARCH", "DEVELOPMENT", "R&D")):
        return "RDT&E"
    if "PROCURE" in t:
        return "Procurement"
    if any(k in t for k in ("OPER", "MAINT", "O&M")):
        return "O&M"
    if any(k in t for k in ("MILCON", "CONSTRUCTION")):
        return "MILCON"
    if any(k in t for k in ("MILPERS", "PERSONNEL")):
        return "Military Personnel"
    return approp_title  # show verbatim if unrecognized


# ── SQL helpers ───────────────────────────────────────────────────────────────

def _build_keyword_where() -> tuple[str, list[str]]:
    """WHERE fragment matching hypersonics keywords across key text columns."""
    clauses: list[str] = []
    params: list[str] = []
    for col in _SEARCH_COLS:
        for kw in _HYPERSONICS_KEYWORDS:
            clauses.append(f"{col} LIKE ?")
            params.append(f"%{kw}%")
    return "(" + " OR ".join(clauses) + ")", params


def _desc_subquery(conn: sqlite3.Connection) -> tuple[str, list[str]]:
    """Return a WHERE fragment that matches PEs found in pe_descriptions.

    Returns ('', []) if the pe_descriptions table does not exist.
    """
    try:
        conn.execute("SELECT 1 FROM pe_descriptions LIMIT 0")
    except sqlite3.OperationalError:
        return "", []

    clauses = [f"description_text LIKE ?" for _ in _DESC_KEYWORDS]
    params = [f"%{kw}%" for kw in _DESC_KEYWORDS]
    subq_where = " OR ".join(clauses)
    fragment = (
        f"pe_number IN "
        f"(SELECT DISTINCT pe_number FROM pe_descriptions WHERE {subq_where})"
    )
    return fragment, params


def _build_pivot_query(
    all_amount_cols: set[str],
    desc_where: str = "",
    desc_params: list[Any] | None = None,
    extra_where: str = "",
    extra_params: list[Any] | None = None,
) -> tuple[str, list[Any]]:
    """Build the pivoted SELECT query.

    For each fiscal year N in [_FY_START, _FY_END], emits:
      SUM(CASE WHEN fiscal_year = 'FY N' THEN COALESCE(<best col>) END) AS fyN

    Priority: request → total → enacted → actual.

    Rows are matched by keywords on budget_lines columns OR by pe_number
    appearing in pe_descriptions (when desc_where is provided).
    """
    kw_where, kw_params = _build_keyword_where()

    # Combine keyword match with description match (OR)
    if desc_where:
        match_where = f"({kw_where} OR {desc_where})"
        match_params: list[Any] = list(kw_params) + list(desc_params or [])
    else:
        match_where = kw_where
        match_params = list(kw_params)

    # Per-year pivot columns
    year_parts: list[str] = []
    for yr in range(_FY_START, _FY_END + 1):
        priority = [
            f"amount_fy{yr}_request",
            f"amount_fy{yr}_total",
            f"amount_fy{yr}_enacted",
            f"amount_fy{yr}_actual",
        ]
        available = [c for c in priority if c in all_amount_cols]
        coalesce_expr = f"COALESCE({', '.join(available)})" if available else "NULL"
        year_parts.append(
            f"SUM(CASE WHEN fiscal_year = 'FY {yr}' THEN {coalesce_expr} END) AS fy{yr}"
        )

    year_cols_sql = ",\n    ".join(year_parts)

    where_parts = [match_where, "fiscal_year >= 'FY 2015'"]
    all_params: list[Any] = match_params

    if extra_where:
        where_parts.append(extra_where)
    if extra_params:
        all_params = all_params + list(extra_params)

    full_where = " AND ".join(where_parts)

    sql = f"""
        SELECT
            pe_number,
            MAX(organization_name)     AS organization_name,
            exhibit_type,
            line_item_title,
            MAX(budget_activity_title) AS budget_activity_title,
            MAX(appropriation_title)   AS appropriation_title,
            MAX(account_title)         AS account_title,
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


def _enrich_rows(rows: list[sqlite3.Row]) -> list[dict]:
    """Convert rows to dicts and add derived color_of_money field."""
    result: list[dict] = []
    for r in rows:
        d = dict(r)
        d["color_of_money"] = _color_of_money(d.get("appropriation_title"))
        result.append(d)
    return result


# ── GET /api/v1/hypersonics ───────────────────────────────────────────────────

@router.get(
    "",
    summary="Pivoted hypersonics PE lines: one row per sub-element, one column per FY",
)
def get_hypersonics(
    service: str | None = Query(None, description="Filter by service/org name (substring)"),
    exhibit: str | None = Query(None, description="Filter by exhibit type (exact, e.g. 'r2')"),
    fy_from: int | None = Query(None, ge=2015, le=2030, description="Start fiscal year"),
    fy_to: int | None = Query(None, ge=2015, le=2030, description="End fiscal year"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return all hypersonics-related budget line sub-elements as a pivoted table.

    Sources: keyword match on budget_lines + pe_descriptions narrative search.
    Each row is a unique (pe_number, exhibit_type, line_item_title) combination.
    Columns fy2015–fy2026 show the primary requested/enacted amount ($K).
    """
    all_cols = set(get_amount_columns(conn))
    desc_where, desc_params = _desc_subquery(conn)
    extra_where, extra_params = _apply_filters(service, exhibit, fy_from, fy_to)
    sql, params = _build_pivot_query(
        all_cols, desc_where, desc_params, extra_where, extra_params
    )
    rows = conn.execute(sql, params).fetchall()

    year_range = list(range(_FY_START, _FY_END + 1))
    active_years = (
        [yr for yr in year_range if any(r[f"fy{yr}"] is not None for r in rows)]
        if rows else year_range
    )

    return {
        "count": len(rows),
        "fiscal_years": active_years,
        "keywords": _HYPERSONICS_KEYWORDS,
        "rows": _enrich_rows(rows),
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
    """Download pivoted hypersonics PE lines as CSV.

    Same filters as GET /api/v1/hypersonics.
    """
    all_cols = set(get_amount_columns(conn))
    desc_where, desc_params = _desc_subquery(conn)
    extra_where, extra_params = _apply_filters(service, exhibit, fy_from, fy_to)
    sql, params = _build_pivot_query(
        all_cols, desc_where, desc_params, extra_where, extra_params
    )
    rows = conn.execute(sql, params).fetchall()
    items = _enrich_rows(rows)

    year_range = list(range(_FY_START, _FY_END + 1))

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "PE Number", "Service/Org", "Exhibit Type", "Line Item Title",
        "Budget Activity", "Appropriation", "Color of Money",
        *[f"FY{yr} ($K)" for yr in year_range],
    ])
    for r in items:
        writer.writerow([
            r["pe_number"], r["organization_name"], r["exhibit_type"],
            r["line_item_title"], r["budget_activity_title"],
            r["appropriation_title"], r["color_of_money"],
            *[r.get(f"fy{yr}") for yr in year_range],
        ])

    csv_bytes = buf.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="hypersonics_pe_lines.csv"'},
    )
