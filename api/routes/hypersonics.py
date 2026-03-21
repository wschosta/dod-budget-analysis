"""
Hypersonics PE lines endpoints.

Returns a pivoted view of all budget lines related to hypersonics programs,
FY2015 onward. Sources: budget_lines keyword search + pe_descriptions narrative search.

Matching logic (PE-level): a PE number is included if ANY of its budget_lines rows match
a keyword OR if any pe_descriptions row for that PE matches a keyword. Once a PE is
matched, ALL of its sub-elements (line_item_title rows) are returned — not just the
rows that individually match a keyword.

Each row is a unique (pe_number, exhibit_type, line_item_title) combination.
Columns fy2015–fy2026 show the primary requested/enacted amount ($K) from
that fiscal year's budget document.

Each fy{N} amount column has a companion fy{N}_ref column containing the source
filename for that cell, suitable for citation tooltips in the UI.

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
#
# TODO(real-data): audit keyword recall against the live database. Candidates to add:
#   "boost glide", "HCM", "LRHW Block", "MACH", "LRPF", "HCSW Block",
#   "OpFires" (Army offensive fires — includes hypersonic component),
#   "DAAL" (Glide Phase Interceptor predecessor).
#   Run GET /api/v1/hypersonics/debug?show_misses=1 and eyeball pe_number outliers.
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
    """Map appropriation title to a standard color-of-money category.

    TODO(real-data): check GET /api/v1/hypersonics/debug for any rows landing in
    "Unknown" or returning verbatim approp_title strings. Real budget documents
    sometimes use phrasing like "Research, Development, Test & Evaluation, Navy"
    (already covered) or unusual variants like "Defense-Wide RDT&E" or
    "Missile Procurement, Army" — add matches here if needed.
    """
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

def _build_pe_match_where(conn: sqlite3.Connection) -> tuple[str, list[Any]]:
    """Return a WHERE fragment that selects ALL sub-elements of matching PEs.

    A PE is "matching" if:
      (a) any of its budget_lines rows match a hypersonics keyword in a key column, OR
      (b) any pe_descriptions row for that PE mentions a hypersonics keyword.

    By operating at the PE level (via UNION subquery), we return every sub-element
    of a matched PE — not just the individual rows that happen to mention the keyword.
    """
    # ── (a) Budget-lines keyword match ────────────────────────────────────────
    kw_clauses: list[str] = []
    kw_params: list[Any] = []
    for col in _SEARCH_COLS:
        for kw in _HYPERSONICS_KEYWORDS:
            kw_clauses.append(f"{col} LIKE ?")
            kw_params.append(f"%{kw}%")
    kw_where = " OR ".join(kw_clauses)

    union_parts = [f"SELECT DISTINCT pe_number FROM budget_lines WHERE {kw_where}"]
    all_params: list[Any] = list(kw_params)

    # ── (b) pe_descriptions narrative match ───────────────────────────────────
    # TODO(real-data): pe_descriptions is populated by the enrichment pipeline
    # (`python enrich_budget_db.py`). If it is empty, this UNION arm is a no-op
    # and recall falls back to budget-lines keyword matching only. Run the debug
    # endpoint to check pe_descriptions row count before assuming full coverage.
    try:
        conn.execute("SELECT 1 FROM pe_descriptions LIMIT 0")
        desc_clauses = ["description_text LIKE ?" for _ in _DESC_KEYWORDS]
        desc_params = [f"%{kw}%" for kw in _DESC_KEYWORDS]
        union_parts.append(
            "SELECT DISTINCT pe_number FROM pe_descriptions"
            f" WHERE {' OR '.join(desc_clauses)}"
        )
        all_params.extend(desc_params)
    except sqlite3.OperationalError:
        pass  # pe_descriptions table not yet populated — skip

    fragment = "pe_number IN (\n  " + "\n  UNION\n  ".join(union_parts) + "\n)"
    return fragment, all_params


def _build_pivot_query(
    conn: sqlite3.Connection,
    all_amount_cols: set[str],
    extra_where: str = "",
    extra_params: list[Any] | None = None,
) -> tuple[str, list[Any]]:
    """Build the pivoted SELECT query.

    For each fiscal year N in [_FY_START, _FY_END], emits TWO columns:
      • fy{N}      — SUM of best available amount (request → total → enacted → actual)
      • fy{N}_ref  — source filename for that cell (for citation tooltips)

    Rows are matched at the PE level: any PE whose sub-elements or descriptions
    mention a hypersonics keyword contributes ALL of its sub-elements.
    """
    pe_where, pe_params = _build_pe_match_where(conn)

    # Per-year pivot columns (amount + source reference)
    year_parts: list[str] = []
    for yr in range(_FY_START, _FY_END + 1):
        priority = [
            f"amount_fy{yr}_request",
            f"amount_fy{yr}_total",
            f"amount_fy{yr}_enacted",
            f"amount_fy{yr}_actual",
        ]
        available = [c for c in priority if c in all_amount_cols]
        # TODO(real-data): verify the real schema has amount_fy{N}_request populated
        # for recent years. GET /api/v1/hypersonics/debug lists which priority column
        # (request / total / enacted / actual) is actually used for each FY so you
        # can spot years silently falling back to enacted or actual figures.
        if len(available) == 0:
            coalesce_expr = "NULL"
        elif len(available) == 1:
            coalesce_expr = available[0]
        else:
            coalesce_expr = f"COALESCE({', '.join(available)})"
        year_parts.append(
            f"SUM(CASE WHEN fiscal_year = 'FY {yr}' THEN {coalesce_expr} END) AS fy{yr}"
        )
        # Source file reference for this year's cell — MAX collapses the single matching row.
        year_parts.append(
            f"MAX(CASE WHEN fiscal_year = 'FY {yr}' THEN source_file END) AS fy{yr}_ref"
        )

    year_cols_sql = ",\n    ".join(year_parts)

    where_parts = [pe_where, "fiscal_year >= 'FY 2015'"]
    all_params: list[Any] = list(pe_params)

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


def _enrich_rows(rows: list[sqlite3.Row], year_range: list[int]) -> list[dict]:
    """Convert rows to dicts, add color_of_money, and extract refs into a nested dict.

    Each row gets a ``refs`` key:
      { "fy2026": "fy2026_navy_rdtest.xlsx", "fy2025": "fy2025_navy_rdtest.xlsx", ... }
    Only years with non-null source data are included in ``refs``.
    The raw fy{N}_ref columns are removed from the top-level dict to keep it clean.
    """
    result: list[dict] = []
    for r in rows:
        d = dict(r)
        d["color_of_money"] = _color_of_money(d.get("appropriation_title"))
        refs: dict[str, str] = {}
        for yr in year_range:
            key = f"fy{yr}_ref"
            val = d.pop(key, None)
            if val:
                refs[f"fy{yr}"] = val
        d["refs"] = refs
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

    Matching is PE-level: if any sub-element or pe_description for a PE mentions a
    hypersonics keyword, ALL sub-elements for that PE are returned.

    Each row includes a ``refs`` dict mapping fy{N} → source filename for citation
    tooltips in the UI.
    """
    all_cols = set(get_amount_columns(conn))
    extra_where, extra_params = _apply_filters(service, exhibit, fy_from, fy_to)
    sql, params = _build_pivot_query(conn, all_cols, extra_where, extra_params)
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
        "rows": _enrich_rows(rows, year_range),
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

    Includes fy{N}_source columns alongside each fy{N} amount so recipients
    can trace every figure back to its source document.
    """
    all_cols = set(get_amount_columns(conn))
    extra_where, extra_params = _apply_filters(service, exhibit, fy_from, fy_to)
    sql, params = _build_pivot_query(conn, all_cols, extra_where, extra_params)
    rows = conn.execute(sql, params).fetchall()

    year_range = list(range(_FY_START, _FY_END + 1))
    items = _enrich_rows(rows, year_range)

    # Interleave amount and source columns: FY2015 ($K), FY2015 Source, FY2016 ($K), ...
    fy_headers: list[str] = []
    for yr in year_range:
        fy_headers.extend([f"FY{yr} ($K)", f"FY{yr} Source"])

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "PE Number", "Service/Org", "Exhibit Type", "Line Item Title",
        "Budget Activity", "Appropriation", "Color of Money",
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
            r["appropriation_title"], r["color_of_money"],
            *fy_cells,
        ])

    csv_bytes = buf.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="hypersonics_pe_lines.csv"'},
    )


# ── GET /api/v1/hypersonics/debug ─────────────────────────────────────────────

@router.get(
    "/debug",
    summary="Pre-flight data quality checks for the hypersonics view",
)
def debug_hypersonics(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Surface data-quality stats to validate the hypersonics view against real data.

    Checks:
    - Which amount_fy* columns exist and which priority column is used per year
    - pe_descriptions table status (exists, row count, distinct PE numbers)
    - source_file null rate in matching budget_lines rows
    - Color-of-money breakdown (flags any "Unknown" or verbatim approp_title rows)
    - Per-keyword PE hit counts (helps spot gaps in keyword coverage)
    - Active fiscal years and total matching sub-elements
    """
    result: dict = {}

    # ── 1. Amount column availability ─────────────────────────────────────────
    all_amount_cols = set(get_amount_columns(conn))
    year_col_map: dict[str, str] = {}
    for yr in range(_FY_START, _FY_END + 1):
        priority = [
            f"amount_fy{yr}_request",
            f"amount_fy{yr}_total",
            f"amount_fy{yr}_enacted",
            f"amount_fy{yr}_actual",
        ]
        available = [c for c in priority if c in all_amount_cols]
        year_col_map[f"fy{yr}"] = available[0].split(f"fy{yr}_")[1] if available else "missing"
    result["amount_columns"] = {
        "present": sorted(all_amount_cols),
        "per_year_priority_used": year_col_map,
        "years_with_no_data": [k for k, v in year_col_map.items() if v == "missing"],
    }

    # ── 2. pe_descriptions status ─────────────────────────────────────────────
    try:
        conn.execute("SELECT 1 FROM pe_descriptions LIMIT 0")
        row_count = conn.execute("SELECT COUNT(*) FROM pe_descriptions").fetchone()[0]
        pe_count = conn.execute(
            "SELECT COUNT(DISTINCT pe_number) FROM pe_descriptions"
        ).fetchone()[0]
        kw_hits = conn.execute(
            "SELECT COUNT(DISTINCT pe_number) FROM pe_descriptions WHERE "
            + " OR ".join("description_text LIKE ?" for _ in _DESC_KEYWORDS),
            [f"%{kw}%" for kw in _DESC_KEYWORDS],
        ).fetchone()[0]
        result["pe_descriptions"] = {
            "table_exists": True,
            "row_count": row_count,
            "distinct_pe_numbers": pe_count,
            "pe_numbers_matching_keywords": kw_hits,
            "populated": row_count > 0,
        }
    except sqlite3.OperationalError:
        result["pe_descriptions"] = {"table_exists": False, "populated": False}

    # ── 3. source_file null rate on matching rows ─────────────────────────────
    pe_where, pe_params = _build_pe_match_where(conn)
    base_where = f"{pe_where} AND fiscal_year >= 'FY {_FY_START}'"
    total_rows = conn.execute(
        f"SELECT COUNT(*) FROM budget_lines WHERE {base_where}", pe_params
    ).fetchone()[0]
    null_source = conn.execute(
        f"SELECT COUNT(*) FROM budget_lines WHERE {base_where} AND source_file IS NULL",
        pe_params,
    ).fetchone()[0]
    result["source_file"] = {
        "total_matching_rows": total_rows,
        "null_count": null_source,
        "null_pct": round(null_source / total_rows * 100, 1) if total_rows else 0,
        "ok": null_source == 0,
    }

    # ── 4. Color-of-money breakdown ───────────────────────────────────────────
    com_rows = conn.execute(
        f"SELECT appropriation_title, COUNT(DISTINCT pe_number || exhibit_type || line_item_title) "
        f"FROM budget_lines WHERE {base_where} "
        f"GROUP BY appropriation_title ORDER BY 2 DESC",
        pe_params,
    ).fetchall()
    com_breakdown: dict[str, int] = {}
    unrecognized: list[str] = []
    for approp_title, cnt in com_rows:
        label = _color_of_money(approp_title)
        com_breakdown[label] = com_breakdown.get(label, 0) + cnt
        if label not in ("RDT&E", "Procurement", "O&M", "MILCON", "Military Personnel", "Unknown"):
            unrecognized.append(approp_title or "")
    result["color_of_money"] = {
        "breakdown": com_breakdown,
        "unrecognized_approp_titles": sorted(set(unrecognized)),
        "ok": len(unrecognized) == 0 and com_breakdown.get("Unknown", 0) == 0,
    }

    # ── 5. Per-keyword PE hit counts ──────────────────────────────────────────
    keyword_hits: dict[str, int] = {}
    for kw in _HYPERSONICS_KEYWORDS:
        clauses = " OR ".join(f"{col} LIKE ?" for col in _SEARCH_COLS)
        params = [f"%{kw}%"] * len(_SEARCH_COLS)
        n = conn.execute(
            f"SELECT COUNT(DISTINCT pe_number) FROM budget_lines WHERE {clauses}", params
        ).fetchone()[0]
        keyword_hits[kw] = n
    result["keyword_pe_hits"] = keyword_hits
    result["keywords_with_zero_hits"] = [kw for kw, n in keyword_hits.items() if n == 0]

    # ── 6. Summary ────────────────────────────────────────────────────────────
    pivot_sql, pivot_params = _build_pivot_query(conn, all_amount_cols)
    pivot_rows = conn.execute(pivot_sql, pivot_params).fetchall()
    year_range = list(range(_FY_START, _FY_END + 1))
    active_years = [yr for yr in year_range if any(r[f"fy{yr}"] is not None for r in pivot_rows)]
    result["summary"] = {
        "total_sub_elements": len(pivot_rows),
        "distinct_pe_numbers": len({r["pe_number"] for r in pivot_rows}),
        "active_fiscal_years": active_years,
        "overall_ok": (
            result["source_file"]["ok"]
            and result["color_of_money"]["ok"]
            and len(result["keywords_with_zero_hits"]) == 0
            and result.get("pe_descriptions", {}).get("populated", False)
        ),
    }

    return result
