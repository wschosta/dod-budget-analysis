"""Dashboard summary endpoint for the overview page."""

import json
import sqlite3

from fastapi import APIRouter, Depends, Query

from api.database import get_db
from utils.cache import TTLCache
from utils.database import get_amount_columns

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_summary_cache: TTLCache = TTLCache(maxsize=32, ttl_seconds=300)


def _detect_fy_columns(conn: sqlite3.Connection) -> tuple[str, str]:
    """Detect the best FY request and enacted column names dynamically."""
    cols = get_amount_columns(conn)
    fy26_col = next((c for c in cols if "fy2026_request" in c), "amount_fy2026_request")
    fy25_col = next((c for c in cols if "fy2025_enacted" in c), "amount_fy2025_enacted")
    return fy26_col, fy25_col


@router.get("/summary", summary="Dashboard summary statistics")
def dashboard_summary(
    fiscal_year: str | None = Query(None, description="Filter by fiscal year (e.g. '2026')"),
    service: str | None = Query(None, description="Filter by service/organization name"),
    exhibit_type: str | None = Query(None, description="Filter by exhibit type (e.g. 'R-2')"),
    appropriation_code: str | None = Query(None, description="Filter by appropriation code"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return aggregated statistics for the dashboard overview page.

    Includes:
    - Grand totals (line count, FY26 request, FY25 enacted)
    - Top 6 services by FY26 request amount
    - Top 10 programs with PE numbers
    - Year-over-year by fiscal year
    - Top 6 appropriation categories
    - Budget type distribution (RDT&E, Procurement, O&M, etc.)
    - Enrichment coverage metrics

    Pass fiscal_year, service, exhibit_type, and/or appropriation_code
    to restrict all aggregations.
    """
    cache_key = ("dashboard_summary", fiscal_year, service,
                 exhibit_type, appropriation_code)
    cached = _summary_cache.get(cache_key)
    if cached is not None:
        return cached

    fy26_col, fy25_col = _detect_fy_columns(conn)

    conditions: list[str] = []
    filter_params: list = []
    if fiscal_year:
        conditions.append("fiscal_year = ?")
        filter_params.append(fiscal_year)
    if service:
        conditions.append("organization_name = ?")
        filter_params.append(service)
    if exhibit_type:
        conditions.append("exhibit_type = ?")
        filter_params.append(exhibit_type)
    if appropriation_code:
        conditions.append("appropriation_code = ?")
        filter_params.append(appropriation_code)
    fy_filter = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # Batch the main budget_lines aggregations into a single CTE query.
    # This scans the table once instead of 4 separate passes.
    batch_result = conn.execute(f"""
        WITH base AS (
            SELECT organization_name, fiscal_year,
                   appropriation_code, appropriation_title,
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
        ),
        by_approp AS (
            SELECT appropriation_code, appropriation_title,
                   SUM(fy26) AS total
            FROM base WHERE appropriation_code IS NOT NULL
            GROUP BY appropriation_code
            ORDER BY SUM(COALESCE(fy26, 0)) DESC LIMIT 6
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
        UNION ALL
        SELECT 'by_appropriation', json_group_array(
            json_object('appropriation_code', a.appropriation_code,
                        'appropriation_title', a.appropriation_title,
                        'total', a.total)
        ) FROM by_approp a
    """, filter_params).fetchall()

    # Parse the batch result
    sections = {row[0]: json.loads(row[1]) for row in batch_result}
    totals = sections.get("totals", {})
    by_service = sections.get("by_service", [])
    by_fy = sections.get("by_fiscal_year", [])
    by_approp = sections.get("by_appropriation", [])

    # Top 10 programs — needs its own query since it returns individual rows
    tp_conditions = [f"{fy26_col} IS NOT NULL"]
    if fiscal_year:
        tp_conditions.append("fiscal_year = ?")
    if service:
        tp_conditions.append("organization_name = ?")
    if exhibit_type:
        tp_conditions.append("exhibit_type = ?")
    if appropriation_code:
        tp_conditions.append("appropriation_code = ?")
    tp_where = "WHERE " + " AND ".join(tp_conditions)
    top_programs_rows = conn.execute(
        f"SELECT id, line_item_title, organization_name, pe_number, "
        f"{fy26_col} as fy26_request, {fy25_col} as fy25_enacted "
        f"FROM budget_lines "
        f"{tp_where} "
        f"ORDER BY {fy26_col} DESC LIMIT 10",
        filter_params,
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
    except Exception:
        pass  # Enrichment tables may not exist yet

    # Budget type distribution — separate query since budget_type
    # isn't in the base CTE and may not exist in older schemas.
    by_budget_type: list[dict] = []
    try:
        bt_rows = conn.execute(f"""
            SELECT COALESCE(budget_type, 'Unknown') AS budget_type,
                   SUM({fy26_col}) AS total,
                   SUM({fy25_col}) AS prev_total,
                   COUNT(*) AS line_count
            FROM budget_lines
            {fy_filter}
            GROUP BY COALESCE(budget_type, 'Unknown')
            ORDER BY SUM(COALESCE({fy26_col}, 0)) DESC
        """, filter_params).fetchall()
        by_budget_type = [dict(r) for r in bt_rows]
    except Exception:
        pass  # budget_type column may not exist

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
    except Exception:
        pass

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
    except Exception:
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
    except Exception:
        pass  # Tables may not exist

    result = {
        "totals": totals,
        "by_service": by_service,
        "top_programs": [dict(r) for r in top_programs_rows],
        "by_fiscal_year": by_fy,
        "by_appropriation": by_approp,
        "by_budget_type": by_budget_type,
        "by_exhibit_type": by_exhibit_type,
        "source_stats": source_stats,
        "enrichment": enrichment,
        "freshness": freshness,
    }

    _summary_cache.set(cache_key, result)
    return result
