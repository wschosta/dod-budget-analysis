"""
GET /api/v1/facets endpoint.

Returns per-dimension counts with cross-filtering: each dimension's
counts apply all OTHER active filters but not its own filter.
This enables the UI to show how many results each filter option yields.
"""

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends
from fastapi import Query as FQuery

from api.database import get_db
from utils.cache import TTLCache

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

    if fiscal_year and exclude_dim != "fiscal_year":
        ph = ",".join("?" * len(fiscal_year))
        conditions.append(f"fiscal_year IN ({ph})")
        params.extend(fiscal_year)
    if service and exclude_dim != "service":
        ph = ",".join("?" * len(service))
        conditions.append(f"organization_name IN ({ph})")
        params.extend(service)
    if exhibit_type and exclude_dim != "exhibit_type":
        ph = ",".join("?" * len(exhibit_type))
        conditions.append(f"exhibit_type IN ({ph})")
        params.extend(exhibit_type)
    if budget_type and exclude_dim != "budget_type":
        ph = ",".join("?" * len(budget_type))
        conditions.append(f"budget_type IN ({ph})")
        params.extend(budget_type)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    return where, params


@router.get("", summary="Faceted counts for filter dropdowns")
def get_facets(
    fiscal_year: list[str] | None = FQuery(
        None, description="Current fiscal year filter(s)"),
    service: list[str] | None = FQuery(
        None, description="Current service filter(s)"),
    exhibit_type: list[str] | None = FQuery(
        None, description="Current exhibit type filter(s)"),
    budget_type: list[str] | None = FQuery(
        None, description="Current budget type filter(s)"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return per-dimension facet counts with cross-filtering.

    Each dimension shows counts with all OTHER active filters applied,
    but NOT its own filter. This lets the UI show how many results
    each option would yield if selected.
    """
    cache_key = (
        "facets",
        tuple(sorted(fiscal_year or [])),
        tuple(sorted(service or [])),
        tuple(sorted(exhibit_type or [])),
        tuple(sorted(budget_type or [])),
    )
    cached = _facets_cache.get(cache_key)
    if cached is not None:
        return cached

    result: dict[str, list[dict]] = {}

    # Fiscal year facet (excludes fiscal_year from its own filter)
    where, params = _build_conditions(
        fiscal_year, service, exhibit_type, budget_type,
        exclude_dim="fiscal_year",
    )
    fy_rows = conn.execute(
        f"SELECT fiscal_year AS value, COUNT(*) AS count "
        f"FROM budget_lines {where} "
        f"WHERE fiscal_year IS NOT NULL "
        f"{'AND ' + where.replace('WHERE ', '') if where else ''}"
        f"GROUP BY fiscal_year ORDER BY fiscal_year DESC",
        params,
    ).fetchall()
    # Simplify: run a single clean query per dimension
    where_fy, params_fy = _build_conditions(
        fiscal_year, service, exhibit_type, budget_type,
        exclude_dim="fiscal_year",
    )
    fy_clause = where_fy if where_fy else ""
    extra_cond = "fiscal_year IS NOT NULL"
    if fy_clause:
        fy_clause = fy_clause + " AND " + extra_cond
    else:
        fy_clause = "WHERE " + extra_cond
    fy_rows = conn.execute(
        f"SELECT fiscal_year AS value, COUNT(*) AS count "
        f"FROM budget_lines {fy_clause} "
        f"GROUP BY fiscal_year ORDER BY fiscal_year DESC",
        params_fy,
    ).fetchall()
    result["fiscal_year"] = [
        {"value": r["value"], "count": r["count"]} for r in fy_rows
    ]

    # Service facet
    where_svc, params_svc = _build_conditions(
        fiscal_year, service, exhibit_type, budget_type,
        exclude_dim="service",
    )
    extra_cond = "organization_name IS NOT NULL AND organization_name != ''"
    if where_svc:
        svc_clause = where_svc + " AND " + extra_cond
    else:
        svc_clause = "WHERE " + extra_cond
    svc_rows = conn.execute(
        f"SELECT organization_name AS value, COUNT(*) AS count "
        f"FROM budget_lines {svc_clause} "
        f"GROUP BY organization_name ORDER BY COUNT(*) DESC",
        params_svc,
    ).fetchall()
    result["service"] = [
        {"value": r["value"], "count": r["count"]} for r in svc_rows
    ]

    # Exhibit type facet
    where_et, params_et = _build_conditions(
        fiscal_year, service, exhibit_type, budget_type,
        exclude_dim="exhibit_type",
    )
    extra_cond = "exhibit_type IS NOT NULL"
    if where_et:
        et_clause = where_et + " AND " + extra_cond
    else:
        et_clause = "WHERE " + extra_cond
    # Join with exhibit_types reference for display names
    et_rows = conn.execute(
        f"SELECT b.exhibit_type AS value, "
        f"COALESCE(et.display_name, b.exhibit_type) AS display_name, "
        f"COUNT(*) AS count "
        f"FROM budget_lines b "
        f"LEFT JOIN exhibit_types et ON et.code = b.exhibit_type "
        f"{et_clause} "
        f"GROUP BY b.exhibit_type ORDER BY COUNT(*) DESC",
        params_et,
    ).fetchall()
    result["exhibit_type"] = [
        {"value": r["value"], "display_name": r["display_name"],
         "count": r["count"]}
        for r in et_rows
    ]

    # Budget type facet
    where_bt, params_bt = _build_conditions(
        fiscal_year, service, exhibit_type, budget_type,
        exclude_dim="budget_type",
    )
    extra_cond = "budget_type IS NOT NULL AND budget_type != ''"
    if where_bt:
        bt_clause = where_bt + " AND " + extra_cond
    else:
        bt_clause = "WHERE " + extra_cond
    bt_rows = conn.execute(
        f"SELECT budget_type AS value, COUNT(*) AS count "
        f"FROM budget_lines {bt_clause} "
        f"GROUP BY budget_type ORDER BY COUNT(*) DESC",
        params_bt,
    ).fetchall()
    result["budget_type"] = [
        {"value": r["value"], "count": r["count"]} for r in bt_rows
    ]

    _facets_cache.set(cache_key, result)
    return result
