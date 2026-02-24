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
from typing import Any

from fastapi import APIRouter, Depends

from api.database import get_db
from utils.metadata import collect_metadata

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metadata", tags=["metadata"])


def _safe_scalar(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> Any:
    """Execute a scalar query, returning None if the table doesn't exist."""
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else None
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        return None


def _collect_timestamps(conn: sqlite3.Connection) -> dict:
    """Collect last-build and last-enrichment timestamps plus key counts.

    Returns a dict with:
        - last_build_time: Most recent ingestion timestamp
        - last_enrichment_time: Most recent enrichment timestamp
        - total_budget_lines: Row count of budget_lines table
        - total_pe_count: Row count of pe_index table
        - total_pdf_pages: Row count of pdf_pages table

    Each query is wrapped in try/except so missing tables return None.
    """
    result: dict[str, Any] = {}

    # last_build_time: prefer data_changelog, fall back to ingested_files
    last_build = _safe_scalar(
        conn,
        "SELECT MAX(timestamp) FROM data_changelog "
        "WHERE action IN ('insert', 'refresh')",
    )
    if not last_build:
        last_build = _safe_scalar(
            conn, "SELECT MAX(ingested_at) FROM ingested_files"
        )
    if not last_build:
        last_build = _safe_scalar(
            conn, "SELECT MAX(updated_at) FROM ingested_files"
        )
    result["last_build_time"] = last_build

    # last_enrichment_time: prefer data_changelog, fall back to pe_index.updated_at
    last_enrich = _safe_scalar(
        conn,
        "SELECT MAX(timestamp) FROM data_changelog WHERE action = 'enrich'",
    )
    if not last_enrich:
        last_enrich = _safe_scalar(
            conn, "SELECT MAX(updated_at) FROM pe_index"
        )
    result["last_enrichment_time"] = last_enrich

    # Key counts
    result["total_budget_lines"] = _safe_scalar(
        conn, "SELECT COUNT(*) FROM budget_lines"
    ) or 0
    result["total_pe_count"] = _safe_scalar(
        conn, "SELECT COUNT(*) FROM pe_index"
    ) or 0
    result["total_pdf_pages"] = _safe_scalar(
        conn, "SELECT COUNT(*) FROM pdf_pages"
    ) or 0

    return result


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
    enrichment coverage statistics, amount summaries, and timestamp information.
    """
    meta = collect_metadata(conn)
    meta.update(_collect_timestamps(conn))
    return meta


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
