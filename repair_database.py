"""
Repair and upgrade an existing DoD budget database.

Fixes data quality issues identified during UI review (see docs/NOTICED_ISSUES.md):
  1. Creates missing reference tables (services_agencies, exhibit_types,
     appropriation_titles, budget_cycles)
  2. Seeds reference tables with canonical display names
  3. Normalizes organization_name values (ARMY->Army, AF->Air Force, etc.)
  4. Parses and backfills appropriation_code from account_title
  5. Adds missing performance indexes
  6. Runs reference table backfill from normalized data

Safe to run multiple times (idempotent). Works on existing databases.

Usage:
    python repair_database.py
    python repair_database.py --db /path/to/dod_budget.sqlite
    python repair_database.py --dry-run
"""

import argparse
import logging
import sqlite3
import sys
import time
from pathlib import Path

from utils.config import CORE_SUMMARY_TYPES
from utils.normalization import (
    APPROPRIATION_KEYWORDS as _APPROPRIATION_KEYWORDS,
    ORG_NORMALIZE as _ORG_NORMALIZE,
    TITLE_TO_CODE as _TITLE_TO_CODE,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("dod_budget.sqlite")


def step_1_create_reference_tables(conn: sqlite3.Connection) -> None:
    """Create missing reference tables if they don't exist."""
    logger.info("Step 1: Creating reference tables...")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS services_agencies (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            code        TEXT    NOT NULL UNIQUE,
            full_name   TEXT    NOT NULL,
            category    TEXT    NOT NULL DEFAULT 'Other'
        );
        CREATE TABLE IF NOT EXISTS exhibit_types (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            code         TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            exhibit_class TEXT NOT NULL DEFAULT 'other',
            description  TEXT
        );
        CREATE TABLE IF NOT EXISTS appropriation_titles (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            code  TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            color_of_money TEXT
        );
        CREATE TABLE IF NOT EXISTS budget_cycles (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            code  TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL
        );
    """)
    logger.info("  Reference tables ready")


def step_2_seed_reference_tables(conn: sqlite3.Connection) -> None:
    """Seed reference tables with canonical data (INSERT OR IGNORE)."""
    logger.info("Step 2: Seeding reference tables...")

    # Import EXHIBIT_TYPES from builder for canonical display names
    from pipeline.builder import EXHIBIT_TYPES

    seeded = 0
    for code, display_name in EXHIBIT_TYPES.items():
        exhibit_class = "summary" if code in CORE_SUMMARY_TYPES else "detail"
        cur = conn.execute(
            "INSERT OR IGNORE INTO exhibit_types (code, display_name, exhibit_class) VALUES (?, ?, ?)",
            (code, display_name, exhibit_class),
        )
        seeded += cur.rowcount

    # Budget cycles
    for code, label in [
        ("PB", "President's Budget"),
        ("ENACTED", "Enacted"),
        ("CR", "Continuing Resolution"),
        ("AMENDED", "Amended Budget"),
        ("SAR", "Selected Acquisition Report"),
    ]:
        cur = conn.execute(
            "INSERT OR IGNORE INTO budget_cycles (code, label) VALUES (?, ?)",
            (code, label),
        )
        seeded += cur.rowcount

    conn.commit()
    logger.info(f"  Seeded {seeded} reference rows")


def step_3_normalize_org_names(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    """Normalize inconsistent organization_name values."""
    logger.info("Step 3: Normalizing organization names...")

    # Build the CASE WHEN clause
    cases = []
    params = []
    in_values = []
    for old_val, new_val in _ORG_NORMALIZE.items():
        if old_val != new_val:  # Skip identity mappings
            cases.append("WHEN organization_name = ? THEN ?")
            params.extend([old_val, new_val])
            in_values.append(old_val)

    if not cases:
        logger.info("  No normalization rules to apply")
        return 0

    # Count affected rows first
    placeholders = ",".join("?" * len(in_values))
    count_row = conn.execute(
        f"SELECT COUNT(*) FROM budget_lines WHERE organization_name IN ({placeholders})",
        in_values,
    ).fetchone()
    affected = count_row[0] if count_row else 0

    if affected == 0:
        logger.info("  No rows need normalization")
        return 0

    if dry_run:
        logger.info(f"  Would normalize {affected:,} rows")
        return affected

    case_sql = " ".join(cases)
    sql = (
        f"UPDATE budget_lines SET organization_name = CASE {case_sql} "
        f"ELSE organization_name END "
        f"WHERE organization_name IN ({placeholders})"
    )
    conn.execute(sql, params + in_values)
    conn.commit()
    logger.info(f"  Normalized {affected:,} rows")
    return affected


def step_4_backfill_appropriation_codes(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    """Backfill appropriation_code from account_title for NULL rows."""
    logger.info("Step 4: Backfilling appropriation codes...")

    # Check how many rows need backfill
    count_row = conn.execute(
        "SELECT COUNT(*) FROM budget_lines "
        "WHERE (appropriation_code IS NULL OR appropriation_code = '') "
        "AND appropriation_title IS NOT NULL AND appropriation_title != ''"
    ).fetchone()
    need_backfill = count_row[0] if count_row else 0

    if need_backfill == 0:
        logger.info("  No rows need appropriation code backfill")
        return 0

    if dry_run:
        logger.info(f"  Would scan {need_backfill:,} rows for appropriation codes")
        return need_backfill

    # Build batch UPDATE using keyword matching
    # Process in chunks to avoid holding huge transactions
    BATCH_SIZE = 10000
    total_updated = 0

    rows = conn.execute(
        "SELECT id, appropriation_title FROM budget_lines "
        "WHERE (appropriation_code IS NULL OR appropriation_code = '') "
        "AND appropriation_title IS NOT NULL AND appropriation_title != ''"
    ).fetchall()

    updates: list[tuple[str, int]] = []
    for row in rows:
        row_id = row[0]
        title = str(row[1]).strip()
        lower = title.lower()
        # Strategy 1: Exact title match (highest confidence)
        code = _TITLE_TO_CODE.get(title)
        if code:
            updates.append((code, row_id))
            continue
        # Strategy 2: Leading numeric code
        parts = title.split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            updates.append((parts[0], row_id))
            continue
        # Strategy 3: Keyword-based
        for keyword, code in _APPROPRIATION_KEYWORDS.items():
            if keyword in lower:
                updates.append((code, row_id))
                break

    if updates:
        for i in range(0, len(updates), BATCH_SIZE):
            batch = updates[i : i + BATCH_SIZE]
            conn.executemany(
                "UPDATE budget_lines SET appropriation_code = ? WHERE id = ?",
                batch,
            )
        conn.commit()
        total_updated = len(updates)

    logger.info(f"  Backfilled {total_updated:,} of {need_backfill:,} rows")
    return total_updated


def step_5_add_indexes(conn: sqlite3.Connection) -> None:
    """Add missing performance indexes."""
    logger.info("Step 5: Adding performance indexes...")
    indexes = [
        ("idx_bl_fiscal_year", "budget_lines(fiscal_year)"),
        ("idx_bl_org", "budget_lines(organization_name)"),
        ("idx_bl_exhibit", "budget_lines(exhibit_type)"),
        ("idx_bl_pe", "budget_lines(pe_number)"),
        ("idx_bl_approp", "budget_lines(appropriation_code)"),
        ("idx_bl_approp_title", "budget_lines(appropriation_title)"),
        ("idx_bl_org_fy", "budget_lines(organization_name, fiscal_year)"),
        ("idx_bl_fy_org", "budget_lines(fiscal_year, organization_name)"),
    ]
    created = 0
    for name, definition in indexes:
        try:
            conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {definition}")
            created += 1
        except sqlite3.OperationalError as e:
            logger.debug(f"  Index {name} skipped: {e}")
    conn.commit()
    logger.info(f"  Ensured {created} indexes exist")


def step_6_backfill_reference_data(conn: sqlite3.Connection, dry_run: bool = False) -> dict:
    """Run reference table backfill from budget_lines data."""
    logger.info("Step 6: Backfilling reference tables from data...")
    from pipeline.backfill import backfill

    summary = backfill(conn, dry_run=dry_run)
    for table, count in summary.items():
        action = "Would insert" if dry_run else "Populated"
        logger.info(f"  {action} {count:,} rows into {table}")
    logger.info("  Reference table backfill complete")
    return summary


def step_7_backfill_source_fiscal_year(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    """Add source_fiscal_year column and backfill from source_file path."""
    logger.info("Step 7: Backfilling source_fiscal_year...")

    # Ensure column exists (always add, even on dry run, so we can count)
    existing = {r[1] for r in conn.execute("PRAGMA table_info(budget_lines)").fetchall()}
    if "source_fiscal_year" not in existing:
        conn.execute("ALTER TABLE budget_lines ADD COLUMN source_fiscal_year TEXT")
        conn.commit()
        logger.info("  Added source_fiscal_year column")

    # Count rows needing backfill
    count_row = conn.execute(
        "SELECT COUNT(*) FROM budget_lines WHERE source_fiscal_year IS NULL"
    ).fetchone()
    need_backfill = count_row[0] if count_row else 0

    if need_backfill == 0:
        logger.info("  No rows need source_fiscal_year backfill")
        return 0

    if dry_run:
        logger.info(f"  Would backfill {need_backfill:,} rows")
        return need_backfill

    # Extract FY from source_file path (e.g., "FY2025\PB\..." -> "2025")
    import re
    rows = conn.execute(
        "SELECT id, source_file FROM budget_lines WHERE source_fiscal_year IS NULL"
    ).fetchall()

    updates: list[tuple[str, int]] = []
    for row in rows:
        m = re.search(r"FY\s*(\d{4})", row[1] or "", re.IGNORECASE)
        if m:
            updates.append((m.group(1), row[0]))

    if updates:
        conn.executemany(
            "UPDATE budget_lines SET source_fiscal_year = ? WHERE id = ?",
            updates,
        )
        conn.commit()

    logger.info(f"  Backfilled {len(updates):,} of {need_backfill:,} rows")
    return len(updates)


def step_8_rebuild_fts(conn: sqlite3.Connection) -> None:
    """Rebuild FTS5 indexes to ensure consistency after data changes."""
    logger.info("Step 8: Rebuilding FTS5 indexes...")
    for table in ["budget_lines_fts", "pdf_pages_fts"]:
        try:
            conn.execute(f"INSERT INTO {table}({table}) VALUES('rebuild')")
            logger.info(f"  Rebuilt {table}")
        except sqlite3.OperationalError:
            logger.debug(f"  {table} does not exist, skipping")
    conn.execute("PRAGMA optimize")
    conn.commit()
    logger.info("  ✓ FTS5 rebuild complete")


def repair(db_path: Path, dry_run: bool = False) -> dict:
    """Run all repair steps on the database.

    Returns a summary dict with counts from each step.
    """
    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        sys.exit(1)

    logger.info(f"Repairing database: {db_path}")
    if dry_run:
        logger.info("DRY RUN -- no changes will be made")
    logger.info("")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")

    start = time.time()
    summary = {}

    try:
        step_1_create_reference_tables(conn)
        step_2_seed_reference_tables(conn)
        summary["org_normalized"] = step_3_normalize_org_names(conn, dry_run)
        summary["approp_backfilled"] = step_4_backfill_appropriation_codes(conn, dry_run)
        step_5_add_indexes(conn)
        summary["reference"] = step_6_backfill_reference_data(conn, dry_run)
        summary["source_fy_backfilled"] = step_7_backfill_source_fiscal_year(conn, dry_run)
        if not dry_run:
            step_8_rebuild_fts(conn)
    finally:
        conn.close()

    elapsed = time.time() - start
    logger.info("")
    logger.info(f"{'Dry run' if dry_run else 'Repair'} complete in {elapsed:.1f}s")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Repair and upgrade an existing DoD budget database."
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help="Path to the SQLite database (default: dod_budget.sqlite)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without modifying the database",
    )
    args = parser.parse_args(argv)

    repair(Path(args.db), dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
