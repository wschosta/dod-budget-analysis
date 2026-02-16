"""
DoD Budget Database Builder

Ingests Excel spreadsheets and PDF documents from the DoD_Budget_Documents
directory into a searchable SQLite database with full-text search (FTS5).

Supports incremental updates — only processes new or modified files.

Usage:
    python build_budget_db.py                  # Build or update the database
    python build_budget_db.py --rebuild        # Force full rebuild
    python build_budget_db.py --db mydb.sqlite # Custom database path
"""

import argparse
import os  # TODO: Remove unused import (os is never referenced)
import re
import sqlite3
import sys
import time
from pathlib import Path

import openpyxl
import pandas as pd  # TODO: Remove unused import (pandas is never referenced)
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
            extra_fields TEXT
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


# TODO: This function is ~110 lines with three large loops over h_lower doing
# related but distinct work (common fields, sub-activity/line-item, amounts).
# Consider splitting into _map_common_fields, _map_line_item_fields, and
# _map_amount_fields for readability and easier per-exhibit customization.
def _map_columns(headers: list, exhibit_type: str) -> dict:
    """Map column headers to standardized field names.

    Returns a dict mapping our field names to column indices.
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

        data_rows = rows[header_idx + 1:]
        batch = []

        for row in data_rows:
            if not row or all(v is None for v in row):
                continue

            acct = row[col_map["account"]] if col_map.get("account") is not None and col_map["account"] < len(row) else None
            if not acct:
                continue

            org_code = str(row[col_map["organization"]]).strip() if col_map.get("organization") is not None and col_map["organization"] < len(row) and row[col_map["organization"]] else ""
            org_name = ORG_MAP.get(org_code, org_code)

            # TODO: get_val and get_str are redefined as closures on every row
            # iteration, but they only depend on col_map (loop-invariant) and row.
            # Move them outside the loop and pass row as a parameter to avoid
            # re-creating function objects on every iteration.
            def get_val(field):
                idx = col_map.get(field)
                if idx is not None and idx < len(row):
                    return row[idx]
                return None

            def get_str(field):
                v = get_val(field)
                return str(v).strip() if v is not None else None

            batch.append((
                str(file_path.relative_to(DOCS_DIR)),
                exhibit_type,
                sheet_name,
                fiscal_year,
                str(acct).strip(),
                get_str("account_title"),
                org_code,
                org_name,
                get_str("budget_activity"),
                get_str("budget_activity_title"),
                get_str("sub_activity"),
                get_str("sub_activity_title"),
                get_str("line_item"),
                get_str("line_item_title"),
                get_str("classification"),
                _safe_float(get_val("amount_fy2024_actual")),
                _safe_float(get_val("amount_fy2025_enacted")),
                _safe_float(get_val("amount_fy2025_supplemental")),
                _safe_float(get_val("amount_fy2025_total")),
                _safe_float(get_val("amount_fy2026_request")),
                _safe_float(get_val("amount_fy2026_reconciliation")),
                _safe_float(get_val("amount_fy2026_total")),
                _safe_float(get_val("quantity_fy2024")),
                _safe_float(get_val("quantity_fy2025")),
                _safe_float(get_val("quantity_fy2026_request")),
                _safe_float(get_val("quantity_fy2026_total")),
                None,  # extra_fields
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
                    extra_fields
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, batch)
            total_rows += len(batch)

    wb.close()
    conn.commit()
    return total_rows


# ── PDF Ingestion ─────────────────────────────────────────────────────────────

def _extract_table_text(tables: list) -> str:
    """Convert extracted PDF tables to searchable text."""
    if not tables:
        return ""

    parts = []
    for table in tables:
        if not table:
            continue
        for row in table:
            cells = [str(c).strip() if c else "" for c in row]
            parts.append(" | ".join(c for c in cells if c))

    return "\n".join(parts)


def _determine_category(file_path: Path) -> str:
    """Determine the budget category from the file path."""
    # TODO: Add handling for "space_force" / "spaceforce" and "marine_corps" /
    # "marines" paths — ORG_MAP has Space Force and Marine Corps codes but this
    # function would classify those files as "Other". Also consider using
    # ORG_MAP values as the canonical list to keep the two in sync.
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
    return "Other"


def ingest_pdf_file(conn: sqlite3.Connection, file_path: Path) -> int:
    """Ingest a single PDF file into the database."""
    category = _determine_category(file_path)
    relative_path = str(file_path.relative_to(DOCS_DIR))
    total_pages = 0

    try:
        with pdfplumber.open(str(file_path)) as pdf:
            batch = []
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                tables = page.extract_tables()
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

                # Batch insert every 100 pages
                if len(batch) >= 100:
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
        # TODO(bug): This INSERT provides 6 values but ingested_files has 8 columns,
        # so it will fail at runtime. Use explicit column names like the INSERT at
        # line ~639, and include file_modified (st_mtime) instead of datetime('now').
        conn.execute(
            "INSERT OR REPLACE INTO ingested_files VALUES (?,?,?,datetime('now'),?,?)",
            (relative_path, "pdf", file_path.stat().st_size, 0, f"error: {e}")
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
        print(f"ERROR: Documents directory not found: {docs_dir}")
        # TODO: Raise an exception (e.g., FileNotFoundError) instead of calling
        # sys.exit(1). The GUI calls build_database() in a background thread,
        # so sys.exit() would kill the entire application instead of reporting
        # the error gracefully through the progress callback.
        sys.exit(1)

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

        stat = pdf.stat()
        conn.execute(
            "INSERT OR REPLACE INTO ingested_files (file_path, file_type, file_size, file_modified, ingested_at, row_count, status) VALUES (?,?,?,?,datetime('now'),?,?)",
            (rel_path, "pdf", stat.st_size, stat.st_mtime, pages, "ok")
        )
        total_pdf_pages += pages

        # Commit every 10 files
        if processed % 10 == 0:
            conn.commit()

    conn.commit()
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

    build_database(args.docs, args.db, rebuild=args.rebuild)


if __name__ == "__main__":
    main()
