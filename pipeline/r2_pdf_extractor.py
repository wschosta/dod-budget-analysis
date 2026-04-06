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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import get_connection

logger = logging.getLogger(__name__)

# ── PE number extraction ─────────────────────────────────────────────────────

_PE_RE = re.compile(r"PE\s+(\d{7,}[A-Z]*\d*[A-Z]*)")

# ── Appropriation code extraction ────────────────────────────────────────────
# Matches "0400:" or "0400 /" at the start of the appropriation line
_APPROP_RE = re.compile(r"(\d{4}[A-Z]?)\s*[:/]")

# ── Organization from source_file path ───────────────────────────────────────

_ORG_FROM_FILE: list[tuple[str, str]] = [
    ("RDTE_OSD", "OSD"),
    ("RDTE_DARPA", "DARPA"),
    ("RDTE_SOCOM", "SOCOM"),
    ("RDTE_MDA", "MDA"),
    ("RDTE_DTRA", "DTRA"),
    ("RDTE_DISA", "DISA"),
    ("RDTE_DLA", "DLA"),
    ("RDTE_DCSA", "DCSA"),
    ("RDTE_DCMA", "DCMA"),
    ("RDTE_DCAA", "DCAA"),
    ("RDTE_DTIC", "DTIC"),
    ("RDTE_DHRA", "DHRA"),
    ("RDTE_DSCA", "DSCA"),
    ("RDTE_CBDP", "CBDP"),
    ("RDTE_CHIPS", "OSD"),
    ("RDTE_CYBERCOM", "CYBER"),
    ("RDTE_OTE", "OSD"),
    ("RDTE_TJS", "TJS"),
    ("Missile_Defense", "MDA"),
    ("DHP", "DHP"),
    ("Joint_Staff", "TJS"),
    ("jcs", "TJS"),
    ("whs", "WHS"),
    ("volume", "OSD"),  # generic fallback for older "volumeN" files
]

# ── COST table parsing ───────────────────────────────────────────────────────

# Matches the COST header line in various formats:
# "COST ($ in Millions)", "Cost (in millions)", "$'s in Millions", etc.
_COST_HEADER_RE = re.compile(
    r"(?:COST|Cost|\$['\u2019]s)\s*\(\$?\s*(?:['\u2019]s\s*)?in\s*(Millions?|Thousands?)\)",
    re.IGNORECASE,
)

# FY column labels: "FY 2025", "FY2025", "FY 98", "FY98", or bare "1998"
_FY_4DIGIT_RE = re.compile(r"FY\s*(\d{4})")
_FY_2DIGIT_RE = re.compile(r"FY\s*(\d{2})(?!\d)")
_BARE_YEAR_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")

# Numeric amount: e.g. "19.708", "633,782", "0", ".833"
_AMOUNT_TOKEN_RE = re.compile(r"^-?[\d,]+\.?\d*$")


def _parse_amount(token: str) -> float | None:
    """Parse a single amount token, returning None for non-numeric values."""
    token = token.strip().replace(",", "")
    # Strip footnote markers like "19.708*" or "0****"
    token = token.rstrip("*#")
    if not token or token in ("-", "--", "TBD", "N/A", "Continuing", "CONTINUING"):
        return None
    try:
        return float(token)
    except ValueError:
        return None


def _infer_org(source_file: str) -> str | None:
    """Infer organization name from source_file path."""
    for fragment, org in _ORG_FROM_FILE:
        if fragment.lower() in source_file.lower():
            return org
    return None


def _extract_fy_from_fiscal_year(fy_str: str | None) -> int | None:
    """Extract 4-digit year from fiscal_year column like 'FY 2025' or 'FY2025'."""
    if not fy_str:
        return None
    m = re.search(r"(\d{4})", fy_str)
    return int(m.group(1)) if m else None


def parse_r2_cost_table(
    text: str,
) -> dict | None:
    """Parse an R-2 page's COST table, returning structured data.

    Returns a dict with:
        pe_number: str
        approp_code: str | None
        unit_multiplier: float (1000 for millions, 1 for thousands)
        fy_amounts: dict[str, list[tuple[str, float|None]]]
            Maps row label -> [(fy_year, amount), ...]
    Returns None if the page doesn't contain a parseable COST table.
    """
    # Must contain a COST header
    cost_match = _COST_HEADER_RE.search(text)
    if not cost_match:
        return None

    # Determine unit: millions → multiply by 1000 to get $K
    unit_str = cost_match.group(1).lower()
    unit_multiplier = 1000.0 if "million" in unit_str else 1.0

    # Extract PE number from header area
    pe_match = _PE_RE.search(text[:800])
    if not pe_match:
        return None
    pe_number = pe_match.group(1)

    # Extract appropriation code
    approp_match = _APPROP_RE.search(text[:500])
    approp_code = approp_match.group(1) if approp_match else None

    # Find the COST header line and extract FY columns
    lines = text.split("\n")
    cost_line_idx = None
    for i, line in enumerate(lines):
        if cost_match.group(0) in line:
            cost_line_idx = i
            break

    if cost_line_idx is None:
        return None

    # FY columns may be on the same line as COST or adjacent lines
    fy_header_area = lines[max(0, cost_line_idx - 1)] + " " + lines[cost_line_idx]
    if cost_line_idx + 1 < len(lines):
        fy_header_area += " " + lines[cost_line_idx + 1]

    # Try 4-digit FY first, then 2-digit, then bare years
    fy_labels = _FY_4DIGIT_RE.findall(fy_header_area)
    if not fy_labels:
        # 2-digit: FY 98 → 1998/2098 (heuristic: <50 → 20xx, >=50 → 19xx)
        short = _FY_2DIGIT_RE.findall(fy_header_area)
        if short:
            fy_labels = [f"{'20' if int(y) < 50 else '19'}{y}" for y in short]
    if not fy_labels:
        # Bare 4-digit years (1998, 1999, ...) — filter to plausible FY range
        bare = _BARE_YEAR_RE.findall(fy_header_area)
        fy_labels = [y for y in bare if 1990 <= int(y) <= 2035]
    if not fy_labels:
        return None

    # Parse data rows after the COST header
    fy_amounts: dict[str, list[tuple[str, float | None]]] = {}
    data_start = cost_line_idx + 1
    # Skip continuation lines from the header (e.g., "Complete", "Years FY...")
    while data_start < len(lines):
        stripped = lines[data_start].strip()
        if not stripped:
            data_start += 1
            continue
        # Skip header continuation lines that contain FY labels or "Complete"
        if stripped in ("Complete", "Complete Cost") or stripped.startswith("Years "):
            data_start += 1
            continue
        break

    for i in range(data_start, min(data_start + 20, len(lines))):
        line = lines[i].strip()
        if not line:
            continue
        # Stop at section headers
        if line.startswith(("A.", "B.", "C.", "D.", "E.", "Note", "R-1 Line")):
            break

        # Try to split line into label + amounts
        # The amounts are at the end, space-separated
        tokens = line.split()
        if len(tokens) < 2:
            continue

        # Find where the numbers start by scanning from the right
        amounts: list[float | None] = []
        label_end = len(tokens)
        for j in range(len(tokens) - 1, -1, -1):
            parsed = _parse_amount(tokens[j])
            if parsed is not None or tokens[j] in ("-", "--", "TBD", "N/A", "Continuing", "CONTINUING"):
                amounts.insert(0, parsed)
                label_end = j
            else:
                break

        if not amounts:
            continue

        label = " ".join(tokens[:label_end]).strip()
        if not label:
            continue

        # Pair amounts with FY labels (amounts may be fewer than FY labels)
        paired = list(zip(fy_labels, amounts))
        if paired:
            fy_amounts[label] = paired

    if not fy_amounts:
        return None

    return {
        "pe_number": pe_number,
        "approp_code": approp_code,
        "unit_multiplier": unit_multiplier,
        "fy_amounts": fy_amounts,
    }


# ── budget_lines column mapping ──────────────────────────────────────────────

def _fy_to_amount_col(fy_year: str, source_fy: int | None) -> str | None:
    """Map a fiscal year label to the appropriate amount column name.

    The column naming depends on the relationship between the FY in the data
    and the source document's fiscal year.  For simplicity, we use _total
    as the suffix for all extracted amounts.
    """
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
) -> dict:
    """Extract R-2 funding data from Defense-Wide PDF pages into budget_lines.

    Returns a summary dict with counts.
    """
    t0 = time.time()

    # Find R-2 pages with COST tables
    logger.info("Scanning pdf_pages for R-2 cost tables...")
    query = """
        SELECT id, source_file, page_number, fiscal_year,
               substr(page_text, 1, 4000) as page_text
        FROM pdf_pages
        WHERE source_file LIKE '%Defense_Wide%'
          AND (page_text LIKE '%Total PE Cost%' OR page_text LIKE '%Total Program Element%')
          AND (page_text LIKE '%COST%Millions%' OR page_text LIKE '%Cost%millions%'
               OR page_text LIKE '%COST%Thousands%' OR page_text LIKE '%Cost%thousands%'
               OR page_text LIKE "%$'s in Millions%")
    """
    if limit:
        query += f" LIMIT {limit}"

    pages = conn.execute(query).fetchall()
    logger.info("  Found %d pages with R-2 cost tables", len(pages))

    if not pages:
        return {"pages_scanned": 0, "rows_inserted": 0, "pages_parsed": 0, "pages_skipped": 0}

    # Track which source_file+page combos already have budget_lines rows
    existing = set()
    try:
        rows = conn.execute(
            "SELECT DISTINCT source_file FROM budget_lines WHERE exhibit_type = 'r2_pdf'"
        ).fetchall()
        existing = {r[0] for r in rows}
    except sqlite3.OperationalError:
        pass

    # Collect all needed amount columns
    needed_cols: set[str] = set()
    insert_rows: list[dict] = []
    parsed = 0
    skipped = 0

    for page_id, source_file, page_num, fiscal_year, text in pages:
        if source_file in existing:
            skipped += 1
            continue

        result = parse_r2_cost_table(text)
        if not result:
            skipped += 1
            continue

        parsed += 1
        source_fy = _extract_fy_from_fiscal_year(fiscal_year)
        org = _infer_org(source_file)
        pe = result["pe_number"]
        approp = result["approp_code"]
        mult = result["unit_multiplier"]

        for label, fy_pairs in result["fy_amounts"].items():
            row_data = {
                "source_file": source_file,
                "exhibit_type": "r2_pdf",
                "sheet_name": f"page_{page_num}",
                "fiscal_year": str(source_fy) if source_fy else fiscal_year,
                "pe_number": pe,
                "account": approp,
                "organization_name": org,
                "line_item_title": label,
                "budget_type": "RDT&E",
                "amount_unit": "thousands",
            }

            for fy_year, amount in fy_pairs:
                col = _fy_to_amount_col(fy_year, source_fy)
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

    # Ensure all needed columns exist
    if needed_cols:
        _ensure_amount_columns(conn, needed_cols)

    # Get the full column list for budget_lines
    all_cols = [r[1] for r in conn.execute("PRAGMA table_info(budget_lines)").fetchall()]

    # Insert rows
    inserted = 0
    for row_data in insert_rows:
        cols = [c for c in all_cols if c in row_data]
        vals = [row_data[c] for c in cols]
        placeholders = ", ".join("?" for _ in cols)
        col_names = ", ".join(cols)
        conn.execute(f"INSERT OR IGNORE INTO budget_lines ({col_names}) VALUES ({placeholders})", vals)
        inserted += 1

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
        description="Extract R-2 funding data from Defense-Wide PDF pages into budget_lines."
    )
    parser.add_argument("--db", type=Path, default=Path("dod_budget.sqlite"),
                        help="Path to SQLite database")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse but don't insert; show sample rows")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of pages to process")
    args = parser.parse_args()

    if not args.db.exists():
        logger.error("Database not found: %s", args.db)
        sys.exit(1)

    conn = get_connection(args.db)
    result = extract_r2_from_pdfs(conn, dry_run=args.dry_run, limit=args.limit)
    conn.close()

    print(f"\nSummary:")
    for k, v in result.items():
        print(f"  {k}: {v:,}")


if __name__ == "__main__":
    main()
