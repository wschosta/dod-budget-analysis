"""Shared SQL query builder utilities for DoD Budget API routes.

Provides DRY WHERE clause and ORDER BY construction used by budget_lines.py,
frontend.py, and download.py.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from utils.config import CORE_SUMMARY_TYPES
from utils.database import _validate_identifier, get_amount_columns


ALLOWED_SORT_COLUMNS = {
    "id", "source_file", "exhibit_type", "fiscal_year",
    "organization_name", "account", "account_title", "pe_number",
    "amount_fy2026_request", "amount_fy2025_enacted", "amount_fy2024_actual",
}

# Pattern for valid amount column names (amount_fyYYYY_type)
_AMOUNT_COL_RE = re.compile(r"^amount_fy\d{4}_[a-z]+$")

# Fallback labels used when DB introspection isn't available.
# The frontend dynamically discovers columns via get_amount_columns() at runtime.
FISCAL_YEAR_COLUMN_LABELS = [
    {"column": "amount_fy2024_actual", "label": "FY2024 Actual"},
    {"column": "amount_fy2025_enacted", "label": "FY2025 Enacted"},
    {"column": "amount_fy2025_total", "label": "FY2025 Total"},
    {"column": "amount_fy2026_request", "label": "FY2026 Request"},
    {"column": "amount_fy2026_total", "label": "FY2026 Total"},
]

DEFAULT_AMOUNT_COLUMN = "amount_fy2026_request"


def amount_col_to_label(col: str) -> str:
    """Convert an amount column name to a human-readable label.

    Example: 'amount_fy2024_actual' → 'FY2024 Actual'
    """
    label = col.replace("amount_fy", "FY")
    for suffix, replacement in [
        ("_actual", " Actual"), ("_enacted", " Enacted"),
        ("_request", " Request"), ("_total", " Total"),
        ("_supplemental", " Supplemental"), ("_reconciliation", " Reconciliation"),
    ]:
        label = label.replace(suffix, replacement)
    return label


def make_fiscal_year_column_labels(columns: list[str]) -> list[dict[str, str]]:
    """Build the column-label list from discovered amount columns."""
    return [{"column": c, "label": amount_col_to_label(c)} for c in sorted(columns)]


def validate_amount_column(column: str | None) -> str:
    """Validate and return an amount column name, defaulting to FY2026 request.

    Accepts any column matching the ``amount_fy{YYYY}_{type}`` pattern
    to support databases with arbitrary fiscal year data.

    Args:
        column: Column name to validate. None returns the default.

    Returns:
        A safe amount column name.

    Raises:
        ValueError: If the column name doesn't match the expected pattern.
    """
    if column is None:
        return DEFAULT_AMOUNT_COLUMN
    if not _AMOUNT_COL_RE.match(column):
        raise ValueError(
            f"Invalid amount column: '{column}'. "
            f"Must match pattern amount_fyYYYY_type (e.g. amount_fy2026_request)."
        )
    return column


def _add_in_condition(
    conditions: list[str],
    params: list[Any],
    column: str,
    values: list[Any] | None,
) -> None:
    """Append an ``IN (?, ?, ...)`` condition if *values* is non-empty.

    Mutates *conditions* and *params* in place.  Does nothing when *values*
    is ``None`` or empty.
    """
    if not values:
        return
    placeholders = ",".join("?" * len(values))
    conditions.append(f"{column} IN ({placeholders})")
    params.extend(values)


def build_where_clause(
    fiscal_year: list[str] | None = None,
    service: list[str] | None = None,
    exhibit_type: list[str] | None = None,
    pe_number: list[str] | None = None,
    appropriation_code: list[str] | None = None,
    budget_type: list[str] | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    q: str | None = None,
    fts_ids: list[int] | None = None,
    amount_column: str | None = None,
    exclude_summary: bool = False,
    extra_conditions: list[str] | None = None,
) -> tuple[str, list[Any]]:
    """Build a SQL WHERE clause from filter parameters.

    Args:
        fiscal_year: Filter by fiscal year(s).
        service: Filter by service/organization name (LIKE match).
        exhibit_type: Filter by exhibit type(s).
        pe_number: Filter by PE number(s).
        appropriation_code: Filter by appropriation code(s).
        budget_type: Filter by budget type(s) (e.g. RDT&E, Procurement).
        min_amount: Minimum amount value (applied to amount_column).
        max_amount: Maximum amount value (applied to amount_column).
        q: Free-text search (unused here — caller should use fts_ids).
        fts_ids: Row IDs from FTS MATCH query to restrict results.
        amount_column: Which FY amount column to filter on.
            Must be in VALID_AMOUNT_COLUMNS. Defaults to amount_fy2026_request.
        exclude_summary: If True, exclude summary exhibit types (P-1, R-1,
            O-1, M-1, C-1, RF-1, P-1R) to avoid double-counting.
        extra_conditions: Additional raw SQL condition strings to include
            in the WHERE clause. These are ANDed with other conditions.

    Returns:
        Tuple of (where_clause_string, params_list). The where_clause_string
        starts with "WHERE " if any conditions exist, or is "" if none.
    """
    conditions: list[str] = []
    params: list[Any] = []

    if exclude_summary:
        conditions.append(EXCLUDE_SUMMARY_SQL)

    if extra_conditions:
        conditions.extend(extra_conditions)

    _add_in_condition(conditions, params, "fiscal_year", fiscal_year)
    # FIX-002b: exact IN() matching (LIKE was too broad).
    _add_in_condition(conditions, params, "organization_name", service)
    _add_in_condition(conditions, params, "exhibit_type", exhibit_type)
    _add_in_condition(conditions, params, "pe_number", pe_number)
    _add_in_condition(conditions, params, "appropriation_code", appropriation_code)
    _add_in_condition(conditions, params, "budget_type", budget_type)

    # EAGLE-1: Use dynamic amount column (validated against whitelist)
    amt_col = validate_amount_column(amount_column)

    if min_amount is not None:
        conditions.append(f"{amt_col} >= ?")
        params.append(min_amount)

    if max_amount is not None:
        conditions.append(f"{amt_col} <= ?")
        params.append(max_amount)

    if fts_ids is not None:
        if not fts_ids:
            # Empty FTS result → no rows match
            return "WHERE 1=0", []
        _add_in_condition(conditions, params, "id", fts_ids)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    return where, params


def build_order_clause(
    sort_by: str,
    sort_dir: str,
    allowed_sorts: set[str] | None = None,
    default_sort: str = "id",
) -> str:
    """Build a safe SQL ORDER BY clause.

    Args:
        sort_by: Column name to sort by.
        sort_dir: Direction: 'asc' or 'desc' (case-insensitive).
        allowed_sorts: Set of valid sort column names. Defaults to
            ALLOWED_SORT_COLUMNS if not provided.
        default_sort: Column to use if sort_by is not in allowed_sorts.

    Returns:
        ORDER BY clause string, e.g. "ORDER BY id ASC".
    """
    if allowed_sorts is None:
        allowed_sorts = ALLOWED_SORT_COLUMNS
    col = sort_by if sort_by in allowed_sorts else default_sort
    direction = "DESC" if sort_dir.lower() == "desc" else "ASC"
    return f"ORDER BY {col} {direction}"


# ---------------------------------------------------------------------------
# Shared FY column detection
# ---------------------------------------------------------------------------


def detect_fy_columns(
    conn: sqlite3.Connection,
    *,
    request_fy: str = "fy2026_request",
    baseline_fy: str = "fy2025_enacted",
) -> tuple[str, str]:
    """Detect the best FY request and baseline amount column names.

    Queries the database schema via :func:`utils.database.get_amount_columns`
    and returns validated column names for the requested and baseline fiscal
    years.  Falls back to the given defaults when no match is found.

    Args:
        conn: Open SQLite connection.
        request_fy: Substring to match for the "request" column
            (default ``"fy2026_request"``).
        baseline_fy: Substring to match for the "baseline" column
            (default ``"fy2025_enacted"``).

    Returns:
        ``(request_col, baseline_col)`` — validated column names safe for
        interpolation into SQL.
    """
    cols = get_amount_columns(conn)
    req_col = next(
        (c for c in cols if request_fy in c),
        f"amount_{request_fy}",
    )
    base_col = next(
        (c for c in cols if baseline_fy in c),
        f"amount_{baseline_fy}",
    )
    _validate_identifier(req_col, "column name")
    _validate_identifier(base_col, "column name")
    return req_col, base_col


# ---------------------------------------------------------------------------
# Shared YoY (year-over-year) calculation
# ---------------------------------------------------------------------------


def compute_yoy_change(
    current: float | None,
    previous: float | None,
) -> float | None:
    """Compute year-over-year percentage change.

    Returns ``None`` when *previous* is zero/``None`` or *current* is
    ``None``, avoiding division-by-zero.

    Example:
        >>> compute_yoy_change(120, 100)
        20.0
    """
    if current is None or not previous:
        return None
    return round((current - previous) / abs(previous) * 100, 2)


# ---------------------------------------------------------------------------
# Summary exhibit exclusion
# ---------------------------------------------------------------------------

#: Exhibit types that represent summary-level aggregations (p1, r1, etc.).
#: Queries that sum dollar amounts should exclude these to avoid double-counting
#: with the detail-level exhibits (p5, r2, etc.).
#: Derived from the canonical CORE_SUMMARY_TYPES in utils/config.py.
SUMMARY_EXHIBIT_TYPES: tuple[str, ...] = tuple(sorted(CORE_SUMMARY_TYPES))

#: Ready-to-interpolate SQL fragment for excluding summary exhibits.
EXCLUDE_SUMMARY_SQL = (
    "exhibit_type NOT IN ("
    + ",".join(f"'{e}'" for e in SUMMARY_EXHIBIT_TYPES)
    + ")"
)


# ---------------------------------------------------------------------------
# Placeholder / IN-clause helpers (public API)
# ---------------------------------------------------------------------------


def make_placeholders(values: list[Any] | int) -> str:
    """Return comma-separated ``?`` placeholders for a parameterised query.

    Accepts either an integer count or a list (whose length is used).

    Examples:
        >>> make_placeholders(3)
        '?,?,?'
        >>> make_placeholders(["a", "b"])
        '?,?'
    """
    n = values if isinstance(values, int) else len(values)
    return ",".join("?" * n)


# ---------------------------------------------------------------------------
# Pagination helpers
# ---------------------------------------------------------------------------


def compute_pagination(
    offset: int,
    limit: int,
    total: int,
) -> dict[str, int | bool]:
    """Derive page metadata from offset/limit/total.

    Returns a dict with ``page`` (0-based), ``page_count``, and ``has_next``.
    """
    if limit <= 0:
        return {"page": 0, "page_count": 1, "has_next": False}
    return {
        "page": offset // limit,
        "page_count": max(1, (total + limit - 1) // limit),
        "has_next": offset + limit < total,
    }


def fetch_with_has_more(
    cursor: sqlite3.Cursor,
    limit: int,
) -> tuple[list[sqlite3.Row], bool]:
    """Fetch *limit* + 1 rows to detect whether more results exist.

    The cursor must already have been executed.  Returns
    ``(rows[:limit], has_more)``.
    """
    rows = cursor.fetchmany(limit + 1)
    if len(rows) > limit:
        return rows[:limit], True
    return rows, False


def parse_json_list(val: str | None) -> list[str]:
    """Parse a JSON array column value, returning [] on any failure."""
    if not val:
        return []
    try:
        data = json.loads(val)
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


def fetch_bli_related_pes(
    conn: sqlite3.Connection, bli_key: str
) -> list[dict[str, Any]]:
    """Return Phase-11 BLI→PE mappings (joined with pe_index for titles).

    Returns ``[]`` when the ``bli_pe_map`` table is missing — e.g. on a DB
    that hasn't run enrichment Phase 11 yet.
    """
    try:
        rows = conn.execute(
            """
            SELECT bpm.pe_number, bpm.confidence, bpm.source_file, bpm.page_number,
                   pi.display_title AS pe_title
            FROM bli_pe_map bpm
            LEFT JOIN pe_index pi ON pi.pe_number = bpm.pe_number
            WHERE bpm.bli_key = ?
            ORDER BY bpm.confidence DESC, bpm.pe_number
            """,
            (bli_key,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]
