"""Database metadata collection utilities (HAWK-5).

Provides functions to collect summary metadata about the DoD budget database:
table counts, fiscal year ranges, exhibit types, services, and enrichment
coverage statistics.

Usage:
    from utils.metadata import collect_metadata

    meta = collect_metadata(conn)
    # meta == {"tables": {...}, "fiscal_years": [...], "services": [...], ...}
"""

from __future__ import annotations

import sqlite3
from datetime import datetime


def collect_metadata(conn: sqlite3.Connection) -> dict:
    """Collect comprehensive metadata about the budget database.

    Returns a dict with:
        - tables: row counts per table
        - fiscal_years: distinct fiscal years in budget_lines
        - services: distinct organization names
        - exhibit_types: distinct exhibit types
        - enrichment: coverage stats for enrichment tables
        - last_modified: database file modification timestamp (if available)
        - version: schema version info

    Args:
        conn: Open SQLite connection with row_factory=sqlite3.Row.

    Returns:
        Dict of metadata about the database.
    """
    meta: dict = {
        "generated_at": datetime.now().isoformat(),
    }

    # ── Table row counts ─────────────────────────────────────────────────
    tables = {}
    known_tables = [
        "budget_lines", "pdf_pages", "pe_index", "pe_descriptions",
        "pe_tags", "pe_lineage", "project_descriptions",
    ]
    for table in known_tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            tables[table] = count
        except sqlite3.OperationalError:
            tables[table] = None  # table doesn't exist
    meta["tables"] = tables

    # ── Distinct fiscal years ────────────────────────────────────────────
    try:
        rows = conn.execute(
            "SELECT DISTINCT fiscal_year FROM budget_lines "
            "WHERE fiscal_year IS NOT NULL ORDER BY fiscal_year"
        ).fetchall()
        meta["fiscal_years"] = [r[0] for r in rows]
    except sqlite3.OperationalError:
        meta["fiscal_years"] = []

    # ── Distinct services / organizations ────────────────────────────────
    try:
        rows = conn.execute(
            "SELECT DISTINCT organization_name FROM budget_lines "
            "WHERE organization_name IS NOT NULL ORDER BY organization_name"
        ).fetchall()
        meta["services"] = [r[0] for r in rows]
    except sqlite3.OperationalError:
        meta["services"] = []

    # ── Distinct exhibit types ───────────────────────────────────────────
    try:
        rows = conn.execute(
            "SELECT DISTINCT exhibit_type FROM budget_lines "
            "WHERE exhibit_type IS NOT NULL ORDER BY exhibit_type"
        ).fetchall()
        meta["exhibit_types"] = [r[0] for r in rows]
    except sqlite3.OperationalError:
        meta["exhibit_types"] = []

    # ── Enrichment coverage ──────────────────────────────────────────────
    enrichment: dict = {}

    # PE index coverage
    try:
        pe_count = conn.execute("SELECT COUNT(*) FROM pe_index").fetchone()[0]
        bl_pe_count = conn.execute(
            "SELECT COUNT(DISTINCT pe_number) FROM budget_lines "
            "WHERE pe_number IS NOT NULL"
        ).fetchone()[0]
        enrichment["pe_index"] = {
            "total": pe_count,
            "budget_lines_distinct_pes": bl_pe_count,
            "coverage_pct": round(pe_count / bl_pe_count * 100, 1) if bl_pe_count else 0,
        }
    except sqlite3.OperationalError:
        enrichment["pe_index"] = None

    # Tag statistics
    try:
        tag_count = conn.execute("SELECT COUNT(*) FROM pe_tags").fetchone()[0]
        distinct_tags = conn.execute(
            "SELECT COUNT(DISTINCT tag) FROM pe_tags"
        ).fetchone()[0]
        tag_sources = conn.execute(
            "SELECT tag_source, COUNT(*) as cnt FROM pe_tags "
            "GROUP BY tag_source ORDER BY cnt DESC"
        ).fetchall()
        enrichment["pe_tags"] = {
            "total": tag_count,
            "distinct_tags": distinct_tags,
            "by_source": {r[0]: r[1] for r in tag_sources},
        }
    except sqlite3.OperationalError:
        enrichment["pe_tags"] = None

    # Description coverage
    try:
        desc_count = conn.execute("SELECT COUNT(*) FROM pe_descriptions").fetchone()[0]
        desc_pe_count = conn.execute(
            "SELECT COUNT(DISTINCT pe_number) FROM pe_descriptions"
        ).fetchone()[0]
        enrichment["pe_descriptions"] = {
            "total": desc_count,
            "distinct_pes": desc_pe_count,
        }
    except sqlite3.OperationalError:
        enrichment["pe_descriptions"] = None

    # Project decomposition coverage
    try:
        proj_count = conn.execute("SELECT COUNT(*) FROM project_descriptions").fetchone()[0]
        proj_with_num = conn.execute(
            "SELECT COUNT(*) FROM project_descriptions "
            "WHERE project_number IS NOT NULL"
        ).fetchone()[0]
        enrichment["project_descriptions"] = {
            "total": proj_count,
            "with_project_number": proj_with_num,
            "pe_level_fallback": proj_count - proj_with_num,
        }
    except sqlite3.OperationalError:
        enrichment["project_descriptions"] = None

    # Lineage links
    try:
        lineage_count = conn.execute("SELECT COUNT(*) FROM pe_lineage").fetchone()[0]
        enrichment["pe_lineage"] = {"total": lineage_count}
    except sqlite3.OperationalError:
        enrichment["pe_lineage"] = None

    meta["enrichment"] = enrichment

    # ── Amount summary ───────────────────────────────────────────────────
    try:
        row = conn.execute("""
            SELECT
                SUM(COALESCE(amount_fy2026_request, 0)) as total_fy2026,
                SUM(COALESCE(amount_fy2025_enacted, 0)) as total_fy2025,
                SUM(COALESCE(amount_fy2024_actual, 0))  as total_fy2024
            FROM budget_lines
        """).fetchone()
        meta["amounts"] = {
            "total_fy2026_request": round(row[0], 2) if row[0] else 0,
            "total_fy2025_enacted": round(row[1], 2) if row[1] else 0,
            "total_fy2024_actual": round(row[2], 2) if row[2] else 0,
        }
    except sqlite3.OperationalError:
        meta["amounts"] = None

    return meta
