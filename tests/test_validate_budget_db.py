"""
Unit tests for validate_budget_db.py check functions — Step 1.B6

Tests each check function against a minimal in-memory SQLite database
populated with known-good and known-bad data. No pdfplumber or network
access required.
"""
import sqlite3
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Stub pdfplumber to avoid cryptography import issues
for _mod in ("pdfplumber", "openpyxl", "pandas"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

from build_budget_db import create_database
from validate_budget_db import (
    check_missing_years,
    check_duplicates,
    check_zero_amounts,
    check_column_alignment,
    check_unknown_exhibits,
    check_ingestion_errors,
    check_unit_consistency,
    check_empty_files,
)


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def conn(tmp_path):
    """Empty database with full schema, row_factory set for dict-like access."""
    db = tmp_path / "test.sqlite"
    c = create_database(db)
    c.row_factory = sqlite3.Row   # validate_budget_db.py uses r["col"] syntax
    yield c
    c.close()


def _insert_line(conn, **kwargs):
    """Insert one row into budget_lines with sensible defaults."""
    defaults = dict(
        source_file="test/p1_army.xlsx",
        exhibit_type="p1",
        sheet_name="Sheet1",
        fiscal_year="FY 2026",
        account="2035",
        account_title="Aircraft Procurement",
        organization="A",
        organization_name="Army",
        budget_activity=None,
        budget_activity_title=None,
        sub_activity=None,
        sub_activity_title=None,
        line_item=None,
        line_item_title=None,
        classification=None,
        amount_fy2024_actual=100.0,
        amount_fy2025_enacted=110.0,
        amount_fy2025_supplemental=None,
        amount_fy2025_total=None,
        amount_fy2026_request=120.0,
        amount_fy2026_reconciliation=None,
        amount_fy2026_total=None,
        quantity_fy2024=None,
        quantity_fy2025=None,
        quantity_fy2026_request=None,
        quantity_fy2026_total=None,
        extra_fields=None,
        pe_number=None,
        currency_year="then-year",
        appropriation_code=None,
        appropriation_title=None,
        amount_unit="thousands",
        budget_type="procurement",
    )
    defaults.update(kwargs)
    conn.execute("""
        INSERT INTO budget_lines (
            source_file, exhibit_type, sheet_name, fiscal_year,
            account, account_title, organization, organization_name,
            budget_activity, budget_activity_title,
            sub_activity, sub_activity_title,
            line_item, line_item_title, classification,
            amount_fy2024_actual, amount_fy2025_enacted,
            amount_fy2025_supplemental, amount_fy2025_total,
            amount_fy2026_request, amount_fy2026_reconciliation,
            amount_fy2026_total,
            quantity_fy2024, quantity_fy2025,
            quantity_fy2026_request, quantity_fy2026_total,
            extra_fields,
            pe_number, currency_year,
            appropriation_code, appropriation_title,
            amount_unit, budget_type
        ) VALUES (
            :source_file, :exhibit_type, :sheet_name, :fiscal_year,
            :account, :account_title, :organization, :organization_name,
            :budget_activity, :budget_activity_title,
            :sub_activity, :sub_activity_title,
            :line_item, :line_item_title, :classification,
            :amount_fy2024_actual, :amount_fy2025_enacted,
            :amount_fy2025_supplemental, :amount_fy2025_total,
            :amount_fy2026_request, :amount_fy2026_reconciliation,
            :amount_fy2026_total,
            :quantity_fy2024, :quantity_fy2025,
            :quantity_fy2026_request, :quantity_fy2026_total,
            :extra_fields,
            :pe_number, :currency_year,
            :appropriation_code, :appropriation_title,
            :amount_unit, :budget_type
        )
    """, defaults)
    conn.commit()


def _insert_ingested(conn, file_path="test/f.xlsx", file_type="xlsx",
                     row_count=5, status="ok"):
    conn.execute(
        "INSERT INTO ingested_files "
        "(file_path, file_type, file_size, file_modified, ingested_at, row_count, status) "
        "VALUES (?,?,?,?,datetime('now'),?,?)",
        (file_path, file_type, 1024, 1700000000.0, row_count, status)
    )
    conn.commit()


# ── check_missing_years ───────────────────────────────────────────────────────

def test_check_missing_years_empty_db(conn):
    """Empty DB → single 'no data' warning."""
    issues = check_missing_years(conn)
    assert len(issues) == 1
    assert issues[0]["severity"] == "warning"
    assert "No budget line data" in issues[0]["detail"]


def test_check_missing_years_no_gaps(conn):
    """All orgs have the same years → no issues."""
    for org, name in [("A", "Army"), ("N", "Navy")]:
        for fy in ("FY 2025", "FY 2026"):
            _insert_line(conn, organization=org, organization_name=name,
                         fiscal_year=fy)
    assert check_missing_years(conn) == []


def test_check_missing_years_gap_detected(conn):
    """One org missing a year that another has → issue returned."""
    _insert_line(conn, organization="A", organization_name="Army",
                 fiscal_year="FY 2025")
    _insert_line(conn, organization="A", organization_name="Army",
                 fiscal_year="FY 2026")
    _insert_line(conn, organization="N", organization_name="Navy",
                 fiscal_year="FY 2026")  # missing FY 2025
    issues = check_missing_years(conn)
    assert any("Navy" in i["detail"] for i in issues)
    navy_issue = next(i for i in issues if "Navy" in i["detail"])
    assert "FY 2025" in navy_issue["detail"]


# ── check_duplicates ──────────────────────────────────────────────────────────

def test_check_duplicates_none(conn):
    """Unique rows → no duplicates."""
    _insert_line(conn, fiscal_year="FY 2025")
    _insert_line(conn, fiscal_year="FY 2026")
    assert check_duplicates(conn) == []


def test_check_duplicates_found(conn):
    """Identical key tuples → duplicate reported."""
    for _ in range(3):
        _insert_line(conn)  # same source_file, exhibit_type, account, line_item, fiscal_year
    issues = check_duplicates(conn)
    assert len(issues) == 1
    assert issues[0]["severity"] == "error"
    assert issues[0]["count"] == 3


# ── check_zero_amounts ────────────────────────────────────────────────────────

def test_check_zero_amounts_none(conn):
    """Rows with amounts → no zero-amount issue."""
    _insert_line(conn, amount_fy2026_request=500.0)
    assert check_zero_amounts(conn) == []


def test_check_zero_amounts_flagged(conn):
    """Row with all NULL amounts → flagged."""
    _insert_line(conn,
                 amount_fy2024_actual=None,
                 amount_fy2025_enacted=None,
                 amount_fy2026_request=None)
    issues = check_zero_amounts(conn)
    assert len(issues) == 1
    assert issues[0]["total"] == 1


# ── check_column_alignment ────────────────────────────────────────────────────

def test_check_column_alignment_no_issues(conn):
    """Rows with both account and organization → no issues."""
    _insert_line(conn, account="2035", organization="A")
    assert check_column_alignment(conn) == []


def test_check_column_alignment_missing_org(conn):
    """Row with account but empty organization → flagged."""
    _insert_line(conn, account="2035", organization="", organization_name="")
    issues = check_column_alignment(conn)
    assert len(issues) == 1
    assert issues[0]["severity"] == "warning"


# ── check_unknown_exhibits ────────────────────────────────────────────────────

def test_check_unknown_exhibits_known(conn):
    """Known exhibit types → no issues."""
    _insert_line(conn, exhibit_type="p1")
    assert check_unknown_exhibits(conn) == []


def test_check_unknown_exhibits_unknown(conn):
    """Unrecognized exhibit type → info-level issue."""
    _insert_line(conn, exhibit_type="zz_unknown")
    issues = check_unknown_exhibits(conn)
    assert any(i["exhibit_type"] == "zz_unknown" for i in issues)
    assert all(i["severity"] == "info" for i in issues)


# ── check_ingestion_errors ────────────────────────────────────────────────────

def test_check_ingestion_errors_none(conn):
    """All files with status 'ok' → no issues."""
    _insert_ingested(conn, status="ok")
    assert check_ingestion_errors(conn) == []


def test_check_ingestion_errors_found(conn):
    """File with non-ok status → error-level issue."""
    _insert_ingested(conn, file_path="bad/file.xlsx", status="error: corrupt")
    issues = check_ingestion_errors(conn)
    assert len(issues) == 1
    assert issues[0]["severity"] == "error"
    assert "bad/file.xlsx" in issues[0]["detail"]


# ── check_unit_consistency ────────────────────────────────────────────────────

def test_check_unit_consistency_ok(conn):
    """All rows use 'thousands' → no issues."""
    _insert_line(conn, amount_unit="thousands")
    assert check_unit_consistency(conn) == []


def test_check_unit_consistency_flagged(conn):
    """Row with amount_unit='millions' → warning."""
    _insert_line(conn, amount_unit="millions")
    issues = check_unit_consistency(conn)
    assert len(issues) == 1
    assert issues[0]["severity"] == "warning"
    assert "millions" in issues[0]["detail"]


# ── check_empty_files ─────────────────────────────────────────────────────────

def test_check_empty_files_none(conn):
    """File with row_count > 0 → no issues."""
    _insert_ingested(conn, row_count=10, status="ok")
    assert check_empty_files(conn) == []


def test_check_empty_files_flagged(conn):
    """File with row_count = 0 → warning."""
    _insert_ingested(conn, row_count=0, status="ok")
    issues = check_empty_files(conn)
    assert len(issues) == 1
    assert issues[0]["severity"] == "warning"
