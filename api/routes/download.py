"""
GET /api/v1/download endpoint (Step 2.C4-a).

Streams large result sets as CSV, JSON, or Excel without loading everything
into memory. Accepts the same filter parameters as /budget-lines.

DL-001: Excel (.xlsx) export via openpyxl write_only mode.
DL-002: Keyword search filter (q) for FTS-filtered downloads.
DL-003: X-Total-Count header for client progress tracking.
OPT-DL-001: Uses shared WHERE builder from utils/query.py.
"""

import csv
import io
import json
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from api.database import get_db
from utils import sanitize_fts5_query
from utils.query import build_where_clause

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


def _build_download_sql(
    fiscal_year: list[str] | None,
    service: list[str] | None,
    exhibit_type: list[str] | None,
    pe_number: list[str] | None,
    q: str | None,
    conn: sqlite3.Connection,
    limit: int,
) -> tuple[str, list[Any], int]:
    """Build the download SQL with all filters applied.

    Returns:
        (sql, params, total_count)
    """
    # DL-002: Handle FTS keyword filter
    fts_ids: list[int] | None = None
    if q and q.strip():
        try:
            safe_q = sanitize_fts5_query(q.strip())
            fts_rows = conn.execute(
                "SELECT rowid FROM budget_lines_fts WHERE budget_lines_fts MATCH ?",
                (safe_q,),
            ).fetchall()
            fts_ids = [r[0] for r in fts_rows]
        except Exception:
            fts_ids = []

    # OPT-DL-001: Use shared WHERE builder
    where, params = build_where_clause(
        fiscal_year=fiscal_year,
        service=service,
        exhibit_type=exhibit_type,
        pe_number=pe_number,
        fts_ids=fts_ids,
    )

    # DL-003: Count first for X-Total-Count header
    count_sql = f"SELECT COUNT(*) FROM budget_lines {where}"
    total = conn.execute(count_sql, params).fetchone()[0]

    col_list = ", ".join(_DOWNLOAD_COLUMNS)
    sql = f"SELECT {col_list} FROM budget_lines {where} LIMIT {limit}"

    return sql, params, total


@router.get("", summary="Download search results as CSV, JSON, or Excel")
def download(
    fmt: str = Query("csv", pattern="^(csv|json|xlsx)$", description="Output format"),
    fiscal_year: list[str] | None = Query(None),
    service: list[str] | None = Query(None),
    exhibit_type: list[str] | None = Query(None),
    pe_number: list[str] | None = Query(None),
    # DL-002: keyword search filter
    q: str | None = Query(None, description="Keyword search filter (FTS5)"),
    limit: int = Query(
        10_000, ge=1, le=100_000,
        description="Max rows to export (default 10,000)",
    ),
    conn: sqlite3.Connection = Depends(get_db),
) -> StreamingResponse:
    """Stream budget line items as CSV, JSON (newline-delimited), or Excel."""
    sql, params, total_count = _build_download_sql(
        fiscal_year=fiscal_year,
        service=service,
        exhibit_type=exhibit_type,
        pe_number=pe_number,
        q=q,
        conn=conn,
        limit=limit,
    )

    # DL-003: X-Total-Count header
    extra_headers: dict[str, str] = {"X-Total-Count": str(total_count)}

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
            headers={
                "Content-Disposition": "attachment; filename=budget_lines.csv",
                **extra_headers,
            },
        )

    if fmt == "xlsx":
        # DL-001: Excel export using openpyxl write_only mode
        def xlsx_stream():
            import openpyxl
            from openpyxl.writer.excel import save_virtual_workbook

            wb = openpyxl.Workbook(write_only=True)
            ws = wb.create_sheet("Budget Lines")
            ws.append(_DOWNLOAD_COLUMNS)
            for row in _iter_rows(conn, sql, params):
                ws.append(list(row))
            # save_virtual_workbook returns bytes for streaming
            yield save_virtual_workbook(wb)

        return StreamingResponse(
            xlsx_stream(),
            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
            headers={
                "Content-Disposition": "attachment; filename=budget_lines.xlsx",
                **extra_headers,
            },
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
            "Content-Disposition": "attachment; filename=budget_lines.ndjson",
            **extra_headers,
        },
    )
