"""
GET /api/v1/download endpoint (Step 2.C4-a).

Streams large result sets as CSV or JSON without loading everything into memory.
Accepts the same filter parameters as /budget-lines.

──────────────────────────────────────────────────────────────────────────────
TODOs for this file
──────────────────────────────────────────────────────────────────────────────

TODO 3.A5-b / DL-001 [Group: TIGER] [Complexity: MEDIUM] [Tokens: ~2500] [User: NO]
    Add Excel (.xlsx) export format.
    The wireframe (docs/UI_WIREFRAMES.md section 4) shows Excel as a download
    option. Steps:
      1. Add fmt=xlsx to the Query() pattern: "^(csv|json|xlsx)$"
      2. Use openpyxl (already a dependency) to create an in-memory workbook
      3. Write headers and stream rows in batches using openpyxl's
         write_only mode for memory efficiency
      4. Return as StreamingResponse with Content-Type
         application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
      5. Add Content-Disposition with .xlsx filename
    Acceptance: /api/v1/download?fmt=xlsx returns valid Excel workbook.

TODO OPT-DL-001 [Group: TIGER] [Complexity: MEDIUM] [Tokens: ~2000] [User: NO]
    DRY: Replace inline WHERE clause builder with shared utility.
    This file builds its own WHERE clause (lines 61-81) identical to the one
    in budget_lines.py. Steps:
      1. Import build_where_clause from utils/query.py (see OPT-FE-001)
      2. Replace inline conditions/params construction with the shared function
      3. Add keyword search (q) filter support to downloads
    Acceptance: Download uses same WHERE builder as budget-lines; tests pass.

TODO DL-002 [Group: TIGER] [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Add keyword search filter to downloads.
    Currently downloads only support structured filters (FY, service, etc.)
    but not free-text search. The wireframe shows downloads apply ALL current
    filters including search text. Steps:
      1. Add q: str = Query(None) parameter to the download endpoint
      2. If q is provided, join with budget_lines_fts via MATCH
      3. Test with combined filters + search term
    Acceptance: /api/v1/download?q=missile&fmt=csv returns FTS-filtered results.

TODO DL-003 [Group: TIGER] [Complexity: LOW] [Tokens: ~1000] [User: NO]
    Add export row count header for client progress tracking.
    Steps:
      1. Before streaming, COUNT(*) the filtered result set
      2. Add X-Total-Count header to the StreamingResponse
      3. Frontend can use this to show download progress percentage
    Acceptance: Response includes X-Total-Count header with row count.
"""

import csv
import io
import json
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from api.database import get_db

router = APIRouter(prefix="/download", tags=["download"])

_DOWNLOAD_COLUMNS = [
    "id", "source_file", "exhibit_type", "sheet_name", "fiscal_year",
    "account", "account_title", "organization_name",
    "budget_activity_title", "sub_activity_title",
    "line_item", "line_item_title", "pe_number",
    "appropriation_code", "appropriation_title",
    "amount_fy2024_actual", "amount_fy2025_enacted", "amount_fy2025_supplemental",
    "amount_fy2025_total", "amount_fy2026_request", "amount_fy2026_reconciliation",
    "amount_fy2026_total", "amount_type", "amount_unit", "currency_year",
]

_ALLOWED_SORT = {"id", "source_file", "exhibit_type", "fiscal_year",
                 "organization_name", "amount_fy2026_request"}


def _iter_rows(conn: sqlite3.Connection, sql: str, params: list[Any]):
    """Yield rows one at a time to enable streaming."""
    cur = conn.execute(sql, params)
    while True:
        batch = cur.fetchmany(500)
        if not batch:
            break
        yield from batch


@router.get("", summary="Download search results as CSV or JSON")
def download(
    fmt: str = Query("csv", pattern="^(csv|json)$", description="Output format"),
    fiscal_year: list[str] | None = Query(None),
    service: list[str] | None = Query(None),
    exhibit_type: list[str] | None = Query(None),
    pe_number: list[str] | None = Query(None),
    limit: int = Query(
        10_000, ge=1, le=100_000,
        description="Max rows to export (default 10,000)",
    ),
    conn: sqlite3.Connection = Depends(get_db),
) -> StreamingResponse:
    """Stream budget line items as CSV or JSON (newline-delimited)."""
    # Build WHERE clause
    conditions: list[str] = []
    params: list[Any] = []

    if fiscal_year:
        ph = ",".join("?" * len(fiscal_year))
        conditions.append(f"fiscal_year IN ({ph})")
        params.extend(fiscal_year)
    if service:
        sub = " OR ".join("organization_name LIKE ?" for _ in service)
        conditions.append(f"({sub})")
        params.extend(f"%{s}%" for s in service)
    if exhibit_type:
        ph = ",".join("?" * len(exhibit_type))
        conditions.append(f"exhibit_type IN ({ph})")
        params.extend(exhibit_type)
    if pe_number:
        ph = ",".join("?" * len(pe_number))
        conditions.append(f"pe_number IN ({ph})")
        params.extend(pe_number)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    col_list = ", ".join(_DOWNLOAD_COLUMNS)
    sql = f"SELECT {col_list} FROM budget_lines {where} LIMIT {limit}"

    if fmt == "csv":
        def csv_stream():
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=_DOWNLOAD_COLUMNS)
            writer.writeheader()
            yield buf.getvalue()
            for row in _iter_rows(conn, sql, params):
                buf.seek(0)
                buf.truncate()
                writer.writerow(dict(zip(_DOWNLOAD_COLUMNS, row)))
                yield buf.getvalue()

        return StreamingResponse(
            csv_stream(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=budget_lines.csv"},
        )

    # JSON newline-delimited (NDJSON)
    def json_stream():
        for row in _iter_rows(conn, sql, params):
            d = dict(zip(_DOWNLOAD_COLUMNS, row))
            yield json.dumps(d, default=str) + "\n"

    return StreamingResponse(
        json_stream(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": "attachment; filename=budget_lines.ndjson"
        },
    )
