"""
Frontend HTML routes (Step 3.A0-a).

Serves the Jinja2 templates for the search UI, results partial,
detail partial, and charts page.

Routes:
    GET /                       → index.html (search + filter sidebar)
    GET /charts                 → charts.html (Chart.js visualisations)
    GET /partials/results       → partials/results.html (HTMX swap target)
    GET /partials/detail/{id}   → partials/detail.html (HTMX swap target)

OPT-FE-001: _build_where uses shared utils/query.py builder (DRY).
OPT-FE-002: Reference data queries cached with TTL to reduce DB hits.

TODO 3.A3-c / FE-001 [Group: LION] [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Add amount range (min/max) filter support.
    Steps:
      1. In _parse_filters(), read min_amount and max_amount from query params
      2. In _query_results(), add WHERE clauses:
         amount_fy2026_request >= ? AND amount_fy2026_request <= ?
      3. Pass min_amount/max_amount to template context for form pre-fill
    Acceptance: Amount range filter narrows results correctly.

TODO 3.A3-d / FE-002 [Group: LION] [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Add appropriation filter support.
    Steps:
      1. Add _get_appropriations(conn) helper returning DISTINCT
         appropriation_code, appropriation_title from budget_lines
      2. In _parse_filters(), read appropriation_code from query params
      3. In _query_results(), add WHERE appropriation_code IN (?) clause
      4. Pass appropriation list to index template context
    Acceptance: Appropriation dropdown filters results correctly.

TODO 3.A6-b / FE-006 [Group: LION] [Complexity: MEDIUM] [Tokens: ~3000] [User: NO]
    Add related items query to detail_partial().
    Steps:
      1. After fetching the main item, query for related rows:
         SELECT id, fiscal_year, amount_fy2026_request FROM budget_lines
         WHERE pe_number = ? AND id != ? ORDER BY fiscal_year
      2. Fall back to matching on organization_name + line_item_title
      3. Pass related_items list to detail.html template
    Acceptance: Detail panel shows same program across fiscal years.
"""

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from api.database import get_db
from api.routes.budget_lines import _ALLOWED_SORT
from utils.cache import TTLCache
from utils.query import build_where_clause
from utils import sanitize_fts5_query

router = APIRouter(tags=["frontend"])

# Templates instance is set by create_app() after mounting.
_templates: Jinja2Templates | None = None

# OPT-FE-002: TTL caches for reference data (5-minute TTL)
_services_cache: TTLCache = TTLCache(maxsize=4, ttl_seconds=300)
_exhibit_types_cache: TTLCache = TTLCache(maxsize=4, ttl_seconds=300)
_fiscal_years_cache: TTLCache = TTLCache(maxsize=4, ttl_seconds=300)


def set_templates(t: Jinja2Templates) -> None:
    global _templates
    _templates = t


def _tmpl() -> Jinja2Templates:
    if _templates is None:
        raise RuntimeError("Templates not initialised — call set_templates() first")
    return _templates


# ── Reference helpers (OPT-FE-002: cached) ────────────────────────────────────

def _get_services(conn: sqlite3.Connection) -> list[dict]:
    cache_key = ("services", id(conn))
    cached = _services_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        rows = conn.execute(
            "SELECT code, full_name FROM services_agencies ORDER BY code"
        ).fetchall()
        result = [dict(r) for r in rows]
    except Exception:
        rows = conn.execute(
            "SELECT DISTINCT organization_name AS code FROM budget_lines "
            "WHERE organization_name IS NOT NULL ORDER BY organization_name"
        ).fetchall()
        result = [{"code": r["code"], "full_name": r["code"]} for r in rows]
    _services_cache.set(cache_key, result)
    return result


def _get_exhibit_types(conn: sqlite3.Connection) -> list[dict]:
    cache_key = ("exhibit_types", id(conn))
    cached = _exhibit_types_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        rows = conn.execute(
            "SELECT code, display_name FROM exhibit_types ORDER BY code"
        ).fetchall()
        result = [dict(r) for r in rows]
    except Exception:
        rows = conn.execute(
            "SELECT DISTINCT exhibit_type AS code FROM budget_lines "
            "WHERE exhibit_type IS NOT NULL ORDER BY exhibit_type"
        ).fetchall()
        result = [{"code": r["code"], "display_name": r["code"]} for r in rows]
    _exhibit_types_cache.set(cache_key, result)
    return result


def _get_fiscal_years(conn: sqlite3.Connection) -> list[dict]:
    cache_key = ("fiscal_years", id(conn))
    cached = _fiscal_years_cache.get(cache_key)
    if cached is not None:
        return cached
    rows = conn.execute(
        "SELECT fiscal_year, COUNT(*) AS row_count FROM budget_lines "
        "WHERE fiscal_year IS NOT NULL "
        "GROUP BY fiscal_year ORDER BY fiscal_year"
    ).fetchall()
    result = [{"fiscal_year": r["fiscal_year"], "row_count": r["row_count"]} for r in rows]
    _fiscal_years_cache.set(cache_key, result)
    return result


def _parse_filters(request: Request) -> dict[str, Any]:
    """Extract filter params from query string into a dict."""
    params = request.query_params
    return {
        "q":           params.get("q", ""),
        "fiscal_year": params.getlist("fiscal_year"),
        "service":     params.getlist("service"),
        "exhibit_type": params.getlist("exhibit_type"),
        "pe_number":   params.getlist("pe_number"),
        "sort_by":     params.get("sort_by", "id"),
        "sort_dir":    params.get("sort_dir", "asc"),
        "page":        max(1, int(params.get("page", 1))),
    }


def _query_results(
    filters: dict[str, Any],
    conn: sqlite3.Connection,
    page_size: int = 25,
) -> dict[str, Any]:
    """Run the filtered budget_lines query and return template context vars."""
    sort_by  = filters["sort_by"] if filters["sort_by"] in _ALLOWED_SORT else "id"
    sort_dir = "DESC" if filters["sort_dir"] == "desc" else "ASC"
    page     = filters["page"]
    offset   = (page - 1) * page_size

    # OPT-FE-001: Use shared WHERE builder from utils/query.py
    where, params = build_where_clause(
        fiscal_year=filters["fiscal_year"] or None,
        service=filters["service"] or None,
        exhibit_type=filters["exhibit_type"] or None,
        pe_number=filters["pe_number"] or None,
        appropriation_code=None,
    )

    # Apply keyword filter against FTS if provided
    q = filters["q"].strip()
    fts_ids: list[int] | None = None
    if q:
        try:
            safe_q = sanitize_fts5_query(q)
        except Exception:
            safe_q = q.replace('"', '""')
        try:
            fts_rows = conn.execute(
                "SELECT rowid FROM budget_lines_fts WHERE budget_lines_fts MATCH ?",
                (safe_q,),
            ).fetchall()
            fts_ids = [r[0] for r in fts_rows]
        except Exception:
            fts_ids = []

    if fts_ids is not None:
        if not fts_ids:
            return {
                "items": [], "total": 0, "page": page,
                "total_pages": 0, "sort_by": sort_by.lower(),
                "sort_dir": filters["sort_dir"],
            }
        id_placeholders = ",".join("?" * len(fts_ids))
        id_condition = f"id IN ({id_placeholders})"
        if where:
            where = where + f" AND {id_condition}"
            params = params + fts_ids
        else:
            where = f"WHERE {id_condition}"
            params = fts_ids

    total = conn.execute(f"SELECT COUNT(*) FROM budget_lines {where}", params).fetchone()[0]
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, total_pages)

    rows = conn.execute(
        f"SELECT id, exhibit_type, fiscal_year, account, account_title, "
        f"organization_name, budget_activity_title, line_item_title, pe_number, "
        f"amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request "
        f"FROM budget_lines {where} "
        f"ORDER BY {sort_by} {sort_dir} LIMIT ? OFFSET ?",
        params + [page_size, offset],
    ).fetchall()

    return {
        "items":       [dict(r) for r in rows],
        "total":       total,
        "page":        page,
        "total_pages": total_pages,
        "sort_by":     sort_by,
        "sort_dir":    filters["sort_dir"],
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> HTMLResponse:
    """Main search page."""
    filters       = _parse_filters(request)
    results       = _query_results(filters, conn)
    fiscal_years  = _get_fiscal_years(conn)
    services      = _get_services(conn)
    exhibit_types = _get_exhibit_types(conn)

    return _tmpl().TemplateResponse(
        "index.html",
        {
            "request":       request,
            "filters":       filters,
            "fiscal_years":  fiscal_years,
            "services":      services,
            "exhibit_types": exhibit_types,
            **results,
        },
    )


@router.get("/charts", response_class=HTMLResponse, include_in_schema=False)
def charts(request: Request) -> HTMLResponse:
    """Chart.js visualisations page."""
    return _tmpl().TemplateResponse("charts.html", {"request": request})


@router.get("/partials/results", response_class=HTMLResponse, include_in_schema=False)
def results_partial(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """HTMX partial: filtered/paginated results table."""
    filters = _parse_filters(request)
    results = _query_results(filters, conn)

    return _tmpl().TemplateResponse(
        "partials/results.html",
        {"request": request, **results},
    )


@router.get("/partials/detail/{item_id}", response_class=HTMLResponse, include_in_schema=False)
def detail_partial(
    item_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """HTMX partial: full detail panel for a single budget line."""
    row = conn.execute(
        "SELECT * FROM budget_lines WHERE id = ?", (item_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Budget line {item_id} not found")

    return _tmpl().TemplateResponse(
        "partials/detail.html",
        {"request": request, "item": dict(row)},
    )
