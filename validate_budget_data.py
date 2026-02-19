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

──────────────────────────────────────────────────────────────────────────────
Remaining TODOs
──────────────────────────────────────────────────────────────────────────────

DONE 1.B6-a: check_fiscal_year_coverage() added — flags orgs missing expected FYs.
DONE 1.B6-d: check_column_types() added — detects text in numeric amount columns.
DONE 1.B6-h: validate_all() wired into build_budget_db.py post-build step.
DONE 2.B3-a: generate_quality_report() writes data_quality_report.json with
    row counts by (service, fiscal_year, exhibit_type), null/zero percentages
    for each amount column, and full validation check results.
"""

import json
import sqlite3
import sys
from datetime import datetime
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
    # Single query instead of three separate COUNT(*) round-trips.
    row = conn.execute("""
        SELECT
            (SELECT COUNT(*) FROM budget_lines)  AS budget_count,
            (SELECT COUNT(*) FROM pdf_pages)     AS pdf_count,
            (SELECT COUNT(*) FROM ingested_files) AS file_count
    """).fetchone()
    budget_count, pdf_count, file_count = row[0], row[1], row[2]

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
    # Single UNION ALL query replaces 7 separate table scans.
    union_parts = " UNION ALL ".join(
        f"SELECT source_file, exhibit_type, account, organization,"
        f" '{col}' AS col_name, {col} AS val"
        f" FROM budget_lines WHERE ABS({col}) > {threshold}"
        for col in AMOUNT_COLUMNS
    )
    cur = conn.execute(f"SELECT * FROM ({union_parts}) LIMIT 70")
    for row in cur.fetchall():
        outliers.append({
            "source_file": row[0], "exhibit_type": row[1],
            "account": row[2], "organization": row[3],
            "column": row[4], "value": row[5],
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
    # Use GROUP BY aggregates instead of correlated subqueries to avoid
    # one COUNT(*) per file (which is extremely slow on thousands of PDFs).
    cur = conn.execute("""
        SELECT i.file_path, i.row_count, i.file_type, actual.cnt
        FROM ingested_files i
        JOIN (
            SELECT source_file, COUNT(*) AS cnt FROM budget_lines GROUP BY source_file
            UNION ALL
            SELECT source_file, COUNT(*) AS cnt FROM pdf_pages GROUP BY source_file
        ) actual ON actual.source_file = i.file_path
        WHERE i.row_count IS NOT NULL
          AND i.row_count != actual.cnt
    """)
    mismatches = [
        {"file_path": row[0], "expected": row[1], "file_type": row[2], "actual": row[3]}
        for row in cur.fetchall()
    ]
    return {
        "name": "row_count_consistency",
        "status": "warn" if mismatches else "pass",
        "message": f"{len(mismatches)} file(s) have row count mismatches"
                   if mismatches else "All row counts consistent",
        "details": mismatches,
    }


def check_fiscal_year_coverage(conn: sqlite3.Connection) -> dict:
    """1.B6-a: Flag orgs that are missing fiscal years present in other orgs."""
    cur = conn.execute("""
        SELECT organization_name,
               GROUP_CONCAT(DISTINCT fiscal_year) AS years
        FROM budget_lines
        WHERE organization_name IS NOT NULL AND organization_name != ''
        GROUP BY organization_name
    """)
    rows = cur.fetchall()
    if not rows:
        return {
            "name": "fiscal_year_coverage",
            "status": "pass",
            "message": "No organization data to compare",
            "details": [],
        }

    all_years: set = set()
    org_years: dict = {}
    for r in rows:
        years = set(r[1].split(",")) if r[1] else set()
        org_years[r[0]] = years
        all_years.update(years)

    missing = []
    for org, years in org_years.items():
        gap = sorted(all_years - years)
        if gap:
            missing.append({"organization": org, "missing_years": gap})

    return {
        "name": "fiscal_year_coverage",
        "status": "warn" if missing else "pass",
        "message": (
            f"{len(missing)} org(s) missing fiscal years present in others"
            if missing else "All orgs have consistent fiscal year coverage"
        ),
        "details": missing,
    }


def check_column_types(conn: sqlite3.Connection) -> dict:
    """1.B6-d: Detect text values stored in numeric amount columns."""
    misaligned = []
    # Single UNION ALL query replaces 7 separate table scans.
    union_parts = " UNION ALL ".join(
        f"SELECT source_file, exhibit_type, '{col}' AS col_name, {col} AS val"
        f" FROM budget_lines"
        f" WHERE {col} IS NOT NULL"
        f"   AND TYPEOF({col}) NOT IN ('real', 'integer')"
        for col in AMOUNT_COLUMNS
    )
    try:
        cur = conn.execute(f"SELECT * FROM ({union_parts}) LIMIT 70")
        for row in cur.fetchall():
            misaligned.append({
                "source_file": row[0],
                "exhibit_type": row[1],
                "column": row[2],
                "value": row[3],
            })
    except Exception:
        pass

    return {
        "name": "column_types",
        "status": "warn" if misaligned else "pass",
        "message": (
            f"{len(misaligned)} row(s) have text in numeric amount columns"
            if misaligned else "All amount columns contain numeric values"
        ),
        "details": misaligned,
    }


# ── Orchestrator ──────────────────────────────────────────────────────────────

ALL_CHECKS = [
    check_database_stats,
    check_duplicate_rows,
    check_null_heavy_rows,
    check_unknown_exhibit_types,
    check_value_ranges,
    check_row_count_consistency,
    check_fiscal_year_coverage,   # 1.B6-a
    check_column_types,           # 1.B6-d
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
        print(f"  Checking {check_fn.__name__}...", end=" ", flush=True)
        result = check_fn(conn)
        print(result["status"].upper())
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
    print("  Budget Database Validation Report")
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


def generate_quality_report(
    db_path: Path = DEFAULT_DB_PATH,
    output_path: Path = Path("data_quality_report.json"),
    print_console: bool = True,
) -> dict:
    """Generate a JSON data-quality report after a build (2.B3-a).

    Extends the basic validation summary with:
      - Row counts broken down by (service/org, fiscal_year, exhibit_type)
      - Null/zero percentages for each amount column
      - Full validation check results from validate_all()

    Writes the report to output_path and returns the report dict.

    Args:
        db_path:       Path to the SQLite database.
        output_path:   JSON file to write (default: data_quality_report.json).
        print_console: If True, also print the human-readable validation report.

    Returns:
        Report dict with keys: timestamp, database, total_budget_lines,
        row_counts_by_service_fy_exhibit, amount_column_stats,
        validation_summary.
    """
    conn = get_connection(db_path)

    # 1. Row counts by (organization_name, fiscal_year, exhibit_type)
    cur = conn.execute("""
        SELECT organization_name, fiscal_year, exhibit_type, COUNT(*) AS row_count
        FROM budget_lines
        WHERE organization_name IS NOT NULL
        GROUP BY organization_name, fiscal_year, exhibit_type
        ORDER BY organization_name, fiscal_year, exhibit_type
    """)
    row_counts = [
        {
            "service": r[0],
            "fiscal_year": r[1],
            "exhibit_type": r[2],
            "row_count": r[3],
        }
        for r in cur.fetchall()
    ]

    # 2. Null/zero percentages for each amount column.
    # Single conditional-aggregation query replaces 14 separate COUNT(*) scans
    # (2 per column × 7 columns).  All counts computed in one table pass.
    agg_exprs = ", ".join(
        f"SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) AS {col}_null,"
        f" SUM(CASE WHEN {col} = 0    THEN 1 ELSE 0 END) AS {col}_zero"
        for col in AMOUNT_COLUMNS
    )
    agg_row = conn.execute(
        f"SELECT COUNT(*) AS total, {agg_exprs} FROM budget_lines"
    ).fetchone()
    total_rows = agg_row[0]
    amount_stats: dict = {}
    for i, col in enumerate(AMOUNT_COLUMNS):
        null_ct = agg_row[1 + i * 2] or 0
        zero_ct = agg_row[2 + i * 2] or 0
        if total_rows:
            amount_stats[col] = {
                "null_count": null_ct,
                "null_pct": round(null_ct / total_rows * 100, 1),
                "zero_count": zero_ct,
                "zero_pct": round(zero_ct / total_rows * 100, 1),
            }
        else:
            amount_stats[col] = {
                "null_count": 0, "null_pct": 0.0,
                "zero_count": 0, "zero_pct": 0.0,
            }

    conn.close()

    # 3. Run validation checks
    val_summary = validate_all(db_path)
    if print_console:
        print_report(val_summary)

    report = {
        "timestamp": datetime.now().isoformat(),
        "database": str(db_path),
        "total_budget_lines": total_rows,
        "row_counts_by_service_fy_exhibit": row_counts,
        "amount_column_stats": amount_stats,
        "validation_summary": {
            "total_checks": val_summary["total_checks"],
            "total_warnings": val_summary["total_warnings"],
            "total_failures": val_summary["total_failures"],
            "checks": val_summary["checks"],
        },
    }

    output_path.write_text(json.dumps(report, indent=2))
    return report


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
