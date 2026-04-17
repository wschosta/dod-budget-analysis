"""
GET /api/v1/search endpoint (Step 2.C3-a).

Reuses FTS5 MATCH logic from search_budget.py.  Returns unified results with
optional snippet highlighting for both budget lines and PDF pages.

SEARCH-001: BM25 relevance scoring via FTS5 rank function.
SEARCH-002: Structured filter support (fiscal_year, service, exhibit_type).
SEARCH-003: HTML highlighting with <mark> tags in snippets.
SEARCH-004: Search suggestions/autocomplete endpoint.
"""

import logging
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.database import get_db
from api.models import FilterParams, SearchResponse, SearchResultItem
from utils import sanitize_fts5_query
from utils.formatting import extract_snippet_highlighted
from utils.query import build_where_clause

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


# ── SEARCH-001: BM25-ranked budget lines query ───────────────────────────────

# SEARCH-005: FTS scan cap (issue #60).
# Without this, the FTS subquery materialises *all* matching rows before the
# outer JOIN+LIMIT is applied, which is expensive on large corpora.
# When there are no structured WHERE filters and sorting is by relevance, we
# pass exactly offset+limit to the FTS subquery (ORDER BY rank enables FTS5's
# early-termination optimiser path).  When structured filters are present the
# filter attrition rate is unknown, so we use a generous cap instead.
_FTS_SCAN_LIMIT = 10_000


def _budget_select(
    fts_query: str,
    sort: str,
    fiscal_year: list[str] | None,
    service: list[str] | None,
    exhibit_type: list[str] | None,
    limit: int,
    offset: int,
    pe_number: list[str] | None = None,
    appropriation_code: list[str] | None = None,
) -> tuple[str, list[Any]]:
    """Build the budget lines search query with BM25 scoring."""
    # SEARCH-002: Build structured WHERE clause
    where, params = build_where_clause(
        fiscal_year=fiscal_year,
        service=service,
        exhibit_type=exhibit_type,
        pe_number=pe_number,
        appropriation_code=appropriation_code,
    )

    # SEARCH-005: Bound the FTS scan to avoid full materialisation (issue #60).
    # For unfiltered relevance queries the exact row count is known up-front;
    # ORDER BY rank lets FTS5 stop scanning once the top rows are found.
    # For filtered or amount-sorted queries a generous cap is used instead.
    if not where and sort == "relevance":
        fts_limit = min(_FTS_SCAN_LIMIT, offset + limit)
        fts_subquery = (
            "SELECT rowid, bm25(budget_lines_fts) AS score "
            "FROM budget_lines_fts "
            "WHERE budget_lines_fts MATCH ? "
            f"ORDER BY rank LIMIT {fts_limit}"
        )
    else:
        fts_subquery = (
            "SELECT rowid, bm25(budget_lines_fts) AS score "
            "FROM budget_lines_fts "
            f"WHERE budget_lines_fts MATCH ? LIMIT {_FTS_SCAN_LIMIT}"
        )

    if where:
        sql = f"""
            SELECT b.id, b.source_file, b.exhibit_type, b.sheet_name, b.fiscal_year,
                   b.account, b.account_title, b.organization_name,
                   b.budget_activity_title, b.sub_activity_title,
                   b.line_item, b.line_item_title,
                   b.amount_fy2024_actual, b.amount_fy2025_enacted,
                   b.amount_fy2026_request, b.amount_fy2026_total,
                   b.pe_number, b.amount_type,
                   fts.score
            FROM budget_lines b
            JOIN ({fts_subquery}) fts ON b.id = fts.rowid
            {where}
        """
    else:
        sql = f"""
            SELECT b.id, b.source_file, b.exhibit_type, b.sheet_name, b.fiscal_year,
                   b.account, b.account_title, b.organization_name,
                   b.budget_activity_title, b.sub_activity_title,
                   b.line_item, b.line_item_title,
                   b.amount_fy2024_actual, b.amount_fy2025_enacted,
                   b.amount_fy2026_request, b.amount_fy2026_total,
                   b.pe_number, b.amount_type,
                   fts.score
            FROM budget_lines b
            JOIN ({fts_subquery}) fts ON b.id = fts.rowid
        """

    if sort == "amount_desc":
        sql += " ORDER BY COALESCE(b.amount_fy2026_request, b.amount_fy2025_enacted, 0) DESC"
    else:
        # relevance: BM25 returns negative values — lower = better rank, so ASC
        sql += " ORDER BY fts.score ASC"

    sql += " LIMIT ? OFFSET ?"
    return sql, [fts_query] + params + [limit, offset]


def _pdf_select(
    fts_query: str,
    fiscal_year: list[str] | None,
    exhibit_type: list[str] | None,
    limit: int,
    offset: int,
    service: list[str] | None = None,
) -> tuple[str, list[Any]]:
    """Build the PDF pages search query with BM25 scoring via subquery JOIN.

    LION-100: Supports fiscal_year and exhibit_type filtering on pdf_pages
    columns added during LION-100 schema update.
    """
    from utils.query import _add_in_condition

    conditions: list[str] = []
    params: list[Any] = [fts_query]

    _add_in_condition(conditions, params, "p.fiscal_year", fiscal_year)
    _add_in_condition(conditions, params, "p.exhibit_type", exhibit_type)
    if service:
        sub = " OR ".join("p.source_category LIKE ?" for _ in service)
        conditions.append(f"({sub})")
        params.extend(f"%{s}%" for s in service)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # SEARCH-005: Bound the FTS scan (issue #60).
    pdf_fts_limit = (
        min(_FTS_SCAN_LIMIT, offset + limit) if not conditions else _FTS_SCAN_LIMIT
    )

    sql = f"""
        SELECT p.id, p.source_file, p.source_category, p.page_number,
               p.page_text, p.has_tables, p.fiscal_year, p.exhibit_type,
               fts.score
        FROM pdf_pages p
        JOIN (
            SELECT rowid, bm25(pdf_pages_fts) AS score
            FROM pdf_pages_fts
            WHERE pdf_pages_fts MATCH ?
            ORDER BY rank LIMIT {pdf_fts_limit}
        ) fts ON p.id = fts.rowid
        {where}
        ORDER BY fts.score ASC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    return sql, params


def _description_select(
    fts_query: str,
    raw_query: str,
    limit: int,
    offset: int,
    conn: sqlite3.Connection,
) -> list[dict]:
    """Search pe_descriptions via FTS5 (or LIKE fallback).

    Returns a list of result dicts with result_type="description".
    """
    results: list[dict] = []

    # Try FTS5 first
    try:
        conn.execute("SELECT 1 FROM pe_descriptions_fts LIMIT 0")
        # SEARCH-005: Bound the FTS scan (issue #60).
        desc_fts_limit = min(_FTS_SCAN_LIMIT, offset + limit)
        rows = conn.execute(
            f"""
            SELECT d.id, d.pe_number, d.section_header, d.description_text,
                   d.source_file, d.fiscal_year,
                   bm25(pe_descriptions_fts) AS score
            FROM pe_descriptions d
            JOIN (
                SELECT rowid, bm25(pe_descriptions_fts) AS score
                FROM pe_descriptions_fts
                WHERE pe_descriptions_fts MATCH ?
                ORDER BY rank LIMIT {desc_fts_limit}
            ) fts ON d.id = fts.rowid
            ORDER BY fts.score ASC
            LIMIT ? OFFSET ?
        """,
            (fts_query, limit, offset),
        ).fetchall()
        for row in rows:
            d = dict(row)
            score = d.pop("score", None)
            snippet = extract_snippet_highlighted(
                str(d.get("description_text") or ""), raw_query, html=True, max_len=200
            )
            results.append(
                {
                    "result_type": "description",
                    "id": d["id"],
                    "source_file": d.get("source_file", ""),
                    "snippet": snippet,
                    "score": score,
                    "data": d,
                }
            )
        return results
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass  # FTS5 table doesn't exist, try LIKE fallback

    # LIKE fallback on pe_descriptions
    try:
        rows = conn.execute(
            """
            SELECT id, pe_number, section_header, description_text,
                   source_file, fiscal_year
            FROM pe_descriptions
            WHERE description_text LIKE ?
            ORDER BY pe_number, fiscal_year
            LIMIT ? OFFSET ?
        """,
            (f"%{raw_query}%", limit, offset),
        ).fetchall()
        for row in rows:
            d = dict(row)
            snippet = extract_snippet_highlighted(
                str(d.get("description_text") or ""), raw_query, html=True, max_len=200
            )
            results.append(
                {
                    "result_type": "description",
                    "id": d["id"],
                    "source_file": d.get("source_file", ""),
                    "snippet": snippet,
                    "score": None,
                    "data": d,
                }
            )
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        logger.warning(
            "pe_descriptions search failed for q=%r", raw_query, exc_info=True
        )

    return results


def _bli_description_select(
    fts_query: str,
    raw_query: str,
    limit: int,
    offset: int,
    conn: sqlite3.Connection,
) -> list[dict]:
    """Search bli_descriptions via FTS5 (or LIKE fallback).

    Mirrors ``_description_select`` but targets the procurement narrative
    corpus (P-5 justification text extracted by enrichment Phase 9).
    Returns result dicts with ``result_type="bli_description"``.
    """
    results: list[dict] = []

    try:
        conn.execute("SELECT 1 FROM bli_descriptions_fts LIMIT 0")
        desc_fts_limit = min(_FTS_SCAN_LIMIT, offset + limit)
        rows = conn.execute(
            f"""
            SELECT d.id, d.bli_key, d.section_header, d.description_text,
                   d.source_file, d.fiscal_year,
                   bm25(bli_descriptions_fts) AS score
            FROM bli_descriptions d
            JOIN (
                SELECT rowid, bm25(bli_descriptions_fts) AS score
                FROM bli_descriptions_fts
                WHERE bli_descriptions_fts MATCH ?
                ORDER BY rank LIMIT {desc_fts_limit}
            ) fts ON d.id = fts.rowid
            ORDER BY fts.score ASC
            LIMIT ? OFFSET ?
            """,
            (fts_query, limit, offset),
        ).fetchall()
        for row in rows:
            d = dict(row)
            score = d.pop("score", None)
            snippet = extract_snippet_highlighted(
                str(d.get("description_text") or ""), raw_query, html=True, max_len=200
            )
            results.append({
                "result_type": "bli_description",
                "id": d["id"],
                "source_file": d.get("source_file", ""),
                "snippet": snippet,
                "score": score,
                "data": d,
            })
        return results
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass  # FTS5 table doesn't exist yet, fall through to LIKE

    try:
        rows = conn.execute(
            """
            SELECT id, bli_key, section_header, description_text,
                   source_file, fiscal_year
            FROM bli_descriptions
            WHERE description_text LIKE ?
            ORDER BY bli_key, fiscal_year
            LIMIT ? OFFSET ?
            """,
            (f"%{raw_query}%", limit, offset),
        ).fetchall()
        for row in rows:
            d = dict(row)
            snippet = extract_snippet_highlighted(
                str(d.get("description_text") or ""), raw_query, html=True, max_len=200
            )
            results.append({
                "result_type": "bli_description",
                "id": d["id"],
                "source_file": d.get("source_file", ""),
                "snippet": snippet,
                "score": None,
                "data": d,
            })
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        logger.warning(
            "bli_descriptions search failed for q=%r", raw_query, exc_info=True
        )

    return results


@router.get(
    "",
    response_model=SearchResponse,
    summary="Full-text search",
    responses={
        400: {
            "description": "Invalid search parameters",
            "content": {
                "application/json": {
                    "example": {
                        "error": "Bad request",
                        "detail": "Invalid sort parameter",
                        "status_code": 400,
                    }
                }
            },
        },
        422: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "example": {
                        "error": "Validation error",
                        "detail": "q: ensure this value has at least 1 characters",
                        "status_code": 422,
                    }
                }
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {
                "application/json": {
                    "example": {"error": "Too many requests", "status_code": 429}
                }
            },
        },
    },
)
def search(
    q: str = Query(
        ..., min_length=1, max_length=500, description="Search query string"
    ),
    filters: FilterParams = Depends(),
    type: str = Query(
        "both",
        description="Result type: 'both', 'excel', or 'pdf'",
        pattern="^(both|excel|pdf)$",
    ),
    source: str = Query(
        "budget_lines",
        description="Search source: 'budget_lines' (default), 'descriptions', or 'both'",
    ),
    sort: str = Query(
        "relevance",
        description="Sort order: 'relevance' (BM25) or 'amount_desc'",
        pattern="^(relevance|amount_desc)$",
    ),
    limit: int = Query(20, ge=1, le=200, description="Max results per type"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    conn: sqlite3.Connection = Depends(get_db),
) -> SearchResponse:
    """Search budget line items and/or PDF page content with FTS5.

    Results are ranked by BM25 relevance by default (SEARCH-001).
    Snippets include HTML <mark> highlighting (SEARCH-003).

    The `source` parameter controls which data sources are searched:
    - "budget_lines" (default): searches budget_lines and pdf_pages (controlled by `type`)
    - "descriptions": searches pe_descriptions only
    - "both": searches budget_lines/pdf_pages AND pe_descriptions
    """
    # Validate source parameter
    if source not in ("budget_lines", "descriptions", "both"):
        source = "budget_lines"

    fts_query = sanitize_fts5_query(q)
    if not fts_query:
        raise HTTPException(
            status_code=400, detail="Query contains no searchable terms"
        )

    results: list[SearchResultItem] = []
    # Fetch limit+1 rows per type to detect if more results exist
    fetch_limit = limit + 1
    bl_has_more = False
    pdf_has_more = False
    desc_has_more = False

    # Search budget_lines and pdf_pages when source is "budget_lines" or "both"
    if source in ("budget_lines", "both"):
        if type in ("both", "excel"):
            try:
                sql, params = _budget_select(
                    fts_query=fts_query,
                    sort=sort,
                    fiscal_year=filters.fiscal_year,
                    service=filters.service,
                    exhibit_type=filters.exhibit_type,
                    limit=fetch_limit,
                    offset=offset,
                    pe_number=filters.pe_number,
                    appropriation_code=filters.appropriation_code,
                )
                rows = conn.execute(sql, params).fetchall()
            except (sqlite3.OperationalError, sqlite3.DatabaseError):
                logger.warning(
                    "Budget lines FTS query failed for q=%r", q, exc_info=True
                )
                rows = []
            if len(rows) > limit:
                bl_has_more = True
                rows = rows[:limit]
            for row in rows:
                d = dict(row)
                score = d.pop("score", None)
                # SEARCH-003: HTML-highlighted snippet
                snippet = extract_snippet_highlighted(
                    str(d.get("line_item_title") or d.get("account_title") or ""),
                    q,
                    html=True,
                )
                results.append(
                    SearchResultItem(
                        result_type="budget_line",
                        id=d["id"],
                        source_file=d["source_file"],
                        snippet=snippet,
                        score=score,
                        data=d,
                    )
                )

        if type in ("both", "pdf"):
            try:
                sql, params = _pdf_select(
                    fts_query,
                    filters.fiscal_year,
                    filters.exhibit_type,
                    fetch_limit,
                    offset,
                    service=filters.service,
                )
                rows = conn.execute(sql, params).fetchall()
            except (sqlite3.OperationalError, sqlite3.DatabaseError):
                logger.warning("PDF pages FTS query failed for q=%r", q, exc_info=True)
                rows = []
            if len(rows) > limit:
                pdf_has_more = True
                rows = rows[:limit]
            for row in rows:
                d = dict(row)
                score = d.pop("score", None)
                snippet = extract_snippet_highlighted(
                    str(d.get("page_text") or ""), q, html=True
                )
                results.append(
                    SearchResultItem(
                        result_type="pdf_page",
                        id=d["id"],
                        source_file=d["source_file"],
                        snippet=snippet,
                        score=score,
                        data=d,
                    )
                )

    # Search pe_descriptions and bli_descriptions when source is "descriptions" or "both"
    if source in ("descriptions", "both"):
        desc_results = _description_select(fts_query, q, fetch_limit, offset, conn)
        if len(desc_results) > limit:
            desc_has_more = True
            desc_results = desc_results[:limit]
        bli_desc_results = _bli_description_select(
            fts_query, q, fetch_limit, offset, conn
        )
        if len(bli_desc_results) > limit:
            desc_has_more = True
            bli_desc_results = bli_desc_results[:limit]
        for dr in (*desc_results, *bli_desc_results):
            results.append(
                SearchResultItem(
                    result_type=dr["result_type"],
                    id=dr["id"],
                    source_file=dr["source_file"] or "",
                    snippet=dr["snippet"],
                    score=dr["score"],
                    data=dr["data"],
                )
            )

    bl_count = sum(1 for r in results if r.result_type == "budget_line")
    pdf_count = sum(1 for r in results if r.result_type == "pdf_page")

    return SearchResponse(
        query=q,
        total=len(results),
        budget_line_count=bl_count,
        pdf_page_count=pdf_count,
        limit=limit,
        offset=offset,
        has_more=bl_has_more or pdf_has_more or desc_has_more,
        results=results,
    )


# ── SEARCH-004: Search suggestions / autocomplete ────────────────────────────


@router.get(
    "/suggest",
    summary="Search suggestions/autocomplete",
    response_model=list[dict],
)
def suggest(
    q: str = Query(..., min_length=1, max_length=200, description="Prefix to complete"),
    limit: int = Query(5, ge=1, le=20, description="Max suggestions"),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[dict]:
    """Return search suggestions for typeahead UI.

    Queries DISTINCT line_item_title, account_title, pe_number, and
    pe_index display_title for values matching the given prefix.
    Uses prefix match first; falls back to contains match if needed.
    PE entries include display_title for richer autocomplete display.
    """
    prefix = q.strip()
    if not prefix:
        return []

    prefix_param = f"{prefix}%"
    contains_param = f"%{prefix}%"
    suggestions: list[dict] = []
    seen: set[str] = set()

    def _add(value: str, field: str, label: str | None = None) -> None:
        key = f"{field}:{value}"
        if key not in seen:
            seen.add(key)
            entry: dict = {"value": value, "field": field}
            if label:
                entry["label"] = label
            suggestions.append(entry)

    # PE numbers with their display titles (prefix match)
    try:
        for r in conn.execute(
            "SELECT pe_number, display_title FROM pe_index "
            "WHERE pe_number LIKE ? OR display_title LIKE ? "
            "LIMIT ?",
            (prefix_param, contains_param, limit),
        ).fetchall():
            _add(r["pe_number"], "pe_number", r["display_title"])
    except sqlite3.OperationalError:
        pass  # pe_index table may not exist

    # Budget line fields in one query: prefix titles first, then contains
    # matches for titles, account, and org — ordered by priority.
    if len(suggestions) < limit:
        try:
            rows = conn.execute(
                "SELECT value, field FROM ("
                "  SELECT DISTINCT line_item_title AS value, 'line_item_title' AS field, 1 AS prio"
                "  FROM budget_lines"
                "  WHERE line_item_title LIKE ? AND line_item_title IS NOT NULL"
                "  UNION ALL"
                "  SELECT DISTINCT line_item_title, 'line_item_title', 2"
                "  FROM budget_lines"
                "  WHERE line_item_title LIKE ? AND line_item_title NOT LIKE ?"
                "  AND line_item_title IS NOT NULL"
                "  UNION ALL"
                "  SELECT DISTINCT account_title, 'account_title', 3"
                "  FROM budget_lines"
                "  WHERE account_title LIKE ? AND account_title IS NOT NULL"
                "  UNION ALL"
                "  SELECT DISTINCT organization_name, 'organization_name', 4"
                "  FROM budget_lines"
                "  WHERE organization_name LIKE ? AND organization_name IS NOT NULL"
                ") ORDER BY prio LIMIT ?",
                (
                    prefix_param,
                    contains_param,
                    prefix_param,
                    contains_param,
                    contains_param,
                    limit * 3,
                ),
            ).fetchall()
            for r in rows:
                if len(suggestions) >= limit:
                    break
                _add(r["value"], r["field"])
        except sqlite3.OperationalError:
            logger.debug("Suggest query failed", exc_info=True)

    return suggestions[:limit]
