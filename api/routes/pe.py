"""
PE-centric API endpoints.

Supports the three core GUI use cases:
  1. PE lookup by number — funding table by year, sub-elements, related PEs, descriptions
  2. Topic/tag search — find PE lines matching a tag or free-text topic
  3. Export — Spruill-style funding table (CSV) or ZIP of PDF pages for a PE set

LION integration:
  DONE LION-100: pdf_pages now has fiscal_year/exhibit_type — used in pdf-pages endpoint.
  DONE LION-103: pdf_pe_numbers junction — get_pe_pdf_pages uses direct JOIN.
  DONE LION-106: pe_tags.source_files + confidence included in tag responses.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from api.database import get_db, get_db_path
from utils.strings import sanitize_fts5_query

router = APIRouter(prefix="/pe", tags=["pe"])


# ── Helper: row → dict ────────────────────────────────────────────────────────

def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def _json_list(val: str | None) -> list[str]:
    """Parse a JSON array column value, returning [] on failure."""
    if not val:
        return []
    try:
        return json.loads(val)
    except Exception:
        return []


# ── GET /api/v1/pe/top-changes ────────────────────────────────────────────────

@router.get(
    "/top-changes",
    summary="PEs with largest year-over-year funding changes",
)
def get_top_changes(
    direction: str | None = Query(
        None, description="Filter: 'increase', 'decrease', or None for both"),
    service: str | None = Query(None, description="Filter by service/org"),
    limit: int = Query(20, ge=1, le=100),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return PEs ranked by absolute FY2025→FY2026 funding delta.

    Useful for identifying programs gaining or losing significant funding.
    Results include PE title, organization, and percentage change.
    """
    conditions = ["b.pe_number IS NOT NULL"]
    params: list[Any] = []

    if service:
        conditions.append("b.organization_name LIKE ?")
        params.append(f"%{service}%")

    where = " AND ".join(conditions)

    rows = conn.execute(f"""
        SELECT
            b.pe_number,
            MAX(b.organization_name) AS organization_name,
            MAX(b.line_item_title)   AS display_title,
            SUM(COALESCE(b.amount_fy2025_total, 0))  AS fy2025_total,
            SUM(COALESCE(b.amount_fy2026_request, 0)) AS fy2026_request,
            SUM(COALESCE(b.amount_fy2026_request, 0))
                - SUM(COALESCE(b.amount_fy2025_total, 0)) AS delta
        FROM budget_lines b
        WHERE {where}
        GROUP BY b.pe_number
        HAVING fy2025_total != 0 OR fy2026_request != 0
        ORDER BY ABS(delta) DESC
        LIMIT ?
    """, params + [limit * 2]).fetchall()  # over-fetch for filtering

    items = []
    for r in rows:
        if len(items) >= limit:
            break
        d = _row_dict(r)
        fy25 = d["fy2025_total"] or 0
        fy26 = d["fy2026_request"] or 0
        delta = d["delta"] or 0

        if direction == "increase" and delta <= 0:
            continue
        if direction == "decrease" and delta >= 0:
            continue

        d["pct_change"] = (
            round(((fy26 - fy25) / abs(fy25)) * 100, 1) if fy25 != 0 else None
        )
        d["change_type"] = (
            "new" if fy25 == 0 and fy26 > 0
            else "terminated" if fy25 > 0 and fy26 == 0
            else "increase" if delta > 0
            else "decrease" if delta < 0
            else "flat"
        )
        items.append(d)

    return {"count": len(items), "items": items}


# ── GET /api/v1/pe/compare ───────────────────────────────────────────────────

@router.get(
    "/compare",
    summary="Side-by-side funding comparison of two or more PEs",
)
def compare_pes(
    pe: list[str] = Query(..., description="PE numbers to compare (2-10)"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return funding data for multiple PEs side by side.

    Each PE entry includes its title, organization, and funding amounts
    for FY2024-FY2026. Useful for the comparison chart view.
    """
    if len(pe) < 2:
        raise HTTPException(status_code=400, detail="At least 2 PE numbers required")
    if len(pe) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 PE numbers for comparison")

    ph = ",".join("?" * len(pe))

    # Get index info
    index_rows = conn.execute(
        f"SELECT pe_number, display_title, organization_name, budget_type "
        f"FROM pe_index WHERE pe_number IN ({ph})", pe,
    ).fetchall()
    index_map = {r["pe_number"]: _row_dict(r) for r in index_rows}

    # Get funding aggregates per PE
    funding_rows = conn.execute(f"""
        SELECT
            pe_number,
            SUM(COALESCE(amount_fy2024_actual, 0))  AS fy2024_actual,
            SUM(COALESCE(amount_fy2025_enacted, 0)) AS fy2025_enacted,
            SUM(COALESCE(amount_fy2025_total, 0))   AS fy2025_total,
            SUM(COALESCE(amount_fy2026_request, 0)) AS fy2026_request,
            SUM(COALESCE(amount_fy2026_total, 0))   AS fy2026_total
        FROM budget_lines
        WHERE pe_number IN ({ph})
        GROUP BY pe_number
    """, pe).fetchall()
    funding_map = {r["pe_number"]: _row_dict(r) for r in funding_rows}

    items = []
    for p in pe:
        entry = {
            "pe_number": p,
            "display_title": index_map.get(p, {}).get("display_title"),
            "organization_name": index_map.get(p, {}).get("organization_name"),
            "funding": funding_map.get(p, {}),
        }
        items.append(entry)

    return {"count": len(items), "items": items}


# ── GET /api/v1/pe/{pe_number} ────────────────────────────────────────────────

@router.get(
    "/{pe_number}",
    summary="Full PE detail: funding by year, tags, related PEs",
)
def get_pe(
    pe_number: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return the full PE record including:
    - Index entry (title, org, budget type)
    - Funding amounts by fiscal year from budget_lines
    - Tags from all sources
    - Related PE numbers (definite + suggested)
    """
    row = conn.execute(
        "SELECT * FROM pe_index WHERE pe_number = ?", (pe_number,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"PE {pe_number} not found in pe_index. "
                            "Run enrich_budget_db.py first.")
    index = _row_dict(row)
    index["fiscal_years"] = _json_list(index.get("fiscal_years"))
    index["exhibit_types"] = _json_list(index.get("exhibit_types"))

    # Funding by year
    funding_rows = conn.execute("""
        SELECT
            fiscal_year, exhibit_type, organization_name,
            account_title, budget_activity_title,
            amount_fy2024_actual, amount_fy2025_enacted, amount_fy2025_total,
            amount_fy2026_request, amount_fy2026_total,
            quantity_fy2024, quantity_fy2025, quantity_fy2026_request
        FROM budget_lines
        WHERE pe_number = ?
        ORDER BY fiscal_year, exhibit_type
    """, (pe_number,)).fetchall()

    # Tags (LION-106: include source_files for provenance display)
    tag_rows = conn.execute("""
        SELECT tag, tag_source, confidence, source_files FROM pe_tags
        WHERE pe_number = ?
        ORDER BY confidence DESC, tag
    """, (pe_number,)).fetchall()

    # Related PEs
    related_rows = conn.execute("""
        SELECT referenced_pe, link_type, confidence, fiscal_year, context_snippet
        FROM pe_lineage
        WHERE source_pe = ?
        ORDER BY confidence DESC, referenced_pe
        LIMIT 50
    """, (pe_number,)).fetchall()

    # Summary stats — quick counts for UI badges/indicators
    desc_count = conn.execute(
        "SELECT COUNT(*) FROM pe_descriptions WHERE pe_number = ?",
        (pe_number,),
    ).fetchone()[0]

    pdf_page_count = 0
    try:
        pdf_page_count = conn.execute(
            "SELECT COUNT(*) FROM pdf_pe_numbers WHERE pe_number = ?",
            (pe_number,),
        ).fetchone()[0]
    except Exception:
        pass

    return {
        "pe_number": pe_number,
        "index": index,
        "funding": [_row_dict(r) for r in funding_rows],
        "tags": [_row_dict(r) for r in tag_rows],
        "related": [_row_dict(r) for r in related_rows],
        "summary": {
            "funding_rows": len(funding_rows),
            "tag_count": len(tag_rows),
            "description_count": desc_count,
            "related_count": len(related_rows),
            "pdf_page_count": pdf_page_count,
        },
    }


# ── GET /api/v1/pe/{pe_number}/years ─────────────────────────────────────────

@router.get(
    "/{pe_number}/years",
    summary="Funding matrix: one row per fiscal year with all amount columns",
)
def get_pe_years(
    pe_number: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return a year × amount matrix for a PE — the primary funding table."""
    rows = conn.execute("""
        SELECT
            fiscal_year,
            exhibit_type,
            organization_name,
            SUM(amount_fy2024_actual)       AS fy2024_actual,
            SUM(amount_fy2025_enacted)      AS fy2025_enacted,
            SUM(amount_fy2025_total)        AS fy2025_total,
            SUM(amount_fy2026_request)      AS fy2026_request,
            SUM(amount_fy2026_total)        AS fy2026_total,
            SUM(quantity_fy2024)            AS qty_fy2024,
            SUM(quantity_fy2025)            AS qty_fy2025,
            SUM(quantity_fy2026_request)    AS qty_fy2026_request
        FROM budget_lines
        WHERE pe_number = ?
        GROUP BY fiscal_year, exhibit_type, organization_name
        ORDER BY fiscal_year, exhibit_type
    """, (pe_number,)).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No budget lines for PE {pe_number}")
    return {"pe_number": pe_number, "years": [_row_dict(r) for r in rows]}


# ── GET /api/v1/pe/{pe_number}/changes ────────────────────────────────────

@router.get(
    "/{pe_number}/changes",
    summary="Year-over-year funding changes for a PE",
)
def get_pe_changes(
    pe_number: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return year-over-year funding deltas for a PE.

    Compares FY2025 enacted/total vs FY2026 request to surface budget
    increases, decreases, and new/terminated line items. Useful for
    identifying programs gaining or losing funding.
    """
    rows = conn.execute("""
        SELECT
            line_item_title,
            exhibit_type,
            SUM(COALESCE(amount_fy2025_total, 0))     AS fy2025_total,
            SUM(COALESCE(amount_fy2026_request, 0))    AS fy2026_request,
            SUM(COALESCE(amount_fy2026_request, 0))
                - SUM(COALESCE(amount_fy2025_total, 0)) AS delta,
            CASE
                WHEN SUM(COALESCE(amount_fy2025_total, 0)) = 0
                     AND SUM(COALESCE(amount_fy2026_request, 0)) > 0
                    THEN 'new'
                WHEN SUM(COALESCE(amount_fy2025_total, 0)) > 0
                     AND SUM(COALESCE(amount_fy2026_request, 0)) = 0
                    THEN 'terminated'
                WHEN SUM(COALESCE(amount_fy2026_request, 0))
                     > SUM(COALESCE(amount_fy2025_total, 0))
                    THEN 'increase'
                WHEN SUM(COALESCE(amount_fy2026_request, 0))
                     < SUM(COALESCE(amount_fy2025_total, 0))
                    THEN 'decrease'
                ELSE 'flat'
            END AS change_type
        FROM budget_lines
        WHERE pe_number = ?
        GROUP BY line_item_title, exhibit_type
        HAVING fy2025_total != 0 OR fy2026_request != 0
        ORDER BY ABS(delta) DESC
    """, (pe_number,)).fetchall()

    # Compute PE-level totals
    total_fy25 = sum(r["fy2025_total"] or 0 for r in rows)
    total_fy26 = sum(r["fy2026_request"] or 0 for r in rows)
    pct_change = None
    if total_fy25 and total_fy25 != 0:
        pct_change = round(((total_fy26 - total_fy25) / abs(total_fy25)) * 100, 1)

    return {
        "pe_number": pe_number,
        "total_fy2025": total_fy25,
        "total_fy2026_request": total_fy26,
        "total_delta": total_fy26 - total_fy25,
        "pct_change": pct_change,
        "line_items": [_row_dict(r) for r in rows],
    }


# ── GET /api/v1/pe/{pe_number}/subelements ────────────────────────────────────

@router.get(
    "/{pe_number}/subelements",
    summary="Sub-elements of a PE for a given fiscal year",
)
def get_pe_subelements(
    pe_number: str,
    fy: str | None = Query(None, description="Filter by fiscal year, e.g. '2026'"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return all budget_lines rows for a PE (optionally filtered by year).

    Covers all sub-element types:
    - R-2/R-3 project lines (exhibit_type in r2, r3)
    - P-5 procurement line items (exhibit_type = p5)
    - Budget activity breakdowns within R-1/P-1 summary rows
    """
    params: list[Any] = [pe_number]
    fy_clause = ""
    if fy:
        fy_clause = "AND fiscal_year = ?"
        params.append(fy)

    rows = conn.execute(f"""
        SELECT
            id, fiscal_year, exhibit_type, organization_name,
            account_title, budget_activity, budget_activity_title,
            sub_activity, sub_activity_title,
            line_item, line_item_title,
            amount_fy2024_actual, amount_fy2025_enacted, amount_fy2025_total,
            amount_fy2026_request, amount_fy2026_total,
            quantity_fy2024, quantity_fy2025, quantity_fy2026_request,
            source_file
        FROM budget_lines
        WHERE pe_number = ? {fy_clause}
        ORDER BY exhibit_type, fiscal_year, line_item
    """, params).fetchall()

    return {
        "pe_number": pe_number,
        "fiscal_year": fy,
        "count": len(rows),
        "subelements": [_row_dict(r) for r in rows],
    }


# ── GET /api/v1/pe/{pe_number}/descriptions ───────────────────────────────────

@router.get(
    "/{pe_number}/descriptions",
    summary="Narrative description text for a PE",
)
def get_pe_descriptions(
    pe_number: str,
    fy: str | None = Query(None, description="Filter by fiscal year"),
    section: str | None = Query(None, description="Filter by section header (substring match)"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return narrative sections extracted from PDF pages for this PE.

    Supports filtering by fiscal year and section header name to drill into
    specific narrative blocks (e.g., 'Accomplishments', 'Acquisition Strategy').
    """
    params: list[Any] = [pe_number]
    clauses: list[str] = []
    if fy:
        clauses.append("AND fiscal_year = ?")
        params.append(fy)
    if section:
        clauses.append("AND section_header LIKE ?")
        params.append(f"%{section}%")

    extra_where = " ".join(clauses)

    total = conn.execute(
        f"SELECT COUNT(*) FROM pe_descriptions WHERE pe_number = ? {extra_where}",
        params,
    ).fetchone()[0]

    rows = conn.execute(f"""
        SELECT id, fiscal_year, source_file, page_start, page_end,
               section_header, description_text
        FROM pe_descriptions
        WHERE pe_number = ? {extra_where}
        ORDER BY fiscal_year, page_start
        LIMIT ? OFFSET ?
    """, params + [limit, offset]).fetchall()

    # Also return the distinct section headers for this PE (for UI filtering)
    headers = conn.execute(
        "SELECT DISTINCT section_header FROM pe_descriptions "
        "WHERE pe_number = ? AND section_header IS NOT NULL "
        "ORDER BY section_header",
        (pe_number,),
    ).fetchall()

    return {
        "pe_number": pe_number,
        "fiscal_year": fy,
        "section_filter": section,
        "total": total,
        "limit": limit,
        "offset": offset,
        "available_sections": [r[0] for r in headers],
        "descriptions": [_row_dict(r) for r in rows],
    }


# ── GET /api/v1/pe/{pe_number}/pdf-pages ─────────────────────────────────────

@router.get(
    "/{pe_number}/pdf-pages",
    summary="PDF pages mentioning this PE (via junction table)",
)
def get_pe_pdf_pages(
    pe_number: str,
    fy: str | None = Query(None, description="Filter by fiscal year"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return PDF pages that mention this PE number.

    LION-103: Uses the pdf_pe_numbers junction table for fast lookups
    instead of scanning pdf_pages text. Falls back to text search if the
    junction table is empty or missing.
    """
    params: list[Any] = [pe_number]
    fy_clause = ""
    if fy:
        fy_clause = "AND j.fiscal_year = ?"
        params.append(fy)

    # Try junction table first (LION-103)
    try:
        total = conn.execute(
            f"SELECT COUNT(*) FROM pdf_pe_numbers j "
            f"WHERE j.pe_number = ? {fy_clause}",
            params,
        ).fetchone()[0]
    except Exception:
        total = 0

    if total > 0:
        rows = conn.execute(f"""
            SELECT j.pe_number, j.page_number, j.source_file, j.fiscal_year,
                   pp.page_text, pp.has_tables, pp.exhibit_type
            FROM pdf_pe_numbers j
            JOIN pdf_pages pp ON pp.id = j.pdf_page_id
            WHERE j.pe_number = ? {fy_clause}
            ORDER BY j.source_file, j.page_number
            LIMIT ? OFFSET ?
        """, params + [limit, offset]).fetchall()
    else:
        # Fallback: text search on pdf_pages (pre-LION-103 databases)
        fb_params: list[Any] = [f"%{pe_number}%"]
        fb_fy = ""
        if fy:
            fb_fy = "AND fiscal_year = ?"
            fb_params.append(fy)

        total = conn.execute(
            f"SELECT COUNT(*) FROM pdf_pages "
            f"WHERE page_text LIKE ? {fb_fy}",
            fb_params,
        ).fetchone()[0]

        rows = conn.execute(f"""
            SELECT NULL AS pe_number, page_number, source_file, fiscal_year,
                   page_text, has_tables, exhibit_type
            FROM pdf_pages
            WHERE page_text LIKE ? {fb_fy}
            ORDER BY source_file, page_number
            LIMIT ? OFFSET ?
        """, fb_params + [limit, offset]).fetchall()

    return {
        "pe_number": pe_number,
        "fiscal_year": fy,
        "total": total,
        "limit": limit,
        "offset": offset,
        "pages": [_row_dict(r) for r in rows],
    }


# ── GET /api/v1/pe/{pe_number}/related ───────────────────────────────────────

@router.get(
    "/{pe_number}/related",
    summary="Related PE numbers detected via lineage analysis",
)
def get_pe_related(
    pe_number: str,
    min_confidence: float = Query(0.0, ge=0.0, le=1.0,
                                  description="Minimum confidence threshold"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return PE numbers related to this one, with link type and confidence.

    link_type values:
    - explicit_pe_ref  (confidence ~0.95): PE number explicitly mentioned in text
    - name_match       (confidence ~0.60): Program name matched across PE lines
    """
    rows = conn.execute("""
        SELECT
            l.referenced_pe,
            l.link_type,
            MAX(l.confidence) AS confidence,
            GROUP_CONCAT(DISTINCT l.fiscal_year) AS fiscal_years,
            COUNT(*) AS mention_count,
            MIN(l.context_snippet) AS sample_snippet,
            p.display_title AS referenced_title,
            p.organization_name AS referenced_org
        FROM pe_lineage l
        LEFT JOIN pe_index p ON p.pe_number = l.referenced_pe
        WHERE l.source_pe = ? AND l.confidence >= ?
        GROUP BY l.referenced_pe, l.link_type
        ORDER BY MAX(l.confidence) DESC, COUNT(*) DESC
    """, (pe_number, min_confidence)).fetchall()

    return {
        "pe_number": pe_number,
        "related_count": len(rows),
        "related": [_row_dict(r) for r in rows],
    }


# ── GET /api/v1/pe  (browse/search by tag or topic) ──────────────────────────

@router.get(
    "",
    summary="Browse or search PEs by tag, topic query, or filters",
)
def list_pes(
    tag: list[str] | None = Query(None, description="Filter by tag(s) (AND logic)"),
    q: str | None = Query(None, description="Free-text topic search via FTS5"),
    service: str | None = Query(None, description="Filter by service/org name"),
    budget_type: str | None = Query(None, description="Filter by budget type"),
    approp: str | None = Query(None, description="Filter by appropriation title (substring)"),
    ba: str | None = Query(None, description="Filter by budget activity title (substring, e.g. '6.2')"),
    fy: str | None = Query(None, description="Filter to PEs present in a fiscal year"),
    sort_by: str | None = Query(None, description="Sort field: pe_number (default), funding, name"),
    sort_dir: str | None = Query(None, description="Sort direction: asc (default) or desc"),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return a paginated list of PE numbers matching the given filters.

    Tag filtering uses AND logic — all specified tags must be present.
    Free-text search uses FTS5 against description text.
    """
    conditions: list[str] = []
    params: list[Any] = []

    # Base: always join against pe_index
    base_from = "pe_index p"

    # Tag filter — all tags must match (AND)
    if tag:
        for t in tag:
            base_from += f"""
                JOIN pe_tags pt_{len(params)} ON pt_{len(params)}.pe_number = p.pe_number
                    AND pt_{len(params)}.tag = ?"""
            params.append(t.lower())

    # Service filter
    if service:
        conditions.append("p.organization_name LIKE ?")
        params.append(f"%{service}%")

    # Budget type filter
    if budget_type:
        conditions.append("p.budget_type = ?")
        params.append(budget_type)

    # Appropriation filter (matches PE numbers that appear in budget_lines
    # with a matching appropriation_title)
    if approp:
        conditions.append("""p.pe_number IN (
            SELECT DISTINCT pe_number FROM budget_lines
            WHERE appropriation_title LIKE ?
        )""")
        params.append(f"%{approp}%")

    # Budget activity filter (e.g. "6.2" matches "6.2 Applied Research")
    if ba:
        conditions.append("""p.pe_number IN (
            SELECT DISTINCT pe_number FROM budget_lines
            WHERE budget_activity_title LIKE ?
        )""")
        params.append(f"%{ba}%")

    # Fiscal year filter (pe_index.fiscal_years is a JSON array)
    if fy:
        conditions.append("p.fiscal_years LIKE ?")
        params.append(f'%"{fy}"%')

    # FTS5 topic search — restrict to PEs that have matching description text.
    # Uses pe_descriptions_fts (FTS5) when available; falls back to LIKE scan.
    if q:
        safe_q = sanitize_fts5_query(q)
        if safe_q:
            # Try FTS5 first, fall back to LIKE if table doesn't exist
            try:
                conn.execute("SELECT 1 FROM pe_descriptions_fts LIMIT 0")
                conditions.append("""p.pe_number IN (
                    SELECT pe_number FROM pe_descriptions_fts
                    WHERE pe_descriptions_fts MATCH ?
                )""")
                params.append(safe_q)
            except Exception:
                conditions.append("""p.pe_number IN (
                    SELECT DISTINCT pe_number FROM pe_descriptions
                    WHERE description_text LIKE ?
                )""")
                params.append(f"%{q}%")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    count_sql = f"SELECT COUNT(DISTINCT p.pe_number) FROM {base_from} {where}"
    total = conn.execute(count_sql, params).fetchone()[0]

    # Determine sort column and direction
    _SORT_ALLOWED = {"pe_number", "funding", "name"}
    effective_sort = sort_by if sort_by in _SORT_ALLOWED else "pe_number"
    direction = "DESC" if sort_dir == "desc" else "ASC"

    if effective_sort == "funding":
        # Join budget_lines SUM so ORDER BY can reference it
        data_sql = f"""
            SELECT DISTINCT p.pe_number, p.display_title, p.organization_name,
                   p.budget_type, p.fiscal_years, p.exhibit_types,
                   COALESCE(bl_sum.total, 0) AS _sort_funding
            FROM {base_from}
            LEFT JOIN (
                SELECT pe_number, SUM(COALESCE(amount_fy2026_request, 0)) AS total
                FROM budget_lines GROUP BY pe_number
            ) bl_sum ON bl_sum.pe_number = p.pe_number
            {where}
            ORDER BY _sort_funding {direction}, p.pe_number
            LIMIT ? OFFSET ?
        """
    elif effective_sort == "name":
        data_sql = f"""
            SELECT DISTINCT p.pe_number, p.display_title, p.organization_name,
                   p.budget_type, p.fiscal_years, p.exhibit_types
            FROM {base_from} {where}
            ORDER BY p.display_title {direction}, p.pe_number
            LIMIT ? OFFSET ?
        """
    else:
        data_sql = f"""
            SELECT DISTINCT p.pe_number, p.display_title, p.organization_name,
                   p.budget_type, p.fiscal_years, p.exhibit_types
            FROM {base_from} {where}
            ORDER BY p.pe_number {direction}
            LIMIT ? OFFSET ?
        """
    rows = conn.execute(data_sql, params + [limit, offset]).fetchall()

    # Batch-fetch tags for all PEs in this page to avoid N+1 query pattern.
    # Single query instead of one per PE.
    pe_numbers = [r["pe_number"] for r in rows]
    tags_by_pe: dict[str, list[dict]] = {}
    if pe_numbers:
        ph = ",".join("?" * len(pe_numbers))
        all_tags = conn.execute(
            f"SELECT pe_number, tag, tag_source, confidence FROM pe_tags "
            f"WHERE pe_number IN ({ph}) ORDER BY confidence DESC, tag",
            pe_numbers,
        ).fetchall()
        for t in all_tags:
            tags_by_pe.setdefault(t["pe_number"], []).append(
                {"tag": t["tag"], "tag_source": t["tag_source"],
                 "confidence": t["confidence"]}
            )

    # Batch-fetch enrichment status and funding totals for all PEs in this page.
    desc_pes: set[str] = set()
    related_pes: set[str] = set()
    funding_by_pe: dict[str, float] = {}
    if pe_numbers:
        ph = ",".join("?" * len(pe_numbers))
        for r2 in conn.execute(
            f"SELECT DISTINCT pe_number FROM pe_descriptions "
            f"WHERE pe_number IN ({ph})", pe_numbers,
        ).fetchall():
            desc_pes.add(r2[0])
        try:
            for r2 in conn.execute(
                f"SELECT DISTINCT source_pe FROM pe_lineage "
                f"WHERE source_pe IN ({ph})", pe_numbers,
            ).fetchall():
                related_pes.add(r2[0])
        except Exception:
            pass
        # Latest-year funding total for sorting/display
        for r2 in conn.execute(
            f"SELECT pe_number, "
            f"  SUM(COALESCE(amount_fy2026_request, 0)) AS total_fy2026 "
            f"FROM budget_lines WHERE pe_number IN ({ph}) "
            f"GROUP BY pe_number", pe_numbers,
        ).fetchall():
            funding_by_pe[r2[0]] = r2[1] or 0.0

    items = []
    for r in rows:
        d = _row_dict(r)
        d["fiscal_years"] = _json_list(d.get("fiscal_years"))
        d["exhibit_types"] = _json_list(d.get("exhibit_types"))
        d["tags"] = tags_by_pe.get(r["pe_number"], [])
        d["has_descriptions"] = r["pe_number"] in desc_pes
        d["has_related"] = r["pe_number"] in related_pes
        d["total_fy2026_request"] = funding_by_pe.get(r["pe_number"], 0.0)
        items.append(d)

    return {"total": total, "limit": limit, "offset": offset, "items": items}


# ── GET /api/v1/tags ──────────────────────────────────────────────────────────

@router.get(
    "/tags/all",
    summary="All tags with PE counts (for autocomplete and filter UI)",
)
def list_tags(
    tag_source: str | None = Query(None,
        description="Filter by source: structured, keyword, taxonomy, llm"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return all distinct tags and how many PEs each applies to."""
    params: list[Any] = []
    src_clause = ""
    if tag_source:
        src_clause = "WHERE tag_source = ?"
        params.append(tag_source)

    rows = conn.execute(f"""
        SELECT tag, tag_source, COUNT(DISTINCT pe_number) AS pe_count
        FROM pe_tags
        {src_clause}
        GROUP BY tag, tag_source
        ORDER BY pe_count DESC, tag
    """, params).fetchall()

    return {"total": len(rows), "tags": [_row_dict(r) for r in rows]}


# ── GET /api/v1/pe/{pe_number}/export/table ───────────────────────────────────

@router.get(
    "/{pe_number}/export/table",
    summary="Export Spruill-style funding table as CSV",
    response_class=Response,
)
def export_pe_table(
    pe_number: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """Download a Spruill-chart-style funding table for a PE as CSV.

    Columns: PE, Title, Service, Exhibit, FY2024 Actual, FY2025 Enacted,
             FY2025 Total, FY2026 Request, FY2026 Total, % Change (25→26),
             Qty FY2024, Qty FY2025, Qty FY2026 Request
    """
    rows = conn.execute("""
        SELECT
            pe_number, line_item_title, organization_name,
            exhibit_type, fiscal_year,
            amount_fy2024_actual, amount_fy2025_enacted, amount_fy2025_total,
            amount_fy2026_request, amount_fy2026_total,
            quantity_fy2024, quantity_fy2025, quantity_fy2026_request
        FROM budget_lines
        WHERE pe_number = ?
        ORDER BY exhibit_type, fiscal_year, line_item_title
    """, (pe_number,)).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail=f"No budget lines for PE {pe_number}")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "PE Number", "Title", "Service", "Exhibit Type", "Fiscal Year",
        "FY2024 Actual ($K)", "FY2025 Enacted ($K)", "FY2025 Total ($K)",
        "FY2026 Request ($K)", "FY2026 Total ($K)",
        "% Change (FY25 Total → FY26 Req)",
        "Qty FY2024", "Qty FY2025", "Qty FY2026 Request",
    ])
    for r in rows:
        fy25 = r["amount_fy2025_total"] or 0.0
        fy26 = r["amount_fy2026_request"] or 0.0
        pct_change = ""
        if fy25 and fy25 != 0:
            pct_change = f"{((fy26 - fy25) / abs(fy25)) * 100:.1f}%"
        writer.writerow([
            r["pe_number"], r["line_item_title"], r["organization_name"],
            r["exhibit_type"], r["fiscal_year"],
            r["amount_fy2024_actual"], r["amount_fy2025_enacted"],
            r["amount_fy2025_total"], r["amount_fy2026_request"],
            r["amount_fy2026_total"], pct_change,
            r["quantity_fy2024"], r["quantity_fy2025"],
            r["quantity_fy2026_request"],
        ])

    csv_bytes = buf.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="pe_{pe_number}_funding.csv"'
        },
    )


# ── GET /api/v1/pe/export/pages ───────────────────────────────────────────────

@router.get(
    "/export/pages",
    summary="ZIP of PDF page text for a set of PE numbers",
    response_class=Response,
)
def export_pe_pages(
    pe: list[str] = Query(..., description="One or more PE numbers"),
    fy: str | None = Query(None, description="Limit to a specific fiscal year"),
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """Download a ZIP file containing the extracted text of all PDF pages
    associated with the specified PE numbers.

    Each file in the ZIP is named: {pe_number}_{fy}_{source_file_stem}_p{page}.txt
    """
    if not pe:
        raise HTTPException(status_code=400, detail="At least one pe= parameter is required.")
    if len(pe) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 PE numbers per export.")

    fy_clause = "AND d.fiscal_year = ?" if fy else ""
    params: list[Any] = pe + ([fy] if fy else [])

    pe_placeholders = ",".join("?" * len(pe))
    rows = conn.execute(f"""
        SELECT DISTINCT d.pe_number, d.fiscal_year, d.source_file,
               d.page_start, d.page_end, pp.page_number, pp.page_text
        FROM pe_descriptions d
        JOIN pdf_pages pp ON pp.source_file = d.source_file
            AND pp.page_number BETWEEN d.page_start AND d.page_end
        WHERE d.pe_number IN ({pe_placeholders}) {fy_clause}
        ORDER BY d.pe_number, d.fiscal_year, d.source_file, pp.page_number
    """, params).fetchall()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No PDF pages found for the specified PE(s). "
                   "Run enrich_budget_db.py Phase 2 first."
        )

    # Build ZIP in memory
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in rows:
            stem = Path(r["source_file"]).stem[:40]
            fname = (
                f"{r['pe_number']}/"
                f"{r['fiscal_year'] or 'unk'}/"
                f"{stem}_p{r['page_number']:04d}.txt"
            )
            zf.writestr(fname, r["page_text"] or "")

    pe_label = "_".join(pe[:3]) + ("_etc" if len(pe) > 3 else "")
    return Response(
        content=zip_buf.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="pe_{pe_label}_pages.zip"'
        },
    )
