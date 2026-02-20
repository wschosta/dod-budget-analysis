"""
Frontend HTML routes (Step 3.A0-a).

Serves the Jinja2 templates for the search UI, results partial,
detail partial, and charts page.

Routes:
    GET /                       → index.html (search + filter sidebar)
    GET /charts                 → charts.html (Chart.js visualisations)
    GET /partials/results       → partials/results.html (HTMX swap target)
    GET /partials/detail/{id}   → partials/detail.html (HTMX swap target)
"""

# DONE [Group: LION] LION-001: Add error page templates (404, 500) with branded styling (~1,500 tokens)

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


# LION-001: Custom HTML error handlers for 404/500 pages
def register_error_handlers(app) -> None:
    """Register custom exception handlers that render branded error pages."""
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        tmpl = _tmpl()
        return tmpl.TemplateResponse(
            "errors/404.html", {"request": request}, status_code=404
        )

    @app.exception_handler(500)
    async def server_error_handler(request: Request, exc):
        tmpl = _tmpl()
        return tmpl.TemplateResponse(
            "errors/500.html", {"request": request}, status_code=500
        )

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
        _services_cache.set(cache_key, result)  # only cache stable reference table
    except Exception:
        rows = conn.execute(
            "SELECT DISTINCT organization_name AS code FROM budget_lines "
            "WHERE organization_name IS NOT NULL ORDER BY organization_name"
        ).fetchall()
        result = [{"code": r["code"], "full_name": r["code"]} for r in rows]
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
        _exhibit_types_cache.set(cache_key, result)  # only cache stable reference table
    except Exception:
        rows = conn.execute(
            "SELECT DISTINCT exhibit_type AS code FROM budget_lines "
            "WHERE exhibit_type IS NOT NULL ORDER BY exhibit_type"
        ).fetchall()
        result = [{"code": r["code"], "display_name": r["code"]} for r in rows]
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


def _get_appropriations(conn: sqlite3.Connection) -> list[dict]:
    """FE-002: Return distinct appropriation codes and titles."""
    rows = conn.execute(
        "SELECT DISTINCT appropriation_code AS code, appropriation_title AS title "
        "FROM budget_lines "
        "WHERE appropriation_code IS NOT NULL "
        "ORDER BY appropriation_code"
    ).fetchall()
    return [{"code": r["code"], "title": r["title"]} for r in rows]


def _parse_filters(request: Request) -> dict[str, Any]:
    """Extract filter params from query string into a dict."""
    params = request.query_params
    # FE-001: parse min/max amount
    min_amt = params.get("min_amount", "")
    max_amt = params.get("max_amount", "")
    return {
        "q":                 params.get("q", ""),
        "fiscal_year":       params.getlist("fiscal_year"),
        "service":           params.getlist("service"),
        "exhibit_type":      params.getlist("exhibit_type"),
        "pe_number":         params.getlist("pe_number"),
        "appropriation_code": params.getlist("appropriation_code"),
        "min_amount":        min_amt,
        "max_amount":        max_amt,
        "sort_by":           params.get("sort_by", "id"),
        "sort_dir":          params.get("sort_dir", "asc"),
        "page":              max(1, int(params.get("page", 1))),
        "page_size":         min(100, max(10, int(params.get("page_size", 25)))),
    }


def _query_results(
    filters: dict[str, Any],
    conn: sqlite3.Connection,
    page_size: int | None = None,
) -> dict[str, Any]:
    """Run the filtered budget_lines query and return template context vars."""
    sort_by   = filters["sort_by"] if filters["sort_by"] in _ALLOWED_SORT else "id"
    sort_dir  = "DESC" if filters["sort_dir"] == "desc" else "ASC"
    page      = filters["page"]
    page_size = page_size or filters.get("page_size", 25)
    offset    = (page - 1) * page_size

    # OPT-FE-001: Use shared WHERE builder from utils/query.py
    where, params = build_where_clause(
        fiscal_year=filters["fiscal_year"] or None,
        service=filters["service"] or None,
        exhibit_type=filters["exhibit_type"] or None,
        pe_number=filters["pe_number"] or None,
        appropriation_code=filters.get("appropriation_code") or None,
    )

    # FE-001: amount range filter
    min_amt = filters.get("min_amount", "")
    max_amt = filters.get("max_amount", "")
    if min_amt:
        try:
            val = float(min_amt)
            connector = "AND" if where else "WHERE"
            where = f"{where} {connector} amount_fy2026_request >= ?"
            params = list(params) + [val]
        except ValueError:
            pass
    if max_amt:
        try:
            val = float(max_amt)
            connector = "AND" if where else "WHERE"
            where = f"{where} {connector} amount_fy2026_request <= ?"
            params = list(params) + [val]
        except ValueError:
            pass

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
        "page_size":   page_size,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> HTMLResponse:
    """Main search page."""
    filters        = _parse_filters(request)
    results        = _query_results(filters, conn)
    fiscal_years   = _get_fiscal_years(conn)
    services       = _get_services(conn)
    exhibit_types  = _get_exhibit_types(conn)
    appropriations = _get_appropriations(conn)

    return _tmpl().TemplateResponse(
        "index.html",
        {
            "request":        request,
            "filters":        filters,
            "fiscal_years":   fiscal_years,
            "services":       services,
            "exhibit_types":  exhibit_types,
            "appropriations": appropriations,
            **results,
        },
    )


@router.get("/about", response_class=HTMLResponse, include_in_schema=False)
def about(request: Request) -> HTMLResponse:
    """About page."""
    return _tmpl().TemplateResponse("about.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request) -> HTMLResponse:
    """Dashboard overview page with summary statistics."""
    return _tmpl().TemplateResponse("dashboard.html", {"request": request})


@router.get("/charts", response_class=HTMLResponse, include_in_schema=False)
def charts(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> HTMLResponse:
    """Chart.js visualisations page."""
    fiscal_years = _get_fiscal_years(conn)
    return _tmpl().TemplateResponse(
        "charts.html",
        {"request": request, "fiscal_years": fiscal_years},
    )


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
        {"request": request, "filters": filters, **results},
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

    item = dict(row)

    # FE-006: Related items — same program across fiscal years
    related_items: list[dict] = []
    pe_number = item.get("pe_number")
    if pe_number:
        related_rows = conn.execute(
            "SELECT id, fiscal_year, line_item_title, organization_name, "
            "amount_fy2026_request FROM budget_lines "
            "WHERE pe_number = ? AND id != ? ORDER BY fiscal_year",
            (pe_number, item_id),
        ).fetchall()
        related_items = [dict(r) for r in related_rows]

    # Fall back: match on organization_name + line_item_title if no PE results
    if not related_items:
        org   = item.get("organization_name")
        title = item.get("line_item_title")
        if org and title:
            related_rows = conn.execute(
                "SELECT id, fiscal_year, line_item_title, organization_name, "
                "amount_fy2026_request FROM budget_lines "
                "WHERE organization_name = ? AND line_item_title = ? AND id != ? "
                "ORDER BY fiscal_year",
                (org, title, item_id),
            ).fetchall()
            related_items = [dict(r) for r in related_rows]

    return _tmpl().TemplateResponse(
        "partials/detail.html",
        {"request": request, "item": item, "related_items": related_items},
    )


# ── Program Explorer routes ──────────────────────────────────────────────────

def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    """Check if a table exists in the database."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


@router.get("/programs", response_class=HTMLResponse, include_in_schema=False)
def programs(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> HTMLResponse:
    """Program Explorer landing page."""
    services = _get_services(conn)
    tags: list[dict] = []
    items: list[dict] = []
    total = 0

    if _table_exists(conn, "pe_index"):
        try:
            from api.routes.pe import list_pes, list_tags
            tag_result = list_tags(tag_source=None, conn=conn)
            tags = tag_result.get("tags", [])[:30]

            pe_result = list_pes(tag=None, q=None, service=None,
                                budget_type=None, approp=None, fy=None,
                                limit=25, offset=0, conn=conn)
            items = pe_result.get("items", [])
            total = pe_result.get("total", 0)
        except Exception:
            pass

    return _tmpl().TemplateResponse("programs.html", {
        "request": request,
        "services": services,
        "tags": tags,
        "items": items,
        "total": total,
    })


@router.get("/programs/{pe_number}", response_class=HTMLResponse, include_in_schema=False)
def program_detail(
    pe_number: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """Program Element detail page."""
    if not _table_exists(conn, "pe_index"):
        raise HTTPException(status_code=404, detail="Program enrichment data not available. "
                            "Run enrich_budget_db.py to populate PE data.")
    try:
        from api.routes.pe import get_pe
        pe_data = get_pe(pe_number, conn=conn)
    except HTTPException:
        raise HTTPException(status_code=404, detail=f"Program {pe_number} not found")

    # Also fetch related PE titles for display
    related = pe_data.get("related", [])
    for rel in related:
        if not rel.get("referenced_title"):
            title_row = conn.execute(
                "SELECT display_title FROM pe_index WHERE pe_number = ?",
                (rel.get("referenced_pe"),),
            ).fetchone()
            if title_row:
                rel["referenced_title"] = title_row["display_title"]

    return _tmpl().TemplateResponse("program-detail.html", {
        "request": request,
        "pe_data": pe_data,
    })


@router.get("/partials/program-list", response_class=HTMLResponse, include_in_schema=False)
def program_list_partial(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """HTMX partial: filtered PE card grid."""
    items: list[dict] = []
    total = 0

    if _table_exists(conn, "pe_index"):
        try:
            from api.routes.pe import list_pes
            params = request.query_params
            tag_values = params.getlist("tag") or None
            result = list_pes(
                tag=tag_values,
                q=params.get("q") or None,
                service=params.get("service") or None,
                budget_type=None, approp=None, fy=None,
                limit=25, offset=0, conn=conn,
            )
            items = result.get("items", [])
            total = result.get("total", 0)
        except Exception:
            pass

    return _tmpl().TemplateResponse("partials/program-list.html", {
        "request": request,
        "items": items,
        "total": total,
    })


@router.get("/partials/program-descriptions/{pe_number}",
            response_class=HTMLResponse, include_in_schema=False)
def program_descriptions_partial(
    pe_number: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """HTMX partial: PE narrative descriptions."""
    descriptions: list[dict] = []
    total = 0

    if _table_exists(conn, "pe_descriptions"):
        try:
            from api.routes.pe import get_pe_descriptions
            result = get_pe_descriptions(pe_number, fy=None, section=None, limit=10, offset=0, conn=conn)
            descriptions = result.get("descriptions", [])
            total = result.get("total", 0)
        except Exception:
            pass

    return _tmpl().TemplateResponse("partials/program-descriptions.html", {
        "request": request,
        "descriptions": descriptions,
        "total": total,
    })
