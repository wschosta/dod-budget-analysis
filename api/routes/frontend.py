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

import logging
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response
from fastapi.templating import Jinja2Templates

from pathlib import Path as _Path

from api.database import get_db
from utils.database import get_amount_columns, table_exists
from pipeline.builder import EXHIBIT_TYPES as _EXHIBIT_TYPE_NAMES
from utils.cache import TTLCache
from utils.query import (
    ALLOWED_SORT_COLUMNS,
    _AMOUNT_COL_RE,
    build_where_clause,
    make_placeholders,
    parse_json,
    validate_amount_column,
    FISCAL_YEAR_COLUMN_LABELS,
    DEFAULT_AMOUNT_COLUMN,
    make_fiscal_year_column_labels,
)
from utils import sanitize_fts5_query

logger = logging.getLogger(__name__)


def _safe_int(value: str, default: int) -> int:
    """Convert string to int, returning default on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


router = APIRouter(tags=["frontend"])


# LION-001: Custom HTML error handlers for 404/500 pages
def register_error_handlers(app: Any) -> None:
    """Register custom exception handlers that render branded error pages."""

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception) -> HTMLResponse:
        tmpl = _tmpl()
        return tmpl.TemplateResponse(
            request, "errors/404.html", status_code=404
        )

    @app.exception_handler(500)
    async def server_error_handler(request: Request, exc: Exception) -> HTMLResponse:
        tmpl = _tmpl()
        return tmpl.TemplateResponse(
            request, "errors/500.html", status_code=500
        )

# Templates instance is set by create_app() after mounting.
_templates: Jinja2Templates | None = None

# OPT-FE-002: TTL caches for reference data (5-minute TTL)
_services_cache: TTLCache = TTLCache(maxsize=4, ttl_seconds=300)
_exhibit_types_cache: TTLCache = TTLCache(maxsize=4, ttl_seconds=300)
_fiscal_years_cache: TTLCache = TTLCache(maxsize=4, ttl_seconds=300)


def _format_fy(value: str | None) -> str:
    """Format fiscal year for display, avoiding FYFY duplication."""
    if not value:
        return ""
    s = str(value).strip()
    # Strip existing FY prefix (with or without space)
    if s.upper().startswith("FY"):
        s = s[2:].lstrip()
    return f"FY {s}" if s else ""


def _path_basename(value: str | None) -> str:
    """Return the final path segment, handling both `\\` and `/` separators.

    The corpus is indexed on Windows so source_file values use backslashes,
    but the same DB may be read on Linux in CI/deploy.  ``os.path.basename``
    only handles the platform's native separator; splitting on both keeps
    templates readable on either platform.
    """
    if not value:
        return ""
    s = str(value).replace("\\", "/")
    return s.rsplit("/", 1)[-1]


def set_templates(t: Jinja2Templates | None) -> None:
    global _templates
    _templates = t
    if t is not None:
        t.env.filters["format_fy"] = _format_fy
        t.env.filters["path_basename"] = _path_basename


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
            "SELECT b.organization_name AS code, "
            "COALESCE(s.full_name, b.organization_name) AS full_name, "
            "COUNT(*) AS row_count "
            "FROM budget_lines b "
            "LEFT JOIN services_agencies s ON LOWER(b.organization_name) = LOWER(s.code) "
            "WHERE b.organization_name IS NOT NULL AND b.organization_name != '' "
            "GROUP BY b.organization_name "
            "ORDER BY COUNT(*) DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute(
            "SELECT organization_name AS code, "
            "organization_name AS full_name, "
            "COUNT(*) AS row_count "
            "FROM budget_lines "
            "WHERE organization_name IS NOT NULL AND organization_name != '' "
            "GROUP BY organization_name "
            "ORDER BY COUNT(*) DESC"
        ).fetchall()
    result = [{"code": r["code"], "full_name": r["full_name"], "row_count": r["row_count"]} for r in rows]
    _services_cache.set(cache_key, result)
    return result


def _get_exhibit_types(conn: sqlite3.Connection) -> list[dict]:
    cache_key = ("exhibit_types", id(conn))
    cached = _exhibit_types_cache.get(cache_key)
    if cached is not None:
        return cached
    # _EXHIBIT_TYPE_NAMES merged with KEYWORD_ONLY_EXHIBIT_TYPES for full coverage
    from pipeline.builder import KEYWORD_ONLY_EXHIBIT_TYPES as _EXTRA_NAMES
    _all_names = {**_EXHIBIT_TYPE_NAMES, **_EXTRA_NAMES}

    def _clean_display(code: str, raw: str | None) -> str:
        """Return a human-readable label, falling back to the static map.

        Fixes issue #4: when the exhibit_types table exists but display_name
        is NULL, empty, or identical to the code (e.g. 'c1'), use the static
        map so the dropdown shows 'Military Construction (C-1)' not 'c1 — c1'.
        """
        if raw and raw.strip() and raw.strip().lower() != code.lower():
            return raw.strip()
        return _all_names.get(code, code.upper())

    try:
        rows = conn.execute(
            "SELECT code, display_name FROM exhibit_types ORDER BY code"
        ).fetchall()
        result = [{"code": r["code"], "display_name": _clean_display(r["code"], r["display_name"])} for r in rows]
        _exhibit_types_cache.set(cache_key, result)  # only cache stable reference table
    except sqlite3.OperationalError:
        rows = conn.execute(
            "SELECT DISTINCT exhibit_type AS code FROM budget_lines "
            "WHERE exhibit_type IS NOT NULL ORDER BY exhibit_type"
        ).fetchall()
        result = [{"code": r["code"], "display_name": _clean_display(r["code"], None)} for r in rows]
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
    try:
        rows = conn.execute(
            "SELECT TRIM(fiscal_year) AS fiscal_year, COUNT(*) AS row_count "
            "FROM budget_lines "
            "WHERE fiscal_year IS NOT NULL "
            "AND (TRIM(fiscal_year) GLOB '[0-9][0-9][0-9][0-9]' "
            "     OR TRIM(fiscal_year) GLOB 'FY [0-9][0-9][0-9][0-9]' "
            "     OR TRIM(fiscal_year) GLOB 'FY[0-9][0-9][0-9][0-9]') "
            "GROUP BY TRIM(fiscal_year) ORDER BY TRIM(fiscal_year)"
        ).fetchall()
    except Exception:
        logger.debug("Fiscal year GLOB query failed", exc_info=True)
        rows = []
    # Fallback: if GLOB matched nothing, try permissive LIKE
    if not rows:
        try:
            rows = conn.execute(
                "SELECT TRIM(fiscal_year) AS fiscal_year, COUNT(*) AS row_count "
                "FROM budget_lines "
                "WHERE fiscal_year IS NOT NULL AND fiscal_year != '' "
                "AND fiscal_year NOT LIKE '%Detail%' "
                "AND fiscal_year NOT LIKE '%Emergency%' "
                "AND fiscal_year NOT LIKE '%Act%' "
                "AND LENGTH(TRIM(fiscal_year)) <= 10 "
                "GROUP BY TRIM(fiscal_year) ORDER BY TRIM(fiscal_year)"
            ).fetchall()
        except Exception:
            logger.debug("Fiscal year fallback query failed", exc_info=True)
            rows = []
    result = [{"fiscal_year": r["fiscal_year"], "row_count": r["row_count"]} for r in rows]
    _fiscal_years_cache.set(cache_key, result)
    return result


def _get_budget_types(conn: sqlite3.Connection) -> list[dict]:
    """Return distinct budget_type values (colors of money)."""
    rows = conn.execute(
        "SELECT budget_type, COUNT(*) AS cnt "
        "FROM budget_lines "
        "WHERE budget_type IS NOT NULL AND budget_type != '' "
        "GROUP BY budget_type "
        "ORDER BY COUNT(*) DESC"
    ).fetchall()
    return [{"code": r["budget_type"], "title": r["budget_type"]} for r in rows]


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
        "budget_type":       params.getlist("budget_type"),
        "min_amount":        min_amt,
        "max_amount":        max_amt,
        "amount_column":     amount_column,
        "sort_by":           params.get("sort_by", "id"),
        "sort_dir":          params.get("sort_dir", "asc"),
        "page":              max(1, _safe_int(params.get("page", "1"), 1)),
        # EAGLE-4: Expanded page size cap from 100 to 200
        "page_size":         min(200, max(10, _safe_int(params.get("page_size", "25"), 25))),
    }

# EAGLE-4: Page size options for template dropdown
PAGE_SIZE_OPTIONS = [25, 50, 100, 200]


def _query_results(
    filters: dict[str, Any],
    conn: sqlite3.Connection,
    page_size: int | None = None,
) -> dict[str, Any]:
    """Run the filtered budget_lines query and return template context vars."""
    raw_sort = filters["sort_by"]
    # Accept both static allowed columns and any valid amount_fy* column
    if raw_sort in ALLOWED_SORT_COLUMNS or _AMOUNT_COL_RE.match(raw_sort):
        sort_by = raw_sort
    else:
        sort_by = "id"
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
        budget_type=filters.get("budget_type") or None,
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
            fts_terms = parsed.fts5_query
            parsed_query = {
                "raw": q,
                "fts_terms": parsed.fts5_query,
                "field_filters": [
                    {"field": field, "op": "=", "value": val}
                    for field, vals in parsed.filters.items()
                    for val in vals
                ],
                "amount_filters": [
                    {"op": op, "value": val}
                    for op, val in parsed.amount_filters
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
            for field, vals in parsed.filters.items():
                col = _FIELD_TO_COLUMN.get(field)
                if col:
                    for val in vals:
                        extra_field_conditions.append(f"{col} = ?")
                        extra_field_params.append(val)

            # Convert amount filters to SQL WHERE conditions
            amt_col = filters.get("amount_column", DEFAULT_AMOUNT_COLUMN)
            for af_op, af_val in parsed.amount_filters:
                if af_op in (">", "<", ">=", "<="):
                    extra_field_conditions.append(f"{amt_col} {af_op} ?")
                    extra_field_params.append(af_val)
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
        id_placeholders = make_placeholders(fts_ids)
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
    # Issue #29: Dynamically discover all amount_fy* columns instead of hardcoding.
    amount_cols = get_amount_columns(conn)
    if not amount_cols:
        amount_cols = ["amount_fy2024_actual", "amount_fy2025_enacted", "amount_fy2025_total",
                       "amount_fy2026_request", "amount_fy2026_total"]
    amt_select = ", ".join(amount_cols)
    rows = conn.execute(
        f"SELECT id, exhibit_type, fiscal_year, account, account_title, "
        f"organization_name, budget_activity_title, line_item_title, pe_number, "
        f"{amt_select}, source_file "
        f"FROM budget_lines {where} "
        f"ORDER BY {sort_by} {sort_dir} LIMIT ? OFFSET ?",
        params + [page_size, offset],
    ).fetchall()

    items = [dict(r) for r in rows]

    # ── Total program value from golden record (line_item_amounts) ─────────
    # Batch-query total value + FY range for PE numbers in current results.
    pe_numbers = list({r["pe_number"] for r in items if r.get("pe_number")})
    pe_totals: dict[str, dict] = {}
    if pe_numbers and table_exists(conn, "line_item_amounts"):
        try:
            placeholders = make_placeholders(pe_numbers)
            total_rows = conn.execute(
                f"SELECT li.pe_number, "
                f"       SUM(a.amount) AS total_value, "
                f"       MIN(a.target_fy) AS fy_min, "
                f"       MAX(a.target_fy) AS fy_max "
                f"FROM line_items li "
                f"JOIN line_item_amounts a ON a.line_item_id = li.id "
                f"WHERE li.pe_number IN ({placeholders}) "
                f"GROUP BY li.pe_number",
                pe_numbers,
            ).fetchall()
            for tr in total_rows:
                pe_totals[tr["pe_number"]] = {
                    "total_value": tr["total_value"],
                    "fy_min": tr["fy_min"],
                    "fy_max": tr["fy_max"],
                }
        except Exception:
            logger.debug("Failed to load golden record totals", exc_info=True)

    # Attach total program value to each item
    for item in items:
        pe = item.get("pe_number")
        if pe and pe in pe_totals:
            item["_pe_total"] = pe_totals[pe]

    return {
        "items":       items,
        "total":       total,
        "page":        page,
        "total_pages": total_pages,
        "sort_by":     sort_by,
        "sort_dir":    filters["sort_dir"],
        "page_size":   page_size,
        # Issue #29: Pass dynamic amount columns to templates
        "amount_columns": amount_cols,
        # EAGLE-5: Parsed query structure for template display
        "parsed_query": parsed_query,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/", include_in_schema=False)
def index(request: Request) -> RedirectResponse:
    """Redirect to Explorer page."""
    return RedirectResponse(url="/explorer", status_code=302)


@router.get("/home", response_class=HTMLResponse, include_in_schema=False)
def home_page(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> HTMLResponse:
    """Original search/home page (archived, still accessible via /home)."""
    filters        = _parse_filters(request)
    results        = _query_results(filters, conn)
    fiscal_years   = _get_fiscal_years(conn)
    services       = _get_services(conn)
    exhibit_types  = _get_exhibit_types(conn)
    budget_types   = _get_budget_types(conn)

    # Build dynamic FY column labels from discovered amount columns
    amt_cols = results.get("amount_columns", [])
    fy_col_labels = make_fiscal_year_column_labels(amt_cols) if amt_cols else FISCAL_YEAR_COLUMN_LABELS

    return _tmpl().TemplateResponse(
        request,
        "index.html",
        context={
            "filters":        filters,
            "fiscal_years":   fiscal_years,
            "services":       services,
            "exhibit_types":  exhibit_types,
            "budget_types":   budget_types,
            # Dynamic amount column context — discovered from DB schema
            "amount_column":        filters.get("amount_column", DEFAULT_AMOUNT_COLUMN),
            "fiscal_year_columns":  fy_col_labels,
            # EAGLE-4: Pagination options for template dropdown
            "page_size_options":    PAGE_SIZE_OPTIONS,
            **results,
        },
    )


@router.get("/about", response_class=HTMLResponse, include_in_schema=False)
def about(request: Request) -> HTMLResponse:
    """About page."""
    return _tmpl().TemplateResponse(request, "about.html")


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard(request: Request) -> HTMLResponse:
    """Dashboard overview page with summary statistics."""
    return _tmpl().TemplateResponse(request, "dashboard.html")


@router.get("/charts", response_class=HTMLResponse, include_in_schema=False)
def charts(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> HTMLResponse:
    """Chart.js visualisations page."""
    # Reverse so latest fiscal year (e.g. 2026) is at the top of the dropdown
    fiscal_years = list(reversed(_get_fiscal_years(conn)))
    return _tmpl().TemplateResponse(
        request,
        "charts.html",
        context={"fiscal_years": fiscal_years},
    )


@router.get("/partials/results", response_class=HTMLResponse, include_in_schema=False)
def results_partial(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """HTMX partial: filtered/paginated results table."""
    # FIX-010: Non-HTMX requests (e.g. browser refresh) redirect to full page
    if not request.headers.get("HX-Request"):
        qs = str(request.query_params)
        return RedirectResponse(url=f"/?{qs}" if qs else "/", status_code=302)

    filters = _parse_filters(request)
    results = _query_results(filters, conn)

    # Build dynamic FY column labels from discovered amount columns
    amt_cols = results.get("amount_columns", [])
    fy_col_labels = make_fiscal_year_column_labels(amt_cols) if amt_cols else FISCAL_YEAR_COLUMN_LABELS

    response = _tmpl().TemplateResponse(
        request,
        "partials/results.html",
        context={
            "filters": filters,
            # Dynamic amount column context — discovered from DB schema
            "amount_column": filters.get("amount_column", DEFAULT_AMOUNT_COLUMN),
            "fiscal_year_columns": fy_col_labels,
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
) -> Response:
    """HTMX partial: full detail panel for a single budget line."""
    # FIX-010: Non-HTMX requests redirect to the search page
    if not request.headers.get("HX-Request"):
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

    if pe_number and table_exists(conn, "pe_tags"):
        try:
            # Get tags for this item's PE
            item_tags = conn.execute(
                "SELECT DISTINCT tag FROM pe_tags WHERE pe_number = ?",
                (pe_number,),
            ).fetchall()
            tag_list = [t[0] for t in item_tags]

            if tag_list:
                # Find other PEs sharing these tags, ranked by shared tag count
                tag_placeholders = make_placeholders(tag_list)
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
            logger.debug("Tag-based related items lookup failed", exc_info=True)

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

    # Phase 11: BLI→PE mappings mined from P-5 PDF headers (shared helper).
    from api.routes.budget_lines import _fetch_related_pes
    related_pes = [
        rp.model_dump()
        for rp in _fetch_related_pes(
            conn, item.get("exhibit_type"), item.get("account"), item.get("line_item")
        )
    ]

    return _tmpl().TemplateResponse(
        request,
        "partials/detail.html",
        context={
            "item": item,
            "related_items": related_items,
            "related_pes": related_pes,
        },
    )


# ── Program Explorer routes ──────────────────────────────────────────────────


@router.get("/programs", response_class=HTMLResponse, include_in_schema=False)
def programs(request: Request, conn: sqlite3.Connection = Depends(get_db)) -> HTMLResponse:
    """Program Explorer landing page."""
    services = _get_services(conn)
    tags: list[dict] = []
    items: list[dict] = []
    total = 0

    has_pe_data = table_exists(conn, "pe_index")

    params = request.query_params
    try:
        limit = min(100, max(10, int(params.get("limit", "25"))))
    except (ValueError, TypeError):
        limit = 25
    try:
        offset = max(0, int(params.get("offset", "0")))
    except (ValueError, TypeError):
        offset = 0

    if has_pe_data:
        try:
            from api.routes.pe import list_pes, list_tags
            tag_result = list_tags(tag_source=None, conn=conn)
            tags = tag_result.get("tags", [])[:30]

            tag_values = params.getlist("tag") or None
            pe_result = list_pes(tag=tag_values,
                                q=params.get("q") or None,
                                service=params.get("service") or None,
                                budget_type=None, approp=None, account=None,
                                ba=None, exhibit=None, fy=None,
                                sort_by=None, sort_dir=None,
                                count_only=False, limit=limit, offset=offset,
                                conn=conn)
            items = pe_result.get("items", [])
            total = pe_result.get("total", 0)
        except Exception:
            logger.debug("Failed to load PE data for programs page", exc_info=True)

    return _tmpl().TemplateResponse(request, "programs.html", context={
        "services": services,
        "tags": tags,
        "items": items,
        "total": total,
        "has_pe_data": has_pe_data,
        "limit": limit,
        "offset": offset,
    })


@router.get("/programs/{pe_number}", response_class=HTMLResponse, include_in_schema=False)
def program_detail(
    pe_number: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """Program Element detail page."""
    if not table_exists(conn, "pe_index"):
        raise HTTPException(status_code=404, detail="Program enrichment data not available. "
                            "Run enrich_budget_db.py to populate PE data.")
    try:
        from api.routes.pe import get_pe
        pe_data = get_pe(pe_number, conn=conn)
    except HTTPException as exc:
        raise HTTPException(
            status_code=404,
            detail=exc.detail or f"Program {pe_number} not found",
        ) from exc

    # Batch-fetch related PE titles to avoid N+1 queries
    related = pe_data.get("related", [])
    missing_pes = [r["referenced_pe"] for r in related
                   if not r.get("referenced_title") and r.get("referenced_pe")]
    if missing_pes:
        ph = make_placeholders(missing_pes)
        title_map = {
            r["pe_number"]: r["display_title"]
            for r in conn.execute(
                f"SELECT pe_number, display_title FROM pe_index "
                f"WHERE pe_number IN ({ph})", missing_pes
            ).fetchall()
        }
        for rel in related:
            if not rel.get("referenced_title") and rel.get("referenced_pe"):
                rel["referenced_title"] = title_map.get(rel["referenced_pe"])

    return _tmpl().TemplateResponse(request, "program-detail.html", context={
        "pe_data": pe_data,
    })


@router.get("/bli/{bli_key:path}", response_class=HTMLResponse, include_in_schema=False)
def bli_detail(
    bli_key: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """Procurement (BLI) detail page — analogue of /programs/{pe_number}."""
    from api.routes.bli import get_bli
    try:
        bli_data = get_bli(bli_key, conn=conn)
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail or f"BLI {bli_key} not found",
        ) from exc

    return _tmpl().TemplateResponse(request, "bli-detail.html", context={
        "bli_data": bli_data,
    })


@router.get("/compare", response_class=HTMLResponse, include_in_schema=False)
def spruill_page(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """Spruill-style multi-PE funding comparison page."""
    params = request.query_params
    selected_pes = params.getlist("pe")
    return _tmpl().TemplateResponse(request, "spruill.html", context={
        "selected_pes": selected_pes,
    })


@router.get("/partials/spruill-table", response_class=HTMLResponse, include_in_schema=False)
def spruill_table_partial(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """HTMX partial: Spruill comparison table."""
    params = request.query_params
    pe_list = params.getlist("pe")
    detail = params.get("detail", "false").lower() in ("true", "1", "yes")
    rows: list[dict] = []
    fiscal_years: list[str] = []
    pe_count = 0

    if len(pe_list) >= 2 and table_exists(conn, "budget_lines"):
        try:
            from api.routes.pe import get_spruill_table
            result = get_spruill_table(pe=pe_list, detail=detail, conn=conn)
            rows = result.get("rows", [])
            fiscal_years = result.get("fiscal_years", [])
            pe_count = result.get("pe_count", 0)
        except Exception:
            logger.debug("Failed to load Spruill table data", exc_info=True)

    return _tmpl().TemplateResponse(request, "partials/spruill-table.html", context={
        "rows": rows,
        "fiscal_years": fiscal_years,
        "pe_count": pe_count,
    })


@router.get("/partials/program-list", response_class=HTMLResponse, include_in_schema=False)
def program_list_partial(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """HTMX partial: filtered PE card grid."""
    items: list[dict] = []
    total = 0

    params = request.query_params
    sort_by = params.get("sort_by") or None
    sort_dir = params.get("sort_dir") or None

    try:
        limit = min(100, max(10, int(params.get("limit", "25"))))
    except (ValueError, TypeError):
        limit = 25
    try:
        offset = max(0, int(params.get("offset", "0")))
    except (ValueError, TypeError):
        offset = 0

    if table_exists(conn, "pe_index"):
        try:
            from api.routes.pe import list_pes
            tag_values = params.getlist("tag") or None
            result = list_pes(
                tag=tag_values,
                q=params.get("q") or None,
                service=params.get("service") or None,
                budget_type=None, approp=None, account=None, ba=None,
                exhibit=None, fy=None, sort_by=sort_by, sort_dir=sort_dir,
                count_only=False, limit=limit, offset=offset, conn=conn,
            )
            items = result.get("items", [])
            total = result.get("total", 0)
        except Exception:
            logger.debug("Failed to load PE list for program-list partial", exc_info=True)

    return _tmpl().TemplateResponse(request, "partials/program-list.html", context={
        "items": items,
        "total": total,
        "sort_by": sort_by or "pe_number",
        "sort_dir": sort_dir or "asc",
        "limit": limit,
        "offset": offset,
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

    if table_exists(conn, "pe_descriptions"):
        try:
            from api.routes.pe import get_pe_descriptions
            result = get_pe_descriptions(pe_number, fy=None, section=None, limit=10, offset=0, conn=conn)
            descriptions = result.get("descriptions", [])
            total = result.get("total", 0)
        except Exception:
            logger.debug("Failed to load PE descriptions for %s", pe_number, exc_info=True)

    return _tmpl().TemplateResponse(request, "partials/program-descriptions.html", context={
        "descriptions": descriptions,
        "total": total,
    })


@router.get("/partials/program-related/{pe_number}",
            response_class=HTMLResponse, include_in_schema=False)
def program_related_partial(
    pe_number: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """HTMX partial: Related programs with confidence filter and pagination."""
    related: list[dict] = []
    total = 0
    limit = 20
    min_confidence = 0.0

    params = request.query_params
    try:
        limit = min(100, max(10, int(params.get("limit", "20"))))
    except (ValueError, TypeError):
        pass
    try:
        min_confidence = max(0.0, min(1.0, float(params.get("min_confidence", "0"))))
    except (ValueError, TypeError):
        pass

    if table_exists(conn, "pe_lineage"):
        try:
            from api.routes.pe import get_pe_related
            result = get_pe_related(
                pe_number,
                min_confidence=min_confidence,
                limit=limit,
                offset=0,
                conn=conn,
            )
            related = result.get("related", [])
            total = result.get("total", 0)
        except Exception:
            logger.debug("Failed to load related PEs for %s", pe_number, exc_info=True)

    return _tmpl().TemplateResponse(request, "partials/program-related.html", context={
        "pe_number": pe_number,
        "related": related,
        "total": total,
        "limit": limit,
        "min_confidence": min_confidence,
    })


@router.get("/partials/program-projects/{pe_number}",
            response_class=HTMLResponse, include_in_schema=False)
def program_projects_partial(
    pe_number: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """HTMX partial: Project-level descriptions for a PE."""
    projects: list[dict] = []

    if table_exists(conn, "project_descriptions"):
        try:
            from api.routes.pe import get_pe
            pe_data = get_pe(pe_number, conn=conn)
            projects = pe_data.get("projects", [])
        except Exception:
            logger.debug("Failed to load project descriptions for %s", pe_number, exc_info=True)

    return _tmpl().TemplateResponse(request, "partials/program-projects.html", context={
        "pe_number": pe_number,
        "projects": projects,
    })


@router.get("/partials/program-changes/{pe_number}",
            response_class=HTMLResponse, include_in_schema=False)
def program_changes_partial(
    pe_number: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """HTMX partial: Year-over-year funding changes for a PE."""
    changes: list[dict] = []
    summary: dict = {
        "total_fy2025": 0,
        "total_fy2026_request": 0,
        "total_delta": 0,
        "pct_change": None,
    }

    if table_exists(conn, "budget_lines"):
        try:
            from api.routes.pe import get_pe_changes
            result = get_pe_changes(pe_number, conn=conn)
            raw_items = result.get("line_items", [])
            # Map API field names to template-expected field names
            for item in raw_items:
                item["amount_fy2025"] = item.get("fy2025_total")
                item["amount_fy2026_request"] = item.get("fy2026_request")
            changes = raw_items
            summary = {
                "total_fy2025": result.get("total_fy2025", 0),
                "total_fy2026_request": result.get("total_fy2026_request", 0),
                "total_delta": result.get("total_delta", 0),
                "pct_change": result.get("pct_change"),
            }
        except Exception:
            logger.debug("Failed to load PE changes for %s", pe_number, exc_info=True)

    return _tmpl().TemplateResponse(request, "partials/program-changes.html", context={
        "pe_number": pe_number,
        "changes": changes,
        "summary": summary,
    })


@router.get("/partials/program-pdf-pages/{pe_number}",
            response_class=HTMLResponse, include_in_schema=False)
def program_pdf_pages_partial(
    pe_number: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """HTMX partial: PDF pages mentioning a PE."""
    pages: list[dict] = []
    total = 0

    params = request.query_params
    fy = params.get("fy") or None
    try:
        limit = min(100, max(1, int(params.get("limit", "20"))))
    except (ValueError, TypeError):
        limit = 20
    try:
        offset = max(0, int(params.get("offset", "0")))
    except (ValueError, TypeError):
        offset = 0

    if table_exists(conn, "pdf_pe_numbers") or table_exists(conn, "pdf_pages"):
        try:
            from api.routes.pe import get_pe_pdf_pages
            result = get_pe_pdf_pages(pe_number, fy=fy, limit=limit, offset=offset, conn=conn)
            pages = result.get("pages", [])
            total = result.get("total", 0)
        except Exception:
            logger.debug("Failed to load PDF pages for %s", pe_number, exc_info=True)

    return _tmpl().TemplateResponse(request, "partials/program-pdf-pages.html", context={
        "pe_number": pe_number,
        "pages": pages,
        "total": total,
    })


@router.get("/partials/top-changes",
            response_class=HTMLResponse, include_in_schema=False)
def top_changes_partial(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """HTMX partial: Top funding increases and decreases."""
    increases: list[dict] = []
    decreases: list[dict] = []

    if table_exists(conn, "budget_lines"):
        try:
            from api.routes.pe import get_top_changes
            inc_result = get_top_changes(
                direction="increase", service=None, min_delta=None,
                sort_by=None, limit=5, conn=conn,
            )
            increases = inc_result.get("items", [])

            dec_result = get_top_changes(
                direction="decrease", service=None, min_delta=None,
                sort_by=None, limit=5, conn=conn,
            )
            decreases = dec_result.get("items", [])
        except Exception:
            logger.debug("Failed to load top changes", exc_info=True)

    return _tmpl().TemplateResponse(request, "partials/top-changes.html", context={
        "increases": increases,
        "decreases": decreases,
    })


# ── Consolidated PE browser ─────────────────────────────────────────────────

_WORK_DB = _Path(__file__).resolve().parents[2] / "dod_budget_work.sqlite"


def _get_work_conn() -> sqlite3.Connection:
    """Open a read-only connection to the consolidated work database."""
    if not _WORK_DB.exists():
        raise HTTPException(
            status_code=503,
            detail="Consolidated database not available. Run scripts/consolidate_pe_lines.py first.",
        )
    conn = sqlite3.connect(f"file:{_WORK_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@router.get("/consolidated", response_class=HTMLResponse, include_in_schema=False)
def consolidated_list(request: Request) -> HTMLResponse:
    """Consolidated PE line items — list view."""
    conn = _get_work_conn()
    try:
        q = request.query_params.get("q", "").strip()
        service = request.query_params.get("service", "").strip()
        budget_type = request.query_params.get("budget_type", "").strip()
        sort_by = request.query_params.get("sort_by", "pe_number").strip()
        page = max(1, _safe_int(request.query_params.get("page", "1"), 1))
        page_size = 24

        _SORT_MAP = {
            "pe_number": "li.pe_number ASC",
            "name": "li.line_item_title ASC",
            "funding_desc": "best_amount DESC",
            "funding_asc": "best_amount ASC",
            "submissions": "li.submission_count DESC",
            "service": "li.organization_name ASC, li.pe_number ASC",
        }
        order_clause = _SORT_MAP.get(sort_by, _SORT_MAP["pe_number"])
        if sort_by not in _SORT_MAP:
            sort_by = "pe_number"

        where_parts: list[str] = []
        params: list[Any] = []

        if q:
            where_parts.append(
                "(li.pe_number LIKE ? OR li.line_item_title LIKE ? "
                "OR li.organization_name LIKE ?)"
            )
            like = f"%{q}%"
            params.extend([like, like, like])
        if service:
            where_parts.append("li.organization_name = ?")
            params.append(service)
        if budget_type:
            where_parts.append("li.budget_type = ?")
            params.append(budget_type)

        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        total = conn.execute(
            f"SELECT COUNT(*) FROM line_items li {where}", params
        ).fetchone()[0]
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)
        offset = (page - 1) * page_size

        items = conn.execute(
            f"""SELECT li.*,
                       (SELECT ROUND(a.amount, 0)
                        FROM line_item_amounts a
                        WHERE a.line_item_id = li.id
                          AND a.amount IS NOT NULL
                        ORDER BY a.precedence_rank, a.target_fy DESC
                        LIMIT 1) AS best_amount,
                       (SELECT a.target_fy || ' ' || a.amount_type
                        FROM line_item_amounts a
                        WHERE a.line_item_id = li.id
                          AND a.amount IS NOT NULL
                        ORDER BY a.precedence_rank, a.target_fy DESC
                        LIMIT 1) AS best_label,
                       (SELECT ROUND(SUM(a.amount), 0)
                        FROM line_item_amounts a
                        WHERE a.line_item_id = li.id
                          AND a.amount IS NOT NULL) AS total_program_value,
                       (SELECT COUNT(DISTINCT a.target_fy)
                        FROM line_item_amounts a
                        WHERE a.line_item_id = li.id
                          AND a.amount IS NOT NULL) AS fy_count
                FROM line_items li {where}
                ORDER BY {order_clause}
                LIMIT ? OFFSET ?""",
            params + [page_size, offset],
        ).fetchall()

        services = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT organization_name FROM line_items ORDER BY organization_name"
            ).fetchall()
        ]
        budget_types = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT budget_type FROM line_items "
                "WHERE budget_type IS NOT NULL ORDER BY budget_type"
            ).fetchall()
        ]
    finally:
        conn.close()

    return _tmpl().TemplateResponse(request, "consolidated.html", context={
        "items": [dict(r) for r in items],
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "page_size": page_size,
        "services": services,
        "budget_types": budget_types,
        "q": q,
        "service": service,
        "budget_type": budget_type,
        "sort_by": sort_by,
    })


@router.get("/consolidated/{pe_number}", response_class=HTMLResponse, include_in_schema=False)
def consolidated_detail(request: Request, pe_number: str) -> HTMLResponse:
    """Consolidated PE detail — golden record + time series + submissions."""
    conn = _get_work_conn()
    try:
        item = conn.execute(
            "SELECT * FROM line_items WHERE pe_number = ? LIMIT 1",
            (pe_number,),
        ).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail=f"PE {pe_number} not found")

        li_id = item["id"]

        amounts = conn.execute(
            """SELECT a.target_fy, a.amount_type, a.amount, a.quantity,
                      a.source_submission_fy, a.precedence_rank
               FROM line_item_amounts a
               INNER JOIN (
                   SELECT target_fy, MIN(precedence_rank) AS best_rank
                   FROM line_item_amounts
                   WHERE line_item_id = ?
                   GROUP BY target_fy
               ) best ON a.target_fy = best.target_fy
                      AND a.precedence_rank = best.best_rank
               WHERE a.line_item_id = ?
               ORDER BY a.target_fy""",
            (li_id, li_id),
        ).fetchall()

        submissions = conn.execute(
            """SELECT fiscal_year, source_file, raw_amounts, raw_quantities
               FROM budget_submissions
               WHERE line_item_id = ?
               ORDER BY fiscal_year, source_file""",
            (li_id,),
        ).fetchall()

        # Parse raw_amounts JSON for display.
        parsed_subs = []
        for s in submissions:
            raw = parse_json(s["raw_amounts"], {})
            parsed_subs.append({
                "fiscal_year": s["fiscal_year"],
                "source_file": s["source_file"],
                "amounts": raw,
            })

        # Group submissions by fiscal_year for the template.
        sub_groups: dict[str, list] = {}
        for ps in parsed_subs:
            fy = ps["fiscal_year"]
            if fy not in sub_groups:
                sub_groups[fy] = []
            sub_groups[fy].append(ps)

        # ── R-2A Sub-Projects ────────────────────────────────────
        projects_by_num: dict[str, dict] = {}
        try:
            proj_rows = conn.execute(
                """SELECT project_number, project_title,
                          fiscal_year, fy_columns, amounts, narrative_text
                   FROM pe_projects
                   WHERE pe_number = ?
                   ORDER BY project_number, fiscal_year DESC""",
                (pe_number,),
            ).fetchall()
            for pr in proj_rows:
                pnum = pr["project_number"]
                fy_cols = parse_json(pr["fy_columns"], [])
                amts = parse_json(pr["amounts"], [])
                entry = {
                    "fiscal_year": pr["fiscal_year"],
                    "fy_columns": fy_cols,
                    "amounts": amts,
                    "narrative_text": pr["narrative_text"] or "",
                }
                if pnum not in projects_by_num:
                    projects_by_num[pnum] = {
                        "project_number": pnum,
                        "project_title": pr["project_title"],
                        "submissions": [entry],
                    }
                else:
                    projects_by_num[pnum]["submissions"].append(entry)
        except Exception:
            pass  # pe_projects table may not exist

        # ── Build funding matrix (transposed: FYs as columns) ────
        all_fys_set: set[int] = set()
        pe_row: dict = {"label": "PE Total", "project_number": None, "fy_vals": {}}
        for a in amounts:
            fy = a["target_fy"]
            pe_row["fy_vals"][fy] = a["amount"]
            all_fys_set.add(fy)

        project_rows: list[dict] = []
        for proj in projects_by_num.values():
            row: dict = {
                "label": proj["project_title"],
                "project_number": proj["project_number"],
                "fy_vals": {},
            }
            # Submissions are already sorted newest-first (fiscal_year DESC)
            for sub in proj["submissions"]:
                if not sub["amounts"] or not sub["fy_columns"]:
                    continue
                sorted_fys = sorted(sub["fy_columns"], key=lambda x: int(x))
                for i, fy_str in enumerate(sorted_fys):
                    if i >= len(sub["amounts"]):
                        break
                    fy_int = int(fy_str)
                    if fy_int not in row["fy_vals"]:  # latest submission wins
                        val_m = sub["amounts"][i]
                        row["fy_vals"][fy_int] = round(val_m * 1000, 1)  # $M → $K
                        all_fys_set.add(fy_int)
            if row["fy_vals"]:
                project_rows.append(row)

        matrix_fys = sorted(all_fys_set)

        # ── "Not accounted for" difference row ──
        diff_row: dict | None = {"label": "Not accounted for", "fy_vals": {}}
        has_diff = False
        for fy in matrix_fys:
            pe_val = pe_row["fy_vals"].get(fy)
            if pe_val is None:
                continue
            sub_sum = sum(r["fy_vals"].get(fy, 0) or 0 for r in project_rows)
            diff = round(pe_val - sub_sum, 1)
            if abs(diff) > 0.5:  # ignore rounding noise
                assert diff_row is not None
                diff_row["fy_vals"][fy] = diff
                has_diff = True
        if not has_diff:
            diff_row = None

        # ── PE-level mission descriptions (by FY) ──
        pe_descriptions: list[dict] = []
        try:
            desc_rows = conn.execute(
                """SELECT fiscal_year, description_text
                   FROM pe_mission_descriptions
                   WHERE pe_number = ?
                   ORDER BY fiscal_year""",
                (pe_number,),
            ).fetchall()
            pe_descriptions = [
                {"fiscal_year": r["fiscal_year"], "text": r["description_text"]}
                for r in desc_rows
            ]
        except Exception:
            pass  # table may not exist yet

        # ── Tags (PE-level and project-level) ──
        pe_tags: list[dict] = []
        project_tags: dict[str, list[dict]] = {}
        try:
            tag_rows = conn.execute(
                """SELECT tag, tag_source, confidence, project_number
                   FROM pe_tags
                   WHERE pe_number = ?
                   ORDER BY confidence DESC, tag""",
                (pe_number,),
            ).fetchall()
            for t in tag_rows:
                entry = {
                    "tag": t["tag"],
                    "tag_source": t["tag_source"],
                    "confidence": t["confidence"],
                }
                if t["project_number"]:
                    pn = t["project_number"]
                    if pn not in project_tags:
                        project_tags[pn] = []
                    project_tags[pn].append(entry)
                else:
                    pe_tags.append(entry)
        except Exception:
            pass  # pe_tags table may not exist

    finally:
        conn.close()

    return _tmpl().TemplateResponse(request, "consolidated_detail.html", context={
        "item": dict(item),
        "amounts": [dict(a) for a in amounts],
        "sub_groups": sub_groups,
        "sub_count": len(parsed_subs),
        "projects": list(projects_by_num.values()),
        "matrix_fys": matrix_fys,
        "pe_row": pe_row,
        "project_rows": project_rows,
        "diff_row": diff_row,
        "pe_descriptions": pe_descriptions,
        "pe_tags": pe_tags,
        "project_tags": project_tags,
    })

# ── GET /explorer ────────────────────────────────────────────────────────────

@router.get("/explorer", response_class=HTMLResponse)
async def explorer_page(
    request: Request,
    keywords: str | None = None,
) -> HTMLResponse:
    """Server-rendered keyword explorer page."""
    return _tmpl().TemplateResponse(request, "explorer.html", context={
        "keyword_input": keywords or "",
    })
