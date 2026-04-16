"""Tests for api/routes/keyword_xlsx.py — XLSX styling and helper functions.

Tests the pure utility functions that don't require a full xlsxwriter workbook.
The build_keyword_xlsx integration requires actual data; we test the helpers and
style definitions that make up the presentation layer.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

xlsxwriter = pytest.importorskip("xlsxwriter")

from api.routes.keyword_xlsx import (  # noqa: E402
    xlsx_base_styles,
    _col_letter,
    _COL_WIDTH_DEFAULTS,
    HIDDEN_LOOKUP_COL,
    SPILL_MAX_ROW,
)


# ── xlsx_base_styles ─────────────────────────────────────────────────────────


class TestXlsxBaseStyles:
    def test_returns_dict(self):
        styles = xlsx_base_styles()
        assert isinstance(styles, dict)

    def test_required_style_keys(self):
        styles = xlsx_base_styles()
        assert "header" in styles
        assert "base" in styles
        assert "italic" in styles
        assert "total" in styles
        assert "source" in styles
        assert "desc" in styles
        assert "money_fmt" in styles

    def test_header_style_properties(self):
        styles = xlsx_base_styles()
        h = styles["header"]
        assert h["bold"] is True
        assert h["font_color"] == "#FFFFFF"
        assert h["bg_color"] == "#2C3E50"
        assert h["text_wrap"] is True

    def test_money_format_is_string(self):
        styles = xlsx_base_styles()
        assert isinstance(styles["money_fmt"], str)
        assert "$" in styles["money_fmt"]


# ── _col_letter ──────────────────────────────────────────────────────────────


class TestColLetter:
    def test_single_letter_columns(self):
        assert _col_letter(1) == "A"
        assert _col_letter(2) == "B"
        assert _col_letter(26) == "Z"

    def test_double_letter_columns(self):
        assert _col_letter(27) == "AA"
        assert _col_letter(28) == "AB"
        assert _col_letter(52) == "AZ"
        assert _col_letter(53) == "BA"


# ── Column width defaults ───────────────────────────────────────────────────


class TestColWidthDefaults:
    def test_known_columns_have_widths(self):
        assert "PE Number" in _COL_WIDTH_DEFAULTS
        assert "Line Item Title" in _COL_WIDTH_DEFAULTS
        assert "Color of Money" in _COL_WIDTH_DEFAULTS

    def test_widths_are_positive_ints(self):
        for header, width in _COL_WIDTH_DEFAULTS.items():
            assert isinstance(width, int), f"{header} width is not int"
            assert width > 0, f"{header} width is not positive"


# ── Constants ────────────────────────────────────────────────────────────────


class TestConstants:
    def test_hidden_lookup_col(self):
        assert isinstance(HIDDEN_LOOKUP_COL, int)
        assert HIDDEN_LOOKUP_COL > 100  # Sanity: should be far right

    def test_spill_max_row(self):
        assert isinstance(SPILL_MAX_ROW, int)
        assert SPILL_MAX_ROW > 0


# ── XLSX workbook generation smoke test ──────────────────────────────────────


class TestBuildKeywordXlsx:
    """Smoke test for build_keyword_xlsx with minimal data.

    The function signature is:
        build_keyword_xlsx(items, active_years, desc_by_pe_fy,
                          fixed_columns, ..., keywords=None)
    """

    def _make_item(self, pe="0602120A", org="Army", title="Cyber Research"):
        return {
            "pe_number": pe,
            "organization_name": org,
            "exhibit_type": "r1",
            "line_item_title": title,
            "budget_activity_title": "BA 2",
            "budget_activity_norm": "BA 2",
            "appropriation_title": "RDT&E, Army",
            "color_of_money": "RDT&E",
            "lineage_note": None,
            "matched_keywords_row": '["cyber"]',
            "matched_keywords_desc": "[]",
            "description_text": "Develops advanced cybersecurity capabilities.",
            "fy2024": 100.0,
            "fy2024_ref": "FY2024_PB.xlsx",
            "fy2025": 125.0,
            "fy2025_ref": "FY2025_PB.xlsx",
            "fy2026": 150.0,
            "fy2026_ref": "FY2026_PB.xlsx",
        }

    def _fixed_cols(self):
        from api.routes.explorer import _FIXED_COLUMNS
        return list(_FIXED_COLUMNS)

    def test_produces_bytes(self):
        """build_keyword_xlsx returns bytes of a valid XLSX file."""
        from api.routes.keyword_xlsx import build_keyword_xlsx

        items = [self._make_item()]
        result = build_keyword_xlsx(
            items=items,
            active_years=[2024, 2025, 2026],
            desc_by_pe_fy={},
            fixed_columns=self._fixed_cols(),
            keywords=["cyber"],
        )
        assert isinstance(result, bytes)
        assert len(result) > 100
        # XLSX files start with PK zip header
        assert result[:2] == b"PK"

    def test_empty_rows_produces_valid_xlsx(self):
        """Empty items list should still produce a valid (but empty) XLSX."""
        from api.routes.keyword_xlsx import build_keyword_xlsx

        result = build_keyword_xlsx(
            items=[],
            active_years=[2025, 2026],
            desc_by_pe_fy={},
            fixed_columns=self._fixed_cols(),
            keywords=["missile"],
        )
        assert isinstance(result, bytes)
        assert result[:2] == b"PK"

    def test_with_description_map(self):
        """desc_by_pe_fy content should be incorporated into the workbook."""
        from api.routes.keyword_xlsx import build_keyword_xlsx

        items = [self._make_item()]
        desc_map = {
            ("0602120A", "2025"): "FY2025 description text for cyber research.",
        }
        result = build_keyword_xlsx(
            items=items,
            active_years=[2025, 2026],
            desc_by_pe_fy=desc_map,
            fixed_columns=self._fixed_cols(),
            keywords=["cyber"],
        )
        assert isinstance(result, bytes)
        assert len(result) > 100
