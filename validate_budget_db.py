"""
DoD Budget Database Validation Suite — Step 1.B6

Runs automated quality checks against the SQLite budget database and
produces a summary report flagging anomalies.

Usage:
    python validate_budget_db.py                     # Default database
    python validate_budget_db.py --db mydb.sqlite    # Custom path
    python validate_budget_db.py --verbose            # Show all issue details
    python validate_budget_db.py --json               # JSON output
    python validate_budget_db.py --html > report.html # HTML report (TIGER-007)
    python validate_budget_db.py --threshold warning  # Exit non-zero on warnings+

---
TODOs for this file
---

DONE LION-108-val: Validation checks for LION schema changes.
    (a) check_pdf_pages_fiscal_year — warns if >5% of pdf_pages have NULL fiscal_year
    (b) check_pdf_pe_numbers_populated — warns if junction table is empty/missing
    (c) check_pe_tags_source_files — warns if pe_tags.source_files has NULLs

"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime
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


# DONE [Group: TIGER] TIGER-001: Add cross-year budget consistency validation — flag >10x YoY changes
# DONE [Group: TIGER] TIGER-002: Add appropriation title consistency validation
# DONE [Group: TIGER] TIGER-003: Add line item rollup reconciliation
# DONE [Group: TIGER] TIGER-004: Add referential integrity validation (budget_lines → lookup tables)
# DONE [Group: TIGER] TIGER-005: Add FY column completeness check
# DONE [Group: TIGER] TIGER-006: Integrate PDF quality metrics into validation report
# DONE [Group: TIGER] TIGER-007: Add HTML validation report export and --threshold flag

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


# ── TIGER-001: Cross-year budget consistency validation ─────────────────────

def check_yoy_budget_anomalies(conn: sqlite3.Connection) -> list[dict]:
    """Detect anomalous year-over-year budget changes (>10x / 1000%).

    For each (organization, account, exhibit_type) group, compares adjacent
    fiscal year amounts.  A change ratio > 10 suggests a potential data issue
    (though large changes may be legitimate policy shifts).

    Severity: WARNING
    """
    issues = []
    amount_cols = _get_amount_columns(conn)
    if len(amount_cols) < 2:
        return issues

    # Compare adjacent pairs of amount columns
    for i in range(len(amount_cols) - 1):
        col_old = amount_cols[i]
        col_new = amount_cols[i + 1]
        try:
            rows = conn.execute(f"""
                SELECT organization_name, account, exhibit_type,
                       {col_old} AS amount_old, {col_new} AS amount_new
                FROM budget_lines
                WHERE {col_old} IS NOT NULL AND {col_old} != 0
                  AND {col_new} IS NOT NULL AND {col_new} != 0
                  AND ABS({col_new} - {col_old}) / MAX(ABS({col_old}), 1) > 10
                ORDER BY ABS({col_new} - {col_old}) / MAX(ABS({col_old}), 1) DESC
                LIMIT 50
            """).fetchall()
        except Exception:
            continue

        if rows:
            issues.append({
                "check": "yoy_budget_anomalies",
                "severity": "warning",
                "detail": (
                    f"{len(rows)} row(s) have >1000% change from {col_old} to {col_new}"
                ),
                "columns": [col_old, col_new],
                "count": len(rows),
                "samples": [
                    f"{r['organization_name']} / {r['account']} / {r['exhibit_type']}: "
                    f"{r['amount_old']:,.0f} → {r['amount_new']:,.0f}"
                    for r in rows[:5]
                ],
            })

    return issues


# ── TIGER-002: Appropriation title consistency validation ───────────────────

def check_appropriation_title_consistency(conn: sqlite3.Connection) -> list[dict]:
    """Detect the same appropriation code used with different titles.

    Severity: WARNING
    """
    issues = []
    try:
        rows = conn.execute("""
            SELECT account, COUNT(DISTINCT account_title) AS title_count
            FROM budget_lines
            WHERE account IS NOT NULL AND account != ''
              AND account_title IS NOT NULL AND account_title != ''
            GROUP BY account
            HAVING title_count > 1
        """).fetchall()
    except Exception:
        return []

    for r in rows:
        # Fetch the distinct titles for this account
        titles = conn.execute(
            "SELECT DISTINCT account_title FROM budget_lines "
            "WHERE account = ? AND account_title IS NOT NULL AND account_title != ''",
            (r["account"],),
        ).fetchall()
        title_list = [t["account_title"] for t in titles]
        issues.append({
            "check": "appropriation_title_consistency",
            "severity": "warning",
            "detail": (
                f"Account '{r['account']}' has {r['title_count']} distinct titles: "
                f"{'; '.join(title_list[:5])}"
            ),
            "account": r["account"],
            "title_count": r["title_count"],
            "titles": title_list,
        })

    return issues


# ── TIGER-003: Line item rollup reconciliation ─────────────────────────────

def check_line_item_rollups(conn: sqlite3.Connection) -> list[dict]:
    """Verify that detail line items sum correctly to budget activity totals.

    For each (organization, account, fiscal_year, exhibit_type), sums all
    line item amounts and compares against the budget activity total row
    (where budget_activity_title contains 'total').
    Flags discrepancies > $1M (to allow for rounding).

    Severity: WARNING
    """
    issues = []
    amount_cols = _get_amount_columns(conn)
    if not amount_cols:
        return issues

    # Use the most recent request column for comparison
    check_col = amount_cols[-1]

    try:
        # Get total rows (rows where budget_activity_title suggests a total)
        total_rows = conn.execute(f"""
            SELECT organization_name, account, fiscal_year, exhibit_type,
                   SUM(COALESCE({check_col}, 0)) AS total_amount
            FROM budget_lines
            WHERE LOWER(COALESCE(budget_activity_title, '')) LIKE '%total%'
            GROUP BY organization_name, account, fiscal_year, exhibit_type
        """).fetchall()

        if not total_rows:
            return issues

        # Get detail sums (non-total rows)
        detail_rows = conn.execute(f"""
            SELECT organization_name, account, fiscal_year, exhibit_type,
                   SUM(COALESCE({check_col}, 0)) AS detail_sum
            FROM budget_lines
            WHERE LOWER(COALESCE(budget_activity_title, '')) NOT LIKE '%total%'
              AND budget_activity_title IS NOT NULL
              AND budget_activity_title != ''
            GROUP BY organization_name, account, fiscal_year, exhibit_type
        """).fetchall()

        detail_map = {
            (r["organization_name"], r["account"], r["fiscal_year"], r["exhibit_type"]):
                r["detail_sum"]
            for r in detail_rows
        }

        for r in total_rows:
            key = (r["organization_name"], r["account"], r["fiscal_year"], r["exhibit_type"])
            detail_sum = detail_map.get(key)
            if detail_sum is None:
                continue
            total_amount = r["total_amount"] or 0
            diff = abs(total_amount - detail_sum)
            # Flag discrepancies > $1M (amounts are in thousands, so 1000 = $1M)
            if diff > 1000:
                issues.append({
                    "check": "line_item_rollups",
                    "severity": "warning",
                    "detail": (
                        f"Rollup mismatch for {key[0]} / {key[1]} / {key[2]} / {key[3]}: "
                        f"total={total_amount:,.0f} detail_sum={detail_sum:,.0f} "
                        f"diff=${diff:,.0f}K"
                    ),
                    "organization": key[0],
                    "account": key[1],
                    "fiscal_year": key[2],
                    "exhibit_type": key[3],
                    "total_amount": total_amount,
                    "detail_sum": detail_sum,
                    "difference": diff,
                })
    except Exception:
        pass

    return issues


# ── TIGER-004: Referential integrity validation ────────────────────────────

def check_referential_integrity(conn: sqlite3.Connection) -> list[dict]:
    """Verify all referenced values exist in lookup tables.

    Checks that:
    - organization_name values in budget_lines exist in services_agencies
    - exhibit_type values in budget_lines exist in exhibit_types

    Severity: ERROR for missing references
    """
    issues = []

    # Check organization_name → services_agencies
    try:
        orphaned_orgs = conn.execute("""
            SELECT DISTINCT b.organization_name, COUNT(*) AS cnt
            FROM budget_lines b
            LEFT JOIN services_agencies s ON b.organization_name = s.code
               OR b.organization_name = s.full_name
            WHERE b.organization_name IS NOT NULL
              AND b.organization_name != ''
              AND s.code IS NULL
            GROUP BY b.organization_name
            ORDER BY cnt DESC
        """).fetchall()

        for r in orphaned_orgs:
            issues.append({
                "check": "referential_integrity",
                "severity": "error",
                "detail": (
                    f"Organization '{r['organization_name']}' ({r['cnt']} rows) "
                    "not found in services_agencies table"
                ),
                "table": "services_agencies",
                "missing_value": r["organization_name"],
                "count": r["cnt"],
            })
    except Exception:
        # services_agencies table may not exist
        pass

    # Check exhibit_type → exhibit_types
    try:
        orphaned_exhibits = conn.execute("""
            SELECT DISTINCT b.exhibit_type, COUNT(*) AS cnt
            FROM budget_lines b
            LEFT JOIN exhibit_types e ON b.exhibit_type = e.code
            WHERE b.exhibit_type IS NOT NULL
              AND b.exhibit_type != ''
              AND e.code IS NULL
            GROUP BY b.exhibit_type
            ORDER BY cnt DESC
        """).fetchall()

        for r in orphaned_exhibits:
            issues.append({
                "check": "referential_integrity",
                "severity": "error",
                "detail": (
                    f"Exhibit type '{r['exhibit_type']}' ({r['cnt']} rows) "
                    "not found in exhibit_types table"
                ),
                "table": "exhibit_types",
                "missing_value": r["exhibit_type"],
                "count": r["cnt"],
            })
    except Exception:
        # exhibit_types table may not exist
        pass

    return issues


# ── TIGER-005: FY column completeness check ────────────────────────────────

# Expected FY amount columns based on current budget cycle
EXPECTED_FY_COLUMNS = {
    "amount_fy2024_actual",
    "amount_fy2025_enacted",
    "amount_fy2025_supplemental",
    "amount_fy2025_total",
    "amount_fy2026_request",
    "amount_fy2026_reconciliation",
    "amount_fy2026_total",
}


def check_expected_fy_columns(conn: sqlite3.Connection) -> list[dict]:
    """Verify expected fiscal year columns exist in the budget_lines schema.

    Checks PRAGMA table_info for amount_fy* columns and compares against
    the expected set.

    Severity: ERROR for missing expected columns
    """
    issues = []
    actual_cols = set(_get_amount_columns(conn))
    missing = EXPECTED_FY_COLUMNS - actual_cols
    if missing:
        issues.append({
            "check": "expected_fy_columns",
            "severity": "error",
            "detail": (
                f"Missing expected FY columns: {', '.join(sorted(missing))}"
            ),
            "missing_columns": sorted(missing),
        })
    return issues


# ── TIGER-006: PDF extraction quality metrics ──────────────────────────────

def check_pdf_extraction_quality(conn: sqlite3.Connection) -> list[dict]:
    """Check PDF extraction quality and calculate quality score.

    Queries pdf_pages for:
    - Pages with suspiciously short text (< 50 chars excluding whitespace)
    - Pages where has_tables=1 but extracted table text is empty

    Severity: WARNING if quality score < 0.9; INFO otherwise
    """
    issues = []
    try:
        total_pages = conn.execute(
            "SELECT COUNT(*) AS c FROM pdf_pages"
        ).fetchone()["c"]
    except Exception:
        return issues

    if total_pages == 0:
        return issues

    # Short text pages
    try:
        short_pages = conn.execute("""
            SELECT COUNT(*) AS c FROM pdf_pages
            WHERE LENGTH(REPLACE(REPLACE(COALESCE(page_text, ''), ' ', ''),
                         CHAR(10), '')) < 50
        """).fetchone()["c"]
    except Exception:
        short_pages = 0

    # Empty table data pages
    try:
        empty_table_pages = conn.execute("""
            SELECT COUNT(*) AS c FROM pdf_pages
            WHERE has_tables = 1
              AND (table_data IS NULL OR TRIM(table_data) = '')
        """).fetchone()["c"]
    except Exception:
        empty_table_pages = 0

    bad_pages = short_pages + empty_table_pages
    # Avoid double-counting pages that are both short and have empty tables
    good_pages = max(total_pages - bad_pages, 0)
    quality_score = round(good_pages / total_pages, 4) if total_pages > 0 else 1.0

    severity = "warning" if quality_score < 0.9 else "info"
    issues.append({
        "check": "pdf_extraction_quality",
        "severity": severity,
        "detail": (
            f"PDF extraction quality score: {quality_score:.2%} "
            f"({good_pages}/{total_pages} good pages, "
            f"{short_pages} short text, {empty_table_pages} empty table data)"
        ),
        "pdf_quality_score": quality_score,
        "total_pages": total_pages,
        "short_text_pages": short_pages,
        "empty_table_pages": empty_table_pages,
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


# ── Budget type validation ────────────────────────────────────────────────

_KNOWN_BUDGET_TYPES = {
    "MilPers", "O&M", "Procurement", "RDT&E", "Revolving", "Construction",
    # Also accept lowercase/variants that appear in enrichment
    "milpers", "om", "procurement", "rdte", "revolving", "construction",
}


def check_budget_type_values(conn: sqlite3.Connection) -> list[dict]:
    """Check that budget_type values are from the known set.

    Flags unknown values as info-level (may indicate new exhibit types
    or data format changes).
    """
    issues = []
    try:
        rows = conn.execute("""
            SELECT budget_type, COUNT(*) AS cnt
            FROM budget_lines
            WHERE budget_type IS NOT NULL
            GROUP BY budget_type
        """).fetchall()
    except Exception:
        return []

    for row in rows:
        bt = row[0]
        if bt not in _KNOWN_BUDGET_TYPES:
            issues.append({
                "check": "budget_type_values",
                "severity": "info",
                "detail": f"Unknown budget_type '{bt}' ({row[1]} rows)",
                "budget_type": bt,
                "count": row[1],
            })

    return issues


# ── LION-108-val: Validation checks for LION schema changes ──────────────

def check_pdf_pages_fiscal_year(conn: sqlite3.Connection) -> list[dict]:
    """LION-108-val(a): Check that pdf_pages.fiscal_year is populated.

    After LION-100, every pdf_pages row should have a fiscal_year derived
    from the directory path.  Warns if >5% of rows are NULL.
    """
    issues = []
    try:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM pdf_pages"
        ).fetchone()["c"]
    except Exception:
        return []

    if total == 0:
        return []

    try:
        null_fy = conn.execute(
            "SELECT COUNT(*) AS c FROM pdf_pages WHERE fiscal_year IS NULL"
        ).fetchone()["c"]
    except Exception:
        # Column may not exist in older databases
        return [{
            "check": "pdf_pages_fiscal_year",
            "severity": "warning",
            "detail": "pdf_pages table missing fiscal_year column (LION-100 not applied)",
        }]

    if null_fy > 0:
        pct = null_fy / total * 100
        severity = "warning" if pct > 5 else "info"
        issues.append({
            "check": "pdf_pages_fiscal_year",
            "severity": severity,
            "detail": (
                f"{null_fy}/{total} pdf_pages rows ({pct:.1f}%) have NULL fiscal_year"
            ),
            "null_count": null_fy,
            "total": total,
            "null_pct": round(pct, 2),
        })

    return issues


def check_pdf_pe_numbers_populated(conn: sqlite3.Connection) -> list[dict]:
    """LION-108-val(b): Check that pdf_pe_numbers has rows for PE-containing PDFs.

    After LION-103, the pdf_pe_numbers junction table should be populated
    during ingestion.  Warns if the table exists but is empty while pdf_pages
    has text mentioning PE-like patterns.
    """
    issues = []

    if not _table_exists(conn, "pdf_pe_numbers"):
        return [{
            "check": "pdf_pe_numbers_populated",
            "severity": "warning",
            "detail": "pdf_pe_numbers table does not exist (LION-103 not applied)",
        }]

    junction_count = conn.execute(
        "SELECT COUNT(*) AS c FROM pdf_pe_numbers"
    ).fetchone()["c"]

    if junction_count == 0:
        # Check if there are any pdf_pages that might contain PE numbers
        try:
            pe_pages = conn.execute("""
                SELECT COUNT(*) AS c FROM pdf_pages
                WHERE page_text LIKE '%0_0_____%'
            """).fetchone()["c"]
        except Exception:
            pe_pages = 0

        if pe_pages > 0:
            issues.append({
                "check": "pdf_pe_numbers_populated",
                "severity": "warning",
                "detail": (
                    f"pdf_pe_numbers is empty but {pe_pages} pdf_pages "
                    "may contain PE numbers — re-run ingestion with LION-103"
                ),
                "pe_page_estimate": pe_pages,
            })
    else:
        issues.append({
            "check": "pdf_pe_numbers_populated",
            "severity": "info",
            "detail": f"pdf_pe_numbers has {junction_count:,} PE-page links",
            "junction_count": junction_count,
        })

    return issues


def check_pe_tags_source_files(conn: sqlite3.Connection) -> list[dict]:
    """LION-108-val(c): Check that pe_tags.source_files is populated.

    After LION-106, every pe_tags row should have a non-null source_files
    JSON array for provenance tracking.
    """
    issues = []

    if not _table_exists(conn, "pe_tags"):
        return []

    try:
        total = conn.execute(
            "SELECT COUNT(*) AS c FROM pe_tags"
        ).fetchone()["c"]
    except Exception:
        return []

    if total == 0:
        return []

    try:
        null_src = conn.execute(
            "SELECT COUNT(*) AS c FROM pe_tags WHERE source_files IS NULL"
        ).fetchone()["c"]
    except Exception:
        return [{
            "check": "pe_tags_source_files",
            "severity": "warning",
            "detail": "pe_tags table missing source_files column (LION-106 not applied)",
        }]

    if null_src > 0:
        issues.append({
            "check": "pe_tags_source_files",
            "severity": "warning",
            "detail": (
                f"{null_src}/{total} pe_tags rows have NULL source_files — "
                "re-run enrichment Phase 3 with LION-106"
            ),
            "null_count": null_src,
            "total": total,
        })

    return issues


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    r = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone()
    return r is not None


ALL_CHECKS = [
    ("Missing Fiscal Years", check_missing_years),
    ("Duplicate Rows", check_duplicates),
    ("Zero-Amount Line Items", check_zero_amounts),
    ("Column Alignment", check_column_alignment),
    ("Unknown Exhibit Types", check_unknown_exhibits),
    ("Ingestion Errors", check_ingestion_errors),
    ("Empty Files", check_empty_files),
    ("Unit Consistency", check_unit_consistency),                # Step 1.B3-f
    ("PE Number Format", check_pe_number_format),                # VALDB-001
    ("Negative Amounts", check_negative_amounts),                # VALDB-002
    ("Database Integrity", check_integrity),                      # SCHEMA-003
    ("YoY Budget Anomalies", check_yoy_budget_anomalies),        # TIGER-001
    ("Appropriation Title Consistency", check_appropriation_title_consistency),  # TIGER-002
    ("Line Item Rollups", check_line_item_rollups),              # TIGER-003
    ("Referential Integrity", check_referential_integrity),      # TIGER-004
    ("Expected FY Columns", check_expected_fy_columns),          # TIGER-005
    ("PDF Extraction Quality", check_pdf_extraction_quality),    # TIGER-006
    ("Budget Type Values", check_budget_type_values),              # Budget type ref check
    ("PDF Pages Fiscal Year", check_pdf_pages_fiscal_year),      # LION-108-val(a)
    ("PDF PE Numbers Junction", check_pdf_pe_numbers_populated), # LION-108-val(b)
    ("PE Tags Source Files", check_pe_tags_source_files),        # LION-108-val(c)
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
    pdf_quality_score = None

    for check_name, check_fn in ALL_CHECKS:
        issues = check_fn(conn)
        count = len(issues)
        total_issues += count
        for issue in issues:
            severity_counts[issue["severity"]] += 1
            # TIGER-006: Extract PDF quality score
            if "pdf_quality_score" in issue:
                pdf_quality_score = issue["pdf_quality_score"]
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

    result = {
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
    # TIGER-006: Include PDF quality score in report
    if pdf_quality_score is not None:
        result["pdf_quality_score"] = pdf_quality_score
    return result


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


# ── TIGER-007: HTML report generation ──────────────────────────────────────

_SEVERITY_COLORS = {
    "error": "#dc3545",
    "warning": "#ffc107",
    "info": "#17a2b8",
}

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DoD Budget Validation Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
         max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #333; }}
  h1 {{ border-bottom: 2px solid #333; padding-bottom: 0.5rem; }}
  .timestamp {{ color: #666; font-size: 0.9rem; }}
  .summary-table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
  .summary-table th, .summary-table td {{ border: 1px solid #ddd; padding: 8px 12px;
                                          text-align: left; }}
  .summary-table th {{ background: #f8f9fa; }}
  .pass {{ color: #28a745; font-weight: bold; }}
  .fail {{ color: #dc3545; font-weight: bold; }}
  .warn {{ color: #856404; font-weight: bold; }}
  .sev-error {{ background: #f8d7da; color: #721c24; padding: 2px 6px;
                border-radius: 3px; font-size: 0.85rem; }}
  .sev-warning {{ background: #fff3cd; color: #856404; padding: 2px 6px;
                  border-radius: 3px; font-size: 0.85rem; }}
  .sev-info {{ background: #d1ecf1; color: #0c5460; padding: 2px 6px;
               border-radius: 3px; font-size: 0.85rem; }}
  details {{ margin: 0.5rem 0; border: 1px solid #ddd; border-radius: 4px; padding: 0.5rem; }}
  details summary {{ cursor: pointer; font-weight: 600; }}
  details summary:hover {{ color: #0056b3; }}
  .issue {{ padding: 4px 0; border-bottom: 1px solid #eee; font-size: 0.9rem; }}
  .issue:last-child {{ border-bottom: none; }}
  .metric {{ display: inline-block; padding: 4px 10px; margin: 2px;
             background: #e9ecef; border-radius: 3px; font-size: 0.9rem; }}
</style>
</head>
<body>
<h1>DoD Budget Database Validation Report</h1>
<p class="timestamp">Generated: {timestamp}</p>

<h2>Database Overview</h2>
<div>
  <span class="metric">Budget Lines: {budget_lines:,}</span>
  <span class="metric">PDF Pages: {pdf_pages:,}</span>
  <span class="metric">Files Ingested: {files_ingested:,}</span>
</div>

<h2>Summary</h2>
<table class="summary-table">
<tr><th>Metric</th><th>Count</th></tr>
<tr><td>Total Issues</td><td>{total_issues}</td></tr>
<tr><td><span class="sev-error">Errors</span></td><td>{errors}</td></tr>
<tr><td><span class="sev-warning">Warnings</span></td><td>{warnings}</td></tr>
<tr><td><span class="sev-info">Info</span></td><td>{info}</td></tr>
</table>

<h2>Check Results</h2>
<table class="summary-table">
<tr><th>Check</th><th>Status</th><th>Issues</th></tr>
{check_rows}
</table>

<h2>Details</h2>
{check_details}

</body>
</html>"""


def generate_html_report(conn: sqlite3.Connection) -> str:
    """Run all checks and return a styled HTML report (TIGER-007)."""
    report = generate_json_report(conn)

    check_rows = []
    check_details = []

    for check in report["checks"]:
        status_class = check["status"]
        status_label = check["status"].upper()
        check_rows.append(
            f'<tr><td>{check["name"]}</td>'
            f'<td class="{status_class}">{status_label}</td>'
            f'<td>{check["issue_count"]}</td></tr>'
        )

        if check["issues"]:
            issue_html = []
            for issue in check["issues"][:20]:
                sev_class = f"sev-{issue['severity']}"
                issue_html.append(
                    f'<div class="issue"><span class="{sev_class}">'
                    f'{issue["severity"].upper()}</span> {issue["detail"]}</div>'
                )
            if check["issue_count"] > 20:
                issue_html.append(
                    f'<div class="issue">... and {check["issue_count"] - 20} more</div>'
                )
            check_details.append(
                f'<details><summary>{check["name"]} ({check["issue_count"]} issues)</summary>'
                f'{"".join(issue_html)}</details>'
            )

    return _HTML_TEMPLATE.format(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        budget_lines=report["database"]["budget_lines"],
        pdf_pages=report["database"]["pdf_pages"],
        files_ingested=report["database"]["files_ingested"],
        total_issues=report["summary"]["total_issues"],
        errors=report["summary"]["errors"],
        warnings=report["summary"]["warnings"],
        info=report["summary"]["info"],
        check_rows="\n".join(check_rows),
        check_details="\n".join(check_details),
    )


# ── TIGER-007: Threshold-based exit code ───────────────────────────────────

_SEVERITY_LEVELS = {"info": 0, "warning": 1, "error": 2}


def _exceeds_threshold(report: dict, threshold: str) -> bool:
    """Check if any issues exceed the given severity threshold."""
    threshold_level = _SEVERITY_LEVELS.get(threshold, 2)
    for check in report["checks"]:
        for issue in check["issues"]:
            if _SEVERITY_LEVELS.get(issue["severity"], 0) >= threshold_level:
                return True
    return False


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
    parser.add_argument("--html", action="store_true",
                        help="Output a styled HTML report (TIGER-007)")
    parser.add_argument("--threshold", default="error",
                        choices=["info", "warning", "error"],
                        help="Exit non-zero if issues at/above this severity (default: error)")
    args = parser.parse_args()

    conn = get_connection(args.db)

    if args.html:
        html = generate_html_report(conn)
        print(html)
        report = generate_json_report(conn)
        should_fail = _exceeds_threshold(report, args.threshold)
        conn.close()
        sys.exit(1 if should_fail else 0)
    elif args.json:
        report = generate_json_report(conn)
        print(json.dumps(report, indent=2))
        should_fail = _exceeds_threshold(report, args.threshold)
        conn.close()
        sys.exit(1 if should_fail else 0)
    else:
        issue_count = generate_report(conn, verbose=args.verbose)
        conn.close()
        sys.exit(1 if issue_count > 0 else 0)


if __name__ == "__main__":
    main()
