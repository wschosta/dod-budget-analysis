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

from fastapi import APIRouter, Body, Depends, Query
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
    lineage_note            TEXT,
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
    core, _ = _collect_matching_pe_numbers_split(conn)
    return core[0] | core[1] if len(core) == 2 else core[0]


def _collect_matching_pe_numbers_split(
    conn: sqlite3.Connection,
) -> tuple[tuple[set[str], set[str]], set[str]]:
    """Return (budget_lines_matched, desc_matched) PE number sets.

    budget_lines_matched: PEs found via keyword search in budget_lines columns.
    desc_matched: additional PEs found via narrative keyword search in pe_descriptions.

    The union of both is the full matched set for the cache, but only
    budget_lines_matched PEs should be mined for PDF sub-elements (the
    desc-matched set is too broad and would pull in thousands of unrelated PEs).
    """
    bl_matched: set[str] = set()

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
    bl_matched.update(r[0] for r in rows if r[0])

    # (b) pe_descriptions narrative match
    desc_matched: set[str] = set()
    try:
        conn.execute("SELECT 1 FROM pe_descriptions LIMIT 0")
        desc_clauses = ["description_text LIKE ?" for _ in _DESC_KEYWORDS]
        desc_params = [f"%{kw}%" for kw in _DESC_KEYWORDS]
        rows = conn.execute(
            "SELECT DISTINCT pe_number FROM pe_descriptions"
            f" WHERE {' OR '.join(desc_clauses)}",
            desc_params,
        ).fetchall()
        desc_matched.update(r[0] for r in rows if r[0])
    except sqlite3.OperationalError:
        pass

    # Remove overlap so desc_matched only contains extras
    desc_matched -= bl_matched

    return (bl_matched, desc_matched), bl_matched | desc_matched


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


def _parse_r2_cost_block(page_text: str, source_file: str, fiscal_year: str
                         ) -> list[dict[str, Any]]:
    """Parse R-2/R-2A COST block from a PDF page to extract project-level funding.

    Returns a list of dicts with keys:
        pe_number, project_code, project_title, source_file, fiscal_year,
        fy_amounts: {fyXXXX: amount_in_thousands}
    """
    import re

    lines = page_text.split("\n")
    results: list[dict[str, Any]] = []

    # 1. Extract PE number from header line: "PE 0604182A / Hypersonics"
    pe_number = None
    pe_title = None
    for line in lines[:10]:
        m = re.search(r"PE\s+(\d{7}[A-Z])\s*/\s*(.+?)(?:\s+\d|$)", line)
        if m:
            pe_number = m.group(1)
            pe_title = m.group(2).strip()
            break
    if not pe_number:
        return []

    # 2. Find the COST block and parse FY column headers
    cost_idx = None
    for i, line in enumerate(lines):
        if "COST" in line and "Millions" in line:
            cost_idx = i
            break
    if cost_idx is None:
        return []

    # The FY header line is typically right after COST line
    # Format: "Years  FY 2024  FY 2025  Base  OOC  Total  FY 2027  ..."
    fy_header_line = lines[cost_idx + 1] if cost_idx + 1 < len(lines) else ""

    # Detect the budget-year split columns: "Base", "OOC/OCO", "Total"
    # These represent the budget-year (typically fiscal_year) broken into components
    # We want the "Total" for the budget year
    # fiscal_year may be "FY 2026" or "2026"
    _fy_m = re.search(r"(\d{4})", fiscal_year or "")
    budget_year = int(_fy_m.group(1)) if _fy_m else None

    # Build ordered list of what each numeric column represents.
    # Header format (single-spaced from PDF extraction):
    #   "Years FY 2024 FY 2025 Base OOC Total FY 2027 FY 2028 ... Complete Cost"
    # The column order corresponds to numbers in the data rows:
    #   prior_years, fy_n-2, fy_n-1, base, ooc, total, fy_n+1, ...
    # We parse keyword positions left-to-right to build the column map.
    col_fy_map: list[int | None] = []

    # Use regex to find all column keywords in order
    col_tokens = re.finditer(
        r"(?:FY\s+\d{4}|Years|Base|OOC|OCO|Total|Complete|Cost)\b",
        fy_header_line, re.IGNORECASE,
    )
    for m in col_tokens:
        tok = m.group().strip()
        fy_m = re.match(r"FY\s+(\d{4})", tok, re.IGNORECASE)
        tok_upper = tok.upper()
        if tok_upper == "YEARS":
            col_fy_map.append(None)  # "Prior Years" column — skip value but keep alignment
            continue
        elif fy_m:
            col_fy_map.append(int(fy_m.group(1)))
        elif tok_upper == "BASE":
            col_fy_map.append(None)
        elif tok_upper in ("OOC", "OCO"):
            col_fy_map.append(None)
        elif tok_upper == "TOTAL":
            if budget_year:
                col_fy_map.append(budget_year)
            else:
                col_fy_map.append(None)
        elif tok_upper in ("COMPLETE", "COST"):
            col_fy_map.append(None)

    if not col_fy_map:
        return []

    # 3. Parse project rows after the header
    # Project rows contain: "<code>: <title> <numbers...>" or "Total Program Element <numbers...>"
    # Numbers are like: 228.962, 1,076.050, -, 0.000
    num_pattern = re.compile(r"[\d,]+\.\d{3}|(?<!\w)-(?!\w)|0\.000")

    for i in range(cost_idx + 2, min(cost_idx + 15, len(lines))):
        line = lines[i].strip()
        if not line:
            continue
        # Stop at section boundaries
        if any(line.startswith(s) for s in (
            "Quantity of RDT&E",
            "A. Mission",
            "B. Accomplishments",
            "Note",
            "Program MDAP",
        )):
            break

        # Skip "Total Program Element" row — we want sub-project rows
        if "Total Program Element" in line:
            continue

        # Detect continuation lines (title wraps to next line, no numbers)
        nums_in_line = num_pattern.findall(line)
        if not nums_in_line:
            # Continuation of previous project title
            if results:
                results[-1]["project_title"] += " " + line.strip()
            continue

        # Extract project code and title before the numbers start
        first_num_pos = re.search(r"\s[\d,]+\.\d{3}|\s-\s|\s-$", line)
        if first_num_pos:
            prefix = line[:first_num_pos.start()].strip()
        else:
            prefix = line.strip()

        # Parse project code: "HX2: Hypersonic Weapon" or "644183: HACM"
        code_m = re.match(r"^([A-Z0-9]+):\s*(.+)", prefix)
        if code_m:
            project_code = code_m.group(1)
            project_title = code_m.group(2).strip()
        else:
            project_code = None
            project_title = prefix

        # Parse the numeric values — aligned 1:1 with col_fy_map
        all_nums = num_pattern.findall(line)
        fy_nums = all_nums

        fy_amounts: dict[str, float] = {}
        for j, val_str in enumerate(fy_nums):
            if j >= len(col_fy_map):
                break
            fy_year = col_fy_map[j]
            if fy_year is None:
                continue
            if val_str == "-":
                continue
            try:
                amount_millions = float(val_str.replace(",", ""))
                # Convert millions to thousands (budget_lines uses thousands)
                fy_amounts[f"fy{fy_year}"] = amount_millions * 1000.0
            except ValueError:
                continue

        if fy_amounts:
            results.append({
                "pe_number": pe_number,
                "pe_title": pe_title,
                "project_code": project_code,
                "project_title": project_title,
                "source_file": source_file,
                "fiscal_year": fiscal_year,
                "fy_amounts": fy_amounts,
                "description_text": "",  # filled below
            })

    # 4. Extract description text from Section A (Mission Description) and
    #    Section B project-level Title/Description blocks.
    desc_parts: list[str] = []
    in_section_a = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("A. Mission Description"):
            in_section_a = True
            continue
        if in_section_a:
            # Stop at section B or C header
            if re.match(r"^[B-Z]\.\s", stripped):
                break
            if stripped:
                desc_parts.append(stripped)
    section_a_text = " ".join(desc_parts).strip()

    # Also extract Section B project Title/Description pairs
    project_descs: dict[str, str] = {}  # project_title_prefix -> description
    current_title = None
    current_desc_parts: list[str] = []
    in_section_b = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("B. Accomplishments") or stripped.startswith("C. Accomplishments"):
            in_section_b = True
            continue
        if not in_section_b:
            continue
        # Stop at next major section
        if re.match(r"^[C-Z]\.\s(?!Accomplishments)", stripped):
            break
        if stripped.startswith("Title:"):
            # Save previous
            if current_title and current_desc_parts:
                project_descs[current_title] = " ".join(current_desc_parts).strip()
            title_text = stripped[len("Title:"):].strip()
            # Strip trailing FY amounts from title line
            title_text = re.sub(r"\s+[\d,.]+\s*$", "", title_text).strip()
            current_title = title_text
            current_desc_parts = []
        elif stripped.startswith("Description:") and current_title:
            current_desc_parts.append(stripped[len("Description:"):].strip())
        elif current_title and current_desc_parts and not stripped.startswith("FY "):
            # Continuation of description text
            if not re.match(r"^(Accomplishments|Congressional|Title:)", stripped):
                current_desc_parts.append(stripped)
    # Save last
    if current_title and current_desc_parts:
        project_descs[current_title] = " ".join(current_desc_parts).strip()

    # Attach description text to results
    for item in results:
        parts = []
        if section_a_text:
            parts.append(section_a_text)
        # Try to match project-level description by title prefix
        proj_title = item["project_title"]
        for desc_title, desc_text in project_descs.items():
            # Fuzzy match: check if the project title starts with or contains the desc title
            if (proj_title.lower().startswith(desc_title[:20].lower())
                    or desc_title.lower().startswith(proj_title[:20].lower())):
                parts.append(f"[{desc_title}] {desc_text}")
                break
        item["description_text"] = "\n\n".join(parts) if parts else ""

    return results


def _mine_pdf_subelements(
    conn: sqlite3.Connection,
    pe_numbers: set[str],
    core_pes: set[str] | None = None,
) -> tuple[list[dict[str, Any]], set[str]]:
    """Mine R-2/R-2A sub-element data from pdf_pages for the given PE numbers.

    Scans pdf_pages for R-2/R-2A exhibit first-pages that contain COST tables,
    extracts project-level funding breakdowns, and returns rows suitable for
    insertion into the hypersonics cache.

    For *core* PEs (direct keyword matches in line item title), all sub-elements
    are kept. For *desc-only* PEs (keyword only in PE description), sub-elements
    are filtered: only those whose project title or description text matches a
    hypersonics keyword are retained.

    Only processes FY >= _FY_START to match the cache's fiscal year range.
    """
    if not pe_numbers:
        return [], set()

    try:
        conn.execute("SELECT 1 FROM pdf_pages LIMIT 0")
    except sqlite3.OperationalError:
        return [], set()

    if core_pes is None:
        core_pes = pe_numbers

    # For large PE sets, scan all R-2/R-2A exhibit pages and filter by PE in
    # Python rather than building hundreds of LIKE clauses.
    fy_min_str = f"FY {_FY_START}"

    rows = conn.execute(
        """
        SELECT source_file, page_number, page_text, fiscal_year
        FROM pdf_pages
        WHERE (page_text LIKE '%Exhibit R-2,%' OR page_text LIKE '%Exhibit R-2A%')
          AND page_text LIKE '%COST%Millions%'
          AND source_file LIKE '%detail%'
          AND fiscal_year >= ?
        ORDER BY fiscal_year DESC, source_file, page_number
        """,
        [fy_min_str],
    ).fetchall()

    logger.info("PDF sub-element mining: scanning %d R-2/R-2A pages for %d PEs",
                len(rows), len(pe_numbers))

    # Parse all pages and collect raw sub-element rows.
    # Keep rows from known PEs unconditionally, AND discover new PEs whose
    # R-2 title or description matches a hypersonics keyword.
    seen: set[tuple[str, str | None, str]] = set()
    raw_items: list[dict[str, Any]] = []
    discovered_pes: set[str] = set()  # PEs found via R-2 keyword match

    for r in rows:
        source_file, page_number, page_text, fiscal_year = r
        parsed = _parse_r2_cost_block(page_text, source_file, fiscal_year)
        for item in parsed:
            pe = item["pe_number"]
            key = (pe, item.get("project_code"), fiscal_year)
            if key in seen:
                continue

            if pe in pe_numbers:
                # Known PE — keep unconditionally
                seen.add(key)
                raw_items.append(item)
            else:
                # Unknown PE — check if R-2 title or description has keywords
                text_fields = [
                    item.get("project_title", ""),
                    item.get("description_text", ""),
                    item.get("pe_title", ""),
                ]
                matched = _find_matched_keywords(text_fields)
                if matched:
                    item["_matched_r2_keywords"] = matched
                    seen.add(key)
                    raw_items.append(item)
                    discovered_pes.add(pe)

    if discovered_pes:
        logger.info("PDF sub-element mining: discovered %d new PEs via R-2 keyword matches: %s",
                    len(discovered_pes), ", ".join(sorted(discovered_pes)))

    logger.info("PDF sub-element mining: %d raw rows before consolidation", len(raw_items))

    # Consolidate into one golden-timeseries row per (pe_number, project_code).
    consolidated = _consolidate_r2_timeseries(raw_items)

    # Tag rows with keyword matches (for display as keyword pills) but keep
    # ALL sub-elements — if a PE is in the cache at R-1 level, we show all its
    # R-2 sub-elements so the user can see the full funding picture.
    for item in consolidated:
        if not item.get("_matched_r2_keywords"):
            text_fields = [
                item.get("project_title", ""),
                item.get("description_text", ""),
                item.get("pe_title", ""),
            ]
            matched = _find_matched_keywords(text_fields)
            if matched:
                item["_matched_r2_keywords"] = matched

    logger.info("PDF sub-element mining: %d final project rows (%d discovered PEs)",
                len(consolidated), len(discovered_pes))
    return consolidated, discovered_pes


def _consolidate_r2_timeseries(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse multiple budget-submission rows into one golden row per project.

    For each (pe_number, project_code), build a single timeseries by picking
    each FY cell from the most recent budget submission that reports it.
    Also tracks the source_file per FY cell for citation links.
    """
    import re

    # Group by (pe_number, project_code)
    groups: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for item in items:
        key = (item["pe_number"], item.get("project_code"))
        groups.setdefault(key, []).append(item)

    results: list[dict[str, Any]] = []
    for (pe, proj_code), group in groups.items():
        # Sort by budget submission year descending (most recent first)
        def _doc_fy(item: dict[str, Any]) -> int:
            m = re.search(r"(\d{4})", item.get("fiscal_year", ""))
            return int(m.group(1)) if m else 0

        group.sort(key=_doc_fy, reverse=True)

        # Build golden timeseries: for each FY, take the first non-null value
        golden_amounts: dict[str, float] = {}
        golden_refs: dict[str, str] = {}  # fy key -> source_file
        for item in group:
            for fy_key, amount in item["fy_amounts"].items():
                if fy_key not in golden_amounts:
                    golden_amounts[fy_key] = amount
                    golden_refs[fy_key] = item["source_file"]

        # Use metadata from the most recent submission
        latest = group[0]
        # Use the longest/most recent description available
        best_desc = ""
        for item in group:
            desc = item.get("description_text", "")
            if len(desc) > len(best_desc):
                best_desc = desc
        results.append({
            "pe_number": pe,
            "pe_title": latest.get("pe_title"),
            "project_code": proj_code,
            "project_title": latest["project_title"],
            "source_file": latest["source_file"],
            "fiscal_year": latest["fiscal_year"],
            "fy_amounts": golden_amounts,
            "fy_refs": golden_refs,
            "description_text": best_desc,
        })

    return results


def _normalize_program_name(title: str) -> str:
    """Extract a canonical short name for cross-PE matching.

    Strips project codes, parenthetical abbreviations, and common suffixes
    to produce a fuzzy-matchable program identity.
    E.g. "643883: Hypersonic Attack Cruise Missile" → "hypersonic attack cruise missile"
         "644183: Hypersonic Attack Cruise Missile (HACM)" → "hypersonic attack cruise missile"
    """
    import re
    # Strip leading project code
    s = re.sub(r"^[A-Z0-9]+:\s*", "", title)
    # Strip parenthetical abbreviations
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s)
    # Normalize whitespace and lowercase
    return " ".join(s.lower().split())


def _annotate_cross_pe_lineages(conn: sqlite3.Connection) -> None:
    """Detect R-2 projects that migrated across PEs and annotate with lineage_note.

    Finds projects with matching normalized names under different PE numbers,
    then writes a human-readable note like:
        "→ Moved to PE 0604183F" or "← From PE 0604033F"
    """
    rows = conn.execute(f"""
        SELECT id, pe_number, line_item_title
        FROM {_CACHE_TABLE}
        WHERE exhibit_type = 'r2'
    """).fetchall()

    if not rows:
        return

    # Build normalized name → list of (id, pe_number, title)
    from collections import defaultdict
    name_groups: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for row_id, pe, title in rows:
        norm = _normalize_program_name(title)
        if norm:
            name_groups[norm].append((row_id, pe, title))

    updates: list[tuple[str, int]] = []
    for norm_name, members in name_groups.items():
        # Only interesting if same name appears under multiple PEs
        pe_set = {pe for _, pe, _ in members}
        if len(pe_set) < 2:
            continue

        # Sort by PE number to get a consistent ordering
        sorted_members = sorted(members, key=lambda x: x[1])

        # For each member, annotate with links to the other PEs
        for row_id, pe, title in sorted_members:
            other_pes = sorted(p for p in pe_set if p != pe)
            if not other_pes:
                continue
            note = "Also in PE " + ", ".join(other_pes)
            updates.append((note, row_id))

    if updates:
        conn.executemany(
            f"UPDATE {_CACHE_TABLE} SET lineage_note = ? WHERE id = ?",
            updates,
        )
        logger.info("Cross-PE lineage: annotated %d R-2 rows", len(updates))


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
    (bl_pes, _desc_pes), matched_pes = _collect_matching_pe_numbers_split(conn)
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
        # Priority: actual spend > enacted > total > request (best accuracy first).
        # Use MAX across ALL submissions (not just fiscal_year=yr) so that actuals
        # reported in later submissions are picked up instead of zero-valued requests.
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
            # COALESCE + MAX(NULLIF): skip zero and negative values (reconciliation deltas)
            # to prefer real funding amounts from higher-priority columns.
            parts = [f"MAX(CASE WHEN {c} > 0 THEN {c} END)" for c in available]
            # Fall back to 0 only if every column is NULL/zero/negative
            coalesce_expr = f"COALESCE({', '.join(parts)}, 0)"
        year_parts.append(f"{coalesce_expr} AS fy{yr}")
        year_parts.append(
            f"MAX(CASE WHEN {available[0]} IS NOT NULL THEN source_file END) AS fy{yr}_ref"
            if available else f"NULL AS fy{yr}_ref"
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

    # 6b. Insert PDF-mined R-2/R-2A sub-elements
    pdf_result = _mine_pdf_subelements(conn, matched_pes, core_pes=bl_pes)
    pdf_subelements: list[dict[str, Any]] = pdf_result[0]
    discovered_pes: set[str] = pdf_result[1]

    # For PEs discovered via R-2 keyword matches, also insert R-1 budget_lines rows
    if discovered_pes:
        disc_placeholders = ", ".join("?" for _ in discovered_pes)
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
            WHERE pe_number IN ({disc_placeholders})
              AND CAST(fiscal_year AS INTEGER) >= {_FY_START}
            GROUP BY pe_number, exhibit_type, line_item_title
            ORDER BY pe_number, exhibit_type, line_item_title
        """
        disc_rows = conn.execute(disc_sql, list(discovered_pes)).fetchall()
        disc_desc_map = _get_description_map(conn, discovered_pes)
        disc_desc_kw_map = _get_desc_keyword_map(conn, discovered_pes)
        for r in disc_rows:
            d = dict(r)
            text_fields = [d.get("line_item_title"), d.get("account_title"), d.get("budget_activity_title")]
            row_kws = _find_matched_keywords(text_fields)
            dkws = disc_desc_kw_map.get(d["pe_number"], [])
            vals = [
                d["pe_number"], d.get("organization_name"), d.get("exhibit_type"),
                d.get("line_item_title"), d.get("budget_activity"), d.get("budget_activity_title"),
                _normalize_budget_activity(d.get("budget_activity"), d.get("budget_activity_title")),
                d.get("appropriation_title"), d.get("account_title"),
                _color_of_money(d.get("appropriation_title")),
                json.dumps(row_kws) if row_kws else "[]",
                json.dumps(dkws) if dkws else "[]",
                disc_desc_map.get(d["pe_number"]) or None,
            ]
            for yr in year_range:
                vals.append(d.get(f"fy{yr}"))
                vals.append(d.get(f"fy{yr}_ref"))
            conn.execute(insert_sql, vals)
            count += 1
        logger.info("Hypersonics cache: added %d R-1 rows for %d discovered PEs",
                    len(disc_rows), len(discovered_pes))
    pdf_count = 0
    for item in pdf_subelements:
        pe = item["pe_number"]
        title = item["project_title"]
        if item.get("project_code"):
            title = f"{item['project_code']}: {title}"

        # Row-level keyword matching on project title + R-2 description
        row_kws = item.get("_matched_r2_keywords") or _find_matched_keywords([title])
        desc_kws = desc_kw_map.get(pe, [])

        # Use R-2 description if available, fall back to PE-level description
        r2_desc = item.get("description_text", "")
        description = r2_desc if r2_desc else (desc_map.get(pe) or None)

        vals = [
            pe,
            None,  # organization_name — not in PDF text, filled below
            "r2",  # exhibit_type
            title,
            None,  # budget_activity
            None,  # budget_activity_title
            None,  # budget_activity_norm
            None,  # appropriation_title
            item.get("pe_title"),  # account_title — use PE title
            "RDT&E",  # color_of_money — R-2 is always RDT&E
            json.dumps(row_kws) if row_kws else "[]",
            json.dumps(desc_kws) if desc_kws else "[]",
            description,
        ]
        fy_refs = item.get("fy_refs", {})
        for yr in year_range:
            fy_key = f"fy{yr}"
            vals.append(item["fy_amounts"].get(fy_key))
            vals.append(fy_refs.get(fy_key) if item["fy_amounts"].get(fy_key) is not None else None)

        conn.execute(insert_sql, vals)
        pdf_count += 1

    if pdf_count:
        # Back-fill organization_name from R-1 rows where available
        conn.execute(f"""
            UPDATE {_CACHE_TABLE} AS c
            SET organization_name = (
                SELECT r1.organization_name
                FROM {_CACHE_TABLE} r1
                WHERE r1.pe_number = c.pe_number
                  AND r1.exhibit_type = 'r1'
                  AND r1.organization_name IS NOT NULL
                LIMIT 1
            )
            WHERE c.exhibit_type = 'r2' AND c.organization_name IS NULL
        """)

        # Fallback: infer organization from source_file path for remaining blanks.
        # Check the most recent FY ref column for a service path fragment.
        _ORG_FROM_PATH = [
            ("US_Army", "Army"),
            ("US_Air_Force", "Air Force"),
            ("US_Navy", "Navy"),
            ("Defense_Wide", "Defense-Wide"),
            ("DARPA", "DARPA"),
            ("SOCOM", "SOCOM"),
        ]
        latest_ref_col = f"fy{year_range[-1]}_ref"
        fallback_ref_col = f"fy{year_range[-2]}_ref" if len(year_range) > 1 else latest_ref_col
        for path_fragment, org_name in _ORG_FROM_PATH:
            conn.execute(
                f"""
                UPDATE {_CACHE_TABLE}
                SET organization_name = ?
                WHERE (organization_name IS NULL OR organization_name = '')
                  AND ({latest_ref_col} LIKE ? OR {fallback_ref_col} LIKE ?)
                """,
                [org_name, f"%{path_fragment}%", f"%{path_fragment}%"],
            )

    count += pdf_count
    logger.info("Hypersonics cache: %d R-2 sub-element rows from PDFs", pdf_count)

    # 6c. Detect and annotate cross-PE program lineages among R-2 rows.
    # Match projects that share the same short program name across different PEs.
    if pdf_count:
        _annotate_cross_pe_lineages(conn)

    # 7. Create indexes for fast filtering
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_hc_pe ON {_CACHE_TABLE}(pe_number)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_hc_org ON {_CACHE_TABLE}(organization_name)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_hc_exhibit ON {_CACHE_TABLE}(exhibit_type)")

    conn.commit()
    logger.info("Hypersonics cache rebuilt: %d rows (%d from budget_lines, %d from PDFs)",
                count, count - pdf_count, pdf_count)
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
        "Color of Money", "Keywords (Row)", "Keywords (Desc)", "Description",
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
            r.get("description_text", ""),
            *fy_cells,
        ])

    csv_bytes = buf.getvalue().encode("utf-8-sig")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="hypersonics_pe_lines.csv"'},
    )


# ── POST /api/v1/hypersonics/download/xlsx ────────────────────────────────────

@router.post(
    "/download/xlsx",
    summary="Download selected hypersonics rows as XLSX with formatting",
    response_class=Response,
)
def download_hypersonics_xlsx(
    show_ids: list[str] = Body(..., description="data-idx values of SHOW-checked rows"),
    total_ids: list[str] = Body(..., description="data-idx values of TOTAL-checked rows"),
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """Download an XLSX with all SHOW-checked rows.

    Rows that are SHOW-only (not TOTAL-checked) are rendered in italics.
    Rows that are TOTAL-checked get normal formatting.
    A "Totals" row is appended at the bottom summing the TOTAL-checked FY columns.
    """
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill, numbers

    _ensure_cache(conn)

    year_range = list(range(_FY_START, _FY_END + 1))

    # Fetch all cache rows, grouped by PE as the template does
    sql = f"SELECT * FROM {_CACHE_TABLE} ORDER BY pe_number, exhibit_type, line_item_title"
    all_rows = conn.execute(sql).fetchall()
    items = _cache_rows_to_dicts(all_rows)

    # Group by PE (preserving order) and assign data-idx values matching the template
    from collections import OrderedDict
    pe_groups: OrderedDict[str, list[dict]] = OrderedDict()
    for item in items:
        pe = item["pe_number"]
        pe_groups.setdefault(pe, []).append(item)

    # Build lookup: data-idx → (row_dict, child_index_in_pe)
    idx_to_row: dict[str, dict] = {}
    for pe, children in pe_groups.items():
        for i, child in enumerate(children):
            idx = f"{pe}-{i}"
            idx_to_row[idx] = child

    show_set = set(show_ids)
    total_set = set(total_ids)

    # Filter to only SHOW-checked rows, preserving order
    selected_rows: list[tuple[str, dict]] = []  # (data_idx, row_dict)
    for pe, children in pe_groups.items():
        for i, child in enumerate(children):
            idx = f"{pe}-{i}"
            if idx in show_set:
                selected_rows.append((idx, child))

    if not selected_rows:
        return Response(
            content=b"No rows selected",
            media_type="text/plain",
            status_code=400,
        )

    # Detect which FY columns have any data in selected rows
    active_years = [
        yr for yr in year_range
        if any(row.get(f"fy{yr}") is not None for _, row in selected_rows)
    ]

    # Build workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hypersonics"

    # Styles
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
    header_font_white = Font(bold=True, size=11, color="FFFFFF")
    italic_font = Font(italic=True, color="888888", size=10)
    normal_font = Font(size=10)
    total_font = Font(bold=True, size=11)
    money_fmt = '#,##0'

    # Headers
    headers = [
        "PE Number", "Service/Org", "Exhibit", "Line Item / Sub-Program",
        "Budget Activity", "Color of Money", "Description", "In Totals",
    ]
    for yr in active_years:
        headers.append(f"FY{yr} ($K)")

    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = header_font_white
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    # Data rows
    total_sums: dict[int, float] = {}  # FY year → sum
    row_num = 2
    for data_idx, row in selected_rows:
        is_total = data_idx in total_set
        font = normal_font if is_total else italic_font

        vals = [
            row.get("pe_number", ""),
            row.get("organization_name", ""),
            row.get("exhibit_type", ""),
            row.get("line_item_title", ""),
            row.get("budget_activity_norm", ""),
            row.get("color_of_money", ""),
            row.get("description_text", ""),
            "Yes" if is_total else "",
        ]
        for i, v in enumerate(vals, 1):
            cell = ws.cell(row=row_num, column=i, value=v)
            cell.font = font

        # FY columns
        for fy_col_idx, yr in enumerate(active_years):
            col = len(vals) + fy_col_idx + 1
            amount = row.get(f"fy{yr}")
            cell = ws.cell(row=row_num, column=col, value=amount)
            cell.font = font
            if amount is not None:
                cell.number_format = money_fmt
                if is_total:
                    total_sums[yr] = total_sums.get(yr, 0) + amount

        row_num += 1

    # Totals row
    if total_sums:
        ws.cell(row=row_num, column=1, value="TOTALS").font = total_font
        ws.cell(row=row_num, column=8, value="Sum").font = total_font
        for fy_col_idx, yr in enumerate(active_years):
            col = 8 + fy_col_idx + 1
            val = total_sums.get(yr)
            if val is not None:
                cell = ws.cell(row=row_num, column=col, value=val)
                cell.font = total_font
                cell.number_format = money_fmt

    # Column widths
    col_widths = [14, 14, 8, 50, 20, 12, 60, 10] + [14] * len(active_years)
    for i, w in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w

    # Freeze panes: freeze header row + first 4 columns
    ws.freeze_panes = "E2"

    # Auto-filter
    ws.auto_filter.ref = ws.dimensions

    # Write to bytes
    buf = io.BytesIO()
    wb.save(buf)
    xlsx_bytes = buf.getvalue()

    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="hypersonics_selected.xlsx"'},
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


# ── GET /api/v1/hypersonics/desc ──────────────────────────────────────────────

@router.get(
    "/desc/{pe_number}",
    summary="Get description text for a PE or R-2 project",
)
def get_description(
    pe_number: str,
    project: str | None = None,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Return description_text for a PE (R-1 level) or specific R-2 project row."""
    try:
        if project:
            row = conn.execute(
                f"SELECT description_text FROM {_CACHE_TABLE} "
                "WHERE pe_number = ? AND line_item_title = ? AND description_text IS NOT NULL LIMIT 1",
                [pe_number, project],
            ).fetchone()
        else:
            # Prefer R-2 description (contains actual Mission Description from R-2A
            # exhibit), fall back to R-1 only if no R-2 desc exists.
            row = conn.execute(
                f"SELECT description_text FROM {_CACHE_TABLE} "
                "WHERE pe_number = ? AND exhibit_type = 'r2' AND description_text IS NOT NULL LIMIT 1",
                [pe_number],
            ).fetchone()
            if not row:
                row = conn.execute(
                    f"SELECT description_text FROM {_CACHE_TABLE} "
                    "WHERE pe_number = ? AND description_text IS NOT NULL LIMIT 1",
                    [pe_number],
                ).fetchone()
        return {"description": row[0] if row else None}
    except sqlite3.OperationalError:
        return {"description": None}


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
