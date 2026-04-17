"""
Keyword Explorer endpoints.

A generalized version of the Hypersonics page that accepts user-supplied
keywords.  Users enter keywords, the system builds a cache (with PDF mining),
and they can preview results and download a customized XLSX.

Endpoints:
  POST /api/v1/explorer/build             — start async cache build
  GET  /api/v1/explorer/status            — poll build progress
  GET  /api/v1/explorer                   — JSON PE-level summary + available columns
  POST /api/v1/explorer/download/xlsx     — XLSX with user-selected columns
  GET  /api/v1/explorer/desc/{pe_number}  — lazy-load description text
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import threading
import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Query
from fastapi.responses import Response

from api.database import get_db
from api.routes.keyword_helpers import FY_END, FY_START, find_matched_keywords
from utils.config import R2_TYPES
from api.routes.keyword_search import (
    build_cache_table,
    cache_rows_to_dicts,
    load_per_fy_descriptions,
    lookup_cache_description,
)
from api.routes.keyword_xlsx import build_keyword_xlsx
from utils.config import EXHIBIT_R1
from utils.fuzzy_match import expand_keywords

logger = logging.getLogger(__name__)

# ── Hypersonics preset ────────────────────────────────────────────────────────

_HYPERSONICS_KEYWORDS = [
    # Generic / cross-program
    "hypersonic", "boost glide", "glide body", "glide vehicle", "scramjet",
    # Offensive — Air Force
    "ARRW", "AGM-183", "HACM", "HCSW",
    # Offensive — Army
    "LRHW", "Dark Eagle", "OpFires",
    # Offensive — Navy / Joint
    "C-HGB", "CHGB", "conventional prompt strike", "prompt strike",
    # Offensive — Navy / SM-6 / OASUW
    "offensive anti", "oasuw", "standard missile 6", "sm-6",
    "blk ib", "increment ii",
    # Generic speed / regime
    "high speed", "mach", "conventional prompt",
    # Defensive / tracking
    "Glide Phase Interceptor", "HBTSS",
]

_EXTRA_PES = [
    "0101101F", "0210600A", "0601102F", "0601153N", "0602102F",
    "0602114N", "0602235N", "0602602F", "0602750N", "0603032F",
    "0603183D8Z", "0603273F", "0603467E", "0603601F", "0603673N",
    "0603680D8Z", "0603680F", "0603941D8Z", "0603945D8Z", "0604250D8Z",
    "0604331D8Z", "0604940D8Z", "0605456A", "0607210D8Z", "0902199D8Z",
]

_PRESETS: dict[str, dict] = {
    "hypersonics": {
        "keywords": _HYPERSONICS_KEYWORDS,
        "extra_pes": _EXTRA_PES,
        "label": "Hypersonics Programs",
    },
}

router = APIRouter(prefix="/explorer", tags=["explorer"])

# ── Input validation constants ────────────────────────────────────────────────

MAX_KEYWORDS = 50
MIN_KEYWORD_LEN = 2
MAX_KEYWORD_LEN = 100
MAX_CACHE_TABLES = 50
_KEYWORD_RE = re.compile(r"^[a-zA-Z0-9\s\-/&.]+$")

# ── Build progress tracking ──────────────────────────────────────────────────

# Module-level dict: keyword_set_id → progress state.
# Protected by a lock for thread safety (BackgroundTasks run in threads).
_build_lock = threading.Lock()
_build_progress: dict[str, dict[str, Any]] = {}
_PROGRESS_TTL_SECONDS = 24 * 3600  # evict finished entries after 24 hours

# ── Fixed columns for XLSX export ─────────────────────────────────────────────

_FIXED_COLUMNS: list[tuple[str, str]] = [
    ("PE Number", "pe_number"),
    ("Service/Org", "organization_name"),
    ("Exhibit Type", "exhibit_type"),
    ("Line Item Title", "line_item_title"),
    ("Alternate Titles", "lineage_note"),
    ("Budget Activity", "budget_activity_norm"),
    ("Appropriation", "appropriation_title"),
    ("Color of Money", "color_of_money"),
]

# Per-FY sub-columns (($K), In Total, Source, Description, Keywords)
# are always included for each active fiscal year.

_COL_TO_FIELD: dict[str, str] = {h: f for h, f in _FIXED_COLUMNS}

# Pre-compiled patterns for FY column name parsing in _extract_column_value
_FY_AMOUNT_COL_RE = re.compile(r"FY(\d{4})\s*\(\$K\)")
_FY_SOURCE_COL_RE = re.compile(r"FY(\d{4})\s*Source")
_FY_DESC_COL_RE = re.compile(r"FY(\d{4})\s*Description")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _keyword_set_id(keywords: list[str], extra_pes: list[str] | None = None) -> str:
    """SHA-256 hash of sorted lowercase keywords + optional extra PEs."""
    normalized = sorted(set(kw.strip().lower() for kw in keywords if kw.strip()))
    key = ",".join(normalized)
    if extra_pes:
        key += "|" + ",".join(sorted(set(pe.strip().upper() for pe in extra_pes if pe.strip())))
    return hashlib.sha256(key.encode()).hexdigest()


def _cache_table_name(kw_id: str) -> str:
    """Return cache table name from keyword set ID."""
    return f"explorer_cache_{kw_id[:16]}"


class KeywordValidationError(ValueError):
    """Raised by _parse_keywords with a pre-sanitized user-facing message.

    The exception's ``str()`` is intentionally safe to echo back to HTTP
    clients — all messages are authored in this module, never contain
    traceback data, and cap at MAX_KEYWORD_LEN + 100 characters.  Endpoints
    can catch this specific subclass instead of bare ValueError to make the
    safety contract explicit for reviewers and static analysis.
    """


_MAX_USER_ERROR_LEN = MAX_KEYWORD_LEN + 100


def _public_error_message(exc: KeywordValidationError) -> str:
    """Return a length-bounded, newline-free message safe to send to clients."""
    msg = exc.args[0] if exc.args else "Invalid keywords"
    return str(msg).split("\n", 1)[0][:_MAX_USER_ERROR_LEN]


def _parse_keywords(raw: str) -> list[str]:
    """Parse and validate comma-separated keywords string.

    Returns cleaned keyword list. Raises KeywordValidationError on failure.
    """
    if not raw or not raw.strip():
        raise KeywordValidationError("No keywords provided")

    parts = [k.strip() for k in raw.split(",") if k.strip()]
    if not parts:
        raise KeywordValidationError("No keywords provided")
    if len(parts) > MAX_KEYWORDS:
        raise KeywordValidationError(f"Too many keywords (max {MAX_KEYWORDS})")

    cleaned: list[str] = []
    for kw in parts:
        if len(kw) < MIN_KEYWORD_LEN:
            raise KeywordValidationError(
                f"Keyword '{kw}' is too short (min {MIN_KEYWORD_LEN} characters)"
            )
        if len(kw) > MAX_KEYWORD_LEN:
            raise KeywordValidationError(
                f"Keyword '{kw}' is too long (max {MAX_KEYWORD_LEN} characters)"
            )
        if not _KEYWORD_RE.match(kw):
            raise KeywordValidationError(
                f"Keyword '{kw}' contains invalid characters"
            )
        cleaned.append(kw)
    return cleaned


def _parse_extra_pes(raw: str) -> list[str]:
    """Parse comma-separated PE numbers into an uppercase list."""
    if not raw:
        return []
    return [pe.strip().upper() for pe in raw.split(",") if pe.strip()]


def _resolve_keyword_set(
    keywords: str, extra_pes: str = ""
) -> tuple[list[str], list[str] | None, str]:
    """Parse keywords + extra PEs and return (keyword_list, pe_list, kw_id).

    Raises ValueError if keywords fail validation.
    """
    keyword_list = _parse_keywords(keywords)
    pe_list = _parse_extra_pes(extra_pes) or None
    kw_id = _keyword_set_id(keyword_list, pe_list)
    return keyword_list, pe_list, kw_id


def _ensure_meta_table(conn: sqlite3.Connection) -> None:
    """Create the explorer_cache_meta table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS explorer_cache_meta (
            keyword_set_id   TEXT PRIMARY KEY,
            keywords_json    TEXT NOT NULL,
            table_name       TEXT NOT NULL,
            built_at         REAL NOT NULL,
            last_accessed_at REAL NOT NULL,
            row_count        INTEGER
        )
    """)


def _prune_old_caches(conn: sqlite3.Connection) -> None:
    """Remove explorer cache tables exceeding MAX_CACHE_TABLES (oldest first)."""
    _ensure_meta_table(conn)
    rows = conn.execute(
        "SELECT keyword_set_id, table_name FROM explorer_cache_meta "
        "ORDER BY last_accessed_at DESC"
    ).fetchall()
    if len(rows) <= MAX_CACHE_TABLES:
        return
    for kw_id, table_name in rows[MAX_CACHE_TABLES:]:
        conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        conn.execute("DELETE FROM explorer_cache_meta WHERE keyword_set_id = ?", [kw_id])
    conn.commit()
    logger.info("Pruned %d old explorer caches", len(rows) - MAX_CACHE_TABLES)


def _prune_stale_progress() -> None:
    """Remove finished entries from _build_progress older than TTL (call under lock)."""
    cutoff = time.time() - _PROGRESS_TTL_SECONDS
    stale = [
        k for k, v in _build_progress.items()
        if v.get("state") in ("ready", "error") and v.get("_ts", 0) < cutoff
    ]
    for k in stale:
        del _build_progress[k]


def _do_build(
    db_path: str,
    kw_id: str,
    keywords: list[str],
    expanded: list[str],
    extra_pes: list[str] | None = None,
) -> None:
    """Background task: build the explorer cache table.

    Runs in a separate thread via BackgroundTasks. Uses its own DB connection
    since SQLite connections aren't thread-safe.
    """
    cache_table = _cache_table_name(kw_id)

    def _progress(step: str, detail: dict[str, Any]) -> None:
        with _build_lock:
            _build_progress[kw_id] = {
                "state": "building",
                "progress": step,
                **detail,
            }

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")

        _ensure_meta_table(conn)
        _prune_old_caches(conn)

        row_count = build_cache_table(
            conn, cache_table, expanded, expanded,
            fy_start=FY_START, fy_end=FY_END,
            progress_callback=_progress,
            extra_pes=extra_pes,
        )

        # Record in metadata
        now = time.time()
        conn.execute(
            "INSERT OR REPLACE INTO explorer_cache_meta "
            "(keyword_set_id, keywords_json, table_name, built_at, last_accessed_at, row_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [kw_id, json.dumps(keywords), cache_table, now, now, row_count],
        )
        conn.commit()
        conn.close()

        with _build_lock:
            _build_progress[kw_id] = {
                "state": "ready",
                "progress": "done",
                "row_count": row_count,
                "_ts": time.time(),
            }
    except Exception as e:
        logger.exception("Explorer cache build failed for %s", kw_id)
        with _build_lock:
            _build_progress[kw_id] = {
                "state": "error",
                "progress": str(e),
                "_ts": time.time(),
            }


# ── POST /api/v1/explorer/build ──────────────────────────────────────────────

@router.post(
    "/build",
    summary="Start async cache build for a keyword set",
)
def start_build(
    keywords: str = Query(..., description="Comma-separated keywords"),
    extra_pes: str = Query("", description="Comma-separated PE numbers to force-include"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Kick off a background cache build and return immediately."""
    try:
        keyword_list, pe_list, kw_id = _resolve_keyword_set(keywords, extra_pes)
    except KeywordValidationError as e:
        return {"error": _public_error_message(e)}

    expanded = expand_keywords(keyword_list)

    with _build_lock:
        _prune_stale_progress()

    # Check if cache already exists and is fresh
    _ensure_meta_table(conn)
    meta = conn.execute(
        "SELECT built_at, row_count FROM explorer_cache_meta WHERE keyword_set_id = ?",
        [kw_id],
    ).fetchone()

    if meta:
        age_hours = (time.time() - meta[0]) / 3600
        if age_hours < 24:
            # Cache is fresh — update access time and return ready
            conn.execute(
                "UPDATE explorer_cache_meta SET last_accessed_at = ? WHERE keyword_set_id = ?",
                [time.time(), kw_id],
            )
            conn.commit()
            with _build_lock:
                _build_progress[kw_id] = {
                    "state": "ready",
                    "progress": "done",
                    "row_count": meta[1],
                    "_ts": time.time(),
                }
            return {
                "keyword_set_id": kw_id,
                "keywords": keyword_list,
                "expanded_keywords": expanded,
                "state": "ready",
            }

    # Check if build is already in progress
    with _build_lock:
        current = _build_progress.get(kw_id, {})
        if current.get("state") == "building":
            return {
                "keyword_set_id": kw_id,
                "keywords": keyword_list,
                "expanded_keywords": expanded,
                "state": "building",
            }

        _build_progress[kw_id] = {
            "state": "building",
            "progress": "starting",
        }

    # Get DB path for the background thread
    db_path = conn.execute("PRAGMA database_list").fetchone()[2]

    background_tasks.add_task(_do_build, db_path, kw_id, keyword_list, expanded, pe_list or None)

    return {
        "keyword_set_id": kw_id,
        "keywords": keyword_list,
        "expanded_keywords": expanded,
        "state": "building",
    }


# ── GET /api/v1/explorer/status ──────────────────────────────────────────────

@router.get(
    "/status",
    summary="Poll cache build progress",
)
def build_status(
    keywords: str = Query(..., description="Comma-separated keywords"),
    extra_pes: str = Query("", description="Comma-separated PE numbers (must match build call)"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return current build state for a keyword set.

    Checks in-memory progress first; falls back to the database so that
    completed builds survive process restarts / uvicorn reloads.
    """
    try:
        keyword_list, pe_list, kw_id = _resolve_keyword_set(keywords, extra_pes)
    except KeywordValidationError as e:
        return {"state": "error", "progress": _public_error_message(e)}

    with _build_lock:
        status = _build_progress.get(kw_id)

    # If in-memory says "ready" or "error", trust it
    if status and status.get("state") in ("ready", "error"):
        return {"keyword_set_id": kw_id, **status}

    # Check DB — the build may have finished (in this or a previous process)
    _ensure_meta_table(conn)
    meta = conn.execute(
        "SELECT row_count, built_at FROM explorer_cache_meta WHERE keyword_set_id = ?",
        [kw_id],
    ).fetchone()
    if meta is not None:
        # Refresh in-memory state so subsequent polls are fast
        ready = {"state": "ready", "progress": "done", "row_count": meta[0], "_ts": time.time()}
        with _build_lock:
            _build_progress[kw_id] = ready
        return {"keyword_set_id": kw_id, **ready}

    # In-memory says "building" but DB has no result yet — still in progress
    if status and status.get("state") == "building":
        return {"keyword_set_id": kw_id, **status}

    return {"state": "not_started", "keyword_set_id": kw_id}


# ── GET /api/v1/explorer ─────────────────────────────────────────────────────

@router.get(
    "",
    summary="PE-level summary and available columns for a keyword set",
)
def get_explorer_data(
    keywords: str = Query(..., description="Comma-separated keywords"),
    extra_pes: str = Query("", description="Comma-separated PE numbers (must match build call)"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return PE-level summary of cached results plus available download columns."""
    try:
        keyword_list, pe_list, kw_id = _resolve_keyword_set(keywords, extra_pes)
    except KeywordValidationError as e:
        return {"error": _public_error_message(e)}

    cache_table = _cache_table_name(kw_id)
    expanded = expand_keywords(keyword_list)

    # Build PE-level summary via SQL aggregate (avoids loading all rows)
    try:
        pe_rows = conn.execute(f"""
            SELECT
                pe_number,
                MAX(CASE WHEN exhibit_type = '{EXHIBIT_R1}' THEN line_item_title END) AS r1_title,
                MAX(line_item_title) AS any_title,
                MAX(organization_name) AS service,
                COUNT(*) AS total_sub_elements,
                SUM(CASE WHEN matched_keywords_row != '[]' OR matched_keywords_desc != '[]' THEN 1 ELSE 0 END) AS matching
            FROM {cache_table}
            GROUP BY pe_number
            ORDER BY pe_number
        """).fetchall()
    except sqlite3.OperationalError:
        return {"error": "Cache not built yet. Call POST /build first."}

    total_rows = sum(r[4] for r in pe_rows)

    pe_summary: list[dict] = []
    for r in pe_rows:
        pe_summary.append({
            "pe_number": r[0],
            "pe_title": r[1] or r[2] or r[0],
            "service": r[3] or "",
            "total_sub_elements": r[4],
            "matching_sub_elements": r[5],
        })

    # Detect active years (which FY columns have any non-null data) — single query
    year_range = list(range(FY_START, FY_END + 1))
    active_years = []
    if pe_rows:
        checks = ", ".join(
            f"MAX(CASE WHEN fy{yr} IS NOT NULL THEN 1 ELSE 0 END) AS has_{yr}"
            for yr in year_range
        )
        fy_check_row = conn.execute(f"SELECT {checks} FROM {cache_table}").fetchone()
        if fy_check_row:
            active_years = [yr for i, yr in enumerate(year_range) if fy_check_row[i]]

    # Build available columns list (static + dynamic FY columns).
    # Per-year columns are offered as an interleaved [value, source, description]
    # triple so selecting them in order keeps the output columns grouped by year.
    available_columns = [h for h, _f in _FIXED_COLUMNS]
    for yr in active_years:
        available_columns.append(f"FY{yr} ($K)")
        available_columns.append(f"FY{yr} Source")
        available_columns.append(f"FY{yr} Description")

    # Default selected columns — fixed metadata, then an interleaved FY triple
    # (value / source / description) per active year so the sheet reads left to
    # right in chronological order with descriptions adjacent to amounts.
    default_columns = [
        "PE Number", "Service/Org", "Exhibit Type", "Line Item Title",
        "Color of Money",
    ]
    for yr in active_years:
        default_columns.append(f"FY{yr} ($K)")
        default_columns.append(f"FY{yr} Source")
        default_columns.append(f"FY{yr} Description")

    return {
        "keyword_set_id": kw_id,
        "keywords": keyword_list,
        "expanded_keywords": expanded,
        "pe_summary": pe_summary,
        "total_pes": len(pe_summary),
        "total_rows": total_rows,
        "active_years": active_years,
        "available_columns": available_columns,
        "default_columns": default_columns,
    }


# ── POST /api/v1/explorer/download/xlsx ──────────────────────────────────────

@router.post(
    "/download/xlsx",
    summary="Download explorer results as XLSX",
    response_class=Response,
)
def download_explorer_xlsx(
    keywords: str = Body(..., description="Comma-separated keywords"),
    matching_only: bool = Body(False, description="Only include directly matching sub-elements"),
    include_intotal: bool = Body(True, description="Include per-year In Total (Y/N/P) columns"),
    include_source: bool = Body(True, description="Include FY Source columns"),
    include_description: bool = Body(True, description="Include FY Description columns"),
    include_desc_keywords: bool = Body(True, description="Include per-FY Keywords columns"),
    fiscal_years: str = Body("", description="Comma-separated FYs to include (empty = all active)"),
    extra_pes: str = Body("", description="Comma-separated PE numbers (must match build call)"),
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """Generate XLSX with fixed columns, optional sub-columns, and user-selected fiscal years.

    Uses a fixed column layout. Y/N/P is computed per line per FY.
    """
    try:
        keyword_list, pe_list, kw_id = _resolve_keyword_set(keywords, extra_pes)
    except KeywordValidationError as e:
        return Response(
            content=_public_error_message(e).encode(),
            media_type="text/plain",
            status_code=400,
        )

    cache_table = _cache_table_name(kw_id)

    try:
        sql = f"SELECT * FROM {cache_table} ORDER BY pe_number, exhibit_type, line_item_title"
        raw_rows = conn.execute(sql).fetchall()
    except sqlite3.OperationalError:
        return Response(content=b"Cache not built", media_type="text/plain", status_code=400)

    items = cache_rows_to_dicts(raw_rows)

    if matching_only:
        items = [
            r for r in items
            if r.get("matched_keywords_row")
        ]

    if not items:
        return Response(content=b"No rows to export", media_type="text/plain", status_code=400)

    year_range = list(range(FY_START, FY_END + 1))
    active_years = [
        yr for yr in year_range
        if any(r.get(f"fy{yr}") is not None for r in items)
    ]

    # Filter to user-selected fiscal years (if specified)
    if fiscal_years and fiscal_years.strip():
        requested_fys = set()
        for fy in fiscal_years.split(","):
            fy = fy.strip()
            try:
                requested_fys.add(int(fy))
            except ValueError:
                pass
        if requested_fys:
            active_years = [yr for yr in active_years if yr in requested_fys]

    desc_by_pe_fy = load_per_fy_descriptions(
        conn, {r.get("pe_number", "") for r in items}
    )

    # Per-FY description keyword matching
    fy_desc_kws: dict[tuple[str, str], list[str]] = {}
    for (pe, fy), desc_text in desc_by_pe_fy.items():
        kws = find_matched_keywords([desc_text], keyword_list)
        if kws:
            fy_desc_kws[(pe, fy)] = kws

    # Precompute PEs that have at least one per-FY description keyword match (O(1) lookup)
    pes_with_desc_match = {pe for pe, _fy in fy_desc_kws}

    # Determine which PEs have ANY keyword match.
    # matched_keywords_desc is PE-level (too broad for inclusion filtering);
    # only row-level title hits and per-FY description hits count.
    # Extra PEs are always included (user explicitly requested them).
    pes_with_match: set[str] = set(pe_list) if pe_list else set()
    pe_has_r2_match: set[str] = set()
    for r in items:
        pe = r.get("pe_number", "")
        has_row_match = bool(r.get("matched_keywords_row"))
        if has_row_match or pe in pes_with_desc_match:
            pes_with_match.add(pe)
            if r.get("exhibit_type") in R2_TYPES:
                pe_has_r2_match.add(pe)

    # Filter out PEs with zero matches in all rows and all FY descriptions
    items = [r for r in items if r.get("pe_number", "") in pes_with_match]

    if not items:
        return Response(content=b"No matching rows to export", media_type="text/plain", status_code=400)

    xlsx_bytes = build_keyword_xlsx(
        items=items,
        active_years=active_years,
        desc_by_pe_fy=desc_by_pe_fy,
        fy_desc_kws=fy_desc_kws,
        pe_has_r2_match=pe_has_r2_match,
        fixed_columns=list(_FIXED_COLUMNS),
        include_source=include_source,
        include_description=include_description,
        include_intotal=include_intotal,
        include_desc_keywords=include_desc_keywords,
        sheet_title="Explorer",
        keywords=keyword_list,
    )

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="explorer_{time.strftime("%Y%m%d_%H%M%S")}.xlsx"'},
    )


# ── GET /api/v1/explorer/presets ──────────────────────────────────────────────

@router.get(
    "/presets/{name}",
    summary="Return keyword and PE lists for a named preset",
)
def get_preset(name: str) -> dict:
    """Return keywords and extra_pes for a named search preset."""
    if name not in _PRESETS:
        return {"error": f"Unknown preset: {name}", "available": list(_PRESETS)}
    return _PRESETS[name]


def _extract_column_value(
    row: dict,
    col_name: str,
    year_range: list[int],
    desc_by_pe_fy: dict[tuple[str, str], str] | None = None,
    in_totals: bool | None = None,
) -> Any:
    """Extract a cell value from a cache row dict for a given column name."""
    if col_name == "In Totals":
        if in_totals is None:
            in_totals = bool(
                row.get("matched_keywords_row") or row.get("matched_keywords_desc")
            )
        return "Yes" if in_totals else ""

    # Static columns
    field = _COL_TO_FIELD.get(col_name)
    if field:
        val = row.get(field, "")
        # Format list fields
        if field in ("matched_keywords_row", "matched_keywords_desc"):
            if isinstance(val, list):
                return ", ".join(val)
        return val if val is not None else ""

    # FY amount columns: "FY2024 ($K)"
    m = _FY_AMOUNT_COL_RE.match(col_name)
    if m:
        yr = int(m.group(1))
        return row.get(f"fy{yr}")

    # FY source columns: "FY2024 Source"
    m = _FY_SOURCE_COL_RE.match(col_name)
    if m:
        yr = int(m.group(1))
        return row.get("refs", {}).get(f"fy{yr}", "")

    # FY description columns: "FY2024 Description"
    m = _FY_DESC_COL_RE.match(col_name)
    if m:
        yr = int(m.group(1))
        if desc_by_pe_fy is None:
            return ""
        pe = row.get("pe_number", "")
        return desc_by_pe_fy.get((pe, str(yr)), "")

    return ""


# ── GET /api/v1/explorer/desc/{pe_number} ────────────────────────────────────

@router.get(
    "/desc/{pe_number}",
    summary="Get description text for a PE from explorer cache",
)
def get_description(
    pe_number: str,
    keywords: str = Query(..., description="Comma-separated keywords"),
    project: str | None = None,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return description_text for a PE from the explorer cache."""
    try:
        keyword_list, _, kw_id = _resolve_keyword_set(keywords)
    except ValueError:
        return {"description": None}
    cache_table = _cache_table_name(kw_id)
    desc = lookup_cache_description(conn, cache_table, pe_number, project=project)
    return {"description": desc}
