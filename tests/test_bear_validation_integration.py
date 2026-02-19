"""
BEAR-003: Validation integration tests with intentional errors.

Create a test database with known data quality issues and verify all checks
catch them:
1. Duplicate rows (same source_file + exhibit_type + account + line_item + fiscal_year)
2. Missing fiscal years for one service
3. Zero-amount rows
4. Invalid PE number format
5. Negative amounts
6. Unknown exhibit type
7. Column misalignment (account without organization)
"""
# DONE [Group: BEAR] BEAR-003: Add validation integration tests with 7+ intentional data errors (~3,000 tokens)

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from build_budget_db import create_database


def _build_bad_db(tmp_path):
    """Build a test DB with 7+ intentional data quality issues."""
    db_path = tmp_path / "validation_bad.sqlite"
    conn = create_database(db_path)
    conn.row_factory = sqlite3.Row

    # Issue 1: Duplicate rows (same key tuple)
    for _ in range(2):
        conn.execute(
            """INSERT INTO budget_lines
               (source_file, exhibit_type, fiscal_year, account, line_item,
                account_title, organization, organization_name, pe_number,
                amount_fy2026_request)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("dup.xlsx", "p1", "2026", "2035", "BLI-001",
             "Aircraft Procurement", "A", "Army", "0205231A", 5000.0),
        )

    # Issue 2: Missing fiscal years — Navy only has 2026, Army has 2025 and 2026
    conn.execute(
        """INSERT INTO budget_lines
           (source_file, exhibit_type, fiscal_year, account, line_item,
            account_title, organization, organization_name, pe_number,
            amount_fy2025_enacted)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("army_2025.xlsx", "p1", "2025", "2035", "BLI-002",
         "Procurement", "A", "Army", "0205231A", 3000.0),
    )
    conn.execute(
        """INSERT INTO budget_lines
           (source_file, exhibit_type, fiscal_year, account, line_item,
            account_title, organization, organization_name, pe_number,
            amount_fy2026_request)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("navy_2026.xlsx", "p1", "2026", "1506", "BLI-003",
         "Weapons Procurement", "N", "Navy", "0305116BB", 7000.0),
    )

    # Issue 3: Zero-amount row (all amounts NULL or zero)
    conn.execute(
        """INSERT INTO budget_lines
           (source_file, exhibit_type, fiscal_year, account, line_item,
            account_title, organization, organization_name, pe_number)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("zeros.xlsx", "r1", "2026", "1300", "BLI-004",
         "Zero Budget Line", "A", "Army", "0602702E"),
    )

    # Issue 4: Invalid PE number format (should be 7 digits + 1-2 uppercase letters)
    conn.execute(
        """INSERT INTO budget_lines
           (source_file, exhibit_type, fiscal_year, account, line_item,
            account_title, organization, organization_name, pe_number,
            amount_fy2026_request)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("bad_pe.xlsx", "r1", "2026", "1300", "BLI-005",
         "Bad PE Line", "A", "Army", "INVALID_PE", 1000.0),
    )

    # Issue 5: Negative amount
    conn.execute(
        """INSERT INTO budget_lines
           (source_file, exhibit_type, fiscal_year, account, line_item,
            account_title, organization, organization_name, pe_number,
            amount_fy2026_request)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("negative.xlsx", "p1", "2026", "2035", "BLI-006",
         "Rescission Line", "A", "Army", "0205231A", -500.0),
    )

    # Issue 6: Unknown exhibit type
    conn.execute(
        """INSERT INTO budget_lines
           (source_file, exhibit_type, fiscal_year, account, line_item,
            account_title, organization, organization_name, pe_number,
            amount_fy2026_request)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("unknown.xlsx", "z99", "2026", "9999", "BLI-007",
         "Unknown Exhibit", "D", "Defense-Wide", "0602702E", 2000.0),
    )

    # Issue 7: Column misalignment — account without organization
    conn.execute(
        """INSERT INTO budget_lines
           (source_file, exhibit_type, fiscal_year, account, line_item,
            account_title, organization, organization_name, pe_number,
            amount_fy2026_request)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("misaligned.xlsx", "p1", "2026", "2035", "BLI-008",
         "Misaligned Line", NULL, NULL, "0205231A", 1500.0),
    )

    # Register files in ingested_files so ingestion_errors check has data
    for fname in ["dup.xlsx", "army_2025.xlsx", "navy_2026.xlsx", "zeros.xlsx",
                  "bad_pe.xlsx", "negative.xlsx", "unknown.xlsx", "misaligned.xlsx"]:
        conn.execute(
            "INSERT OR IGNORE INTO ingested_files (file_path, file_type, row_count, status) "
            "VALUES (?, 'xlsx', 1, 'ok')",
            (fname,),
        )

    conn.commit()
    return conn, db_path


# SQLite doesn't have a NULL keyword for params — use None
NULL = None


@pytest.fixture()
def bad_db(tmp_path):
    """Return (conn, db_path) for a DB with intentional issues."""
    conn, db_path = _build_bad_db(tmp_path)
    yield conn, db_path
    conn.close()


class TestValidationIntegration:
    """Run individual validation checks against a DB with known issues."""

    def test_check_duplicates_finds_duplicates(self, bad_db):
        from validate_budget_db import check_duplicates
        conn, _ = bad_db
        issues = check_duplicates(conn)
        assert len(issues) > 0
        assert any(i["check"] == "duplicates" for i in issues)
        assert any(i["severity"] == "error" for i in issues)

    def test_check_missing_years_finds_gaps(self, bad_db):
        from validate_budget_db import check_missing_years
        conn, _ = bad_db
        issues = check_missing_years(conn)
        # Navy is missing FY2025 that Army has
        assert len(issues) > 0
        assert any("missing" in str(i.get("detail", "")).lower() for i in issues)

    def test_check_zero_amounts_finds_zeros(self, bad_db):
        from validate_budget_db import check_zero_amounts
        conn, _ = bad_db
        issues = check_zero_amounts(conn)
        assert len(issues) > 0
        assert any(i["check"] == "zero_amounts" for i in issues)

    def test_check_pe_number_format_finds_invalid(self, bad_db):
        from validate_budget_db import check_pe_number_format
        conn, _ = bad_db
        issues = check_pe_number_format(conn)
        assert len(issues) > 0
        assert any("INVALID_PE" in str(i.get("samples", [])) for i in issues)

    def test_check_negative_amounts_finds_negatives(self, bad_db):
        from validate_budget_db import check_negative_amounts
        conn, _ = bad_db
        issues = check_negative_amounts(conn)
        assert len(issues) > 0
        assert any(i["severity"] == "info" for i in issues)

    def test_check_unknown_exhibits_finds_unknown(self, bad_db):
        from validate_budget_db import check_unknown_exhibits
        conn, _ = bad_db
        issues = check_unknown_exhibits(conn)
        assert len(issues) > 0
        assert any("z99" in str(i.get("exhibit_type", "")) for i in issues)

    def test_check_column_alignment_finds_misalignment(self, bad_db):
        from validate_budget_db import check_column_alignment
        conn, _ = bad_db
        issues = check_column_alignment(conn)
        assert len(issues) > 0
        assert any(i["check"] == "column_alignment" for i in issues)

    def test_generate_json_report_includes_all_issues(self, bad_db):
        """JSON report aggregates all checks and includes all issue types."""
        from validate_budget_db import generate_json_report
        conn, _ = bad_db
        report = generate_json_report(conn)

        assert "summary" in report
        assert "checks" in report
        assert report["summary"]["total_issues"] >= 7

        # Verify severity levels are present
        assert report["summary"]["errors"] > 0    # duplicates
        assert report["summary"]["warnings"] > 0  # zero amounts, etc.
        assert report["summary"]["info"] > 0      # negative amounts

        # Verify each check ran
        check_names = {c["name"] for c in report["checks"]}
        assert "Duplicate Rows" in check_names
        assert "Zero-Amount Line Items" in check_names
        assert "PE Number Format" in check_names
        assert "Negative Amounts" in check_names
        assert "Unknown Exhibit Types" in check_names
        assert "Column Alignment" in check_names

    def test_generate_json_report_is_serializable(self, bad_db):
        """JSON report can be serialized to JSON string."""
        from validate_budget_db import generate_json_report
        conn, _ = bad_db
        report = generate_json_report(conn)
        # Should not raise
        json_str = json.dumps(report, indent=2)
        assert len(json_str) > 100
