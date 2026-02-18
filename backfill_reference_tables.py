"""
Backfill reference tables from existing flat budget_lines data (Step 2.B1-b).

Reads unique values from the budget_lines table and inserts them into:
  - services_agencies    (from organization_name)
  - exhibit_types        (from exhibit_type)
  - appropriation_titles (from account / account_title)

Uses INSERT OR IGNORE so seeded rows are preserved and there are no duplicates.
Run once after building the database, or any time new data is loaded.

Usage:
    python backfill_reference_tables.py
    python backfill_reference_tables.py --db /path/to/dod_budget.sqlite
    python backfill_reference_tables.py --dry-run
"""

import argparse
import sqlite3
import sys
from pathlib import Path


DEFAULT_DB_PATH = Path("dod_budget.sqlite")


def backfill(conn: sqlite3.Connection, dry_run: bool = False) -> dict:
    """Populate reference tables from flat budget_lines data.

    Returns a summary dict with counts of rows inserted per table.
    """
    summary: dict[str, int] = {
        "services_agencies": 0,
        "exhibit_types": 0,
        "appropriation_titles": 0,
    }

    # ── services_agencies ─────────────────────────────────────────────────────
    # Extract distinct organization_name values; skip nulls and blanks.
    orgs = conn.execute(
        "SELECT DISTINCT organization_name FROM budget_lines "
        "WHERE organization_name IS NOT NULL AND organization_name != '' "
        "ORDER BY organization_name"
    ).fetchall()

    for (org_name,) in orgs:
        code = org_name.strip()
        # Classify by known keywords
        if any(k in code.lower() for k in ["army", "usmc", "marine"]):
            category = "Military Department"
        elif any(k in code.lower() for k in ["navy", "naval"]):
            category = "Military Department"
        elif any(k in code.lower() for k in ["air force", "usaf", "space force"]):
            category = "Military Department"
        elif any(k in code.lower() for k in ["defense-wide", "dod", "osd", "darpa",
                                               "mda", "dia", "nsa", "nga", "nro",
                                               "disa", "socom"]):
            category = "Defense Agency"
        else:
            category = "Other"

        if not dry_run:
            conn.execute(
                "INSERT OR IGNORE INTO services_agencies (code, full_name, category) "
                "VALUES (?, ?, ?)",
                (code, code, category),
            )
        summary["services_agencies"] += 1

    # ── exhibit_types ─────────────────────────────────────────────────────────
    exhibit_class_map = {
        "p-1": "summary", "p-1r": "summary",
        "p-5": "procurement", "p-5a": "procurement",
        "p-40": "procurement", "p-21": "procurement",
        "r-1": "summary",
        "r-2": "rdte", "r-2a": "rdte", "r-3": "rdte", "r-4": "rdte",
        "o-1": "om",
        "m-1": "milpers",
        "c-1": "construction",
        "rf-1": "summary",
    }

    exhibits = conn.execute(
        "SELECT DISTINCT exhibit_type FROM budget_lines "
        "WHERE exhibit_type IS NOT NULL AND exhibit_type != '' "
        "ORDER BY exhibit_type"
    ).fetchall()

    for (exhibit_code,) in exhibits:
        code = exhibit_code.strip()
        normalized = code.lower()
        exhibit_class = exhibit_class_map.get(normalized, "other")
        display_name = code.upper()

        if not dry_run:
            conn.execute(
                "INSERT OR IGNORE INTO exhibit_types "
                "(code, display_name, exhibit_class) VALUES (?, ?, ?)",
                (code, display_name, exhibit_class),
            )
        summary["exhibit_types"] += 1

    # ── appropriation_titles ──────────────────────────────────────────────────
    # Use (account, account_title) pairs; account is the code, account_title is
    # the display name.  Fallback: use account as both when title is absent.
    approp_rows = conn.execute(
        "SELECT DISTINCT account, account_title FROM budget_lines "
        "WHERE account IS NOT NULL AND account != '' "
        "ORDER BY account"
    ).fetchall()

    for (account, account_title) in approp_rows:
        code = account.strip()
        title = (account_title or code).strip()

        if not dry_run:
            conn.execute(
                "INSERT OR IGNORE INTO appropriation_titles (code, title) "
                "VALUES (?, ?)",
                (code, title),
            )
        summary["appropriation_titles"] += 1

    if not dry_run:
        conn.commit()

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill reference tables from flat budget_lines data."
    )
    parser.add_argument(
        "--db",
        default=str(DEFAULT_DB_PATH),
        help="Path to the SQLite database (default: dod_budget.sqlite)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows to insert without modifying the database",
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Error: database not found at {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        summary = backfill(conn, dry_run=args.dry_run)
    except sqlite3.OperationalError as exc:
        # Reference tables may not exist yet (flat schema only)
        print(f"Warning: {exc}", file=sys.stderr)
        print(
            "Hint: run 'python schema_design.py' or 'python build_budget_db.py' "
            "first to create the normalized schema.",
            file=sys.stderr,
        )
        conn.close()
        return 1
    finally:
        conn.close()

    action = "Would insert" if args.dry_run else "Inserted"
    for table, count in summary.items():
        print(f"  {action} {count:,} rows into {table}")

    if args.dry_run:
        print("\nDry run complete — no changes made.")
    else:
        print("\nBackfill complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
