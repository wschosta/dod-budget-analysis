"""
Budget Data Validation Suite — Step 1.B6

Automated checks that run against a populated dod_budget.sqlite database and
flag anomalies.  Designed to run after every build_budget_db.py invocation
(or as a standalone QA step).

Usage:
    python validate_budget_data.py                      # Validate default DB
    python validate_budget_data.py --db path/to/db      # Custom DB path
    python validate_budget_data.py --strict              # Non-zero exit on warnings
    python validate_budget_data.py --json                # Output as JSON

Status: Core validation checks implemented (1.B6-b, 1.B6-c, 1.B6-e, 1.B6-f, 1.B6-g)

Remaining Phase 1 enhancements:
    1.B6-a: Check for missing fiscal-year coverage per service.
    1.B6-d: Detect column misalignment (text in numeric columns or vice versa).
    1.B6-h: Wire validation into build_budget_db.py post-build step (auto-validate after build)
"""

import json
import sqlite3
import sys
from pathlib import Path

# Shared utilities: Import from utils package for consistency across codebase
from utils import get_connection

DEFAULT_DB_PATH = Path("dod_budget.sqlite")

AMOUNT_COLUMNS = [
    "amount_fy2024_actual",
    "amount_fy2025_enacted",
    "amount_fy2025_supplemental",
    "amount_fy2025_total",
    "amount_fy2026_request",
    "amount_fy2026_reconciliation",
    "amount_fy2026_total",
]

KNOWN_EXHIBIT_TYPES = {"m1", "o1", "p1", "p1r", "r1", "rf1", "c1"}


# ── Individual checks ────────────────────────────────────────────────────────

def check_database_stats(conn: sqlite3.Connection) -> dict:
    """Basic stats — not a validation, but useful context for the report."""
    budget_count = conn.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0]
    pdf_count = conn.execute("SELECT COUNT(*) FROM pdf_pages").fetchone()[0]
    file_count = conn.execute("SELECT COUNT(*) FROM ingested_files").fetchone()[0]

    if budget_count == 0 and pdf_count == 0:
        return {
            "name": "database_stats",
            "status": "fail",
            "message": "Database is empty — no data to validate",
            "details": {"budget_lines": 0, "pdf_pages": 0, "ingested_files": 0},
        }
    return {
        "name": "database_stats",
        "status": "pass",
        "message": f"{budget_count} budget lines, {pdf_count} PDF pages, {file_count} files",
        "details": {
            "budget_lines": budget_count,
            "pdf_pages": pdf_count,
            "ingested_files": file_count,
        },
    }


def check_duplicate_rows(conn: sqlite3.Connection) -> dict:
    """1.B6-b: Detect rows with identical key fields (likely parsing bugs)."""
    cur = conn.execute("""
        SELECT source_file, exhibit_type, account, organization,
               budget_activity, line_item, sheet_name, COUNT(*) as cnt
        FROM budget_lines
        GROUP BY source_file, exhibit_type, account, organization,
                 budget_activity, line_item, sheet_name
        HAVING cnt > 1
        ORDER BY cnt DESC
        LIMIT 50
    """)
    dupes = [dict(zip([d[0] for d in cur.description], row)) for row in cur.fetchall()]
    total_dupes = sum(d["cnt"] - 1 for d in dupes)
    return {
        "name": "duplicate_rows",
        "status": "warn" if dupes else "pass",
        "message": f"{total_dupes} duplicate row(s) across {len(dupes)} key combination(s)"
                   if dupes else "No duplicates found",
        "details": dupes,
    }


def check_null_heavy_rows(conn: sqlite3.Connection) -> dict:
    """1.B6-c: Flag rows where ALL amount columns are NULL or zero."""
    conditions = " AND ".join(
        f"(COALESCE({col}, 0) = 0)" for col in AMOUNT_COLUMNS
    )
    cur = conn.execute(f"""
        SELECT exhibit_type, COUNT(*) as cnt
        FROM budget_lines
        WHERE {conditions}
        GROUP BY exhibit_type
        ORDER BY cnt DESC
    """)
    rows = [{"exhibit_type": r[0], "count": r[1]} for r in cur.fetchall()]
    total = sum(r["count"] for r in rows)

    total_rows = conn.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0]
    pct = (total / total_rows * 100) if total_rows else 0

    return {
        "name": "null_heavy_rows",
        "status": "warn" if pct > 10 else "pass",
        "message": f"{total} row(s) ({pct:.1f}%) have all-null/zero amounts",
        "details": rows,
    }


def check_unknown_exhibit_types(conn: sqlite3.Connection) -> dict:
    """1.B6-e: Flag exhibit types not in the known set."""
    placeholders = ",".join(f"'{t}'" for t in KNOWN_EXHIBIT_TYPES)
    cur = conn.execute(f"""
        SELECT exhibit_type, COUNT(*) as cnt
        FROM budget_lines
        WHERE exhibit_type NOT IN ({placeholders})
        GROUP BY exhibit_type
        ORDER BY cnt DESC
    """)
    rows = [{"exhibit_type": r[0], "count": r[1]} for r in cur.fetchall()]
    return {
        "name": "unknown_exhibit_types",
        "status": "warn" if rows else "pass",
        "message": f"{len(rows)} unknown exhibit type(s) found" if rows
                   else "All exhibit types are known",
        "details": rows,
    }


def check_value_ranges(conn: sqlite3.Connection) -> dict:
    """1.B6-f: Flag extreme monetary values (likely unit-of-measure errors)."""
    threshold = 1_000_000_000  # $1T in thousands
    outliers = []
    for col in AMOUNT_COLUMNS:
        cur = conn.execute(f"""
            SELECT source_file, exhibit_type, account, organization, {col}
            FROM budget_lines
            WHERE ABS({col}) > ?
            LIMIT 10
        """, (threshold,))
        for row in cur.fetchall():
            outliers.append({
                "source_file": row[0], "exhibit_type": row[1],
                "account": row[2], "organization": row[3],
                "column": col, "value": row[4],
            })
    return {
        "name": "value_ranges",
        "status": "warn" if outliers else "pass",
        "message": f"{len(outliers)} extreme value(s) found (>$1T in thousands)"
                   if outliers else "All values within expected range",
        "details": outliers,
    }


def check_row_count_consistency(conn: sqlite3.Connection) -> dict:
    """1.B6-g: Cross-check ingested_files.row_count against actual counts."""
    cur = conn.execute("""
        SELECT i.file_path, i.row_count, i.file_type,
               CASE i.file_type
                   WHEN 'excel' THEN (SELECT COUNT(*) FROM budget_lines
                                      WHERE source_file = i.file_path)
                   WHEN 'pdf'   THEN (SELECT COUNT(*) FROM pdf_pages
                                      WHERE source_file = i.file_path)
               END as actual_count
        FROM ingested_files i
        WHERE i.row_count IS NOT NULL
    """)
    mismatches = []
    for row in cur.fetchall():
        file_path, expected, file_type, actual = row
        if actual is not None and expected != actual:
            mismatches.append({
                "file_path": file_path, "file_type": file_type,
                "expected": expected, "actual": actual,
            })
    return {
        "name": "row_count_consistency",
        "status": "warn" if mismatches else "pass",
        "message": f"{len(mismatches)} file(s) have row count mismatches"
                   if mismatches else "All row counts consistent",
        "details": mismatches,
    }


# ── Orchestrator ──────────────────────────────────────────────────────────────

ALL_CHECKS = [
    check_database_stats,
    check_duplicate_rows,
    check_null_heavy_rows,
    check_unknown_exhibit_types,
    check_value_ranges,
    check_row_count_consistency,
]


def validate_all(db_path: Path = DEFAULT_DB_PATH, strict: bool = False) -> dict:
    """Run all validation checks and return a summary dict."""
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        print("Run 'python build_budget_db.py' first to build the database.")
        sys.exit(1)

    conn = get_connection(db_path)
    results = []
    for check_fn in ALL_CHECKS:
        result = check_fn(conn)
        results.append(result)
    conn.close()

    total_warnings = sum(1 for r in results if r["status"] == "warn")
    total_failures = sum(1 for r in results if r["status"] == "fail")

    summary = {
        "database": str(db_path),
        "checks": results,
        "total_checks": len(results),
        "total_warnings": total_warnings,
        "total_failures": total_failures,
        "exit_code": 1 if strict and (total_warnings + total_failures) > 0 else 0,
    }
    return summary


def print_report(summary: dict) -> None:
    """Print a human-readable validation report."""
    print(f"\n{'='*60}")
    print(f"  Budget Database Validation Report")
    print(f"  Database: {summary['database']}")
    print(f"{'='*60}\n")

    for check in summary["checks"]:
        icon = {"pass": "OK", "warn": "WARN", "fail": "FAIL"}[check["status"]]
        print(f"  [{icon:4s}] {check['name']}: {check['message']}")
        if check["status"] != "pass" and check.get("details"):
            details = check["details"]
            if isinstance(details, list):
                for d in details[:5]:
                    print(f"           {d}")
                if len(details) > 5:
                    print(f"           ... and {len(details) - 5} more")

    print(f"\n  Summary: {summary['total_checks']} checks, "
          f"{summary['total_warnings']} warning(s), "
          f"{summary['total_failures']} failure(s)\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Validate budget database")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero on any warnings or failures")
    parser.add_argument("--json", action="store_true", dest="output_json",
                        help="Output results as JSON")
    args = parser.parse_args()

    summary = validate_all(args.db, strict=args.strict)

    if args.output_json:
        print(json.dumps(summary, indent=2))
    else:
        print_report(summary)

    sys.exit(summary["exit_code"])
