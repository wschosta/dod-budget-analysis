"""
Tests for enrich_budget_db.py — all five enrichment phases.

Uses in-memory SQLite databases to avoid touching the real DB.
"""
from __future__ import annotations

import json
import sqlite3
import threading

import pytest

from pipeline.enricher import (
    run_phase1,
    run_phase2,
    run_phase3,
    run_phase4,
    run_phase5,
    _extract_fy_from_path,
    _extract_pe_title_from_text,
    _context_window,
    _tags_from_keywords,
    _get_checkpoint,
    _save_checkpoint,
    _drop_enrichment_tables,
    _EXHIBIT_TO_BUDGET_TYPE,
    _MIN_TEXT_FOR_NAME_MATCH,
    _MAX_NAME_MATCHES_PER_ROW,
    _MIN_TITLE_WORDS,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_db() -> sqlite3.Connection:
    """Create an in-memory DB with all required tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            exhibit_type TEXT,
            fiscal_year TEXT,
            account TEXT,
            account_title TEXT,
            organization TEXT,
            organization_name TEXT,
            budget_activity TEXT,
            budget_activity_title TEXT,
            sub_activity TEXT,
            sub_activity_title TEXT,
            line_item TEXT,
            line_item_title TEXT,
            pe_number TEXT,
            budget_type TEXT,
            appropriation_title TEXT,
            amount_fy2024_actual REAL,
            amount_fy2025_enacted REAL,
            amount_fy2025_total REAL,
            amount_fy2026_request REAL,
            amount_fy2026_total REAL,
            quantity_fy2024 REAL,
            quantity_fy2025 REAL,
            quantity_fy2026_request REAL,
            extra_fields TEXT
        );

        CREATE TABLE pdf_pages (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            source_category TEXT,
            fiscal_year TEXT,
            exhibit_type TEXT,
            page_number INTEGER,
            page_text TEXT,
            has_tables INTEGER DEFAULT 0,
            table_data TEXT
        );

        CREATE TABLE pe_index (
            pe_number TEXT PRIMARY KEY,
            display_title TEXT,
            organization_name TEXT,
            budget_type TEXT,
            fiscal_years TEXT,
            exhibit_types TEXT,
            source TEXT NOT NULL DEFAULT 'budget_lines',
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE pdf_pe_numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT NOT NULL,
            page_number INTEGER,
            source_file TEXT,
            fiscal_year TEXT,
            pdf_page_id INTEGER REFERENCES pdf_pages(id)
        );
        CREATE INDEX IF NOT EXISTS idx_ppn_pe ON pdf_pe_numbers(pe_number);

        CREATE TABLE pe_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT NOT NULL,
            fiscal_year TEXT,
            source_file TEXT,
            page_start INTEGER,
            page_end INTEGER,
            section_header TEXT,
            description_text TEXT
        );

        CREATE TABLE pe_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT NOT NULL,
            project_number TEXT,
            tag TEXT NOT NULL,
            tag_source TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            source_files TEXT,
            UNIQUE(pe_number, project_number, tag, tag_source)
        );

        CREATE TABLE pe_lineage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_pe TEXT NOT NULL,
            referenced_pe TEXT NOT NULL,
            fiscal_year TEXT,
            source_file TEXT,
            page_number INTEGER,
            context_snippet TEXT,
            link_type TEXT NOT NULL,
            confidence REAL DEFAULT 0.5,
            UNIQUE(source_pe, referenced_pe, link_type, fiscal_year)
        );

        CREATE TABLE project_descriptions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number        TEXT NOT NULL,
            project_number   TEXT,
            project_title    TEXT,
            fiscal_year      TEXT,
            section_header   TEXT NOT NULL,
            description_text TEXT NOT NULL,
            source_file      TEXT,
            page_start       INTEGER,
            page_end         INTEGER,
            created_at       TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_proj_desc_pe ON project_descriptions(pe_number);
        CREATE INDEX IF NOT EXISTS idx_proj_desc_proj ON project_descriptions(project_number);
        CREATE INDEX IF NOT EXISTS idx_proj_desc_fy ON project_descriptions(fiscal_year);
    """)
    return conn


@pytest.fixture()
def conn():
    db = _make_db()
    yield db
    db.close()


def _insert_budget_line(conn, pe_number="0602120A", fiscal_year="2026",
                         exhibit_type="r1", org="Army",
                         title="Radar Technology", ba_title="6.2 Applied Research",
                         approp_title="Research, Development, Test and Evaluation, Army"):
    conn.execute("""
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             budget_activity_title, line_item_title, pe_number,
             budget_type, appropriation_title)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("army/r1.xlsx", exhibit_type, fiscal_year, org,
          ba_title, title, pe_number, "rdte", approp_title))
    conn.commit()


def _insert_pdf_page(conn, source_file="army/FY2026/r2_army.pdf",
                     page_number=1, page_text="",
                     source_category="Army", exhibit_type=None) -> int:
    """Insert a pdf_pages row and return its id."""
    cur = conn.execute("""
        INSERT INTO pdf_pages
            (source_file, source_category, page_number, page_text, exhibit_type)
        VALUES (?, ?, ?, ?, ?)
    """, (source_file, source_category, page_number, page_text, exhibit_type))
    conn.commit()
    return cur.lastrowid


def _insert_pdf_pe_number(conn, pe_number: str, pdf_page_id: int,
                          page_number: int = 1,
                          source_file: str = "army/FY2026/r2_army.pdf",
                          fiscal_year: str | None = "2026"):
    """Insert a pdf_pe_numbers junction row."""
    conn.execute("""
        INSERT INTO pdf_pe_numbers
            (pe_number, page_number, source_file, fiscal_year, pdf_page_id)
        VALUES (?, ?, ?, ?, ?)
    """, (pe_number, page_number, source_file, fiscal_year, pdf_page_id))
    conn.commit()


# ── Phase 1 tests ─────────────────────────────────────────────────────────────

class TestPhase1:
    def test_empty_budget_lines(self, conn):
        count = run_phase1(conn)
        assert count == 0
        assert conn.execute("SELECT COUNT(*) FROM pe_index").fetchone()[0] == 0

    def test_single_pe(self, conn):
        _insert_budget_line(conn, pe_number="0602120A", fiscal_year="2026")
        count = run_phase1(conn)
        assert count == 1
        row = conn.execute("SELECT * FROM pe_index WHERE pe_number = '0602120A'").fetchone()
        assert row is not None
        assert row["display_title"] == "Radar Technology"
        assert row["organization_name"] == "Army"
        assert row["source"] == "budget_lines"
        assert "2026" in json.loads(row["fiscal_years"])
        assert "r1" in json.loads(row["exhibit_types"])

    def test_multiple_fiscal_years(self, conn):
        _insert_budget_line(conn, fiscal_year="2025")
        _insert_budget_line(conn, fiscal_year="2026")
        run_phase1(conn)
        row = conn.execute("SELECT * FROM pe_index WHERE pe_number = '0602120A'").fetchone()
        fy_list = json.loads(row["fiscal_years"])
        assert "2025" in fy_list
        assert "2026" in fy_list

    def test_multiple_pes(self, conn):
        _insert_budget_line(conn, pe_number="0602120A")
        _insert_budget_line(conn, pe_number="0603000A", title="Fighter Aircraft")
        count = run_phase1(conn)
        assert count == 2
        assert conn.execute("SELECT COUNT(*) FROM pe_index").fetchone()[0] == 2

    def test_upsert_on_rerun(self, conn):
        _insert_budget_line(conn)
        run_phase1(conn)
        run_phase1(conn)  # second run should not raise or duplicate
        assert conn.execute("SELECT COUNT(*) FROM pe_index").fetchone()[0] == 1

    def test_null_pe_excluded(self, conn):
        conn.execute("""
            INSERT INTO budget_lines (source_file, exhibit_type, fiscal_year,
                organization_name, line_item_title, pe_number, budget_type)
            VALUES ('x.xlsx', 'r1', '2026', 'Army', 'Unknown', NULL, 'rdte')
        """)
        conn.commit()
        count = run_phase1(conn)
        assert count == 0


# ── Phase 1 PDF-only PE tests ────────────────────────────────────────────────

class TestPhase1PdfOnly:
    """Tests for Pass 2 of Phase 1: PDF-only PE discovery."""

    def test_indexes_pdf_only_pes(self, conn):
        """PEs in pdf_pe_numbers but not in budget_lines are indexed with source='pdf'."""
        # PE A in budget_lines, PEs A and B in pdf_pe_numbers
        _insert_budget_line(conn, pe_number="0602120A")
        page_id = _insert_pdf_page(conn, page_text="PE 0602120A content",
                                   exhibit_type="r2")
        _insert_pdf_pe_number(conn, "0602120A", page_id)
        page_id2 = _insert_pdf_page(conn, page_text="PE 0603999BR: DARPA Special Program content",
                                    source_file="darpa/FY2026/r2_darpa.pdf",
                                    source_category="Defense-Wide", exhibit_type="r2",
                                    page_number=2)
        _insert_pdf_pe_number(conn, "0603999BR", page_id2, page_number=2,
                              source_file="darpa/FY2026/r2_darpa.pdf")

        count = run_phase1(conn)
        assert count == 2

        # A should be from budget_lines
        row_a = conn.execute(
            "SELECT source FROM pe_index WHERE pe_number = '0602120A'"
        ).fetchone()
        assert row_a["source"] == "budget_lines"

        # B should be from pdf
        row_b = conn.execute(
            "SELECT * FROM pe_index WHERE pe_number = '0603999BR'"
        ).fetchone()
        assert row_b is not None
        assert row_b["source"] == "pdf"

    def test_title_extraction(self, conn):
        """Title is extracted from PDF text patterns like 'PE XXXXXXXA: Title'."""
        page_id = _insert_pdf_page(
            conn, page_text="PE 0602702F: Advanced Radar Technology Development",
            source_file="af/FY2026/r2_af.pdf", source_category="Air Force",
            exhibit_type="r2",
        )
        _insert_pdf_pe_number(conn, "0602702F", page_id,
                              source_file="af/FY2026/r2_af.pdf")
        run_phase1(conn)

        row = conn.execute(
            "SELECT display_title FROM pe_index WHERE pe_number = '0602702F'"
        ).fetchone()
        assert row is not None
        assert row["display_title"] == "Advanced Radar Technology Development"

    def test_no_title_fallback(self, conn):
        """PE with no recognizable title pattern gets NULL display_title."""
        page_id = _insert_pdf_page(
            conn, page_text="Some text mentioning 0603999BR in passing",
            source_file="dw/FY2026/r2_dw.pdf", source_category="Defense-Wide",
        )
        _insert_pdf_pe_number(conn, "0603999BR", page_id,
                              source_file="dw/FY2026/r2_dw.pdf")
        run_phase1(conn)

        row = conn.execute(
            "SELECT display_title FROM pe_index WHERE pe_number = '0603999BR'"
        ).fetchone()
        assert row is not None
        assert row["display_title"] is None

    def test_does_not_overwrite_budget_lines_pe(self, conn):
        """PE in both budget_lines and pdf_pe_numbers keeps budget_lines data."""
        _insert_budget_line(conn, pe_number="0602120A", title="Excel Title")
        page_id = _insert_pdf_page(
            conn, page_text="PE 0602120A: PDF Title from narrative",
        )
        _insert_pdf_pe_number(conn, "0602120A", page_id)

        run_phase1(conn)

        row = conn.execute(
            "SELECT display_title, source FROM pe_index WHERE pe_number = '0602120A'"
        ).fetchone()
        # budget_lines version should win (Pass 1 INSERT OR REPLACE, Pass 2 INSERT OR IGNORE)
        assert row["source"] == "budget_lines"
        assert row["display_title"] == "Excel Title"

    def test_org_inference(self, conn):
        """Organization is inferred from pdf_pages.source_category."""
        page_id = _insert_pdf_page(
            conn, page_text="PE 0603999BR: Special Ops Program",
            source_file="army/FY2026/r2_army.pdf",
            source_category="Army", exhibit_type="r2",
        )
        _insert_pdf_pe_number(conn, "0603999BR", page_id,
                              source_file="army/FY2026/r2_army.pdf")
        run_phase1(conn)

        row = conn.execute(
            "SELECT organization_name FROM pe_index WHERE pe_number = '0603999BR'"
        ).fetchone()
        assert row["organization_name"] == "Army"

    def test_budget_type_inference(self, conn):
        """Budget type is inferred from exhibit type of source PDF pages."""
        page_id = _insert_pdf_page(
            conn, page_text="PE 0603999BR: Special Research Program",
            source_file="dw/FY2026/r2_dw.pdf",
            source_category="Defense-Wide", exhibit_type="r2",
        )
        _insert_pdf_pe_number(conn, "0603999BR", page_id,
                              source_file="dw/FY2026/r2_dw.pdf")
        run_phase1(conn)

        row = conn.execute(
            "SELECT budget_type FROM pe_index WHERE pe_number = '0603999BR'"
        ).fetchone()
        assert row["budget_type"] == "RDT&E"

    def test_phase2_processes_pdf_only_pes(self, conn):
        """After Phase 1 indexes a PDF-only PE, Phase 2 creates pe_descriptions for it."""
        page_id = _insert_pdf_page(
            conn,
            page_text=(
                "PE 0603999BR: Special Research Program\n"
                "Accomplishments/Planned Programs\n"
                "In FY2026, the program completed prototype testing."
            ),
            source_file="dw/FY2026/r2_dw.pdf",
            source_category="Defense-Wide", exhibit_type="r2",
        )
        _insert_pdf_pe_number(conn, "0603999BR", page_id,
                              source_file="dw/FY2026/r2_dw.pdf")

        run_phase1(conn)
        # Verify it's indexed
        assert conn.execute(
            "SELECT COUNT(*) FROM pe_index WHERE pe_number = '0603999BR'"
        ).fetchone()[0] == 1

        count = run_phase2(conn)
        assert count > 0
        desc = conn.execute(
            "SELECT * FROM pe_descriptions WHERE pe_number = '0603999BR'"
        ).fetchone()
        assert desc is not None

    def test_phase3_tags_pdf_only_pes(self, conn):
        """A PDF-only PE with narrative text about 'hypersonic' gets the tag."""
        page_id = _insert_pdf_page(
            conn,
            page_text=(
                "PE 0603999BR: Hypersonic Strike Program\n"
                "The program develops hypersonic glide vehicle technology."
            ),
            source_file="dw/FY2026/r2_dw.pdf",
            source_category="Defense-Wide", exhibit_type="r2",
        )
        _insert_pdf_pe_number(conn, "0603999BR", page_id,
                              source_file="dw/FY2026/r2_dw.pdf")

        run_phase1(conn)
        run_phase2(conn)
        run_phase3(conn, with_llm=False)

        tags = [r["tag"] for r in conn.execute(
            "SELECT tag FROM pe_tags WHERE pe_number = '0603999BR'"
        ).fetchall()]
        assert "hypersonic" in tags

    def test_empty_pdf_pe_numbers(self, conn):
        """Pass 2 produces 0 when pdf_pe_numbers is empty."""
        _insert_budget_line(conn)
        count = run_phase1(conn)
        assert count == 1  # Only Pass 1 PE
        assert conn.execute("SELECT COUNT(*) FROM pe_index").fetchone()[0] == 1


# ── Phase 2 tests ─────────────────────────────────────────────────────────────

class TestPhase2:
    def test_no_pdf_pages(self, conn):
        _insert_budget_line(conn)
        run_phase1(conn)
        count = run_phase2(conn)
        assert count == 0

    def test_pe_found_in_page_text(self, conn):
        _insert_budget_line(conn, pe_number="0602120A")
        run_phase1(conn)
        text = (
            "Program Element: 0602120A\n"
            "Accomplishments/Planned Program\n"
            "In FY2026, the program completed radar prototype testing and "
            "demonstrated 95% detection rate against low-observable targets."
        )
        _insert_pdf_page(conn, page_text=text)
        count = run_phase2(conn)
        assert count > 0
        row = conn.execute("SELECT * FROM pe_descriptions WHERE pe_number = '0602120A'").fetchone()
        assert row is not None
        assert "radar" in row["description_text"].lower()

    def test_unknown_pe_skipped(self, conn):
        # PE in PDF but not in pe_index → should be skipped
        run_phase1(conn)  # pe_index empty
        _insert_pdf_page(conn, page_text="PE 0602120A mentioned here")
        count = run_phase2(conn)
        assert count == 0

    def test_fiscal_year_extracted_from_path(self, conn):
        _insert_budget_line(conn, pe_number="0602120A")
        run_phase1(conn)
        _insert_pdf_page(conn, source_file="army/FY2026/r2.pdf",
                         page_text="0602120A radar technology development")
        run_phase2(conn)
        row = conn.execute("SELECT fiscal_year FROM pe_descriptions LIMIT 1").fetchone()
        assert row["fiscal_year"] == "2026"

    def test_incremental_skips_done_files(self, conn):
        _insert_budget_line(conn, pe_number="0602120A")
        run_phase1(conn)
        _insert_pdf_page(conn, source_file="army/FY2026/r2.pdf",
                         page_text="0602120A program description text")
        run_phase2(conn)
        count_after_first = conn.execute("SELECT COUNT(*) FROM pe_descriptions").fetchone()[0]
        run_phase2(conn)  # second run — same file already done
        count_after_second = conn.execute("SELECT COUNT(*) FROM pe_descriptions").fetchone()[0]
        assert count_after_first == count_after_second


# ── Phase 3 tests ─────────────────────────────────────────────────────────────

class TestPhase3:
    def _setup(self, conn, text="hypersonic glide vehicle technology development"):
        _insert_budget_line(conn, pe_number="0602120A",
                            ba_title="6.2 Applied Research",
                            approp_title="Research, Development, Test and Evaluation, Army",
                            org="Army")
        run_phase1(conn)
        conn.execute("""
            INSERT INTO pe_descriptions (pe_number, fiscal_year, source_file,
                page_start, page_end, description_text)
            VALUES ('0602120A', '2026', 'army/r2.pdf', 1, 1, ?)
        """, (text,))
        conn.commit()

    def test_structured_tags_service(self, conn):
        self._setup(conn)
        run_phase3(conn, with_llm=False)
        tags = [r["tag"] for r in conn.execute(
            "SELECT tag FROM pe_tags WHERE pe_number = '0602120A' AND tag_source = 'structured'"
        ).fetchall()]
        assert "army" in tags

    def test_structured_tags_approp(self, conn):
        self._setup(conn)
        run_phase3(conn, with_llm=False)
        tags = [r["tag"] for r in conn.execute(
            "SELECT tag FROM pe_tags WHERE pe_number = '0602120A' AND tag_source = 'structured'"
        ).fetchall()]
        assert "rdte" in tags

    def test_structured_tags_ba(self, conn):
        self._setup(conn)
        run_phase3(conn, with_llm=False)
        tags = [r["tag"] for r in conn.execute(
            "SELECT tag FROM pe_tags WHERE pe_number = '0602120A' AND tag_source = 'structured'"
        ).fetchall()]
        assert "applied-research" in tags

    def test_keyword_tag_hypersonic(self, conn):
        self._setup(conn, text="hypersonic glide vehicle")
        run_phase3(conn, with_llm=False)
        tags = [r["tag"] for r in conn.execute(
            "SELECT tag FROM pe_tags WHERE pe_number = '0602120A' AND tag_source = 'keyword'"
        ).fetchall()]
        assert "hypersonic" in tags

    def test_keyword_tag_cyber(self, conn):
        self._setup(conn, text="cybersecurity resilience program")
        run_phase3(conn, with_llm=False)
        tag_names = [r["tag"] for r in conn.execute(
            "SELECT tag FROM pe_tags WHERE pe_number = '0602120A'"
        ).fetchall()]
        assert "cyber" in tag_names

    def test_incremental_skips_tagged_pes(self, conn):
        self._setup(conn)
        run_phase3(conn, with_llm=False)
        count1 = conn.execute("SELECT COUNT(*) FROM pe_tags").fetchone()[0]
        run_phase3(conn, with_llm=False)
        count2 = conn.execute("SELECT COUNT(*) FROM pe_tags").fetchone()[0]
        assert count1 == count2  # no duplicates added


# ── Phase 4 tests ─────────────────────────────────────────────────────────────

class TestPhase4:
    def _setup(self, conn):
        for pe, title in [("0602120A", "Radar Technology"),
                           ("0603000A", "Fighter Systems")]:
            _insert_budget_line(conn, pe_number=pe, title=title)
        run_phase1(conn)

    def test_explicit_pe_ref(self, conn):
        self._setup(conn)
        # Description for 0602120A mentions 0603000A explicitly
        conn.execute("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end, description_text)
            VALUES ('0602120A', '2026', 'r2.pdf', 1, 1,
                'This program supports 0603000A through shared radar components.')
        """)
        conn.commit()
        count = run_phase4(conn)
        assert count > 0
        row = conn.execute("""
            SELECT * FROM pe_lineage
            WHERE source_pe = '0602120A' AND referenced_pe = '0603000A'
        """).fetchone()
        assert row is not None
        assert row["link_type"] == "explicit_pe_ref"
        assert row["confidence"] >= 0.9

    def test_no_self_reference(self, conn):
        self._setup(conn)
        conn.execute("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end, description_text)
            VALUES ('0602120A', '2026', 'r2.pdf', 1, 1,
                'PE 0602120A continues radar development in FY2026.')
        """)
        conn.commit()
        run_phase4(conn)
        self_refs = conn.execute("""
            SELECT * FROM pe_lineage WHERE source_pe = referenced_pe
        """).fetchall()
        assert len(self_refs) == 0

    def test_no_lineage_when_empty(self, conn):
        self._setup(conn)
        count = run_phase4(conn)
        assert count == 0

    def test_excel_co_occurrence(self, conn):
        """PE cross-references in extra_fields generate lineage rows."""
        self._setup(conn)
        import json
        # Add extra_fields with additional PE references
        conn.execute("""
            UPDATE budget_lines SET extra_fields = ?
            WHERE pe_number = '0602120A'
        """, (json.dumps({"additional_pe_numbers": ["0603000A"]}),))
        conn.commit()
        count = run_phase4(conn)
        assert count > 0
        row = conn.execute("""
            SELECT * FROM pe_lineage
            WHERE source_pe = '0602120A'
              AND referenced_pe = '0603000A'
              AND link_type = 'excel_co_occurrence'
        """).fetchone()
        assert row is not None
        assert row["confidence"] >= 0.8


# ── Phase 4 noise reduction tests ──────────────────────────────────────────────

class TestPhase4NoiseReduction:
    """Tests for Phase 4 name_match noise reduction strategies."""

    def _setup_many_pes(self, conn, count=8):
        """Insert multiple PEs with long enough titles (>= _MIN_TITLE_WORDS words)."""
        pes = []
        for i in range(count):
            pe = f"060{2000 + i:04d}A"
            # Ensure title has >= _MIN_TITLE_WORDS words
            title = f"Advanced Technology Development Program Number {i}"
            _insert_budget_line(conn, pe_number=pe, title=title)
            pes.append(pe)
        run_phase1(conn)
        return pes

    def test_short_text_skips_name_match(self, conn):
        """Strategy 1: text shorter than _MIN_TEXT_FOR_NAME_MATCH skips name_match.

        Explicit PE refs (4a) should still be found even on short text.
        """
        pes = self._setup_many_pes(conn, count=3)
        # Short text (<200 chars) that mentions pe[1] by name and pe[2] explicitly
        short_text = f"See PE {pes[1]} and Advanced Technology Development Program Number 2."
        assert len(short_text) < _MIN_TEXT_FOR_NAME_MATCH

        conn.execute("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end, description_text)
            VALUES (?, '2026', 'r2.pdf', 1, 1, ?)
        """, (pes[0], short_text))
        conn.commit()

        run_phase4(conn)

        # 4a: explicit PE ref should still be found
        explicit = conn.execute("""
            SELECT * FROM pe_lineage
            WHERE source_pe = ? AND link_type = 'explicit_pe_ref'
        """, (pes[0],)).fetchall()
        assert len(explicit) >= 1

        # 4b: name_match should NOT be found (text too short)
        name_matches = conn.execute("""
            SELECT * FROM pe_lineage
            WHERE source_pe = ? AND link_type = 'name_match'
        """, (pes[0],)).fetchall()
        assert len(name_matches) == 0

    def test_pe_density_skips_name_match(self, conn):
        """Strategy 2: text with >_MAX_PE_REFS_FOR_NAME_MATCH explicit PE refs
        skips name_match (likely a summary/listing page)."""
        pes = self._setup_many_pes(conn, count=8)
        # Build long text that mentions 6+ PEs explicitly (tabular listing)
        pe_mentions = " ".join(pes[1:7])  # 6 explicit PE refs
        long_text = (
            f"Budget Summary Table for Programs: {pe_mentions}. "
            + "Additional context " * 30  # pad to exceed _MIN_TEXT_FOR_NAME_MATCH
            + "Advanced Technology Development Program Number 7"  # title match for pes[7]
        )
        assert len(long_text) >= _MIN_TEXT_FOR_NAME_MATCH

        conn.execute("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end, description_text)
            VALUES (?, '2026', 'listing.pdf', 1, 1, ?)
        """, (pes[0], long_text))
        conn.commit()

        run_phase4(conn)

        # Explicit refs should all be found
        explicit = conn.execute("""
            SELECT COUNT(*) FROM pe_lineage
            WHERE source_pe = ? AND link_type = 'explicit_pe_ref'
        """, (pes[0],)).fetchone()[0]
        assert explicit >= 5

        # name_match should NOT be found (too many PE refs → listing page)
        name_matches = conn.execute("""
            SELECT COUNT(*) FROM pe_lineage
            WHERE source_pe = ? AND link_type = 'name_match'
        """, (pes[0],)).fetchone()[0]
        assert name_matches == 0

    def test_per_row_cap_on_name_match(self, conn):
        """Strategy 3: name_match links are capped at _MAX_NAME_MATCHES_PER_ROW per row."""
        # Create many PEs with long titles
        pes = self._setup_many_pes(conn, count=8)
        # Build text mentioning many program titles (but few explicit PE refs)
        title_mentions = ". ".join(
            f"Advanced Technology Development Program Number {i}"
            for i in range(1, 8)
        )
        long_text = (
            f"Program overview: {title_mentions}. "
            + "Additional context for length " * 10
        )
        assert len(long_text) >= _MIN_TEXT_FOR_NAME_MATCH

        conn.execute("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end, description_text)
            VALUES (?, '2026', 'overview.pdf', 1, 1, ?)
        """, (pes[0], long_text))
        conn.commit()

        run_phase4(conn)

        name_matches = conn.execute("""
            SELECT COUNT(*) FROM pe_lineage
            WHERE source_pe = ? AND link_type = 'name_match'
        """, (pes[0],)).fetchone()[0]
        assert name_matches <= _MAX_NAME_MATCHES_PER_ROW

    def test_dedup_name_match_against_explicit_pe_ref(self, conn):
        """Strategy 5: name_match is suppressed for PEs already found via
        explicit_pe_ref in the same description row."""
        pes = self._setup_many_pes(conn, count=3)
        # Text mentions pes[1] both by PE number AND by title
        long_text = (
            f"This program references {pes[1]} (Advanced Technology "
            f"Development Program Number 1) for shared components. "
            + "Additional context " * 20
        )
        assert len(long_text) >= _MIN_TEXT_FOR_NAME_MATCH

        conn.execute("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end, description_text)
            VALUES (?, '2026', 'r2.pdf', 1, 1, ?)
        """, (pes[0], long_text))
        conn.commit()

        run_phase4(conn)

        # Should have explicit_pe_ref but NOT duplicate name_match
        explicit = conn.execute("""
            SELECT COUNT(*) FROM pe_lineage
            WHERE source_pe = ? AND referenced_pe = ? AND link_type = 'explicit_pe_ref'
        """, (pes[0], pes[1])).fetchone()[0]
        assert explicit >= 1

        name_match = conn.execute("""
            SELECT COUNT(*) FROM pe_lineage
            WHERE source_pe = ? AND referenced_pe = ? AND link_type = 'name_match'
        """, (pes[0], pes[1])).fetchone()[0]
        assert name_match == 0

    def test_min_title_words_constant(self):
        """Verify _MIN_TITLE_WORDS is 5 (up from old hardcoded 4)."""
        assert _MIN_TITLE_WORDS == 5

    def test_long_text_with_few_pe_refs_allows_name_match(self, conn):
        """Verify that name_match DOES work when text is long enough, has few
        explicit PE refs, and the title is long enough."""
        pes = self._setup_many_pes(conn, count=3)
        # Long text with NO explicit PE refs but mentions pes[1]'s title
        long_text = (
            "The program leverages Advanced Technology Development Program Number 1 "
            "for shared radar component development and testing capabilities. "
            + "Additional technical context about the integration effort " * 10
        )
        assert len(long_text) >= _MIN_TEXT_FOR_NAME_MATCH

        conn.execute("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end, description_text)
            VALUES (?, '2026', 'r2.pdf', 1, 1, ?)
        """, (pes[0], long_text))
        conn.commit()

        run_phase4(conn)

        # Should find a name_match (all conditions met)
        name_matches = conn.execute("""
            SELECT COUNT(*) FROM pe_lineage
            WHERE source_pe = ? AND link_type = 'name_match'
        """, (pes[0],)).fetchone()[0]
        assert name_matches >= 1


# ── Utility function tests ────────────────────────────────────────────────────

class TestHelpers:
    def test_extract_fy_from_path(self):
        assert _extract_fy_from_path("army/FY2026/r2.pdf") == "2026"
        assert _extract_fy_from_path("navy/FY 2025/p5.pdf") == "2025"
        assert _extract_fy_from_path("no_year_here.pdf") is None

    def test_context_window_center(self):
        text = "a" * 100 + "MATCH" + "b" * 100
        snippet = _context_window(text, 102, window=20)
        assert "MATCH" in snippet

    def test_context_window_short_text(self):
        text = "short text"
        snippet = _context_window(text, 5, window=200)
        assert snippet == "short text"

    def test_tags_from_keywords_hypersonic(self):
        tags = _tags_from_keywords("0602120A", "hypersonic glide vehicle research")
        tag_names = [t[1] for t in tags]
        assert "hypersonic" in tag_names

    def test_tags_from_keywords_no_match(self):
        tags = _tags_from_keywords("0602120A", "general administrative support activities")
        assert len(tags) == 0

    def test_tags_from_keywords_multiple(self):
        tags = _tags_from_keywords("0602120A", "cyber and space satellite program")
        tag_names = [t[1] for t in tags]
        assert "cyber" in tag_names
        assert "space" in tag_names

    def test_tags_from_keywords_quantum(self):
        tags = _tags_from_keywords("0602120A", "quantum computing research for cryptography")
        tag_names = [t[1] for t in tags]
        assert "quantum" in tag_names

    def test_tags_from_keywords_microelectronics(self):
        tags = _tags_from_keywords("0602120A", "microelectronics fabrication and ASIC design")
        tag_names = [t[1] for t in tags]
        assert "microelectronics" in tag_names

    def test_tags_from_keywords_5g(self):
        tags = _tags_from_keywords("0602120A", "5G tactical network implementation")
        tag_names = [t[1] for t in tags]
        assert "5g-comms" in tag_names

    def test_tags_from_keywords_submarine(self):
        tags = _tags_from_keywords("0602120A", "submarine warfare and undersea systems")
        tag_names = [t[1] for t in tags]
        assert "submarine" in tag_names

    def test_extract_pe_title_colon(self):
        text = "PE 0602702F: Advanced Radar Technology Development\nMore text here."
        title = _extract_pe_title_from_text("0602702F", text)
        assert title == "Advanced Radar Technology Development"

    def test_extract_pe_title_slash(self):
        text = "PE 0603999BR / Special Operations Research Program\nDetails follow."
        title = _extract_pe_title_from_text("0603999BR", text)
        assert title == "Special Operations Research Program"

    def test_extract_pe_title_dash(self):
        text = "Program Element 0602120A - Tactical Radar Systems\nMore."
        title = _extract_pe_title_from_text("0602120A", text)
        assert title == "Tactical Radar Systems"

    def test_extract_pe_title_wrong_pe(self):
        text = "PE 0602702F: Advanced Radar Technology Development"
        title = _extract_pe_title_from_text("0603999BR", text)
        assert title is None

    def test_extract_pe_title_no_match(self):
        text = "No PE title pattern here, just mentions 0602702F in passing."
        title = _extract_pe_title_from_text("0602702F", text)
        assert title is None

    def test_exhibit_to_budget_type_mapping(self):
        assert _EXHIBIT_TO_BUDGET_TYPE["r1"] == "RDT&E"
        assert _EXHIBIT_TO_BUDGET_TYPE["r2"] == "RDT&E"
        assert _EXHIBIT_TO_BUDGET_TYPE["p1"] == "Procurement"
        assert _EXHIBIT_TO_BUDGET_TYPE["p5"] == "Procurement"
        assert _EXHIBIT_TO_BUDGET_TYPE["o1"] == "O&M"
        assert _EXHIBIT_TO_BUDGET_TYPE["m1"] == "MilPers"
        assert _EXHIBIT_TO_BUDGET_TYPE["c1"] == "MilCon"


# ── Phase 5 tests ─────────────────────────────────────────────────────────────

class TestPhase5:
    """Tests for Phase 5: project-level narrative decomposition."""

    def _setup_pe(self, conn, pe_number="0602120A"):
        """Insert a budget line and build pe_index for a PE."""
        _insert_budget_line(conn, pe_number=pe_number)
        run_phase1(conn)

    def _insert_pe_description(self, conn, pe_number="0602120A",
                                fiscal_year="2026",
                                source_file="army/FY2026/r2.pdf",
                                page_start=1, page_end=3,
                                section_header="Description",
                                description_text="Sample description."):
        """Insert a pe_descriptions row for Phase 5 to consume."""
        conn.execute("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end,
                 section_header, description_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (pe_number, fiscal_year, source_file, page_start, page_end,
              section_header, description_text))
        conn.commit()

    # ── Empty / missing data edge cases ───────────────────────────────────

    def test_empty_pe_descriptions(self, conn):
        """Phase 5 returns 0 when pe_descriptions is empty."""
        self._setup_pe(conn)
        count = run_phase5(conn)
        assert count == 0

    def test_null_description_text_skipped(self, conn):
        """Rows with NULL description_text are skipped (WHERE clause)."""
        self._setup_pe(conn)
        conn.execute("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end,
                 section_header, description_text)
            VALUES ('0602120A', '2026', 'army/r2.pdf', 1, 1, 'Header', NULL)
        """)
        conn.commit()
        count = run_phase5(conn)
        assert count == 0

    def test_whitespace_only_description_skipped(self, conn):
        """Descriptions containing only whitespace produce no rows."""
        self._setup_pe(conn)
        self._insert_pe_description(conn, description_text="   \n  \t  ")
        count = run_phase5(conn)
        assert count == 0

    # ── PE-level fallback (no project boundaries detected) ────────────────

    def test_pe_level_fallback_no_projects(self, conn):
        """When no project boundaries are found, text is stored with
        project_number=NULL as a PE-level fallback."""
        self._setup_pe(conn)
        text = (
            "This program develops advanced radar technology for tactical "
            "applications. The system provides 360-degree coverage with "
            "electronic scanning capabilities."
        )
        self._insert_pe_description(conn, description_text=text)
        count = run_phase5(conn)
        assert count > 0

        rows = conn.execute("""
            SELECT pe_number, project_number, project_title, description_text
            FROM project_descriptions
            WHERE pe_number = '0602120A'
        """).fetchall()
        assert len(rows) >= 1
        # All rows should have NULL project_number (PE-level fallback)
        for row in rows:
            assert row["project_number"] is None
            assert row["project_title"] is None

    def test_pe_fallback_preserves_section_header(self, conn):
        """PE-level fallback uses the original section_header or defaults
        to 'Description' when section_header is NULL."""
        self._setup_pe(conn)
        # Text without narrative section headers or project boundaries
        text = "General radar capability development and testing program."
        self._insert_pe_description(
            conn, description_text=text, section_header=None,
        )
        count = run_phase5(conn)
        assert count > 0
        row = conn.execute("""
            SELECT section_header FROM project_descriptions
            WHERE pe_number = '0602120A'
        """).fetchone()
        assert row is not None
        assert row["section_header"] == "Description"

    def test_pe_fallback_with_narrative_sections(self, conn):
        """When no project boundaries are found but narrative section headers
        exist, individual narrative sections are stored at PE level."""
        self._setup_pe(conn)
        text = (
            "Accomplishments/Planned Programs\n"
            "In FY2026, the program completed radar prototype testing and "
            "demonstrated 95% detection rate against low-observable targets. "
            "The advanced phased array antenna design exceeded requirements.\n"
            "Acquisition Strategy\n"
            "The program uses competitive prototyping through two prime "
            "contractors selected during the Milestone B competition phase. "
            "Full rate production decision expected in FY2028."
        )
        self._insert_pe_description(conn, description_text=text)
        count = run_phase5(conn)
        assert count >= 2

        rows = conn.execute("""
            SELECT section_header, project_number FROM project_descriptions
            WHERE pe_number = '0602120A'
            ORDER BY id
        """).fetchall()
        headers = [r["section_header"] for r in rows]
        assert any("Accomplishments" in h for h in headers)
        assert any("Acquisition" in h for h in headers)
        # All should be PE-level (NULL project_number)
        for r in rows:
            assert r["project_number"] is None

    # ── Project decomposition (splitting into per-project entries) ─────────

    def test_project_decomposition_single_project(self, conn):
        """A single project boundary is detected and stored with its
        project_number and project_title."""
        self._setup_pe(conn)
        text = (
            "Project Number: P101   Project Title: Advanced Targeting System\n"
            "This project develops next-generation targeting systems for "
            "precision engagement. The system integrates electro-optical "
            "and infrared sensors for all-weather operations."
        )
        self._insert_pe_description(conn, description_text=text)
        count = run_phase5(conn)
        assert count > 0

        rows = conn.execute("""
            SELECT pe_number, project_number, project_title, description_text
            FROM project_descriptions
            WHERE pe_number = '0602120A'
        """).fetchall()
        assert len(rows) >= 1
        proj_rows = [r for r in rows if r["project_number"] is not None]
        assert len(proj_rows) >= 1
        assert proj_rows[0]["project_number"] == "P101"
        assert "Advanced Targeting System" in (proj_rows[0]["project_title"] or "")

    def test_project_decomposition_multiple_projects(self, conn):
        """Multiple project boundaries result in separate rows per project."""
        self._setup_pe(conn)
        text = (
            "Project Number: P101   Project Title: Advanced Targeting System\n"
            "This project develops next-generation targeting for precision "
            "engagement with electro-optical sensors and radar integration.\n\n"
            "Project Number: P202   Project Title: Defensive Countermeasures\n"
            "This project focuses on electronic warfare countermeasures "
            "and active protection systems for ground vehicles."
        )
        self._insert_pe_description(conn, description_text=text)
        count = run_phase5(conn)
        assert count >= 2

        rows = conn.execute("""
            SELECT project_number, project_title FROM project_descriptions
            WHERE pe_number = '0602120A' AND project_number IS NOT NULL
            ORDER BY project_number
        """).fetchall()
        proj_nums = [r["project_number"] for r in rows]
        assert "P101" in proj_nums
        assert "P202" in proj_nums

    def test_project_with_narrative_subsections(self, conn):
        """Projects containing recognized narrative section headers are
        decomposed into multiple rows per project."""
        self._setup_pe(conn)
        text = (
            "Project Number: P101   Project Title: Advanced Targeting System\n"
            "Accomplishments/Planned Programs\n"
            "In FY2026, the project completed prototype testing and full "
            "system integration for the targeting pod modification program. "
            "Testing demonstrated improved detection at extended ranges.\n"
            "Acquisition Strategy\n"
            "The project uses sole-source contracting with the original "
            "equipment manufacturer for production and sustainment support. "
            "Engineering change proposals are evaluated competitively."
        )
        self._insert_pe_description(conn, description_text=text)
        count = run_phase5(conn)
        assert count >= 2

        rows = conn.execute("""
            SELECT project_number, section_header FROM project_descriptions
            WHERE pe_number = '0602120A' AND project_number = 'P101'
            ORDER BY id
        """).fetchall()
        headers = [r["section_header"] for r in rows]
        assert any("Accomplishments" in h for h in headers)
        assert any("Acquisition" in h for h in headers)

    def test_project_colon_format(self, conn):
        """'Project: 1234 - Title' format is correctly parsed."""
        self._setup_pe(conn)
        text = (
            "Project: ABC1 — Hypersonic Glide Vehicle\n"
            "This project researches hypersonic glide body aerodynamics "
            "and thermal protection systems for next-generation strike."
        )
        self._insert_pe_description(conn, description_text=text)
        count = run_phase5(conn)
        assert count > 0

        row = conn.execute("""
            SELECT project_number, project_title FROM project_descriptions
            WHERE pe_number = '0602120A' AND project_number IS NOT NULL
        """).fetchone()
        assert row is not None
        assert row["project_number"] == "ABC1"

    # ── Table schema validation ───────────────────────────────────────────

    def test_schema_columns_exist(self, conn):
        """project_descriptions table has all expected columns."""
        self._setup_pe(conn)
        self._insert_pe_description(
            conn,
            description_text="Radar technology for tactical engagement.",
        )
        run_phase5(conn)

        # Read column names from pragma
        cols_info = conn.execute(
            "PRAGMA table_info(project_descriptions)"
        ).fetchall()
        col_names = {c[1] for c in cols_info}
        expected = {
            "id", "pe_number", "project_number", "project_title",
            "fiscal_year", "section_header", "description_text",
            "source_file", "page_start", "page_end", "created_at",
        }
        assert expected.issubset(col_names)

    def test_fiscal_year_propagated(self, conn):
        """Fiscal year from pe_descriptions is propagated to project_descriptions."""
        self._setup_pe(conn)
        self._insert_pe_description(
            conn, fiscal_year="2027",
            description_text="Advanced radar prototype development and testing.",
        )
        run_phase5(conn)

        rows = conn.execute("""
            SELECT fiscal_year FROM project_descriptions
            WHERE pe_number = '0602120A'
        """).fetchall()
        assert len(rows) >= 1
        assert all(r["fiscal_year"] == "2027" for r in rows)

    def test_source_file_propagated(self, conn):
        """Source file from pe_descriptions is propagated to project_descriptions."""
        self._setup_pe(conn)
        self._insert_pe_description(
            conn, source_file="navy/FY2026/r2_navy.pdf",
            description_text="Submarine combat system integration and testing.",
        )
        run_phase5(conn)

        row = conn.execute("""
            SELECT source_file FROM project_descriptions
            WHERE pe_number = '0602120A'
        """).fetchone()
        assert row is not None
        assert row["source_file"] == "navy/FY2026/r2_navy.pdf"

    def test_page_range_propagated(self, conn):
        """Page start/end from pe_descriptions are propagated."""
        self._setup_pe(conn)
        self._insert_pe_description(
            conn, page_start=5, page_end=8,
            description_text="Electronic warfare system development program.",
        )
        run_phase5(conn)

        row = conn.execute("""
            SELECT page_start, page_end FROM project_descriptions
            WHERE pe_number = '0602120A'
        """).fetchone()
        assert row is not None
        assert row["page_start"] == 5
        assert row["page_end"] == 8

    # ── Incremental / idempotent behavior ─────────────────────────────────

    def test_incremental_skips_done_source_files(self, conn):
        """Phase 5 skips source files that are already in project_descriptions."""
        self._setup_pe(conn)
        self._insert_pe_description(
            conn,
            description_text="Radar technology research and development.",
        )
        count1 = run_phase5(conn)
        assert count1 > 0
        rows1 = conn.execute(
            "SELECT COUNT(*) FROM project_descriptions"
        ).fetchone()[0]

        # Second run should skip the same source file
        run_phase5(conn)
        rows2 = conn.execute(
            "SELECT COUNT(*) FROM project_descriptions"
        ).fetchone()[0]
        assert rows1 == rows2

    # ── Description text truncation ───────────────────────────────────────

    def test_long_description_truncated(self, conn):
        """Descriptions over 4000 chars are truncated for the fallback path."""
        self._setup_pe(conn)
        long_text = "A" * 5000
        self._insert_pe_description(conn, description_text=long_text)
        count = run_phase5(conn)
        assert count > 0

        row = conn.execute("""
            SELECT description_text FROM project_descriptions
            WHERE pe_number = '0602120A'
        """).fetchone()
        assert row is not None
        assert len(row["description_text"]) <= 4000

    def test_creates_table_if_not_exists(self, conn):
        """Phase 5 creates project_descriptions table if it does not exist."""
        # Drop the table that _make_db created
        conn.execute("DROP TABLE IF EXISTS project_descriptions")
        conn.commit()

        self._setup_pe(conn)
        self._insert_pe_description(
            conn,
            description_text="Autonomous unmanned system development.",
        )
        count = run_phase5(conn)
        assert count > 0

        # Verify the table was recreated
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "project_descriptions" in tables


# ── Checkpoint resumability tests ────────────────────────────────────────────

class TestCheckpointHelpers:
    """Tests for the checkpoint helper functions."""

    def test_get_checkpoint_empty(self, conn):
        """_get_checkpoint returns 0 when no checkpoint exists."""
        assert _get_checkpoint(conn, 4) == 0
        assert _get_checkpoint(conn, 5) == 0

    def test_save_and_get_checkpoint(self, conn):
        """_save_checkpoint stores a value that _get_checkpoint retrieves."""
        _save_checkpoint(conn, 4, 12345)
        conn.commit()
        assert _get_checkpoint(conn, 4) == 12345

    def test_checkpoint_update(self, conn):
        """_save_checkpoint overwrites a previous checkpoint for the same phase."""
        _save_checkpoint(conn, 4, 100)
        conn.commit()
        _save_checkpoint(conn, 4, 500)
        conn.commit()
        assert _get_checkpoint(conn, 4) == 500

    def test_checkpoints_independent_per_phase(self, conn):
        """Phase 4 and Phase 5 checkpoints are stored independently."""
        _save_checkpoint(conn, 4, 100)
        _save_checkpoint(conn, 5, 200)
        conn.commit()
        assert _get_checkpoint(conn, 4) == 100
        assert _get_checkpoint(conn, 5) == 200

    def test_drop_clears_checkpoints(self, conn):
        """_drop_enrichment_tables clears the checkpoints table."""
        _save_checkpoint(conn, 4, 100)
        conn.commit()
        _drop_enrichment_tables(conn)
        assert _get_checkpoint(conn, 4) == 0


class TestPhase4Checkpoint:
    """Tests for Phase 4 checkpoint-based resumability."""

    def _setup(self, conn):
        for pe, title in [("0602120A", "Radar Technology"),
                           ("0603000A", "Fighter Systems")]:
            _insert_budget_line(conn, pe_number=pe, title=title)
        run_phase1(conn)

    def test_phase4_saves_checkpoint(self, conn):
        """Phase 4 saves a checkpoint after processing rows."""
        self._setup(conn)
        conn.execute("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end, description_text)
            VALUES ('0602120A', '2026', 'r2.pdf', 1, 1,
                'This program supports 0603000A through shared radar components.')
        """)
        conn.commit()

        run_phase4(conn)

        # Checkpoint should be set to the max rowid processed
        ckpt = _get_checkpoint(conn, 4)
        assert ckpt > 0

    def test_phase4_resumes_from_checkpoint(self, conn):
        """Phase 4 only processes rows beyond the saved checkpoint."""
        self._setup(conn)
        # Insert first description row
        conn.execute("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end, description_text)
            VALUES ('0602120A', '2026', 'r2.pdf', 1, 1,
                'This program supports 0603000A through shared radar components.')
        """)
        conn.commit()

        # First run — should find a cross-reference
        count1 = run_phase4(conn)
        assert count1 > 0
        lineage_after_run1 = conn.execute("SELECT COUNT(*) FROM pe_lineage").fetchone()[0]

        # Insert a second description row (will have higher rowid)
        conn.execute("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end, description_text)
            VALUES ('0603000A', '2026', 'r2b.pdf', 2, 2,
                'This program references 0602120A for radar testing.')
        """)
        conn.commit()

        # Second run — should only process the new row, not the old one
        count2 = run_phase4(conn)
        assert count2 > 0  # found cross-ref in the new row
        lineage_after_run2 = conn.execute("SELECT COUNT(*) FROM pe_lineage").fetchone()[0]
        assert lineage_after_run2 > lineage_after_run1

    def test_phase4_no_reprocessing_when_checkpoint_current(self, conn):
        """Phase 4 returns 0 new lineage rows when checkpoint covers all rows."""
        self._setup(conn)
        conn.execute("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end, description_text)
            VALUES ('0602120A', '2026', 'r2.pdf', 1, 1,
                'This program supports 0603000A through shared radar components.')
        """)
        conn.commit()

        # First run processes everything
        run_phase4(conn)
        lineage_count = conn.execute("SELECT COUNT(*) FROM pe_lineage").fetchone()[0]

        # Second run with no new data — checkpoint skips all rows
        # (only 4c Excel co-occurrence runs, which produces 0 with no extra_fields)
        count2 = run_phase4(conn)
        assert count2 == 0
        # Lineage count unchanged
        assert conn.execute("SELECT COUNT(*) FROM pe_lineage").fetchone()[0] == lineage_count

    def test_phase4_checkpoint_with_stop_event(self, conn):
        """Phase 4 saves checkpoint when stopped via stop_event."""
        self._setup(conn)
        # Insert several rows
        for i in range(5):
            conn.execute("""
                INSERT INTO pe_descriptions
                    (pe_number, fiscal_year, source_file, page_start, page_end, description_text)
                VALUES ('0602120A', '2026', ?, ?, ?,
                    'Text mentioning 0603000A in radar description.')
            """, (f"r2_{i}.pdf", i, i))
        conn.commit()

        # Run Phase 4 fully first
        run_phase4(conn)
        ckpt_full = _get_checkpoint(conn, 4)
        assert ckpt_full > 0

        # Now add more rows and run with immediate stop
        for i in range(5, 10):
            conn.execute("""
                INSERT INTO pe_descriptions
                    (pe_number, fiscal_year, source_file, page_start, page_end, description_text)
                VALUES ('0602120A', '2026', ?, ?, ?,
                    'More text about 0603000A radar systems.')
            """, (f"r2_{i}.pdf", i, i))
        conn.commit()

        stop = threading.Event()
        stop.set()  # Already stopped before running
        run_phase4(conn, stop_event=stop)

        # Checkpoint should still be at the previous position (no new work done)
        assert _get_checkpoint(conn, 4) == ckpt_full


class TestPhase5Checkpoint:
    """Tests for Phase 5 checkpoint-based resumability."""

    def _setup_pe(self, conn, pe_number="0602120A"):
        _insert_budget_line(conn, pe_number=pe_number)
        run_phase1(conn)

    def _insert_pe_description(self, conn, pe_number="0602120A",
                                fiscal_year="2026",
                                source_file="army/FY2026/r2.pdf",
                                page_start=1, page_end=3,
                                section_header="Description",
                                description_text="Sample description."):
        conn.execute("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end,
                 section_header, description_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (pe_number, fiscal_year, source_file, page_start, page_end,
              section_header, description_text))
        conn.commit()

    def test_phase5_saves_checkpoint(self, conn):
        """Phase 5 saves a checkpoint after processing rows."""
        self._setup_pe(conn)
        self._insert_pe_description(
            conn,
            description_text="Radar technology for tactical engagement systems.",
        )
        run_phase5(conn)

        ckpt = _get_checkpoint(conn, 5)
        assert ckpt > 0

    def test_phase5_resumes_from_checkpoint(self, conn):
        """Phase 5 only processes rows beyond the saved checkpoint."""
        self._setup_pe(conn)
        self._insert_pe_description(
            conn,
            source_file="army/FY2026/r2_a.pdf",
            description_text="Radar technology for tactical systems.",
        )

        # First run
        count1 = run_phase5(conn)
        assert count1 > 0
        rows_after_run1 = conn.execute(
            "SELECT COUNT(*) FROM project_descriptions"
        ).fetchone()[0]

        # Add a new description row
        self._insert_pe_description(
            conn,
            source_file="army/FY2026/r2_b.pdf",
            description_text="Electronic warfare countermeasures development.",
        )

        # Second run — should only process the new row
        count2 = run_phase5(conn)
        assert count2 > 0
        rows_after_run2 = conn.execute(
            "SELECT COUNT(*) FROM project_descriptions"
        ).fetchone()[0]
        assert rows_after_run2 > rows_after_run1

    def test_phase5_no_reprocessing_when_checkpoint_current(self, conn):
        """Phase 5 returns 0 when checkpoint covers all rows."""
        self._setup_pe(conn)
        self._insert_pe_description(
            conn,
            description_text="Advanced radar prototype development.",
        )

        run_phase5(conn)
        rows1 = conn.execute(
            "SELECT COUNT(*) FROM project_descriptions"
        ).fetchone()[0]

        # Second run — no new data
        count2 = run_phase5(conn)
        assert count2 == 0
        rows2 = conn.execute(
            "SELECT COUNT(*) FROM project_descriptions"
        ).fetchone()[0]
        assert rows1 == rows2
