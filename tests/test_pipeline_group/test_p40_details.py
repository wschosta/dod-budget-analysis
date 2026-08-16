"""Persisting P-40 detail that the Excel P-1 rows do not carry.

P-40 funding is deliberately not merged into budget_lines — reconciliation
showed 89.5% agreement with structural exceptions, so P-1 stays authoritative
for line-item money. What P-40 uniquely has is stored instead: the out-year
horizon, quantities, the Code B program element, and the printed line item
title, keyed so they join to budget_lines rather than compete with it.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.p40_details import populate_p40_details  # noqa: E402
from pipeline.p40_positional import P40HeaderColumns  # noqa: E402
from pipeline.schema import migrate  # noqa: E402

PAGE = """UNCLASSIFIED
Exhibit P-40, Budget Line Item Justification: PB 2024 Defense Counterintelligence and Security Agency Date: March 2023
Appropriation / Budget Activity / Budget Sub Activity: P-1 Line Item Number / Title:
0300D: Procurement, Defense-Wide / BA 01: Major Equipment / BSA 9: Major 20 / Major Equipment, DCSA
ID Code (A=Service Ready, B=Not Service Ready): Program Elements for Code B Items: 0901220SE Other Related Program Elements: N/A
Prior FY 2024 FY 2024 FY 2024 To
Resource Summary Years FY 2022 FY 2023 Base OCO Total FY 2025 FY 2026 FY 2027 FY 2028 Complete Total
Procurement Quantity (Units in Each) 4 2 1 3 - 3 1 1 1 1 - 14
Net Procurement (P-1) ($ in Millions) 21.909 3.014 2.346 2.135 - 2.135 2.187 2.233 2.279 2.327 Continuing Continuing
Description:
"""


@pytest.fixture()
def db(tmp_path):
    """A database with one P-40 page recorded in pdf_pages."""
    path = tmp_path / "p40.sqlite"
    conn = sqlite3.connect(str(path))
    conn.executescript("""
        CREATE TABLE pdf_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT, source_category TEXT, fiscal_year TEXT,
            exhibit_type TEXT, page_exhibit_type TEXT, page_number INTEGER,
            page_text TEXT, has_tables INTEGER DEFAULT 0, table_data TEXT
        );
    """)
    conn.execute(
        "INSERT INTO pdf_pages (source_file, page_exhibit_type, page_number, page_text)"
        " VALUES ('FY2024/PB/x/PROC_DCSA.pdf', 'p40', 17, ?)", (PAGE,),
    )
    conn.commit()
    migrate(conn)
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def fake_pdf():
    """Stand in for pdfplumber: the line item comes from word coordinates."""
    class _Page:
        pass

    class _PDF:
        pages = [_Page() for _ in range(20)]

        def close(self):
            pass

    cols = P40HeaderColumns(
        line_item="20", line_item_title="Major Equipment, DCSA",
        raw_right_column="20 / Major Equipment, DCSA",
    )
    with patch("pdfplumber.open", return_value=_PDF()), \
         patch("pipeline.p40_details.extract_header_columns", return_value=cols):
        yield


def _rows(path, sql):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql)]
    finally:
        conn.close()


class TestPopulate:
    def test_stores_the_line_item_with_its_join_key(self, db, fake_pdf, tmp_path):
        summary = populate_p40_details(db, tmp_path)
        assert summary["details"] == 1

        row = _rows(db, "SELECT * FROM p40_line_details")[0]
        assert row["account"] == "0300D"
        assert row["sub_activity"] == "9"       # disambiguates multi-agency items
        assert row["line_item"] == "20"
        assert row["fiscal_year"] == "2024"

    def test_keeps_what_excel_lacks(self, db, fake_pdf, tmp_path):
        populate_p40_details(db, tmp_path)
        row = _rows(db, "SELECT * FROM p40_line_details")[0]
        assert row["pe_number"] == "0901220SE"          # Code B link to RDT&E
        assert row["line_item_title"] == "Major Equipment, DCSA"

        amounts = {r["column_label"]: r for r in _rows(db, "SELECT * FROM p40_line_amounts")}
        # Out-years: the whole point — budget_lines has no FY2028 column.
        assert amounts["fy2028"]["amount"] == pytest.approx(2327.0)
        assert amounts["fy2025"]["amount"] == pytest.approx(2187.0)

    def test_amounts_are_thousands_not_millions(self, db, fake_pdf, tmp_path):
        """P-40 prints millions; the rest of the database stores thousands."""
        populate_p40_details(db, tmp_path)
        amounts = {r["column_label"]: r["amount"] for r in _rows(db, "SELECT * FROM p40_line_amounts")}
        assert amounts["prior_years"] == pytest.approx(21_909.0)

    def test_quantities_are_kept_alongside_amounts(self, db, fake_pdf, tmp_path):
        populate_p40_details(db, tmp_path)
        rows = {r["column_label"]: r for r in _rows(db, "SELECT * FROM p40_line_amounts")}
        assert rows["prior_years"]["quantity"] == pytest.approx(4.0)
        assert rows["fy2024_base"]["quantity"] == pytest.approx(3.0)

    def test_continuing_is_flagged_not_stored_as_zero(self, db, fake_pdf, tmp_path):
        """"Continuing" means funding runs past the horizon, not that it is 0."""
        populate_p40_details(db, tmp_path)
        rows = {r["column_label"]: r for r in _rows(db, "SELECT * FROM p40_line_amounts")}
        assert rows["to_complete"]["amount"] is None
        assert rows["to_complete"]["is_continuing"] == 1
        assert rows["fy2024_oco"]["is_continuing"] == 0   # "-" is absent, not continuing

    def test_rerun_rebuilds_rather_than_accumulating(self, db, fake_pdf, tmp_path):
        first = populate_p40_details(db, tmp_path)
        second = populate_p40_details(db, tmp_path)
        assert first == second
        assert len(_rows(db, "SELECT id FROM p40_line_details")) == 1


class TestSkips:
    def test_page_without_a_line_item_is_skipped_not_stored(self, db, tmp_path):
        """A null key would collapse unrelated line items onto one row."""
        class _PDF:
            pages = [object() for _ in range(20)]

            def close(self):
                pass

        with patch("pdfplumber.open", return_value=_PDF()), \
             patch("pipeline.p40_details.extract_header_columns",
                   return_value=P40HeaderColumns()):
            summary = populate_p40_details(db, tmp_path)

        assert summary["details"] == 0
        assert summary["skipped_no_line_item"] == 1
        assert _rows(db, "SELECT * FROM p40_line_details") == []

    def test_unreadable_book_does_not_abort_the_run(self, db, tmp_path):
        with patch("pdfplumber.open", side_effect=OSError("corrupt")):
            summary = populate_p40_details(db, tmp_path)
        assert summary["skipped_no_line_item"] == 1
        assert summary["details"] == 0


class TestMissingBsaStillDeduplicates:
    """A missing BSA must not defeat the UNIQUE key.

    SQLite treats NULLs as distinct in a UNIQUE constraint, so storing NULL
    for the 616 Navy line items that print no BSA meant the same line item was
    written once per page instead of once. Empty string collides properly.
    """

    def test_same_line_item_twice_yields_one_row(self, db, tmp_path):
        import sqlite3 as _sqlite3
        from unittest.mock import patch as _patch

        # A second page for the same line item, as a Navy book would produce.
        conn = _sqlite3.connect(str(db))
        page_no_bsa = PAGE.replace("/ BSA 9: Major 20 /", "/ 20 /")
        conn.execute(
            "INSERT INTO pdf_pages (source_file, page_exhibit_type, page_number, page_text)"
            " VALUES ('FY2024/PB/x/PROC_DCSA.pdf', 'p40', 18, ?)", (page_no_bsa,),
        )
        conn.execute(
            "UPDATE pdf_pages SET page_text = ? WHERE page_number = 17", (page_no_bsa,),
        )
        conn.commit()
        conn.close()

        class _PDF:
            pages = [object() for _ in range(20)]

            def close(self):
                pass

        cols = P40HeaderColumns(line_item="20", line_item_title="Major Equipment, DCSA")
        with _patch("pdfplumber.open", return_value=_PDF()), \
             _patch("pipeline.p40_details.extract_header_columns", return_value=cols):
            populate_p40_details(db, tmp_path)

        rows = _rows(db, "SELECT account, sub_activity, line_item, fiscal_year FROM p40_line_details")
        assert len(rows) == 1, f"missing BSA defeated the UNIQUE key: {rows}"
        assert rows[0]["sub_activity"] == ""
