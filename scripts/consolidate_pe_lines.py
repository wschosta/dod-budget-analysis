"""
Consolidate budget_lines into a normalized PE-centric schema.

Phase 1: PE-keyed rows only (~41K rows -> ~12K consolidated line_items).

Creates three new tables in the target database:
  - line_items:         One golden record per unique PE line
  - line_item_amounts:  Normalized EAV amounts (replaces 84 sparse columns)
  - budget_submissions: Raw per-submission archive (full audit trail)

Does NOT modify the original budget_lines table.

Usage:
    python scripts/consolidate_pe_lines.py [--db dod_budget_work.sqlite] [--dry-run]
"""

import argparse
import json
import logging
import re
import sqlite3
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AMOUNT_COL_RE = re.compile(r"^amount_fy(\d{4})_(\w+)$")
QUANTITY_COL_RE = re.compile(r"^quantity_fy(\d{4})(?:_(\w+))?$")

# Precedence: lower = better.  "actual" is the most authoritative.
AMOUNT_TYPE_PRECEDENCE = {
    "actual": 1,
    "enacted": 2,
    "total": 3,
    "request": 4,
    "supplemental": 5,
    "reconciliation": 6,
}

# Metadata columns to copy from the latest submission into line_items.
METADATA_COLS = [
    "account_title", "organization", "organization_name",
    "budget_activity", "budget_activity_title",
    "sub_activity", "sub_activity_title",
    "line_item_title", "classification",
    "cost_type", "cost_type_title", "add_non_add",
    "appropriation_code", "appropriation_title",
    "budget_type", "amount_type", "amount_unit", "currency_year",
]

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

DDL_LINE_ITEMS = """
CREATE TABLE IF NOT EXISTS line_items (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    exhibit_type          TEXT NOT NULL,
    account               TEXT,
    pe_number             TEXT NOT NULL,
    line_item             TEXT,

    account_title         TEXT,
    organization          TEXT,
    organization_name     TEXT,
    budget_activity       TEXT,
    budget_activity_title TEXT,
    sub_activity          TEXT,
    sub_activity_title    TEXT,
    line_item_title       TEXT,
    classification        TEXT,
    cost_type             TEXT,
    cost_type_title       TEXT,
    add_non_add           TEXT,
    appropriation_code    TEXT,
    appropriation_title   TEXT,
    budget_type           TEXT,
    amount_type           TEXT DEFAULT 'budget_authority',
    amount_unit           TEXT DEFAULT 'thousands',
    currency_year         TEXT,

    metadata_source_file  TEXT,
    metadata_fiscal_year  TEXT,
    latest_description    TEXT,

    first_seen_fy         TEXT,
    last_seen_fy          TEXT,
    submission_count      INTEGER DEFAULT 0,

    created_at            TEXT DEFAULT (datetime('now')),
    updated_at            TEXT DEFAULT (datetime('now'))
);
"""

DDL_LINE_ITEMS_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_li_key_pe
    ON line_items(exhibit_type, account, pe_number)
    WHERE line_item IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_li_key_pe_li
    ON line_items(exhibit_type, account, pe_number, line_item)
    WHERE line_item IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_li_pe          ON line_items(pe_number);
CREATE INDEX IF NOT EXISTS idx_li_exhibit     ON line_items(exhibit_type);
CREATE INDEX IF NOT EXISTS idx_li_org         ON line_items(organization_name);
CREATE INDEX IF NOT EXISTS idx_li_account     ON line_items(account);
CREATE INDEX IF NOT EXISTS idx_li_budget_type ON line_items(budget_type);
CREATE INDEX IF NOT EXISTS idx_li_approp      ON line_items(appropriation_code);
"""

DDL_LINE_ITEM_AMOUNTS = """
CREATE TABLE IF NOT EXISTS line_item_amounts (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    line_item_id          INTEGER NOT NULL REFERENCES line_items(id) ON DELETE CASCADE,
    target_fy             INTEGER NOT NULL,
    amount_type           TEXT NOT NULL,
    amount                REAL,
    quantity              REAL,
    source_submission_fy  TEXT,
    source_file           TEXT,
    precedence_rank       INTEGER,
    UNIQUE(line_item_id, target_fy, amount_type)
);
"""

DDL_LINE_ITEM_AMOUNTS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_lia_line_item  ON line_item_amounts(line_item_id);
CREATE INDEX IF NOT EXISTS idx_lia_target_fy  ON line_item_amounts(target_fy);
CREATE INDEX IF NOT EXISTS idx_lia_type       ON line_item_amounts(amount_type);
"""

DDL_BUDGET_SUBMISSIONS = """
CREATE TABLE IF NOT EXISTS budget_submissions (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    line_item_id          INTEGER NOT NULL REFERENCES line_items(id) ON DELETE CASCADE,
    fiscal_year           TEXT NOT NULL,
    source_file           TEXT NOT NULL,
    sheet_name            TEXT,
    raw_amounts           TEXT,
    raw_quantities        TEXT,
    extra_fields          TEXT,
    ingested_at           TEXT DEFAULT (datetime('now')),
    UNIQUE(line_item_id, fiscal_year, source_file)
);
"""

DDL_BUDGET_SUBMISSIONS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_bs_line_item   ON budget_submissions(line_item_id);
CREATE INDEX IF NOT EXISTS idx_bs_fy          ON budget_submissions(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_bs_source      ON budget_submissions(source_file);
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fy_sort_key(fy: str) -> int:
    """Convert fiscal_year string to sortable int.  '2026' -> 2026."""
    try:
        return int(re.sub(r"\D", "", str(fy)))
    except (ValueError, TypeError):
        return 0


def _discover_fy_columns(conn: sqlite3.Connection):
    """Return (amount_cols, quantity_cols) lists from budget_lines PRAGMA."""
    cols = conn.execute("PRAGMA table_info(budget_lines)").fetchall()
    amount_cols = []
    quantity_cols = []
    for c in cols:
        name = c[1]
        if AMOUNT_COL_RE.match(name):
            amount_cols.append(name)
        elif QUANTITY_COL_RE.match(name):
            quantity_cols.append(name)
    return sorted(amount_cols), sorted(quantity_cols)


def _parse_amount_col(col: str):
    """Parse 'amount_fy2024_actual' -> (2024, 'actual') or None."""
    m = AMOUNT_COL_RE.match(col)
    if m:
        return int(m.group(1)), m.group(2)
    return None


def _parse_quantity_col(col: str):
    """Parse 'quantity_fy2024' -> (2024, None) or 'quantity_fy2024_request' -> (2024, 'request')."""
    m = QUANTITY_COL_RE.match(col)
    if m:
        return int(m.group(1)), m.group(2)
    return None


def _get_latest_description(conn: sqlite3.Connection, pe_number: str) -> str | None:
    """Get the most recent narrative description for a PE number."""
    row = conn.execute(
        """SELECT description_text FROM pe_descriptions
           WHERE pe_number = ? AND description_text IS NOT NULL
           ORDER BY fiscal_year DESC LIMIT 1""",
        (pe_number,),
    ).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Main consolidation logic
# ---------------------------------------------------------------------------


def create_tables(conn: sqlite3.Connection):
    """Create the three new tables (idempotent)."""
    conn.executescript(DDL_LINE_ITEMS)
    conn.executescript(DDL_LINE_ITEMS_INDEXES)
    conn.executescript(DDL_LINE_ITEM_AMOUNTS)
    conn.executescript(DDL_LINE_ITEM_AMOUNTS_INDEXES)
    conn.executescript(DDL_BUDGET_SUBMISSIONS)
    conn.executescript(DDL_BUDGET_SUBMISSIONS_INDEXES)
    log.info("Created tables: line_items, line_item_amounts, budget_submissions")


def populate_line_items(conn: sqlite3.Connection) -> dict[tuple, int]:
    """Populate line_items from budget_lines PE groups.

    Returns a mapping of (exhibit_type, account, pe_number) -> line_items.id
    """
    log.info("Populating line_items...")

    # Find all unique PE groups with their latest submission info.
    groups = conn.execute("""
        SELECT
            exhibit_type,
            account,
            pe_number,
            MIN(fiscal_year) AS first_fy,
            MAX(fiscal_year) AS last_fy,
            COUNT(*) AS sub_count
        FROM budget_lines
        WHERE pe_number IS NOT NULL AND pe_number != ''
        GROUP BY exhibit_type, account, pe_number
        ORDER BY pe_number, exhibit_type
    """).fetchall()

    log.info("  Found %d unique PE groups", len(groups))

    key_to_id: dict[tuple, int] = {}
    batch = []

    for g in groups:
        exhibit_type, account, pe_number, first_fy, last_fy, sub_count = g

        # Get metadata from the latest submission for this group.
        meta_cols_sql = ", ".join(METADATA_COLS)
        latest = conn.execute(
            f"""SELECT source_file, fiscal_year, {meta_cols_sql}
                FROM budget_lines
                WHERE exhibit_type IS ? AND account IS ? AND pe_number = ?
                ORDER BY fiscal_year DESC
                LIMIT 1""",
            (exhibit_type, account, pe_number),
        ).fetchone()

        if not latest:
            continue

        source_file = latest[0]
        fiscal_year = latest[1]
        meta_values = latest[2:]

        # Get latest narrative description.
        description = _get_latest_description(conn, pe_number)

        batch.append((
            exhibit_type, account, pe_number, None,  # line_item NULL for PE rows
            *meta_values,
            source_file, fiscal_year, description,
            first_fy, last_fy, sub_count,
        ))

    # Bulk insert.
    meta_placeholders = ", ".join(["?"] * len(METADATA_COLS))
    conn.executemany(
        f"""INSERT OR IGNORE INTO line_items (
                exhibit_type, account, pe_number, line_item,
                {", ".join(METADATA_COLS)},
                metadata_source_file, metadata_fiscal_year, latest_description,
                first_seen_fy, last_seen_fy, submission_count
            ) VALUES (?, ?, ?, ?, {meta_placeholders}, ?, ?, ?, ?, ?, ?)""",
        batch,
    )
    conn.commit()

    # Build the key -> id mapping.
    rows = conn.execute(
        "SELECT id, exhibit_type, account, pe_number FROM line_items"
    ).fetchall()
    for r in rows:
        key_to_id[(r[1], r[2], r[3])] = r[0]

    log.info("  Inserted %d line_items rows", len(key_to_id))
    return key_to_id


def populate_submissions_and_amounts(
    conn: sqlite3.Connection,
    key_to_id: dict[tuple, int],
    amount_cols: list[str],
    quantity_cols: list[str],
):
    """Populate budget_submissions and line_item_amounts from budget_lines."""
    log.info("Populating budget_submissions and line_item_amounts...")

    # Fetch all PE rows from budget_lines.
    all_col_names = [c[1] for c in conn.execute("PRAGMA table_info(budget_lines)").fetchall()]
    rows = conn.execute(
        """SELECT * FROM budget_lines
           WHERE pe_number IS NOT NULL AND pe_number != ''"""
    ).fetchall()

    log.info("  Processing %d source rows", len(rows))

    sub_batch = []
    # Collect amounts keyed by (line_item_id, target_fy, amount_type) ->
    #   list of (amount, quantity, submission_fy, source_file)
    amounts_by_key: dict[tuple, list] = {}

    col_index = {name: i for i, name in enumerate(all_col_names)}

    for row in rows:
        exhibit_type = row[col_index["exhibit_type"]]
        account = row[col_index["account"]]
        pe_number = row[col_index["pe_number"]]
        key = (exhibit_type, account, pe_number)

        line_item_id = key_to_id.get(key)
        if line_item_id is None:
            continue

        fiscal_year = row[col_index["fiscal_year"]]
        source_file = row[col_index["source_file"]]
        sheet_name = row[col_index.get("sheet_name", -1)] if "sheet_name" in col_index else None
        extra_fields = row[col_index.get("extra_fields", -1)] if "extra_fields" in col_index else None

        # Build raw JSON blobs.
        raw_amounts = {}
        for ac in amount_cols:
            idx = col_index.get(ac)
            if idx is not None:
                val = row[idx]
                if val is not None:
                    raw_amounts[ac] = val

        raw_quantities = {}
        for qc in quantity_cols:
            idx = col_index.get(qc)
            if idx is not None:
                val = row[idx]
                if val is not None:
                    raw_quantities[qc] = val

        sub_batch.append((
            line_item_id, fiscal_year, source_file, sheet_name,
            json.dumps(raw_amounts) if raw_amounts else None,
            json.dumps(raw_quantities) if raw_quantities else None,
            extra_fields,
        ))

        # Decompose amount columns into normalized rows.
        for ac in amount_cols:
            idx = col_index.get(ac)
            if idx is None:
                continue
            val = row[idx]
            if val is None or val == 0:
                continue
            parsed = _parse_amount_col(ac)
            if not parsed:
                continue
            target_fy, amt_type = parsed
            akey = (line_item_id, target_fy, amt_type)
            if akey not in amounts_by_key:
                amounts_by_key[akey] = []
            amounts_by_key[akey].append((val, None, fiscal_year, source_file))

        # Decompose quantity columns — attach to matching amount type.
        for qc in quantity_cols:
            idx = col_index.get(qc)
            if idx is None:
                continue
            val = row[idx]
            if val is None or val == 0:
                continue
            parsed = _parse_quantity_col(qc)
            if not parsed:
                continue
            target_fy, qty_type = parsed
            # Map quantity type to an amount type: bare quantity -> "request" or best guess
            if qty_type is None:
                # Bare quantity_fy2024 — associate with the primary amount for that FY
                # Store separately; we'll merge later.
                amt_type = "quantity"
            else:
                amt_type = qty_type
            akey = (line_item_id, target_fy, f"qty_{amt_type}")
            if akey not in amounts_by_key:
                amounts_by_key[akey] = []
            amounts_by_key[akey].append((None, val, fiscal_year, source_file))

    # Insert budget_submissions.
    conn.executemany(
        """INSERT OR IGNORE INTO budget_submissions
           (line_item_id, fiscal_year, source_file, sheet_name,
            raw_amounts, raw_quantities, extra_fields)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        sub_batch,
    )
    conn.commit()
    log.info("  Inserted %d budget_submissions rows", len(sub_batch))

    # Resolve golden values and insert line_item_amounts.
    log.info("  Resolving golden amounts from %d unique (item, fy, type) keys...", len(amounts_by_key))
    amt_batch = []

    for (line_item_id, target_fy, amt_type), candidates in amounts_by_key.items():
        # Skip quantity-only entries for now — they'll be merged below.
        if amt_type.startswith("qty_"):
            continue

        # Pick winner: best precedence, then latest submission.
        prec = AMOUNT_TYPE_PRECEDENCE.get(amt_type, 99)
        # Among candidates for this exact (item, fy, type), pick latest submission.
        best = max(candidates, key=lambda c: _fy_sort_key(c[2]))
        amount_val, _, sub_fy, src_file = best

        # Try to attach a quantity from matching qty_ entries.
        qty_val = None
        for qty_suffix in [amt_type, "quantity"]:
            qty_key = (line_item_id, target_fy, f"qty_{qty_suffix}")
            if qty_key in amounts_by_key:
                qty_best = max(amounts_by_key[qty_key], key=lambda c: _fy_sort_key(c[2]))
                qty_val = qty_best[1]
                break

        amt_batch.append((
            line_item_id, target_fy, amt_type,
            amount_val, qty_val,
            sub_fy, src_file, prec,
        ))

    # Also insert standalone quantity rows that don't have a matching amount.
    for (line_item_id, target_fy, amt_type), candidates in amounts_by_key.items():
        if not amt_type.startswith("qty_"):
            continue
        # Check if we already have an amount row for this (item, fy).
        real_type = amt_type[4:]  # strip "qty_"
        has_amount = any(
            k == (line_item_id, target_fy, real_type)
            for k in amounts_by_key
            if not k[2].startswith("qty_")
        )
        if has_amount:
            continue  # Already attached above.
        best = max(candidates, key=lambda c: _fy_sort_key(c[2]))
        _, qty_val, sub_fy, src_file = best
        display_type = real_type if real_type != "quantity" else "request"
        amt_batch.append((
            line_item_id, target_fy, display_type,
            None, qty_val,
            sub_fy, src_file,
            AMOUNT_TYPE_PRECEDENCE.get(display_type, 99),
        ))

    conn.executemany(
        """INSERT OR IGNORE INTO line_item_amounts
           (line_item_id, target_fy, amount_type,
            amount, quantity,
            source_submission_fy, source_file, precedence_rank)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        amt_batch,
    )
    conn.commit()
    log.info("  Inserted %d line_item_amounts rows", len(amt_batch))


def create_compatibility_view(conn: sqlite3.Connection):
    """Create a budget_lines VIEW that emulates the old wide-column format.

    Only covers PE-keyed rows for now.  The old budget_lines table is NOT
    renamed — this view is created alongside it with a different name during
    the validation phase.
    """
    # Discover all distinct (target_fy, amount_type) pairs to generate CASE columns.
    pairs = conn.execute(
        """SELECT DISTINCT target_fy, amount_type
           FROM line_item_amounts
           WHERE amount_type NOT LIKE 'qty_%'
           ORDER BY target_fy, amount_type"""
    ).fetchall()

    case_clauses = []
    for target_fy, amt_type in pairs:
        col_name = f"amount_fy{target_fy}_{amt_type}"
        case_clauses.append(
            f"MAX(CASE WHEN a.target_fy = {target_fy} AND a.amount_type = '{amt_type}' "
            f"THEN a.amount END) AS [{col_name}]"
        )

    # Also generate quantity pivot columns.
    qty_pairs = conn.execute(
        """SELECT DISTINCT target_fy, amount_type
           FROM line_item_amounts
           WHERE quantity IS NOT NULL
           ORDER BY target_fy"""
    ).fetchall()

    qty_clauses = []
    seen_qty = set()
    for target_fy, amt_type in qty_pairs:
        qty_col = f"quantity_fy{target_fy}"
        if amt_type and amt_type != "request":
            qty_col = f"quantity_fy{target_fy}_{amt_type}"
        if qty_col not in seen_qty:
            seen_qty.add(qty_col)
            qty_clauses.append(
                f"MAX(CASE WHEN a.target_fy = {target_fy} THEN a.quantity END) AS [{qty_col}]"
            )

    all_pivots = ",\n    ".join(case_clauses + qty_clauses)

    view_sql = f"""
CREATE VIEW IF NOT EXISTS budget_lines_consolidated AS
SELECT
    li.id,
    li.metadata_source_file AS source_file,
    li.exhibit_type,
    NULL AS sheet_name,
    li.last_seen_fy AS fiscal_year,
    li.account,
    li.account_title,
    li.organization,
    li.organization_name,
    li.budget_activity,
    li.budget_activity_title,
    li.sub_activity,
    li.sub_activity_title,
    li.line_item,
    li.line_item_title,
    li.classification,
    li.cost_type,
    li.cost_type_title,
    li.add_non_add,
    li.pe_number,
    li.currency_year,
    li.appropriation_code,
    li.appropriation_title,
    li.amount_unit,
    li.budget_type,
    li.amount_type,
    NULL AS extra_fields,
    {all_pivots}
FROM line_items li
LEFT JOIN line_item_amounts a ON a.line_item_id = li.id
GROUP BY li.id;
"""
    conn.execute("DROP VIEW IF EXISTS budget_lines_consolidated")
    conn.executescript(view_sql)
    log.info("Created compatibility view: budget_lines_consolidated")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def consolidate(db_path: str, dry_run: bool = False) -> dict:
    """Run the full consolidation pipeline.

    Returns summary statistics.
    """
    log.info("Opening database: %s", db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")

    t0 = time.time()

    # Step 1: Discover FY columns in the source table.
    amount_cols, quantity_cols = _discover_fy_columns(conn)
    log.info("Discovered %d amount columns, %d quantity columns", len(amount_cols), len(quantity_cols))

    if dry_run:
        groups = conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT 1 FROM budget_lines
                WHERE pe_number IS NOT NULL AND pe_number != ''
                GROUP BY exhibit_type, account, pe_number
            )
        """).fetchone()[0]
        total = conn.execute(
            "SELECT COUNT(*) FROM budget_lines WHERE pe_number IS NOT NULL AND pe_number != ''"
        ).fetchone()[0]
        log.info("DRY RUN: Would consolidate %d rows into %d line_items", total, groups)
        conn.close()
        return {"line_items": groups, "source_rows": total, "dry_run": True}

    # Step 2: Create new tables.
    create_tables(conn)

    # Step 3: Populate line_items.
    key_to_id = populate_line_items(conn)

    # Step 4: Populate budget_submissions + line_item_amounts.
    populate_submissions_and_amounts(conn, key_to_id, amount_cols, quantity_cols)

    # Step 5: Create compatibility view.
    create_compatibility_view(conn)

    elapsed = time.time() - t0

    # Gather stats.
    stats = {
        "line_items": conn.execute("SELECT COUNT(*) FROM line_items").fetchone()[0],
        "line_item_amounts": conn.execute("SELECT COUNT(*) FROM line_item_amounts").fetchone()[0],
        "budget_submissions": conn.execute("SELECT COUNT(*) FROM budget_submissions").fetchone()[0],
        "elapsed_seconds": round(elapsed, 1),
    }

    conn.close()

    log.info("Consolidation complete in %.1fs", elapsed)
    log.info("  line_items:         %s", f"{stats['line_items']:,}")
    log.info("  line_item_amounts:  %s", f"{stats['line_item_amounts']:,}")
    log.info("  budget_submissions: %s", f"{stats['budget_submissions']:,}")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Consolidate PE budget lines")
    parser.add_argument(
        "--db",
        default="dod_budget_work.sqlite",
        help="Path to SQLite database (default: dod_budget_work.sqlite)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making changes",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        log.error("Database not found: %s", db_path)
        sys.exit(1)

    stats = consolidate(str(db_path), dry_run=args.dry_run)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
