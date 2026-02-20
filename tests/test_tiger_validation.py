"""
Tests for TIGER validation checks (TIGER-001 through TIGER-007).

Tests each new check function against a minimal in-memory SQLite database.
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

from build_budget_db import create_database  # noqa: E402
from validate_budget_db import (  # noqa: E402
    check_yoy_budget_anomalies,
    check_appropriation_title_consistency,
    check_line_item_rollups,
    check_referential_integrity,
    check_expected_fy_columns,
    check_pdf_extraction_quality,
    generate_json_report,
    generate_html_report,
    _exceeds_threshold,
)


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def conn(tmp_path):
    """Empty database with full schema, row_factory set for dict-like access."""
    db = tmp_path / "test.sqlite"
    c = create_database(db)
    c.row_factory = sqlite3.Row
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


def _insert_pdf_page(conn, source_file="test/doc.pdf", page_number=1,
                     page_text="This is a normal page with enough text content.",
                     has_tables=0, table_data=None):
    conn.execute(
        "INSERT INTO pdf_pages (source_file, source_category, page_number, "
        "page_text, has_tables, table_data) VALUES (?, ?, ?, ?, ?, ?)",
        (source_file, "test", page_number, page_text, has_tables, table_data),
    )
    conn.commit()


# ── TIGER-001: YoY Budget Anomalies ─────────────────────────────────────────

class TestCheckYoyBudgetAnomalies:
    def test_no_anomalies(self, conn):
        """Normal changes (within 10x) → no issues."""
        _insert_line(conn, amount_fy2024_actual=100.0, amount_fy2025_enacted=150.0,
                     amount_fy2026_request=200.0)
        issues = check_yoy_budget_anomalies(conn)
        assert issues == []

    def test_anomaly_detected(self, conn):
        """Change > 10x → flagged as warning."""
        _insert_line(conn, amount_fy2024_actual=1.0, amount_fy2025_enacted=100.0,
                     amount_fy2026_request=120.0)
        issues = check_yoy_budget_anomalies(conn)
        # 1.0 → 100.0 is a 100x change which exceeds 10x threshold
        assert any(i["check"] == "yoy_budget_anomalies" for i in issues)
        anomaly = next(i for i in issues if i["check"] == "yoy_budget_anomalies")
        assert anomaly["severity"] == "warning"

    def test_empty_db(self, conn):
        """Empty DB → no issues."""
        assert check_yoy_budget_anomalies(conn) == []


# ── TIGER-002: Appropriation Title Consistency ───────────────────────────────

class TestCheckAppropriationTitleConsistency:
    def test_consistent_titles(self, conn):
        """Same account code always has same title → no issues."""
        _insert_line(conn, account="2035", account_title="Aircraft Procurement")
        _insert_line(conn, account="2035", account_title="Aircraft Procurement",
                     fiscal_year="FY 2025")
        issues = check_appropriation_title_consistency(conn)
        assert issues == []

    def test_inconsistent_titles_detected(self, conn):
        """Same account code with different titles → warning."""
        _insert_line(conn, account="2035", account_title="Aircraft Procurement")
        _insert_line(conn, account="2035", account_title="Aircraft Procurement, Army",
                     fiscal_year="FY 2025")
        issues = check_appropriation_title_consistency(conn)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert issues[0]["account"] == "2035"
        assert issues[0]["title_count"] == 2

    def test_empty_db(self, conn):
        """Empty DB → no issues."""
        assert check_appropriation_title_consistency(conn) == []


# ── TIGER-003: Line Item Rollups ─────────────────────────────────────────────

class TestCheckLineItemRollups:
    def test_matching_rollups(self, conn):
        """Detail items sum matches total row → no issues."""
        _insert_line(conn, budget_activity_title="Combat Aircraft",
                     amount_fy2026_total=500.0)
        _insert_line(conn, budget_activity_title="Total",
                     amount_fy2026_total=500.0)
        issues = check_line_item_rollups(conn)
        assert issues == []

    def test_rollup_mismatch_detected(self, conn):
        """Detail sum does not match total → warning (if diff > $1M)."""
        # Detail row with large amount
        _insert_line(conn, budget_activity_title="Combat Aircraft",
                     amount_fy2026_total=100000.0)
        # Total row claiming much more
        _insert_line(conn, budget_activity_title="Grand Total",
                     amount_fy2026_total=200000.0)
        issues = check_line_item_rollups(conn)
        # Difference of 100,000 ($100M) > threshold of 1000 ($1M)
        rollup_issues = [i for i in issues if i["check"] == "line_item_rollups"]
        assert len(rollup_issues) > 0
        assert rollup_issues[0]["severity"] == "warning"

    def test_empty_db(self, conn):
        """Empty DB → no issues."""
        assert check_line_item_rollups(conn) == []


# ── TIGER-004: Referential Integrity ─────────────────────────────────────────

class TestCheckReferentialIntegrity:
    def test_no_lookup_tables(self, conn):
        """When lookup tables don't exist → gracefully returns empty (no crash)."""
        _insert_line(conn)
        issues = check_referential_integrity(conn)
        # Should not crash even without services_agencies/exhibit_types tables
        assert isinstance(issues, list)

    def test_orphaned_org_detected(self, conn):
        """Organization not in services_agencies → error."""
        # Create the lookup table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS services_agencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                full_name TEXT NOT NULL,
                category TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO services_agencies (code, full_name, category) "
            "VALUES ('Navy', 'Department of the Navy', 'military')"
        )
        conn.commit()
        # Insert a budget line with org not in lookup
        _insert_line(conn, organization_name="Army")
        issues = check_referential_integrity(conn)
        org_issues = [i for i in issues if i.get("table") == "services_agencies"]
        assert len(org_issues) >= 1
        assert org_issues[0]["severity"] == "error"

    def test_orphaned_exhibit_detected(self, conn):
        """Exhibit type not in exhibit_types → error."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exhibit_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                exhibit_class TEXT NOT NULL,
                description TEXT
            )
        """)
        conn.execute(
            "INSERT INTO exhibit_types (code, display_name, exhibit_class) "
            "VALUES ('r1', 'RDT&E Summary', 'rdte')"
        )
        conn.commit()
        _insert_line(conn, exhibit_type="p1")
        issues = check_referential_integrity(conn)
        exhibit_issues = [i for i in issues if i.get("table") == "exhibit_types"]
        assert len(exhibit_issues) >= 1
        assert exhibit_issues[0]["severity"] == "error"
        assert exhibit_issues[0]["missing_value"] == "p1"

    def test_complete_references(self, conn):
        """All references exist → no issues."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS services_agencies (
                id INTEGER PRIMARY KEY, code TEXT UNIQUE, full_name TEXT, category TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS exhibit_types (
                id INTEGER PRIMARY KEY, code TEXT UNIQUE, display_name TEXT,
                exhibit_class TEXT, description TEXT
            )
        """)
        conn.execute("INSERT INTO services_agencies (code, full_name, category) "
                     "VALUES ('Army', 'Department of the Army', 'military')")
        conn.execute("INSERT INTO exhibit_types (code, display_name, exhibit_class) "
                     "VALUES ('p1', 'Procurement P-1', 'procurement')")
        conn.commit()
        _insert_line(conn, organization_name="Army", exhibit_type="p1")
        issues = check_referential_integrity(conn)
        assert issues == []


# ── TIGER-005: Expected FY Columns ──────────────────────────────────────────

class TestCheckExpectedFyColumns:
    def test_complete_schema(self, conn):
        """Standard schema has all expected columns → no issues."""
        issues = check_expected_fy_columns(conn)
        assert issues == []

    def test_missing_column(self, conn):
        """Schema missing an expected column → error."""
        # Create a minimal budget_lines table missing some columns
        conn2 = sqlite3.connect(":memory:")
        conn2.row_factory = sqlite3.Row
        conn2.execute("""
            CREATE TABLE budget_lines (
                id INTEGER PRIMARY KEY,
                amount_fy2024_actual REAL,
                amount_fy2025_enacted REAL,
                amount_fy2026_request REAL
            )
        """)
        issues = check_expected_fy_columns(conn2)
        assert len(issues) == 1
        assert issues[0]["severity"] == "error"
        assert "missing_columns" in issues[0]
        # Should report missing columns
        assert "amount_fy2025_supplemental" in issues[0]["missing_columns"]
        conn2.close()


# ── TIGER-006: PDF Extraction Quality ────────────────────────────────────────

class TestCheckPdfExtractionQuality:
    def test_no_pdf_pages(self, conn):
        """Empty pdf_pages → no issues."""
        issues = check_pdf_extraction_quality(conn)
        assert issues == []

    def test_good_quality(self, conn):
        """All pages have sufficient text → info severity (score >= 0.9)."""
        for i in range(10):
            _insert_pdf_page(conn, page_number=i,
                             page_text="A" * 100)  # 100 chars > 50 threshold
        issues = check_pdf_extraction_quality(conn)
        assert len(issues) == 1
        assert issues[0]["severity"] == "info"
        assert issues[0]["pdf_quality_score"] >= 0.9

    def test_poor_quality(self, conn):
        """Many short-text pages → warning severity (score < 0.9)."""
        # 8 bad pages, 2 good pages
        for i in range(8):
            _insert_pdf_page(conn, page_number=i, page_text="Hi")
        for i in range(8, 10):
            _insert_pdf_page(conn, page_number=i,
                             page_text="A" * 100)
        issues = check_pdf_extraction_quality(conn)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert issues[0]["pdf_quality_score"] < 0.9

    def test_empty_table_data(self, conn):
        """Pages with has_tables=1 but empty table_data → counted as bad."""
        _insert_pdf_page(conn, page_text="A" * 100, has_tables=1, table_data="")
        issues = check_pdf_extraction_quality(conn)
        assert len(issues) == 1
        assert issues[0]["empty_table_pages"] == 1


# ── TIGER-007: Report export improvements ────────────────────────────────────

class TestReportExport:
    def test_json_report_includes_pdf_quality_score(self, conn):
        """JSON report includes pdf_quality_score when PDF pages exist."""
        _insert_pdf_page(conn, page_text="A" * 100)
        _insert_ingested(conn)
        report = generate_json_report(conn)
        assert "pdf_quality_score" in report

    def test_html_report_generates(self, conn):
        """HTML report generates valid HTML string."""
        _insert_line(conn)
        _insert_ingested(conn)
        html = generate_html_report(conn)
        assert "<!DOCTYPE html>" in html
        assert "DoD Budget Validation Report" in html
        assert "<table" in html

    def test_html_report_severity_colors(self, conn):
        """HTML report includes severity-based styling."""
        _insert_line(conn)
        _insert_ingested(conn)
        html = generate_html_report(conn)
        assert "sev-error" in html or "sev-warning" in html or "sev-info" in html

    def test_exceeds_threshold_error(self):
        """Error threshold only triggers on errors."""
        report = {
            "checks": [
                {"issues": [{"severity": "warning"}]},
                {"issues": [{"severity": "info"}]},
            ]
        }
        assert not _exceeds_threshold(report, "error")
        report["checks"].append({"issues": [{"severity": "error"}]})
        assert _exceeds_threshold(report, "error")

    def test_exceeds_threshold_warning(self):
        """Warning threshold triggers on warnings and errors."""
        report = {
            "checks": [
                {"issues": [{"severity": "info"}]},
            ]
        }
        assert not _exceeds_threshold(report, "warning")
        report["checks"].append({"issues": [{"severity": "warning"}]})
        assert _exceeds_threshold(report, "warning")

    def test_exceeds_threshold_info(self):
        """Info threshold triggers on any issue."""
        report = {
            "checks": [
                {"issues": [{"severity": "info"}]},
            ]
        }
        assert _exceeds_threshold(report, "info")
