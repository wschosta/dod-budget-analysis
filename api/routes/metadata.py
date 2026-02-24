"""GET /api/v1/metadata endpoint (HAWK-5).

Returns summary metadata about the DoD budget database including table counts,
fiscal year ranges, available services, exhibit types, and enrichment coverage.

Useful for:
  - GUI dashboard overview panels
  - Health monitoring and completeness checks
  - Client-side filter option population
"""

import logging
import sqlite3

from fastapi import APIRouter, Depends

from api.database import get_db
from utils.metadata import collect_metadata

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metadata", tags=["metadata"])


@router.get(
    "",
    summary="Database metadata and coverage statistics",
    response_description="Summary metadata about the budget database",
)
def get_metadata(
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return comprehensive metadata about the budget database.

    Includes table row counts, distinct fiscal years, services, exhibit types,
    enrichment coverage statistics, and amount summaries.
    """
    return collect_metadata(conn)


def _safe_count(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    """Execute a COUNT query, returning 0 if the table doesn't exist."""
    try:
        return conn.execute(sql, params).fetchone()[0]
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return 0


@router.get(
    "/enrichment",
    summary="Enrichment coverage statistics",
    response_description="Counts and coverage metrics for all enrichment tables",
)
def get_enrichment_metadata(
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return enrichment-specific coverage statistics.

    Provides counts for each enrichment table and coverage metrics showing
    how many PEs have descriptions, tags, and lineage data. Handles missing
    tables gracefully (returns 0 for missing tables).
    """
    pe_count = _safe_count(conn, "SELECT COUNT(*) FROM pe_index")
    pe_with_descriptions = _safe_count(
        conn, "SELECT COUNT(DISTINCT pe_number) FROM pe_descriptions"
    )
    pe_with_tags = _safe_count(
        conn, "SELECT COUNT(DISTINCT pe_number) FROM pe_tags"
    )
    pe_with_lineage = _safe_count(
        conn, "SELECT COUNT(DISTINCT source_pe) FROM pe_lineage"
    )
    total_tags = _safe_count(conn, "SELECT COUNT(*) FROM pe_tags")
    total_descriptions = _safe_count(conn, "SELECT COUNT(*) FROM pe_descriptions")
    total_lineage = _safe_count(conn, "SELECT COUNT(*) FROM pe_lineage")
    total_projects = _safe_count(conn, "SELECT COUNT(*) FROM project_descriptions")

    # Last enrichment timestamp from pe_index.updated_at
    last_enrichment = None
    try:
        row = conn.execute(
            "SELECT MAX(updated_at) FROM pe_index"
        ).fetchone()
        if row and row[0]:
            last_enrichment = row[0]
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass

    # Tag source breakdown
    tag_sources: dict[str, int] = {}
    try:
        rows = conn.execute(
            "SELECT tag_source, COUNT(*) AS cnt FROM pe_tags GROUP BY tag_source ORDER BY cnt DESC"
        ).fetchall()
        tag_sources = {r[0]: r[1] for r in rows}
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass

    return {
        "enrichment": {
            "pe_count": pe_count,
            "pe_with_descriptions": pe_with_descriptions,
            "pe_with_tags": pe_with_tags,
            "pe_with_lineage": pe_with_lineage,
            "total_tags": total_tags,
            "total_descriptions": total_descriptions,
            "total_lineage": total_lineage,
            "total_projects": total_projects,
            "tag_sources": tag_sources,
            "last_enrichment": last_enrichment,
        }
    }
