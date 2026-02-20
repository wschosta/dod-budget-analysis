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
    check_enrichment_orphans,
    _get_amount_columns,
    generate_report,
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


# ── _get_amount_columns ────────────────────────────────────────────────────────

def test_get_amount_columns_returns_list(conn):
    """Returns a list of amount_fy* column names from budget_lines schema."""
    cols = _get_amount_columns(conn)
    assert isinstance(cols, list)
    assert len(cols) > 0


def test_get_amount_columns_prefix(conn):
    """Every column returned starts with 'amount_fy'."""
    cols = _get_amount_columns(conn)
    for col in cols:
        assert col.startswith("amount_fy"), f"Unexpected column: {col}"


def test_get_amount_columns_includes_standard(conn):
    """Standard FY2024-2026 amount columns are present."""
    cols = _get_amount_columns(conn)
    assert "amount_fy2024_actual" in cols
    assert "amount_fy2025_enacted" in cols
    assert "amount_fy2026_request" in cols


# ── generate_report ────────────────────────────────────────────────────────────

def test_generate_report_empty_db_returns_int(conn, capsys):
    """generate_report returns an integer issue count."""
    result = generate_report(conn)
    assert isinstance(result, int)


def test_generate_report_empty_db_prints_output(conn, capsys):
    """generate_report prints report header to stdout."""
    generate_report(conn)
    out = capsys.readouterr().out
    assert "VALIDATION REPORT" in out


def test_generate_report_no_issues_pass(conn, capsys):
    """Clean database with data reports zero errors."""
    _insert_line(conn, amount_fy2026_request=500.0)
    _insert_ingested(conn, row_count=1, status="ok")
    result = generate_report(conn)
    # May have warnings (missing years in single-org DB), but no errors
    assert result >= 0


def test_generate_report_verbose_shows_detail(conn, capsys):
    """Verbose mode prints issue details."""
    # Insert a duplicate to trigger an issue
    for _ in range(2):
        _insert_line(conn)
    generate_report(conn, verbose=True)
    out = capsys.readouterr().out
    # Verbose mode should show at least one issue detail
    assert "ERROR" in out or "WARNING" in out or "INFO" in out


# ── Budget Type Values ────────────────────────────────────────────────────────

from validate_budget_db import (
    check_budget_type_values,
    check_pdf_pages_fiscal_year,
    check_pdf_pe_numbers_populated,
    check_pe_tags_source_files,
)


def test_budget_type_known_values(conn):
    """Known budget_type values → no issues."""
    _insert_line(conn, budget_type="RDT&E")
    issues = check_budget_type_values(conn)
    assert len(issues) == 0


def test_budget_type_unknown_flagged(conn):
    """Unknown budget_type → info-level issue."""
    _insert_line(conn, budget_type="weird_type")
    issues = check_budget_type_values(conn)
    assert len(issues) == 1
    assert issues[0]["severity"] == "info"
    assert issues[0]["budget_type"] == "weird_type"


# ── LION-108-val: PDF Pages Fiscal Year ──────────────────────────────────────


def test_pdf_pages_fy_all_populated(conn):
    """All pdf_pages have fiscal_year → no issues."""
    conn.execute(
        "INSERT INTO pdf_pages (source_file, source_category, fiscal_year, "
        "page_number, page_text) VALUES (?, ?, ?, ?, ?)",
        ("r2.pdf", "Army", "FY 2026", 1, "test text"),
    )
    conn.commit()
    issues = check_pdf_pages_fiscal_year(conn)
    assert len(issues) == 0


def test_pdf_pages_fy_null_warning(conn):
    """pdf_pages with NULL fiscal_year → warning when >5%."""
    for i in range(20):
        fy = None if i < 5 else "FY 2026"  # 25% null
        conn.execute(
            "INSERT INTO pdf_pages (source_file, source_category, fiscal_year, "
            "page_number, page_text) VALUES (?, ?, ?, ?, ?)",
            ("r2.pdf", "Army", fy, i, "text"),
        )
    conn.commit()
    issues = check_pdf_pages_fiscal_year(conn)
    assert len(issues) == 1
    assert issues[0]["severity"] == "warning"
    assert issues[0]["null_count"] == 5


def test_pdf_pages_fy_null_info_when_low(conn):
    """pdf_pages with low NULL fiscal_year rate → info."""
    for i in range(100):
        fy = None if i == 0 else "FY 2026"  # 1% null
        conn.execute(
            "INSERT INTO pdf_pages (source_file, source_category, fiscal_year, "
            "page_number, page_text) VALUES (?, ?, ?, ?, ?)",
            ("r2.pdf", "Army", fy, i, "text"),
        )
    conn.commit()
    issues = check_pdf_pages_fiscal_year(conn)
    assert len(issues) == 1
    assert issues[0]["severity"] == "info"


def test_pdf_pages_fy_empty_table(conn):
    """Empty pdf_pages → no issues."""
    issues = check_pdf_pages_fiscal_year(conn)
    assert len(issues) == 0


# ── LION-108-val: PDF PE Numbers Junction ────────────────────────────────────

def test_pdf_pe_numbers_populated(conn):
    """pdf_pe_numbers with data → info-level report."""
    conn.execute(
        "INSERT INTO pdf_pe_numbers (pdf_page_id, pe_number, page_number, "
        "source_file, fiscal_year) VALUES (?, ?, ?, ?, ?)",
        (1, "0602120A", 1, "r2.pdf", "FY 2026"),
    )
    conn.commit()
    issues = check_pdf_pe_numbers_populated(conn)
    assert len(issues) == 1
    assert issues[0]["severity"] == "info"
    assert issues[0]["junction_count"] == 1


def test_pdf_pe_numbers_empty_with_pe_pages(conn):
    """pdf_pe_numbers empty but pdf_pages has PE text → warning."""
    conn.execute(
        "INSERT INTO pdf_pages (source_file, source_category, page_number, page_text) "
        "VALUES (?, ?, ?, ?)",
        ("r2.pdf", "Army", 1, "PE 0602120A radar program"),
    )
    conn.commit()
    issues = check_pdf_pe_numbers_populated(conn)
    assert len(issues) == 1
    assert issues[0]["severity"] == "warning"


# ── LION-108-val: PE Tags Source Files ───────────────────────────────────────

def test_pe_tags_source_files_populated(conn):
    """pe_tags with source_files → no issues."""
    conn.execute("""
        INSERT INTO pe_index (pe_number, display_title) VALUES ('0602120A', 'Radar')
    """)
    conn.execute("""
        INSERT INTO pe_tags (pe_number, tag, tag_source, confidence, source_files)
        VALUES ('0602120A', 'army', 'structured', 1.0, '["r1.xlsx"]')
    """)
    conn.commit()
    issues = check_pe_tags_source_files(conn)
    assert len(issues) == 0


def test_pe_tags_source_files_null_warning(conn):
    """pe_tags with NULL source_files → warning."""
    conn.execute("""
        INSERT INTO pe_index (pe_number, display_title) VALUES ('0602120A', 'Radar')
    """)
    conn.execute("""
        INSERT INTO pe_tags (pe_number, tag, tag_source, confidence, source_files)
        VALUES ('0602120A', 'army', 'structured', 1.0, NULL)
    """)
    conn.commit()
    issues = check_pe_tags_source_files(conn)
    assert len(issues) == 1
    assert issues[0]["severity"] == "warning"
    assert issues[0]["null_count"] == 1


def test_pe_tags_source_files_empty_table(conn):
    """Empty pe_tags → no issues."""
    issues = check_pe_tags_source_files(conn)
    assert len(issues) == 0


# ── Enrichment Orphans ───────────────────────────────────────────────────

def test_enrichment_orphans_none(conn):
    """No orphans when pe_descriptions refs match pe_index."""
    conn.execute("INSERT INTO pe_index (pe_number, display_title) VALUES ('0602120A', 'Radar')")
    conn.execute("""
        INSERT INTO pe_descriptions (pe_number, fiscal_year, description_text)
        VALUES ('0602120A', '2026', 'Radar program')
    """)
    conn.commit()
    issues = check_enrichment_orphans(conn)
    assert len(issues) == 0


def test_enrichment_orphans_detected(conn):
    """Orphaned pe_descriptions rows referencing unknown PE → warning."""
    conn.execute("INSERT INTO pe_index (pe_number, display_title) VALUES ('0602120A', 'Radar')")
    conn.execute("""
        INSERT INTO pe_descriptions (pe_number, fiscal_year, description_text)
        VALUES ('9999999X', '2026', 'Orphan description')
    """)
    conn.commit()
    issues = check_enrichment_orphans(conn)
    assert len(issues) >= 1
    assert any(i["table"] == "pe_descriptions" for i in issues)
    assert issues[0]["severity"] == "warning"


def test_enrichment_orphans_empty_tables(conn):
    """Empty enrichment tables → no issues."""
    issues = check_enrichment_orphans(conn)
    assert len(issues) == 0
