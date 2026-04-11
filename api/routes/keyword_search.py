"""
Shared keyword-search cache-building logic.

Extracted from hypersonics.py so that both the Hypersonics page and the
generic Keyword Explorer can reuse the same pivot/cache/PDF-mining pipeline.

All public functions accept ``keywords`` and ``cache_table`` (or similar)
as parameters — no module-level keyword lists are hard-coded here.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from typing import Any

from utils.database import get_amount_columns
from utils.strings import clean_narrative
from utils.patterns import PE_NUMBER_STRICT_CI, PE_SUFFIX_PATTERN

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SEARCH_COLS = ["line_item_title", "account_title", "budget_activity_title"]

FY_START = 2015
FY_END = 2026

# Regex to extract PE number and title from PDF exhibit header lines
_PE_TITLE_RE = re.compile(
    rf"PE\s+(\d{{7}}{PE_SUFFIX_PATTERN})\s*[/:]\s*(.+?)(?:\s+\d|$)"
)

# RDT&E BA categories (BA 01-07) — canonical titles
BA_CANONICAL: dict[str, str] = {
    "01": "BA 1: Basic Research",
    "02": "BA 2: Applied Research",
    "03": "BA 3: Advanced Technology Development",
    "04": "BA 4: Advanced Component Dev & Prototypes",
    "05": "BA 5: System Development & Demonstration",
    "06": "BA 6: RDT&E Management Support",
    "07": "BA 7: Operational Systems Development",
}

_ORG_FROM_PATH = [
    ("US_Army", "Army"),
    ("US_Air_Force", "Air Force"),
    ("US_Navy", "Navy"),
    ("Defense_Wide", "Defense-Wide"),
    ("DARPA", "DARPA"),
    ("SOCOM", "SOCOM"),
]


# ── Cache DDL ─────────────────────────────────────────────────────────────────


def cache_ddl(table_name: str, fy_start: int = FY_START, fy_end: int = FY_END) -> str:
    """Return the CREATE TABLE DDL for a keyword-search cache table."""
    fy_cols = "\n".join(
        f"    fy{yr} REAL, fy{yr}_ref TEXT," for yr in range(fy_start, fy_end + 1)
    )
    # Remove trailing comma from last FY line
    fy_cols = fy_cols.rstrip(",")
    return f"""
CREATE TABLE IF NOT EXISTS {table_name} (
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
{fy_cols}
);
"""


# ── Normalization helpers ─────────────────────────────────────────────────────


def normalize_budget_activity(ba_number: str | None, ba_title: str | None) -> str:
    """Map budget_activity number to canonical BA label, falling back to title."""
    if ba_number and ba_number.strip() in BA_CANONICAL:
        return BA_CANONICAL[ba_number.strip()]
    if ba_title:
        return ba_title.strip()
    return "Unknown"


def color_of_money(approp_title: str | None) -> str:
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


# ── Keyword matching ─────────────────────────────────────────────────────────


def find_matched_keywords(
    text_fields: list[str | None],
    keywords: list[str],
) -> list[str]:
    """Return which of *keywords* match (case-insensitive substring) in *text_fields*."""
    combined = " ".join((t or "") for t in text_fields).lower()
    if not combined.strip():
        return []
    return [kw for kw in keywords if kw.lower() in combined]


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
        pe_placeholders = ", ".join("?" for _ in pe_keywords)
        pe_upper = [pk.strip().upper() for pk in pe_keywords]
        rows = conn.execute(
            f"SELECT DISTINCT pe_number FROM budget_lines WHERE pe_number IN ({pe_placeholders})",
            pe_upper,
        ).fetchall()
        bl_matched.update(r[0] for r in rows if r[0])
        # Fallback: check pe_index for PDF-only PEs not in budget_lines
        remaining_pes = set(pe_upper) - bl_matched
        if remaining_pes:
            try:
                rp = ", ".join("?" for _ in remaining_pes)
                pi_rows = conn.execute(
                    f"SELECT DISTINCT pe_number FROM pe_index WHERE pe_number IN ({rp})",
                    list(remaining_pes),
                ).fetchall()
                bl_matched.update(r[0] for r in pi_rows if r[0])
            except sqlite3.OperationalError:
                pass  # pe_index table may not exist

    # (a) Budget-lines keyword match
    kw_clauses: list[str] = []
    kw_params: list[Any] = []
    for col in search_cols:
        for kw in keywords:
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
        desc_clauses = ["description_text LIKE ?" for _ in desc_keywords]
        desc_params = [f"%{kw}%" for kw in desc_keywords]
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

    placeholders = ", ".join("?" for _ in pe_numbers)
    pe_list = list(pe_numbers)
    rows = conn.execute(
        f"SELECT pe_number, description_text, "
        f"CASE "
        f"  WHEN section_header LIKE '%Mission Description%' THEN 1 "
        f"  WHEN section_header LIKE '%Accomplishments%' THEN 2 "
        f"  WHEN section_header LIKE '%Acquisition Strategy%' THEN 3 "
        f"  ELSE 4 END AS priority "
        f"FROM pe_descriptions "
        f"WHERE pe_number IN ({placeholders}) AND section_header IS NOT NULL "
        f"ORDER BY pe_number, priority",
        pe_list,
    ).fetchall()

    # Group by PE, take top 3 per PE
    from itertools import groupby

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

    placeholders = ", ".join("?" for _ in pe_numbers)
    pe_list = list(pe_numbers)

    # Single query: fetch all (pe_number, description_text) pairs
    rows = conn.execute(
        f"SELECT DISTINCT pe_number, description_text FROM pe_descriptions "
        f"WHERE pe_number IN ({placeholders})",
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


def _is_garbage_description(text: str | None) -> bool:
    """Detect R-1 page header text or other artifacts masquerading as descriptions."""
    if not text:
        return True
    stripped = text.strip()
    if len(stripped) < 80:
        return True
    garbage_markers = [
        "Exhibit R-1",
        "President's Budget",
        "Total Obligational Authority",
        "R D T & E Program Exhibit",
        "RDT&E PROGRAM EXHIBIT",
    ]
    for marker in garbage_markers:
        if marker in stripped[:300]:
            return True
    return False


# ── R-2 PDF parsing ──────────────────────────────────────────────────────────


def parse_r2_cost_block(
    page_text: str,
    source_file: str,
    fiscal_year: str,
) -> list[dict[str, Any]]:
    """Parse R-2/R-2A COST block from a PDF page to extract project-level funding.

    Returns a list of dicts with keys:
        pe_number, project_code, project_title, source_file, fiscal_year,
        fy_amounts: {fyXXXX: amount_in_thousands}
    """
    lines = page_text.split("\n")
    results: list[dict[str, Any]] = []

    # 1. Extract PE number from header line
    pe_number = None
    pe_title = None
    for line in lines[:10]:
        m = _PE_TITLE_RE.search(line)
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

    fy_header_line = lines[cost_idx + 1] if cost_idx + 1 < len(lines) else ""

    _fy_m = re.search(r"(\d{4})", fiscal_year or "")
    budget_year = int(_fy_m.group(1)) if _fy_m else None

    col_fy_map: list[int | None] = []
    col_tokens = re.finditer(
        r"(?:FY\s+\d{4}|Years|Base|OOC|OCO|Total|Complete|Cost)\b",
        fy_header_line,
        re.IGNORECASE,
    )
    for m in col_tokens:
        tok = m.group().strip()
        fy_m = re.match(r"FY\s+(\d{4})", tok, re.IGNORECASE)
        tok_upper = tok.upper()
        if tok_upper == "YEARS":
            col_fy_map.append(None)
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
    num_pattern = re.compile(r"[\d,]+\.\d{3}|(?<!\w)-(?!\w)|0\.000")

    for i in range(cost_idx + 2, min(cost_idx + 15, len(lines))):
        line = lines[i].strip()
        if not line:
            continue
        if any(
            line.startswith(s)
            for s in (
                "Quantity of RDT&E",
                "A. Mission",
                "B. Accomplishments",
                "Note",
                "Program MDAP",
            )
        ):
            break

        if "Total Program Element" in line:
            continue

        nums_in_line = num_pattern.findall(line)
        if not nums_in_line:
            if results:
                results[-1]["project_title"] += " " + line.strip()
            continue

        first_num_pos = re.search(r"\s[\d,]+\.\d{3}|\s-\s|\s-$", line)
        if first_num_pos:
            prefix = line[: first_num_pos.start()].strip()
        else:
            prefix = line.strip()

        code_m = re.match(r"^([A-Z0-9]+):\s*(.+)", prefix)
        if code_m:
            project_code = code_m.group(1)
            project_title = code_m.group(2).strip()
        else:
            project_code = None
            project_title = prefix

        all_nums = num_pattern.findall(line)

        fy_amounts: dict[str, float] = {}
        for j, val_str in enumerate(all_nums):
            if j >= len(col_fy_map):
                break
            fy_year = col_fy_map[j]
            if fy_year is None:
                continue
            if val_str == "-":
                continue
            try:
                amount_millions = float(val_str.replace(",", ""))
                fy_amounts[f"fy{fy_year}"] = amount_millions * 1000.0
            except ValueError:
                continue

        if fy_amounts:
            results.append(
                {
                    "pe_number": pe_number,
                    "pe_title": pe_title,
                    "project_code": project_code,
                    "project_title": project_title,
                    "source_file": source_file,
                    "fiscal_year": fiscal_year,
                    "fy_amounts": fy_amounts,
                    "description_text": "",
                }
            )

    # 4. Extract description text from Section A and Section B
    desc_parts: list[str] = []
    in_section_a = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("A. Mission Description"):
            in_section_a = True
            continue
        if in_section_a:
            if re.match(r"^[B-Z]\.\s", stripped):
                break
            if stripped:
                desc_parts.append(stripped)
    section_a_text = " ".join(desc_parts).strip()

    project_descs: dict[str, str] = {}
    current_title = None
    current_desc_parts: list[str] = []
    in_section_b = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("B. Accomplishments") or stripped.startswith(
            "C. Accomplishments"
        ):
            in_section_b = True
            continue
        if not in_section_b:
            continue
        if re.match(r"^[C-Z]\.\s(?!Accomplishments)", stripped):
            break
        if stripped.startswith("Title:"):
            if current_title and current_desc_parts:
                project_descs[current_title] = " ".join(current_desc_parts).strip()
            title_text = stripped[len("Title:") :].strip()
            title_text = re.sub(r"\s+[\d,.]+\s*$", "", title_text).strip()
            current_title = title_text
            current_desc_parts = []
        elif stripped.startswith("Description:") and current_title:
            current_desc_parts.append(stripped[len("Description:") :].strip())
        elif current_title and current_desc_parts and not stripped.startswith("FY "):
            if not re.match(r"^(Accomplishments|Congressional|Title:)", stripped):
                current_desc_parts.append(stripped)
    if current_title and current_desc_parts:
        project_descs[current_title] = " ".join(current_desc_parts).strip()

    for item in results:
        parts = []
        if section_a_text:
            parts.append(section_a_text)
        proj_title = item["project_title"]
        for desc_title, desc_text in project_descs.items():
            if proj_title.lower().startswith(
                desc_title[:20].lower()
            ) or desc_title.lower().startswith(proj_title[:20].lower()):
                parts.append(f"[{desc_title}] {desc_text}")
                break
        raw_desc = "\n\n".join(parts) if parts else ""
        item["description_text"] = clean_narrative(raw_desc) if raw_desc else ""

    return results


def consolidate_r2_timeseries(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse multiple budget-submission rows into one golden row per project."""
    groups: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for item in items:
        key = (item["pe_number"], item.get("project_code"))
        groups.setdefault(key, []).append(item)

    results: list[dict[str, Any]] = []
    for (pe, proj_code), group in groups.items():

        def _doc_fy(item: dict[str, Any]) -> int:
            m = re.search(r"(\d{4})", item.get("fiscal_year", ""))
            return int(m.group(1)) if m else 0

        group.sort(key=_doc_fy, reverse=True)

        golden_amounts: dict[str, float] = {}
        golden_refs: dict[str, str] = {}
        for item in group:
            for fy_key, amount in item["fy_amounts"].items():
                if fy_key not in golden_amounts:
                    golden_amounts[fy_key] = amount
                    golden_refs[fy_key] = item["source_file"]

        latest = group[0]
        best_desc = ""
        for item in group:
            desc = item.get("description_text", "")
            if len(desc) > len(best_desc):
                best_desc = desc
        results.append(
            {
                "pe_number": pe,
                "pe_title": latest.get("pe_title"),
                "project_code": proj_code,
                "project_title": latest["project_title"],
                "source_file": latest["source_file"],
                "fiscal_year": latest["fiscal_year"],
                "fy_amounts": golden_amounts,
                "fy_refs": golden_refs,
                "description_text": best_desc,
            }
        )

    return results


def mine_pdf_subelements(
    conn: sqlite3.Connection,
    pe_numbers: set[str],
    keywords: list[str],
    core_pes: set[str] | None = None,
    fy_start: int = FY_START,
) -> tuple[list[dict[str, Any]], set[str]]:
    """Mine R-2/R-2A sub-element data from pdf_pages for the given PE numbers.

    Returns (consolidated_rows, discovered_pes).
    """
    if not pe_numbers:
        return [], set()

    try:
        conn.execute("SELECT 1 FROM pdf_pages LIMIT 0")
    except sqlite3.OperationalError:
        return [], set()

    if core_pes is None:
        core_pes = pe_numbers

    fy_min_str = f"FY {fy_start}"

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

    logger.info(
        "PDF sub-element mining: scanning %d R-2/R-2A pages for %d PEs",
        len(rows),
        len(pe_numbers),
    )

    seen: set[tuple[str, str | None, str]] = set()
    raw_items: list[dict[str, Any]] = []
    discovered_pes: set[str] = set()

    for r in rows:
        source_file, page_number, page_text, fiscal_year = r
        parsed = parse_r2_cost_block(page_text, source_file, fiscal_year)
        for item in parsed:
            pe = item["pe_number"]
            key = (pe, item.get("project_code"), fiscal_year)
            if key in seen:
                continue

            if pe in pe_numbers:
                seen.add(key)
                raw_items.append(item)
            else:
                text_fields = [
                    item.get("project_title", ""),
                    item.get("description_text", ""),
                    item.get("pe_title", ""),
                ]
                matched = find_matched_keywords(text_fields, keywords)
                if matched:
                    item["_matched_r2_keywords"] = matched
                    seen.add(key)
                    raw_items.append(item)
                    discovered_pes.add(pe)

    if discovered_pes:
        logger.info(
            "PDF sub-element mining: discovered %d new PEs via R-2 keyword matches: %s",
            len(discovered_pes),
            ", ".join(sorted(discovered_pes)),
        )

    logger.info(
        "PDF sub-element mining: %d raw rows before consolidation", len(raw_items)
    )

    consolidated = consolidate_r2_timeseries(raw_items)

    for item in consolidated:
        if not item.get("_matched_r2_keywords"):
            text_fields = [
                item.get("project_title", ""),
                item.get("description_text", ""),
                item.get("pe_title", ""),
            ]
            matched = find_matched_keywords(text_fields, keywords)
            if matched:
                item["_matched_r2_keywords"] = matched

    logger.info(
        "PDF sub-element mining: %d final project rows (%d discovered PEs)",
        len(consolidated),
        len(discovered_pes),
    )
    return consolidated, discovered_pes


def normalize_program_name(title: str) -> str:
    """Extract a canonical short name for cross-PE matching."""
    s = re.sub(r"^[A-Z0-9]+:\s*", "", title)
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s)
    return " ".join(s.lower().split())


def annotate_cross_pe_lineages(
    conn: sqlite3.Connection,
    cache_table: str,
) -> None:
    """Detect R-2 projects that migrated across PEs and annotate with lineage_note."""
    rows = conn.execute(f"""
        SELECT id, pe_number, line_item_title
        FROM {cache_table}
        WHERE exhibit_type = 'r2'
    """).fetchall()

    if not rows:
        return

    from collections import defaultdict

    name_groups: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for row_id, pe, title in rows:
        norm = normalize_program_name(title)
        if norm:
            name_groups[norm].append((row_id, pe, title))

    updates: list[tuple[str, int]] = []
    for norm_name, members in name_groups.items():
        pe_set = {pe for _, pe, _ in members}
        if len(pe_set) < 2:
            continue
        sorted_members = sorted(members, key=lambda x: x[1])
        for row_id, pe, title in sorted_members:
            other_pes = sorted(p for p in pe_set if p != pe)
            if not other_pes:
                continue
            note = "Also in PE " + ", ".join(other_pes)
            updates.append((note, row_id))

    if updates:
        conn.executemany(
            f"UPDATE {cache_table} SET lineage_note = ? WHERE id = ?",
            updates,
        )
        logger.info("Cross-PE lineage: annotated %d R-2 rows", len(updates))


# ── Query helpers ─────────────────────────────────────────────────────────────


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
    result: list[dict] = []
    for r in rows:
        d = dict(r)
        for field in ("matched_keywords_row", "matched_keywords_desc"):
            kw_json = d.get(field, "[]")
            try:
                d[field] = json.loads(kw_json) if kw_json else []
            except (json.JSONDecodeError, TypeError):
                d[field] = []
        refs: dict[str, str] = {}
        for yr in year_range:
            ref_key = f"fy{yr}_ref"
            val = d.pop(ref_key, None)
            if val:
                refs[f"fy{yr}"] = val
        d["refs"] = refs
        result.append(d)
    return result


def load_per_fy_descriptions(
    conn: sqlite3.Connection,
    pe_numbers: list[str] | set[str],
    min_length: int = 80,
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

    placeholders = ", ".join("?" for _ in pes)
    rows = conn.execute(
        f"SELECT pe_number, fiscal_year, section_header, description_text "
        f"FROM pe_descriptions "
        f"WHERE pe_number IN ({placeholders}) "
        f"  AND section_header IS NOT NULL "
        f"ORDER BY pe_number, fiscal_year, "
        f"  CASE "
        f"    WHEN section_header LIKE '%Mission Description%' THEN 1 "
        f"    WHEN section_header LIKE '%Accomplishments%' THEN 2 "
        f"    WHEN section_header LIKE '%Acquisition Strategy%' THEN 3 "
        f"    ELSE 4 END",
        pes,
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


# ── Shared XLSX styles ───────────────────────────────────────────────────────


def xlsx_base_styles() -> dict[str, Any]:
    """Return a dict of openpyxl style objects shared across XLSX export endpoints.

    Lazily imports openpyxl so module load stays cheap.
    """
    from openpyxl.styles import Font, PatternFill

    return {
        "header_fill": PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid"),
        "header_font": Font(bold=True, size=11, color="FFFFFF"),
        "base_font": Font(size=10),
        "italic_font": Font(italic=True, color="888888", size=10),
        "total_font": Font(bold=True, size=11),
        "source_font": Font(size=9, color="666666"),
        "desc_font": Font(size=9, color="444444"),
        "money_fmt": "#,##0",
    }


# ── R-1 stub enrichment helpers ──────────────────────────────────────────────


def _extract_r1_titles_for_stubs(
    conn: sqlite3.Connection,
    cache_table: str,
    pdf_only_pes: set[str],
) -> None:
    """Extract real R-1 titles from PDF pages for stub rows.

    For each PDF-only PE, query pdf_pages (joined with pdf_pe_numbers) for
    pages whose text contains 'Exhibit R-1'. Parse the PE title from the
    first ~10 lines using the standard ``PE <number> / <title>`` pattern
    and UPDATE the stub row's line_item_title.

    If the PE already has a non-PE-number title (e.g. from pe_index), and
    the PDF title differs, log the mismatch but don't overwrite.
    """
    sorted_pes = sorted(pdf_only_pes)
    placeholders = ", ".join("?" for _ in sorted_pes)

    # Batch-fetch all R-1 exhibit pages for the full PE set in one query
    try:
        rows = conn.execute(
            f"""
            SELECT ppn.pe_number, pp.page_text
            FROM pdf_pages pp
            JOIN pdf_pe_numbers ppn ON ppn.pdf_page_id = pp.id
            WHERE ppn.pe_number IN ({placeholders})
              AND pp.page_text LIKE '%Exhibit R-1%'
            """,
            sorted_pes,
        ).fetchall()
    except sqlite3.OperationalError:
        logger.debug("Cannot query pdf_pe_numbers for R-1 titles (table missing?)")
        return

    # Group page texts by PE
    pe_pages: dict[str, list[str]] = {}
    for pe_num, page_text in rows:
        pe_pages.setdefault(pe_num, []).append(page_text)

    # Batch-fetch current cache titles for all PEs
    cache_rows = conn.execute(
        f"SELECT pe_number, line_item_title FROM {cache_table} "
        f"WHERE pe_number IN ({placeholders}) AND exhibit_type = 'r1'",
        sorted_pes,
    ).fetchall()
    current_titles = {r[0]: r[1] for r in cache_rows}

    update_batch: list[tuple[str, str, str]] = []
    for pe in sorted_pes:
        pages = pe_pages.get(pe, [])
        pdf_title = None
        for page_text in pages:
            for line in page_text.split("\n")[:10]:
                m = _PE_TITLE_RE.search(line)
                if m and m.group(1) == pe:
                    pdf_title = m.group(2).strip()
                    break
            if pdf_title:
                break

        if not pdf_title:
            continue

        current_title = current_titles.get(pe)
        if current_title == pe:
            update_batch.append((pdf_title, pe, pe))
            logger.debug("R-1 title for %s set from PDF: %s", pe, pdf_title)
        elif current_title and current_title != pdf_title:
            logger.info(
                "R-1 title mismatch for %s: cache='%s', pdf='%s'",
                pe,
                current_title,
                pdf_title,
            )

    if update_batch:
        conn.executemany(
            f"UPDATE {cache_table} SET line_item_title = ? "
            f"WHERE pe_number = ? AND exhibit_type = 'r1' AND line_item_title = ?",
            update_batch,
        )


def _aggregate_r2_funding_into_r1_stubs(
    conn: sqlite3.Connection,
    cache_table: str,
    year_range: list[int],
) -> None:
    """Sum R-2 sub-element funding into R-1 stub rows with NULL amounts.

    Only updates stub rows (where the FY amounts are NULL), preserving any
    R-1 rows that already have budget_lines-sourced funding data.
    """
    fy_cols = [f"fy{yr}" for yr in year_range]
    null_check = " AND ".join(f"stub.{col} IS NULL" for col in fy_cols)

    # Aggregate all FY columns in one pass via CTE, then UPDATE-FROM
    sum_cols = ", ".join(f"SUM({col}) AS {col}" for col in fy_cols)
    set_sql = ", ".join(f"{col} = sums.{col}" for col in fy_cols)

    result = conn.execute(
        f"WITH sums AS ("
        f"  SELECT pe_number, {sum_cols} FROM {cache_table} "
        f"  WHERE exhibit_type = 'r2' GROUP BY pe_number"
        f") "
        f"UPDATE {cache_table} AS stub SET {set_sql} "
        f"FROM sums "
        f"WHERE stub.pe_number = sums.pe_number "
        f"AND stub.exhibit_type = 'r1' AND ({null_check})"
    )

    if result.rowcount:
        logger.info("R-1 funding aggregated from R-2 sub-elements for %d PEs", result.rowcount)


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
        ep_placeholders = ", ".join("?" for _ in extra_set)
        existing = conn.execute(
            f"SELECT DISTINCT pe_number FROM budget_lines WHERE pe_number IN ({ep_placeholders})",
            list(extra_set),
        ).fetchall()
        found_extra = {r[0] for r in existing}
        # Also check pe_index for PDF-only PEs (e.g., D8Z Defense-Wide programs)
        remaining = extra_set - found_extra
        if remaining:
            try:
                rp = ", ".join("?" for _ in remaining)
                pi_rows = conn.execute(
                    f"SELECT DISTINCT pe_number FROM pe_index WHERE pe_number IN ({rp})",
                    list(remaining),
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
    pe_placeholders = ", ".join("?" for _ in matched_pes)
    pe_params = list(matched_pes)

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
        HAVING COUNT(*) > 0
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
    ]
    for yr in year_range:
        insert_cols.extend([f"fy{yr}", f"fy{yr}_ref"])
    placeholders_insert = ", ".join("?" for _ in insert_cols)
    insert_sql = f"INSERT INTO {cache_table} ({', '.join(insert_cols)}) VALUES ({placeholders_insert})"

    count = 0
    for r in rows:
        d = dict(r)
        text_fields = [
            d.get("line_item_title"),
            d.get("account_title"),
            d.get("budget_activity_title"),
        ]
        row_kws = find_matched_keywords(text_fields, keywords)

        vals = [
            d["pe_number"],
            d.get("organization_name"),
            d.get("exhibit_type"),
            d.get("line_item_title"),
            d.get("budget_activity"),
            d.get("budget_activity_title"),
            normalize_budget_activity(
                d.get("budget_activity"), d.get("budget_activity_title")
            ),
            d.get("appropriation_title"),
            d.get("account_title"),
            color_of_money(d.get("appropriation_title")),
            json.dumps(row_kws) if row_kws else "[]",
            "[]",  # matched_keywords_desc — set per-row only for R-2 sub-elements
            (
                None
                if _is_garbage_description(desc_map.get(d["pe_number"]))
                else desc_map.get(d["pe_number"])
            ),
        ]
        for yr in year_range:
            vals.append(d.get(f"fy{yr}"))
            vals.append(d.get(f"fy{yr}_ref"))

        conn.execute(insert_sql, vals)
        count += 1

    # 6a. Insert stub R-1 rows for extra PEs that exist only in PDFs (no budget_lines data).
    # This ensures they appear in the cache even if the R-2 mining step doesn't find them.
    if extra_pes:
        cached_pes = {
            r[0]
            for r in conn.execute(
                f"SELECT DISTINCT pe_number FROM {cache_table}"
            ).fetchall()
        }
        pdf_only_pes = (set(extra_pes) & matched_pes) - cached_pes
        if pdf_only_pes:
            # Pull metadata from pe_index
            pp = ", ".join("?" for _ in pdf_only_pes)
            pi_meta = conn.execute(
                f"SELECT pe_number, display_title, organization_name FROM pe_index WHERE pe_number IN ({pp})",
                list(pdf_only_pes),
            ).fetchall()
            pi_map = {r[0]: (r[1], r[2]) for r in pi_meta}
            stub_desc_map = get_description_map(conn, pdf_only_pes)
            for pe in sorted(pdf_only_pes):
                title, org = pi_map.get(pe, (None, None))
                desc = stub_desc_map.get(pe)
                if _is_garbage_description(desc):
                    desc = None
                vals = [
                    pe,
                    org,
                    "r1",
                    title or pe,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "RDT&E",
                    "[]",
                    "[]",
                    desc,
                ]
                for yr in year_range:
                    vals.extend([None, None])
                conn.execute(insert_sql, vals)
                count += 1
            logger.info(
                "Cache: inserted %d stub rows for PDF-only extra PEs", len(pdf_only_pes)
            )

            _extract_r1_titles_for_stubs(conn, cache_table, pdf_only_pes)

    _progress("mining_pdfs", budget_line_rows=count)

    # 6b. Insert PDF-mined R-2/R-2A sub-elements
    pdf_subelements, discovered_pes = mine_pdf_subelements(
        conn,
        matched_pes,
        keywords,
        core_pes=bl_pes,
        fy_start=fy_start,
    )

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
              AND CAST(fiscal_year AS INTEGER) >= {fy_start}
            GROUP BY pe_number, exhibit_type, line_item_title
            ORDER BY pe_number, exhibit_type, line_item_title
        """
        disc_rows = conn.execute(disc_sql, list(discovered_pes)).fetchall()
        disc_desc_map = get_description_map(conn, discovered_pes)
        for r in disc_rows:
            d = dict(r)
            text_fields = [
                d.get("line_item_title"),
                d.get("account_title"),
                d.get("budget_activity_title"),
            ]
            row_kws = find_matched_keywords(text_fields, keywords)
            vals = [
                d["pe_number"],
                d.get("organization_name"),
                d.get("exhibit_type"),
                d.get("line_item_title"),
                d.get("budget_activity"),
                d.get("budget_activity_title"),
                normalize_budget_activity(
                    d.get("budget_activity"), d.get("budget_activity_title")
                ),
                d.get("appropriation_title"),
                d.get("account_title"),
                color_of_money(d.get("appropriation_title")),
                json.dumps(row_kws) if row_kws else "[]",
                "[]",  # matched_keywords_desc — set per-row only for R-2 sub-elements
                (
                    None
                    if _is_garbage_description(disc_desc_map.get(d["pe_number"]))
                    else disc_desc_map.get(d["pe_number"])
                ),
            ]
            for yr in year_range:
                vals.append(d.get(f"fy{yr}"))
                vals.append(d.get(f"fy{yr}_ref"))
            conn.execute(insert_sql, vals)
            count += 1
        logger.info(
            "Cache: added %d R-1 rows for %d discovered PEs",
            len(disc_rows),
            len(discovered_pes),
        )

    pdf_count = 0
    for item in pdf_subelements:
        pe = item["pe_number"]
        title = item["project_title"]
        if item.get("project_code"):
            title = f"{item['project_code']}: {title}"

        row_kws = item.get("_matched_r2_keywords") or find_matched_keywords(
            [title], keywords
        )
        r2_desc = item.get("description_text", "")
        if _is_garbage_description(r2_desc):
            r2_desc = ""
        fallback = desc_map.get(pe)
        if _is_garbage_description(fallback):
            fallback = None
        description = r2_desc if r2_desc else fallback
        # Check the sub-element's own description for keyword matches
        desc_kws = (
            find_matched_keywords([r2_desc, title], desc_keywords) if r2_desc else []
        )
        desc_kws = [kw for kw in desc_kws if kw not in row_kws]

        vals = [
            pe,
            None,  # organization_name — not in PDF text, filled below
            "r2",
            title,
            None,  # budget_activity
            None,  # budget_activity_title
            None,  # budget_activity_norm
            None,  # appropriation_title
            item.get("pe_title"),
            "RDT&E",
            json.dumps(row_kws) if row_kws else "[]",
            json.dumps(desc_kws) if desc_kws else "[]",
            description,
        ]
        fy_refs = item.get("fy_refs", {})
        for yr in year_range:
            fy_key = f"fy{yr}"
            vals.append(item["fy_amounts"].get(fy_key))
            vals.append(
                fy_refs.get(fy_key)
                if item["fy_amounts"].get(fy_key) is not None
                else None
            )

        conn.execute(insert_sql, vals)
        pdf_count += 1

    if pdf_count:
        # Back-fill organization_name from R-1 rows
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

        # Fallback: infer organization from source_file path
        latest_ref_col = f"fy{year_range[-1]}_ref"
        fallback_ref_col = (
            f"fy{year_range[-2]}_ref" if len(year_range) > 1 else latest_ref_col
        )
        for path_fragment, org_name in _ORG_FROM_PATH:
            conn.execute(
                f"""
                UPDATE {cache_table}
                SET organization_name = ?
                WHERE (organization_name IS NULL OR organization_name = '')
                  AND ({latest_ref_col} LIKE ? OR {fallback_ref_col} LIKE ?)
                """,
                [org_name, f"%{path_fragment}%", f"%{path_fragment}%"],
            )

        # Final fallback: fill from pe_index (enrichment Phase 1)
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
            pass  # pe_index may not exist if enrichment hasn't run

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
