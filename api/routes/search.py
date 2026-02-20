"""
GET /api/v1/search endpoint (Step 2.C3-a).

Reuses FTS5 MATCH logic from search_budget.py.  Returns unified results with
optional snippet highlighting for both budget lines and PDF pages.

SEARCH-001: BM25 relevance scoring via FTS5 rank function.
SEARCH-002: Structured filter support (fiscal_year, service, exhibit_type).
SEARCH-003: HTML highlighting with <mark> tags in snippets.
SEARCH-004: Search suggestions/autocomplete endpoint.
"""

import html as _html
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from api.database import get_db
from api.models import SearchResponse, SearchResultItem
from utils import sanitize_fts5_query
from utils.formatting import extract_snippet_highlighted
from utils.query import build_where_clause

router = APIRouter(prefix="/search", tags=["search"])


def _snippet(text: str | None, query: str | None, max_len: int = 200) -> str | None:
    """Extract snippet from text around first matching term.

    OPT-FMT-002: Delegates to shared extract_snippet_highlighted() in utils/formatting.
    Kept here for backward compatibility with existing tests.
    """
    if not text or not query:
        return None
    return extract_snippet_highlighted(text, query, max_len=max_len, html=False)


# ── SEARCH-001: BM25-ranked budget lines query ───────────────────────────────
# Use FTS5 bm25() function for relevance scoring.
# sort=relevance orders by BM25 score (lower magnitude = better rank).
# sort=amount_desc orders by the current FY request amount.

def _budget_select(
    fts_query: str,
    sort: str,
    fiscal_year: list[str] | None,
    service: list[str] | None,
    exhibit_type: list[str] | None,
    limit: int,
    offset: int,
) -> tuple[str, list[Any]]:
    """Build the budget lines search query with BM25 scoring."""
    # SEARCH-002: Build structured WHERE clause
    where, params = build_where_clause(
        fiscal_year=fiscal_year,
        service=service,
        exhibit_type=exhibit_type,
    )

    # Combine FTS MATCH with structured filters via subquery
    fts_subquery = (
        "SELECT rowid, bm25(budget_lines_fts) AS score "
        "FROM budget_lines_fts "
        "WHERE budget_lines_fts MATCH ?"
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
) -> tuple[str, list[Any]]:
    """Build the PDF pages search query with BM25 scoring via subquery JOIN.

    LION-100: Supports fiscal_year and exhibit_type filtering on pdf_pages
    columns added during LION-100 schema update.
    """
    conditions: list[str] = []
    params: list[Any] = [fts_query]

    if fiscal_year:
        placeholders = ",".join("?" * len(fiscal_year))
        conditions.append(f"p.fiscal_year IN ({placeholders})")
        params.extend(fiscal_year)
    if exhibit_type:
        placeholders = ",".join("?" * len(exhibit_type))
        conditions.append(f"p.exhibit_type IN ({placeholders})")
        params.extend(exhibit_type)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    sql = f"""
        SELECT p.id, p.source_file, p.source_category, p.page_number,
               p.page_text, p.has_tables, p.fiscal_year, p.exhibit_type,
               fts.score
        FROM pdf_pages p
        JOIN (
            SELECT rowid, bm25(pdf_pages_fts) AS score
            FROM pdf_pages_fts
            WHERE pdf_pages_fts MATCH ?
        ) fts ON p.id = fts.rowid
        {where}
        ORDER BY fts.score ASC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])
    return sql, params


@router.get(
    "",
    response_model=SearchResponse,
    summary="Full-text search",
    responses={
        400: {"description": "Invalid search parameters", "content": {"application/json": {"example": {"error": "Bad request", "detail": "Invalid sort parameter", "status_code": 400}}}},
        422: {"description": "Validation error", "content": {"application/json": {"example": {"error": "Validation error", "detail": "q: ensure this value has at least 1 characters", "status_code": 422}}}},
        429: {"description": "Rate limit exceeded", "content": {"application/json": {"example": {"error": "Too many requests", "status_code": 429}}}},
    },
)
def search(
    q: str = Query(..., min_length=1, description="Search query string"),
    type: str = Query(
        "both",
        description="Result type: 'both', 'excel', or 'pdf'",
        pattern="^(both|excel|pdf)$",
    ),
    sort: str = Query(
        "relevance",
        description="Sort order: 'relevance' (BM25) or 'amount_desc'",
        pattern="^(relevance|amount_desc)$",
    ),
    # SEARCH-002: structured filters
    fiscal_year: list[str] | None = Query(None, description="Filter by fiscal year(s)"),
    service: list[str] | None = Query(None, description="Filter by service/org name"),
    exhibit_type: list[str] | None = Query(None, description="Filter by exhibit type(s)"),
    limit: int = Query(20, ge=1, le=100, description="Max results per type"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    conn: sqlite3.Connection = Depends(get_db),
) -> SearchResponse:
    """Search budget line items and/or PDF page content with FTS5.

    Results are ranked by BM25 relevance by default (SEARCH-001).
    Snippets include HTML <mark> highlighting (SEARCH-003).
    """
    # Guard against FastAPI FieldInfo defaults when called directly from tests
    if not isinstance(fiscal_year, list):
        fiscal_year = None
    if not isinstance(service, list):
        service = None
    if not isinstance(exhibit_type, list):
        exhibit_type = None

    fts_query = sanitize_fts5_query(q)
    if not fts_query:
        raise HTTPException(status_code=400, detail="Query contains no searchable terms")

    results: list[SearchResultItem] = []

    if type in ("both", "excel"):
        try:
            sql, params = _budget_select(
                fts_query=fts_query,
                sort=sort,
                fiscal_year=fiscal_year,
                service=service,
                exhibit_type=exhibit_type,
                limit=limit,
                offset=offset,
            )
            rows = conn.execute(sql, params).fetchall()
        except Exception:
            rows = []
        for row in rows:
            d = dict(row)
            score = d.pop("score", None)
            # SEARCH-003: HTML-highlighted snippet
            snippet = extract_snippet_highlighted(
                d.get("line_item_title") or d.get("account_title"),
                q,
                html=True,
            )
            results.append(SearchResultItem(
                result_type="budget_line",
                id=d["id"],
                source_file=d["source_file"],
                snippet=snippet,
                score=score,
                data=d,
            ))

    if type in ("both", "pdf"):
        try:
            sql, params = _pdf_select(
                fts_query, fiscal_year, exhibit_type, limit, offset
            )
            rows = conn.execute(sql, params).fetchall()
        except Exception:
            rows = []
        for row in rows:
            d = dict(row)
            score = d.pop("score", None)
            snippet = extract_snippet_highlighted(d.get("page_text"), q, html=True)
            results.append(SearchResultItem(
                result_type="pdf_page",
                id=d["id"],
                source_file=d["source_file"],
                snippet=snippet,
                score=score,
                data=d,
            ))

    return SearchResponse(
        query=q,
        total=len(results),
        limit=limit,
        offset=offset,
        results=results,
    )


# ── SEARCH-004: Search suggestions / autocomplete ────────────────────────────

@router.get(
    "/suggest",
    summary="Search suggestions/autocomplete",
    response_model=list[dict],
)
def suggest(
    q: str = Query(..., min_length=1, description="Prefix to complete"),
    limit: int = Query(5, ge=1, le=20, description="Max suggestions"),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[dict]:
    """Return search suggestions for typeahead UI.

    Queries DISTINCT line_item_title, account_title, and pe_number for
    values that start with (or contain) the given prefix.
    """
    prefix = q.strip()
    if not prefix:
        return []

    like_param = f"{prefix}%"
    suggestions: list[dict] = []

    # Try line_item_title first
    try:
        rows = conn.execute(
            "SELECT DISTINCT line_item_title AS value, 'line_item_title' AS field "
            "FROM budget_lines "
            "WHERE line_item_title LIKE ? AND line_item_title IS NOT NULL "
            "LIMIT ?",
            (like_param, limit),
        ).fetchall()
        suggestions.extend({"value": r["value"], "field": r["field"]} for r in rows)
    except Exception:
        pass

    if len(suggestions) < limit:
        try:
            rows = conn.execute(
                "SELECT DISTINCT account_title AS value, 'account_title' AS field "
                "FROM budget_lines "
                "WHERE account_title LIKE ? AND account_title IS NOT NULL "
                "LIMIT ?",
                (like_param, limit - len(suggestions)),
            ).fetchall()
            suggestions.extend({"value": r["value"], "field": r["field"]} for r in rows)
        except Exception:
            pass

    if len(suggestions) < limit:
        try:
            rows = conn.execute(
                "SELECT DISTINCT pe_number AS value, 'pe_number' AS field "
                "FROM budget_lines "
                "WHERE pe_number LIKE ? AND pe_number IS NOT NULL "
                "LIMIT ?",
                (like_param, limit - len(suggestions)),
            ).fetchall()
            suggestions.extend({"value": r["value"], "field": r["field"]} for r in rows)
        except Exception:
            pass

    return suggestions[:limit]
