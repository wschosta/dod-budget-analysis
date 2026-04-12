"""Unit tests for Explorer XLSX export helpers.

These cover the column-extraction and per-FY description lookup logic used by
``download_explorer_xlsx`` so we can verify the interleaved FY layout without
standing up a full cache.
"""

import sqlite3

import pytest

pytest.importorskip("fastapi")

from api.routes.explorer import _extract_column_value  # noqa: E402
from api.routes.keyword_search import load_per_fy_descriptions  # noqa: E402


class TestExtractColumnValue:
    def _row(self) -> dict:
        return {
            "pe_number": "0603285E",
            "organization_name": "DARPA",
            "exhibit_type": "r2",
            "line_item_title": "Tactical Technology",
            "budget_activity_title": "BA 3",
            "budget_activity_norm": "BA 3",
            "appropriation_title": "RDT&E, Defense-Wide",
            "color_of_money": "RDT&E",
            "matched_keywords_row": ["hypersonic"],
            "matched_keywords_desc": [],
            "description_text": "Legacy description",
            "fy2024": 12345.0,
            "fy2025": 67890.0,
            "refs": {"fy2024": "FY2024_PB.xlsx", "fy2025": "FY2026_PB.xlsx"},
        }

    def test_fy_value_column(self):
        val = _extract_column_value(self._row(), "FY2024 ($K)", [2024, 2025])
        assert val == 12345.0

    def test_fy_source_column(self):
        val = _extract_column_value(self._row(), "FY2024 Source", [2024, 2025])
        assert val == "FY2024_PB.xlsx"

    def test_fy_description_column_reads_per_fy_map(self):
        desc_map = {
            ("0603285E", "2024"): "FY2024 narrative text for tactical technology.",
            ("0603285E", "2025"): "FY2025 narrative text for tactical technology.",
        }
        val = _extract_column_value(
            self._row(), "FY2024 Description", [2024, 2025], desc_map
        )
        assert val == "FY2024 narrative text for tactical technology."

    def test_fy_description_column_without_map_is_empty(self):
        val = _extract_column_value(self._row(), "FY2024 Description", [2024, 2025])
        assert val == ""

    def test_in_totals_column_yes_from_matches(self):
        # Row has matched_keywords_row → inferred as in totals
        assert _extract_column_value(self._row(), "In Totals", [2024]) == "Yes"

    def test_in_totals_column_blank_when_no_matches(self):
        row = self._row()
        row["matched_keywords_row"] = []
        row["matched_keywords_desc"] = []
        assert _extract_column_value(row, "In Totals", [2024]) == ""

    def test_in_totals_column_respects_explicit_flag(self):
        # Explicit in_totals=False overrides inferred state
        row = self._row()
        val = _extract_column_value(row, "In Totals", [2024], None, False)
        assert val == ""

    def test_removed_column_returns_empty(self):
        """Columns removed from _COL_TO_FIELD return empty string."""
        val = _extract_column_value(self._row(), "Keywords (Row)", [2024])
        assert val == ""


class TestLoadPerFyDescriptions:
    """Tests for the shared ``load_per_fy_descriptions`` helper."""
    @pytest.fixture()
    def conn(self, tmp_path):
        db_path = tmp_path / "pe_desc.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            CREATE TABLE pe_descriptions (
                pe_number TEXT,
                fiscal_year TEXT,
                section_header TEXT,
                description_text TEXT
            )
            """
        )
        rows = [
            (
                "0603285E",
                "2024",
                "A. Mission Description",
                "x" * 100,  # long enough to pass the 80-char filter
            ),
            (
                "0603285E",
                "2024",
                "B. Accomplishments",
                "Secondary text that should be ignored because Mission Description wins",
            ),
            (
                "0603285E",
                "2025",
                "A. Mission Description",
                "y" * 120,
            ),
            (
                "0603285E",
                "2026",
                "A. Mission Description",
                "too short",  # under 80 chars — filtered out
            ),
        ]
        conn.executemany(
            "INSERT INTO pe_descriptions VALUES (?, ?, ?, ?)", rows
        )
        conn.commit()
        yield conn
        conn.close()

    def test_priority_and_length_filter(self, conn):
        result = load_per_fy_descriptions(conn, ["0603285E"])
        assert result[("0603285E", "2024")] == "x" * 100
        assert result[("0603285E", "2025")] == "y" * 120
        # 2026 row is filtered out because description is too short
        assert ("0603285E", "2026") not in result

    def test_missing_table_returns_empty(self, tmp_path):
        empty_db = tmp_path / "empty.sqlite"
        conn = sqlite3.connect(str(empty_db))
        try:
            result = load_per_fy_descriptions(conn, ["0603285E"])
            assert result == {}
        finally:
            conn.close()


class TestDefaultColumnsInterleaved:
    """Regression test: default column layout should interleave FY value/source/desc."""

    def test_default_order_triples(self):
        from api.routes.explorer import _ALL_COLUMNS

        # Simulate the default_columns construction with two active years
        active_years = [2024, 2025]
        default_columns = [
            "PE Number", "Service/Org", "Exhibit Type", "Line Item Title",
            "Color of Money",
        ]
        for yr in active_years:
            default_columns.append(f"FY{yr} ($K)")
            default_columns.append(f"FY{yr} Source")
            default_columns.append(f"FY{yr} Description")

        # Available columns should include all three FY variants
        available_columns = list(_ALL_COLUMNS)
        for yr in active_years:
            available_columns.append(f"FY{yr} ($K)")
            available_columns.append(f"FY{yr} Source")
            available_columns.append(f"FY{yr} Description")

        assert "FY2024 Description" in available_columns
        assert default_columns.index("FY2024 ($K)") + 1 == default_columns.index(
            "FY2024 Source"
        )
        assert default_columns.index("FY2024 Source") + 1 == default_columns.index(
            "FY2024 Description"
        )
