"""
Tests for PDF quality audit script — Step 1.B5-a

Tests the quality detection logic using an in-memory SQLite database
with controlled test data. No real PDFs or downloaded corpus required.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from pdf_quality_audit import (
    _non_ascii_ratio,
    _whitespace_line_ratio,
    _classify_source_file,
    audit_pdf_quality,
    generate_report,
)


class TestNonAsciiRatio:
    def test_all_ascii(self):
        assert _non_ascii_ratio("Hello World") == 0.0

    def test_empty_string(self):
        assert _non_ascii_ratio("") == 0.0

    def test_mixed(self):
        # 2 non-ASCII out of 7 chars total
        ratio = _non_ascii_ratio("AB\u00e9CD\u00f1F")
        assert 0.2 < ratio < 0.4

    def test_all_non_ascii(self):
        assert _non_ascii_ratio("\u00e9\u00f1\u00fc") == 1.0


class TestWhitespaceLineRatio:
    def test_no_whitespace_lines(self):
        assert _whitespace_line_ratio("line1\nline2\nline3") == 0.0

    def test_all_whitespace(self):
        assert _whitespace_line_ratio("\n\n\n") == 1.0

    def test_mixed(self):
        ratio = _whitespace_line_ratio("data\n\nmore data\n")
        # 4 lines: "data", "", "more data", "" -> 2/4 = 0.5
        assert ratio == 0.5

    def test_empty_string(self):
        assert _whitespace_line_ratio("") == 1.0


class TestClassifySourceFile:
    def test_army(self):
        assert _classify_source_file("DoD/FY2026/US_Army/p1.pdf") == "Army"

    def test_navy(self):
        assert _classify_source_file("DoD/FY2026/Navy/r1.pdf") == "Navy"

    def test_air_force(self):
        assert _classify_source_file("DoD/FY2026/Air_Force/o1.pdf") == "Air Force"

    def test_comptroller(self):
        assert _classify_source_file("DoD/Comptroller/summary.pdf") == "Comptroller"

    def test_unknown(self):
        assert _classify_source_file("misc/budget.pdf") == "Other"


@pytest.fixture()
def pdf_db(tmp_path):
    """Create a temporary database with pdf_pages for audit tests."""
    db_path = tmp_path / "test_audit.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE pdf_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            source_category TEXT,
            page_number INTEGER,
            page_text TEXT,
            has_tables INTEGER DEFAULT 0,
            table_data TEXT
        )
    """)
    # Good page
    conn.execute("""
        INSERT INTO pdf_pages (source_file, page_number, page_text, has_tables, table_data)
        VALUES ('Army/budget.pdf', 1,
                'Department of the Army Budget Justification FY2026 Procurement',
                0, NULL)
    """)
    # Bad page: high non-ASCII
    conn.execute("""
        INSERT INTO pdf_pages (source_file, page_number, page_text, has_tables, table_data)
        VALUES ('Navy/garbled.pdf', 3,
                '\u00e9\u00f1\u00fc\u00e9\u00f1\u00fc\u00e9\u00f1\u00fc\u00e9\u00f1\u00fc\u00e9\u00f1\u00fc\u00e9\u00f1ABC',
                0, NULL)
    """)
    # Bad page: very short text
    conn.execute("""
        INSERT INTO pdf_pages (source_file, page_number, page_text, has_tables, table_data)
        VALUES ('Air_Force/cover.pdf', 1, 'Page 1', 0, NULL)
    """)
    # Bad page: tables flagged but empty
    conn.execute("""
        INSERT INTO pdf_pages (source_file, page_number, page_text, has_tables, table_data)
        VALUES ('Defense_Wide/tables.pdf', 5,
                'Table of Contents for Defense Agency Budget Materials FY2026',
                1, '')
    """)
    # Bad page: mostly whitespace
    conn.execute("""
        INSERT INTO pdf_pages (source_file, page_number, page_text, has_tables, table_data)
        VALUES ('Comptroller/ws.pdf', 2,
                'Header\n\n\n\n\n\n\n\n\n\nFooter',
                0, NULL)
    """)
    conn.commit()
    conn.close()
    return db_path


class TestAuditPdfQuality:
    def test_detects_flagged_pages(self, pdf_db):
        result = audit_pdf_quality(pdf_db)
        assert result["total_pages"] == 5
        assert len(result["flagged_pages"]) >= 3  # at least 3 bad pages

    def test_good_page_not_flagged(self, pdf_db):
        result = audit_pdf_quality(pdf_db)
        flagged_files = [p["source_file"] for p in result["flagged_pages"]]
        assert "Army/budget.pdf" not in flagged_files

    def test_short_text_detected(self, pdf_db):
        result = audit_pdf_quality(pdf_db)
        flagged_files = [p["source_file"] for p in result["flagged_pages"]]
        assert "Air_Force/cover.pdf" in flagged_files

    def test_empty_table_data_detected(self, pdf_db):
        result = audit_pdf_quality(pdf_db)
        flagged_files = [p["source_file"] for p in result["flagged_pages"]]
        assert "Defense_Wide/tables.pdf" in flagged_files

    def test_summary_by_issue_populated(self, pdf_db):
        result = audit_pdf_quality(pdf_db)
        assert "very_short_text" in result["summary_by_issue"]

    def test_summary_by_source_populated(self, pdf_db):
        result = audit_pdf_quality(pdf_db)
        assert len(result["summary_by_source"]) > 0


class TestGenerateReport:
    def test_produces_markdown(self, pdf_db):
        result = audit_pdf_quality(pdf_db)
        report = generate_report(result)
        assert "# PDF Extraction Quality Audit Report" in report
        assert "Summary" in report

    def test_empty_db_produces_report(self, tmp_path):
        db_path = tmp_path / "empty.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE pdf_pages (
                id INTEGER PRIMARY KEY, source_file TEXT,
                source_category TEXT, page_number INTEGER,
                page_text TEXT, has_tables INTEGER, table_data TEXT
            )
        """)
        conn.commit()
        conn.close()
        result = audit_pdf_quality(db_path)
        report = generate_report(result)
        assert "No quality issues" in report
