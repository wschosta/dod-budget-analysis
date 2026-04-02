"""Tests for PE number keyword detection in Explorer/keyword search.

Verifies that collect_matching_pe_numbers_split() correctly:
- Detects PE number keywords (standard and D8Z suffixes)
- Handles whitespace around PE numbers
- Falls back to pe_index for PDF-only PEs not in budget_lines
"""

import sqlite3

import pytest


@pytest.fixture()
def pe_search_db(tmp_path):
    """Create a minimal DB with budget_lines and pe_index tables for PE search tests."""
    db_path = tmp_path / "pe_search.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY,
            pe_number TEXT,
            line_item_title TEXT,
            account_title TEXT,
            budget_activity_title TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE pe_index (
            pe_number TEXT PRIMARY KEY,
            display_title TEXT,
            organization_name TEXT
        )
        """
    )
    # Standard PE in budget_lines
    conn.execute(
        "INSERT INTO budget_lines (pe_number, line_item_title, account_title, budget_activity_title) "
        "VALUES ('0604030N', 'Tomahawk', 'Weapons', 'BA 4')"
    )
    # D8Z PE only in pe_index (PDF-only)
    conn.execute(
        "INSERT INTO pe_index (pe_number, display_title, organization_name) "
        "VALUES ('0603183D8Z', 'Research Program', 'Defense-Wide')"
    )
    # Standard PE in both tables
    conn.execute(
        "INSERT INTO pe_index (pe_number, display_title, organization_name) "
        "VALUES ('0604030N', 'Tomahawk', 'Navy')"
    )
    conn.commit()
    yield conn
    conn.close()


class TestCollectMatchingPeNumbersSplit:
    """Test PE number detection in collect_matching_pe_numbers_split()."""

    def test_standard_pe_keyword_found(self, pe_search_db):
        """A standard PE number keyword (e.g., 0604030N) is detected and returned."""
        from api.routes.keyword_search import collect_matching_pe_numbers_split

        (bl_matched, _desc), all_matched = collect_matching_pe_numbers_split(
            pe_search_db, ["0604030N"], []
        )
        assert "0604030N" in bl_matched
        assert "0604030N" in all_matched

    def test_d8z_pe_keyword_found(self, pe_search_db):
        """A D8Z PE number keyword (e.g., 0603183D8Z) is detected via pe_index fallback."""
        from api.routes.keyword_search import collect_matching_pe_numbers_split

        (bl_matched, _desc), all_matched = collect_matching_pe_numbers_split(
            pe_search_db, ["0603183D8Z"], []
        )
        assert "0603183D8Z" in bl_matched
        assert "0603183D8Z" in all_matched

    def test_pe_keyword_with_whitespace(self, pe_search_db):
        """Whitespace around PE keywords is stripped before matching."""
        from api.routes.keyword_search import collect_matching_pe_numbers_split

        (bl_matched, _desc), all_matched = collect_matching_pe_numbers_split(
            pe_search_db, ["  0604030N  "], []
        )
        assert "0604030N" in bl_matched

    def test_pe_keyword_case_insensitive(self, pe_search_db):
        """PE keywords are matched case-insensitively."""
        from api.routes.keyword_search import collect_matching_pe_numbers_split

        (bl_matched, _desc), all_matched = collect_matching_pe_numbers_split(
            pe_search_db, ["0604030n"], []
        )
        assert "0604030N" in bl_matched

    def test_d8z_pe_keyword_with_whitespace(self, pe_search_db):
        """D8Z PE keyword with whitespace is stripped and found via pe_index."""
        from api.routes.keyword_search import collect_matching_pe_numbers_split

        (bl_matched, _desc), all_matched = collect_matching_pe_numbers_split(
            pe_search_db, [" 0603183D8Z "], []
        )
        assert "0603183D8Z" in bl_matched

    def test_non_pe_keyword_not_treated_as_pe(self, pe_search_db):
        """A non-PE keyword like 'hypersonic' is not treated as a PE number."""
        from api.routes.keyword_search import collect_matching_pe_numbers_split

        (bl_matched, _desc), all_matched = collect_matching_pe_numbers_split(
            pe_search_db, ["hypersonic"], []
        )
        # 'hypersonic' shouldn't match any PE via the PE-detection path
        # (it might match via LIKE search, but not here since our test data
        # doesn't have 'hypersonic' in any column)
        assert "0603183D8Z" not in bl_matched

    def test_pdf_only_pe_not_in_budget_lines(self, pe_search_db):
        """A PE existing only in pe_index (not budget_lines) is found via fallback."""
        from api.routes.keyword_search import collect_matching_pe_numbers_split

        # Verify this PE is NOT in budget_lines
        row = pe_search_db.execute(
            "SELECT COUNT(*) FROM budget_lines WHERE pe_number = '0603183D8Z'"
        ).fetchone()
        assert row[0] == 0, "Test setup: D8Z PE should not be in budget_lines"

        # But it should still be found via pe_index fallback
        (bl_matched, _desc), all_matched = collect_matching_pe_numbers_split(
            pe_search_db, ["0603183D8Z"], []
        )
        assert "0603183D8Z" in all_matched

    def test_no_pe_index_table_graceful(self, tmp_path):
        """If pe_index table doesn't exist, no crash occurs."""
        from api.routes.keyword_search import collect_matching_pe_numbers_split

        db_path = tmp_path / "no_pe_index.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE budget_lines (
                id INTEGER PRIMARY KEY,
                pe_number TEXT,
                line_item_title TEXT,
                account_title TEXT,
                budget_activity_title TEXT
            )
            """
        )
        conn.commit()

        # Should not raise even though pe_index doesn't exist
        (bl_matched, _desc), all_matched = collect_matching_pe_numbers_split(
            conn, ["0603183D8Z"], []
        )
        assert "0603183D8Z" not in all_matched
        conn.close()
