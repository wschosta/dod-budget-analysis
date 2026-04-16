"""Tests for Phase 11 — P-5 PDF header BLI↔PE mining.

Covers:
    * Extraction: records (bli_key, pe_number) pairs when both appear in the
      first ~1,500 chars of a P-5 page.
    * Confidence policy: 0.9 for single-PE pages, 0.6 for multi-PE pages.
    * Idempotence: re-running does not duplicate rows or overwrite
      higher-confidence entries with lower ones.
    * Backfill: P-1 / P-1R budget_lines rows with missing pe_number inherit
      high-confidence (>=0.8) mappings; low-confidence mappings are skipped.
    * Schema migration 5 creates the bli_pe_map table and is idempotent.
"""
from __future__ import annotations

import sqlite3

import pytest

from pipeline.enricher import run_phase11
from pipeline.schema import migrate


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_db() -> sqlite3.Connection:
    """Minimal DB with the tables Phase 11 reads from / writes to."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT,
            exhibit_type TEXT,
            fiscal_year TEXT,
            account TEXT,
            line_item TEXT,
            line_item_title TEXT,
            pe_number TEXT
        );

        CREATE TABLE pdf_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT,
            fiscal_year TEXT,
            exhibit_type TEXT,
            page_number INTEGER,
            page_text TEXT
        );

        CREATE TABLE bli_index (
            bli_key TEXT PRIMARY KEY,
            account TEXT NOT NULL,
            line_item TEXT,
            display_title TEXT
        );
        """
    )
    return conn


def _seed_bli(conn: sqlite3.Connection, account: str, line_item: str,
              title: str = "Sample Item") -> str:
    bli_key = f"{account}:{line_item}"
    conn.execute(
        "INSERT OR REPLACE INTO bli_index (bli_key, account, line_item, display_title) "
        "VALUES (?, ?, ?, ?)",
        (bli_key, account, line_item, title),
    )
    return bli_key


def _seed_page(conn: sqlite3.Connection, source_file: str, page_number: int,
               text: str, fiscal_year: str = "FY2025") -> None:
    conn.execute(
        "INSERT INTO pdf_pages "
        "(source_file, fiscal_year, exhibit_type, page_number, page_text) "
        "VALUES (?, ?, 'p5', ?, ?)",
        (source_file, fiscal_year, page_number, text),
    )


def _seed_p1_row(conn: sqlite3.Connection, account: str, line_item: str,
                 fy: str = "FY2026") -> int:
    cur = conn.execute(
        "INSERT INTO budget_lines "
        "(source_file, exhibit_type, fiscal_year, account, line_item) "
        "VALUES ('test.xlsx', 'p1', ?, ?, ?)",
        (fy, account, line_item),
    )
    return cur.lastrowid


# ── Extraction tests ──────────────────────────────────────────────────────────


def test_extraction_single_pe_high_confidence():
    conn = _make_db()
    _seed_bli(conn, "1506N", "0577")
    header = (
        "UNCLASSIFIED Exhibit P-40 Navy PB 2024 | "
        "Appropriation / Budget Activity / Budget Sub Activity: "
        "1506N: Aircraft Procurement, Navy / BA 01 "
        "Line Item 0577 / EP-3 Series Mods "
        "Program Element 0305206N"
    )
    _seed_page(conn, "APN.pdf", 1, header)

    inserted = run_phase11(conn)

    assert inserted == 1
    rows = conn.execute(
        "SELECT bli_key, pe_number, confidence FROM bli_pe_map"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["bli_key"] == "1506N:0577"
    assert rows[0]["pe_number"] == "0305206N"
    assert rows[0]["confidence"] == pytest.approx(0.9)


def test_extraction_multi_pe_lower_confidence():
    conn = _make_db()
    _seed_bli(conn, "0300D", "1109")
    header = (
        "UNCLASSIFIED Exhibit P-40 MDA PB 2026 "
        "Appropriation 0300D: Procurement, Defense-Wide "
        "BLI 1109 Budget Line Item Justification "
        "Program elements: 0603881C and 0604876C"
    )
    _seed_page(conn, "MDA.pdf", 89, header)

    run_phase11(conn)

    rows = conn.execute(
        "SELECT pe_number, confidence FROM bli_pe_map ORDER BY pe_number"
    ).fetchall()
    assert [r["pe_number"] for r in rows] == ["0603881C", "0604876C"]
    assert all(r["confidence"] == pytest.approx(0.6) for r in rows)


def test_extraction_requires_both_account_and_line_item():
    """Account present but line_item missing from head → no match."""
    conn = _make_db()
    _seed_bli(conn, "1506N", "9999")  # line_item not in text
    header = (
        "UNCLASSIFIED Navy | 1506N: Aircraft Procurement "
        "Program Element 0305206N"
    )
    _seed_page(conn, "APN.pdf", 1, header)

    inserted = run_phase11(conn)

    assert inserted == 0
    count = conn.execute("SELECT COUNT(*) FROM bli_pe_map").fetchone()[0]
    assert count == 0


def test_extraction_no_pe_on_page_is_noop():
    conn = _make_db()
    _seed_bli(conn, "1506N", "0577")
    _seed_page(conn, "APN.pdf", 1, "UNCLASSIFIED 1506N line 0577 no PE mentioned here")

    inserted = run_phase11(conn)

    assert inserted == 0


def test_extraction_ignores_pe_beyond_scan_window():
    """PE appearing past the 1500-char window is not mined (headers only)."""
    conn = _make_db()
    _seed_bli(conn, "1506N", "0577")
    # Padding pushes the PE mention past the head window.
    padding = "X " * 1000  # ~2000 chars
    page_text = (
        f"UNCLASSIFIED Navy 1506N line 0577 header text {padding} "
        f"Program Element 0305206N appears in body"
    )
    _seed_page(conn, "APN.pdf", 1, page_text)

    inserted = run_phase11(conn)

    assert inserted == 0


def test_extraction_skips_unknown_accounts():
    """Account not in bli_index → no mapping even if PE is present."""
    conn = _make_db()
    _seed_bli(conn, "1506N", "0577")  # unrelated BLI
    header = "UNCLASSIFIED 9999Z line 1234 Program Element 0305206N"
    _seed_page(conn, "stray.pdf", 1, header)

    inserted = run_phase11(conn)

    assert inserted == 0


def test_extraction_idempotent():
    conn = _make_db()
    _seed_bli(conn, "1506N", "0577")
    header = "1506N line 0577 Program Element 0305206N"
    _seed_page(conn, "APN.pdf", 1, header)

    run_phase11(conn)
    first = conn.execute("SELECT COUNT(*) FROM bli_pe_map").fetchone()[0]
    run_phase11(conn)
    second = conn.execute("SELECT COUNT(*) FROM bli_pe_map").fetchone()[0]

    assert first == 1
    assert second == 1


# ── Backfill tests ────────────────────────────────────────────────────────────


def test_backfill_populates_p1_pe_number():
    conn = _make_db()
    _seed_bli(conn, "1506N", "0577")
    _seed_page(conn, "APN.pdf", 1, "1506N line 0577 Program Element 0305206N")
    row_id = _seed_p1_row(conn, "1506N", "0577")

    run_phase11(conn)

    pe = conn.execute(
        "SELECT pe_number FROM budget_lines WHERE id = ?", (row_id,)
    ).fetchone()[0]
    assert pe == "0305206N"


def test_backfill_skips_low_confidence():
    """Multi-PE headers produce confidence 0.6; backfill requires >=0.8."""
    conn = _make_db()
    _seed_bli(conn, "0300D", "1109")
    multi_pe_header = (
        "0300D line 1109 Program Elements 0603881C and 0604876C"
    )
    _seed_page(conn, "MDA.pdf", 1, multi_pe_header)
    row_id = _seed_p1_row(conn, "0300D", "1109")

    run_phase11(conn)

    pe = conn.execute(
        "SELECT pe_number FROM budget_lines WHERE id = ?", (row_id,)
    ).fetchone()[0]
    assert pe is None


def test_backfill_preserves_existing_pe_number():
    conn = _make_db()
    _seed_bli(conn, "1506N", "0577")
    _seed_page(conn, "APN.pdf", 1, "1506N line 0577 Program Element 0305206N")
    cur = conn.execute(
        "INSERT INTO budget_lines "
        "(source_file, exhibit_type, fiscal_year, account, line_item, pe_number) "
        "VALUES ('x.xlsx', 'p1', 'FY2026', '1506N', '0577', '0999999N')"
    )
    row_id = cur.lastrowid

    run_phase11(conn)

    pe = conn.execute(
        "SELECT pe_number FROM budget_lines WHERE id = ?", (row_id,)
    ).fetchone()[0]
    assert pe == "0999999N"  # untouched


def test_backfill_ignores_non_procurement_rows():
    """R-2 rows with the same (account, line_item) are not touched."""
    conn = _make_db()
    _seed_bli(conn, "1506N", "0577")
    _seed_page(conn, "APN.pdf", 1, "1506N line 0577 Program Element 0305206N")
    conn.execute(
        "INSERT INTO budget_lines "
        "(source_file, exhibit_type, fiscal_year, account, line_item) "
        "VALUES ('r2.pdf', 'r2_pdf', 'FY2026', '1506N', '0577')"
    )

    run_phase11(conn)

    pe = conn.execute(
        "SELECT pe_number FROM budget_lines WHERE exhibit_type='r2_pdf'"
    ).fetchone()[0]
    assert pe is None


# ── Schema migration ──────────────────────────────────────────────────────────


def test_migration_005_creates_bli_pe_map_idempotent(tmp_path):
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(db_path))
    first = migrate(conn)
    assert first >= 1  # at least one migration applied on a fresh DB

    # Table and index exist.
    tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    indexes = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
    }
    assert "bli_pe_map" in tables
    assert "idx_bli_pe_map_pe" in indexes

    # Re-running is a noop.
    second = migrate(conn)
    assert second == 0
    conn.close()
