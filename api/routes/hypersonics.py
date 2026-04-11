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
from collections import Counter, OrderedDict
from typing import Any

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import Response

from api.database import get_db
from api.routes.keyword_search import (
    FY_END,
    FY_START,
    apply_filters,
    build_cache_table,
    build_keyword_xlsx,
    cache_rows_to_dicts,
    ensure_cache,
    load_per_fy_descriptions,
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

    # ── Offensive — Navy / SM-6 / OASUW ──────────────────────────────────
    "offensive anti",       # Offensive Anti-Surface Warfare references
    "oasuw",                # Offensive Anti-Surface Warfare (OASUW)
    "standard missile 6",   # Standard Missile 6 (SM-6)
    "sm-6",                 # SM-6 abbreviation
    "blk ib",               # Block IB variant designation
    "increment ii",         # program increment references

    # ── Generic speed / regime ─────────────────────────────────────────────
    "high speed",           # high-speed strike / high-speed weapons
    "mach",                 # Mach-regime references (broad)
    "conventional prompt",  # broader catch for conventional prompt programs

    # ── Defensive / tracking ───────────────────────────────────────────────
    "Glide Phase Interceptor",  # GPI — MDA program to defeat HGVs in glide
    "HBTSS",                # Hypersonic and Ballistic Tracking Space Sensor
]

# Keywords excluded from description search (too noisy for narrative matching).
_DESC_EXCLUDE = {"glide body", "AGM-183"}
_DESC_KEYWORDS = [kw for kw in _HYPERSONICS_KEYWORDS if kw not in _DESC_EXCLUDE]

_CACHE_TABLE = "hypersonics_cache"

# Fixed (non-FY) columns in the XLSX export, in order.
_XLSX_FIXED_HEADERS: list[str] = [
    "PE Number", "Service/Org", "Exhibit", "Line Item / Sub-Program",
    "Budget Activity", "Color of Money",
]
_XLSX_COL_TO_FIELD: list[tuple[str, str]] = [
    ("PE Number", "pe_number"),
    ("Service/Org", "organization_name"),
    ("Exhibit", "exhibit_type"),
    ("Line Item / Sub-Program", "line_item_title"),
    ("Budget Activity", "budget_activity_norm"),
    ("Color of Money", "color_of_money"),
]


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


def _query_cache(
    conn: sqlite3.Connection,
    service: str | None = None,
    exhibit: str | None = None,
) -> tuple[list[dict], list[int]]:
    """Query the hypersonics cache with optional filters. Returns (items, year_range)."""
    _ensure_cache(conn)
    extra_where, extra_params = apply_filters(service, exhibit, None, None)
    where = f"WHERE {extra_where}" if extra_where else ""
    sql = f"SELECT * FROM {_CACHE_TABLE} {where} ORDER BY pe_number, exhibit_type, line_item_title"
    rows = conn.execute(sql, extra_params).fetchall()
    return cache_rows_to_dicts(rows), list(range(FY_START, FY_END + 1))


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
    items, year_range = _query_cache(conn, service, exhibit)
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
    items, year_range = _query_cache(conn, service, exhibit)

    fy_headers: list[str] = []
    for yr in year_range:
        fy_headers.extend([f"FY{yr} ($K)", f"FY{yr} Source"])

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "PE Number", "Service/Org", "Exhibit", "Line Item / Sub-Program",
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

    TOTAL-checked rows are marked Y; SHOW-only rows are marked N.
    Three totals rows (Y / P / Grand Total) and a Summary pivot sheet are included.
    """
    _ensure_cache(conn)

    year_range = list(range(FY_START, FY_END + 1))

    sql = f"SELECT * FROM {_CACHE_TABLE} ORDER BY pe_number, exhibit_type, line_item_title"
    all_rows = conn.execute(sql).fetchall()
    items = cache_rows_to_dicts(all_rows)

    pe_groups: OrderedDict[str, list[dict]] = OrderedDict()
    for item in items:
        pe = item["pe_number"]
        pe_groups.setdefault(pe, []).append(item)

    show_set = set(show_ids)
    total_set = set(total_ids)

    # Build idx→row mapping, filter to SHOW-checked, tag each row with its data-idx
    selected: list[dict] = []
    for pe, children in pe_groups.items():
        for i, child in enumerate(children):
            idx = f"{pe}-{i}"
            if idx in show_set:
                child["_data_idx"] = idx
                selected.append(child)

    if not selected:
        return Response(content=b"No rows selected", media_type="text/plain", status_code=400)

    active_years = [
        yr for yr in year_range
        if any(row.get(f"fy{yr}") is not None for row in selected)
    ]

    desc_by_pe_fy = load_per_fy_descriptions(
        conn, {row.get("pe_number", "") for row in selected}
    )

    xlsx_bytes = build_keyword_xlsx(
        items=selected,
        active_years=active_years,
        desc_by_pe_fy=desc_by_pe_fy,
        is_total_fn=lambda row: row.get("_data_idx", "") in total_set,
        fixed_columns=_XLSX_COL_TO_FIELD,
        sheet_title="Hypersonics",
    )

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
        logger.warning("OperationalError fetching description for PE %s", pe_number, exc_info=True)
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
            row_counts: Counter[str] = Counter()
            desc_counts: Counter[str] = Counter()
            for r in kw_rows:
                row_counts.update(json.loads(r[0] or "[]"))
                desc_counts.update(json.loads(r[1] or "[]"))
            all_kw_counts = dict(row_counts + desc_counts)
            result["keyword_hit_counts"] = {"row": row_counts, "desc": desc_counts, "combined": all_kw_counts}
            result["keywords_with_zero_hits"] = [
                kw for kw in _HYPERSONICS_KEYWORDS if kw not in all_kw_counts
            ]
        except Exception:
            pass

    return result
