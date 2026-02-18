"""
DoD Budget Database Validation Suite — Step 1.B6

Runs automated quality checks against the SQLite budget database and
produces a summary report flagging anomalies.

Usage:
    python validate_budget_db.py                     # Default database
    python validate_budget_db.py --db mydb.sqlite    # Custom path
    python validate_budget_db.py --verbose            # Show all issue details
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# Shared utilities: Import from utils package for consistency across codebase
from utils import get_connection

DEFAULT_DB_PATH = Path("dod_budget.sqlite")

# Known exhibit types (from build_budget_db.py)
KNOWN_EXHIBIT_TYPES = {"m1", "o1", "p1", "p1r", "r1", "rf1", "c1"}

# Known organizations (from build_budget_db.py ORG_MAP values)
KNOWN_ORGS = {"Army", "Navy", "Air Force", "Space Force",
              "Defense-Wide", "Marine Corps", "Joint Staff"}

# Amount columns in the budget_lines table
AMOUNT_COLUMNS = [
    "amount_fy2024_actual",
    "amount_fy2025_enacted",
    "amount_fy2025_supplemental",
    "amount_fy2025_total",
    "amount_fy2026_request",
    "amount_fy2026_reconciliation",
    "amount_fy2026_total",
]


# ── Individual checks ────────────────────────────────────────────────────────

def check_missing_years(conn: sqlite3.Connection) -> list[dict]:
    """Check for services that are missing expected fiscal years."""
    issues = []
    rows = conn.execute("""
        SELECT organization_name, GROUP_CONCAT(DISTINCT fiscal_year) AS years,
               COUNT(DISTINCT fiscal_year) AS year_count
        FROM budget_lines
        WHERE organization_name IS NOT NULL AND organization_name != ''
        GROUP BY organization_name
    """).fetchall()

    if not rows:
        return [{"check": "missing_years", "severity": "warning",
                 "detail": "No budget line data found in database"}]

    # Collect all fiscal years present across any service
    all_years: set[str] = set()
    org_years: dict[str, set[str]] = {}
    for r in rows:
        years = set(r["years"].split(",")) if r["years"] else set()
        org_years[r["organization_name"]] = years
        all_years.update(years)

    for org, years in org_years.items():
        missing = all_years - years
        if missing:
            issues.append({
                "check": "missing_years",
                "severity": "warning",
                "detail": f"{org} is missing fiscal years: {', '.join(sorted(missing))}",
                "organization": org,
                "missing": sorted(missing),
            })

    return issues


def check_duplicates(conn: sqlite3.Connection) -> list[dict]:
    """Find rows with identical key tuples that suggest duplicate ingestion."""
    issues = []
    rows = conn.execute("""
        SELECT source_file, exhibit_type, account, line_item, fiscal_year,
               COUNT(*) AS cnt
        FROM budget_lines
        GROUP BY source_file, exhibit_type, account, line_item, fiscal_year
        HAVING cnt > 1
        ORDER BY cnt DESC
        LIMIT 50
    """).fetchall()

    for r in rows:
        issues.append({
            "check": "duplicates",
            "severity": "error",
            "detail": (f"{r['cnt']} duplicate rows: "
                       f"{r['source_file']} / {r['exhibit_type']} / "
                       f"account={r['account']} / line_item={r['line_item']} / "
                       f"fy={r['fiscal_year']}"),
            "count": r["cnt"],
            "source_file": r["source_file"],
        })

    return issues


def check_zero_amounts(conn: sqlite3.Connection) -> list[dict]:
    """Find line items where every amount column is NULL or zero."""
    issues = []
    null_checks = " AND ".join(
        f"(COALESCE({col}, 0) = 0)" for col in AMOUNT_COLUMNS
    )
    rows = conn.execute(f"""
        SELECT source_file, exhibit_type, account, account_title,
               organization_name, fiscal_year
        FROM budget_lines
        WHERE {null_checks}
        LIMIT 100
    """).fetchall()

    if rows:
        total = conn.execute(f"""
            SELECT COUNT(*) AS cnt FROM budget_lines WHERE {null_checks}
        """).fetchone()["cnt"]

        issues.append({
            "check": "zero_amounts",
            "severity": "warning",
            "detail": f"{total} line items have all amount columns as NULL or zero",
            "total": total,
            "samples": [
                f"{r['source_file']} / {r['exhibit_type']} / "
                f"{r['account_title'] or r['account']} ({r['organization_name']})"
                for r in rows[:10]
            ],
        })

    return issues


def check_column_alignment(conn: sqlite3.Connection) -> list[dict]:
    """Find rows where account is populated but organization is missing."""
    issues = []
    rows = conn.execute("""
        SELECT source_file, exhibit_type, account, account_title,
               fiscal_year, COUNT(*) AS cnt
        FROM budget_lines
        WHERE account IS NOT NULL AND account != ''
          AND (organization IS NULL OR organization = '')
        GROUP BY source_file, exhibit_type
        ORDER BY cnt DESC
        LIMIT 20
    """).fetchall()

    for r in rows:
        issues.append({
            "check": "column_alignment",
            "severity": "warning",
            "detail": (f"{r['cnt']} rows with account but no organization: "
                       f"{r['source_file']} ({r['exhibit_type']})"),
            "source_file": r["source_file"],
            "count": r["cnt"],
        })

    return issues


def check_unknown_exhibits(conn: sqlite3.Connection) -> list[dict]:
    """Find exhibit_type values not in the known set."""
    issues = []
    rows = conn.execute("""
        SELECT exhibit_type, COUNT(*) AS cnt
        FROM budget_lines
        WHERE exhibit_type IS NOT NULL
        GROUP BY exhibit_type
        ORDER BY cnt DESC
    """).fetchall()

    for r in rows:
        if r["exhibit_type"] not in KNOWN_EXHIBIT_TYPES:
            issues.append({
                "check": "unknown_exhibits",
                "severity": "info",
                "detail": (f"Unknown exhibit type '{r['exhibit_type']}' "
                           f"({r['cnt']} rows)"),
                "exhibit_type": r["exhibit_type"],
                "count": r["cnt"],
            })

    return issues


def check_ingestion_errors(conn: sqlite3.Connection) -> list[dict]:
    """Find files that were ingested with errors."""
    issues = []
    rows = conn.execute("""
        SELECT file_path, file_type, status
        FROM ingested_files
        WHERE status != 'ok'
        ORDER BY file_path
    """).fetchall()

    for r in rows:
        issues.append({
            "check": "ingestion_errors",
            "severity": "error",
            "detail": f"Ingestion error for {r['file_path']}: {r['status']}",
            "file_path": r["file_path"],
        })

    return issues


def check_empty_files(conn: sqlite3.Connection) -> list[dict]:
    """Find ingested files that produced zero rows/pages."""
    issues = []
    rows = conn.execute("""
        SELECT file_path, file_type
        FROM ingested_files
        WHERE status = 'ok' AND (row_count IS NULL OR row_count = 0)
        ORDER BY file_path
    """).fetchall()

    for r in rows:
        issues.append({
            "check": "empty_files",
            "severity": "warning",
            "detail": f"{r['file_type'].upper()} file produced 0 rows: {r['file_path']}",
            "file_path": r["file_path"],
        })

    return issues


# ── Report generation ────────────────────────────────────────────────────────

ALL_CHECKS = [
    ("Missing Fiscal Years", check_missing_years),
    ("Duplicate Rows", check_duplicates),
    ("Zero-Amount Line Items", check_zero_amounts),
    ("Column Alignment", check_column_alignment),
    ("Unknown Exhibit Types", check_unknown_exhibits),
    ("Ingestion Errors", check_ingestion_errors),
    ("Empty Files", check_empty_files),
]


def generate_report(conn: sqlite3.Connection, verbose: bool = False) -> int:
    """Run all checks and print a summary report. Returns total issue count."""
    print("=" * 65)
    print("  DoD BUDGET DATABASE VALIDATION REPORT")
    print("=" * 65)

    # Database overview
    total_lines = conn.execute("SELECT COUNT(*) AS c FROM budget_lines").fetchone()["c"]
    total_pages = conn.execute("SELECT COUNT(*) AS c FROM pdf_pages").fetchone()["c"]
    total_files = conn.execute("SELECT COUNT(*) AS c FROM ingested_files").fetchone()["c"]
    print(f"\n  Database overview:")
    print(f"    Budget lines:   {total_lines:,}")
    print(f"    PDF pages:      {total_pages:,}")
    print(f"    Files ingested: {total_files:,}")

    # Run checks
    total_issues = 0
    severity_counts = {"error": 0, "warning": 0, "info": 0}

    for check_name, check_fn in ALL_CHECKS:
        issues = check_fn(conn)
        count = len(issues)
        total_issues += count

        if count == 0:
            status = "PASS"
        else:
            for issue in issues:
                severity_counts[issue["severity"]] += 1
            severities = set(i["severity"] for i in issues)
            status = "FAIL" if "error" in severities else "WARN"

        print(f"\n  [{status:>4}] {check_name} — {count} issue(s)")

        if verbose and issues:
            for issue in issues[:20]:
                sev = issue["severity"].upper()
                print(f"         [{sev}] {issue['detail']}")
                if "samples" in issue:
                    for sample in issue["samples"][:5]:
                        print(f"           - {sample}")
            if count > 20:
                print(f"         ... and {count - 20} more")

    # Summary
    print(f"\n{'=' * 65}")
    if total_issues == 0:
        print("  RESULT: ALL CHECKS PASSED")
    else:
        print(f"  RESULT: {total_issues} issue(s) found")
        print(f"    Errors:   {severity_counts['error']}")
        print(f"    Warnings: {severity_counts['warning']}")
        print(f"    Info:     {severity_counts['info']}")
    print(f"{'=' * 65}")

    return total_issues


def main():
    """Parse CLI arguments, run all validation checks, and exit with status code."""
    parser = argparse.ArgumentParser(
        description="Validate the DoD budget database for data quality issues")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                        help=f"Database path (default: {DEFAULT_DB_PATH})")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show details for each issue found")
    args = parser.parse_args()

    conn = get_connection(args.db)
    issue_count = generate_report(conn, verbose=args.verbose)
    conn.close()

    sys.exit(1 if issue_count > 0 else 0)


if __name__ == "__main__":
    main()
