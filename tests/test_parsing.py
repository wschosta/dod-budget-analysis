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
# TODO [Step 1.C2]: Implement unit tests for parsing logic.
#
# Test groups to implement:
#   - test_detect_exhibit_type: verify _detect_exhibit_type() for all EXHIBIT_TYPES
#   - test_map_columns: verify _map_columns() for each exhibit type's header row
#   - test_safe_float: verify _safe_float() edge cases
#   - test_sanitize_filename: verify _sanitize_filename() with special characters
#   - test_ingest_excel_file: integration test with fixture files (needs 1.C1)
#
# See docs/TODO_1C2_unit_tests_parsing.md for full specification.
