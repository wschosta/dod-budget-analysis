"""
Shared keyword-search cache-building logic.

Provides the pivot/cache/PDF-mining pipeline used by the Keyword Explorer.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from itertools import groupby
from typing import Any

from utils.database import get_amount_columns

# Re-exports (preserve existing import paths for explorer.py and tests)
from api.routes.keyword_helpers import (  # noqa: F401
    BA_CANONICAL,
    FY_END,
    FY_START,
    LEVENSHTEIN_THRESHOLD,
    ORG_FROM_PATH,
    PE_TITLE_RE,
    SEARCH_COLS,
    SKIP_RAW_TITLES,
    HIDDEN_LOOKUP_COL,
    PE_NUMBER_STRICT_CI,
    SPILL_MAX_ROW,
    cache_ddl,
    color_of_money,
    find_matched_keywords,
    in_clause,
    is_garbage_description,
    like_clauses,
    normalize_budget_activity,
    safe_json_list,
)
from api.routes.keyword_xlsx import build_keyword_xlsx, xlsx_base_styles  # noqa: F401
from api.routes.keyword_r2 import (  # noqa: F401
    annotate_cross_pe_lineages,
    consolidate_r2_timeseries,
    mine_pdf_subelements,
    normalize_program_name,
    parse_r2_cost_block,
)
from api.routes.keyword_r2 import (
    _aggregate_r2_funding_into_r1_stubs,
    _extract_r1_titles_for_stubs,
)

logger = logging.getLogger(__name__)

# ── PE discovery ──────────────────────────────────────────────────────────────


def collect_matching_pe_numbers_split(
    conn: sqlite3.Connection,
    keywords: list[str],
    desc_keywords: list[str],
    search_cols: list[str] | None = None,
) -> tuple[tuple[set[str], set[str]], set[str]]:
    """Return (budget_lines_matched, desc_matched) PE number sets.

    budget_lines_matched: PEs found via keyword search in budget_lines columns.
    desc_matched: additional PEs found via narrative keyword search in pe_descriptions.
    The union is the full matched set for the cache.
    """
    if search_cols is None:
        search_cols = SEARCH_COLS

    bl_matched: set[str] = set()

    # (a0) Direct PE number match — detect keywords that look like PE numbers
    pe_keywords = [kw for kw in keywords if PE_NUMBER_STRICT_CI.match(kw.strip())]
    if pe_keywords:
        pe_upper = [pk.strip().upper() for pk in pe_keywords]
        ph, params = in_clause(pe_upper)
        rows = conn.execute(
            f"SELECT DISTINCT pe_number FROM budget_lines WHERE pe_number IN ({ph})",
            params,
        ).fetchall()
        bl_matched.update(r[0] for r in rows if r[0])
        # Fallback: check pe_index for PDF-only PEs not in budget_lines
        remaining_pes = set(pe_upper) - bl_matched
        if remaining_pes:
            try:
                rp, rp_params = in_clause(remaining_pes)
                pi_rows = conn.execute(
                    f"SELECT DISTINCT pe_number FROM pe_index WHERE pe_number IN ({rp})",
                    rp_params,
                ).fetchall()
                bl_matched.update(r[0] for r in pi_rows if r[0])
            except sqlite3.OperationalError:
                pass  # pe_index table may not exist

    # (a) Budget-lines keyword match
    kw_where, kw_params = like_clauses(search_cols, keywords)
    rows = conn.execute(
        f"SELECT DISTINCT pe_number FROM budget_lines WHERE {kw_where}", kw_params
    ).fetchall()
    bl_matched.update(r[0] for r in rows if r[0])

    # (b) pe_descriptions narrative match
    desc_matched: set[str] = set()
    try:
        conn.execute("SELECT 1 FROM pe_descriptions LIMIT 0")
        desc_where, desc_params = like_clauses(["description_text"], desc_keywords)
        rows = conn.execute(
            f"SELECT DISTINCT pe_number FROM pe_descriptions WHERE {desc_where}",
            desc_params,
        ).fetchall()
        desc_matched.update(r[0] for r in rows if r[0])
    except sqlite3.OperationalError:
        pass

    # Remove overlap so desc_matched only contains extras
    desc_matched -= bl_matched
    return (bl_matched, desc_matched), bl_matched | desc_matched


# ── Description helpers ───────────────────────────────────────────────────────


def get_description_map(
    conn: sqlite3.Connection,
    pe_numbers: set[str],
) -> dict[str, str]:
    """Build PE → truncated description text map for UI display."""
    if not pe_numbers:
        return {}
    try:
        conn.execute("SELECT 1 FROM pe_descriptions LIMIT 0")
    except sqlite3.OperationalError:
        return {}

    ph, pe_list = in_clause(pe_numbers)
    rows = conn.execute(
        f"SELECT pe_number, description_text, "
        f"CASE "
        f"  WHEN section_header LIKE '%Mission Description%' THEN 1 "
        f"  WHEN section_header LIKE '%Accomplishments%' THEN 2 "
        f"  WHEN section_header LIKE '%Acquisition Strategy%' THEN 3 "
        f"  ELSE 4 END AS priority "
        f"FROM pe_descriptions "
        f"WHERE pe_number IN ({ph}) AND section_header IS NOT NULL "
        f"ORDER BY pe_number, priority",
        pe_list,
    ).fetchall()

    # Group by PE, take top 3 per PE
    result: dict[str, str] = {}
    for pe, group in groupby(rows, key=lambda r: r[0]):
        texts = [r[1] for r in group if r[1]][:3]
        text = " ".join(texts)
        if len(text) > 2000:
            text = text[:2000] + "…"
        if text.strip():
            result[pe] = text
    return result


def get_desc_keyword_map(
    conn: sqlite3.Connection,
    pe_numbers: set[str],
    desc_keywords: list[str],
) -> dict[str, list[str]]:
    """Build PE → list of desc_keywords that match in pe_descriptions (via SQL LIKE)."""
    if not pe_numbers or not desc_keywords:
        return {}
    try:
        conn.execute("SELECT 1 FROM pe_descriptions LIMIT 0")
    except sqlite3.OperationalError:
        return {}

    ph, pe_list = in_clause(pe_numbers)

    # Single query: fetch all (pe_number, description_text) pairs
    rows = conn.execute(
        f"SELECT DISTINCT pe_number, description_text FROM pe_descriptions "
        f"WHERE pe_number IN ({ph})",
        pe_list,
    ).fetchall()

    # Application-side keyword matching
    result: dict[str, list[str]] = {}
    for pe, desc_text in rows:
        if not desc_text:
            continue
        desc_lower = desc_text.lower()
        for kw in desc_keywords:
            if kw.lower() in desc_lower:
                result.setdefault(pe, [])
                if kw not in result[pe]:
                    result[pe].append(kw)

    return result


# ── Query helpers ─────────────────────────────────────────────────────────────


def lookup_cache_description(
    conn: sqlite3.Connection,
    cache_table: str,
    pe_number: str,
    project: str | None = None,
    prefer_exhibit: str | None = None,
) -> str | None:
    """Look up description_text from a cache table. Returns None on miss.

    If *prefer_exhibit* is set (e.g. ``'r2'``), tries that exhibit type first
    before falling back to any row for the PE.
    """
    try:
        if project:
            row = conn.execute(
                f"SELECT description_text FROM {cache_table} "
                "WHERE pe_number = ? AND line_item_title = ? AND description_text IS NOT NULL LIMIT 1",
                [pe_number, project],
            ).fetchone()
        elif prefer_exhibit:
            row = conn.execute(
                f"SELECT description_text FROM {cache_table} "
                "WHERE pe_number = ? AND exhibit_type = ? AND description_text IS NOT NULL LIMIT 1",
                [pe_number, prefer_exhibit],
            ).fetchone()
            if not row:
                row = conn.execute(
                    f"SELECT description_text FROM {cache_table} "
                    "WHERE pe_number = ? AND description_text IS NOT NULL LIMIT 1",
                    [pe_number],
                ).fetchone()
        else:
            row = conn.execute(
                f"SELECT description_text FROM {cache_table} "
                "WHERE pe_number = ? AND description_text IS NOT NULL LIMIT 1",
                [pe_number],
            ).fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None


def apply_filters(
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
    return (" AND ".join(parts), params) if parts else ("", [])


def cache_rows_to_dicts(
    rows: list[sqlite3.Row],
    fy_start: int = FY_START,
    fy_end: int = FY_END,
) -> list[dict]:
    """Convert cache rows to dicts with refs nested structure."""
    year_range = list(range(fy_start, fy_end + 1))
    ref_keys = [f"fy{yr}_ref" for yr in year_range]
    fy_labels = [f"fy{yr}" for yr in year_range]
    json_cache: dict[str, list] = {}
    result: list[dict] = []
    for r in rows:
        d = dict(r)
        for field in ("matched_keywords_row", "matched_keywords_desc"):
            raw = d.get(field, "[]")
            if raw not in json_cache:
                json_cache[raw] = safe_json_list(raw)
            d[field] = json_cache[raw]
        refs: dict[str, str] = {}
        for ref_key, fy_label in zip(ref_keys, fy_labels):
            val = d.pop(ref_key, None)
            if val:
                refs[fy_label] = val
        d["refs"] = refs
        result.append(d)
    return result


def load_per_fy_descriptions(
    conn: sqlite3.Connection,
    pe_numbers: list[str] | set[str],
    min_length: int = 20,
) -> dict[tuple[str, str], str]:
    """Return a ``(pe_number, fiscal_year)`` → description text map.

    Pulled from ``pe_descriptions`` so each year's column can display narrative
    text taken from that year's submission. Priority order: Mission Description
    → Accomplishments → Acquisition Strategy. Descriptions shorter than
    ``min_length`` characters (after stripping) are filtered out as noise.
    """
    pes = sorted({pe for pe in pe_numbers if pe})
    if not pes:
        return {}

    try:
        conn.execute("SELECT 1 FROM pe_descriptions LIMIT 0")
    except sqlite3.OperationalError:
        return {}

    ph, pe_params = in_clause(pes)
    rows = conn.execute(
        f"SELECT pe_number, fiscal_year, section_header, description_text "
        f"FROM pe_descriptions "
        f"WHERE pe_number IN ({ph}) "
        f"  AND section_header IS NOT NULL "
        f"ORDER BY pe_number, fiscal_year, "
        f"  CASE "
        f"    WHEN section_header LIKE '%Mission Description%' THEN 1 "
        f"    WHEN section_header LIKE '%Accomplishments%' THEN 2 "
        f"    WHEN section_header LIKE '%Acquisition Strategy%' THEN 3 "
        f"    ELSE 4 END",
        pe_params,
    ).fetchall()

    result: dict[tuple[str, str], str] = {}
    for pe_num, fiscal_year, _section_header, description_text in rows:
        if not description_text:
            continue
        key = (pe_num, fiscal_year)
        if key in result:
            continue
        text = description_text.strip()
        if len(text) < min_length:
            continue
        result[key] = text
    return result



# ── Cache builder helpers ─────────────────────────────────────────────────────


def _insert_cache_rows(
    conn: sqlite3.Connection,
    all_rows: list[dict[str, Any]],
    keywords: list[str],
    desc_map: dict[str, str],
    r1_ba: dict[str, str],
    year_range: list[int],
    insert_sql: str,
) -> int:
    """Insert assembled rows into the cache table, computing keyword matches and BA/CoM."""
    batch: list[list] = []
    for d in all_rows:
        text_fields = [
            d.get("line_item_title"),
            d.get("account_title"),
            d.get("budget_activity_title"),
        ]
        row_kws = find_matched_keywords(text_fields, keywords)

        ba_norm = normalize_budget_activity(
            d.get("budget_activity"), d.get("budget_activity_title")
        )
        if (not ba_norm or ba_norm == "Unknown") and d.get("budget_activity_title"):
            ba_norm = d["budget_activity_title"]
        elif not ba_norm or ba_norm == "Unknown":
            ba_norm = r1_ba.get(d["pe_number"]) or ba_norm

        com_val = d.get("_inherited_com") or color_of_money(d.get("appropriation_title"))

        vals = [
            d["pe_number"],
            d.get("organization_name"),
            d.get("exhibit_type"),
            d.get("line_item_title"),
            d.get("budget_activity"),
            d.get("budget_activity_title"),
            ba_norm,
            d.get("appropriation_title"),
            d.get("account_title"),
            com_val,
            json.dumps(row_kws) if row_kws else "[]",
            json.dumps(d.get("_desc_kws", [])) if d.get("_desc_kws") else "[]",
            # Prefer row-level description (R-2 project-specific); fall back to PE-level
            d.get("description_text")
            if d.get("description_text") and not is_garbage_description(d["description_text"])
            else (
                None
                if is_garbage_description(desc_map.get(d["pe_number"]))
                else desc_map.get(d["pe_number"])
            ),
            d.get("_consolidated_titles") or None,
        ]
        for yr in year_range:
            vals.append(d.get(f"fy{yr}"))
            vals.append(d.get(f"fy{yr}_ref"))

        batch.append(vals)

    if batch:
        conn.executemany(insert_sql, batch)
    return len(batch)


def _insert_stub_pes(
    conn: sqlite3.Connection,
    cache_table: str,
    extra_pes: list[str],
    matched_pes: set[str],
    year_range: list[int],
    insert_sql: str,
) -> int:
    """Insert stub R-1 rows for extra PEs that exist only in PDFs."""
    cached_pes = {
        r[0]
        for r in conn.execute(
            f"SELECT DISTINCT pe_number FROM {cache_table}"
        ).fetchall()
    }
    pdf_only_pes = (set(extra_pes) & matched_pes) - cached_pes
    if not pdf_only_pes:
        return 0

    pp, pp_params = in_clause(pdf_only_pes)
    pi_meta = conn.execute(
        f"SELECT pe_number, display_title, organization_name FROM pe_index WHERE pe_number IN ({pp})",
        pp_params,
    ).fetchall()
    pi_map = {r[0]: (r[1], r[2]) for r in pi_meta}
    stub_desc_map = get_description_map(conn, pdf_only_pes)
    count = 0
    for pe in sorted(pdf_only_pes):
        title, org = pi_map.get(pe, (None, None))
        desc = stub_desc_map.get(pe)
        if is_garbage_description(desc):
            desc = None
        vals = [
            pe, org, "r1", title or pe,
            None, None, None, None, None, "RDT&E",
            "[]", "[]", desc,
        ]
        for _yr in year_range:
            vals.extend([None, None])
        conn.execute(insert_sql, vals)
        count += 1
    logger.info("Cache: inserted %d stub rows for PDF-only extra PEs", len(pdf_only_pes))
    _extract_r1_titles_for_stubs(conn, cache_table, pdf_only_pes)
    return count


def _backfill_organization(
    conn: sqlite3.Connection,
    cache_table: str,
    year_range: list[int],
) -> None:
    """Back-fill organization_name from R-1 rows, source paths, and pe_index."""
    conn.execute(f"""
        UPDATE {cache_table} AS c
        SET organization_name = (
            SELECT r1.organization_name
            FROM {cache_table} r1
            WHERE r1.pe_number = c.pe_number
              AND r1.exhibit_type = 'r1'
              AND r1.organization_name IS NOT NULL
            LIMIT 1
        )
        WHERE c.exhibit_type = 'r2' AND c.organization_name IS NULL
    """)

    latest_ref_col = f"fy{year_range[-1]}_ref"
    fallback_ref_col = (
        f"fy{year_range[-2]}_ref" if len(year_range) > 1 else latest_ref_col
    )
    for path_fragment, org_name in ORG_FROM_PATH:
        conn.execute(
            f"""
            UPDATE {cache_table}
            SET organization_name = ?
            WHERE (organization_name IS NULL OR organization_name = '')
              AND ({latest_ref_col} LIKE ? OR {fallback_ref_col} LIKE ?)
            """,
            [org_name, f"%{path_fragment}%", f"%{path_fragment}%"],
        )

    try:
        conn.execute(f"""
            UPDATE {cache_table}
            SET organization_name = (
                SELECT pi.organization_name
                FROM pe_index pi
                WHERE pi.pe_number = {cache_table}.pe_number
                  AND pi.organization_name IS NOT NULL
                LIMIT 1
            )
            WHERE organization_name IS NULL OR organization_name = ''
        """)
    except sqlite3.OperationalError:
        pass


# ── Cache builder ─────────────────────────────────────────────────────────────


def build_cache_table(
    conn: sqlite3.Connection,
    cache_table: str,
    keywords: list[str],
    desc_keywords: list[str],
    fy_start: int = FY_START,
    fy_end: int = FY_END,
    search_cols: list[str] | None = None,
    progress_callback: Any | None = None,
    extra_pes: list[str] | None = None,
) -> int:
    """Full cache rebuild: keyword match → pivot → PDF mine → insert.

    Returns the number of rows inserted.

    *progress_callback*, if provided, is called with ``(step_name, detail_dict)``
    at key milestones so callers can surface build progress.
    """

    from utils.normalization import clean_r2_title as _clean_title

    def _progress(step: str, **kw: Any) -> None:
        if progress_callback:
            progress_callback(step, kw)

    _progress("collecting_pes")

    # 1. Collect matching PE numbers
    (bl_pes, _desc_pes), matched_pes = collect_matching_pe_numbers_split(
        conn,
        keywords,
        desc_keywords,
        search_cols,
    )

    # 1b. Include explicitly listed PEs
    if extra_pes:
        extra_set = set(extra_pes)
        # Check budget_lines first
        ep_ph, ep_params = in_clause(extra_set)
        existing = conn.execute(
            f"SELECT DISTINCT pe_number FROM budget_lines WHERE pe_number IN ({ep_ph})",
            ep_params,
        ).fetchall()
        found_extra = {r[0] for r in existing}
        # Also check pe_index for PDF-only PEs (e.g., D8Z Defense-Wide programs)
        remaining = extra_set - found_extra
        if remaining:
            try:
                rp, rp_params = in_clause(remaining)
                pi_rows = conn.execute(
                    f"SELECT DISTINCT pe_number FROM pe_index WHERE pe_number IN ({rp})",
                    rp_params,
                ).fetchall()
                found_extra |= {r[0] for r in pi_rows}
            except sqlite3.OperationalError:
                pass
        if found_extra:
            bl_pes |= found_extra
            matched_pes |= found_extra
            logger.info(
                "Extra PEs: %d requested, %d found", len(extra_set), len(found_extra)
            )

    if not matched_pes:
        conn.execute(f"DROP TABLE IF EXISTS {cache_table}")
        conn.execute(cache_ddl(cache_table, fy_start, fy_end))
        conn.commit()
        logger.info("No matching PEs found — cache table is empty.")
        _progress("done", row_count=0, pe_count=0)
        return 0

    _progress("building_pivot", pe_count=len(matched_pes))

    # 2. Get description text per PE
    desc_map = get_description_map(conn, matched_pes)

    # 3. Get amount columns
    all_amount_cols = set(get_amount_columns(conn))

    # 4. Build pivot query
    pe_placeholders, pe_params = in_clause(matched_pes)

    year_range = list(range(fy_start, fy_end + 1))
    year_parts: list[str] = []
    for yr in year_range:
        priority = [
            f"amount_fy{yr}_actual",
            f"amount_fy{yr}_enacted",
            f"amount_fy{yr}_total",
            f"amount_fy{yr}_request",
        ]
        available = [c for c in priority if c in all_amount_cols]
        if not available:
            coalesce_expr = "NULL"
        else:
            parts = [f"MAX(CASE WHEN {c} > 0 THEN {c} END)" for c in available]
            coalesce_expr = f"COALESCE({', '.join(parts)}, 0)"
        year_parts.append(f"{coalesce_expr} AS fy{yr}")
        year_parts.append(
            f"MAX(CASE WHEN {available[0]} IS NOT NULL THEN source_file END) AS fy{yr}_ref"
            if available
            else f"NULL AS fy{yr}_ref"
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
          AND CAST(fiscal_year AS INTEGER) >= {fy_start}
        GROUP BY pe_number, exhibit_type, line_item_title
        ORDER BY pe_number, exhibit_type, line_item_title
    """

    rows = conn.execute(sql, pe_params).fetchall()

    # 5. Recreate cache table
    conn.execute(f"DROP TABLE IF EXISTS {cache_table}")
    conn.execute(cache_ddl(cache_table, fy_start, fy_end))

    # 6. Insert enriched rows
    insert_cols = [
        "pe_number",
        "organization_name",
        "exhibit_type",
        "line_item_title",
        "budget_activity",
        "budget_activity_title",
        "budget_activity_norm",
        "appropriation_title",
        "account_title",
        "color_of_money",
        "matched_keywords_row",
        "matched_keywords_desc",
        "description_text",
        "lineage_note",
    ]
    for yr in year_range:
        insert_cols.extend([f"fy{yr}", f"fy{yr}_ref"])
    placeholders_insert = ", ".join("?" for _ in insert_cols)
    insert_sql = f"INSERT INTO {cache_table} ({', '.join(insert_cols)}) VALUES ({placeholders_insert})"

    # 6b. Mine PDF sub-elements BEFORE the merge pre-pass so r2 and r2_pdf
    # rows can be merged together.
    _progress("mining_pdfs", budget_line_rows=len(rows))

    pdf_subelements, discovered_pes = mine_pdf_subelements(
        conn,
        matched_pes,
        keywords,
        core_pes=bl_pes,
        fy_start=fy_start,
    )

    # For PEs discovered via R-2 keyword matches, also load their R-1 budget_lines rows
    if discovered_pes:
        disc_ph, disc_params = in_clause(discovered_pes)
        disc_sql = f"""
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
            WHERE pe_number IN ({disc_ph})
              AND CAST(fiscal_year AS INTEGER) >= {fy_start}
            GROUP BY pe_number, exhibit_type, line_item_title
            ORDER BY pe_number, exhibit_type, line_item_title
        """
        disc_rows = conn.execute(disc_sql, disc_params).fetchall()
        rows = list(rows) + list(disc_rows)
        logger.info(
            "PDF sub-element mining: discovered %d new PEs, added %d budget_lines rows",
            len(discovered_pes), len(disc_rows),
        )

    # ── Pre-pass: clean, deduplicate, and merge R-2 rows ──
    #
    # Collects ALL R-2 rows from both budget_lines (r2_pdf) and PDF mining (r2)
    # into r2_by_code, then merges by project code with prefix + Levenshtein
    # matching. This ensures r2 and r2_pdf rows for the same sub-element merge.

    from utils.normalization import normalize_r2_project_code
    from utils.fuzzy_match import _levenshtein_distance

    def _add_to_r2_groups(d: dict) -> None:
        """Clean an R-2 row and add it to r2_by_code for merge processing."""
        raw = d.get("line_item_title", "")
        cleaned_code, cleaned_title = _clean_title(raw)
        if cleaned_code is None and cleaned_title is None:
            raw_lower = raw.strip().lower()
            if not raw or raw_lower in SKIP_RAW_TITLES or raw_lower.startswith("total program element"):
                return
            cleaned_title = raw.strip()
        clean_title = f"{cleaned_code}: {cleaned_title}" if cleaned_code else (cleaned_title or raw)
        d["line_item_title"] = clean_title
        d["_project_code"] = normalize_r2_project_code(cleaned_code)
        d["_clean_title_only"] = cleaned_title or clean_title
        d["_consolidated"] = []
        key = (d["pe_number"], d["_project_code"] or clean_title)
        r2_by_code.setdefault(key, []).append(d)

    r1_rows: list[dict[str, Any]] = []
    r2_by_code: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    other_rows: list[dict[str, Any]] = []

    # Collect budget_lines rows (r2_pdf + non-R2 types)
    for r in rows:
        d = dict(r)
        et = d.get("exhibit_type", "")

        if et in ("r2", "r2_pdf"):
            _add_to_r2_groups(d)
        elif et == "r1":
            r1_rows.append(d)
            other_rows.append(d)
        else:
            other_rows.append(d)

    # Compute PE-level description keyword matches by scanning ALL pe_descriptions
    # rows (not just the single desc_map entry). This ensures PEs included via
    # description matches have their R-1 row marked with matched_keywords_desc.
    pe_desc_kws: dict[str, list[str]] = {}
    try:
        all_pe_nums: list[str] = sorted({str(d["pe_number"]) for d in other_rows if d.get("pe_number")}
                             | {d.get("pe_number", "") for group in r2_by_code.values() for d in group})
        if all_pe_nums:
            ph, ph_params = in_clause(all_pe_nums)
            desc_rows = conn.execute(
                f"SELECT pe_number, description_text FROM pe_descriptions "
                f"WHERE pe_number IN ({ph}) AND description_text IS NOT NULL",
                ph_params,
            ).fetchall()
            for pe_num, desc_text in desc_rows:
                if pe_num in pe_desc_kws:
                    continue  # already found keywords for this PE
                kws = find_matched_keywords([desc_text], desc_keywords)
                if kws:
                    pe_desc_kws[pe_num] = kws
    except sqlite3.OperationalError:
        pass  # pe_descriptions may not exist
    for d in other_rows:
        pe = d.get("pe_number", "")
        if pe in pe_desc_kws:
            d["_desc_kws"] = pe_desc_kws[pe]

    # Also collect PDF-mined r2 rows (from mine_pdf_subelements) into the same groups
    for item in pdf_subelements:
        raw_title = item["project_title"]
        if item.get("project_code"):
            raw_title = f"{item['project_code']}: {raw_title}"
        r2_desc = item.get("description_text", "")
        if is_garbage_description(r2_desc):
            r2_desc = ""
        fallback = desc_map.get(item["pe_number"])
        if is_garbage_description(fallback):
            fallback = None

        row_kws = item.get("_matched_r2_keywords") or find_matched_keywords(
            [raw_title], keywords
        )
        desc_kws = find_matched_keywords([r2_desc, raw_title], desc_keywords) if r2_desc else []
        desc_kws = [kw for kw in desc_kws if kw not in row_kws]

        d = {
            "pe_number": item["pe_number"],
            "organization_name": None,
            "exhibit_type": "r2",
            "line_item_title": raw_title,
            "budget_activity": None,
            "budget_activity_title": None,
            "appropriation_title": None,
            "account_title": item.get("pe_title"),
            "matched_keywords_row": json.dumps(row_kws) if row_kws else "[]",
            "matched_keywords_desc": json.dumps(desc_kws) if desc_kws else "[]",
            "description_text": r2_desc if r2_desc else fallback,
        }
        fy_refs = item.get("fy_refs", {})
        for yr in year_range:
            fy_key = f"fy{yr}"
            d[f"fy{yr}"] = item["fy_amounts"].get(fy_key)
            d[f"fy{yr}_ref"] = (
                fy_refs.get(fy_key)
                if item["fy_amounts"].get(fy_key) is not None
                else None
            )
        _add_to_r2_groups(d)

    # Fuzzy merge within each (pe, project_code) group.
    # Uses Levenshtein distance < 20% to merge near-duplicates.
    # Prefers r2 (Excel) metadata over r2_pdf; keeps longer title.
    # Keeps rows separate if titles differ substantially (e.g. Mk4A vs Mk4B).
    def _merge_into(target: dict[str, Any], source: dict[str, Any]) -> None:
        """Merge source row into target: FY amounts + consolidated titles."""
        # Prefer r2 exhibit_type
        if source.get("exhibit_type") == "r2" and target.get("exhibit_type") != "r2":
            for k in ("exhibit_type", "organization_name", "budget_activity",
                       "budget_activity_title", "appropriation_title", "account_title"):
                if source.get(k):
                    target[k] = source[k]
        # Keep longer title
        if len(source.get("_clean_title_only", "")) > len(target.get("_clean_title_only", "")):
            target["line_item_title"] = source["line_item_title"]
            target["_clean_title_only"] = source["_clean_title_only"]
        # Merge FY amounts (first non-null wins) and back-fill missing refs
        for yr in year_range:
            col = f"fy{yr}"
            ref_col = f"fy{yr}_ref"
            if target.get(col) is None and source.get(col) is not None:
                target[col] = source[col]
                if source.get(ref_col):
                    target[ref_col] = source[ref_col]
            elif target.get(col) is not None and not target.get(ref_col) and source.get(ref_col):
                target[ref_col] = source[ref_col]
        # Track consolidated title variants
        if source["line_item_title"] != target["line_item_title"]:
            target.setdefault("_consolidated", []).append(source["line_item_title"])
        target["_consolidated"].extend(source.get("_consolidated", []))

    merged_r2: dict[tuple[str, str], dict] = {}
    for (_pe, _code), group in r2_by_code.items():
        # Sort: r2 (Excel) first so they become the merge target
        group.sort(key=lambda d: (0 if d.get("exhibit_type") == "r2" else 1))

        clusters: list[dict[str, Any]] = []
        for row in group:
            title = row.get("_clean_title_only", "").lower()
            matched = False
            for existing in clusters:
                ex_title = existing.get("_clean_title_only", "").lower()
                if not title or not ex_title:
                    continue
                # Prefix match: one title starts with the other (truncation)
                if title.startswith(ex_title) or ex_title.startswith(title):
                    _merge_into(existing, row)
                    matched = True
                    break
                # Levenshtein: merge if < 20% relative to shorter title
                shorter = min(len(title), len(ex_title))
                dist = _levenshtein_distance(title, ex_title)
                if dist / max(shorter, 1) < LEVENSHTEIN_THRESHOLD:
                    _merge_into(existing, row)
                    matched = True
                    break
            if not matched:
                clusters.append(row)

        for row in clusters:
            mkey = (row["pe_number"], row["line_item_title"])
            merged_r2[mkey] = row

    # Propagate R1 BA/CoM to R2 rows
    r1_ba: dict[str, str] = {}
    r1_com: dict[str, str] = {}
    for r1 in r1_rows:
        pe = r1["pe_number"]
        ba = normalize_budget_activity(r1.get("budget_activity"), r1.get("budget_activity_title"))
        com = color_of_money(r1.get("appropriation_title"))
        if ba and ba != "Unknown":
            r1_ba[pe] = ba
        if com and com != "Unknown":
            r1_com[pe] = com

    for row in merged_r2.values():
        pe = row["pe_number"]
        ba_norm = normalize_budget_activity(row.get("budget_activity"), row.get("budget_activity_title"))
        if not ba_norm or ba_norm == "Unknown":
            inherited_ba = r1_ba.get(pe)
            if inherited_ba:
                row["budget_activity_title"] = inherited_ba
        com_val = color_of_money(row.get("appropriation_title"))
        if not com_val or com_val == "Unknown":
            inherited_com = r1_com.get(pe)
            if inherited_com:
                row["_inherited_com"] = inherited_com

    # Propagate PE-level description keywords to R2 rows too
    for row in merged_r2.values():
        pe = row["pe_number"]
        if pe in pe_desc_kws and not row.get("_desc_kws"):
            row["_desc_kws"] = pe_desc_kws[pe]

    # Format consolidated titles for display (None when no alternates)
    for row in merged_r2.values():
        consolidated = row.pop("_consolidated", [])
        unique_alts = sorted(set(t for t in consolidated if t != row["line_item_title"]))
        row["_consolidated_titles"] = "; ".join(unique_alts) if unique_alts else None
        row.pop("_project_code", None)
        row.pop("_clean_title_only", None)

    # Dedup R1 rows: same PE may have variant titles across FYs.
    # Keep the longest title, merge FY amounts.
    r1_dedup: dict[str, dict[str, Any]] = {}
    deduped_other: list[dict[str, Any]] = []
    for d in other_rows:
        if d.get("exhibit_type") == "r1":
            pe = d["pe_number"]
            if pe in r1_dedup:
                existing = r1_dedup[pe]
                if len(d.get("line_item_title", "")) > len(existing.get("line_item_title", "")):
                    existing["line_item_title"] = d["line_item_title"]
                for yr in year_range:
                    col = f"fy{yr}"
                    if existing.get(col) is None and d.get(col) is not None:
                        existing[col] = d[col]
                        ref_col = f"fy{yr}_ref"
                        if d.get(ref_col):
                            existing[ref_col] = d[ref_col]
            else:
                r1_dedup[pe] = d
                deduped_other.append(d)
        else:
            deduped_other.append(d)

    all_rows = deduped_other + list(merged_r2.values())

    # 6. Insert assembled rows into cache table
    count = _insert_cache_rows(
        conn, all_rows, keywords, desc_map, r1_ba, year_range, insert_sql,
    )

    # 6a. Insert stub R-1 rows for extra PEs that exist only in PDFs
    if extra_pes:
        count += _insert_stub_pes(
            conn, cache_table, extra_pes, matched_pes, year_range, insert_sql,
        )

    # 6b. Back-fill organization_name from multiple sources
    pdf_count = sum(1 for d in merged_r2.values() if d.get("exhibit_type") == "r2")
    if pdf_count:
        _backfill_organization(conn, cache_table, year_range)

    count += pdf_count
    logger.info("Cache: %d R-2 sub-element rows from PDFs", pdf_count)

    # 6c. Detect and annotate cross-PE program lineages
    if pdf_count:
        annotate_cross_pe_lineages(conn, cache_table)

    _aggregate_r2_funding_into_r1_stubs(conn, cache_table, year_range)

    # 7. Create indexes for fast filtering
    # Use short hash suffix to avoid name collisions across cache tables
    idx_suffix = cache_table.replace(".", "_")
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{idx_suffix}_pe ON {cache_table}(pe_number)"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{idx_suffix}_org ON {cache_table}(organization_name)"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{idx_suffix}_ex ON {cache_table}(exhibit_type)"
    )

    conn.commit()
    logger.info(
        "Cache rebuilt: %d rows (%d from budget_lines, %d from PDFs)",
        count,
        count - pdf_count,
        pdf_count,
    )
    _progress("done", row_count=count, pe_count=len(matched_pes))
    return count


def ensure_cache(
    conn: sqlite3.Connection,
    cache_table: str,
    keywords: list[str],
    desc_keywords: list[str],
    fy_start: int = FY_START,
    fy_end: int = FY_END,
    progress_callback: Any | None = None,
    extra_pes: list[str] | None = None,
) -> bool:
    """Ensure cache table exists and is populated. Returns True if data available."""
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM {cache_table}").fetchone()[0]
        if n > 0:
            return True
    except sqlite3.OperationalError:
        pass
    logger.info("%s not found or empty — rebuilding...", cache_table)
    return (
        build_cache_table(
            conn,
            cache_table,
            keywords,
            desc_keywords,
            fy_start=fy_start,
            fy_end=fy_end,
            progress_callback=progress_callback,
            extra_pes=extra_pes,
        )
        > 0
    )
