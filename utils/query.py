"""Shared SQL query builder utilities for DoD Budget API routes.

Provides DRY WHERE clause and ORDER BY construction used by budget_lines.py,
frontend.py, and download.py.
"""

from typing import Any


_ALLOWED_SORTS_DEFAULT = {
    "id", "source_file", "exhibit_type", "fiscal_year",
    "organization_name", "account", "account_title", "pe_number",
    "amount_fy2026_request", "amount_fy2025_enacted", "amount_fy2024_actual",
}

# EAGLE-1: Whitelist of valid fiscal year amount columns for dynamic filtering
VALID_AMOUNT_COLUMNS = {
    "amount_fy2024_actual",
    "amount_fy2025_enacted",
    "amount_fy2025_supplemental",
    "amount_fy2025_total",
    "amount_fy2026_request",
    "amount_fy2026_reconciliation",
    "amount_fy2026_total",
}

# EAGLE-1: Human-readable labels for FY amount columns
FISCAL_YEAR_COLUMN_LABELS = [
    {"column": "amount_fy2024_actual", "label": "FY2024 Actual"},
    {"column": "amount_fy2025_enacted", "label": "FY2025 Enacted"},
    {"column": "amount_fy2025_total", "label": "FY2025 Total"},
    {"column": "amount_fy2026_request", "label": "FY2026 Request"},
    {"column": "amount_fy2026_total", "label": "FY2026 Total"},
]

DEFAULT_AMOUNT_COLUMN = "amount_fy2026_request"


def validate_amount_column(column: str | None) -> str:
    """Validate and return an amount column name, defaulting to FY2026 request.

    Args:
        column: Column name to validate. None returns the default.

    Returns:
        A valid amount column name from VALID_AMOUNT_COLUMNS.

    Raises:
        ValueError: If the column name is not in the whitelist.
    """
    if column is None:
        return DEFAULT_AMOUNT_COLUMN
    if column not in VALID_AMOUNT_COLUMNS:
        raise ValueError(
            f"Invalid amount column: '{column}'. "
            f"Must be one of: {', '.join(sorted(VALID_AMOUNT_COLUMNS))}"
        )
    return column


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

    Returns:
        Tuple of (where_clause_string, params_list). The where_clause_string
        starts with "WHERE " if any conditions exist, or is "" if none.
    """
    conditions: list[str] = []
    params: list[Any] = []

    if fiscal_year:
        placeholders = ",".join("?" * len(fiscal_year))
        conditions.append(f"fiscal_year IN ({placeholders})")
        params.extend(fiscal_year)

    # FIX-002b: Changed from LIKE %value% to exact IN() matching.
    # LIKE was too broad — selecting "AF" would match "CAAF" and other orgs.
    if service:
        placeholders = ",".join("?" * len(service))
        conditions.append(f"organization_name IN ({placeholders})")
        params.extend(service)

    if exhibit_type:
        placeholders = ",".join("?" * len(exhibit_type))
        conditions.append(f"exhibit_type IN ({placeholders})")
        params.extend(exhibit_type)

    if pe_number:
        placeholders = ",".join("?" * len(pe_number))
        conditions.append(f"pe_number IN ({placeholders})")
        params.extend(pe_number)

    if appropriation_code:
        placeholders = ",".join("?" * len(appropriation_code))
        conditions.append(f"appropriation_code IN ({placeholders})")
        params.extend(appropriation_code)

    if budget_type:
        placeholders = ",".join("?" * len(budget_type))
        conditions.append(f"budget_type IN ({placeholders})")
        params.extend(budget_type)

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
        id_placeholders = ",".join("?" * len(fts_ids))
        conditions.append(f"id IN ({id_placeholders})")
        params.extend(fts_ids)

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
            _ALLOWED_SORTS_DEFAULT if not provided.
        default_sort: Column to use if sort_by is not in allowed_sorts.

    Returns:
        ORDER BY clause string, e.g. "ORDER BY id ASC".
    """
    if allowed_sorts is None:
        allowed_sorts = _ALLOWED_SORTS_DEFAULT
    col = sort_by if sort_by in allowed_sorts else default_sort
    direction = "DESC" if sort_dir.lower() == "desc" else "ASC"
    return f"ORDER BY {col} {direction}"
