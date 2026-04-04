"""
GET /api/v1/facets endpoint.

Returns per-dimension counts with cross-filtering: each dimension's
counts apply all OTHER active filters but not its own filter.
This enables the UI to show how many results each filter option yields.
"""

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends

from api.database import get_db
from api.models import FilterParams
from utils.cache import TTLCache
from utils.query import _add_in_condition

router = APIRouter(prefix="/facets", tags=["facets"])

_facets_cache: TTLCache = TTLCache(maxsize=64, ttl_seconds=300)


def _build_conditions(
    fiscal_year: list[str] | None,
    service: list[str] | None,
    exhibit_type: list[str] | None,
    budget_type: list[str] | None,
    exclude_dim: str | None = None,
) -> tuple[str, list[Any]]:
    """Build WHERE clause excluding one dimension for cross-filtering."""
    conditions: list[str] = []
    params: list[Any] = []

    if exclude_dim != "fiscal_year":
        _add_in_condition(conditions, params, "fiscal_year", fiscal_year)
    if exclude_dim != "service":
        _add_in_condition(conditions, params, "organization_name", service)
    if exclude_dim != "exhibit_type":
        _add_in_condition(conditions, params, "exhibit_type", exhibit_type)
    if exclude_dim != "budget_type":
        _add_in_condition(conditions, params, "budget_type", budget_type)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


@router.get("", summary="Faceted counts for filter dropdowns")
def get_facets(
    filters: FilterParams = Depends(),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return per-dimension facet counts with cross-filtering.

    Each dimension shows counts with all OTHER active filters applied,
    but NOT its own filter. This lets the UI show how many results
    each option would yield if selected.
    """
    cache_key = (
        "facets",
        tuple(sorted(filters.fiscal_year or [])),
        tuple(sorted(filters.service or [])),
        tuple(sorted(filters.exhibit_type or [])),
        tuple(sorted(filters.budget_type or [])),
    )
    cached = _facets_cache.get(cache_key)
    if cached is not None:
        return cached

    result: dict[str, list[dict]] = {}

    # Facet definitions: (result_key, exclude_dim, column, not_null_cond, order, extra_sql)
    _FACET_DEFS: list[tuple[str, str, str, str, str, str, str]] = [
        # (key, dim, select_cols, from_clause, not_null, group_col, order)
        (
            "fiscal_year",
            "fiscal_year",
            "fiscal_year AS value, COUNT(*) AS count",
            "budget_lines",
            "fiscal_year IS NOT NULL",
            "fiscal_year",
            "fiscal_year DESC",
        ),
        (
            "service",
            "service",
            "organization_name AS value, COUNT(*) AS count",
            "budget_lines",
            "organization_name IS NOT NULL AND organization_name != ''",
            "organization_name",
            "COUNT(*) DESC",
        ),
        (
            "exhibit_type",
            "exhibit_type",
            "b.exhibit_type AS value, COALESCE(et.display_name, b.exhibit_type) AS display_name, COUNT(*) AS count",
            "budget_lines b LEFT JOIN exhibit_types et ON et.code = b.exhibit_type",
            "exhibit_type IS NOT NULL",
            "b.exhibit_type",
            "COUNT(*) DESC",
        ),
        (
            "budget_type",
            "budget_type",
            "budget_type AS value, COUNT(*) AS count",
            "budget_lines",
            "budget_type IS NOT NULL AND budget_type != ''",
            "budget_type",
            "COUNT(*) DESC",
        ),
    ]

    for key, dim, select_cols, from_clause, not_null, group_col, order in _FACET_DEFS:
        where, params = _build_conditions(
            filters.fiscal_year,
            filters.service,
            filters.exhibit_type,
            filters.budget_type,
            exclude_dim=dim,
        )
        if where:
            clause = f"{where} AND {not_null}"
        else:
            clause = f"WHERE {not_null}"
        rows = conn.execute(
            f"SELECT {select_cols} FROM {from_clause} {clause} "
            f"GROUP BY {group_col} ORDER BY {order}",
            params,
        ).fetchall()
        result[key] = [dict(r) for r in rows]

    _facets_cache.set(cache_key, result)
    return result
