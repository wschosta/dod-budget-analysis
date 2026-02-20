"""Dashboard summary endpoint for the overview page."""

import sqlite3

from fastapi import APIRouter, Depends

from api.database import get_db
from utils.cache import TTLCache
from utils.database import get_amount_columns

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_summary_cache: TTLCache = TTLCache(maxsize=4, ttl_seconds=300)


def _detect_fy_columns(conn: sqlite3.Connection) -> tuple[str, str]:
    """Detect the best FY request and enacted column names dynamically."""
    cols = get_amount_columns(conn)
    fy26_col = next((c for c in cols if "fy2026_request" in c), "amount_fy2026_request")
    fy25_col = next((c for c in cols if "fy2025_enacted" in c), "amount_fy2025_enacted")
    return fy26_col, fy25_col


@router.get("/summary", summary="Dashboard summary statistics")
def dashboard_summary(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Return aggregated statistics for the dashboard overview page.

    Includes:
    - Grand totals (line count, FY26 request, FY25 enacted)
    - Top 6 services by FY26 request amount
    - Top 10 programs with PE numbers
    - Year-over-year by fiscal year
    - Top 6 appropriation categories
    """
    cache_key = ("dashboard_summary", id(conn))
    cached = _summary_cache.get(cache_key)
    if cached is not None:
        return cached

    fy26_col, fy25_col = _detect_fy_columns(conn)

    # Grand totals
    totals_row = conn.execute(
        f"SELECT COUNT(*) as total_lines, "
        f"SUM({fy26_col}) as total_fy26_request, "
        f"SUM({fy25_col}) as total_fy25_enacted "
        f"FROM budget_lines"
    ).fetchone()
    totals = dict(totals_row)

    # By service (top 6)
    by_service_rows = conn.execute(
        f"SELECT organization_name as service, "
        f"SUM({fy26_col}) as total, "
        f"SUM({fy25_col}) as prev_total, "
        f"COUNT(*) as line_count "
        f"FROM budget_lines WHERE organization_name IS NOT NULL "
        f"GROUP BY organization_name "
        f"ORDER BY SUM(COALESCE({fy26_col}, 0)) DESC LIMIT 6"
    ).fetchall()

    # Top 10 programs
    top_programs_rows = conn.execute(
        f"SELECT id, line_item_title, organization_name, pe_number, "
        f"{fy26_col} as fy26_request, {fy25_col} as fy25_enacted "
        f"FROM budget_lines "
        f"WHERE {fy26_col} IS NOT NULL "
        f"ORDER BY {fy26_col} DESC LIMIT 10"
    ).fetchall()

    # YoY by fiscal year
    by_fy_rows = conn.execute(
        f"SELECT fiscal_year, "
        f"SUM({fy26_col}) as fy26_total, "
        f"SUM({fy25_col}) as fy25_total "
        f"FROM budget_lines WHERE fiscal_year IS NOT NULL "
        f"GROUP BY fiscal_year ORDER BY fiscal_year"
    ).fetchall()

    # By appropriation (top 6)
    by_approp_rows = conn.execute(
        f"SELECT appropriation_code, appropriation_title, "
        f"SUM({fy26_col}) as total "
        f"FROM budget_lines WHERE appropriation_code IS NOT NULL "
        f"GROUP BY appropriation_code "
        f"ORDER BY SUM(COALESCE({fy26_col}, 0)) DESC LIMIT 6"
    ).fetchall()

    # Enrichment coverage — how much of the database is enriched
    enrichment = {}
    try:
        distinct_pes = conn.execute(
            "SELECT COUNT(DISTINCT pe_number) AS c FROM budget_lines "
            "WHERE pe_number IS NOT NULL"
        ).fetchone()["c"]
        pe_index_count = conn.execute(
            "SELECT COUNT(*) AS c FROM pe_index"
        ).fetchone()["c"]
        pe_with_tags = conn.execute(
            "SELECT COUNT(DISTINCT pe_number) AS c FROM pe_tags"
        ).fetchone()["c"]
        pe_with_desc = conn.execute(
            "SELECT COUNT(DISTINCT pe_number) AS c FROM pe_descriptions"
        ).fetchone()["c"]
        total_tags = conn.execute(
            "SELECT COUNT(*) AS c FROM pe_tags"
        ).fetchone()["c"]
        enrichment = {
            "total_pes": distinct_pes,
            "pe_index_coverage": pe_index_count,
            "pe_with_tags": pe_with_tags,
            "pe_with_descriptions": pe_with_desc,
            "total_tags": total_tags,
            "pct_indexed": round(pe_index_count / distinct_pes * 100, 1)
            if distinct_pes > 0 else 0,
            "pct_tagged": round(pe_with_tags / distinct_pes * 100, 1)
            if distinct_pes > 0 else 0,
            "pct_described": round(pe_with_desc / distinct_pes * 100, 1)
            if distinct_pes > 0 else 0,
        }
    except Exception:
        pass  # Enrichment tables may not exist yet

    result = {
        "totals": totals,
        "by_service": [dict(r) for r in by_service_rows],
        "top_programs": [dict(r) for r in top_programs_rows],
        "by_fiscal_year": [dict(r) for r in by_fy_rows],
        "by_appropriation": [dict(r) for r in by_approp_rows],
        "enrichment": enrichment,
    }

    _summary_cache.set(cache_key, result)
    return result
