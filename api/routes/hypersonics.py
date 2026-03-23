"""
Hypersonics PE lines endpoints.

Returns a pivoted view of all budget lines related to hypersonics programs,
FY2015 onward. Sources: budget_lines keyword search + pe_descriptions narrative search.

Matching logic (PE-level): a PE number is included if ANY of its budget_lines rows match
a keyword OR if any pe_descriptions row for that PE matches a keyword. Once a PE is
matched, ALL of its sub-elements (line_item_title rows) are returned — not just the
rows that individually match a keyword.

Data is served from a pre-computed ``hypersonics_cache`` table for instant reads.
Call ``rebuild_hypersonics_cache(conn)`` after pipeline/enrichment runs, or hit the
POST /api/v1/hypersonics/rebuild endpoint to refresh.

Endpoints:
  GET  /api/v1/hypersonics          — JSON, pivoted table data
  GET  /api/v1/hypersonics/download — streaming CSV of pivoted table
  GET  /api/v1/hypersonics/debug    — data-quality checks
  POST /api/v1/hypersonics/rebuild  — rebuild the materialized cache table
"""

from __future__ import annotations

import csv
import io
import json
import logging
import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from api.database import get_db
from utils.database import get_amount_columns

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hypersonics", tags=["hypersonics"])

# ── Keywords ──────────────────────────────────────────────────────────────────

_HYPERSONICS_KEYWORDS = [
    # ── Generic / cross-program ───────────────────────────────────────────
    "hypersonic",           # hypersonics, hypersonic glide, hypersonic weapon…
    "boost glide",          # boost-glide vehicles (all services)
    "glide body",           # Common Hypersonic Glide Body (C-HGB)
    "glide vehicle",        # generic glide vehicle references
    "scramjet",             # air-breathing hypersonic propulsion

    # ── Offensive — Air Force ──────────────────────────────────────────────
    "ARRW",                 # Air-Launched Rapid Response Weapon (AGM-183A)
    "AGM-183",              # ARRW missile designation
    "HACM",                 # Hypersonic Attack Cruise Missile
    "HCSW",                 # Hypersonic Conventional Strike Weapon (cancelled FY20)

    # ── Offensive — Army ───────────────────────────────────────────────────
    "LRHW",                 # Long Range Hypersonic Weapon / Dark Eagle battery
    "Dark Eagle",           # LRHW battery name
    "OpFires",              # Operational Fires (hypersonic component)

    # ── Offensive — Navy / Joint ───────────────────────────────────────────
    "C-HGB",                # Common Hypersonic Glide Body (joint Army/Navy)
    "CHGB",                 # alternate abbreviation
    "conventional prompt strike",   # Navy CPS program
    "prompt strike",        # catches "Intermediate Range Conventional Prompt Strike"

    # ── Defensive / tracking ───────────────────────────────────────────────
    "Glide Phase Interceptor",  # GPI — MDA program to defeat HGVs in glide
    "HBTSS",                # Hypersonic and Ballistic Tracking Space Sensor
]

_DESC_KEYWORDS = [
    "hypersonic",
    "boost glide",
    "glide vehicle",
    "scramjet",
    "ARRW",
    "HACM",
    "HCSW",
    "LRHW",
    "Dark Eagle",
    "C-HGB",
    "CHGB",
    "conventional prompt strike",
    "prompt strike",
    "Glide Phase Interceptor",
    "HBTSS",
    "OpFires",
]

_SEARCH_COLS = ["line_item_title", "account_title", "budget_activity_title"]

_FY_START = 2015
_FY_END = 2026


# ── Budget Activity normalization (#5) ────────────────────────────────────────

# RDT&E BA categories (BA 01-07) — canonical titles
_BA_CANONICAL: dict[str, str] = {
    "01": "BA 1: Basic Research",
    "02": "BA 2: Applied Research",
    "03": "BA 3: Advanced Technology Development",
    "04": "BA 4: Advanced Component Dev & Prototypes",
    "05": "BA 5: System Development & Demonstration",
    "06": "BA 6: RDT&E Management Support",
    "07": "BA 7: Operational Systems Development",
}


def _normalize_budget_activity(ba_number: str | None, ba_title: str | None) -> str:
    """Map budget_activity number to canonical BA label, falling back to title."""
    if ba_number and ba_number.strip() in _BA_CANONICAL:
        return _BA_CANONICAL[ba_number.strip()]
    if ba_title:
        return ba_title.strip()
    return "Unknown"


# ── Color-of-money normalization ──────────────────────────────────────────────

def _color_of_money(approp_title: str | None) -> str:
    """Map appropriation title to a standard color-of-money category."""
    if not approp_title:
        return "Unknown"
    t = approp_title.upper()
    if any(k in t for k in ("RDT", "RESEARCH", "DEVELOPMENT", "R&D")):
        return "RDT&E"
    if "PROCURE" in t:
        return "Procurement"
    if any(k in t for k in ("OPER", "MAINT", "O&M")):
        return "O&M"
    if any(k in t for k in ("MILCON", "CONSTRUCTION")):
        return "MILCON"
    if any(k in t for k in ("MILPERS", "PERSONNEL")):
        return "Military Personnel"
    return approp_title


# ── Keyword matching helpers (#4) ─────────────────────────────────────────────

def _find_matched_keywords(text_fields: list[str | None]) -> list[str]:
    """Return which hypersonics keywords match in the given text fields."""
    combined = " ".join((t or "") for t in text_fields).lower()
    if not combined.strip():
        return []
    matched = []
    for kw in _HYPERSONICS_KEYWORDS:
        if kw.lower() in combined:
            matched.append(kw)
    return matched


# ── Materialized table (#6) ───────────────────────────────────────────────────

_CACHE_TABLE = "hypersonics_cache"

_CACHE_DDL = f"""
CREATE TABLE IF NOT EXISTS {_CACHE_TABLE} (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    pe_number               TEXT NOT NULL,
    organization_name       TEXT,
    exhibit_type            TEXT,
    line_item_title         TEXT,
    budget_activity         TEXT,
    budget_activity_title   TEXT,
    budget_activity_norm    TEXT,
    appropriation_title     TEXT,
    account_title           TEXT,
    color_of_money          TEXT,
    matched_keywords_row    TEXT,
    matched_keywords_desc   TEXT,
    description_text        TEXT,
    fy2015 REAL, fy2015_ref TEXT,
    fy2016 REAL, fy2016_ref TEXT,
    fy2017 REAL, fy2017_ref TEXT,
    fy2018 REAL, fy2018_ref TEXT,
    fy2019 REAL, fy2019_ref TEXT,
    fy2020 REAL, fy2020_ref TEXT,
    fy2021 REAL, fy2021_ref TEXT,
    fy2022 REAL, fy2022_ref TEXT,
    fy2023 REAL, fy2023_ref TEXT,
    fy2024 REAL, fy2024_ref TEXT,
    fy2025 REAL, fy2025_ref TEXT,
    fy2026 REAL, fy2026_ref TEXT
);
"""


def _collect_matching_pe_numbers(conn: sqlite3.Connection) -> set[str]:
    """Return the set of PE numbers that match any hypersonics keyword."""
    matched: set[str] = set()

    # (a) Budget-lines keyword match
    kw_clauses: list[str] = []
    kw_params: list[Any] = []
    for col in _SEARCH_COLS:
        for kw in _HYPERSONICS_KEYWORDS:
            kw_clauses.append(f"{col} LIKE ?")
            kw_params.append(f"%{kw}%")
    kw_where = " OR ".join(kw_clauses)
    rows = conn.execute(
        f"SELECT DISTINCT pe_number FROM budget_lines WHERE {kw_where}", kw_params
    ).fetchall()
    matched.update(r[0] for r in rows if r[0])

    # (b) pe_descriptions narrative match
    try:
        conn.execute("SELECT 1 FROM pe_descriptions LIMIT 0")
        desc_clauses = ["description_text LIKE ?" for _ in _DESC_KEYWORDS]
        desc_params = [f"%{kw}%" for kw in _DESC_KEYWORDS]
        rows = conn.execute(
            "SELECT DISTINCT pe_number FROM pe_descriptions"
            f" WHERE {' OR '.join(desc_clauses)}",
            desc_params,
        ).fetchall()
        matched.update(r[0] for r in rows if r[0])
    except sqlite3.OperationalError:
        pass

    return matched


def _get_description_map(conn: sqlite3.Connection, pe_numbers: set[str]) -> dict[str, str]:
    """Build PE → truncated description text map for UI display."""
    if not pe_numbers:
        return {}
    try:
        conn.execute("SELECT 1 FROM pe_descriptions LIMIT 0")
    except sqlite3.OperationalError:
        return {}

    result: dict[str, str] = {}
    # Query in batches to avoid huge GROUP_CONCAT — take first 2000 chars only
    for pe in pe_numbers:
        rows = conn.execute(
            "SELECT description_text FROM pe_descriptions "
            "WHERE pe_number = ? LIMIT 5",
            [pe],
        ).fetchall()
        text = " ".join(r[0] for r in rows if r[0])
        if len(text) > 2000:
            text = text[:2000] + "…"
        if text.strip():
            result[pe] = text
    return result


def _get_desc_keyword_map(conn: sqlite3.Connection, pe_numbers: set[str]) -> dict[str, list[str]]:
    """Build PE → list of DESC_KEYWORDS that match in pe_descriptions (via SQL LIKE).

    Uses SQL-level matching to avoid truncation bugs from GROUP_CONCAT.
    """
    if not pe_numbers:
        return {}
    try:
        conn.execute("SELECT 1 FROM pe_descriptions LIMIT 0")
    except sqlite3.OperationalError:
        return {}

    placeholders = ", ".join("?" for _ in pe_numbers)
    pe_list = list(pe_numbers)
    result: dict[str, list[str]] = {}

    for kw in _DESC_KEYWORDS:
        rows = conn.execute(
            f"SELECT DISTINCT pe_number FROM pe_descriptions "
            f"WHERE pe_number IN ({placeholders}) AND description_text LIKE ?",
            pe_list + [f"%{kw}%"],
        ).fetchall()
        for r in rows:
            result.setdefault(r[0], [])
            if kw not in result[r[0]]:
                result[r[0]].append(kw)

    return result


def rebuild_hypersonics_cache(conn: sqlite3.Connection) -> int:
    """Rebuild the hypersonics_cache table from budget_lines + pe_descriptions.

    Returns the number of rows inserted.
    """
    logger.info("Rebuilding hypersonics cache table...")

    # 1. Collect matching PE numbers
    matched_pes = _collect_matching_pe_numbers(conn)
    if not matched_pes:
        conn.execute(f"DROP TABLE IF EXISTS {_CACHE_TABLE}")
        conn.execute(_CACHE_DDL)
        conn.commit()
        logger.info("No matching PEs found — cache table is empty.")
        return 0

    # 2. Get description text per PE (truncated for UI display)
    desc_map = _get_description_map(conn, matched_pes)

    # 2b. Get desc-level keyword matches per PE (via SQL LIKE, no truncation)
    desc_kw_map = _get_desc_keyword_map(conn, matched_pes)

    # 3. Get amount columns
    all_amount_cols = set(get_amount_columns(conn))

    # 4. Build pivot query
    pe_placeholders = ", ".join("?" for _ in matched_pes)
    pe_params = list(matched_pes)

    year_parts: list[str] = []
    for yr in range(_FY_START, _FY_END + 1):
        priority = [
            f"amount_fy{yr}_request",
            f"amount_fy{yr}_total",
            f"amount_fy{yr}_enacted",
            f"amount_fy{yr}_actual",
        ]
        available = [c for c in priority if c in all_amount_cols]
        if not available:
            coalesce_expr = "NULL"
        elif len(available) == 1:
            coalesce_expr = available[0]
        else:
            coalesce_expr = f"COALESCE({', '.join(available)})"
        year_parts.append(
            f"SUM(CASE WHEN fiscal_year = '{yr}' THEN {coalesce_expr} END) AS fy{yr}"
        )
        year_parts.append(
            f"MAX(CASE WHEN fiscal_year = '{yr}' THEN source_file END) AS fy{yr}_ref"
        )

    year_cols_sql = ",\n        ".join(year_parts)
    sql = f"""
        SELECT
            pe_number,
            MAX(organization_name) AS organization_name,
            exhibit_type,
            line_item_title,
            MAX(budget_activity) AS budget_activity,
            MAX(budget_activity_title) AS budget_activity_title,
            MAX(appropriation_title) AS appropriation_title,
            MAX(account_title) AS account_title,
            {year_cols_sql}
        FROM budget_lines
        WHERE pe_number IN ({pe_placeholders})
          AND CAST(fiscal_year AS INTEGER) >= {_FY_START}
        GROUP BY pe_number, exhibit_type, line_item_title
        HAVING COUNT(*) > 0
        ORDER BY pe_number, exhibit_type, line_item_title
    """

    rows = conn.execute(sql, pe_params).fetchall()

    # 5. Recreate cache table
    conn.execute(f"DROP TABLE IF EXISTS {_CACHE_TABLE}")
    conn.execute(_CACHE_DDL)

    # 6. Insert enriched rows
    year_range = list(range(_FY_START, _FY_END + 1))
    insert_cols = [
        "pe_number", "organization_name", "exhibit_type", "line_item_title",
        "budget_activity", "budget_activity_title", "budget_activity_norm",
        "appropriation_title", "account_title", "color_of_money",
        "matched_keywords_row", "matched_keywords_desc", "description_text",
    ]
    for yr in year_range:
        insert_cols.extend([f"fy{yr}", f"fy{yr}_ref"])
    placeholders_insert = ", ".join("?" for _ in insert_cols)
    insert_sql = f"INSERT INTO {_CACHE_TABLE} ({', '.join(insert_cols)}) VALUES ({placeholders_insert})"

    count = 0
    for r in rows:
        d = dict(r)
        # Row-level keyword matching (from structured fields)
        text_fields = [d.get("line_item_title"), d.get("account_title"), d.get("budget_activity_title")]
        row_kws = _find_matched_keywords(text_fields)
        # Desc-level keyword matching (from pe_descriptions via SQL)
        desc_kws = desc_kw_map.get(d["pe_number"], [])

        vals = [
            d["pe_number"],
            d.get("organization_name"),
            d.get("exhibit_type"),
            d.get("line_item_title"),
            d.get("budget_activity"),
            d.get("budget_activity_title"),
            _normalize_budget_activity(d.get("budget_activity"), d.get("budget_activity_title")),
            d.get("appropriation_title"),
            d.get("account_title"),
            _color_of_money(d.get("appropriation_title")),
            json.dumps(row_kws) if row_kws else "[]",
            json.dumps(desc_kws) if desc_kws else "[]",
            desc_map.get(d["pe_number"]) or None,
        ]
        for yr in year_range:
            vals.append(d.get(f"fy{yr}"))
            vals.append(d.get(f"fy{yr}_ref"))

        conn.execute(insert_sql, vals)
        count += 1

    # 7. Create indexes for fast filtering
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_hc_pe ON {_CACHE_TABLE}(pe_number)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_hc_org ON {_CACHE_TABLE}(organization_name)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_hc_exhibit ON {_CACHE_TABLE}(exhibit_type)")

    conn.commit()
    logger.info("Hypersonics cache rebuilt: %d rows", count)
    return count


def _ensure_cache(conn: sqlite3.Connection) -> bool:
    """Ensure hypersonics_cache exists and is populated. Returns True if data available."""
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM {_CACHE_TABLE}").fetchone()[0]
        if n > 0:
            return True
    except sqlite3.OperationalError:
        pass
    # Auto-rebuild on first access
    logger.info("hypersonics_cache not found or empty — rebuilding...")
    return rebuild_hypersonics_cache(conn) > 0


# ── Query helpers (now read from cache) ───────────────────────────────────────

def _apply_filters(
    service: str | None,
    exhibit: str | None,
    fy_from: int | None,
    fy_to: int | None,
) -> tuple[str, list[Any]]:
    """Build WHERE fragments for cache table filters."""
    parts: list[str] = []
    params: list[Any] = []
    if service:
        parts.append("organization_name LIKE ?")
        params.append(f"%{service}%")
    if exhibit:
        parts.append("exhibit_type = ?")
        params.append(exhibit)
    # FY filters: check which FY columns have data
    # (handled client-side for now since data is already pivoted in cache)
    return (" AND ".join(parts), params) if parts else ("", [])


def _cache_rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    """Convert cache rows to dicts with refs nested structure."""
    year_range = list(range(_FY_START, _FY_END + 1))
    result: list[dict] = []
    for r in rows:
        d = dict(r)
        # Parse keyword fields from JSON
        for field in ("matched_keywords_row", "matched_keywords_desc"):
            kw_json = d.get(field, "[]")
            try:
                d[field] = json.loads(kw_json) if kw_json else []
            except (json.JSONDecodeError, TypeError):
                d[field] = []
        # Build refs dict
        refs: dict[str, str] = {}
        for yr in year_range:
            ref_key = f"fy{yr}_ref"
            val = d.pop(ref_key, None)
            if val:
                refs[f"fy{yr}"] = val
        d["refs"] = refs
        result.append(d)
    return result


# ── GET /api/v1/hypersonics ───────────────────────────────────────────────────

@router.get(
    "",
    summary="Pivoted hypersonics PE lines from materialized cache",
)
def get_hypersonics(
    service: str | None = Query(None, description="Filter by service/org name (substring)"),
    exhibit: str | None = Query(None, description="Filter by exhibit type (exact, e.g. 'r2')"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return all hypersonics-related budget line sub-elements as a pivoted table."""
    _ensure_cache(conn)

    extra_where, extra_params = _apply_filters(service, exhibit, None, None)
    where = f"WHERE {extra_where}" if extra_where else ""
    sql = f"SELECT * FROM {_CACHE_TABLE} {where} ORDER BY pe_number, exhibit_type, line_item_title"
    rows = conn.execute(sql, extra_params).fetchall()

    year_range = list(range(_FY_START, _FY_END + 1))
    items = _cache_rows_to_dicts(rows)
    active_years = (
        [yr for yr in year_range if any(r.get(f"fy{yr}") is not None for r in items)]
        if items else year_range
    )

    return {
        "count": len(items),
        "fiscal_years": active_years,
        "keywords": _HYPERSONICS_KEYWORDS,
        "rows": items,
    }


# ── GET /api/v1/hypersonics/download ─────────────────────────────────────────

@router.get(
    "/download",
    summary="Download hypersonics PE lines as CSV",
    response_class=Response,
)
def download_hypersonics(
    service: str | None = Query(None),
    exhibit: str | None = Query(None),
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """Download pivoted hypersonics PE lines as CSV."""
    _ensure_cache(conn)

    extra_where, extra_params = _apply_filters(service, exhibit, None, None)
    where = f"WHERE {extra_where}" if extra_where else ""
    sql = f"SELECT * FROM {_CACHE_TABLE} {where} ORDER BY pe_number, exhibit_type, line_item_title"
    rows = conn.execute(sql, extra_params).fetchall()

    year_range = list(range(_FY_START, _FY_END + 1))
    items = _cache_rows_to_dicts(rows)

    fy_headers: list[str] = []
    for yr in year_range:
        fy_headers.extend([f"FY{yr} ($K)", f"FY{yr} Source"])

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "PE Number", "Service/Org", "Exhibit Type", "Line Item Title",
        "Budget Activity", "Budget Activity (Normalized)", "Appropriation",
        "Color of Money", "Keywords (Row)", "Keywords (Desc)",
        *fy_headers,
    ])
    for r in items:
        fy_cells: list[Any] = []
        for yr in year_range:
            fy_cells.append(r.get(f"fy{yr}"))
            fy_cells.append(r.get("refs", {}).get(f"fy{yr}", ""))
        writer.writerow([
            r["pe_number"], r["organization_name"], r["exhibit_type"],
            r["line_item_title"], r["budget_activity_title"],
            r["budget_activity_norm"], r["appropriation_title"],
            r["color_of_money"],
            ", ".join(r.get("matched_keywords_row", [])),
            ", ".join(r.get("matched_keywords_desc", [])),
            *fy_cells,
        ])

    csv_bytes = buf.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="hypersonics_pe_lines.csv"'},
    )


# ── POST /api/v1/hypersonics/rebuild ──────────────────────────────────────────

@router.post(
    "/rebuild",
    summary="Rebuild the materialized hypersonics cache table",
)
def rebuild_cache(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Rebuild the hypersonics_cache table from budget_lines + pe_descriptions."""
    count = rebuild_hypersonics_cache(conn)
    return {"status": "ok", "rows": count}


# ── GET /api/v1/hypersonics/debug ─────────────────────────────────────────────

@router.get(
    "/debug",
    summary="Pre-flight data quality checks for the hypersonics view",
)
def debug_hypersonics(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Surface data-quality stats to validate the hypersonics view against real data."""
    result: dict = {}

    # 1. Cache status
    try:
        cache_count = conn.execute(f"SELECT COUNT(*) FROM {_CACHE_TABLE}").fetchone()[0]
        distinct_pes = conn.execute(
            f"SELECT COUNT(DISTINCT pe_number) FROM {_CACHE_TABLE}"
        ).fetchone()[0]
        result["cache"] = {
            "table_exists": True,
            "row_count": cache_count,
            "distinct_pe_numbers": distinct_pes,
        }
    except sqlite3.OperationalError:
        result["cache"] = {"table_exists": False, "row_count": 0}

    # 2. pe_descriptions status
    try:
        conn.execute("SELECT 1 FROM pe_descriptions LIMIT 0")
        row_count = conn.execute("SELECT COUNT(*) FROM pe_descriptions").fetchone()[0]
        pe_count = conn.execute(
            "SELECT COUNT(DISTINCT pe_number) FROM pe_descriptions"
        ).fetchone()[0]
        result["pe_descriptions"] = {
            "table_exists": True,
            "row_count": row_count,
            "distinct_pe_numbers": pe_count,
            "populated": row_count > 0,
        }
    except sqlite3.OperationalError:
        result["pe_descriptions"] = {"table_exists": False, "populated": False}

    # 3. Keyword hit summary from cache
    if result.get("cache", {}).get("table_exists"):
        try:
            kw_rows = conn.execute(
                f"SELECT matched_keywords_row, matched_keywords_desc FROM {_CACHE_TABLE}"
            ).fetchall()
            row_counts: dict[str, int] = {}
            desc_counts: dict[str, int] = {}
            for r in kw_rows:
                for kw in json.loads(r[0] or "[]"):
                    row_counts[kw] = row_counts.get(kw, 0) + 1
                for kw in json.loads(r[1] or "[]"):
                    desc_counts[kw] = desc_counts.get(kw, 0) + 1
            all_kw_counts = {kw: row_counts.get(kw, 0) + desc_counts.get(kw, 0) for kw in set(list(row_counts) + list(desc_counts))}
            result["keyword_hit_counts"] = {"row": row_counts, "desc": desc_counts, "combined": all_kw_counts}
            result["keywords_with_zero_hits"] = [
                kw for kw in _HYPERSONICS_KEYWORDS if kw not in all_kw_counts
            ]
        except Exception:
            pass

    return result
