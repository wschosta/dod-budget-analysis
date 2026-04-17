"""BLI-centric API endpoints.

Budget Line Items (BLIs) identify specific procurement items (P-1 / P-1R
exhibits).  They are the procurement-side analogue to PEs — but until now
there's been no way to fetch a BLI directly by its natural key.

This module exposes the minimal surface needed so the ``related_pes``
field on budget-line detail responses (and on the corresponding frontend
partial) actually has somewhere to link *back to* for BLIs.
"""

from __future__ import annotations

import logging
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from api.database import get_db
from utils.query import fetch_bli_related_pes, parse_json_list

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bli", tags=["bli"])


@router.get(
    "/{bli_key:path}",
    summary="BLI detail by composite key",
)
def get_bli(
    bli_key: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return a BLI's index entry, tags, PE mappings, and description snippets.

    ``bli_key`` is the same composite identifier used elsewhere in the
    codebase: ``{account}:{line_item}`` (e.g. ``1506N:0577``).  The colon
    means we rely on FastAPI's ``:path`` converter so forward slashes and
    colons pass through the URL intact.
    """
    try:
        idx = conn.execute(
            "SELECT bli_key, account, line_item, display_title, organization_name, "
            "       budget_type, budget_activity_title, appropriation_code, "
            "       appropriation_title, fiscal_years, exhibit_types, row_count "
            "FROM bli_index WHERE bli_key = ?",
            (bli_key,),
        ).fetchone()
    except sqlite3.OperationalError:
        raise HTTPException(
            status_code=503,
            detail="bli_index table not found — run enrichment Phase 7.",
        ) from None

    if idx is None:
        raise HTTPException(status_code=404, detail=f"BLI {bli_key} not found")

    data = dict(idx)
    data["fiscal_years"] = parse_json_list(data.get("fiscal_years"))
    data["exhibit_types"] = parse_json_list(data.get("exhibit_types"))

    # Tags (optional table — may not exist on partially-enriched DBs).
    try:
        tag_rows = conn.execute(
            "SELECT tag, tag_source, confidence FROM bli_tags "
            "WHERE bli_key = ? ORDER BY confidence DESC, tag",
            (bli_key,),
        ).fetchall()
        data["tags"] = [dict(r) for r in tag_rows]
    except sqlite3.OperationalError:
        data["tags"] = []

    # PE cross-references (Phase 11).
    data["related_pes"] = fetch_bli_related_pes(conn, bli_key)

    # Description snippets — return first 200 chars per row to keep response
    # small; full text is available via /api/v1/search?source=descriptions.
    try:
        desc_rows = conn.execute(
            "SELECT fiscal_year, source_file, page_start, page_end, section_header, "
            "       substr(description_text, 1, 200) AS snippet "
            "FROM bli_descriptions WHERE bli_key = ? "
            "ORDER BY fiscal_year DESC, page_start",
            (bli_key,),
        ).fetchall()
        data["descriptions"] = [dict(r) for r in desc_rows]
    except sqlite3.OperationalError:
        data["descriptions"] = []

    return data
