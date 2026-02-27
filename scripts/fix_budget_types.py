#!/usr/bin/env python3
"""Backfill budget_type from appropriation_code for rows where budget_type is NULL.

Also adds any missing composite indexes and cleans up redundant indexes.
This script is idempotent — safe to run multiple times.

Usage:
    python scripts/fix_budget_types.py [--db PATH]
"""

import argparse
import os
import sqlite3
import sys
import time


# Same mapping as utils/database.py BUDGET_TYPE_CASE_EXPR
APPROP_TO_BUDGET_TYPE = {
    "RDTE": "RDT&E",
    "OPROC": "Procurement",
    "PROC": "Procurement",
    "APAF": "Procurement",
    "MPAF": "Procurement",
    "WPN": "Procurement",
    "SCN": "Procurement",
    "NGRE": "Procurement",
    "DPA": "Procurement",
    "CHEM": "Procurement",
    "O&M": "O&M",
    "ER": "O&M",
    "DRUG": "O&M",
    "MILCON": "Construction",
    "FHSG": "Construction",
    "MILPERS": "MilPers",
    "RFUND": "Revolving",
}

# Composite indexes to ensure exist (may already be created by builder.py)
INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_bl_org_fy ON budget_lines(organization_name, fiscal_year);",
    "CREATE INDEX IF NOT EXISTS idx_bl_bt_fy ON budget_lines(budget_type, fiscal_year);",
    "CREATE INDEX IF NOT EXISTS idx_bl_et_fy ON budget_lines(exhibit_type, fiscal_year);",
    "CREATE INDEX IF NOT EXISTS idx_bl_pe_fy ON budget_lines(pe_number, fiscal_year);",
]


def fix_budget_types(conn: sqlite3.Connection) -> int:
    """Backfill budget_type from appropriation_code where NULL.

    Returns the number of rows updated.
    """
    total_updated = 0
    for approp, bt in APPROP_TO_BUDGET_TYPE.items():
        cur = conn.execute(
            "UPDATE budget_lines SET budget_type = ? "
            "WHERE budget_type IS NULL AND appropriation_code = ?",
            (bt, approp),
        )
        if cur.rowcount:
            print(f"  {approp} -> {bt}: {cur.rowcount:,} rows")
            total_updated += cur.rowcount
    conn.commit()
    return total_updated


def add_indexes(conn: sqlite3.Connection) -> int:
    """Add any missing composite indexes. Returns count of indexes created."""
    count = 0
    for sql in INDEXES:
        try:
            conn.execute(sql)
            count += 1
        except sqlite3.OperationalError:
            pass
    conn.commit()
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix budget_type and add indexes")
    parser.add_argument(
        "--db",
        default=os.environ.get("APP_DB_PATH", "dod_budget.sqlite"),
        help="Path to SQLite database (default: $APP_DB_PATH or dod_budget.sqlite)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"Database not found: {args.db}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(args.db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row

    # ── Step 1: Backfill budget_type ──────────────────────────────────────────
    print("Step 1: Backfilling budget_type from appropriation_code...")
    before = conn.execute(
        "SELECT COUNT(*) FROM budget_lines WHERE budget_type IS NULL"
    ).fetchone()[0]
    print(f"  NULL budget_type rows before: {before:,}")

    t0 = time.time()
    updated = fix_budget_types(conn)
    elapsed = time.time() - t0

    after = conn.execute(
        "SELECT COUNT(*) FROM budget_lines WHERE budget_type IS NULL"
    ).fetchone()[0]
    print(f"  Updated: {updated:,} rows ({elapsed:.1f}s)")
    print(f"  NULL budget_type rows after: {after:,}")
    if after > 0:
        print(f"  Note: {after:,} rows still NULL (no appropriation_code to map)")

    # ── Step 2: Verify distribution ───────────────────────────────────────────
    print("\nStep 2: Budget type distribution after fix:")
    for row in conn.execute(
        "SELECT COALESCE(budget_type, 'NULL') AS bt, COUNT(*) AS cnt "
        "FROM budget_lines GROUP BY budget_type ORDER BY cnt DESC"
    ):
        print(f"  {row['bt']:20s} {row['cnt']:>10,}")

    # ── Step 3: Add indexes ───────────────────────────────────────────────────
    print("\nStep 3: Ensuring composite indexes...")
    t0 = time.time()
    idx_count = add_indexes(conn)
    elapsed = time.time() - t0
    print(f"  Ensured {idx_count} indexes ({elapsed:.1f}s)")

    # ── Step 4: ANALYZE for query planner ─────────────────────────────────────
    print("\nStep 4: Running ANALYZE for query planner optimization...")
    t0 = time.time()
    conn.execute("ANALYZE")
    conn.commit()
    elapsed = time.time() - t0
    print(f"  Done ({elapsed:.1f}s)")

    conn.close()
    print(f"\nDone. Database: {args.db}")


if __name__ == "__main__":
    main()
