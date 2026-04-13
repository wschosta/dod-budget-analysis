"""R-2 PDF parsing, sub-element mining, and R-1 stub enrichment.

Extracted from keyword_search.py. Contains:
- parse_r2_cost_block: Parse R-2 COST tables from PDF page text
- consolidate_r2_timeseries: Merge multi-year R-2 rows per project
- mine_pdf_subelements: Discover and mine R-2 sub-elements from pdf_pages
- annotate_cross_pe_lineages: Detect programs that migrated across PEs
- R-1 stub enrichment helpers
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections import defaultdict
from typing import Any

from api.routes.keyword_helpers import (
    FY_START,
    PE_TITLE_RE,
    find_matched_keywords,
    in_clause,
)
from utils.normalization import clean_r2_title, normalize_r2_project_code
from utils.strings import clean_narrative

logger = logging.getLogger(__name__)


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
        m = PE_TITLE_RE.search(line)
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

    def _doc_fy(item: dict[str, Any]) -> int:
        m = re.search(r"(\d{4})", item.get("fiscal_year", ""))
        return int(m.group(1)) if m else 0

    results: list[dict[str, Any]] = []
    for (pe, proj_code), group in groups.items():
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

    name_groups: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for row_id, pe, title in rows:
        # Skip Congressional Adds (9999) — intentionally multi-PE, not migrations
        if title and title.startswith("9999"):
            continue
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
            f"""UPDATE {cache_table}
                SET lineage_note = CASE
                    WHEN lineage_note IS NOT NULL AND lineage_note != ''
                    THEN lineage_note || '; ' || ?
                    ELSE ?
                END
                WHERE id = ?""",
            # note twice: once for the append branch, once for the else branch
            [(note, note, row_id) for note, row_id in updates],
        )
        logger.info("Cross-PE lineage: annotated %d R-2 rows", len(updates))


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
    ph, pe_params = in_clause(sorted_pes)

    # Batch-fetch all R-1 exhibit pages for the full PE set in one query
    try:
        rows = conn.execute(
            f"""
            SELECT ppn.pe_number, pp.page_text
            FROM pdf_pages pp
            JOIN pdf_pe_numbers ppn ON ppn.pdf_page_id = pp.id
            WHERE ppn.pe_number IN ({ph})
              AND pp.page_text LIKE '%Exhibit R-1%'
            """,
            pe_params,
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
        f"WHERE pe_number IN ({ph}) AND exhibit_type = 'r1'",
        pe_params,
    ).fetchall()
    current_titles = {r[0]: r[1] for r in cache_rows}

    update_batch: list[tuple[str, str, str]] = []
    for pe in sorted_pes:
        pages = pe_pages.get(pe, [])
        pdf_title = None
        for page_text in pages:
            for line in page_text.split("\n")[:10]:
                m = PE_TITLE_RE.search(line)
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


