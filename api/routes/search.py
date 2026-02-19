"""
GET /api/v1/search endpoint (Step 2.C3-a).

Reuses FTS5 MATCH logic from search_budget.py.  Returns unified results with
optional snippet highlighting for both budget lines and PDF pages.

──────────────────────────────────────────────────────────────────────────────
TODOs for this file
──────────────────────────────────────────────────────────────────────────────

TODO SEARCH-001 [Group: TIGER] [Complexity: MEDIUM] [Tokens: ~2500] [User: NO]
    Add BM25 relevance scoring to search results.
    Currently results are ordered by amount (DESC) rather than relevance.
    FTS5 supports bm25() for ranking. Steps:
      1. Use FTS5 rank function: SELECT *, bm25(budget_lines_fts) AS score
      2. Add sort parameter: relevance (default), amount_desc, fiscal_year
      3. Return score field in SearchResultItem
      4. Update _BUDGET_SELECT and _PDF_SELECT to include rank
    Acceptance: Search results ranked by relevance; score field populated.

TODO SEARCH-002 [Group: TIGER] [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Add structured filter support to search endpoint.
    Currently search only accepts a text query and type filter. Add support
    for fiscal_year, service, and exhibit_type filters (same as budget-lines).
    Steps:
      1. Add fiscal_year, service, exhibit_type Query parameters
      2. Build WHERE clause filtering (similar to budget_lines.py)
      3. Combine FTS MATCH with structured filters via subquery or JOIN
    Acceptance: /api/v1/search?q=missile&service=Navy returns Navy results only.

TODO SEARCH-003 [Group: TIGER] [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Improve snippet generation with HTML highlighting.
    Currently _snippet() extracts text but doesn't highlight matching terms.
    Steps:
      1. After extracting the snippet, wrap matching terms in <mark> tags
      2. Ensure the text is HTML-escaped first (prevent XSS), then apply marks
      3. Return highlighted snippet for use in both API and frontend
      4. Use utils/formatting.py highlight_terms() which already exists
    Acceptance: Snippets have matching terms wrapped in <mark> tags.

TODO SEARCH-004 [Group: TIGER] [Complexity: MEDIUM] [Tokens: ~2000] [User: NO]
    Add search suggestions / autocomplete endpoint.
    Steps:
      1. Add GET /api/v1/search/suggest?q=miss&limit=5 endpoint
      2. Query DISTINCT line_item_title, account_title, pe_number
         WHERE column LIKE 'miss%' LIMIT 5
      3. Return compact suggestion list for typeahead UI
      4. Wire into frontend with HTMX hx-trigger="keyup changed delay:200ms"
    Acceptance: Typing in search shows dropdown suggestions from the data.
"""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from api.database import get_db
from api.models import SearchResponse, SearchResultItem

# Reuse the sanitizer from the CLI search module
from utils import sanitize_fts5_query

router = APIRouter(prefix="/search", tags=["search"])

_BUDGET_SELECT = """
    SELECT id, source_file, exhibit_type, sheet_name, fiscal_year,
           account, account_title, organization_name,
           budget_activity_title, sub_activity_title,
           line_item, line_item_title,
           amount_fy2024_actual, amount_fy2025_enacted,
           amount_fy2026_request, amount_fy2026_total,
           pe_number, amount_type
    FROM budget_lines
    WHERE id IN (
        SELECT rowid FROM budget_lines_fts
        WHERE budget_lines_fts MATCH ?
    )
    ORDER BY COALESCE(amount_fy2026_request, amount_fy2025_enacted, 0) DESC
    LIMIT ? OFFSET ?
"""

_PDF_SELECT = """
    SELECT id, source_file, source_category, page_number,
           page_text, has_tables
    FROM pdf_pages
    WHERE id IN (
        SELECT rowid FROM pdf_pages_fts
        WHERE pdf_pages_fts MATCH ?
    )
    LIMIT ? OFFSET ?
"""


def _snippet(text: str | None, query: str, max_len: int = 200) -> str | None:
    """Extract a snippet from text around the first matching query term."""
    if not text or not query:
        return None
    text_lower = text.lower()
    terms = query.lower().split()
    best = len(text)
    for term in terms:
        pos = text_lower.find(term)
        if 0 <= pos < best:
            best = pos
    if best == len(text):
        return text[:max_len]
    start = max(0, best - 80)
    end = min(len(text), start + max_len)
    chunk = text[start:end].strip()
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return prefix + chunk + suffix


@router.get("", response_model=SearchResponse, summary="Full-text search")
def search(
    q: str = Query(..., min_length=1, description="Search query string"),
    type: str = Query(
        "both",
        description="Result type: 'both', 'excel', or 'pdf'",
        pattern="^(both|excel|pdf)$",
    ),
    limit: int = Query(20, ge=1, le=100, description="Max results per type"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    conn: sqlite3.Connection = Depends(get_db),
) -> SearchResponse:
    """Search budget line items and/or PDF page content with FTS5."""
    fts_query = sanitize_fts5_query(q)
    if not fts_query:
        raise HTTPException(status_code=400, detail="Query contains no searchable terms")

    results: list[SearchResultItem] = []

    if type in ("both", "excel"):
        try:
            rows = conn.execute(_BUDGET_SELECT, (fts_query, limit, offset)).fetchall()
        except Exception:
            rows = []
        for row in rows:
            d = dict(row)
            results.append(SearchResultItem(
                result_type="budget_line",
                id=d["id"],
                source_file=d["source_file"],
                snippet=_snippet(d.get("line_item_title") or d.get("account_title"), q),
                data=d,
            ))

    if type in ("both", "pdf"):
        try:
            rows = conn.execute(_PDF_SELECT, (fts_query, limit, offset)).fetchall()
        except Exception:
            rows = []
        for row in rows:
            d = dict(row)
            results.append(SearchResultItem(
                result_type="pdf_page",
                id=d["id"],
                source_file=d["source_file"],
                snippet=_snippet(d.get("page_text"), q),
                data=d,
            ))

    return SearchResponse(
        query=q,
        total=len(results),
        limit=limit,
        offset=offset,
        results=results,
    )
