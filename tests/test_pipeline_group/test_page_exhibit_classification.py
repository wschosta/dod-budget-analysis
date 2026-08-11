"""Per-page exhibit identification for PDF pages.

`pdf_pages.exhibit_type` is derived from the filename, which makes it a *book*
level label stamped onto every page. A `PROC_*.pdf` procurement book is marked
"p5" from cover to back, but measured across the corpus that bucket is 25%
P-3A, 17% P-40, 12% P-21 and only 9% genuinely Exhibit P-5. Anything that
filters on it — a parser, a search facet, an enrichment phase — is working on
a label that is wrong for most rows.

Justification books print their exhibit in a header on nearly every page, so
the page can identify itself. `page_exhibit_type` records that, and is NULL
where a page genuinely has no exhibit header (contents pages, narrative
continuations) rather than guessing.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from pipeline.schema import migrate  # noqa: E402
from utils.patterns import (  # noqa: E402
    PAGE_EXHIBIT_SCAN_CHARS,
    classify_page_exhibit,
    normalize_exhibit_label,
)


class TestNormalizeExhibitLabel:
    @pytest.mark.parametrize("raw,expected", [
        ("P-40", "p40"),
        ("R-2A", "r2a"),
        ("P-5", "p5"),
        ("OP-32A", "op32a"),
        ("PBA-19", "pba19"),
    ])
    def test_matches_corpus_convention(self, raw, expected):
        """Existing exhibit_type values are lowercase with no hyphen."""
        assert normalize_exhibit_label(raw) == expected


class TestClassifyPageExhibit:
    @pytest.mark.parametrize("text,expected", [
        ("Exhibit P-40, Budget Line Item Justification: PB 2024", "p40"),
        ("UNCLASSIFIED\nExhibit R-2A, RDT&E Project Justification", "r2a"),
        ("Exhibit P-5, Cost Analysis: PB 2026 Navy", "p5"),
        ("Exhibit P-21, Production Schedule: PB 2026 Navy", "p21"),
        ("Exhibit OP-5 In-House Care DHP", "op5"),
    ])
    def test_reads_the_header_a_page_prints(self, text, expected):
        assert classify_page_exhibit(text) == expected

    def test_matches_bare_om_codes_without_the_word_exhibit(self):
        """O&M books print OP-32/PB-24 style codes with no "Exhibit" prefix."""
        assert classify_page_exhibit(
            "OP-32A Summary of Price and Program Growth DHP PB24"
        ) == "op32a"

    @pytest.mark.parametrize("text", [
        "",
        None,
        "Table of Contents\nDefense-wide\nOffice of the Inspector General 50",
        "THIS PAGE INTENTIONALLY LEFT BLANK",
    ])
    def test_returns_none_rather_than_guessing(self, text):
        """A page with no exhibit header is unclassified, not mislabelled."""
        assert classify_page_exhibit(text) is None

    def test_ignores_cross_references_deep_in_body_text(self):
        """Only the header counts — "see Exhibit P-5" in prose must not win.

        Scanning the whole page would relabel narrative pages after any
        mention of another exhibit.
        """
        page = "Table of Contents\n" + ("filler line\n" * 400) + "see Exhibit P-5 for detail"
        assert len(page) > PAGE_EXHIBIT_SCAN_CHARS
        assert classify_page_exhibit(page) is None

    def test_first_header_wins_when_a_page_names_several(self):
        text = "Exhibit P-40, Budget Line Item Justification\nrefer also to Exhibit P-5"
        assert classify_page_exhibit(text) == "p40"


class TestMigration7:
    def test_adds_page_exhibit_type_column(self, tmp_path):
        db = tmp_path / "m7.sqlite"
        conn = sqlite3.connect(str(db))
        conn.executescript("""
            CREATE TABLE pdf_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT NOT NULL,
                source_category TEXT,
                fiscal_year TEXT,
                exhibit_type TEXT,
                page_number INTEGER,
                page_text TEXT,
                has_tables INTEGER DEFAULT 0,
                table_data TEXT
            );
        """)
        conn.commit()
        migrate(conn)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(pdf_pages)")}
        conn.close()
        assert "page_exhibit_type" in cols

    def test_migration_is_idempotent(self, tmp_path):
        """ALTER TABLE ADD COLUMN fails if applied twice — version must gate it."""
        db = tmp_path / "m7b.sqlite"
        conn = sqlite3.connect(str(db))
        conn.executescript("""
            CREATE TABLE pdf_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT NOT NULL, source_category TEXT,
                fiscal_year TEXT, exhibit_type TEXT, page_number INTEGER,
                page_text TEXT, has_tables INTEGER DEFAULT 0, table_data TEXT
            );
        """)
        conn.commit()
        migrate(conn)
        second = migrate(conn)  # must be a no-op, not an error
        conn.close()
        assert second == 0


class TestBackfillStep:
    @pytest.fixture()
    def db_with_pages(self, tmp_path):
        db = tmp_path / "backfill.sqlite"
        conn = sqlite3.connect(str(db))
        conn.executescript("""
            CREATE TABLE pdf_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT NOT NULL, source_category TEXT,
                fiscal_year TEXT, exhibit_type TEXT, page_number INTEGER,
                page_text TEXT, has_tables INTEGER DEFAULT 0, table_data TEXT,
                page_exhibit_type TEXT
            );
            INSERT INTO pdf_pages (source_file, exhibit_type, page_number, page_text)
            VALUES
              ('PROC_X.pdf','p5',1,'Exhibit P-40, Budget Line Item Justification'),
              ('PROC_X.pdf','p5',2,'Exhibit P-21, Production Schedule'),
              ('PROC_X.pdf','p5',3,'THIS PAGE INTENTIONALLY LEFT BLANK'),
              ('APN_Book.pdf','p5',4,'Exhibit P-5, Cost Analysis');
        """)
        conn.commit()
        conn.row_factory = sqlite3.Row
        return conn

    def test_backfills_only_pages_with_headers(self, db_with_pages):
        from repair_database import step_16_classify_page_exhibits
        n = step_16_classify_page_exhibits(db_with_pages)
        assert n == 3  # the blank page stays NULL
        rows = {r["page_number"]: r["page_exhibit_type"]
                for r in db_with_pages.execute(
                    "SELECT page_number, page_exhibit_type FROM pdf_pages")}
        assert rows == {1: "p40", 2: "p21", 3: None, 4: "p5"}

    def test_book_level_label_is_left_untouched(self, db_with_pages):
        """exhibit_type is what existing queries and tests filter on."""
        from repair_database import step_16_classify_page_exhibits
        step_16_classify_page_exhibits(db_with_pages)
        kinds = {r[0] for r in db_with_pages.execute(
            "SELECT DISTINCT exhibit_type FROM pdf_pages")}
        assert kinds == {"p5"}

    def test_rerun_is_a_no_op(self, db_with_pages):
        from repair_database import step_16_classify_page_exhibits
        step_16_classify_page_exhibits(db_with_pages)
        assert step_16_classify_page_exhibits(db_with_pages) == 0

    def test_dry_run_writes_nothing(self, db_with_pages):
        from repair_database import step_16_classify_page_exhibits
        step_16_classify_page_exhibits(db_with_pages, dry_run=True)
        remaining = db_with_pages.execute(
            "SELECT COUNT(*) FROM pdf_pages WHERE page_exhibit_type IS NOT NULL"
        ).fetchone()[0]
        assert remaining == 0

    def test_skips_gracefully_before_migration_7(self, tmp_path):
        """Repair may run against a database that predates the column."""
        from repair_database import step_16_classify_page_exhibits
        conn = sqlite3.connect(str(tmp_path / "old.sqlite"))
        conn.executescript(
            "CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY, page_text TEXT);"
        )
        conn.row_factory = sqlite3.Row
        assert step_16_classify_page_exhibits(conn) == 0
        conn.close()
