"""
Reference data endpoints (Step 2.C3-d).

GET /api/v1/reference/services       → list of services/agencies
GET /api/v1/reference/exhibit-types  → list of exhibit types
GET /api/v1/reference/fiscal-years   → list of fiscal years in the database
"""

import sqlite3

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api.database import get_db
from api.models import ExhibitTypeOut, FiscalYearOut, ServiceOut

router = APIRouter(prefix="/reference", tags=["reference"])

_CACHE_HEADER = {"Cache-Control": "max-age=3600"}


@router.get(
    "/services",
    response_model=list[ServiceOut],
    summary="List services and agencies",
)
def list_services(conn: sqlite3.Connection = Depends(get_db)) -> JSONResponse:
    """Return all known military services and defense agencies."""
    try:
        rows = conn.execute(
            "SELECT code, full_name, category FROM services_agencies ORDER BY code"
        ).fetchall()
        data = [dict(r) for r in rows]
    except Exception:
        # Fall back to distinct values from flat budget_lines table
        rows = conn.execute(
            "SELECT DISTINCT organization_name as code FROM budget_lines "
            "WHERE organization_name IS NOT NULL ORDER BY organization_name"
        ).fetchall()
        data = [{"code": r["code"], "full_name": r["code"], "category": "unknown"}
                for r in rows]
    return JSONResponse(content=data, headers=_CACHE_HEADER)


@router.get(
    "/exhibit-types",
    response_model=list[ExhibitTypeOut],
    summary="List exhibit types",
)
def list_exhibit_types(conn: sqlite3.Connection = Depends(get_db)) -> JSONResponse:
    """Return all known budget exhibit types."""
    try:
        rows = conn.execute(
            "SELECT code, display_name, exhibit_class, description "
            "FROM exhibit_types ORDER BY code"
        ).fetchall()
        data = [dict(r) for r in rows]
    except Exception:
        rows = conn.execute(
            "SELECT DISTINCT exhibit_type as code FROM budget_lines "
            "WHERE exhibit_type IS NOT NULL ORDER BY exhibit_type"
        ).fetchall()
        data = [{"code": r["code"], "display_name": r["code"],
                 "exhibit_class": "unknown", "description": None}
                for r in rows]
    return JSONResponse(content=data, headers=_CACHE_HEADER)


@router.get(
    "/fiscal-years",
    response_model=list[FiscalYearOut],
    summary="List fiscal years",
)
def list_fiscal_years(conn: sqlite3.Connection = Depends(get_db)) -> JSONResponse:
    """Return all fiscal years present in the budget_lines table."""
    rows = conn.execute(
        "SELECT fiscal_year, COUNT(*) as row_count FROM budget_lines "
        "WHERE fiscal_year IS NOT NULL "
        "GROUP BY fiscal_year ORDER BY fiscal_year"
    ).fetchall()
    data = [{"fiscal_year": r["fiscal_year"], "row_count": r["row_count"]}
            for r in rows]
    return JSONResponse(content=data, headers=_CACHE_HEADER)


@router.get(
    "/appropriations",
    summary="List distinct appropriation codes with row counts",
)
def list_appropriations(conn: sqlite3.Connection = Depends(get_db)) -> JSONResponse:
    """Return all distinct appropriation codes from budget_lines."""
    rows = conn.execute(
        "SELECT appropriation_code, appropriation_title, COUNT(*) AS row_count "
        "FROM budget_lines "
        "WHERE appropriation_code IS NOT NULL "
        "GROUP BY appropriation_code "
        "ORDER BY row_count DESC"
    ).fetchall()
    data = [{"code": r["appropriation_code"],
             "title": r["appropriation_title"],
             "row_count": r["row_count"]}
            for r in rows]
    return JSONResponse(content=data, headers=_CACHE_HEADER)


@router.get(
    "/budget-types",
    summary="List distinct budget types with row counts",
)
def list_budget_types(conn: sqlite3.Connection = Depends(get_db)) -> JSONResponse:
    """Return all distinct budget_type values from budget_lines."""
    try:
        rows = conn.execute(
            "SELECT COALESCE(budget_type, 'Unknown') AS budget_type, "
            "COUNT(*) AS row_count "
            "FROM budget_lines "
            "GROUP BY COALESCE(budget_type, 'Unknown') "
            "ORDER BY row_count DESC"
        ).fetchall()
        data = [{"budget_type": r["budget_type"], "row_count": r["row_count"]}
                for r in rows]
    except Exception:
        data = []
    return JSONResponse(content=data, headers=_CACHE_HEADER)
