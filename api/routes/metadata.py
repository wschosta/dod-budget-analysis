"""GET /api/v1/metadata endpoint (HAWK-5).

Returns summary metadata about the DoD budget database including table counts,
fiscal year ranges, available services, exhibit types, and enrichment coverage.

Useful for:
  - GUI dashboard overview panels
  - Health monitoring and completeness checks
  - Client-side filter option population
"""

import sqlite3

from fastapi import APIRouter, Depends

from api.database import get_db
from utils.metadata import collect_metadata

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
