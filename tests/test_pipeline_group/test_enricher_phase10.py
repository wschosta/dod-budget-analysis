"""Tests for enricher Phase 10 — R-2 metadata backfill."""

import sqlite3

import pytest

from pipeline.enricher import run_phase10


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create minimal budget_lines + pdf_pages tables for phase 10 testing."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS budget_lines (
            rowid INTEGER PRIMARY KEY,
            pe_number TEXT,
            exhibit_type TEXT,
            fiscal_year TEXT,
            source_file TEXT,
            sheet_name TEXT,
            line_item_title TEXT,
            organization_name TEXT,
            budget_activity TEXT,
            budget_activity_title TEXT,
            appropriation_title TEXT,
            amount_fy2025_total REAL
        );
        CREATE TABLE IF NOT EXISTS pdf_pages (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            page_number INTEGER,
            page_text TEXT,
            fiscal_year TEXT,
            exhibit_type TEXT,
            has_tables INTEGER DEFAULT 0
        );
    """)


@pytest.fixture
def phase10_db(tmp_path):
    """In-memory database with R-1 and R-2 test rows."""
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(db_path))
    _create_schema(conn)

    # R-1 row with full metadata
    conn.execute("""
        INSERT INTO budget_lines
            (pe_number, exhibit_type, fiscal_year, line_item_title,
             budget_activity_title, appropriation_title)
        VALUES ('0603273F', 'r1', '2025', 'Weaponization Technology',
                'BA 3: Advanced Technology Development',
                'Research, Development, Test & Eval, Air Force')
    """)

    # R-2 PDF rows missing metadata — same PE as R-1 above
    conn.execute("""
        INSERT INTO budget_lines
            (pe_number, exhibit_type, fiscal_year, source_file, sheet_name,
             line_item_title, budget_activity_title, appropriation_title)
        VALUES ('0603273F', 'r2_pdf', '2025', 'RDTE_AF.pdf', 'page_5',
                'Hypersonic Strike', NULL, NULL)
    """)

    # R-2 PDF row with NO R-1 match — will need Tier 2 or 3
    conn.execute("""
        INSERT INTO budget_lines
            (pe_number, exhibit_type, fiscal_year, source_file, sheet_name,
             line_item_title, budget_activity_title, appropriation_title)
        VALUES ('0605456A', 'r2_pdf', '2025', 'RDTE_Army.pdf', 'page_10',
                'Missile Defense', NULL, NULL)
    """)

    # R-2 PDF row already populated — should NOT be overwritten
    conn.execute("""
        INSERT INTO budget_lines
            (pe_number, exhibit_type, fiscal_year, source_file, sheet_name,
             line_item_title, budget_activity_title, appropriation_title)
        VALUES ('0601102F', 'r2_pdf', '2025', 'RDTE_AF.pdf', 'page_1',
                'Basic Research', 'BA 1: Basic Research', 'Already Set')
    """)

    # PDF page for Tier 2 testing (matches 0605456A row)
    conn.execute("""
        INSERT INTO pdf_pages
            (source_file, page_number, page_text, fiscal_year, exhibit_type)
        VALUES ('RDTE_Army.pdf', 10,
                'BUDGET ACTIVITY: 5\nAppropriation: 2040 / Research, Development, Test & Eval, Army\nCOST ($ in Millions)\n...',
                '2025', 'r2')
    """)

    conn.commit()
    yield conn
    conn.close()


class TestPhase10Tier1:
    """Tier 1: R-1 cross-reference."""

    def test_inherits_ba_from_r1(self, phase10_db):
        run_phase10(phase10_db)
        row = phase10_db.execute(
            "SELECT budget_activity_title FROM budget_lines "
            "WHERE pe_number = '0603273F' AND exhibit_type = 'r2_pdf'"
        ).fetchone()
        assert row[0] == "BA 3: Advanced Technology Development"

    def test_inherits_appropriation_from_r1(self, phase10_db):
        run_phase10(phase10_db)
        row = phase10_db.execute(
            "SELECT appropriation_title FROM budget_lines "
            "WHERE pe_number = '0603273F' AND exhibit_type = 'r2_pdf'"
        ).fetchone()
        assert row[0] == "Research, Development, Test & Eval, Air Force"


class TestPhase10Tier2:
    """Tier 2: PDF header parsing."""

    def test_ba_from_pdf_header(self, phase10_db):
        run_phase10(phase10_db)
        row = phase10_db.execute(
            "SELECT budget_activity_title FROM budget_lines "
            "WHERE pe_number = '0605456A' AND exhibit_type = 'r2_pdf'"
        ).fetchone()
        assert row[0] == "BA 5: System Development & Demonstration"

    def test_appropriation_from_pdf_header(self, phase10_db):
        run_phase10(phase10_db)
        row = phase10_db.execute(
            "SELECT appropriation_title FROM budget_lines "
            "WHERE pe_number = '0605456A' AND exhibit_type = 'r2_pdf'"
        ).fetchone()
        assert row[0] == "Research, Development, Test & Eval, Army"


class TestPhase10Tier3:
    """Tier 3: PE number inference."""

    def test_ba_from_pe_number(self, phase10_db):
        # Add a row with no R-1 match and no PDF page match
        phase10_db.execute("""
            INSERT INTO budget_lines
                (pe_number, exhibit_type, fiscal_year, source_file, sheet_name,
                 line_item_title, budget_activity_title, appropriation_title)
            VALUES ('0602750N', 'r2_pdf', '2025', 'unknown.pdf', 'page_99',
                    'Some Project', NULL, NULL)
        """)
        phase10_db.commit()

        run_phase10(phase10_db)
        row = phase10_db.execute(
            "SELECT budget_activity_title FROM budget_lines "
            "WHERE pe_number = '0602750N' AND exhibit_type = 'r2_pdf'"
        ).fetchone()
        assert row[0] == "BA 2: Applied Research"


class TestPhase10Idempotency:
    """Already-populated fields must not be overwritten."""

    def test_does_not_overwrite_existing(self, phase10_db):
        run_phase10(phase10_db)
        row = phase10_db.execute(
            "SELECT budget_activity_title, appropriation_title FROM budget_lines "
            "WHERE pe_number = '0601102F' AND exhibit_type = 'r2_pdf'"
        ).fetchone()
        assert row[0] == "BA 1: Basic Research"
        assert row[1] == "Already Set"

    def test_returns_zero_on_second_run(self, phase10_db):
        run_phase10(phase10_db)
        result = run_phase10(phase10_db)
        assert result == 0
