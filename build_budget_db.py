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
Roadmap TODOs for this file (Steps 1.B2 – 1.B5)
──────────────────────────────────────────────────────────────────────────────

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
import sqlite3
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

# ── PE Number Pattern (TODO 1.B4-a) ──────────────────────────────────────────
# Program Element numbers follow the pattern: 7 digits followed by one uppercase letter
# e.g. "0602702E", "0305116BB" (some have two-letter suffixes)
_PE_PATTERN = re.compile(r'\b\d{7}[A-Z]{1,2}\b')

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
            -- TODO: Fiscal year columns are hardcoded to FY2024-2026. When new
            -- budget years are released, the schema, column mapping, and all INSERT
            -- statements must be updated in lockstep. Consider a normalized design
            -- (separate fiscal_year_amounts table with year/type/amount columns) or
            -- storing amounts as JSON in extra_fields for forward compatibility.
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
            -- TODO 1.B4-a: PE number extracted from line_item/account fields
            pe_number TEXT,
            -- TODO 1.B3-b: Currency year (then-year or constant dollars)
            currency_year TEXT,
            -- TODO 1.B4-c: Appropriation code and title split from account_title
            appropriation_code TEXT,
            appropriation_title TEXT
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
    """)

    conn.commit()
    return conn


# ── Excel Ingestion ───────────────────────────────────────────────────────────

def _safe_float(val):
    """Convert a value to float, returning None for non-numeric."""
    if val is None or val == "" or val == " ":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


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


# TODO: This function is ~110 lines with three large loops over h_lower doing
# related but distinct work (common fields, sub-activity/line-item, amounts).
# Consider splitting into _map_common_fields, _map_line_item_fields, and
# _map_amount_fields for readability and easier per-exhibit customization.
def _map_columns(headers: list, exhibit_type: str) -> dict:
    """Map column headers to standardized field names.

    Returns a dict mapping our field names to column indices.
    Optimized to use a single pass over headers with fallback logic.
    """
    mapping = {}
    h_lower = [str(h).lower().replace("\n", " ").strip() if h else "" for h in headers]

    # Single-pass column mapping with normalized field matching
    for i, h in enumerate(h_lower):
        h_normalized = h.replace(" ", "")

        # Common fields
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

        # Sub-activity / line item fields
        elif h in ("bsa", "ag/bsa"):
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
        elif h in ("sag/bli",):
            mapping["line_item"] = i
        elif h == "sag/budget line item (bli) title":
            mapping["line_item_title"] = i
        elif h == "construction project title":
            mapping["line_item_title"] = i
        elif h == "construction project":
            mapping["line_item"] = i
        elif h == "location title":
            mapping.setdefault("sub_activity_title", i)
        elif h == "facility category title":
            mapping.setdefault("sub_activity", i)

        # FY2024 amounts and quantities
        elif "fy2024" in h_normalized or "fy2024" in h:
            if "quantity" in h:
                mapping["quantity_fy2024"] = i
            elif "actual" in h and ("amount" in h or "actual" in h):
                mapping.setdefault("amount_fy2024_actual", i)

        # FY2025 amounts and quantities
        elif "fy2025" in h_normalized or "fy2025" in h:
            if "quantity" in h:
                mapping["quantity_fy2025"] = i
            elif "enacted" in h and ("amount" in h or "enacted" in h):
                mapping.setdefault("amount_fy2025_enacted", i)
            elif "supplemental" in h:
                mapping.setdefault("amount_fy2025_supplemental", i)
            elif "total" in h:
                mapping.setdefault("amount_fy2025_total", i)

        # FY2026 amounts and quantities
        elif "fy2026" in h_normalized or "fy2026" in h:
            if "quantity" in h:
                if "total" in h:
                    mapping["quantity_fy2026_total"] = i
                elif "request" in h or "disc" in h:
                    mapping["quantity_fy2026_request"] = i
            elif "reconcil" in h and ("amount" in h or "reconcil" in h):
                mapping.setdefault("amount_fy2026_reconciliation", i)
            elif "total" in h and ("amount" in h or "total" in h):
                mapping.setdefault("amount_fy2026_total", i)
            elif "request" in h or "disc" in h:
                if "amount" in h or "request" in h or "disc" in h:
                    mapping.setdefault("amount_fy2026_request", i)

        # Authorization/appropriation amounts (C-1 exhibit)
        elif "authorization amount" in h:
            mapping.setdefault("amount_fy2026_request", i)
        elif "appropriation amount" in h:
            mapping.setdefault("amount_fy2025_enacted", i)
        elif "total obligation authority" in h:
            mapping.setdefault("amount_fy2026_total", i)

    return mapping


def ingest_excel_file(conn: sqlite3.Connection, file_path: Path) -> int:
    """Ingest a single Excel file into the database."""
    wb = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
    exhibit_type = _detect_exhibit_type(file_path.name)
    total_rows = 0

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows_iter = ws.iter_rows(values_only=True)

        # Find the header row in the first 5 rows (buffer to avoid full materialization)
        header_idx = None
        first_rows = []
        for i, row in enumerate(rows_iter):
            first_rows.append(row)
            if i >= 4:
                break
            for val in row:
                if val and str(val).strip().lower() == "account":
                    header_idx = i
                    break
            if header_idx is not None:
                break

        if header_idx is None or len(first_rows) < 3:
            continue

        headers = first_rows[header_idx]
        col_map = _map_columns(headers, exhibit_type)

        if "account" not in col_map:
            continue

        # Detect fiscal year from sheet name
        fy_match = re.search(r"(FY\s*)?20\d{2}", sheet_name, re.IGNORECASE)
        fiscal_year = fy_match.group().replace("FY ", "FY").replace("FY", "FY ") if fy_match else sheet_name

        # Detect currency year for this sheet (TODO 1.B3-b)
        currency_year = _detect_currency_year(sheet_name, file_path.name)

        data_rows = rows[header_idx + 1:]
        batch = []

        def get_val(row, field):
            """Safely get value from row using column mapping."""
            idx = col_map.get(field)
            return row[idx] if idx is not None and idx < len(row) else None

        def get_str(row, field):
            """Get string value from row, safe for None."""
            v = get_val(row, field)
            return str(v).strip() if v is not None else None

        def get_org_name(row):
            """Get organization name, defaulting to code if not in map."""
            org_code = get_str(row, "organization") or ""
            return ORG_MAP.get(org_code, org_code)

        # Process rows after header
        for row in rows_iter:
            if not row or all(v is None for v in row):
                continue

            acct = get_val(row, "account")
            if not acct:
                continue

            org_name = get_org_name(row)

            # TODO 1.B4-a: extract PE number from line_item or account fields
            line_item_val = get_str(row, "line_item")
            account_val = str(acct).strip()
            pe_number = _extract_pe_number(line_item_val) or _extract_pe_number(account_val)

            # TODO 1.B4-c: split appropriation code and title from account_title
            acct_title_val = get_str(row, "account_title")
            approp_code, approp_title = _parse_appropriation(acct_title_val)

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
                _safe_float(get_val(row, "amount_fy2024_actual")),
                _safe_float(get_val(row, "amount_fy2025_enacted")),
                _safe_float(get_val(row, "amount_fy2025_supplemental")),
                _safe_float(get_val(row, "amount_fy2025_total")),
                _safe_float(get_val(row, "amount_fy2026_request")),
                _safe_float(get_val(row, "amount_fy2026_reconciliation")),
                _safe_float(get_val(row, "amount_fy2026_total")),
                _safe_float(get_val(row, "quantity_fy2024")),
                _safe_float(get_val(row, "quantity_fy2025")),
                _safe_float(get_val(row, "quantity_fy2026_request")),
                _safe_float(get_val(row, "quantity_fy2026_total")),
                None,         # extra_fields
                pe_number,    # TODO 1.B4-a
                currency_year,  # TODO 1.B3-b
                approp_code,  # TODO 1.B4-c
                approp_title, # TODO 1.B4-c
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
                    appropriation_code, appropriation_title
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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


def ingest_pdf_file(conn: sqlite3.Connection, file_path: Path) -> int:
    """Ingest a single PDF file into the database."""
    category = _determine_category(file_path)
    relative_path = str(file_path.relative_to(DOCS_DIR))
    total_pages = 0

    try:
        with pdfplumber.open(str(file_path)) as pdf:
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

                # Extract tables only if page likely contains structured content
                tables = None
                issue_type = None
                if _likely_has_tables(page):
                    tables, issue_type = _extract_tables_with_timeout(page, timeout_seconds=10)
                    if issue_type:
                        # Record the issue for later analysis
                        conn.execute(
                            "INSERT INTO extraction_issues (file_path, page_number, issue_type, issue_detail) VALUES (?,?,?,?)",
                            (relative_path, i + 1, issue_type.split(':')[0], issue_type)
                        )
                        page_issues_count += 1
                        tables = []
                else:
                    tables = []

                table_text = _extract_table_text(tables)

                # Skip truly empty pages
                if not text.strip() and not table_text.strip():
                    continue

                batch.append((
                    relative_path,
                    category,
                    i + 1,
                    text,
                    1 if tables else 0,
                    table_text if table_text else None,
                ))

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


def _recreate_pdf_fts_triggers(conn: sqlite3.Connection):
    """Recreate FTS5 triggers for pdf_pages table.

    Used after bulk operations to maintain FTS5 index synchronization.
    """
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


def build_database(docs_dir: Path, db_path: Path, rebuild: bool = False,
                   progress_callback=None):
    """Build or incrementally update the budget database.

    Args:
        docs_dir: Path to the DoD_Budget_Documents directory.
        db_path: Path for the SQLite database file.
        rebuild: If True, delete existing database and rebuild from scratch.
        progress_callback: Optional callable(phase, current, total, detail)
            where phase is 'scan', 'excel', 'pdf', 'index', or 'done',
            current/total are progress counts, and detail is a status string.
    """
    def _progress(phase, current, total, detail=""):
        if progress_callback:
            progress_callback(phase, current, total, detail)

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

    # Register data sources
    _progress("scan", 0, 0, "Scanning directories...")
    _register_data_source(conn, docs_dir)

    # Collect all files
    xlsx_files = sorted(docs_dir.rglob("*.xlsx"))
    pdf_files = sorted(docs_dir.rglob("*.pdf"))
    total_files = len(xlsx_files) + len(pdf_files)

    _progress("scan", 0, total_files,
              f"Found {len(xlsx_files)} Excel + {len(pdf_files)} PDF files")
    print(f"\nFound {len(xlsx_files)} Excel files and {len(pdf_files)} PDF files")

    # ── Ingest Excel files ──
    print(f"\n{'='*60}")
    print("  INGESTING EXCEL FILES")
    print(f"{'='*60}")

    total_budget_rows = 0
    skipped_xlsx = 0
    for xi, xlsx in enumerate(xlsx_files):
        rel_path = str(xlsx.relative_to(docs_dir))
        if not rebuild and not _file_needs_update(conn, rel_path, xlsx):
            skipped_xlsx += 1
            _progress("excel", xi + 1, len(xlsx_files),
                      f"Skipped (unchanged): {xlsx.name}")
            continue

        _progress("excel", xi + 1, len(xlsx_files),
                  f"Processing: {xlsx.name}")
        print(f"  Processing: {xlsx.name}...", end=" ", flush=True)

        # Remove old data if re-ingesting
        _remove_file_data(conn, rel_path, "xlsx")

        t0 = time.time()
        rows = ingest_excel_file(conn, xlsx)
        elapsed = time.time() - t0
        print(f"{rows} rows ({elapsed:.1f}s)")

        stat = xlsx.stat()
        conn.execute(
            "INSERT OR REPLACE INTO ingested_files (file_path, file_type, file_size, file_modified, ingested_at, row_count, status) VALUES (?,?,?,?,datetime('now'),?,?)",
            (rel_path, "xlsx", stat.st_size, stat.st_mtime, rows, "ok")
        )
        total_budget_rows += rows

    conn.commit()
    if skipped_xlsx:
        print(f"\n  Skipped {skipped_xlsx} unchanged Excel file(s)")
    print(f"  Ingested budget line items: {total_budget_rows:,}")

    # ── Ingest PDF files ──
    print(f"\n{'='*60}")
    print("  INGESTING PDF FILES")
    print(f"{'='*60}")

    total_pdf_pages = 0
    skipped_pdf = 0
    processed = 0
    last_commit_time = time.time()
    initial_page_count = conn.execute("SELECT COUNT(*) FROM pdf_pages").fetchone()[0]

    # Drop FTS5 triggers for bulk insert speedup - we'll rebuild FTS5 at the end
    # PRAGMA disable_trigger doesn't work on virtual table triggers, so we drop and recreate
    print("  Dropping FTS5 triggers for bulk insert optimization...")
    try:
        conn.execute("DROP TRIGGER IF EXISTS pdf_pages_ai")
        conn.execute("DROP TRIGGER IF EXISTS pdf_pages_ad")
        conn.commit()
    except Exception as e:
        print(f"    (Warning: {e})")

    try:
        for i, pdf in enumerate(pdf_files):
            rel_path = str(pdf.relative_to(docs_dir))
            if not rebuild and not _file_needs_update(conn, rel_path, pdf):
                skipped_pdf += 1
                _progress("pdf", i + 1, len(pdf_files),
                          f"Skipped (unchanged): {pdf.name}")
                continue

            processed += 1
            _progress("pdf", i + 1, len(pdf_files),
                      f"[{processed}] {pdf.name}")
            print(f"  [{processed}/{len(pdf_files) - skipped_pdf}] {pdf.name}...", end=" ", flush=True)

            # Remove old data if re-ingesting
            _remove_file_data(conn, rel_path, "pdf")

            t0 = time.time()
            pages = ingest_pdf_file(conn, pdf)
            elapsed = time.time() - t0
            print(f"{pages} pages ({elapsed:.1f}s)")

            # Check if this file had any extraction issues
            issue_count = conn.execute(
                "SELECT COUNT(*) FROM extraction_issues WHERE file_path = ?",
                (rel_path,)
            ).fetchone()[0]
            file_status = "ok_with_issues" if issue_count > 0 else "ok"

            stat = pdf.stat()
            conn.execute(
                "INSERT OR REPLACE INTO ingested_files (file_path, file_type, file_size, file_modified, ingested_at, row_count, status) VALUES (?,?,?,?,datetime('now'),?,?)",
                (rel_path, "pdf", stat.st_size, stat.st_mtime, pages, file_status)
            )
            total_pdf_pages += pages

            # Commit every 2 seconds for good durability without excessive I/O
            if time.time() - last_commit_time > 2.0:
                conn.commit()
                last_commit_time = time.time()

    finally:
        # Only rebuild FTS5 if we actually added new pages
        final_page_count = conn.execute("SELECT COUNT(*) FROM pdf_pages").fetchone()[0]
        if final_page_count > initial_page_count:
            # Rebuild FTS5 indexes in batch (triggers were dropped, now rebuild in one go)
            print("\n  Rebuilding full-text search indexes...")
            conn.execute("DELETE FROM pdf_pages_fts;")
            conn.execute("""
                INSERT INTO pdf_pages_fts(rowid, page_text, source_file, table_data)
                SELECT id, page_text, source_file, table_data FROM pdf_pages;
            """)
            _recreate_pdf_fts_triggers(conn)
            conn.commit()
            print("  FTS5 rebuild complete and triggers recreated")
        else:
            # No new pages, just recreate triggers without rebuild
            _recreate_pdf_fts_triggers(conn)
            conn.commit()
            print("  Skipped FTS5 rebuild (no new pages added)")

    if skipped_pdf:
        print(f"\n  Skipped {skipped_pdf} unchanged PDF file(s)")
    print(f"  Ingested PDF pages: {total_pdf_pages:,}")

    # ── Detect removed files ──
    all_current = set()
    for f in xlsx_files:
        all_current.add(str(f.relative_to(docs_dir)))
    for f in pdf_files:
        all_current.add(str(f.relative_to(docs_dir)))

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

    # ── Create indexes ──
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

    # ── Update data source timestamps ──
    conn.execute("""
        UPDATE data_sources SET last_updated = datetime('now')
        WHERE source_id IN (
            SELECT DISTINCT
                substr(file_path, 1, instr(substr(file_path, 1+instr(file_path, '/')), '/') + instr(file_path, '/') - 1)
            FROM ingested_files
        )
    """)
    conn.commit()

    # ── Summary ──
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

    _progress("done", total_files, total_files, summary)
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Build DoD budget search database")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                        help=f"Database path (default: {DEFAULT_DB_PATH})")
    parser.add_argument("--docs", type=Path, default=DOCS_DIR,
                        help=f"Documents directory (default: {DOCS_DIR})")
    parser.add_argument("--rebuild", action="store_true",
                        help="Force full rebuild (delete existing database)")
    args = parser.parse_args()

    try:
        build_database(args.docs, args.db, rebuild=args.rebuild)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
