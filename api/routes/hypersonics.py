"""
Hypersonics PE lines endpoints.

Returns a pivoted view of all budget lines related to hypersonics programs,
FY2015 onward. Sources: budget_lines keyword search + pe_descriptions narrative search.

Matching logic (PE-level): a PE number is included if ANY of its budget_lines rows match
a keyword OR if any pe_descriptions row for that PE matches a keyword. Once a PE is
matched, ALL of its sub-elements (line_item_title rows) are returned — not just the
rows that individually match a keyword.

Data is served from a pre-computed ``hypersonics_cache`` table for instant reads.
Call ``rebuild_hypersonics_cache(conn)`` after pipeline/enrichment runs, or hit the
POST /api/v1/hypersonics/rebuild endpoint to refresh.

Endpoints:
  GET  /api/v1/hypersonics          — JSON, pivoted table data
  GET  /api/v1/hypersonics/download — streaming CSV of pivoted table
  GET  /api/v1/hypersonics/debug    — data-quality checks
  POST /api/v1/hypersonics/rebuild  — rebuild the materialized cache table
"""

from __future__ import annotations

import csv
import io
import json
import logging
import sqlite3
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import Response

from api.database import get_db
from api.routes.keyword_search import (
    FY_END,
    FY_START,
    apply_filters,
    build_cache_table,
    cache_rows_to_dicts,
    ensure_cache,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hypersonics", tags=["hypersonics"])

# ── Keywords ──────────────────────────────────────────────────────────────────

_HYPERSONICS_KEYWORDS = [
    # ── Generic / cross-program ───────────────────────────────────────────
    "hypersonic",           # hypersonics, hypersonic glide, hypersonic weapon…
    "boost glide",          # boost-glide vehicles (all services)
    "glide body",           # Common Hypersonic Glide Body (C-HGB)
    "glide vehicle",        # generic glide vehicle references
    "scramjet",             # air-breathing hypersonic propulsion

    # ── Offensive — Air Force ──────────────────────────────────────────────
    "ARRW",                 # Air-Launched Rapid Response Weapon (AGM-183A)
    "AGM-183",              # ARRW missile designation
    "HACM",                 # Hypersonic Attack Cruise Missile
    "HCSW",                 # Hypersonic Conventional Strike Weapon (cancelled FY20)

    # ── Offensive — Army ───────────────────────────────────────────────────
    "LRHW",                 # Long Range Hypersonic Weapon / Dark Eagle battery
    "Dark Eagle",           # LRHW battery name
    "OpFires",              # Operational Fires (hypersonic component)

    # ── Offensive — Navy / Joint ───────────────────────────────────────────
    "C-HGB",                # Common Hypersonic Glide Body (joint Army/Navy)
    "CHGB",                 # alternate abbreviation
    "conventional prompt strike",   # Navy CPS program
    "prompt strike",        # catches "Intermediate Range Conventional Prompt Strike"

    # ── Defensive / tracking ───────────────────────────────────────────────
    "Glide Phase Interceptor",  # GPI — MDA program to defeat HGVs in glide
    "HBTSS",                # Hypersonic and Ballistic Tracking Space Sensor
]

_DESC_KEYWORDS = [
    "hypersonic",
    "boost glide",
    "glide vehicle",
    "scramjet",
    "ARRW",
    "HACM",
    "HCSW",
    "LRHW",
    "Dark Eagle",
    "C-HGB",
    "CHGB",
    "conventional prompt strike",
    "prompt strike",
    "Glide Phase Interceptor",
    "HBTSS",
    "OpFires",
]

_CACHE_TABLE = "hypersonics_cache"

# PEs to always include regardless of keyword matching
_EXTRA_PES = [
    "0101101F", "0210600A", "0601102F", "0601153N", "0602102F",
    "0602114N", "0602235N", "0602602F", "0602750N", "0603032F",
    "0603183D8Z", "0603273F", "0603467E", "0603601F", "0603673N",
    "0603680D8Z", "0603680F", "0603941D8Z", "0603945D8Z", "0604250D8Z",
    "0604331D8Z", "0604940D8Z", "0605456A", "0607210D8Z", "0902199D8Z",
]


# ── Cache management ──────────────────────────────────────────────────────────

def rebuild_hypersonics_cache(conn: sqlite3.Connection) -> int:
    """Rebuild the hypersonics_cache table from budget_lines + pe_descriptions."""
    logger.info("Rebuilding hypersonics cache table...")
    return build_cache_table(
        conn, _CACHE_TABLE, _HYPERSONICS_KEYWORDS, _DESC_KEYWORDS,
        fy_start=FY_START, fy_end=FY_END, extra_pes=_EXTRA_PES,
    )


def _ensure_cache(conn: sqlite3.Connection) -> bool:
    """Ensure hypersonics_cache exists and is populated."""
    return ensure_cache(
        conn, _CACHE_TABLE, _HYPERSONICS_KEYWORDS, _DESC_KEYWORDS,
        fy_start=FY_START, fy_end=FY_END, extra_pes=_EXTRA_PES,
    )


# ── GET /api/v1/hypersonics ───────────────────────────────────────────────────

@router.get(
    "",
    summary="Pivoted hypersonics PE lines from materialized cache",
)
def get_hypersonics(
    service: str | None = Query(None, description="Filter by service/org name (substring)"),
    exhibit: str | None = Query(None, description="Filter by exhibit type (exact, e.g. 'r2')"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return all hypersonics-related budget line sub-elements as a pivoted table."""
    _ensure_cache(conn)

    extra_where, extra_params = apply_filters(service, exhibit, None, None)
    where = f"WHERE {extra_where}" if extra_where else ""
    sql = f"SELECT * FROM {_CACHE_TABLE} {where} ORDER BY pe_number, exhibit_type, line_item_title"
    rows = conn.execute(sql, extra_params).fetchall()

    year_range = list(range(FY_START, FY_END + 1))
    items = cache_rows_to_dicts(rows)
    active_years = (
        [yr for yr in year_range if any(r.get(f"fy{yr}") is not None for r in items)]
        if items else year_range
    )

    return {
        "count": len(items),
        "fiscal_years": active_years,
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
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """Download pivoted hypersonics PE lines as CSV."""
    _ensure_cache(conn)

    extra_where, extra_params = apply_filters(service, exhibit, None, None)
    where = f"WHERE {extra_where}" if extra_where else ""
    sql = f"SELECT * FROM {_CACHE_TABLE} {where} ORDER BY pe_number, exhibit_type, line_item_title"
    rows = conn.execute(sql, extra_params).fetchall()

    year_range = list(range(FY_START, FY_END + 1))
    items = cache_rows_to_dicts(rows)

    fy_headers: list[str] = []
    for yr in year_range:
        fy_headers.extend([f"FY{yr} ($K)", f"FY{yr} Source"])

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "PE Number", "Service/Org", "Exhibit Type", "Line Item Title",
        "Budget Activity", "Budget Activity (Normalized)", "Appropriation",
        "Color of Money", "Keywords (Row)", "Keywords (Desc)", "Description",
        *fy_headers,
    ])
    for r in items:
        fy_cells: list[Any] = []
        for yr in year_range:
            fy_cells.append(r.get(f"fy{yr}"))
            fy_cells.append(r.get("refs", {}).get(f"fy{yr}", ""))
        writer.writerow([
            r["pe_number"], r["organization_name"], r["exhibit_type"],
            r["line_item_title"], r["budget_activity_title"],
            r["budget_activity_norm"], r["appropriation_title"],
            r["color_of_money"],
            ", ".join(r.get("matched_keywords_row", [])),
            ", ".join(r.get("matched_keywords_desc", [])),
            r.get("description_text", ""),
            *fy_cells,
        ])

    csv_bytes = buf.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="hypersonics_pe_lines.csv"'},
    )


# ── POST /api/v1/hypersonics/download/xlsx ────────────────────────────────────

@router.post(
    "/download/xlsx",
    summary="Download selected hypersonics rows as XLSX with formatting",
    response_class=Response,
)
def download_hypersonics_xlsx(
    show_ids: list[str] = Body(..., description="data-idx values of SHOW-checked rows"),
    total_ids: list[str] = Body(..., description="data-idx values of TOTAL-checked rows"),
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """Download an XLSX with all SHOW-checked rows.

    Rows that are SHOW-only (not TOTAL-checked) are rendered in italics.
    Rows that are TOTAL-checked get normal formatting.
    A "Totals" row is appended at the bottom summing the TOTAL-checked FY columns.
    """
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    _ensure_cache(conn)

    year_range = list(range(FY_START, FY_END + 1))

    # Fetch all cache rows, grouped by PE as the template does
    sql = f"SELECT * FROM {_CACHE_TABLE} ORDER BY pe_number, exhibit_type, line_item_title"
    all_rows = conn.execute(sql).fetchall()
    items = cache_rows_to_dicts(all_rows)

    # Group by PE (preserving order) and assign data-idx values matching the template
    from collections import OrderedDict
    pe_groups: OrderedDict[str, list[dict]] = OrderedDict()
    for item in items:
        pe = item["pe_number"]
        pe_groups.setdefault(pe, []).append(item)

    # Build lookup: data-idx → (row_dict, child_index_in_pe)
    idx_to_row: dict[str, dict] = {}
    for pe, children in pe_groups.items():
        for i, child in enumerate(children):
            idx = f"{pe}-{i}"
            idx_to_row[idx] = child

    show_set = set(show_ids)
    total_set = set(total_ids)

    # Filter to only SHOW-checked rows, preserving order
    selected_rows: list[tuple[str, dict]] = []  # (data_idx, row_dict)
    for pe, children in pe_groups.items():
        for i, child in enumerate(children):
            idx = f"{pe}-{i}"
            if idx in show_set:
                selected_rows.append((idx, child))

    if not selected_rows:
        return Response(
            content=b"No rows selected",
            media_type="text/plain",
            status_code=400,
        )

    # Detect which FY columns have any data in selected rows
    active_years = [
        yr for yr in year_range
        if any(row.get(f"fy{yr}") is not None for _, row in selected_rows)
    ]

    # Build per-FY description map from pe_descriptions
    selected_pes = list({row.get("pe_number") for _, row in selected_rows if row.get("pe_number")})
    desc_by_pe_fy: dict[tuple[str, str], str] = {}
    if selected_pes:
        pe_placeholders = ", ".join("?" for _ in selected_pes)
        desc_rows = conn.execute(
            f"SELECT pe_number, fiscal_year, section_header, description_text "
            f"FROM pe_descriptions "
            f"WHERE pe_number IN ({pe_placeholders}) "
            f"  AND section_header IS NOT NULL "
            f"ORDER BY pe_number, fiscal_year, "
            f"  CASE "
            f"    WHEN section_header LIKE '%Mission Description%' THEN 1 "
            f"    WHEN section_header LIKE '%Accomplishments%' THEN 2 "
            f"    WHEN section_header LIKE '%Acquisition Strategy%' THEN 3 "
            f"    ELSE 4 END",
            selected_pes,
        ).fetchall()
        for dr in desc_rows:
            key = (dr[0], dr[1])  # (pe_number, fiscal_year)
            if key not in desc_by_pe_fy and dr[3] and len(dr[3].strip()) >= 80:
                desc_by_pe_fy[key] = dr[3].strip()

    # Build workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hypersonics"

    # Styles
    header_fill = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
    header_font_white = Font(bold=True, size=11, color="FFFFFF")
    italic_font = Font(italic=True, color="888888", size=10)
    normal_font = Font(size=10)
    total_font = Font(bold=True, size=11)
    money_fmt = '#,##0'
    desc_font = Font(size=9, color="444444")
    desc_font_italic = Font(size=9, color="999999", italic=True)

    # Headers: fixed cols + FY funding + FY descriptions
    headers = [
        "PE Number", "Service/Org", "Exhibit", "Line Item / Sub-Program",
        "Budget Activity", "Color of Money", "Description", "In Totals",
    ]
    for yr in active_years:
        headers.append(f"FY{yr} ($K)")
    for yr in active_years:
        headers.append(f"Desc FY{yr}")

    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    fixed_col_count = 8  # PE through In Totals
    fy_funding_count = len(active_years)

    # Data rows
    total_sums: dict[int, float] = {}  # FY year → sum
    row_num = 2
    for data_idx, row in selected_rows:
        is_total = data_idx in total_set
        font = normal_font if is_total else italic_font

        vals = [
            row.get("pe_number", ""),
            row.get("organization_name", ""),
            row.get("exhibit_type", ""),
            row.get("line_item_title", ""),
            row.get("budget_activity_norm", ""),
            row.get("color_of_money", ""),
            row.get("description_text", ""),
            "Yes" if is_total else "",
        ]
        for i, v in enumerate(vals, 1):
            cell = ws.cell(row=row_num, column=i, value=v)
            cell.font = font

        # FY funding columns
        for fy_col_idx, yr in enumerate(active_years):
            col = fixed_col_count + fy_col_idx + 1
            amount = row.get(f"fy{yr}")
            cell = ws.cell(row=row_num, column=col, value=amount)
            cell.font = font
            if amount is not None:
                cell.number_format = money_fmt
                if is_total:
                    total_sums[yr] = total_sums.get(yr, 0) + amount

        # FY description columns
        pe = row.get("pe_number", "")
        d_font = desc_font if is_total else desc_font_italic
        for desc_col_idx, yr in enumerate(active_years):
            col = fixed_col_count + fy_funding_count + desc_col_idx + 1
            desc_text = desc_by_pe_fy.get((pe, str(yr)), "")
            if desc_text:
                cell = ws.cell(row=row_num, column=col, value=desc_text)
                cell.font = d_font
                cell.alignment = Alignment(wrap_text=True, vertical="top")

        row_num += 1

    # Totals row
    if total_sums:
        ws.cell(row=row_num, column=1, value="TOTALS").font = total_font
        ws.cell(row=row_num, column=fixed_col_count, value="Sum").font = total_font
        for fy_col_idx, yr in enumerate(active_years):
            col = fixed_col_count + fy_col_idx + 1
            val = total_sums.get(yr)
            if val is not None:
                cell = ws.cell(row=row_num, column=col, value=val)
                cell.font = total_font
                cell.number_format = money_fmt

    # Column widths
    col_widths = (
        [14, 14, 8, 50, 20, 12, 60, 10]
        + [14] * fy_funding_count
        + [40] * fy_funding_count
    )
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # Freeze panes: freeze header row + first 4 columns
    ws.freeze_panes = "E2"

    # Auto-filter
    ws.auto_filter.ref = ws.dimensions

    # Write to bytes
    buf = io.BytesIO()
    wb.save(buf)
    xlsx_bytes = buf.getvalue()

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="hypersonics_selected.xlsx"'},
    )


# ── POST /api/v1/hypersonics/rebuild ──────────────────────────────────────────

@router.post(
    "/rebuild",
    summary="Rebuild the materialized hypersonics cache table",
)
def rebuild_cache(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Rebuild the hypersonics_cache table from budget_lines + pe_descriptions."""
    count = rebuild_hypersonics_cache(conn)
    return {"status": "ok", "rows": count}


# ── GET /api/v1/hypersonics/desc ──────────────────────────────────────────────

@router.get(
    "/desc/{pe_number}",
    summary="Get description text for a PE or R-2 project",
)
def get_description(
    pe_number: str,
    project: str | None = None,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return description_text for a PE (R-1 level) or specific R-2 project row."""
    try:
        if project:
            row = conn.execute(
                f"SELECT description_text FROM {_CACHE_TABLE} "
                "WHERE pe_number = ? AND line_item_title = ? AND description_text IS NOT NULL LIMIT 1",
                [pe_number, project],
            ).fetchone()
        else:
            row = conn.execute(
                f"SELECT description_text FROM {_CACHE_TABLE} "
                "WHERE pe_number = ? AND exhibit_type = 'r2' AND description_text IS NOT NULL LIMIT 1",
                [pe_number],
            ).fetchone()
            if not row:
                row = conn.execute(
                    f"SELECT description_text FROM {_CACHE_TABLE} "
                    "WHERE pe_number = ? AND description_text IS NOT NULL LIMIT 1",
                    [pe_number],
                ).fetchone()
        return {"description": row[0] if row else None}
    except sqlite3.OperationalError:
        return {"description": None}


# ── GET /api/v1/hypersonics/debug ─────────────────────────────────────────────

@router.get(
    "/debug",
    summary="Pre-flight data quality checks for the hypersonics view",
)
def debug_hypersonics(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Surface data-quality stats to validate the hypersonics view against real data."""
    result: dict = {}

    # 1. Cache status
    try:
        cache_count = conn.execute(f"SELECT COUNT(*) FROM {_CACHE_TABLE}").fetchone()[0]
        distinct_pes = conn.execute(
            f"SELECT COUNT(DISTINCT pe_number) FROM {_CACHE_TABLE}"
        ).fetchone()[0]
        result["cache"] = {
            "table_exists": True,
            "row_count": cache_count,
            "distinct_pe_numbers": distinct_pes,
        }
    except sqlite3.OperationalError:
        result["cache"] = {"table_exists": False, "row_count": 0}

    # 2. pe_descriptions status
    try:
        conn.execute("SELECT 1 FROM pe_descriptions LIMIT 0")
        row_count = conn.execute("SELECT COUNT(*) FROM pe_descriptions").fetchone()[0]
        pe_count = conn.execute(
            "SELECT COUNT(DISTINCT pe_number) FROM pe_descriptions"
        ).fetchone()[0]
        result["pe_descriptions"] = {
            "table_exists": True,
            "row_count": row_count,
            "distinct_pe_numbers": pe_count,
            "populated": row_count > 0,
        }
    except sqlite3.OperationalError:
        result["pe_descriptions"] = {"table_exists": False, "populated": False}

    # 3. Keyword hit summary from cache
    if result.get("cache", {}).get("table_exists"):
        try:
            kw_rows = conn.execute(
                f"SELECT matched_keywords_row, matched_keywords_desc FROM {_CACHE_TABLE}"
            ).fetchall()
            row_counts: dict[str, int] = {}
            desc_counts: dict[str, int] = {}
            for r in kw_rows:
                for kw in json.loads(r[0] or "[]"):
                    row_counts[kw] = row_counts.get(kw, 0) + 1
                for kw in json.loads(r[1] or "[]"):
                    desc_counts[kw] = desc_counts.get(kw, 0) + 1
            all_kw_counts = {kw: row_counts.get(kw, 0) + desc_counts.get(kw, 0) for kw in set(list(row_counts) + list(desc_counts))}
            result["keyword_hit_counts"] = {"row": row_counts, "desc": desc_counts, "combined": all_kw_counts}
            result["keywords_with_zero_hits"] = [
                kw for kw in _HYPERSONICS_KEYWORDS if kw not in all_kw_counts
            ]
        except Exception:
            pass

    return result
