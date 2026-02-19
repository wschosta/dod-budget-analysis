"""
DoD Budget Database Validation Suite — Step 1.B6

Runs automated quality checks against the SQLite budget database and
produces a summary report flagging anomalies.

Usage:
    python validate_budget_db.py                     # Default database
    python validate_budget_db.py --db mydb.sqlite    # Custom path
    python validate_budget_db.py --verbose            # Show all issue details

---
TODOs for this file
---

"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

# Shared utilities: Import from utils package for consistency across codebase
from utils import get_connection
from schema_design import check_database_integrity

DEFAULT_DB_PATH = Path("dod_budget.sqlite")

# Known exhibit types — imported from exhibit_catalog so it stays in sync
# with the canonical catalog (Step 1.B1-g-validator).
from exhibit_catalog import list_all_exhibit_types  # noqa: E402
KNOWN_EXHIBIT_TYPES = set(list_all_exhibit_types())

# Known organizations — imported from build_budget_db.py so it stays in sync
# with ORG_MAP (Step 1.B4-b).
from build_budget_db import ORG_MAP as _ORG_MAP  # noqa: E402
KNOWN_ORGS = set(_ORG_MAP.values())

# Amount columns in the budget_lines table — queried dynamically from the
# DB schema (Step 1.B2-a) so the validator automatically adapts when new
# fiscal year columns are added without requiring code changes here.
def _get_amount_columns(conn: sqlite3.Connection) -> list[str]:
    """Return all amount_fy* columns present in budget_lines schema."""
    cols = conn.execute("PRAGMA table_info(budget_lines)").fetchall()
    return [c[1] for c in cols if c[1].startswith("amount_fy")]


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
    amount_cols = _get_amount_columns(conn)
    if not amount_cols:
        return issues
    null_checks = " AND ".join(
        f"(COALESCE({col}, 0) = 0)" for col in amount_cols
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


def check_unit_consistency(conn: sqlite3.Connection) -> list[dict]:
    """Flag budget lines where amount_unit is not 'thousands' (Step 1.B3-f).

    After normalisation all stored amounts should be in thousands of dollars.
    Rows where amount_unit differs indicate a missed unit conversion and the
    stored values may be off by a factor of 1,000.
    """
    issues = []
    try:
        rows = conn.execute("""
            SELECT exhibit_type, source_file, amount_unit, COUNT(*) AS n
            FROM budget_lines
            WHERE amount_unit IS NOT NULL AND amount_unit != 'thousands'
            GROUP BY exhibit_type, source_file, amount_unit
            ORDER BY n DESC
        """).fetchall()
    except Exception:
        # Column may not exist in pre-1.B3-b databases
        return []

    for r in rows:
        issues.append({
            "check": "unit_consistency",
            "severity": "warning",
            "detail": (
                f"{r['exhibit_type']} exhibit '{r['source_file']}' has "
                f"amount_unit='{r['amount_unit']}' ({r['n']} rows) — "
                "unit normalisation may not have been applied"
            ),
            "file_path": r["source_file"],
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


# VALDB-001: PE number format validation
_PE_PATTERN = re.compile(r"^[0-9]{7}[A-Z]{1,2}$")


def check_pe_number_format(conn: sqlite3.Connection) -> list[dict]:
    """Flag populated pe_number values that do not match the DoD PE format.

    Valid PE numbers follow the pattern: 7 digits followed by 1-2 uppercase
    letters (e.g., 0602702E, 0305116BB).  Rows where pe_number is set but
    does not match are likely parsing artefacts or data entry errors.
    """
    issues = []
    try:
        rows = conn.execute("""
            SELECT pe_number, source_file, exhibit_type, COUNT(*) AS cnt
            FROM budget_lines
            WHERE pe_number IS NOT NULL AND pe_number != ''
            GROUP BY pe_number, source_file, exhibit_type
            ORDER BY cnt DESC
        """).fetchall()
    except Exception:
        return []

    malformed = [r for r in rows if not _PE_PATTERN.match(str(r["pe_number"]))]
    if malformed:
        total_rows = sum(r["cnt"] for r in malformed)
        issues.append({
            "check": "pe_number_format",
            "severity": "warning",
            "detail": (
                f"{total_rows} row(s) have malformed PE numbers "
                f"(expected 7 digits + 1-2 uppercase letters)"
            ),
            "total": total_rows,
            "samples": [
                f"'{r['pe_number']}' in {r['source_file']} ({r['cnt']} rows)"
                for r in malformed[:10]
            ],
        })

    return issues


# VALDB-002: Negative amount detection
def check_negative_amounts(conn: sqlite3.Connection) -> list[dict]:
    """Surface line items with negative dollar amounts for review.

    Negative amounts can be legitimate (e.g., rescissions, reductions), but
    are unusual enough that they warrant explicit review.  Flagged as *info*
    rather than warning so they don't inflate the warning count.
    """
    issues = []
    amount_cols = _get_amount_columns(conn)
    if not amount_cols:
        return issues

    for col in amount_cols:
        try:
            rows = conn.execute(f"""
                SELECT source_file, exhibit_type, account_title,
                       organization_name, fiscal_year, {col}
                FROM budget_lines
                WHERE {col} < 0
                ORDER BY {col}
                LIMIT 50
            """).fetchall()
        except Exception:
            continue

        if rows:
            total = conn.execute(
                f"SELECT COUNT(*) AS cnt FROM budget_lines WHERE {col} < 0"
            ).fetchone()["cnt"]
            issues.append({
                "check": "negative_amounts",
                "severity": "info",
                "detail": (
                    f"{total} row(s) have negative {col} "
                    "(may be valid rescissions — review recommended)"
                ),
                "column": col,
                "total": total,
                "samples": [
                    f"{r['source_file']} / "
                    f"{r['account_title'] or '?'} ({r['organization_name']}): "
                    f"{r[col]:,.0f}"
                    for r in rows[:5]
                ],
            })

    return issues


# ── Report generation ────────────────────────────────────────────────────────

def check_integrity(conn: sqlite3.Connection) -> list[dict]:
    """Run PRAGMA integrity_check and FTS sync verification (SCHEMA-003)."""
    result = check_database_integrity(conn)
    issues = []
    if not result["integrity_ok"]:
        issues.append({
            "check": "integrity_check",
            "severity": "error",
            "detail": "; ".join(result["details"]),
        })
    if not result["fts_sync_ok"]:
        issues.append({
            "check": "fts_sync",
            "severity": "error",
            "detail": "; ".join(d for d in result["details"] if "fts_sync" in d),
        })
    return issues


ALL_CHECKS = [
    ("Missing Fiscal Years", check_missing_years),
    ("Duplicate Rows", check_duplicates),
    ("Zero-Amount Line Items", check_zero_amounts),
    ("Column Alignment", check_column_alignment),
    ("Unknown Exhibit Types", check_unknown_exhibits),
    ("Ingestion Errors", check_ingestion_errors),
    ("Empty Files", check_empty_files),
    ("Unit Consistency", check_unit_consistency),      # Step 1.B3-f
    ("PE Number Format", check_pe_number_format),      # VALDB-001
    ("Negative Amounts", check_negative_amounts),      # VALDB-002
    ("Database Integrity", check_integrity),             # SCHEMA-003
]


def generate_json_report(conn: sqlite3.Connection) -> dict:
    """Run all checks and return results as a JSON-serialisable dict.

    Intended for machine-readable output via ``--json``.  The returned dict
    contains a ``checks`` list (one entry per check) plus top-level counts.
    """
    total_lines = conn.execute("SELECT COUNT(*) AS c FROM budget_lines").fetchone()["c"]
    total_pages = conn.execute("SELECT COUNT(*) AS c FROM pdf_pages").fetchone()["c"]
    total_files = conn.execute("SELECT COUNT(*) AS c FROM ingested_files").fetchone()["c"]

    checks_output = []
    total_issues = 0
    severity_counts = {"error": 0, "warning": 0, "info": 0}

    for check_name, check_fn in ALL_CHECKS:
        issues = check_fn(conn)
        count = len(issues)
        total_issues += count
        for issue in issues:
            severity_counts[issue["severity"]] += 1
        severities = list({i["severity"] for i in issues})
        status = "pass"
        if issues:
            status = "fail" if "error" in severities else "warn"
        checks_output.append({
            "name": check_name,
            "status": status,
            "issue_count": count,
            "issues": issues,
        })

    return {
        "database": {
            "budget_lines": total_lines,
            "pdf_pages": total_pages,
            "files_ingested": total_files,
        },
        "summary": {
            "total_issues": total_issues,
            "errors": severity_counts["error"],
            "warnings": severity_counts["warning"],
            "info": severity_counts["info"],
        },
        "checks": checks_output,
    }


def generate_report(conn: sqlite3.Connection, verbose: bool = False) -> int:
    """Run all checks and print a summary report. Returns total issue count."""
    print("=" * 65)
    print("  DoD BUDGET DATABASE VALIDATION REPORT")
    print("=" * 65)

    # Database overview
    total_lines = conn.execute("SELECT COUNT(*) AS c FROM budget_lines").fetchone()["c"]
    total_pages = conn.execute("SELECT COUNT(*) AS c FROM pdf_pages").fetchone()["c"]
    total_files = conn.execute("SELECT COUNT(*) AS c FROM ingested_files").fetchone()["c"]
    print("\n  Database overview:")
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
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON (VALDB-003)")
    args = parser.parse_args()

    conn = get_connection(args.db)

    if args.json:
        report = generate_json_report(conn)
        print(json.dumps(report, indent=2))
        issue_count = report["summary"]["total_issues"]
    else:
        issue_count = generate_report(conn, verbose=args.verbose)

    conn.close()
    sys.exit(1 if issue_count > 0 else 0)


if __name__ == "__main__":
    main()
