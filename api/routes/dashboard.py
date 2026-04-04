"""Dashboard summary endpoint for the overview page."""

import json
import sqlite3

from fastapi import APIRouter, Depends, Query

from api.database import get_db
from utils.cache import TTLCache
from utils.database import BUDGET_TYPE_CASE_EXPR
from utils.query import build_where_clause, detect_fy_columns

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_summary_cache: TTLCache = TTLCache(maxsize=32, ttl_seconds=900)


@router.post("/cache-clear", summary="Clear dashboard cache (dev)")
def clear_dashboard_cache() -> dict:
    """Clear the dashboard summary cache. Useful during development."""
    _summary_cache.clear()
    return {"status": "ok", "message": "Dashboard cache cleared"}



@router.get("/summary", summary="Dashboard summary statistics")
def dashboard_summary(
    fiscal_year: str | None = Query(None, description="Filter by fiscal year (e.g. '2026')"),
    service: str | None = Query(None, description="Filter by service/organization name"),
    exhibit_type: str | None = Query(None, description="Filter by exhibit type (e.g. 'R-2')"),
    budget_type: str | None = Query(None, description="Filter by budget type (color of money)"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return aggregated statistics for the dashboard overview page.

    Includes:
    - Grand totals (line count, FY26 request, FY25 enacted)
    - Top 6 services by FY26 request amount
    - Top 10 programs with PE numbers
    - Year-over-year by fiscal year
    - Budget type distribution (colors of money)
    - Budget type distribution (RDT&E, Procurement, O&M, etc.)
    - Enrichment coverage metrics

    Pass fiscal_year, service, exhibit_type, and/or budget_type
    to restrict all aggregations.
    """
    cache_key = ("dashboard_summary", fiscal_year, service,
                 exhibit_type, budget_type)
    cached = _summary_cache.get(cache_key)
    if cached is not None:
        return cached

    fy26_col, fy25_col = detect_fy_columns(conn)

    # FIX-006: Exclude summary exhibits (p1, r1, o1, m1, c1, rf1, p1r) to avoid
    # double-counting with detail exhibits. Also exclude rows with invalid
    # fiscal_year values (non-numeric like "Details").
    _fy_validity = (
        "(fiscal_year IS NULL OR fiscal_year GLOB '[0-9][0-9][0-9][0-9]' "
        " OR fiscal_year GLOB 'FY [0-9][0-9][0-9][0-9]' "
        " OR fiscal_year GLOB 'FY[0-9][0-9][0-9][0-9]')"
    )

    fy_filter, filter_params = build_where_clause(
        fiscal_year=[fiscal_year] if fiscal_year else None,
        service=[service] if service else None,
        exhibit_type=[exhibit_type] if exhibit_type else None,
        budget_type=[budget_type] if budget_type else None,
        exclude_summary=True,
        extra_conditions=[_fy_validity],
    )

    # Batch the main budget_lines aggregations into a single CTE query.
    # This scans the table once instead of 4 separate passes.
    batch_result = conn.execute(f"""
        WITH base AS (
            SELECT organization_name, fiscal_year,
                   budget_type,
                   id, line_item_title, pe_number,
                   {fy26_col} AS fy26, {fy25_col} AS fy25
            FROM budget_lines
            {fy_filter}
        ),
        totals AS (
            SELECT COUNT(*) AS total_lines,
                   SUM(fy26) AS total_fy26_request,
                   SUM(fy25) AS total_fy25_enacted,
                   COUNT(DISTINCT pe_number) AS distinct_pes,
                   COUNT(DISTINCT fiscal_year) AS distinct_fys,
                   COUNT(DISTINCT organization_name) AS distinct_services
            FROM base
        ),
        by_service AS (
            SELECT organization_name AS service,
                   SUM(fy26) AS total,
                   SUM(fy25) AS prev_total,
                   COUNT(*) AS line_count
            FROM base WHERE organization_name IS NOT NULL
            GROUP BY organization_name
            ORDER BY SUM(COALESCE(fy26, 0)) DESC LIMIT 6
        ),
        by_fy AS (
            SELECT fiscal_year,
                   SUM(fy26) AS fy26_total,
                   SUM(fy25) AS fy25_total
            FROM base WHERE fiscal_year IS NOT NULL
            GROUP BY fiscal_year ORDER BY fiscal_year
        )
        SELECT
            'totals' AS section, json_object(
                'total_lines', t.total_lines,
                'total_fy26_request', t.total_fy26_request,
                'total_fy25_enacted', t.total_fy25_enacted,
                'distinct_pes', t.distinct_pes,
                'distinct_fys', t.distinct_fys,
                'distinct_services', t.distinct_services
            ) AS data
        FROM totals t
        UNION ALL
        SELECT 'by_service', json_group_array(
            json_object('service', s.service, 'total', s.total,
                        'prev_total', s.prev_total, 'line_count', s.line_count)
        ) FROM by_service s
        UNION ALL
        SELECT 'by_fiscal_year', json_group_array(
            json_object('fiscal_year', f.fiscal_year,
                        'fy26_total', f.fy26_total, 'fy25_total', f.fy25_total)
        ) FROM by_fy f
    """, filter_params).fetchall()

    # Parse the batch result
    sections = {row[0]: json.loads(row[1]) for row in batch_result}
    totals = sections.get("totals", {})
    by_service = sections.get("by_service", [])
    by_fy = sections.get("by_fiscal_year", [])

    # Budget type distribution — uses shared CASE expression to derive
    # budget_type from appropriation_code for detail rows where budget_type
    # is NULL. The filter_params list is reused from the base filter above.
    _BT = BUDGET_TYPE_CASE_EXPR
    bt_conditions = [f"{_BT} != 'Unknown'"]
    bt_params: list = list(filter_params)  # re-use base filter params
    if budget_type:
        bt_conditions.append(f"{_BT} = ?")
        bt_params.append(budget_type)
    bt_extra = " AND ".join(bt_conditions)
    by_btype_rows = conn.execute(f"""
        SELECT {_BT} AS budget_type,
               SUM({fy26_col}) AS total,
               SUM({fy25_col}) AS prev_total,
               COUNT(*) AS line_count
        FROM budget_lines
        {fy_filter}
        {"AND " + bt_extra if bt_extra else ""}
        GROUP BY {_BT}
        ORDER BY SUM(COALESCE({fy26_col}, 0)) DESC
    """, bt_params).fetchall()
    by_btype_cte = [dict(r) for r in by_btype_rows]

    # Top 10 programs — needs its own query since it returns individual rows
    tp_where, tp_params = build_where_clause(
        fiscal_year=[fiscal_year] if fiscal_year else None,
        service=[service] if service else None,
        exhibit_type=[exhibit_type] if exhibit_type else None,
        budget_type=[budget_type] if budget_type else None,
        exclude_summary=True,
        extra_conditions=[f"{fy26_col} IS NOT NULL", _fy_validity],
    )
    top_programs_rows = conn.execute(
        f"SELECT id, line_item_title, organization_name, pe_number, "
        f"{fy26_col} as fy26_request, {fy25_col} as fy25_enacted "
        f"FROM budget_lines "
        f"{tp_where} "
        f"ORDER BY {fy26_col} DESC LIMIT 10",
        tp_params,
    ).fetchall()

    # Enrichment coverage — how much of the database is enriched
    enrichment = {}
    try:
        enrich_row = conn.execute("""
            SELECT
                (SELECT COUNT(DISTINCT pe_number) FROM budget_lines
                 WHERE pe_number IS NOT NULL) AS distinct_pes,
                (SELECT COUNT(*) FROM pe_index) AS pe_index_count,
                (SELECT COUNT(DISTINCT pe_number) FROM pe_tags) AS pe_with_tags,
                (SELECT COUNT(DISTINCT pe_number) FROM pe_descriptions) AS pe_with_desc,
                (SELECT COUNT(*) FROM pe_tags) AS total_tags
        """).fetchone()
        distinct_pes = enrich_row[0]
        enrichment = {
            "total_pes": distinct_pes,
            "pe_index_coverage": enrich_row[1],
            "pe_with_tags": enrich_row[2],
            "pe_with_descriptions": enrich_row[3],
            "total_tags": enrich_row[4],
            "pct_indexed": round(enrich_row[1] / distinct_pes * 100, 1)
            if distinct_pes > 0 else 0,
            "pct_tagged": round(enrich_row[2] / distinct_pes * 100, 1)
            if distinct_pes > 0 else 0,
            "pct_described": round(enrich_row[3] / distinct_pes * 100, 1)
            if distinct_pes > 0 else 0,
        }
    except sqlite3.OperationalError:
        pass  # Enrichment tables may not exist yet

    # Exhibit type distribution
    by_exhibit_type: list[dict] = []
    try:
        et_rows = conn.execute(f"""
            SELECT COALESCE(exhibit_type, 'Unknown') AS exhibit_type,
                   SUM({fy26_col}) AS total,
                   COUNT(*) AS line_count
            FROM budget_lines
            {fy_filter}
            GROUP BY COALESCE(exhibit_type, 'Unknown')
            ORDER BY SUM(COALESCE({fy26_col}, 0)) DESC
        """, filter_params).fetchall()
        by_exhibit_type = [dict(r) for r in et_rows]
    except sqlite3.OperationalError:
        pass  # exhibit_type column may not exist

    # Source file stats — Excel vs PDF file counts and totals
    source_stats: dict = {}
    try:
        sf_row = conn.execute("""
            SELECT
                COUNT(DISTINCT CASE WHEN file_type = 'xlsx' THEN file_path END) AS excel_files,
                COUNT(DISTINCT CASE WHEN file_type = 'pdf' THEN file_path END) AS pdf_files,
                SUM(CASE WHEN file_type = 'xlsx' THEN row_count ELSE 0 END) AS excel_rows,
                SUM(CASE WHEN file_type = 'pdf' THEN row_count ELSE 0 END) AS pdf_pages,
                COUNT(DISTINCT file_path) AS total_files
            FROM ingested_files
            WHERE status = 'ok'
        """).fetchone()
        if sf_row:
            source_stats = {
                "excel_files": sf_row["excel_files"],
                "pdf_files": sf_row["pdf_files"],
                "excel_rows": sf_row["excel_rows"] or 0,
                "pdf_pages": sf_row["pdf_pages"] or 0,
                "total_files": sf_row["total_files"],
            }
    except sqlite3.OperationalError:
        pass  # ingested_files may not exist

    # Data freshness — when was the database last built/updated?
    freshness: dict = {}
    try:
        bp = conn.execute("""
            SELECT checkpoint_time, notes, status
            FROM build_progress
            ORDER BY checkpoint_time DESC LIMIT 1
        """).fetchone()
        if bp:
            freshness["last_build"] = bp["checkpoint_time"]
            freshness["last_build_status"] = bp["status"]
            if bp["notes"]:
                freshness["last_build_notes"] = bp["notes"]
        ds = conn.execute("""
            SELECT MAX(last_updated) AS most_recent
            FROM data_sources WHERE last_updated IS NOT NULL
        """).fetchone()
        if ds and ds["most_recent"]:
            freshness["data_sources_updated"] = ds["most_recent"]
    except sqlite3.OperationalError:
        pass  # Tables may not exist

    result = {
        "totals": totals,
        "by_service": by_service,
        "top_programs": [dict(r) for r in top_programs_rows],
        "by_fiscal_year": by_fy,
        "by_budget_type": by_btype_cte,
        "by_exhibit_type": by_exhibit_type,
        "source_stats": source_stats,
        "enrichment": enrichment,
        "freshness": freshness,
    }

    _summary_cache.set(cache_key, result)
    return result
