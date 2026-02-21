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
from utils.query import (
    build_where_clause,
    validate_amount_column,
    FISCAL_YEAR_COLUMN_LABELS,
    DEFAULT_AMOUNT_COLUMN,
)
from utils import sanitize_fts5_query

router = APIRouter(tags=["frontend"])


# LION-001: Custom HTML error handlers for 404/500 pages
def register_error_handlers(app) -> None:
    """Register custom exception handlers that render branded error pages."""

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
    """FIX-002: Query DISTINCT organization_name from budget_lines directly.

    Previously this queried the services_agencies reference table which contained
    both seed data ('Army', 'Air Force') and backfilled data ('ARMY', 'AF'),
    creating duplicates. Now uses only actual values from budget_lines, with a
    LEFT JOIN to services_agencies for display names where available.
    """
    cache_key = ("services", id(conn))
    cached = _services_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        rows = conn.execute(
            "SELECT DISTINCT b.organization_name AS code, "
            "COALESCE(s.full_name, b.organization_name) AS full_name "
            "FROM budget_lines b "
            "LEFT JOIN services_agencies s ON LOWER(b.organization_name) = LOWER(s.code) "
            "WHERE b.organization_name IS NOT NULL AND b.organization_name != '' "
            "ORDER BY b.organization_name"
        ).fetchall()
    except Exception:
        rows = conn.execute(
            "SELECT DISTINCT organization_name AS code, "
            "organization_name AS full_name "
            "FROM budget_lines "
            "WHERE organization_name IS NOT NULL AND organization_name != '' "
            "ORDER BY organization_name"
        ).fetchall()
    result = [{"code": r["code"], "full_name": r["full_name"]} for r in rows]
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
        _exhibit_types_cache.set(cache_key, result)  # only cache stable reference table
    except Exception:
        rows = conn.execute(
            "SELECT DISTINCT exhibit_type AS code FROM budget_lines "
            "WHERE exhibit_type IS NOT NULL ORDER BY exhibit_type"
        ).fetchall()
        result = [{"code": r["code"], "display_name": r["code"]} for r in rows]
    return result


def _get_fiscal_years(conn: sqlite3.Connection) -> list[dict]:
    """FIX-003: Filter to only valid fiscal year values.

    The fiscal_year column contains invalid values like 'Details' and
    'Emergency Disaster Relief Act' from parsing errors. Only return values
    that look like valid fiscal years (4-digit numbers or 'FYxxxx' patterns).
    """
    cache_key = ("fiscal_years", id(conn))
    cached = _fiscal_years_cache.get(cache_key)
    if cached is not None:
        return cached
    rows = conn.execute(
        "SELECT fiscal_year, COUNT(*) AS row_count FROM budget_lines "
        "WHERE fiscal_year IS NOT NULL "
        "AND (fiscal_year GLOB '[0-9][0-9][0-9][0-9]' "
        "     OR fiscal_year GLOB 'FY[0-9][0-9][0-9][0-9]') "
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
    # EAGLE-1: dynamic amount column (validated against whitelist)
    raw_amount_col = params.get("amount_column", "")
    try:
        amount_column = validate_amount_column(raw_amount_col or None)
    except ValueError:
        amount_column = DEFAULT_AMOUNT_COLUMN
    return {
        "q":                 params.get("q", ""),
        "fiscal_year":       params.getlist("fiscal_year"),
        "service":           params.getlist("service"),
        "exhibit_type":      params.getlist("exhibit_type"),
        "pe_number":         params.getlist("pe_number"),
        "appropriation_code": params.getlist("appropriation_code"),
        "min_amount":        min_amt,
        "max_amount":        max_amt,
        "amount_column":     amount_column,
        "sort_by":           params.get("sort_by", "id"),
        "sort_dir":          params.get("sort_dir", "asc"),
        "page":              max(1, int(params.get("page", 1))),
        # EAGLE-4: Expanded page size cap from 100 to 200
        "page_size":         min(200, max(10, int(params.get("page_size", 25)))),
    }

# EAGLE-4: Page size options for template dropdown
PAGE_SIZE_OPTIONS = [25, 50, 100, 200]


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

    # EAGLE-1: Parse amount filter values with dynamic column support
    min_amt_val = None
    max_amt_val = None
    min_amt = filters.get("min_amount", "")
    max_amt = filters.get("max_amount", "")
    if min_amt:
        try:
            min_amt_val = float(min_amt)
        except ValueError:
            pass
    if max_amt:
        try:
            max_amt_val = float(max_amt)
        except ValueError:
            pass

    # OPT-FE-001: Use shared WHERE builder from utils/query.py
    # EAGLE-1: Pass amount_column for dynamic FY filtering
    where, params = build_where_clause(
        fiscal_year=filters["fiscal_year"] or None,
        service=filters["service"] or None,
        exhibit_type=filters["exhibit_type"] or None,
        pe_number=filters["pe_number"] or None,
        appropriation_code=filters.get("appropriation_code") or None,
        min_amount=min_amt_val,
        max_amount=max_amt_val,
        amount_column=filters.get("amount_column"),
    )

    # EAGLE-5: Advanced search integration — parse structured query if available
    q = filters["q"].strip()
    parsed_query: dict | None = None

    # Try to use HAWK's advanced search parser; fall back to raw free-text
    fts_terms = q
    extra_field_conditions: list[str] = []
    extra_field_params: list = []

    if q:
        try:
            from utils.search_parser import parse_search_query
            parsed = parse_search_query(q)
            fts_terms = parsed.fts_terms
            parsed_query = {
                "raw": q,
                "fts_terms": parsed.fts_terms,
                "field_filters": [
                    {"field": f.field, "op": f.op, "value": f.value}
                    for f in parsed.field_filters
                ],
                "amount_filters": [
                    {"op": f.op, "value": f.value}
                    for f in parsed.amount_filters
                ],
            }

            # Convert field filters to SQL WHERE conditions
            _FIELD_TO_COLUMN = {
                "service": "organization_name",
                "exhibit": "exhibit_type",
                "pe": "pe_number",
                "org": "organization_name",
                "tag": None,  # tag filtering handled separately
            }
            for ff in parsed.field_filters:
                col = _FIELD_TO_COLUMN.get(ff.field)
                if col:
                    if ff.op == "=":
                        extra_field_conditions.append(f"{col} = ?")
                        extra_field_params.append(ff.value)

            # Convert amount filters to SQL WHERE conditions
            amt_col = filters.get("amount_column", DEFAULT_AMOUNT_COLUMN)
            for af in parsed.amount_filters:
                if af.op in (">", "<", ">=", "<="):
                    extra_field_conditions.append(f"{amt_col} {af.op} ?")
                    extra_field_params.append(af.value)
        except ImportError:
            # HAWK-4 not merged yet — treat entire query as free-text
            parsed_query = {
                "raw": q, "fts_terms": q,
                "field_filters": [], "amount_filters": [],
            }
        except Exception:
            parsed_query = {
                "raw": q, "fts_terms": q,
                "field_filters": [], "amount_filters": [],
            }

    # Apply extra field/amount conditions from parsed query
    if extra_field_conditions:
        for cond in extra_field_conditions:
            connector = "AND" if where else "WHERE"
            where = f"{where} {connector} {cond}"
        params = list(params) + extra_field_params

    # Apply keyword filter against FTS if provided
    fts_ids: list[int] | None = None
    if fts_terms:
        try:
            safe_q = sanitize_fts5_query(fts_terms)
        except Exception:
            safe_q = fts_terms.replace('"', '""')
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
                "parsed_query": parsed_query,
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

    # FIX-005: Added FY25 total and FY26 total columns.
    # FIX-007: Added source_file for source material links.
    rows = conn.execute(
        f"SELECT id, exhibit_type, fiscal_year, account, account_title, "
        f"organization_name, budget_activity_title, line_item_title, pe_number, "
        f"amount_fy2024_actual, amount_fy2025_enacted, amount_fy2025_total, "
        f"amount_fy2026_request, amount_fy2026_total, source_file "
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
        # EAGLE-5: Parsed query structure for template display
        "parsed_query": parsed_query,
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
            # EAGLE-1: Dynamic amount column context for FY selector
            "amount_column":        filters.get("amount_column", DEFAULT_AMOUNT_COLUMN),
            "fiscal_year_columns":  FISCAL_YEAR_COLUMN_LABELS,
            # EAGLE-4: Pagination options for template dropdown
            "page_size_options":    PAGE_SIZE_OPTIONS,
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
    # FIX-010: Non-HTMX requests (e.g. browser refresh) redirect to full page
    if not request.headers.get("HX-Request"):
        from starlette.responses import RedirectResponse
        qs = str(request.query_params)
        return RedirectResponse(url=f"/?{qs}" if qs else "/", status_code=302)

    filters = _parse_filters(request)
    results = _query_results(filters, conn)

    response = _tmpl().TemplateResponse(
        "partials/results.html",
        {
            "request": request,
            "filters": filters,
            # EAGLE-1: Dynamic amount column context
            "amount_column": filters.get("amount_column", DEFAULT_AMOUNT_COLUMN),
            "fiscal_year_columns": FISCAL_YEAR_COLUMN_LABELS,
            # EAGLE-4: Pagination options
            "page_size_options": PAGE_SIZE_OPTIONS,
            **results,
        },
    )
    # FIX-010: Tell HTMX to push /?params instead of /partials/results?params
    qs = str(request.query_params)
    response.headers["HX-Push-Url"] = f"/?{qs}" if qs else "/"
    return response


@router.get("/partials/detail/{item_id}", response_class=HTMLResponse, include_in_schema=False)
def detail_partial(
    item_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """HTMX partial: full detail panel for a single budget line."""
    # FIX-010: Non-HTMX requests redirect to the search page
    if not request.headers.get("HX-Request"):
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="/", status_code=302)

    row = conn.execute(
        "SELECT * FROM budget_lines WHERE id = ?", (item_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Budget line {item_id} not found")

    item = dict(row)

    # EAGLE-2: Tag-based related items — find budget lines sharing tags
    related_items: list[dict] = []
    pe_number = item.get("pe_number")

    if pe_number and _table_exists(conn, "pe_tags"):
        try:
            # Get tags for this item's PE
            item_tags = conn.execute(
                "SELECT DISTINCT tag FROM pe_tags WHERE pe_number = ?",
                (pe_number,),
            ).fetchall()
            tag_list = [t[0] for t in item_tags]

            if tag_list:
                # Find other PEs sharing these tags, ranked by shared tag count
                tag_placeholders = ",".join("?" * len(tag_list))
                tag_related_rows = conn.execute(
                    f"SELECT b.id, b.pe_number, b.fiscal_year, b.line_item_title, "
                    f"b.organization_name, "
                    f"b.amount_fy2024_actual, b.amount_fy2025_enacted, "
                    f"b.amount_fy2026_request, "
                    f"COUNT(DISTINCT pt.tag) AS shared_tag_count, "
                    f"GROUP_CONCAT(DISTINCT pt.tag) AS shared_tags "
                    f"FROM pe_tags pt "
                    f"JOIN budget_lines b ON b.pe_number = pt.pe_number "
                    f"WHERE pt.tag IN ({tag_placeholders}) "
                    f"AND b.id != ? "
                    f"GROUP BY b.id "
                    f"ORDER BY shared_tag_count DESC, b.pe_number "
                    f"LIMIT 10",
                    tag_list + [item_id],
                ).fetchall()
                related_items = [
                    {
                        **dict(r),
                        "shared_tags": (r["shared_tags"] or "").split(","),
                    }
                    for r in tag_related_rows
                ]
        except Exception:
            pass

    # Fallback: PE number match (original behavior)
    if not related_items and pe_number:
        related_rows = conn.execute(
            "SELECT id, fiscal_year, line_item_title, organization_name, "
            "amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request "
            "FROM budget_lines "
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
                "amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request "
                "FROM budget_lines "
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
                                budget_type=None, approp=None, account=None,
                                ba=None, exhibit=None, fy=None,
                                sort_by=None, sort_dir=None,
                                count_only=False, limit=25, offset=0,
                                conn=conn)
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
                budget_type=None, approp=None, account=None, ba=None,
                exhibit=None, fy=None, sort_by=None, sort_dir=None,
                count_only=False, limit=25, offset=0, conn=conn,
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
