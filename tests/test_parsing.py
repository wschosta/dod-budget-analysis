"""
Unit tests for parsing logic — Step 1.C2

Tests for column detection, value normalization, exhibit-type identification,
and PE/line-item extraction.
"""
import importlib
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# build_budget_db imports heavy third-party modules at module level, which may
# fail in environments without the full dependency stack.  Stub them out so we
# can import the pure-Python utilities we actually test.
for _mod in ("pdfplumber", "openpyxl"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

from build_budget_db import (
    _detect_exhibit_type,
    _safe_float,
    _extract_table_text,
    _determine_category,
    _map_columns,
)
from exhibit_catalog import find_matching_columns


# ── TODO 1.C2-a: _detect_exhibit_type ────────────────────────────────────────

@pytest.mark.parametrize("filename, expected", [
    ("p1_display.xlsx", "p1"),
    ("r1.xlsx", "r1"),
    ("c1_display.xlsx", "c1"),
    ("p1r_display.xlsx", "p1r"),
    ("m1_something_else.xlsx", "m1"),
    ("o1_display.xlsx", "o1"),
    ("rf1_display.xlsx", "rf1"),
    ("unknown_file.xlsx", "unknown"),
    ("P1_DISPLAY.xlsx", "p1"),           # case insensitive
    ("army_p1r_fy2026.xlsx", "p1r"),     # p1r matched before p1
    ("budget_summary.xlsx", "unknown"),
])
def test_detect_exhibit_type(filename, expected):
    assert _detect_exhibit_type(filename) == expected


# ── TODO 1.C2-c: _safe_float ─────────────────────────────────────────────────

@pytest.mark.parametrize("val, expected", [
    (None, None),
    ("", None),
    (" ", None),
    ("123", 123.0),
    (123, 123.0),
    (0, 0.0),
    (0.0, 0.0),
    (-5.5, -5.5),
    ("-5.5", -5.5),
    ("abc", None),
    ("12.34", 12.34),
    (True, 1.0),     # bool is numeric in Python
])
def test_safe_float(val, expected):
    result = _safe_float(val)
    if expected is None:
        assert result is None
    else:
        assert result == expected


# ── TODO 1.C2-d: _determine_category ─────────────────────────────────────────

@pytest.mark.parametrize("path_str, expected", [
    ("DoD_Budget_Documents/FY2026/Comptroller/file.pdf", "Comptroller"),
    ("DoD_Budget_Documents/FY2026/US_Army/file.xlsx", "Army"),
    ("DoD_Budget_Documents/FY2026/Defense_Wide/file.pdf", "Defense-Wide"),
    ("DoD_Budget_Documents/FY2026/Navy/file.xlsx", "Navy"),
    ("DoD_Budget_Documents/FY2026/Air_Force/file.pdf", "Air Force"),
    ("DoD_Budget_Documents/FY2026/Space_Force/file.pdf", "Space Force"),
    ("DoD_Budget_Documents/FY2026/spaceforce/file.pdf", "Space Force"),
    ("DoD_Budget_Documents/FY2026/Marine_Corps/file.pdf", "Marine Corps"),
    ("DoD_Budget_Documents/FY2026/marines/file.xlsx", "Marine Corps"),
    ("DoD_Budget_Documents/FY2026/SomeOther/file.xlsx", "Other"),
])
def test_determine_category(path_str, expected):
    assert _determine_category(Path(path_str)) == expected


# ── TODO 1.C2-e: _extract_table_text ─────────────────────────────────────────

def test_extract_table_text_basic():
    tables = [[
        ["Header1", "Header2", "Header3"],
        ["A", "B", "C"],
        ["D", None, "F"],
    ]]
    result = _extract_table_text(tables)
    lines = result.strip().split("\n")
    assert len(lines) == 3
    assert "Header1 | Header2 | Header3" == lines[0]
    assert "A | B | C" == lines[1]
    assert "D | F" == lines[2]  # None cell skipped


def test_extract_table_text_empty():
    assert _extract_table_text([]) == ""
    assert _extract_table_text(None) == ""


def test_extract_table_text_multiple_tables():
    tables = [
        [["A", "B"]],
        [["C", "D"]],
    ]
    result = _extract_table_text(tables)
    lines = result.strip().split("\n")
    assert len(lines) == 2


# ── TODO 1.C2-b (partial): _map_columns basic coverage ───────────────────────

def test_map_columns_p1_headers():
    """Test that _map_columns finds standard P-1 column mappings."""
    headers = [
        "Account", "Account Title", "Organization",
        "Budget Activity", "Budget Activity Title",
        "Budget Line Item", "Budget Line Item (BLI) Title",
        "FY2024 Actual\nAmount", "FY2025 Enacted\nAmount",
        "FY2026 Request\nAmount",
    ]
    mapping = _map_columns(headers, "p1")
    assert "account" in mapping
    assert "account_title" in mapping
    assert "organization" in mapping
    assert "budget_activity" in mapping
    assert "budget_activity_title" in mapping
    assert "line_item" in mapping
    assert "line_item_title" in mapping


def test_map_columns_c1_authorization():
    """Test that C-1 authorization/appropriation columns are mapped."""
    headers = [
        "Account", "Account Title", "Construction Project",
        "Construction Project Title",
        "Authorization Amount", "Appropriation Amount",
    ]
    mapping = _map_columns(headers, "c1")
    assert "account" in mapping
    assert "line_item" in mapping         # construction project
    assert "line_item_title" in mapping   # construction project title
    # Authorization → amount_fy2026_request, Appropriation → amount_fy2025_enacted
    assert "amount_fy2026_request" in mapping
    assert "amount_fy2025_enacted" in mapping


def test_map_columns_empty_headers():
    """Empty header list should return empty mapping without crashing."""
    mapping = _map_columns([], "p1")
    assert mapping == {}


# ── STEP 1.C2 STATUS: Core tests implemented ───────────────────────────────
#
# COMPLETED test groups:
#   ✓ 1.C2-a: test_detect_exhibit_type
#   ✓ 1.C2-c: test_safe_float
#   ✓ 1.C2-d: test_determine_category
#   ✓ 1.C2-e: test_extract_table_text
#   ✓ 1.C2-b: test_map_columns (partial coverage for P-1, C-1)
#
# REMAINING tasks (per docs/TODO_1C2_unit_tests_parsing.md):
#   - 1.C2-b-extended: Additional _map_columns tests for R, M, O, RF exhibits
#   - 1.C2-f: _sanitize_filename edge case testing
#   - 1.C2-g: Clean up legacy TODO comments in related test files
#
# See docs/TODO_1C2_unit_tests_parsing.md for full specification.

# TODO 1.C2-b-extended [EASY, ~1200 tokens]: Add _map_columns tests for remaining
#   exhibit types. Each is a simple parametrized test with a synthetic header row:
#
#   R-1 headers: ["Account", "Program Element", "Prior Year", "Current Year", "Estimate"]
#     → assert "account" and "budget_activity" in mapping
#   M-1 headers: ["Account", "Personnel Category", "Prior Year Enacted", "FY2026 Request Amount"]
#     → assert "account" in mapping and at least one amount_ key
#   O-1 headers: ["Account", "Budget Activity", "Budget Subactivity (BSA) Title", "FY2025 Enacted Amount"]
#     → assert "sub_activity_title" in mapping
#   RF-1 headers: ["Activity", "Prior Year Revenue", "Current Year Expenses", "Estimate Revenue"]
#     → assert "account" in mapping (RF-1 maps "Activity" to account)
#   Add also: test_detect_exhibit_type extended cases for p5/r2/r3/r4 filenames.
#   No external data needed.

# TODO 1.C2-pe [EASY, ~600 tokens]: Add tests for _extract_pe_number and _parse_appropriation.
#   PE tests: "0602702E" → "0602702E", "0305116BB" → "0305116BB", "not a PE" → None,
#             "Account 0602702E Army" → "0602702E" (embedded).
#   Appropriation tests: "2035 Aircraft Procurement, Army" → ("2035", "Aircraft Procurement, Army"),
#                        "Research Development" → (None, "Research Development"),
#                        None → (None, None).
#   Already importable from build_budget_db; no external data.

# TODO 1.C2-f [EASY, ~500 tokens]: Add _sanitize_filename edge case tests.
#   Test: URL query params stripped ("file.pdf?v=2" → "file.pdf"), special chars removed,
#   leading/trailing whitespace trimmed, empty string → "unnamed".
#   Import sanitize_filename from utils (already exported from utils/__init__.py).
#   No external data needed.

# TODO 1.C2-fy [EASY, ~400 tokens, DEPENDS ON 1.B2-d]: After _normalise_fiscal_year() is
#   added to build_budget_db.py, add parametrized tests:
#     ("FY2026", "FY 2026"), ("FY 2026", "FY 2026"), ("2026", "FY 2026"), ("fy2025", "FY 2025")
#   Import _normalise_fiscal_year from build_budget_db (same pattern as other imports above).


# ── TODO 1.B2-b: Catalog-driven column detection for detail exhibits ───────────

class TestCatalogFindMatchingColumns:
    """Tests for find_matching_columns() covering p5, r2, r3, r4 exhibit types."""

    def test_p5_basic_columns(self):
        """P-5 exhibit: line item number, title, quantity, and justification columns."""
        headers = [
            "Account",
            "Program Element",
            "Line Item",
            "Item Title",
            "Unit",
            "Prior Year Quantity",
            "Estimate Quantity",
            "Justification",
        ]
        result = find_matching_columns("p5", headers)
        # col_idx → field_name; collect matched field names
        fields = set(result.values())
        assert "program_element" in fields
        assert "line_item_number" in fields
        assert "line_item_title" in fields
        assert "unit" in fields
        assert "prior_year_qty" in fields
        assert "estimate_qty" in fields
        assert "justification" in fields

    def test_p5_unit_cost_columns(self):
        """P-5: unit cost columns should be detected."""
        headers = [
            "Account",
            "PE",
            "LIN",
            "Title",
            "Unit of Measure",
            "Prior Year Unit Cost",
            "Current Year Unit Cost",
            "Estimate Unit Cost",
        ]
        result = find_matching_columns("p5", headers)
        fields = set(result.values())
        assert "prior_year_unit_cost" in fields
        assert "current_year_unit_cost" in fields
        assert "estimate_unit_cost" in fields

    def test_r2_basic_columns(self):
        """R-2 exhibit: program element, title, and amount columns."""
        headers = [
            "PE",
            "Program Title",
            "Prior Year",
            "Current Year",
            "Estimate",
            "Key Metric",
            "Achievement",
        ]
        result = find_matching_columns("r2", headers)
        fields = set(result.values())
        assert "program_element" in fields
        assert "title" in fields
        assert "prior_year_amount" in fields
        assert "current_year_amount" in fields
        assert "estimate_amount" in fields
        assert "performance_metric" in fields
        assert "current_achievement" in fields

    def test_r2_sub_element_column(self):
        """R-2: sub-element column should be detected."""
        headers = [
            "Program Element",
            "Sub-Element",
            "Title",
            "Prior Year",
            "Current Year",
            "Estimate",
        ]
        result = find_matching_columns("r2", headers)
        fields = set(result.values())
        assert "sub_element" in fields

    def test_r3_basic_columns(self):
        """R-3 exhibit: project number, title, and development approach."""
        headers = [
            "PE",
            "Project Number",
            "Project Title",
            "Prior Year",
            "Current Year",
            "Estimate",
            "Development Approach",
            "Schedule",
        ]
        result = find_matching_columns("r3", headers)
        fields = set(result.values())
        assert "program_element" in fields
        assert "project_number" in fields
        assert "project_title" in fields
        assert "prior_year_amount" in fields
        assert "estimate_amount" in fields
        assert "development_approach" in fields
        assert "schedule_summary" in fields

    def test_r4_basic_columns(self):
        """R-4 exhibit: program element, line item, amount, and narrative."""
        headers = [
            "PE",
            "Line Item",
            "Total",
            "Narrative",
        ]
        result = find_matching_columns("r4", headers)
        fields = set(result.values())
        assert "program_element" in fields
        assert "line_item" in fields
        assert "amount" in fields
        assert "narrative" in fields

    def test_r4_justification_column(self):
        """R-4: 'Justification' header should map to narrative field."""
        headers = ["PE", "Item", "Amount", "Justification"]
        result = find_matching_columns("r4", headers)
        fields = set(result.values())
        assert "narrative" in fields

    def test_unknown_exhibit_returns_empty(self):
        """Unknown exhibit type returns empty mapping without error."""
        result = find_matching_columns("zz99", ["Account", "Title"])
        assert result == {}

    def test_empty_headers_returns_empty(self):
        """Empty header list returns empty mapping without error."""
        result = find_matching_columns("p5", [])
        assert result == {}

    def test_none_headers_handled(self):
        """None values in header row are treated as empty strings."""
        headers = [None, "PE", None, "Line Item"]
        result = find_matching_columns("p5", headers)
        fields = set(result.values())
        assert "program_element" in fields
        assert "line_item_number" in fields


class TestMapColumnsWithCatalogMerge:
    """Tests that _map_columns() correctly merges catalog columns for detail exhibits."""

    def test_p5_catalog_fields_merged(self):
        """_map_columns for a p5 file picks up catalog-only fields (e.g. line_item_number)."""
        headers = [
            "Account",
            "Program Element",
            "LIN",
            "Title",
            "Unit",
            "Prior Year Quantity",
            "Estimate Quantity",
            "Justification",
        ]
        mapping = _map_columns(headers, "p5")
        # Catalog should add these fields not covered by heuristics
        assert "line_item_number" in mapping
        assert "unit" in mapping
        assert "prior_year_qty" in mapping
        assert "estimate_qty" in mapping
        assert "justification" in mapping

    def test_r2_catalog_fields_merged(self):
        """_map_columns for an r2 file picks up catalog-specific fields."""
        headers = [
            "Account",
            "Program Element",
            "Sub-Element",
            "Program Title",
            "Prior Year",
            "Current Year",
            "Estimate",
            "Planned Achievement",
        ]
        mapping = _map_columns(headers, "r2")
        assert "sub_element" in mapping
        assert "title" in mapping
        assert "planned_achievement" in mapping

    def test_heuristic_wins_over_catalog(self):
        """Heuristic-matched fields are not overwritten by catalog matches."""
        # account is matched by heuristic; catalog also has account-like fields
        # for p1. The heuristic result (index 0) should be preserved.
        headers = [
            "Account",
            "Account Title",
            "Organization",
            "Budget Activity",
        ]
        mapping = _map_columns(headers, "p1")
        assert mapping["account"] == 0
        assert mapping["account_title"] == 1

    def test_r3_catalog_fields_merged(self):
        """_map_columns for r3 picks up project_number and development_approach."""
        headers = [
            "Account",
            "PE",
            "Project No",
            "Title",
            "Prior Year",
            "Current Year",
            "Estimate",
            "Development Approach",
        ]
        mapping = _map_columns(headers, "r3")
        assert "project_number" in mapping
        assert "development_approach" in mapping
