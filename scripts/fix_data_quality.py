"""
Database Data Quality Fix Script

Fixes data quality issues in an existing DoD budget database:
  0. Remove *a.xlsx alternate file duplicates
  1. Cross-file deduplication (remove prior-year column duplicates)
  2. Enhanced appropriation code backfill
  3. Budget type backfill for amendment/ogsi
  4. Empty organization name fill
  5. Appropriation titles reference table cleanup
  6. Handle rows with NULL appropriation code AND title
  7. Post-backfill dedup pass (catches dups from step 2/6 unifying codes)
  8. Rebuild FTS5 indexes and ANALYZE

Safe to run multiple times (idempotent). All steps check preconditions.

Usage:
    python scripts/fix_data_quality.py
    python scripts/fix_data_quality.py --db /path/to/db
    python scripts/fix_data_quality.py --dry-run
    python scripts/fix_data_quality.py --step 1
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

from utils.normalization import (
    APPROPRIATION_KEYWORDS as _ALL_KEYWORDS,
    TITLE_TO_CODE as _TITLE_TO_CODE,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("fix_data_quality")

# Appropriation code → budget type (superset of fix_budget_types.py mapping)
_APPROP_TO_BUDGET_TYPE: dict[str, str] = {
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
    "AMMO": "Procurement",
    "O&M": "O&M",
    "ER": "O&M",
    "DRUG": "O&M",
    "DHP": "O&M",
    "MILCON": "Construction",
    "FHSG": "Construction",
    "MILPERS": "MilPers",
    "RFUND": "Revolving",
}

# Known *a.xlsx alternate file patterns (exhibit stem + 'a')
_ALTERNATE_RE = re.compile(r"^(c1|m1|o1|p1|p1r|r1|rf1)a$", re.IGNORECASE)

# Source directory → organization mapping
_DIR_TO_ORG: dict[str, str] = {
    "army": "Army",
    "us_army": "Army",
    "navy": "Navy",
    "air_force": "Air Force",
    "airforce": "Air Force",
    "air force": "Air Force",
    "space_force": "Space Force",
    "spaceforce": "Space Force",
    "defense_wide": "Defense-Wide",
    "defense-wide": "Defense-Wide",
    "marine": "Marine Corps",
}


# ---------------------------------------------------------------------------
# Step functions
# ---------------------------------------------------------------------------

def step_0_remove_alternate_files(
    conn: sqlite3.Connection, dry_run: bool = False,
) -> int:
    """Remove rows ingested from *a.xlsx alternate Comptroller files.

    These are identical to the base files (r1.xlsx, p1.xlsx, etc.) and
    create exact-duplicate data.  The builder now excludes them, but
    existing databases may already contain the duplicate rows.
    """
    logger.info("Step 0: Removing *a.xlsx alternate file rows...")
    # Use LIKE with both / and \ separators for cross-platform
    patterns = []
    for stem in ("c1a", "m1a", "o1a", "p1a", "p1ra", "r1a", "rf1a"):
        patterns.append(f"%/{stem}.xlsx")
        patterns.append(f"%\\{stem}.xlsx")

    total = 0
    for pat in patterns:
        count = conn.execute(
            "SELECT COUNT(*) FROM budget_lines WHERE source_file LIKE ?",
            (pat,),
        ).fetchone()[0]
        if count:
            if not dry_run:
                conn.execute(
                    "DELETE FROM budget_lines WHERE source_file LIKE ?",
                    (pat,),
                )
            total += count

    if not dry_run and total:
        conn.commit()
        # Also clean ingested_files
        for pat in patterns:
            conn.execute(
                "DELETE FROM ingested_files WHERE file_path LIKE ?",
                (pat,),
            )
        conn.commit()

    logger.info("  %s %d *a.xlsx rows",
                "Would remove" if dry_run else "Removed", total)
    return total


def step_1_cross_file_dedup(
    conn: sqlite3.Connection, dry_run: bool = False,
) -> int:
    """Remove cross-file duplicate rows, keeping the most authoritative source.

    For rows identical across (fiscal_year, pe_number, line_item_title,
    organization_name, exhibit_type, amount_type, appropriation_code) but
    differing only in source_file, keep the row whose source submission
    year best matches the data fiscal_year.
    """
    logger.info("Step 1: Cross-file deduplication...")

    total_before = conn.execute(
        "SELECT COUNT(*) FROM budget_lines",
    ).fetchone()[0]

    # Count duplicates first
    dup_count_sql = """
        SELECT SUM(cnt - 1) FROM (
            SELECT COUNT(*) as cnt
            FROM budget_lines
            GROUP BY fiscal_year, pe_number, line_item_title,
                     organization_name, exhibit_type, amount_type,
                     appropriation_code
            HAVING cnt > 1
        )
    """
    dup_est = conn.execute(dup_count_sql).fetchone()[0] or 0

    if dup_est == 0:
        logger.info("  No cross-file duplicates found")
        return 0

    if dry_run:
        logger.info("  Would remove ~%d cross-file duplicates "
                     "(from %d total rows)", dup_est, total_before)
        return dup_est

    # Delete duplicates, keeping the row from the most relevant source.
    # Priority: source_file whose FY directory matches the row's fiscal_year,
    # then latest source_file (newer PB submissions may have corrections),
    # then lowest id (first ingested).
    deleted = conn.execute("""
        DELETE FROM budget_lines WHERE id NOT IN (
            SELECT id FROM (
                SELECT id,
                    ROW_NUMBER() OVER (
                        PARTITION BY fiscal_year, pe_number, line_item_title,
                                     organization_name, exhibit_type,
                                     amount_type, appropriation_code
                        ORDER BY
                            CASE WHEN source_file LIKE '%' || fiscal_year || '%'
                                 THEN 0 ELSE 1 END,
                            source_file DESC,
                            id ASC
                    ) AS rn
                FROM budget_lines
            )
            WHERE rn = 1
        )
    """).rowcount
    conn.commit()

    total_after = conn.execute(
        "SELECT COUNT(*) FROM budget_lines",
    ).fetchone()[0]

    # Rebuild FTS after mass deletion
    try:
        conn.execute(
            "INSERT INTO budget_lines_fts(budget_lines_fts) VALUES('rebuild')"
        )
        conn.commit()
    except Exception:
        logger.warning("  FTS rebuild skipped (table may not exist)")

    # Reconcile ingested_files row counts
    conn.execute("""
        UPDATE ingested_files SET row_count = (
            SELECT COUNT(*) FROM budget_lines
            WHERE budget_lines.source_file = ingested_files.file_path
        ) WHERE file_type = 'xlsx'
    """)
    conn.commit()

    logger.info("  Removed %d cross-file duplicates (%d -> %d)",
                deleted, total_before, total_after)
    return deleted


def _resolve_code(title: str) -> str | None:
    """Resolve an appropriation title to a code using 3-strategy approach."""
    stripped = title.strip()

    # Strategy 1: Exact title match (highest confidence)
    code = _TITLE_TO_CODE.get(stripped)
    if code:
        return code

    # Strategy 2: Leading numeric code
    parts = stripped.split(None, 1)
    if len(parts) >= 1 and parts[0].isdigit():
        return parts[0]

    # Strategy 3: Keyword matching
    lower = stripped.lower()
    for keyword, kw_code in _ALL_KEYWORDS.items():
        if keyword in lower:
            return kw_code

    return None


def step_2_backfill_appropriation_codes(
    conn: sqlite3.Connection, dry_run: bool = False,
) -> int:
    """Enhanced appropriation code backfill using exact titles + keywords."""
    logger.info("Step 2: Backfilling appropriation codes...")

    rows = conn.execute(
        "SELECT id, appropriation_title FROM budget_lines "
        "WHERE (appropriation_code IS NULL OR appropriation_code = '') "
        "AND appropriation_title IS NOT NULL AND appropriation_title != ''"
    ).fetchall()

    if not rows:
        logger.info("  No rows need appropriation code backfill")
        return 0

    updates: list[tuple[str, int]] = []
    for row_id, title in rows:
        code = _resolve_code(str(title))
        if code:
            updates.append((code, row_id))

    if dry_run:
        logger.info("  Would backfill %d of %d rows",
                     len(updates), len(rows))
        return len(updates)

    batch_size = 10_000
    for i in range(0, len(updates), batch_size):
        conn.executemany(
            "UPDATE budget_lines SET appropriation_code = ? WHERE id = ?",
            updates[i:i + batch_size],
        )
    conn.commit()

    remaining = conn.execute(
        "SELECT COUNT(*) FROM budget_lines "
        "WHERE appropriation_code IS NULL OR appropriation_code = ''"
    ).fetchone()[0]

    logger.info("  Backfilled %d of %d rows (%d still NULL)",
                len(updates), len(rows), remaining)
    return len(updates)


def step_3_backfill_budget_types(
    conn: sqlite3.Connection, dry_run: bool = False,
) -> int:
    """Backfill budget_type for rows where it's NULL but appropriation_code exists."""
    logger.info("Step 3: Backfilling budget types...")

    total_updated = 0
    for approp, bt in _APPROP_TO_BUDGET_TYPE.items():
        if dry_run:
            count = conn.execute(
                "SELECT COUNT(*) FROM budget_lines "
                "WHERE budget_type IS NULL AND appropriation_code = ?",
                (approp,),
            ).fetchone()[0]
            total_updated += count
        else:
            cur = conn.execute(
                "UPDATE budget_lines SET budget_type = ? "
                "WHERE budget_type IS NULL AND appropriation_code = ?",
                (bt, approp),
            )
            total_updated += cur.rowcount

    if not dry_run:
        conn.commit()

    remaining = conn.execute(
        "SELECT COUNT(*) FROM budget_lines WHERE budget_type IS NULL"
    ).fetchone()[0]

    logger.info("  %s %d rows; %d still NULL",
                "Would backfill" if dry_run else "Backfilled",
                total_updated, remaining)
    return total_updated


def step_4_fill_empty_org(
    conn: sqlite3.Connection, dry_run: bool = False,
) -> int:
    """Fill empty organization_name from source_file path."""
    logger.info("Step 4: Filling empty organization names...")

    rows = conn.execute(
        "SELECT id, source_file FROM budget_lines "
        "WHERE organization_name IS NULL OR organization_name = ''"
    ).fetchall()

    if not rows:
        logger.info("  No empty organization names found")
        return 0

    updates: list[tuple[str, int]] = []
    for row_id, source_file in rows:
        org: str | None = None
        if source_file:
            # Normalize separators for matching
            path_lower = source_file.replace("\\", "/").lower()
            for key, value in _DIR_TO_ORG.items():
                if key in path_lower:
                    org = value
                    break
        updates.append((org or "Unspecified", row_id))

    if dry_run:
        orgs = {}
        for org_val, _ in updates:
            orgs[org_val] = orgs.get(org_val, 0) + 1
        for org_val, cnt in sorted(orgs.items(), key=lambda x: -x[1]):
            logger.info("    %s: %d rows", org_val, cnt)
        logger.info("  Would fill %d empty org names", len(updates))
        return len(updates)

    conn.executemany(
        "UPDATE budget_lines SET organization_name = ? WHERE id = ?",
        updates,
    )
    conn.commit()
    logger.info("  Filled %d empty organization names", len(updates))
    return len(updates)


def step_5_clean_appropriation_titles(
    conn: sqlite3.Connection, dry_run: bool = False,
) -> int:
    """Remove footnote strings from appropriation_titles reference table."""
    logger.info("Step 5: Cleaning appropriation_titles reference table...")

    # Check if table exists
    exists = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master "
        "WHERE type='table' AND name='appropriation_titles'"
    ).fetchone()[0]
    if not exists:
        logger.info("  appropriation_titles table does not exist; skipping")
        return 0

    before_count = conn.execute(
        "SELECT COUNT(*) FROM appropriation_titles"
    ).fetchone()[0]

    # Find footnote entries (code starts with *, **, or is empty/whitespace)
    footnotes = conn.execute(
        "SELECT code FROM appropriation_titles "
        "WHERE code LIKE '*%' OR TRIM(code) = ''"
    ).fetchall()

    if dry_run:
        logger.info("  Would remove %d footnote entries (of %d total)",
                     len(footnotes), before_count)
        for row in footnotes[:5]:
            logger.info("    Example: %r", row[0])
        return len(footnotes)

    conn.execute(
        "DELETE FROM appropriation_titles "
        "WHERE code LIKE '*%' OR TRIM(code) = ''"
    )
    conn.commit()

    after_count = conn.execute(
        "SELECT COUNT(*) FROM appropriation_titles"
    ).fetchone()[0]
    logger.info("  Removed %d footnote entries (%d -> %d)",
                len(footnotes), before_count, after_count)
    return len(footnotes)


def step_6_handle_null_title_rows(
    conn: sqlite3.Connection, dry_run: bool = False,
) -> int:
    """Attempt to fill appropriation fields from account_title for orphaned rows."""
    logger.info("Step 6: Handling rows with NULL appropriation code AND title...")

    rows = conn.execute(
        "SELECT id, account_title, appropriation_title FROM budget_lines "
        "WHERE (appropriation_code IS NULL OR appropriation_code = '') "
        "AND account_title IS NOT NULL AND account_title != ''"
    ).fetchall()

    if not rows:
        logger.info("  No orphaned rows with account_title found")
        return 0

    updates: list[tuple[str, str, int]] = []
    for row_id, account_title, approp_title in rows:
        title = str(account_title).strip()
        code = _resolve_code(title)
        if code:
            # Use existing appropriation_title if available, else account_title
            use_title = approp_title if approp_title else title
            updates.append((code, use_title, row_id))

    if dry_run:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM budget_lines "
            "WHERE (appropriation_code IS NULL OR appropriation_code = '')"
        ).fetchone()[0]
        logger.info("  Would fill %d of %d rows from account_title "
                     "(%d total still NULL)",
                     len(updates), len(rows), remaining - len(updates))
        return len(updates)

    batch_size = 10_000
    for i in range(0, len(updates), batch_size):
        conn.executemany(
            "UPDATE budget_lines SET appropriation_code = ?, "
            "appropriation_title = COALESCE(appropriation_title, ?) "
            "WHERE id = ?",
            updates[i:i + batch_size],
        )
    conn.commit()

    remaining = conn.execute(
        "SELECT COUNT(*) FROM budget_lines "
        "WHERE appropriation_code IS NULL OR appropriation_code = ''"
    ).fetchone()[0]
    logger.info("  Filled %d rows from account_title; %d still NULL",
                len(updates), remaining)
    return len(updates)


def step_7_rebuild_fts_and_analyze(
    conn: sqlite3.Connection, dry_run: bool = False,
) -> int:
    """Rebuild FTS5 indexes and run ANALYZE for query planner optimization."""
    logger.info("Step 7: Rebuilding FTS indexes and running ANALYZE...")

    if dry_run:
        logger.info("  Would rebuild FTS indexes and run ANALYZE")
        return 0

    for tbl in ("budget_lines_fts", "pdf_pages_fts"):
        try:
            conn.execute(
                f"INSERT INTO {tbl}({tbl}) VALUES('rebuild')"
            )
            conn.commit()
            logger.info("  Rebuilt %s", tbl)
        except Exception as e:
            logger.warning("  Could not rebuild %s: %s", tbl, e)

    conn.execute("ANALYZE")
    conn.commit()
    logger.info("  ANALYZE complete")
    return 0


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

ALL_STEPS = [
    (0, "Remove *a.xlsx alternates", step_0_remove_alternate_files),
    (1, "Cross-file deduplication", step_1_cross_file_dedup),
    (2, "Appropriation code backfill", step_2_backfill_appropriation_codes),
    (3, "Budget type backfill", step_3_backfill_budget_types),
    (4, "Fill empty organization names", step_4_fill_empty_org),
    (5, "Clean appropriation_titles ref table", step_5_clean_appropriation_titles),
    (6, "Handle NULL title rows", step_6_handle_null_title_rows),
    # Step 7 re-runs dedup to catch duplicates created when backfill
    # steps unified previously-distinct appropriation_code values.
    (7, "Post-backfill dedup pass", step_1_cross_file_dedup),
    (8, "Rebuild FTS and ANALYZE", step_7_rebuild_fts_and_analyze),
]


def run_all(
    db_path: str,
    dry_run: bool = False,
    only_step: int | None = None,
) -> dict[int, int]:
    """Run all (or one) data quality fix steps."""
    db = Path(db_path)
    if not db.exists():
        logger.error("Database not found: %s", db)
        sys.exit(1)

    # Auto-backup before making changes
    if not dry_run:
        backup = db.with_suffix(
            f".sqlite.backup-{datetime.now():%Y%m%d-%H%M%S}"
        )
        logger.info("Creating backup: %s", backup.name)
        shutil.copy2(db, backup)
        logger.info("  Backup created (%d MB)",
                     backup.stat().st_size // (1024 * 1024))

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=OFF")

    total_before = conn.execute(
        "SELECT COUNT(*) FROM budget_lines"
    ).fetchone()[0]
    logger.info("Database: %s (%d budget_lines rows)", db.name, total_before)

    if dry_run:
        logger.info("=== DRY RUN — no changes will be made ===")

    results: dict[int, int] = {}
    t_total = time.time()

    for step_num, description, func in ALL_STEPS:
        if only_step is not None and step_num != only_step:
            continue

        t0 = time.time()
        logger.info("─" * 60)
        try:
            result = func(conn, dry_run=dry_run)
            results[step_num] = result
        except Exception:
            logger.exception("  Step %d FAILED", step_num)
            results[step_num] = -1
        elapsed = time.time() - t0
        logger.info("  Step %d done (%.1fs)", step_num, elapsed)

    total_after = conn.execute(
        "SELECT COUNT(*) FROM budget_lines"
    ).fetchone()[0]

    logger.info("─" * 60)
    logger.info("Summary: %d -> %d rows (%.1fs total)",
                total_before, total_after, time.time() - t_total)

    # Print final data quality snapshot
    for label, sql in [
        ("NULL appropriation_code",
         "SELECT COUNT(*) FROM budget_lines "
         "WHERE appropriation_code IS NULL OR appropriation_code = ''"),
        ("NULL budget_type",
         "SELECT COUNT(*) FROM budget_lines WHERE budget_type IS NULL"),
        ("Empty organization_name",
         "SELECT COUNT(*) FROM budget_lines "
         "WHERE organization_name IS NULL OR organization_name = ''"),
    ]:
        val = conn.execute(sql).fetchone()[0]
        logger.info("  %s: %d", label, val)

    conn.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fix data quality issues in the DoD budget database",
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("APP_DB_PATH", "dod_budget.sqlite"),
        help="Path to SQLite database (default: $APP_DB_PATH or dod_budget.sqlite)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying the database",
    )
    parser.add_argument(
        "--step",
        type=int,
        choices=[s[0] for s in ALL_STEPS],
        help="Run only the specified step",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    run_all(args.db, dry_run=args.dry_run, only_step=args.step)


if __name__ == "__main__":
    main()
