"""
Extract structured R-2 funding data from Defense-Wide PDF pages into budget_lines.

Defense-Wide agencies publish R-2 justification books only as PDFs (no Excel).
The pipeline's builder.py parses the narrative text into pdf_pages but does not
extract the structured funding tables.  This module reads the already-extracted
page text from pdf_pages, parses the "COST ($ in Millions/Thousands)" tables,
and inserts structured rows into budget_lines.

Usage:
    python -m pipeline.r2_pdf_extractor --db dod_budget.sqlite
    python -m pipeline.r2_pdf_extractor --db dod_budget.sqlite --dry-run
    python -m pipeline.r2_pdf_extractor --db dod_budget.sqlite --limit 100
"""

from __future__ import annotations

import argparse
import logging
import re
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

from utils import get_connection
from utils.normalization import clean_r2_title
from utils.organization import infer_org
from utils.query import make_placeholders

from pipeline.r2_cost_parser import (  # noqa: F401
    SKIP_LABEL_PREFIXES,
    SKIP_LINE_LABELS,
    parse_r2_cost_table,
    parse_r2_header_metadata,
)

logger = logging.getLogger(__name__)


def _extract_fy_from_fiscal_year(fy_str: str | None) -> int | None:
    """Extract 4-digit year from fiscal_year column like 'FY 2025' or 'FY2025'."""
    if not fy_str:
        return None
    m = re.search(r"(\d{4})", fy_str)
    return int(m.group(1)) if m else None


# ── budget_lines column mapping ──────────────────────────────────────────────

def _fy_to_amount_col(fy_year: str) -> str | None:
    """Map a fiscal year label to an amount column name (e.g. 'amount_fy2025_total')."""
    try:
        year = int(fy_year)
    except (ValueError, TypeError):
        return None
    return f"amount_fy{year}_total"


def _ensure_amount_columns(conn: sqlite3.Connection, col_names: set[str]) -> None:
    """Add any missing amount columns to budget_lines."""
    existing = {r[1] for r in conn.execute("PRAGMA table_info(budget_lines)").fetchall()}
    for col in sorted(col_names):
        if col not in existing:
            conn.execute(f"ALTER TABLE budget_lines ADD COLUMN {col} REAL")
            logger.info("  Added column %s to budget_lines", col)


# ── Main extraction logic ────────────────────────────────────────────────────

def extract_r2_from_pdfs(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
    limit: int | None = None,
    service_filter: str | None = None,
) -> dict:
    """Extract R-2 funding data from PDF pages into budget_lines.

    Scans all pdf_pages (not just Defense-Wide) for R-2 COST tables and
    inserts structured funding rows into budget_lines.

    Args:
        service_filter: Optional substring to restrict source_file paths,
            e.g. ``"Army"`` or ``"Defense_Wide"``.  Useful for incremental
            testing per service.

    Returns a summary dict with counts.
    """
    t0 = time.time()

    # Find R-2 pages with COST tables
    logger.info("Scanning pdf_pages for R-2 cost tables...")
    query = """
        SELECT id, source_file, page_number, fiscal_year,
               substr(page_text, 1, 4000) as page_text
        FROM pdf_pages
        WHERE (page_text LIKE '%Total PE Cost%' OR page_text LIKE '%Total Program Element%')
          AND (page_text LIKE '%COST%Millions%' OR page_text LIKE '%Cost%millions%'
               OR page_text LIKE '%COST%Thousands%' OR page_text LIKE '%Cost%thousands%'
               OR page_text LIKE "%$'s in Millions%")
    """
    params: list = []
    if service_filter:
        query += " AND source_file LIKE ?"
        params.append(f"%{service_filter}%")
    if limit:
        query += f" LIMIT {int(limit)}"

    pages = conn.execute(query, params).fetchall()
    logger.info("  Found %d pages with R-2 cost tables", len(pages))

    if not pages:
        return {"pages_scanned": 0, "rows_inserted": 0, "pages_parsed": 0, "pages_skipped": 0}

    needed_cols: set[str] = set()
    insert_rows: list[dict] = []
    parsed = 0
    skipped = 0

    for page_id, source_file, page_num, fiscal_year, text in pages:
        result = parse_r2_cost_table(text)
        if not result:
            skipped += 1
            continue

        parsed += 1
        source_fy = _extract_fy_from_fiscal_year(fiscal_year)
        org = infer_org(source_file, page_text=text)
        pe = result["pe_number"]
        approp = result["approp_code"]
        mult = result["unit_multiplier"]

        for label, fy_pairs in result["fy_amounts"].items():
            # Clean title: strip trailing amounts, reject junk rows
            cleaned_code, cleaned_label = clean_r2_title(label)
            if cleaned_code is None and cleaned_label is None:
                continue
            label = f"{cleaned_code}: {cleaned_label}" if cleaned_code else (cleaned_label or label)

            row_data = {
                "source_file": source_file,
                "exhibit_type": "r2_pdf",
                "sheet_name": f"page_{page_num}",
                "fiscal_year": str(source_fy) if source_fy else fiscal_year,
                "pe_number": pe,
                "account": approp,
                "organization_name": org,
                "line_item_title": label,
                "budget_activity": result.get("budget_activity"),
                "budget_activity_title": result.get("budget_activity_title"),
                "appropriation_title": result.get("appropriation_title"),
                "budget_type": "RDT&E",
                "amount_unit": "thousands",
            }

            for fy_year, amount in fy_pairs:
                col = _fy_to_amount_col(fy_year)
                if col and amount is not None:
                    row_data[col] = amount * mult
                    needed_cols.add(col)

            insert_rows.append(row_data)

        if parsed % 500 == 0:
            logger.info("  Parsed %d pages, %d rows so far...", parsed, len(insert_rows))

    logger.info("Parsed %d pages -> %d rows (%d skipped)", parsed, len(insert_rows), skipped)

    if dry_run:
        logger.info("DRY RUN — not inserting. Sample rows:")
        for r in insert_rows[:5]:
            amounts = {k: v for k, v in r.items() if k.startswith("amount_fy") and v is not None}
            logger.info("  PE=%s org=%s title=%s amounts=%s",
                        r["pe_number"], r["organization_name"],
                        (r["line_item_title"] or "")[:40], amounts)
        return {
            "pages_scanned": len(pages),
            "pages_parsed": parsed,
            "pages_skipped": skipped,
            "rows_inserted": 0,
            "rows_prepared": len(insert_rows),
        }

    if needed_cols:
        _ensure_amount_columns(conn, needed_cols)

    # Group rows by column set for efficient executemany
    all_cols = {r[1] for r in conn.execute("PRAGMA table_info(budget_lines)").fetchall()}
    groups: dict[tuple[str, ...], list[list]] = defaultdict(list)
    for row_data in insert_rows:
        cols = tuple(sorted(c for c in row_data if c in all_cols))
        groups[cols].append([row_data[c] for c in cols])

    inserted = 0
    for cols, val_lists in groups.items():
        placeholders = make_placeholders(len(cols))
        col_names = ", ".join(cols)
        conn.executemany(
            f"INSERT OR IGNORE INTO budget_lines ({col_names}) VALUES ({placeholders})",
            val_lists,
        )
        inserted += len(val_lists)

    conn.commit()
    elapsed = time.time() - t0
    logger.info("Inserted %d rows in %.1fs", inserted, elapsed)

    return {
        "pages_scanned": len(pages),
        "pages_parsed": parsed,
        "pages_skipped": skipped,
        "rows_inserted": inserted,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(
        description="Extract R-2 funding data from PDF pages into budget_lines."
    )
    parser.add_argument("--db", type=Path, default=Path("dod_budget.sqlite"),
                        help="Path to SQLite database")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse but don't insert; show sample rows")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of pages to process")
    parser.add_argument("--service", type=str, default=None,
                        help="Restrict to source files matching this string "
                             "(e.g. 'Army', 'Navy', 'Defense_Wide')")
    args = parser.parse_args()

    if not args.db.exists():
        logger.error("Database not found: %s", args.db)
        sys.exit(1)

    conn = get_connection(args.db)
    result = extract_r2_from_pdfs(
        conn, dry_run=args.dry_run, limit=args.limit,
        service_filter=args.service,
    )
    conn.close()

    print("\nSummary:")
    for k, v in result.items():
        print(f"  {k}: {v:,}")


if __name__ == "__main__":
    main()
