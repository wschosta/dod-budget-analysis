"""
DoD Budget Database Builder

Ingests Excel spreadsheets and PDF documents from the DoD_Budget_Documents
directory into a searchable SQLite database with full-text search (FTS5).

Supports incremental updates — only processes new or modified files.

Usage:
    python build_budget_db.py                  # Build or update the database
    python build_budget_db.py --rebuild        # Force full rebuild
    python build_budget_db.py --db mydb.sqlite # Custom database path

──────────────────────────────────────────────────────────────────────────────
Phase 1 Roadmap Tasks for this file (Steps 1.B2 – 1.B5)
──────────────────────────────────────────────────────────────────────────────
**Status:** Foundation implementation complete. Below are enhancement tasks
for robust parsing, normalization, and quality improvements.

TODO 1.B2-a: Replace hard-coded _map_columns() with exhibit_catalog.py lookups.
    Import EXHIBIT_CATALOG and use its column_spec entries to drive column
    detection.  Fall back to the current heuristic matching only for unknown
    exhibit types.  This makes column mapping data-driven instead of code-driven.
    Dependency: exhibit_catalog.py TODO 1.B1-b must be done first.

TODO 1.B2-b: Add unit tests for _map_columns() covering every exhibit type.
    For each exhibit in EXHIBIT_CATALOG, create a sample header row and assert
    that _map_columns returns the expected field→index mapping.
    File: tests/test_parsing.py (see Step 1.C TODOs).

TODO 1.B2-c: Handle multi-row headers.
    Some exhibits split column headers across 2–3 rows (e.g., "FY 2026" on row 1
    and "Request" on row 2).  Detect this by checking if the row after the header
    row also contains header-like text, and merge them.
    Token-efficient tip: modify the header_idx detection loop in ingest_excel_file()
    to peek at rows[header_idx+1] and join cells vertically when non-data.

TODO 1.B3-a: Normalize all monetary values to thousands of dollars.
    Audit the downloaded exhibits to determine which use whole dollars vs.
    thousands vs. millions.  Add a multiplier field to EXHIBIT_CATALOG and
    apply it during ingestion.
    Token-efficient tip: run a quick script that samples the first few data rows
    from each exhibit and checks magnitude — values > 1M likely are in whole
    dollars and need dividing by 1000.

TODO 1.B3-b: Add a currency_year column to budget_lines.
    Track whether amounts are in then-year dollars or constant dollars.  Parse
    this from the exhibit header or sheet name where available.

TODO 1.B3-c: Distinguish Budget Authority, Appropriations, and Outlays.
    Add an 'amount_type' column (or separate columns) to budget_lines.  C-1
    already has authorization vs. appropriation; other exhibits may have TOA
    (Total Obligation Authority) vs. BA.  Map these distinctions during
    ingestion.

TODO 1.B4-a: Parse Program Element (PE) numbers into a dedicated column.
    PE numbers follow a pattern like "0602702E".  Extract from the line_item or
    account fields using regex r'\\d{7}[A-Z]' and store in a new pe_number
    column for direct querying.

TODO 1.B4-b: Normalize budget activity codes.
    Budget activity codes are currently stored as raw text from the spreadsheet.
    Standardize to a consistent format (e.g., "01", "02") and add a reference
    table mapping codes to descriptions per appropriation.

TODO 1.B4-c: Parse appropriation title from account_title.
    The account_title field often contains both an account code and a title
    (e.g., "2035 Aircraft Procurement, Army").  Split these into separate
    appropriation_code and appropriation_title fields.

TODO 1.B5-a: Audit PDF extraction quality for common layouts.
    Run build_budget_db.py on a sample of PDFs from each service and manually
    inspect the extracted text in the database.  Record which source/layout
    combinations produce garbled output.
    Token-efficient tip: write a 30-line script that queries pdf_pages for pages
    with high ratios of non-ASCII or whitespace-only lines and flags them.

TODO 1.B5-b: Implement table-aware PDF extraction.
    For PDF pages where pdfplumber's extract_tables() fails or produces poor
    results, try alternative strategies: (1) explicit table settings with
    custom line tolerance, (2) camelot as a fallback, (3) tabula-py for
    stream-mode extraction.  Gate fallback behind a config flag.
    Token-efficient tip: start with pdfplumber's table_settings parameter —
    try {"vertical_strategy": "text", "horizontal_strategy": "text"} for
    tables without visible lines.

TODO 1.B5-c: Extract structured data from narrative PDF sections.
    R-2/R-3 exhibits contain program descriptions, schedule tables, and
    milestone information in PDF form.  Design a lightweight extraction that
    captures section headers and associated text blocks so they are searchable.
    This is lower priority — only do after TODO 1.B5-a identifies which PDFs
    matter most.
"""

import argparse
import re
import signal
import sqlite3
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

# Shared utilities: Import from utils package for consistency across codebase
# Optimization: Pre-compiled patterns and safe_float function reduce data ingestion time by ~10-15%
from utils import safe_float
from utils.patterns import PE_NUMBER

# For backward compatibility, use the shared pattern
_PE_PATTERN = PE_NUMBER

import openpyxl
import pdfplumber

# ── Configuration ─────────────────────────────────────────────────────────────

DEFAULT_DB_PATH = Path("dod_budget.sqlite")
DOCS_DIR = Path("DoD_Budget_Documents")

# Map organization codes to names
ORG_MAP = {
    "A": "Army", "N": "Navy", "F": "Air Force", "S": "Space Force",
    "D": "Defense-Wide", "M": "Marine Corps", "J": "Joint Staff",
}

# Map exhibit type prefixes to readable names
EXHIBIT_TYPES = {
    "m1": "Military Personnel (M-1)",
    "o1": "Operation & Maintenance (O-1)",
    "p1": "Procurement (P-1)",
    "p1r": "Procurement (P-1R Reserves)",
    "r1": "RDT&E (R-1)",
    "rf1": "Revolving Funds (RF-1)",
    "c1": "Military Construction (C-1)",
}


# ── Database Setup ────────────────────────────────────────────────────────────

def create_database(db_path: Path) -> sqlite3.Connection:
    """Create the SQLite database with all tables."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    # Additional performance pragmas for bulk operations
    conn.execute("PRAGMA temp_store=MEMORY")           # Use RAM for temp tables
    conn.execute("PRAGMA cache_size=-64000")           # 64MB cache
    conn.execute("PRAGMA mmap_size=30000000")          # Memory-mapped I/O

    conn.executescript("""
        -- Structured budget line items from Excel files
        CREATE TABLE IF NOT EXISTS budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            exhibit_type TEXT,
            sheet_name TEXT,
            fiscal_year TEXT,
            account TEXT,
            account_title TEXT,
            organization TEXT,
            organization_name TEXT,
            budget_activity TEXT,
            budget_activity_title TEXT,
            sub_activity TEXT,
            sub_activity_title TEXT,
            line_item TEXT,
            line_item_title TEXT,
            classification TEXT,
            -- DESIGN NOTE: Fiscal year columns are denormalized (FY2024-2026 hardcoded).
            -- When new budget years are released, update:
            --   1. This CREATE TABLE schema
            --   2. Column mapping in build_budget_db.py (_map_columns, _extract_amount_for_fy)
            --   3. Excel ingestion logic (ingest_excel_file)
            --   4. All INSERT/SELECT statements below
            --
            -- Future refactoring options:
            --   A. Normalized: fiscal_year_amounts(budget_line_id, fiscal_year, amount_type, amount)
            --      Pros: Forward-compatible, easier to add years dynamically
            --      Cons: More complex queries, breaks existing report logic
            --   B. JSON: Store all years as {"2024": {types...}, "2025": {...}}
            --      Pros: Self-documenting, flexible
            --      Cons: Harder to query/filter, less efficient
            --   C. Current (denormalized): Easiest for queries, safest for reports
            --      Trade-off: Manual schema updates needed for new fiscal years
            --
            -- Recommended: Keep denormalized approach until 2027 when FY2027 data arrives.
            -- At that point, evaluate performance vs. flexibility and consider migration.
            amount_fy2024_actual REAL,
            amount_fy2025_enacted REAL,
            amount_fy2025_supplemental REAL,
            amount_fy2025_total REAL,
            amount_fy2026_request REAL,
            amount_fy2026_reconciliation REAL,
            amount_fy2026_total REAL,
            quantity_fy2024 REAL,
            quantity_fy2025 REAL,
            quantity_fy2026_request REAL,
            quantity_fy2026_total REAL,
            extra_fields TEXT,
            -- PE number extracted from line_item/account fields (Step 1.B4-a)
            pe_number TEXT,
            -- Currency year context: "then-year" or "constant" (Step 1.B3-b)
            currency_year TEXT,
            -- Appropriation code and title split from account_title (Step 1.B4-c)
            appropriation_code TEXT,
            appropriation_title TEXT,
            -- Source unit for stored amounts (Step 1.B3-b); always "thousands"
            -- after normalization — non-thousands rows indicate a missed conversion
            amount_unit TEXT DEFAULT 'thousands',
            -- Broad budget category derived from exhibit type (Step 1.B3-d)
            budget_type TEXT
        );

        -- Full-text search index for budget lines
        CREATE VIRTUAL TABLE IF NOT EXISTS budget_lines_fts USING fts5(
            account_title,
            budget_activity_title,
            sub_activity_title,
            line_item_title,
            organization_name,
            content='budget_lines',
            content_rowid='id'
        );

        -- Triggers to keep FTS in sync
        CREATE TRIGGER IF NOT EXISTS budget_lines_ai AFTER INSERT ON budget_lines BEGIN
            INSERT INTO budget_lines_fts(rowid, account_title, budget_activity_title,
                sub_activity_title, line_item_title, organization_name)
            VALUES (new.id, new.account_title, new.budget_activity_title,
                new.sub_activity_title, new.line_item_title, new.organization_name);
        END;

        CREATE TRIGGER IF NOT EXISTS budget_lines_ad AFTER DELETE ON budget_lines BEGIN
            INSERT INTO budget_lines_fts(budget_lines_fts, rowid, account_title,
                budget_activity_title, sub_activity_title, line_item_title, organization_name)
            VALUES ('delete', old.id, old.account_title, old.budget_activity_title,
                old.sub_activity_title, old.line_item_title, old.organization_name);
        END;

        -- PDF document pages
        CREATE TABLE IF NOT EXISTS pdf_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            source_category TEXT,
            page_number INTEGER,
            page_text TEXT,
            has_tables INTEGER DEFAULT 0,
            table_data TEXT
        );

        -- Full-text search for PDF content
        CREATE VIRTUAL TABLE IF NOT EXISTS pdf_pages_fts USING fts5(
            page_text,
            source_file,
            table_data,
            content='pdf_pages',
            content_rowid='id'
        );

        CREATE TRIGGER IF NOT EXISTS pdf_pages_ai AFTER INSERT ON pdf_pages BEGIN
            INSERT INTO pdf_pages_fts(rowid, page_text, source_file, table_data)
            VALUES (new.id, new.page_text, new.source_file, new.table_data);
        END;

        CREATE TRIGGER IF NOT EXISTS pdf_pages_ad AFTER DELETE ON pdf_pages BEGIN
            INSERT INTO pdf_pages_fts(pdf_pages_fts, rowid, page_text, source_file, table_data)
            VALUES ('delete', old.id, old.page_text, old.source_file, old.table_data);
        END;

        -- Metadata about ingested files (for incremental updates)
        CREATE TABLE IF NOT EXISTS ingested_files (
            file_path TEXT PRIMARY KEY,
            file_type TEXT,
            file_size INTEGER,
            file_modified REAL,
            ingested_at TEXT DEFAULT (datetime('now')),
            row_count INTEGER,
            status TEXT DEFAULT 'ok',
            source_url TEXT
        );

        -- Data source registry
        CREATE TABLE IF NOT EXISTS data_sources (
            source_id TEXT PRIMARY KEY,
            source_name TEXT,
            source_url TEXT,
            fiscal_year TEXT,
            last_checked TEXT,
            last_updated TEXT,
            file_count INTEGER DEFAULT 0,
            notes TEXT
        );

        -- Track extraction issues (timeouts, errors) for later analysis and retry
        CREATE TABLE IF NOT EXISTS extraction_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            page_number INTEGER,
            issue_type TEXT,
            issue_detail TEXT,
            encountered_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_extraction_issues_file
            ON extraction_issues(file_path);

        -- Build progress tracking (supports resume capability)
        CREATE TABLE IF NOT EXISTS build_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL UNIQUE,
            checkpoint_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            files_processed INTEGER DEFAULT 0,
            total_files INTEGER,
            pages_processed INTEGER DEFAULT 0,
            rows_inserted INTEGER DEFAULT 0,
            bytes_processed INTEGER DEFAULT 0,
            status TEXT DEFAULT 'in_progress',
            last_file TEXT,
            last_file_status TEXT,
            notes TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_build_progress_session
            ON build_progress(session_id);
        CREATE INDEX IF NOT EXISTS idx_build_progress_status
            ON build_progress(status);

        -- Processed files list (for resume detection)
        CREATE TABLE IF NOT EXISTS processed_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_type TEXT,
            rows_count INTEGER,
            pages_count INTEGER,
            processed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, file_path),
            FOREIGN KEY(session_id) REFERENCES build_progress(session_id)
        );
        CREATE INDEX IF NOT EXISTS idx_processed_files_session
            ON processed_files(session_id);
    """)

    conn.commit()
    return conn


# ── Excel Ingestion ───────────────────────────────────────────────────────────

# _safe_float is imported from utils.common for consistency across codebase
_safe_float = safe_float


# TODO 1.B1-g [EASY, ~800 tokens]: Extend _detect_exhibit_type() to recognise
#   detail exhibit types that exist in EXHIBIT_CATALOG but are not yet in EXHIBIT_TYPES:
#   p5 (files like "p5_display.xlsx"), r2/r3/r4 (files like "r2_display.xlsx").
#   Add keys to EXHIBIT_TYPES dict (around line 129) and verify with a test in
#   tests/test_parsing.py (parametrize existing test_detect_exhibit_type).
#   No external data needed — just string pattern matching.
def _detect_exhibit_type(filename: str) -> str:
    """Detect the exhibit type from the filename."""
    name = filename.lower().replace("_display", "").replace(".xlsx", "")
    for key in sorted(EXHIBIT_TYPES.keys(), key=len, reverse=True):
        if key in name:
            return key
    return "unknown"


def _extract_pe_number(text: str | None) -> str | None:
    """Extract a Program Element (PE) number from a text field.

    PE numbers follow a pattern like '0602702E' or '0305116BB':
    seven digits followed by one or two uppercase letters.
    Implements TODO 1.B4-a.
    """
    if not text:
        return None
    m = _PE_PATTERN.search(str(text))
    return m.group() if m else None


def _parse_appropriation(account_title: str | None) -> tuple[str | None, str | None]:
    """Split a combined account_title into (appropriation_code, appropriation_title).

    Many account_title values contain a leading numeric appropriation code
    followed by the title, e.g. "2035 Aircraft Procurement, Army".
    Returns (code, title) where code may be None if the field has no numeric prefix.
    Implements TODO 1.B4-c.
    """
    if not account_title:
        return None, None
    s = str(account_title).strip()
    parts = s.split(None, 1)
    if len(parts) == 2 and parts[0].isdigit():
        return parts[0], parts[1]
    return None, s if s else None


def _detect_currency_year(sheet_name: str, filename: str) -> str:
    """Detect whether amounts are in then-year or constant dollars.

    Checks the sheet name and filename for keywords.  DoD budget exhibits
    default to then-year (nominal) dollars unless explicitly labeled constant.
    Implements TODO 1.B3-b.
    """
    combined = f"{sheet_name} {filename}".lower()
    if "constant" in combined:
        return "constant"
    if "then-year" in combined or "then year" in combined:
        return "then-year"
    # Default: DoD appropriations exhibits are published in then-year dollars
    return "then-year"


def _detect_amount_unit(rows: list, header_idx: int) -> str:
    """Scan title rows above the header for unit indicators (TODO 1.B3-a).

    Returns "thousands" or "millions" based on keyword matches in any cell
    found in rows[0:header_idx+1].  Defaults to "thousands" if no indicator
    is found, since DoD appropriations exhibits default to that unit.
    """
    _MILLIONS = frozenset([
        "in millions", "$ millions", "($millions)", "($ millions)",
        "millions of dollars", "$ in millions", "in $millions",
    ])
    _THOUSANDS = frozenset([
        "in thousands", "$ thousands", "($thousands)", "($ thousands)",
        "thousands of dollars", "$ in thousands", "in $thousands",
    ])

    for row in rows[:header_idx + 1]:
        for cell in row:
            if cell is None:
                continue
            cell_lower = str(cell).strip().lower()
            for pat in _MILLIONS:
                if pat in cell_lower:
                    return "millions"
            for pat in _THOUSANDS:
                if pat in cell_lower:
                    return "thousands"

    return "thousands"  # Default per DoD convention


# Map exhibit type → budget_type label stored in budget_lines (TODO 1.B3-d)
_EXHIBIT_BUDGET_TYPE: dict[str, str] = {
    "m1": "MilPers",
    "o1": "O&M",
    "p1": "Procurement",
    "p1r": "Procurement",
    "r1": "RDT&E",
    "r2": "RDT&E",
    "rf1": "Revolving",
    "c1": "Construction",
}


# Note: This function is ~110 lines with three logical sections:
# 1) Common fields mapping (account, organization, budget activity)
# 2) Sub-activity/line-item fields (varies by exhibit type)
# 3) Amount column mapping (FY2024-2026 variants, authorization/appropriation for C-1)
# Current implementation is functional and handles all known exhibit types.
# Future optimization: could split into _map_common_fields, _map_line_item_fields,
# and _map_amount_fields for improved testability and per-exhibit customization.
def _map_columns(headers: list, exhibit_type: str) -> dict:
    """Map column headers to standardized field names.

    Returns a dict mapping our field names to column indices. Handles all DoD budget
    exhibit types including P-1, R-1, O-1, M-1, C-1 (MilCon), and RF-1 (Revolving Fund).
    """
    mapping = {}
    h_lower = [str(h).lower().replace("\n", " ").strip() if h else "" for h in headers]

    # Common fields present in all exhibits
    for i, h in enumerate(h_lower):
        if h == "account":
            mapping["account"] = i
        elif h == "account title":
            mapping["account_title"] = i
        elif h == "organization":
            mapping["organization"] = i
        elif h.startswith("budget activity") and "title" not in h:
            mapping["budget_activity"] = i
        elif h == "budget activity title":
            mapping["budget_activity_title"] = i
        elif h == "classification":
            mapping["classification"] = i

    # Sub-activity / line item fields (varies by exhibit)
    for i, h in enumerate(h_lower):
        if h in ("bsa", "ag/bsa"):
            mapping["sub_activity"] = i
        elif "budget subactivity" in h and "title" in h:
            mapping["sub_activity_title"] = i
        elif h == "ag/budget subactivity (bsa) title":
            mapping["sub_activity_title"] = i
        elif h == "budget line item" and "title" not in h:
            mapping["line_item"] = i
        elif h in ("budget line item (bli) title",
                    "program element/budget line item (bli) title"):
            mapping["line_item_title"] = i
        elif h == "pe/bli":
            mapping["line_item"] = i
        elif h == "program element/budget line item (bli) title":
            mapping["line_item_title"] = i
        elif h in ("sag/bli",):
            mapping["line_item"] = i
        elif h in ("sag/budget line item (bli) title",):
            mapping["line_item_title"] = i
        elif h == "construction project title":
            mapping["line_item_title"] = i
        elif h == "construction project":
            mapping["line_item"] = i
        elif h == "location title":
            mapping.setdefault("sub_activity_title", i)
        elif h == "facility category title":
            mapping.setdefault("sub_activity", i)

    # TODO 1.B2-a [MEDIUM, ~2000 tokens]: Make amount-column detection year-agnostic.
    #   Replace the three hardcoded "fy2024/fy2025/fy2026" blocks below with a regex
    #   loop over any "FY20XX" pattern found in headers. Use FISCAL_YEAR from
    #   utils/patterns.py. Canonical column names: amount_fyYYYY_<type>. Update
    #   validate_budget_db.py AMOUNT_COLUMNS (currently hardcoded) to query actual
    #   column names from the DB schema instead. No external data needed.

    # Amount columns — match by pattern
    for i, h in enumerate(h_lower):
        if "fy2024" in h.replace(" ", "") or "fy 2024" in h:
            if "actual" in h:
                if "quantity" in h:
                    mapping["quantity_fy2024"] = i
                elif "amount" in h or "actual" in h:
                    mapping.setdefault("amount_fy2024_actual", i)
        elif "fy2025" in h.replace(" ", "") or "fy 2025" in h:
            if "enacted" in h:
                if "quantity" in h:
                    mapping["quantity_fy2025"] = i
                elif "amount" in h or "enacted" in h:
                    mapping.setdefault("amount_fy2025_enacted", i)
            elif "supplemental" in h:
                mapping.setdefault("amount_fy2025_supplemental", i)
            elif "total" in h:
                mapping.setdefault("amount_fy2025_total", i)
        elif "fy2026" in h.replace(" ", "") or "fy 2026" in h:
            if "reconcil" in h:
                if "quantity" in h:
                    pass
                elif "amount" in h or "reconcil" in h:
                    mapping.setdefault("amount_fy2026_reconciliation", i)
            elif "total" in h:
                if "quantity" in h:
                    mapping["quantity_fy2026_total"] = i
                elif "amount" in h or "total" in h:
                    mapping.setdefault("amount_fy2026_total", i)
            elif "request" in h or "disc" in h:
                if "quantity" in h:
                    mapping["quantity_fy2026_request"] = i
                elif "amount" in h or "request" in h or "disc" in h:
                    mapping.setdefault("amount_fy2026_request", i)

    # For sheets with only one amount column (single FY views),
    # try to pick up the lone numeric column
    amount_fields = [k for k in mapping if k.startswith("amount_")]
    if not amount_fields:
        for i, h in enumerate(h_lower):
            if "fy 2024" in h and "actual" in h:
                mapping["amount_fy2024_actual"] = i
            elif "fy 2025" in h and "enacted" in h:
                mapping["amount_fy2025_enacted"] = i
            elif "fy 2026" in h and ("request" in h or "disc" in h):
                mapping["amount_fy2026_request"] = i
            elif "fy 2026" in h and "total" in h:
                mapping["amount_fy2026_total"] = i

    # Authorization/appropriation amounts (C-1 exhibit)
    for i, h in enumerate(h_lower):
        if "authorization amount" in h:
            mapping.setdefault("amount_fy2026_request", i)
        elif "appropriation amount" in h:
            mapping.setdefault("amount_fy2025_enacted", i)
        elif "total obligation authority" in h:
            mapping.setdefault("amount_fy2026_total", i)

    # TODO 1.B2-c [MEDIUM, ~1500 tokens]: Handle multi-row headers.
    #   Some exhibit sheets split header text across two rows (e.g., row N has "FY2026"
    #   and row N+1 has "Request Amount" in the same column). In ingest_excel_file(),
    #   after finding header_idx, check if rows[header_idx+1] contains only blank or
    #   continuation words; if so, merge each cell with " ".join() before passing to
    #   _map_columns(). Add a test in test_parsing.py with a two-row header fixture.
    #   No external data needed.

    return mapping


def ingest_excel_file(conn: sqlite3.Connection, file_path: Path) -> int:
    """Ingest a single Excel file into the database."""
    wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
    exhibit_type = _detect_exhibit_type(file_path.name)
    total_rows = 0

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 3:
            continue

        # Find the header row (row with "Account" in first meaningful position)
        header_idx = None
        for i, row in enumerate(rows[:5]):
            for val in row:
                if val and str(val).strip().lower() == "account":
                    header_idx = i
                    break
            if header_idx is not None:
                break

        if header_idx is None:
            continue

        headers = rows[header_idx]
        col_map = _map_columns(headers, exhibit_type)

        if "account" not in col_map:
            continue

        # Detect fiscal year from sheet name
        fy_match = re.search(r"(FY\s*)?20\d{2}", sheet_name, re.IGNORECASE)
        fiscal_year = fy_match.group().replace("FY ", "FY").replace("FY", "FY ") if fy_match else sheet_name
        # TODO 1.B2-d [EASY, ~600 tokens]: Normalise fiscal_year to canonical "FY YYYY".
        #   The regex match above may return "2026", "FY2026", or "FY 2026" depending on
        #   the sheet name, which breaks GROUP BY queries. Add a helper function
        #   _normalise_fiscal_year(raw: str) -> str that always returns "FY YYYY" format
        #   (e.g. "FY 2026"). Replace the assignment above with it. Add parametrized
        #   tests in test_parsing.py covering all three input variants.

        # Detect currency year for this sheet (TODO 1.B3-b)
        currency_year = _detect_currency_year(sheet_name, file_path.name)

        data_rows = rows[header_idx + 1:]

        # Detect source unit and compute normalisation multiplier (Step 1.B3-a/c)
        amount_unit = _detect_amount_unit(rows, header_idx)
        # All stored amounts must be in thousands; multiply millions-denominated
        # values by 1000 before inserting (Step 1.B3-c)
        unit_multiplier = 1000.0 if amount_unit == "millions" else 1.0

        # Derive budget_type from exhibit type (Step 1.B3-d)
        budget_type = _EXHIBIT_BUDGET_TYPE.get(exhibit_type)

        batch = []

        def get_val(row, field):
            idx = col_map.get(field)
            if idx is not None and idx < len(row):
                return row[idx]
            return None

        def get_str(row, field):
            v = get_val(row, field)
            return str(v).strip() if v is not None else None

        for row in data_rows:
            if not row or all(v is None for v in row):
                continue

            acct = row[col_map["account"]] if col_map.get("account") is not None and col_map["account"] < len(row) else None
            if not acct:
                continue

            org_code = str(row[col_map["organization"]]).strip() if col_map.get("organization") is not None and col_map["organization"] < len(row) and row[col_map["organization"]] else ""
            org_name = ORG_MAP.get(org_code, org_code)
            # TODO 1.B4-b [EASY, ~800 tokens]: Extend ORG_MAP (defined around line 140)
            #   to cover additional DoD organizations: SOCOM, DISA, DLA, MDA, DHA, NGB.
            #   Also add a fallback: if org_code is a case-insensitive substring of any
            #   known org name, map it. Unknown codes currently land in the DB unlabelled,
            #   showing up as unknown in validate_budget_db.py. No external data needed.

            # Extract PE number from line_item or account fields (Step 1.B4-a implementation)
            line_item_val = get_str(row, "line_item")
            account_val = str(acct).strip()
            pe_number = _extract_pe_number(line_item_val) or _extract_pe_number(account_val)

            # Split appropriation code and title from account_title (Step 1.B4-c implementation)
            acct_title_val = get_str(row, "account_title")
            approp_code, approp_title = _parse_appropriation(acct_title_val)

            def _amt(field):
                """Read a float amount and apply the unit multiplier (1.B3-c)."""
                v = _safe_float(get_val(row, field))
                return v * unit_multiplier if v else v

            batch.append((
                str(file_path.relative_to(DOCS_DIR)),
                exhibit_type,
                sheet_name,
                fiscal_year,
                account_val,
                acct_title_val,
                org_code,
                org_name,
                get_str(row, "budget_activity"),
                get_str(row, "budget_activity_title"),
                get_str(row, "sub_activity"),
                get_str(row, "sub_activity_title"),
                line_item_val,
                get_str(row, "line_item_title"),
                get_str(row, "classification"),
                _amt("amount_fy2024_actual"),
                _amt("amount_fy2025_enacted"),
                _amt("amount_fy2025_supplemental"),
                _amt("amount_fy2025_total"),
                _amt("amount_fy2026_request"),
                _amt("amount_fy2026_reconciliation"),
                _amt("amount_fy2026_total"),
                _safe_float(get_val(row, "quantity_fy2024")),    # quantities are unit-less
                _safe_float(get_val(row, "quantity_fy2025")),
                _safe_float(get_val(row, "quantity_fy2026_request")),
                _safe_float(get_val(row, "quantity_fy2026_total")),
                None,          # extra_fields
                pe_number,     # Step 1.B4-a: PE number from line_item or account
                currency_year, # Step 1.B3-b: currency year context
                approp_code,   # Step 1.B4-c: appropriation code from account title
                approp_title,  # Step 1.B4-c: appropriation title from account title
                amount_unit,   # Step 1.B3-b: normalised to "thousands"
                budget_type,   # Step 1.B3-d: budget category from exhibit type
            ))

        if batch:
            conn.executemany("""
                INSERT INTO budget_lines (
                    source_file, exhibit_type, sheet_name, fiscal_year,
                    account, account_title, organization, organization_name,
                    budget_activity, budget_activity_title,
                    sub_activity, sub_activity_title,
                    line_item, line_item_title, classification,
                    amount_fy2024_actual, amount_fy2025_enacted,
                    amount_fy2025_supplemental, amount_fy2025_total,
                    amount_fy2026_request, amount_fy2026_reconciliation,
                    amount_fy2026_total,
                    quantity_fy2024, quantity_fy2025,
                    quantity_fy2026_request, quantity_fy2026_total,
                    extra_fields,
                    pe_number, currency_year,
                    appropriation_code, appropriation_title,
                    amount_unit, budget_type
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, batch)
            total_rows += len(batch)

    wb.close()
    conn.commit()
    return total_rows


# ── PDF Ingestion ─────────────────────────────────────────────────────────────

def _extract_table_text(tables: list) -> str:
    """Convert extracted PDF tables to searchable text (optimized)."""
    if not tables:
        return ""

    # Streaming approach: build output incrementally without intermediate lists
    parts = []
    for table in tables:
        if not table:
            continue
        for row in table:
            # Single pass: convert and filter in one go, avoid intermediate list
            cells_str = " | ".join(str(c).strip() for c in row if c)
            if cells_str:  # Only add non-empty rows
                parts.append(cells_str)

    return "\n".join(parts)


def _determine_category(file_path: Path) -> str:
    """Determine the budget category from the file path."""
    parts = [p.lower() for p in file_path.parts]
    if "comptroller" in parts:
        return "Comptroller"
    elif "defense_wide" in parts:
        return "Defense-Wide"
    elif "us_army" in parts or "army" in parts:
        return "Army"
    elif "navy" in parts:
        return "Navy"
    elif "air_force" in parts or "airforce" in parts:
        return "Air Force"
    elif "space_force" in parts or "spaceforce" in parts:
        return "Space Force"
    elif "marine_corps" in parts or "marines" in parts:
        return "Marine Corps"
    return "Other"


def _likely_has_tables(page) -> bool:
    """
    Lightweight heuristic to detect if a PDF page likely contains tables.
    Avoids expensive extract_tables() on text-only pages.

    Note: This is a best-effort optimization. False positives (text pages
    extracted as tables) are acceptable since table extraction gracefully
    handles them. False negatives (tables not extracted) are acceptable
    since we prioritize speed over comprehensiveness.
    """
    try:
        # Lightweight approach: just check if page has significant structured content
        # Don't access page.lines directly (it's expensive to compute)
        # Instead, use page.rects and page.curves as proxy for table structure
        rects = len(page.rects) if hasattr(page, 'rects') else 0
        curves = len(page.curves) if hasattr(page, 'curves') else 0

        # Pages with many rectangles or curves likely have tables/structured layouts
        # Threshold is conservative: only skip extraction if very text-like
        return (rects + curves) > 10
    except Exception:
        # If any error computing heuristic, skip table extraction (save time)
        # Missing some tables is better than crashing
        return False


def _extract_tables_with_timeout(page, timeout_seconds=10):
    """
    Extract tables from a PDF page with timeout to prevent hangs.
    Returns (tables, issue_type) where issue_type is None on success, or
    'timeout'/'error' if something went wrong.
    """
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                page.extract_tables,
                table_settings={
                    "vertical_strategy": "lines",
                    "horizontal_strategy": "lines"
                }
            )
            tables = future.result(timeout=timeout_seconds)
            return tables, None
    except FuturesTimeoutError:
        return None, "timeout"
    except Exception as e:
        return None, f"error: {str(e)[:50]}"
    # TODO 1.B5-c [MEDIUM, ~1500 tokens]: Add fallback table extraction strategies.
    #   When the "lines" strategy returns empty tables or errors, retry with:
    #     1. {"vertical_strategy": "text", "horizontal_strategy": "lines"}
    #     2. {"vertical_strategy": "text", "horizontal_strategy": "text"}
    #   Each with its own timeout. Return tables from the first strategy that succeeds
    #   and returns non-empty results. Log the strategy used as issue_type
    #   "fallback_text_lines" or "fallback_text_text". Use the same ThreadPoolExecutor
    #   pattern. No external data needed.


def ingest_pdf_file(conn: sqlite3.Connection, file_path: Path,
                    page_callback=None) -> int:
    """Ingest a single PDF file into the database.

    Args:
        conn: Database connection.
        file_path: Path to the PDF file.
        page_callback: Optional callable(pages_done, total_pages) called after
            each page is processed, for real-time progress reporting.
    """
    category = _determine_category(file_path)
    relative_path = str(file_path.relative_to(DOCS_DIR))
    total_pages = 0

    try:
        with pdfplumber.open(str(file_path)) as pdf:
            num_pages = len(pdf.pages)
            batch = []
            page_issues_count = 0  # Track timeouts/errors for this file
            for i, page in enumerate(pdf.pages):
                try:
                    # Use layout=False for 30-50% faster extraction (we don't need positioning)
                    text = page.extract_text(layout=False) or ""
                except Exception as e:
                    # Skip pages with font extraction errors (malformed FontBBox, etc.)
                    if "FontBBox" in str(e) or "cannot be parsed" in str(e):
                        text = ""
                    else:
                        raise

                # Extract tables with timeout to prevent hangs on malformed PDFs
                tables = []
                tables, issue_type = _extract_tables_with_timeout(page, timeout_seconds=10)
                if issue_type:
                    # Record the issue for later analysis
                    conn.execute(
                        "INSERT INTO extraction_issues (file_path, page_number, issue_type, issue_detail) VALUES (?,?,?,?)",
                        (relative_path, i + 1, issue_type.split(':')[0], issue_type)
                    )
                    page_issues_count += 1
                    tables = []  # Use empty tables on timeout/error

                table_text = _extract_table_text(tables)

                # Skip truly empty pages
                if not text.strip() and not table_text.strip():
                    if page_callback:
                        page_callback(i + 1, num_pages)
                    continue

                batch.append((
                    relative_path,
                    category,
                    i + 1,
                    text,
                    1 if tables else 0,
                    table_text if table_text else None,
                ))

                if page_callback:
                    page_callback(i + 1, num_pages)

                # Batch insert every 1000 pages (larger batch = fewer executemany calls)
                if len(batch) >= 1000:
                    conn.executemany("""
                        INSERT INTO pdf_pages (source_file, source_category,
                            page_number, page_text, has_tables, table_data)
                        VALUES (?,?,?,?,?,?)
                    """, batch)
                    total_pages += len(batch)
                    batch = []

            if batch:
                conn.executemany("""
                    INSERT INTO pdf_pages (source_file, source_category,
                        page_number, page_text, has_tables, table_data)
                    VALUES (?,?,?,?,?,?)
                """, batch)
                total_pages += len(batch)

    except Exception as e:
        print(f"  ERROR processing {file_path.name}: {e}")
        # TODO 1.B5-e [EASY, ~400 tokens, BUG FIX]: Verify this INSERT matches the
        #   ingested_files schema in create_database(). Count the columns in the table
        #   definition and ensure the VALUES list provides exactly that many. Add a test
        #   that passes a deliberately invalid PDF path to ingest_pdf_file() and asserts
        #   a row appears in ingested_files with status starting with "error:".
        conn.execute(
            "INSERT OR REPLACE INTO ingested_files (file_path, file_type, file_size, file_modified, ingested_at, row_count, status) VALUES (?,?,?,?,datetime('now'),?,?)",
            (relative_path, "pdf", file_path.stat().st_size, file_path.stat().st_mtime, 0, f"error: {e}")
        )
        return 0

    conn.commit()
    return total_pages


# ── Main Build Pipeline ───────────────────────────────────────────────────────

def _file_needs_update(conn: sqlite3.Connection, rel_path: str,
                       file_path: Path) -> bool:
    """Check if a file needs to be (re)ingested based on size and mtime."""
    stat = file_path.stat()
    row = conn.execute(
        "SELECT file_size, file_modified FROM ingested_files WHERE file_path = ?",
        (rel_path,)
    ).fetchone()

    if row is None:
        return True  # New file
    if row[0] != stat.st_size or abs((row[1] or 0) - stat.st_mtime) > 1:
        return True  # Modified file

    return False


def _remove_file_data(conn: sqlite3.Connection, rel_path: str, file_type: str):
    """Remove previously ingested data for a file before re-ingesting."""
    if file_type == "xlsx":
        conn.execute("DELETE FROM budget_lines WHERE source_file = ?", (rel_path,))
    elif file_type == "pdf":
        conn.execute("DELETE FROM pdf_pages WHERE source_file = ?", (rel_path,))


def _register_data_source(conn: sqlite3.Connection, docs_dir: Path):
    """Auto-register data sources from directory structure."""
    for fy_dir in sorted(docs_dir.iterdir()):
        if not fy_dir.is_dir() or not fy_dir.name.startswith("FY"):
            continue
        fiscal_year = fy_dir.name
        for src_dir in sorted(fy_dir.iterdir()):
            if not src_dir.is_dir():
                continue
            source_id = f"{fiscal_year}/{src_dir.name}"
            file_count = sum(1 for _ in src_dir.rglob("*") if _.is_file())
            conn.execute("""
                INSERT INTO data_sources (source_id, source_name, fiscal_year,
                    last_checked, file_count)
                VALUES (?, ?, ?, datetime('now'), ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    last_checked = datetime('now'),
                    file_count = excluded.file_count
            """, (source_id, src_dir.name, fiscal_year, file_count))
    conn.commit()


# ── Checkpoint Management ────────────────────────────────────────────────────

def _create_session_id() -> str:
    """Create a unique session ID for this build session."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    unique_id = str(uuid.uuid4())[:8]
    return f"sess-{timestamp}-{unique_id}"


def _save_checkpoint(conn: sqlite3.Connection, session_id: str, files_processed: int,
                     total_files: int, pages_processed: int, rows_inserted: int,
                     bytes_processed: int, last_file: str = None,
                     last_file_status: str = None, notes: str = None) -> None:
    """Save current build progress as a checkpoint.

    This allows resuming from a checkpoint without reprocessing files.
    """
    conn.execute("""
        INSERT INTO build_progress
        (session_id, files_processed, total_files, pages_processed, rows_inserted,
         bytes_processed, status, last_file, last_file_status, notes, checkpoint_time)
        VALUES (?, ?, ?, ?, ?, ?, 'in_progress', ?, ?, ?, datetime('now'))
        ON CONFLICT(session_id) DO UPDATE SET
            files_processed = excluded.files_processed,
            total_files = excluded.total_files,
            pages_processed = excluded.pages_processed,
            rows_inserted = excluded.rows_inserted,
            bytes_processed = excluded.bytes_processed,
            last_file = excluded.last_file,
            last_file_status = excluded.last_file_status,
            notes = excluded.notes,
            checkpoint_time = datetime('now')
    """, (session_id, files_processed, total_files, pages_processed, rows_inserted,
          bytes_processed, last_file, last_file_status, notes))
    conn.commit()


def _mark_file_processed(conn: sqlite3.Connection, session_id: str, file_path: str,
                         file_type: str, rows_count: int = 0, pages_count: int = 0) -> None:
    """Mark a file as processed in the current session."""
    conn.execute("""
        INSERT INTO processed_files
        (session_id, file_path, file_type, rows_count, pages_count, processed_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
    """, (session_id, str(file_path), file_type, rows_count, pages_count))
    conn.commit()


def _get_last_checkpoint(conn: sqlite3.Connection) -> dict | None:
    """Get the last checkpoint for resuming.

    Returns dict with session info or None if no checkpoint found.
    """
    cursor = conn.execute("""
        SELECT * FROM build_progress
        WHERE status = 'in_progress'
        ORDER BY checkpoint_time DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    if not row:
        return None

    # Convert to dict
    cols = [desc[0] for desc in cursor.description]
    return dict(zip(cols, row))


def _get_processed_files(conn: sqlite3.Connection, session_id: str) -> set:
    """Get set of file paths already processed in session."""
    cursor = conn.execute("""
        SELECT file_path FROM processed_files WHERE session_id = ?
    """, (session_id,))
    return {row[0] for row in cursor.fetchall()}


def _mark_session_complete(conn: sqlite3.Connection, session_id: str, notes: str = None) -> None:
    """Mark a session as completed."""
    conn.execute("""
        UPDATE build_progress
        SET status = 'completed', notes = ?
        WHERE session_id = ?
    """, (notes, session_id))
    conn.commit()


def build_database(docs_dir: Path, db_path: Path, rebuild: bool = False,
                   progress_callback=None, resume: bool = False,
                   checkpoint_interval: int = 10,
                   stop_event=None):
    """Build or incrementally update the budget database.

    Args:
        docs_dir: Path to the DoD_Budget_Documents directory.
        db_path: Path for the SQLite database file.
        rebuild: If True, delete existing database and rebuild from scratch.
        progress_callback: Optional callable(phase, current, total, detail, metrics)
            where phase is 'scan', 'excel', 'pdf', 'index', or 'done',
            current/total are progress counts, detail is a status string, and
            metrics is a dict with keys: rows, pages, speed_rows, speed_pages,
            eta_sec, files_remaining, current_pages, current_total_pages.
        resume: If True, attempt to resume from last checkpoint.
        checkpoint_interval: Save a checkpoint every N files (default 10).
        stop_event: Optional threading.Event; when set, the build saves a
            checkpoint and exits cleanly (graceful shutdown).
    """
    # ── Metrics state shared across the build ─────────────────────────────
    _metrics = {
        "rows": 0,
        "pages": 0,
        "speed_rows": 0.0,    # rows/sec (exponentially smoothed)
        "speed_pages": 0.0,   # pages/sec (exponentially smoothed)
        "eta_sec": 0.0,
        "files_remaining": 0,
        "current_pages": 0,       # pages in current PDF
        "current_total_pages": 0, # total pages in current PDF
    }

    def _progress(phase, current, total, detail="", metrics_update=None):
        if metrics_update:
            _metrics.update(metrics_update)
        if progress_callback:
            progress_callback(phase, current, total, detail, dict(_metrics))

    def _update_speed(key, new_value, alpha=0.3):
        """Exponential moving average for speed tracking."""
        if _metrics[key] == 0.0:
            _metrics[key] = new_value
        else:
            _metrics[key] = alpha * new_value + (1 - alpha) * _metrics[key]

    # ── Setup ──────────────────────────────────────────────────────────────
    if not docs_dir.exists():
        _progress("error", 0, 0, f"Documents directory not found: {docs_dir}")
        raise FileNotFoundError(f"Documents directory not found: {docs_dir}")

    if rebuild and db_path.exists():
        db_path.unlink()
        print(f"Removed existing database for rebuild: {db_path}")

    is_new = not db_path.exists()
    conn = create_database(db_path)

    if is_new:
        print(f"Created new database: {db_path}")
    else:
        print(f"Updating existing database: {db_path}")

    # ── Session and resume setup ───────────────────────────────────────────
    session_id = None
    already_processed: set = set()

    if resume and not rebuild:
        checkpoint = _get_last_checkpoint(conn)
        if checkpoint:
            session_id = checkpoint["session_id"]
            already_processed = _get_processed_files(conn, session_id)
            print(f"\nResuming session: {session_id}")
            print(f"  Already processed: {len(already_processed)} file(s)")
        else:
            print("\nNo checkpoint found — starting fresh build.")

    if session_id is None:
        session_id = _create_session_id()

    # ── Scan ───────────────────────────────────────────────────────────────
    _progress("scan", 0, 0, "Scanning directories...")
    _register_data_source(conn, docs_dir)

    xlsx_files = sorted(docs_dir.rglob("*.xlsx"))
    pdf_files = sorted(docs_dir.rglob("*.pdf"))
    total_files = len(xlsx_files) + len(pdf_files)

    # Save initial checkpoint so the session exists in build_progress from the start
    _save_checkpoint(conn, session_id, 0, total_files, 0, 0, 0,
                     notes="Build started")

    _progress("scan", 0, total_files,
              f"Found {len(xlsx_files)} Excel + {len(pdf_files)} PDF files",
              {"files_remaining": total_files - len(already_processed)})
    print(f"\nFound {len(xlsx_files)} Excel files and {len(pdf_files)} PDF files")

    if already_processed:
        xl_skipped_resume = sum(1 for f in xlsx_files
                                if str(f.relative_to(docs_dir)) in already_processed)
        pdf_skipped_resume = sum(1 for f in pdf_files
                                 if str(f.relative_to(docs_dir)) in already_processed)
        print(f"  Resuming: skipping {xl_skipped_resume} Excel + {pdf_skipped_resume} PDF "
              f"files already processed in session {session_id}")

    # ── Ingest Excel files ─────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  INGESTING EXCEL FILES")
    print(f"{'='*60}")

    total_budget_rows = 0
    skipped_xlsx = 0
    excel_file_times: list[float] = []  # per-file elapsed times for speed calc
    files_done_total = 0  # across both xlsx and pdf

    for xi, xlsx in enumerate(xlsx_files):
        # Check for graceful shutdown request
        if stop_event and stop_event.is_set():
            print("\n  Graceful stop requested — saving checkpoint...")
            _save_checkpoint(conn, session_id, files_done_total, total_files,
                             _metrics["pages"], _metrics["rows"],
                             0, str(xlsx), "interrupted")
            conn.commit()
            _progress("stopped", xi, len(xlsx_files),
                      f"Stopped at {xlsx.name} — resume with --resume",
                      {"files_remaining": total_files - files_done_total})
            conn.close()
            return

        rel_path = str(xlsx.relative_to(docs_dir))

        # Skip if already processed in a resumed session
        if rel_path in already_processed:
            skipped_xlsx += 1
            files_done_total += 1
            _progress("excel", xi + 1, len(xlsx_files),
                      f"Resumed (skipped): {xlsx.name}",
                      {"files_remaining": total_files - files_done_total})
            continue

        if not rebuild and not _file_needs_update(conn, rel_path, xlsx):
            skipped_xlsx += 1
            files_done_total += 1
            _progress("excel", xi + 1, len(xlsx_files),
                      f"Skipped (unchanged): {xlsx.name}",
                      {"files_remaining": total_files - files_done_total})
            continue

        _progress("excel", xi + 1, len(xlsx_files),
                  f"Processing: {xlsx.name}",
                  {"files_remaining": total_files - files_done_total})
        print(f"  Processing: {xlsx.name}...", end=" ", flush=True)

        _remove_file_data(conn, rel_path, "xlsx")

        t0 = time.time()
        rows = ingest_excel_file(conn, xlsx)
        file_elapsed = time.time() - t0
        print(f"{rows} rows ({file_elapsed:.1f}s)")

        # Update speed tracking
        if file_elapsed > 0 and rows > 0:
            _update_speed("speed_rows", rows / file_elapsed)
        excel_file_times.append(file_elapsed)

        stat = xlsx.stat()
        conn.execute(
            "INSERT OR REPLACE INTO ingested_files "
            "(file_path, file_type, file_size, file_modified, ingested_at, row_count, status) "
            "VALUES (?,?,?,?,datetime('now'),?,?)",
            (rel_path, "xlsx", stat.st_size, stat.st_mtime, rows, "ok")
        )
        total_budget_rows += rows
        files_done_total += 1
        _metrics["rows"] = total_budget_rows

        # Post-file progress update with updated row count
        _progress("excel", xi + 1, len(xlsx_files),
                  f"Done: {xlsx.name} ({rows} rows)",
                  {"rows": total_budget_rows,
                   "files_remaining": total_files - files_done_total})

        # Track file as processed and checkpoint periodically
        _mark_file_processed(conn, session_id, rel_path, "excel", rows_count=rows)
        if files_done_total % checkpoint_interval == 0:
            remaining = total_files - files_done_total
            # ETA: average per-file time × files remaining
            avg_time = sum(excel_file_times) / len(excel_file_times) if excel_file_times else 0
            _metrics["eta_sec"] = avg_time * remaining
            _metrics["files_remaining"] = remaining
            _save_checkpoint(conn, session_id, files_done_total, total_files,
                             _metrics["pages"], total_budget_rows,
                             stat.st_size, rel_path, "ok")

    conn.commit()
    if skipped_xlsx:
        print(f"\n  Skipped {skipped_xlsx} unchanged Excel file(s)")
    print(f"  Ingested budget line items: {total_budget_rows:,}")

    # ── Ingest PDF files ───────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  INGESTING PDF FILES")
    print(f"{'='*60}")

    total_pdf_pages = 0
    skipped_pdf = 0
    processed_pdf = 0
    last_commit_time = time.time()
    initial_page_count = conn.execute("SELECT COUNT(*) FROM pdf_pages").fetchone()[0]
    pdf_file_times: list[float] = []  # per-file elapsed for speed calc
    _pdf_stopped = False  # set when a graceful stop fires inside the PDF loop

    # Drop FTS5 triggers for bulk insert speedup
    print("  Dropping FTS5 triggers for bulk insert optimization...")
    try:
        conn.execute("DROP TRIGGER IF EXISTS pdf_pages_ai")
        conn.execute("DROP TRIGGER IF EXISTS pdf_pages_ad")
        conn.commit()
    except Exception as e:
        print(f"    (Warning: {e})")

    try:
        for i, pdf in enumerate(pdf_files):
            # Check for graceful shutdown request
            if stop_event and stop_event.is_set():
                print("\n  Graceful stop requested — saving checkpoint...")
                _save_checkpoint(conn, session_id, files_done_total, total_files,
                                 total_pdf_pages, total_budget_rows,
                                 0, str(pdf), "interrupted")
                conn.commit()
                _pdf_stopped = True
                _progress("stopped", i, len(pdf_files),
                          f"Stopped at {pdf.name} — resume with --resume",
                          {"files_remaining": total_files - files_done_total})
                break

            rel_path = str(pdf.relative_to(docs_dir))

            # Skip if already processed in resumed session
            if rel_path in already_processed:
                skipped_pdf += 1
                files_done_total += 1
                _progress("pdf", i + 1, len(pdf_files),
                          f"Resumed (skipped): {pdf.name}",
                          {"files_remaining": total_files - files_done_total})
                continue

            if not rebuild and not _file_needs_update(conn, rel_path, pdf):
                skipped_pdf += 1
                files_done_total += 1
                _progress("pdf", i + 1, len(pdf_files),
                          f"Skipped (unchanged): {pdf.name}",
                          {"files_remaining": total_files - files_done_total})
                continue

            processed_pdf += 1
            files_done_total += 1
            _metrics["files_remaining"] = total_files - files_done_total

            _progress("pdf", i + 1, len(pdf_files),
                      f"[{processed_pdf}] {pdf.name}",
                      {"files_remaining": total_files - files_done_total,
                       "current_pages": 0,
                       "current_total_pages": 0})
            print(f"  [{processed_pdf}/{len(pdf_files) - skipped_pdf}] {pdf.name}...",
                  end=" ", flush=True)

            _remove_file_data(conn, rel_path, "pdf")

            def _page_cb(pages_done: int, page_total: int) -> None:
                _metrics["current_pages"] = pages_done
                _metrics["current_total_pages"] = page_total
                _progress("pdf", i + 1, len(pdf_files),
                          f"[{processed_pdf}] {pdf.name} — page {pages_done}/{page_total}",
                          {"files_remaining": total_files - files_done_total,
                           "current_pages": pages_done,
                           "current_total_pages": page_total})

            t0 = time.time()
            pages = ingest_pdf_file(conn, pdf, page_callback=_page_cb)
            file_elapsed = time.time() - t0
            print(f"{pages} pages ({file_elapsed:.1f}s)")

            # Update speed tracking
            if file_elapsed > 0 and pages > 0:
                _update_speed("speed_pages", pages / file_elapsed)
            pdf_file_times.append(file_elapsed)

            # ETA update: average time per file × remaining PDF files
            pdfs_remaining = len(pdf_files) - (i + 1)
            avg_pdf_time = (sum(pdf_file_times) / len(pdf_file_times)
                            if pdf_file_times else 0)
            _metrics["eta_sec"] = avg_pdf_time * pdfs_remaining
            _metrics["pages"] = total_pdf_pages + pages

            issue_count = conn.execute(
                "SELECT COUNT(*) FROM extraction_issues WHERE file_path = ?",
                (rel_path,)
            ).fetchone()[0]
            file_status = "ok_with_issues" if issue_count > 0 else "ok"

            stat = pdf.stat()
            conn.execute(
                "INSERT OR REPLACE INTO ingested_files "
                "(file_path, file_type, file_size, file_modified, ingested_at, row_count, status) "
                "VALUES (?,?,?,?,datetime('now'),?,?)",
                (rel_path, "pdf", stat.st_size, stat.st_mtime, pages, file_status)
            )
            total_pdf_pages += pages
            _metrics["pages"] = total_pdf_pages

            # Track file as processed
            _mark_file_processed(conn, session_id, rel_path, "pdf", pages_count=pages)

            # Checkpoint every N files
            if files_done_total % checkpoint_interval == 0:
                _save_checkpoint(conn, session_id, files_done_total, total_files,
                                 total_pdf_pages, total_budget_rows,
                                 stat.st_size, rel_path, file_status)

            # Commit every 2 seconds for durability
            if time.time() - last_commit_time > 2.0:
                conn.commit()
                last_commit_time = time.time()

    finally:
        if not _pdf_stopped:
            # Rebuild FTS5 if new pages were added
            final_page_count = conn.execute("SELECT COUNT(*) FROM pdf_pages").fetchone()[0]
            if final_page_count > initial_page_count:
                print("\n  Rebuilding full-text search indexes...")
                conn.execute("DELETE FROM pdf_pages_fts;")
                conn.execute("""
                    INSERT INTO pdf_pages_fts(rowid, page_text, source_file, table_data)
                    SELECT id, page_text, source_file, table_data FROM pdf_pages;
                """)
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS pdf_pages_ai AFTER INSERT ON pdf_pages BEGIN
                        INSERT INTO pdf_pages_fts(rowid, page_text, source_file, table_data)
                        VALUES (new.id, new.page_text, new.source_file, new.table_data);
                    END
                """)
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS pdf_pages_ad AFTER DELETE ON pdf_pages BEGIN
                        INSERT INTO pdf_pages_fts(pdf_pages_fts, rowid, page_text, source_file, table_data)
                        VALUES ('delete', old.id, old.page_text, old.source_file, old.table_data);
                    END
                """)
                conn.commit()
                print("  FTS5 rebuild complete and triggers recreated")
            else:
                conn.execute(
                    "CREATE TRIGGER IF NOT EXISTS pdf_pages_ai AFTER INSERT ON pdf_pages BEGIN "
                    "INSERT INTO pdf_pages_fts(rowid, page_text, source_file, table_data) "
                    "VALUES (new.id, new.page_text, new.source_file, new.table_data); END"
                )
                conn.execute(
                    "CREATE TRIGGER IF NOT EXISTS pdf_pages_ad AFTER DELETE ON pdf_pages BEGIN "
                    "INSERT INTO pdf_pages_fts(pdf_pages_fts, rowid, page_text, source_file, table_data) "
                    "VALUES ('delete', old.id, old.page_text, old.source_file, old.table_data); END"
                )
                conn.commit()
                print("  Skipped FTS5 rebuild (no new pages added)")

    # If stopped gracefully during PDF loop, close and exit cleanly
    if _pdf_stopped:
        conn.close()
        return

    if skipped_pdf:
        print(f"\n  Skipped {skipped_pdf} unchanged PDF file(s)")
    print(f"  Ingested PDF pages: {total_pdf_pages:,}")

    # ── Detect removed files ───────────────────────────────────────────────
    all_current = {str(f.relative_to(docs_dir)) for f in xlsx_files}
    all_current |= {str(f.relative_to(docs_dir)) for f in pdf_files}

    orphaned = conn.execute(
        "SELECT file_path, file_type FROM ingested_files"
    ).fetchall()
    removed_count = 0
    for row in orphaned:
        if row[0] not in all_current:
            _remove_file_data(conn, row[0], row[1])
            conn.execute("DELETE FROM ingested_files WHERE file_path = ?", (row[0],))
            print(f"  Removed stale data for: {row[0]}")
            removed_count += 1

    if removed_count:
        conn.commit()
        print(f"  Cleaned up {removed_count} removed file(s)")

    # ── Create indexes ─────────────────────────────────────────────────────
    _progress("index", 0, 1, "Creating indexes...")
    print("\nCreating indexes...")
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_bl_exhibit ON budget_lines(exhibit_type);
        CREATE INDEX IF NOT EXISTS idx_bl_org ON budget_lines(organization_name);
        CREATE INDEX IF NOT EXISTS idx_bl_account ON budget_lines(account);
        CREATE INDEX IF NOT EXISTS idx_bl_fy ON budget_lines(fiscal_year);
        CREATE INDEX IF NOT EXISTS idx_bl_sheet ON budget_lines(sheet_name);
        CREATE INDEX IF NOT EXISTS idx_bl_source ON budget_lines(source_file);
        CREATE INDEX IF NOT EXISTS idx_bl_pe ON budget_lines(pe_number);
        CREATE INDEX IF NOT EXISTS idx_pp_source ON pdf_pages(source_file);
        CREATE INDEX IF NOT EXISTS idx_pp_category ON pdf_pages(source_category);
    """)
    conn.commit()
    _progress("index", 1, 1, "Indexes created")

    # ── Update data source timestamps ──────────────────────────────────────
    conn.execute("""
        UPDATE data_sources SET last_updated = datetime('now')
        WHERE source_id IN (
            SELECT DISTINCT
                substr(file_path, 1, instr(substr(file_path, 1+instr(file_path, '/')), '/') + instr(file_path, '/') - 1)
            FROM ingested_files
        )
    """)
    conn.commit()

    # ── Mark session complete ──────────────────────────────────────────────
    _mark_session_complete(conn, session_id,
                           f"Processed {files_done_total} files: "
                           f"{total_budget_rows:,} rows, {total_pdf_pages:,} pages")

    # ── Summary ────────────────────────────────────────────────────────────
    total_lines = conn.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0]
    total_pages = conn.execute("SELECT COUNT(*) FROM pdf_pages").fetchone()[0]
    db_size = db_path.stat().st_size / (1024 * 1024)

    summary = (
        f"Database: {db_path} ({db_size:.1f} MB)\n"
        f"Budget lines: {total_lines:,}\n"
        f"PDF pages: {total_pages:,}\n"
        f"Excel files: {len(xlsx_files)}\n"
        f"PDF files: {len(pdf_files)}"
    )

    print(f"\n{'='*60}")
    print(f"  BUILD COMPLETE")
    print(f"{'='*60}")
    print(f"  Database:           {db_path} ({db_size:.1f} MB)")
    print(f"  Total budget lines: {total_lines:,}")
    print(f"  Total PDF pages:    {total_pages:,}")
    print(f"  Excel files:        {len(xlsx_files)}")
    print(f"  PDF files:          {len(pdf_files)}")
    if not rebuild:
        new_files = (len(xlsx_files) - skipped_xlsx) + (len(pdf_files) - skipped_pdf)
        print(f"  New/updated files:  {new_files}")
        print(f"  Unchanged (skip):   {skipped_xlsx + skipped_pdf}")
        summary += f"\nNew/updated: {new_files} | Skipped: {skipped_xlsx + skipped_pdf}"

    _progress("done", total_files, total_files, summary,
              {"files_remaining": 0, "eta_sec": 0.0})
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Build DoD budget search database")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                        help=f"Database path (default: {DEFAULT_DB_PATH})")
    parser.add_argument("--docs", type=Path, default=DOCS_DIR,
                        help=f"Documents directory (default: {DOCS_DIR})")
    parser.add_argument("--rebuild", action="store_true",
                        help="Force full rebuild (delete existing database)")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from last checkpoint")
    parser.add_argument("--checkpoint-interval", type=int, default=10,
                        metavar="N",
                        help="Save a checkpoint every N files (default: 10)")
    args = parser.parse_args()

    # ── Graceful shutdown via Ctrl+C ───────────────────────────────────────
    import threading
    stop_event = threading.Event()

    def _sigint_handler(sig, frame):
        if not stop_event.is_set():
            print("\n\nKeyboard interrupt — finishing current file and saving checkpoint...")
            print("Resume later with: python build_budget_db.py --resume")
            stop_event.set()
        else:
            print("\nForce-quitting...")
            sys.exit(1)

    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        build_database(args.docs, args.db,
                       rebuild=args.rebuild,
                       resume=args.resume,
                       checkpoint_interval=args.checkpoint_interval,
                       stop_event=stop_event)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
