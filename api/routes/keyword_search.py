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

        first_num_pos = re.search(r"\s[\d,]+\.\d{2,3}|\s-\s|\s-$", line)
        if first_num_pos:
            prefix = line[: first_num_pos.start()].strip()
        else:
            prefix = line.strip()

        # Clean the extracted title: strip any remaining trailing amounts,
        # normalize project codes, and reject junk rows.
        from utils.normalization import clean_r2_title
        project_code, project_title = clean_r2_title(prefix)
        if project_code is None and project_title is None:
            continue  # junk row (table header/footer/total)
        if project_title is None:
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
    from utils.normalization import normalize_r2_project_code

    groups: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for item in items:
        raw_code = item.get("project_code")
        norm_code = normalize_r2_project_code(raw_code)
        # Fallback: extract code from title if none parsed
        if norm_code is None:
            m = re.match(r"^[Ee]?(\d{3,5})\s+", item.get("project_title", ""))
            if m:
                norm_code = m.group(1).lstrip("0") or m.group(1)
        key = (item["pe_number"], norm_code)
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
    """Return xlsxwriter format property dicts for shared XLSX styling.

    Returns raw dicts — consumers call ``wb.add_format(props)`` to create
    workbook-bound Format objects (xlsxwriter formats are per-workbook).
    """
    return {
        "header": {"bold": True, "font_size": 11, "font_color": "#FFFFFF",
                   "bg_color": "#2C3E50", "text_wrap": True, "align": "center"},
        "base": {"font_size": 10},
        "italic": {"italic": True, "font_color": "#888888", "font_size": 10},
        "total": {"bold": True, "font_size": 11},
        "source": {"font_size": 9, "font_color": "#666666", "valign": "top"},
        "desc": {"font_size": 9, "font_color": "#444444", "valign": "top"},
        "money_fmt": "$#,##0",
    }


# ── Shared XLSX workbook builder ─────────────────────────────────────────────

# Default column widths keyed by header name.
_COL_WIDTH_DEFAULTS: dict[str, int] = {
    "PE Number": 14, "Service/Org": 14,
    "Exhibit": 8, "Exhibit Type": 8,
    "Line Item / Sub-Program": 50, "Line Item Title": 50,
    "Budget Activity": 20, "Budget Activity (Normalized)": 20,
    "Appropriation": 30, "Color of Money": 12,
    "Keywords (Row)": 20, "Keywords (Desc)": 20,
    "Description": 60, "In Totals": 10,
}


def _col_letter(one_based: int) -> str:
    """Convert a 1-based column index to an Excel letter (1 → 'A')."""
    from xlsxwriter.utility import xl_col_to_name
    return xl_col_to_name(one_based - 1)


def build_keyword_xlsx(
    items: list[dict],
    active_years: list[int],
    desc_by_pe_fy: dict[tuple[str, str], str],
    fixed_columns: list[tuple[str, str]],
    include_source: bool = True,
    include_description: bool = True,
    include_intotal: bool = True,
    include_desc_keywords: bool = True,
    sheet_title: str = "Results",
    build_summary: bool = True,
    keywords: list[str] | None = None,
    fy_desc_kws: dict[tuple[str, str], list[str]] | None = None,
    pe_has_r2_match: set[str] | None = None,
) -> bytes:
    """Build a keyword-search XLSX workbook and return it as bytes.

    Uses xlsxwriter for proper Excel 365 dynamic array formula support.
    Y/N/P is computed per-FY based on description keyword matches.
    """
    import io

    import xlsxwriter

    sty = xlsx_base_styles()
    money_fmt_str = sty["money_fmt"]
    fixed_count = len(fixed_columns)

    if fy_desc_kws is None:
        fy_desc_kws = {}
    if pe_has_r2_match is None:
        pe_has_r2_match = set()

    # Compute FY column stride and per-year column positions (1-based)
    fy_stride = (1 + int(include_intotal) + int(include_source)
                 + int(include_description) + int(include_desc_keywords))

    class _FyCols:
        __slots__ = ("val", "intotal", "src", "desc", "desc_kw",
                     "val_l", "intotal_l", "src_l", "desc_l", "desc_kw_l")

        def __init__(self, fy_idx: int) -> None:
            base = fixed_count + (fy_idx * fy_stride) + 1
            col = base
            self.val = col
            col += 1
            self.intotal = col if include_intotal else 0
            if include_intotal:
                col += 1
            self.src = col if include_source else 0
            if include_source:
                col += 1
            self.desc = col if include_description else 0
            if include_description:
                col += 1
            self.desc_kw = col if include_desc_keywords else 0
            self.val_l = _col_letter(self.val)
            self.intotal_l = _col_letter(self.intotal) if self.intotal else ""
            self.src_l = _col_letter(self.src) if self.src else ""
            self.desc_l = _col_letter(self.desc) if self.desc else ""
            self.desc_kw_l = _col_letter(self.desc_kw) if self.desc_kw else ""

    fy_cols = [_FyCols(i) for i in range(len(active_years))]
    intotal_letters = [fc.intotal_l for fc in fy_cols if fc.intotal_l]

    # ── Build workbook ──
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    ws = wb.add_worksheet(sheet_title)

    # Create all Format objects once (xlsxwriter formats are workbook-bound)
    fmt = {
        "header": wb.add_format(sty["header"]),
        "base": wb.add_format(sty["base"]),
        "base_money": wb.add_format({**sty["base"], "num_format": money_fmt_str}),
        "total": wb.add_format(sty["total"]),
        "total_money": wb.add_format({**sty["total"], "num_format": money_fmt_str}),
        "source": wb.add_format(sty["source"]),
        "desc": wb.add_format(sty["desc"]),
        "cf_bold": wb.add_format({"bold": True}),
        "cf_italic_gray": wb.add_format({"italic": True, "font_color": "#888888"}),
        "cf_green": wb.add_format({"bg_color": "#C6EFCE"}),
        "cf_yellow": wb.add_format({"bg_color": "#FFEB9C"}),
        "cf_red": wb.add_format({"bg_color": "#FFC7CE"}),
    }

    # ── Headers (row 0, 0-indexed) ──
    headers: list[str] = [h for h, _ in fixed_columns]
    for yr in active_years:
        headers.append(f"FY{yr} ($K)")
        if include_intotal:
            headers.append(f"FY{yr} In Total")
        if include_source:
            headers.append(f"FY{yr} Source")
        if include_description:
            headers.append(f"FY{yr} Description")
        if include_desc_keywords:
            headers.append(f"FY{yr} Desc Keywords")

    for ci, h in enumerate(headers):
        ws.write(0, ci, h, fmt["header"])

    # ── Data rows (row_num is 1-based for formula references) ──
    first_data_row = 2
    row_num = first_data_row
    for row in items:
        r0 = row_num - 1  # 0-indexed for ws.write
        pe = row.get("pe_number", "")
        et = row.get("exhibit_type", "")

        for ci, (_header, field) in enumerate(fixed_columns):
            val = row.get(field, "")
            if isinstance(val, list):
                val = ", ".join(val)
            ws.write(r0, ci, val if val is not None else "", fmt["base"])

        refs_map = row.get("refs", {}) or {}
        for fi, yr in enumerate(active_years):
            fc = fy_cols[fi]

            amount = row.get(f"fy{yr}")
            if amount is not None:
                ws.write_number(r0, fc.val - 1, amount, fmt["base_money"])
            else:
                ws.write_blank(r0, fc.val - 1, None, fmt["base"])

            if fc.intotal:
                # Per-FY Y/N/P logic based on description keyword matches
                fy_key = (pe, str(yr))
                if fy_key in fy_desc_kws and et in ("r2", "r2_pdf"):
                    in_total = "Y"
                elif fy_key in fy_desc_kws and et == "r1":
                    in_total = "N" if pe in pe_has_r2_match else "P"
                else:
                    in_total = "N"
                ws.write(r0, fc.intotal - 1, in_total, fmt["base"])

            if fc.src:
                source_ref = refs_map.get(f"fy{yr}", "")
                if source_ref:
                    ws.write(r0, fc.src - 1, source_ref, fmt["source"])

            if fc.desc:
                desc_text = desc_by_pe_fy.get((pe, str(yr)), "")
                if desc_text:
                    ws.write(r0, fc.desc - 1, desc_text, fmt["desc"])

            if fc.desc_kw:
                kws = fy_desc_kws.get((pe, str(yr)), [])
                ws.write(r0, fc.desc_kw - 1, ", ".join(kws) if kws else "", fmt["base"])

        row_num += 1

    last_data_row = row_num - 1

    # ── Data validation (Y/N/P dropdown) ──
    if include_intotal and last_data_row >= first_data_row:
        for fc in fy_cols:
            ws.data_validation(
                first_data_row - 1, fc.intotal - 1,
                last_data_row - 1, fc.intotal - 1,
                {"validate": "list", "source": ["Y", "N", "P"],
                 "error_message": "Please enter Y, N, or P",
                 "error_title": "Invalid value"},
            )

    # ── Conditional formatting ──
    if include_intotal and last_data_row >= first_data_row and active_years:
        r1 = first_data_row - 1  # 0-indexed first data row
        r2 = last_data_row - 1   # 0-indexed last data row
        for fc in fy_cols:
            data_cols = [fc.val - 1]
            if fc.src:
                data_cols.append(fc.src - 1)
            if fc.desc:
                data_cols.append(fc.desc - 1)
            for c0 in data_cols:
                ws.conditional_format(r1, c0, r2, c0, {
                    "type": "formula",
                    "criteria": f'=${fc.intotal_l}{first_data_row}="Y"',
                    "format": fmt["cf_bold"],
                })
                ws.conditional_format(r1, c0, r2, c0, {
                    "type": "formula",
                    "criteria": f'=${fc.intotal_l}{first_data_row}="N"',
                    "format": fmt["cf_italic_gray"],
                })
            ic0 = fc.intotal - 1
            for val, key in [("Y", "cf_green"), ("P", "cf_yellow"), ("N", "cf_red")]:
                ws.conditional_format(r1, ic0, r2, ic0, {
                    "type": "formula",
                    "criteria": f'=${fc.intotal_l}{first_data_row}="{val}"',
                    "format": fmt[key],
                })

        or_parts = ",".join(f'${lt}{first_data_row}="Y"' for lt in intotal_letters)
        and_parts = ",".join(f'${lt}{first_data_row}="N"' for lt in intotal_letters)
        ws.conditional_format(r1, 0, r2, fixed_count - 1, {
            "type": "formula",
            "criteria": f"=OR({or_parts})",
            "format": fmt["cf_bold"],
        })
        ws.conditional_format(r1, 0, r2, fixed_count - 1, {
            "type": "formula",
            "criteria": f"=AND({and_parts})",
            "format": fmt["cf_italic_gray"],
        })

    # ── Totals rows ──
    if include_intotal and last_data_row >= first_data_row and active_years:
        y_row, p_row, grand_row = row_num, row_num + 1, row_num + 2
        ws.write(y_row - 1, 0, "Y TOTALS", fmt["total"])
        ws.write(p_row - 1, 0, "P TOTALS", fmt["total"])
        ws.write(grand_row - 1, 0, "GRAND TOTAL", fmt["total"])
        for fc in fy_cols:
            val_rng = f"${fc.val_l}${first_data_row}:${fc.val_l}${last_data_row}"
            it_rng = f"${fc.intotal_l}${first_data_row}:${fc.intotal_l}${last_data_row}"
            for tr, label, criteria in [(y_row, "Y Sum", "Y"), (p_row, "P Sum", "P")]:
                ws.write(tr - 1, fc.intotal - 1, label, fmt["total"])
                ws.write_formula(tr - 1, fc.val - 1,
                                 f'=SUMIF({it_rng},"{criteria}",{val_rng})', fmt["total_money"])
            ws.write(grand_row - 1, fc.intotal - 1, "Grand Sum", fmt["total"])
            ws.write_formula(grand_row - 1, fc.val - 1,
                             f"={fc.val_l}{y_row}+{fc.val_l}{p_row}", fmt["total_money"])
    elif last_data_row >= first_data_row and active_years:
        totals_row = row_num
        ws.write(totals_row - 1, 0, "TOTALS", fmt["total"])
        for fc in fy_cols:
            vr = f"${fc.val_l}${first_data_row}:${fc.val_l}${last_data_row}"
            ws.write_formula(totals_row - 1, fc.val - 1, f"=SUM({vr})", fmt["total_money"])

    # ── Column widths ──
    for ci, (header, _field) in enumerate(fixed_columns):
        ws.set_column(ci, ci, _COL_WIDTH_DEFAULTS.get(header, 14))
    for fc in fy_cols:
        ws.set_column(fc.val - 1, fc.val - 1, 14)
        if fc.intotal:
            ws.set_column(fc.intotal - 1, fc.intotal - 1, 10)
        if fc.src:
            ws.set_column(fc.src - 1, fc.src - 1, 30)
        if fc.desc:
            ws.set_column(fc.desc - 1, fc.desc - 1, 40)
        if fc.desc_kw:
            ws.set_column(fc.desc_kw - 1, fc.desc_kw - 1, 25)

    freeze_col = min(5, fixed_count + 1)
    ws.freeze_panes(1, freeze_col - 1)
    ws.autofilter(0, 0, max(last_data_row, row_num) - 1, len(headers) - 1)

    # ── Selected sheet (dynamic FILTER of data sheet, Y or P rows only) ──
    if include_intotal and last_data_row >= first_data_row and active_years:
        ws_sel = wb.add_worksheet("Selected")

        # Same headers as data sheet
        for ci, h in enumerate(headers):
            ws_sel.write(0, ci, h, fmt["header"])

        # FILTER formula: show rows where ANY In Total column = "Y" or "P"
        data_range = f"'{sheet_title}'!$A${first_data_row}:${_col_letter(len(headers))}${last_data_row}"
        it_checks = []
        for fc in fy_cols:
            if fc.intotal:
                it_col = f"'{sheet_title}'!${fc.intotal_l}${first_data_row}:${fc.intotal_l}${last_data_row}"
                it_checks.append(f'({it_col}="Y")+({it_col}="P")')
        filter_crit = "+".join(it_checks)
        filter_formula = f"=FILTER({data_range},{filter_crit},\"No matching rows\")"
        ws_sel.write_dynamic_array_formula(1, 0, 1, 0, filter_formula, fmt["base"])

        # Copy column widths from data sheet
        for ci, (header, _field) in enumerate(fixed_columns):
            ws_sel.set_column(ci, ci, _COL_WIDTH_DEFAULTS.get(header, 14))
        for fc in fy_cols:
            ws_sel.set_column(fc.val - 1, fc.val - 1, 14, fmt["base_money"])
            if fc.intotal:
                ws_sel.set_column(fc.intotal - 1, fc.intotal - 1, 10)
            if fc.src:
                ws_sel.set_column(fc.src - 1, fc.src - 1, 30)
            if fc.desc:
                ws_sel.set_column(fc.desc - 1, fc.desc - 1, 40)

        ws_sel.freeze_panes(1, freeze_col - 1)

    # ── Summary sheets ──
    if build_summary and include_intotal:
        field_to_col = {field: _col_letter(ci) for ci, (_h, field) in enumerate(fixed_columns, 1)}
        val_letters = [fc.val_l for fc in fy_cols]
        it_letters = [fc.intotal_l for fc in fy_cols]
        _build_xlsx_summary(
            wb, items, active_years, sheet_title,
            field_to_col, val_letters, it_letters,
            first_data_row, last_data_row, fmt,
            keywords=keywords,
        )

    # ── Keyword co-occurrence matrix ──
    if keywords and len(keywords) > 1:
        _build_keyword_matrix(wb, items, keywords, fmt)

    wb.close()
    return buf.getvalue()


def _build_xlsx_summary(
    wb: Any,
    items: list[dict],
    active_years: list[int],
    data_sheet_name: str,
    field_to_col: dict[str, str],
    val_letters: list[str],
    intotal_letters: list[str],
    first_data_row: int,
    last_data_row: int,
    fmt: dict[str, Any] | None = None,
    keywords: list[str] | None = None,
) -> None:
    """Build dynamic Summary sheets using xlsxwriter spill formulas.

    Creates PE Summary, dimension breakdowns (By Service, etc.), Keyword Matrix
    (if keywords provided), and an About sheet with methodology documentation.
    """
    ds = data_sheet_name
    pe_col = field_to_col.get("pe_number", "A")
    n_years = len(active_years)

    pr = f"'{ds}'!${pe_col}${first_data_row}:${pe_col}${last_data_row}"
    vr = [f"'{ds}'!${val_letters[yi]}${first_data_row}:${val_letters[yi]}${last_data_row}" for yi in range(n_years)]
    ir = [f"'{ds}'!${intotal_letters[yi]}${first_data_row}:${intotal_letters[yi]}${last_data_row}" for yi in range(n_years)]

    if fmt is None:
        sty = xlsx_base_styles()
        fmt = {
            "header": wb.add_format(sty["header"]),
            "base": wb.add_format(sty["base"]),
            "base_money": wb.add_format({**sty["base"], "num_format": sty["money_fmt"]}),
            "total": wb.add_format(sty["total"]),
            "total_money": wb.add_format({**sty["total"], "num_format": sty["money_fmt"]}),
        }

    # Pre-compute PE→title map for PE Summary sheet
    pe_titles: dict[str, str] = {}
    for row in items:
        pe = row.get("pe_number", "")
        if not pe or pe in pe_titles:
            continue
        # Prefer R-1 title; will be overwritten by later R-1 rows (last wins)
        if row.get("exhibit_type") == "r1":
            pe_titles[pe] = row.get("line_item_title", pe)
        elif pe not in pe_titles:
            pe_titles[pe] = row.get("line_item_title", pe)
    # Second pass: R-1 titles overwrite any R-2 fallbacks
    for row in items:
        pe = row.get("pe_number", "")
        if pe and row.get("exhibit_type") == "r1" and row.get("line_item_title"):
            pe_titles[pe] = row["line_item_title"]

    # Merged header format (centered, no wrap)
    fmt_merge = wb.add_format({
        "bold": True, "font_size": 11, "font_color": "#FFFFFF",
        "bg_color": "#2C3E50", "align": "center", "valign": "vcenter",
        "border": 1,
    })
    fmt_sub = wb.add_format({
        "bold": True, "font_size": 10, "font_color": "#FFFFFF",
        "bg_color": "#34495E", "align": "center", "border": 1,
    })

    def _write_summary_sheet(
        sheet_name: str,
        label_col: str = "PE Number",
        match_rng: str | None = None,
        include_title: bool = False,
    ) -> None:
        """Write a summary sheet with merged FY headers and Y/P/Total column groups.

        Layout:
        Row 0: Label | (PE Title) |    FY2024 ($K)     |    FY2025 ($K)     |      Row Total      |
        Row 1:       |            |  Y  |  P  | Total  |  Y  |  P  | Total  |  Y  |  P  | Total  |
        Row 2: Total |            | $xx | $xx |  $xx   | ... (SUMPRODUCT)   | $xx | $xx |  $xx   |
        Row 3+: (spill data)
        """
        ws = wb.add_worksheet(sheet_name)
        mr = match_rng or pr
        unique_expr = f"SORT(UNIQUE({mr}))"

        sumifs_y_all = "+".join(f"SUMIFS({vr[yi]},{mr},_xlpm.v,{ir[yi]},\"Y\")" for yi in range(n_years))
        sumifs_p_all = "+".join(f"SUMIFS({vr[yi]},{mr},_xlpm.v,{ir[yi]},\"P\")" for yi in range(n_years))
        filtered = (
            f"FILTER({unique_expr},"
            f"MAP({unique_expr},LAMBDA(_xlpm.v,{sumifs_y_all}+{sumifs_p_all}))<>0,"
            f"\"(none)\")"
        )

        # Column A: label (PE Number or dimension name)
        col = 0
        ws.merge_range(0, col, 1, col, label_col, fmt_merge)
        ws.write(2, col, "Total", fmt["total"])
        ws.write_dynamic_array_formula(3, col, 3, col, f"={filtered}", fmt["base"])
        ws.set_column(col, col, 16, fmt["base"])
        col += 1

        # Column B: PE Title (only for PE Summary)
        if include_title:
            ws.merge_range(0, col, 1, col, "PE Title", fmt_merge)
            ws.write(2, col, "", fmt["total"])
            # Write PE→title lookup table in far-right columns (ZA/ZB)
            lk_col_pe = 200  # column GS (far right, hidden)
            lk_col_title = 201
            for ti, (pe, title) in enumerate(sorted(pe_titles.items())):
                ws.write(ti, lk_col_pe, pe)
                ws.write(ti, lk_col_title, title)
            lk_count = len(pe_titles)
            # INDEX/MATCH formula to look up title from PE in column A
            pe_lk = f"${_col_letter(lk_col_pe + 1)}$1:${_col_letter(lk_col_pe + 1)}${lk_count}"
            ti_lk = f"${_col_letter(lk_col_title + 1)}$1:${_col_letter(lk_col_title + 1)}${lk_count}"
            ws.write_dynamic_array_formula(
                3, col, 3, col,
                f"=MAP({filtered},LAMBDA(_xlpm.v,IFERROR(INDEX({ti_lk},MATCH(_xlpm.v,{pe_lk},0)),_xlpm.v)))",
                fmt["base"],
            )
            ws.set_column(col, col, 40, fmt["base"])
            # Hide lookup columns
            ws.set_column(lk_col_pe, lk_col_title, None, None, {"hidden": True})
            col += 1

        # FY year groups: each gets 3 columns (Y, P, Total) with merged header
        row_tot_y = []
        row_tot_p = []

        for yi in range(n_years):
            yr = active_years[yi]

            # Merged FY header across 3 columns
            ws.merge_range(0, col, 0, col + 2, f"FY{yr} ($K)", fmt_merge)

            for ci, (sub_label, crit) in enumerate([("Y", "Y"), ("P", "P"), ("Total", None)]):
                c = col + ci
                ws.write(1, c, sub_label, fmt_sub)

                if crit:
                    ws.write_formula(2, c,
                                     f'=SUMPRODUCT(({ir[yi]}="{crit}")*{vr[yi]})',
                                     fmt["total_money"])
                    formula = (
                        f"=MAP({filtered},"
                        f"LAMBDA(_xlpm.v,SUMIFS({vr[yi]},{mr},_xlpm.v,{ir[yi]},\"{crit}\")))"
                    )
                    if crit == "Y":
                        row_tot_y.append(f"SUMIFS({vr[yi]},{mr},_xlpm.v,{ir[yi]},\"Y\")")
                    else:
                        row_tot_p.append(f"SUMIFS({vr[yi]},{mr},_xlpm.v,{ir[yi]},\"P\")")
                else:
                    ws.write_formula(2, c,
                                     f'=SUMPRODUCT(({ir[yi]}="Y")*{vr[yi]})+SUMPRODUCT(({ir[yi]}="P")*{vr[yi]})',
                                     fmt["total_money"])
                    formula = (
                        f"=MAP({filtered},"
                        f"LAMBDA(_xlpm.v,"
                        f"SUMIFS({vr[yi]},{mr},_xlpm.v,{ir[yi]},\"Y\")"
                        f"+SUMIFS({vr[yi]},{mr},_xlpm.v,{ir[yi]},\"P\")))"
                    )

                ws.write_dynamic_array_formula(3, c, 3, c, formula, fmt["base_money"])
                ws.set_column(c, c, 14, fmt["base_money"])  # default format for spill rows

            col += 3

        # Row Total group: Y, P, Total (same 3-column pattern)
        ws.merge_range(0, col, 0, col + 2, "Row Total ($K)", fmt_merge)

        for ci, (sub_label, parts_y, parts_p) in enumerate([
            ("Y", row_tot_y, []),
            ("P", [], row_tot_p),
            ("Total", row_tot_y, row_tot_p),
        ]):
            c = col + ci
            ws.write(1, c, sub_label, fmt_sub)

            if sub_label == "Y":
                sp = "+".join(f'SUMPRODUCT(({ir[yi]}="Y")*{vr[yi]})' for yi in range(n_years))
                sumifs = "+".join(parts_y)
            elif sub_label == "P":
                sp = "+".join(f'SUMPRODUCT(({ir[yi]}="P")*{vr[yi]})' for yi in range(n_years))
                sumifs = "+".join(parts_p)
            else:
                sp = "+".join(
                    f'SUMPRODUCT(({ir[yi]}="Y")*{vr[yi]})+SUMPRODUCT(({ir[yi]}="P")*{vr[yi]})'
                    for yi in range(n_years)
                )
                sumifs = "+".join(row_tot_y) + "+" + "+".join(row_tot_p)

            ws.write_formula(2, c, f"={sp}", fmt["total_money"])
            ws.write_dynamic_array_formula(
                3, c, 3, c,
                f"=MAP({filtered},LAMBDA(_xlpm.v,{sumifs}))",
                fmt["base_money"],
            )
            ws.set_column(c, c, 14, fmt["base_money"])

        ws.freeze_panes(3, 1)

    # PE Summary (with title column)
    _write_summary_sheet("PE Summary", include_title=True)

    # Dimension summaries
    svc_col = field_to_col.get("organization_name", "B")
    ba_col = field_to_col.get("budget_activity_norm", field_to_col.get("budget_activity_title", "E"))
    com_col = field_to_col.get("color_of_money", "F")

    for sheet_name, label, dcol in [
        ("By Service", "Service/Agency", svc_col),
        ("By Budget Activity", "Budget Activity", ba_col),
        ("By Color of Money", "Color of Money", com_col),
    ]:
        dim_rng = f"'{ds}'!${dcol}${first_data_row}:${dcol}${last_data_row}"
        _write_summary_sheet(sheet_name, label_col=label, match_rng=dim_rng)

    # ── About sheet (last) ──
    import time as _time

    ws_about = wb.add_worksheet("About")
    fmt_title = wb.add_format({"bold": True, "font_size": 14})
    fmt_section = wb.add_format({"bold": True, "font_size": 12, "bottom": 1})
    fmt_label = wb.add_format({"bold": True, "font_size": 10, "valign": "top"})
    fmt_text = wb.add_format({"font_size": 10, "text_wrap": True, "valign": "top"})

    r = 0
    ws_about.write(r, 0, "DoD Budget Explorer \u2014 Export Documentation", fmt_title)
    r += 1
    ws_about.write(r, 0, "Generated", fmt_label)
    ws_about.write(r, 1, _time.strftime("%Y-%m-%d %H:%M:%S"), fmt_text)
    r += 2

    ws_about.write(r, 0, "Search Parameters", fmt_section)
    r += 1
    ws_about.write(r, 0, "Keywords", fmt_label)
    ws_about.write(r, 1, ", ".join(keywords) if keywords else "(none)", fmt_text)
    r += 1
    ws_about.write(r, 0, "Total rows", fmt_label)
    ws_about.write(r, 1, len(items), fmt_text)
    r += 1
    matching = sum(1 for row in items if row.get("matched_keywords_row") or row.get("matched_keywords_desc"))
    ws_about.write(r, 0, "Matching rows", fmt_label)
    ws_about.write(r, 1, matching, fmt_text)
    r += 1
    unique_pe_count = len({row.get("pe_number") for row in items if row.get("pe_number")})
    ws_about.write(r, 0, "Unique PEs", fmt_label)
    ws_about.write(r, 1, unique_pe_count, fmt_text)
    r += 2

    ws_about.write(r, 0, "Data Source", fmt_section)
    r += 1
    ws_about.write(r, 0, "DoD Comptroller budget justification documents: Excel R-1/R-2 exhibits "
                   "and PDF-mined R-2/R-2A sub-element pages. All amounts in thousands of dollars ($K).", fmt_text)
    r += 2

    ws_about.write(r, 0, "Y/N/P Methodology", fmt_section)
    r += 1
    ws_about.write(r, 0, "Y (Yes)", fmt_label)
    ws_about.write(r, 1, "Row directly matches one or more search keywords. Included in Y totals.", fmt_text)
    r += 1
    ws_about.write(r, 0, "N (No)", fmt_label)
    ws_about.write(r, 1, "Row included for PE context but does not directly match keywords. Excluded from totals.", fmt_text)
    r += 1
    ws_about.write(r, 0, "P (Possible)", fmt_label)
    ws_about.write(r, 1, "User-assigned flag for rows that may be relevant. Change N\u2192P in the data sheet "
                   "and the summary sheets will update automatically.", fmt_text)
    r += 2

    ws_about.write(r, 0, "Sheet Descriptions", fmt_section)
    r += 1
    sheets_desc = [
        (ds, "Raw data with per-year In Total (Y/N/P) flags, conditional formatting, "
         "and data validation. Change flags here to update all summary sheets."),
        ("PE Summary", "Pivot by Program Element. Shows only PEs with non-zero Y+P totals. "
         "Includes PE title lookup. Columns: Y/P/Total per fiscal year."),
        ("By Service", "Pivot by Service/Agency (Army, Navy, Air Force, etc.)."),
        ("By Budget Activity", "Pivot by Budget Activity category."),
        ("By Color of Money", "Pivot by appropriation type (RDT&E, Procurement, etc.)."),
        ("Keyword Matrix", "NxN co-occurrence table showing how often each pair of search "
         "keywords appears together in the same row."),
    ]
    for sname, sdesc in sheets_desc:
        ws_about.write(r, 0, sname, fmt_label)
        ws_about.write(r, 1, sdesc, fmt_text)
        r += 1
    r += 1

    ws_about.write(r, 0, "Caveats", fmt_section)
    r += 1
    caveats = [
        "PDF-mined rows (exhibit_type='r2_pdf') may show 'Unknown' for Budget Activity and Color of Money.",
        "Amounts are in thousands of dollars ($K). Multiply by 1,000 for actual dollar values.",
        "Non-matching rows (N) are included because their parent PE matched a keyword. "
        "They provide context but are excluded from Y totals.",
        "Summary sheets use Excel 365 dynamic array formulas (FILTER, MAP, LAMBDA). "
        "They require Microsoft 365 or Excel 2021+.",
    ]
    for caveat in caveats:
        ws_about.write(r, 0, "\u2022 " + caveat, fmt_text)
        r += 1

    ws_about.set_column(0, 0, 20)
    ws_about.set_column(1, 1, 80)



def _build_keyword_matrix(
    wb: Any,
    items: list[dict],
    keywords: list[str],
    fmt: dict[str, Any] | None = None,
) -> None:
    """Build a keyword co-occurrence matrix sheet.

    Shows an NxN table: cell (i,j) = number of rows where keyword i AND keyword j
    both appear. Diagonal = total rows matching that keyword alone.
    """
    import json

    if fmt is None:
        sty = xlsx_base_styles()
        fmt = {
            "header": wb.add_format(sty["header"]),
            "base": wb.add_format(sty["base"]),
            "total": wb.add_format(sty["total"]),
        }

    ws = wb.add_worksheet("Keyword Matrix")

    fmt_header_rot = wb.add_format({
        "bold": True, "font_size": 11, "font_color": "#FFFFFF",
        "bg_color": "#2C3E50", "align": "center", "rotation": 90,
    })
    fmt_center = wb.add_format({"font_size": 10, "align": "center"})
    fmt_diag = wb.add_format({"bold": True, "font_size": 11, "bg_color": "#D6E4F0", "align": "center"})

    kw_lower = [kw.lower() for kw in keywords]
    kw_display = list(keywords)

    row_kw_sets: list[set[str]] = []
    for row in items:
        kws_r = row.get("matched_keywords_row", [])
        kws_d = row.get("matched_keywords_desc", [])
        if isinstance(kws_r, str):
            kws_r = json.loads(kws_r) if kws_r else []
        if isinstance(kws_d, str):
            kws_d = json.loads(kws_d) if kws_d else []
        combined = {k.lower() for k in kws_r} | {k.lower() for k in kws_d}
        if combined:
            row_kw_sets.append(combined)

    n = len(kw_lower)
    matrix = [[0] * n for _ in range(n)]
    for kw_set in row_kw_sets:
        present = [i for i in range(n) if kw_lower[i] in kw_set]
        for i in present:
            for j in present:
                matrix[i][j] += 1

    active = [i for i in range(n) if matrix[i][i] > 0]
    if not active:
        ws.write(0, 0, "No keyword matches found.", fmt["base"])
        return

    ws.write(0, 0, "Keyword", fmt["header"])
    for ci, idx in enumerate(active):
        ws.write(0, 1 + ci, kw_display[idx], fmt_header_rot)
    ws.write(0, 1 + len(active), "Total", fmt["header"])

    for ri, idx_i in enumerate(active):
        ws.write(1 + ri, 0, kw_display[idx_i], fmt["base"])
        for ci, idx_j in enumerate(active):
            val = matrix[idx_i][idx_j]
            cell_fmt = fmt_diag if idx_i == idx_j else fmt_center
            ws.write(1 + ri, 1 + ci, val if val > 0 else "", cell_fmt)
        ws.write(1 + ri, 1 + len(active), matrix[idx_i][idx_i], fmt["total"])

    ws.set_column(0, 0, 28)
    ws.set_column(1, len(active) + 1, 6)
    ws.freeze_panes(1, 1)


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
        rows = list(rows) + [dict(r) for r in disc_rows]
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
            return
        clean_title = f"{cleaned_code}: {cleaned_title}" if cleaned_code else (cleaned_title or raw)
        d["line_item_title"] = clean_title
        d["_project_code"] = normalize_r2_project_code(cleaned_code)
        d["_clean_title_only"] = cleaned_title or clean_title
        d["_consolidated"] = []
        key = (d["pe_number"], d["_project_code"] or clean_title)
        r2_by_code.setdefault(key, []).append(d)

    r1_rows: list[dict] = []
    r2_by_code: dict[tuple[str, str | None], list[dict]] = {}
    other_rows: list[dict] = []

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
        all_pe_nums = sorted({d.get("pe_number") for d in other_rows if d.get("pe_number")}
                             | {d.get("pe_number", "") for group in r2_by_code.values() for d in group})
        if all_pe_nums:
            ph = ", ".join("?" for _ in all_pe_nums)
            desc_rows = conn.execute(
                f"SELECT pe_number, description_text FROM pe_descriptions "
                f"WHERE pe_number IN ({ph}) AND description_text IS NOT NULL",
                list(all_pe_nums),
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
        if _is_garbage_description(r2_desc):
            r2_desc = ""
        fallback = desc_map.get(item["pe_number"])
        if _is_garbage_description(fallback):
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
    def _merge_into(target: dict, source: dict) -> None:
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
        # Merge FY amounts (first non-null wins)
        for yr in year_range:
            col = f"fy{yr}"
            if target.get(col) is None and source.get(col) is not None:
                target[col] = source[col]
                ref_col = f"fy{yr}_ref"
                if source.get(ref_col):
                    target[ref_col] = source[ref_col]
        # Track consolidated title variants
        if source["line_item_title"] != target["line_item_title"]:
            target.setdefault("_consolidated", []).append(source["line_item_title"])
        target["_consolidated"].extend(source.get("_consolidated", []))

    merged_r2: dict[tuple[str, str], dict] = {}
    for (_pe, _code), group in r2_by_code.items():
        # Sort: r2 (Excel) first so they become the merge target
        group.sort(key=lambda d: (0 if d.get("exhibit_type") == "r2" else 1))

        clusters: list[dict] = []
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
                if dist / max(shorter, 1) < 0.20:
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

    # Format consolidated titles for display
    for row in merged_r2.values():
        consolidated = row.pop("_consolidated", [])
        if consolidated:
            unique_alts = sorted(set(t for t in consolidated if t != row["line_item_title"]))
            row["_consolidated_titles"] = "; ".join(unique_alts) if unique_alts else ""
        else:
            row["_consolidated_titles"] = ""
        row.pop("_project_code", None)
        row.pop("_clean_title_only", None)

    # Dedup R1 rows: same PE may have variant titles across FYs.
    # Keep the longest title, merge FY amounts.
    r1_dedup: dict[str, dict] = {}
    deduped_other: list[dict] = []
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

    count = 0
    for d in all_rows:
        text_fields = [
            d.get("line_item_title"),
            d.get("account_title"),
            d.get("budget_activity_title"),
        ]
        row_kws = find_matched_keywords(text_fields, keywords)

        # Use inherited BA/CoM from R1 if available
        ba_norm = normalize_budget_activity(
            d.get("budget_activity"), d.get("budget_activity_title")
        )
        if (not ba_norm or ba_norm == "Unknown") and d.get("budget_activity_title"):
            ba_norm = d["budget_activity_title"]  # may have been set by R1 inheritance
        elif not ba_norm or ba_norm == "Unknown":
            ba_norm = r1_ba.get(d["pe_number"])

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

    # PDF-mined R-2 rows were already merged into the pre-pass above (r2_by_code).
    # The back-fill and lineage annotation still run on the combined result.
    pdf_count = sum(1 for d in merged_r2.values() if d.get("exhibit_type") == "r2")
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
