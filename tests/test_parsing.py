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
    _extract_pe_number,
    _detect_amount_unit,
)
from utils.common import sanitize_filename


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
    (None, 0.0),      # None -> default 0.0
    ("", 0.0),        # empty string -> default 0.0
    (" ", 0.0),       # whitespace-only -> default 0.0
    ("123", 123.0),
    (123, 123.0),
    (0, 0.0),
    (0.0, 0.0),
    (-5.5, -5.5),
    ("-5.5", -5.5),
    ("abc", 0.0),     # unparseable -> default 0.0
    ("12.34", 12.34),
    (True, 1.0),      # bool is numeric in Python
])
def test_safe_float(val, expected):
    assert _safe_float(val) == expected


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


# ── 1.C2-a extended: _map_columns additional exhibit types ───────────────────

def test_map_columns_r1_headers():
    """R-1 research exhibits use PE/BLI instead of Budget Line Item."""
    headers = [
        "Account", "Account Title", "Organization",
        "Budget Activity", "Budget Activity Title",
        "PE/BLI", "Program Element/Budget Line Item (BLI) Title",
        "FY2024 Actual\nAmount", "FY2025 Enacted\nAmount",
        "FY2026 Request\nAmount",
    ]
    mapping = _map_columns(headers, "r1")
    assert "account" in mapping
    assert "organization" in mapping
    assert "budget_activity" in mapping
    assert "line_item" in mapping        # PE/BLI → line_item
    assert "line_item_title" in mapping  # Program Element/BLI Title


def test_map_columns_o1_headers():
    """O-1 operation & maintenance exhibits use BSA sub-activity columns."""
    headers = [
        "Account", "Account Title", "Organization",
        "Budget Activity", "Budget Activity Title",
        "BSA", "Budget SubActivity Title",
        "FY2024 Actual\nAmount", "FY2025 Enacted\nAmount",
        "FY2026 Request\nAmount",
    ]
    mapping = _map_columns(headers, "o1")
    assert "account" in mapping
    assert "sub_activity" in mapping        # BSA → sub_activity
    assert "sub_activity_title" in mapping  # Budget SubActivity Title


def test_map_columns_m1_headers():
    """M-1 military personnel exhibits share the same BSA layout as O-1."""
    headers = [
        "Account", "Account Title", "Organization",
        "Budget Activity", "Budget Activity Title",
        "BSA", "Budget SubActivity Title",
        "FY2024 Actual\nAmount", "FY2025 Enacted\nAmount",
        "FY2026 Request\nAmount",
    ]
    mapping = _map_columns(headers, "m1")
    assert "sub_activity" in mapping
    assert "sub_activity_title" in mapping
    assert "amount_fy2024_actual" in mapping
    assert "amount_fy2026_request" in mapping


def test_map_columns_rf1_headers():
    """RF-1 revolving fund exhibits share the P-1 Budget Line Item layout."""
    headers = [
        "Account", "Account Title", "Organization",
        "Budget Activity", "Budget Activity Title",
        "Budget Line Item", "Budget Line Item (BLI) Title",
        "FY2024 Actual\nAmount", "FY2025 Enacted\nAmount",
        "FY2026 Request\nAmount",
    ]
    mapping = _map_columns(headers, "rf1")
    assert "line_item" in mapping
    assert "line_item_title" in mapping
    assert "amount_fy2025_enacted" in mapping
    assert "amount_fy2026_request" in mapping


def test_map_columns_p1r_headers():
    """P-1R exhibits use the same columns as P-1."""
    headers = [
        "Account", "Account Title", "Organization",
        "Budget Activity", "Budget Activity Title",
        "Budget Line Item", "Budget Line Item (BLI) Title",
        "FY2024 Actual\nAmount", "FY2025 Enacted\nAmount",
        "FY2026 Request\nAmount",
    ]
    mapping = _map_columns(headers, "p1r")
    assert "account" in mapping
    assert "line_item" in mapping
    assert "line_item_title" in mapping
    assert "amount_fy2024_actual" in mapping
    assert "amount_fy2026_request" in mapping


def test_map_columns_multiline_headers():
    """Headers with embedded newlines are normalised before matching."""
    headers = [
        "Account", "Account Title",
        "FY2024 Actual\nAmount",
        "FY2025 Enacted\nAmount",
        "FY2026 Request\nAmount",
    ]
    mapping = _map_columns(headers, "p1")
    assert "amount_fy2024_actual" in mapping
    assert "amount_fy2025_enacted" in mapping
    assert "amount_fy2026_request" in mapping


def test_map_columns_year_agnostic():
    """Year-agnostic detection works for any fiscal year (Step 1.B2-a)."""
    headers = [
        "Account", "Account Title",
        "FY2022 Actual\nAmount",
        "FY2023 Enacted\nAmount",
        "FY2023 Supplemental\nAmount",
        "FY2023 Total\nAmount",
        "FY2024 Request\nAmount",
        "FY2024 Reconciliation\nAmount",
    ]
    mapping = _map_columns(headers, "p1")
    assert "amount_fy2022_actual" in mapping
    assert "amount_fy2023_enacted" in mapping
    assert "amount_fy2023_supplemental" in mapping
    assert "amount_fy2023_total" in mapping
    assert "amount_fy2024_request" in mapping
    assert "amount_fy2024_reconciliation" in mapping


def test_map_columns_case_insensitive():
    """Column matching is case-insensitive."""
    headers = [
        "ACCOUNT", "ACCOUNT TITLE", "ORGANIZATION",
        "BUDGET ACTIVITY", "BUDGET ACTIVITY TITLE",
        "BUDGET LINE ITEM", "BUDGET LINE ITEM (BLI) TITLE",
    ]
    mapping = _map_columns(headers, "p1")
    assert "account" in mapping
    assert "account_title" in mapping
    assert "organization" in mapping
    assert "line_item" in mapping
    assert "line_item_title" in mapping


# ── 1.C2-b: sanitize_filename tests ──────────────────────────────────────────

def test_sanitize_filename_normal():
    """Normal filenames pass through unchanged."""
    assert sanitize_filename("budget_FY2026.xlsx") == "budget_FY2026.xlsx"


def test_sanitize_filename_path_separators():
    """Forward and backward slashes are replaced with underscores."""
    result = sanitize_filename("army/budget\\file.pdf")
    assert "/" not in result
    assert "\\" not in result


def test_sanitize_filename_query_string():
    """Query parameters after '?' are stripped."""
    result = sanitize_filename("file.pdf?key=value&other=123")
    assert "?" not in result
    assert result == "file.pdf"


def test_sanitize_filename_invalid_chars():
    """Invalid filesystem characters are replaced."""
    for ch in '<>:"|*':
        result = sanitize_filename(f"file{ch}name.pdf")
        assert ch not in result


def test_sanitize_filename_unicode():
    """Unicode filenames are handled without error."""
    result = sanitize_filename("budzhet_\u0444\u0430\u0439\u043b.pdf")
    assert isinstance(result, str)
    assert len(result) > 0


def test_sanitize_filename_empty():
    """Empty string returns a string (not None or an exception)."""
    result = sanitize_filename("")
    assert isinstance(result, str)


# ── 1.C2-d: _extract_pe_number tests ─────────────────────────────────────────

def test_extract_pe_number_valid():
    """Standard 7-digit + 1-2 uppercase letter PE numbers are extracted."""
    assert _extract_pe_number("0602702E") == "0602702E"
    assert _extract_pe_number("0305116BB") == "0305116BB"


def test_extract_pe_number_embedded():
    """PE number embedded in a longer string is found correctly."""
    result = _extract_pe_number("Program 0801273F Advanced Research")
    assert result == "0801273F"


def test_extract_pe_number_no_match():
    """Returns None when no PE number is present."""
    assert _extract_pe_number("no pe here") is None
    assert _extract_pe_number("") is None
    assert _extract_pe_number(None) is None


def test_extract_pe_number_returns_first():
    """When multiple PE numbers appear, the first match is returned."""
    result = _extract_pe_number("0602702E and 0305116BB programs")
    assert result == "0602702E"


# ── 1.B3-a: _detect_amount_unit tests ────────────────────────────────────────

def test_detect_amount_unit_default():
    """Returns 'thousands' when no unit indicator is found."""
    rows = [["Account", "Title", "FY2026 Request"]]
    assert _detect_amount_unit(rows, 0) == "thousands"


def test_detect_amount_unit_thousands():
    """Explicit 'in thousands' label returns 'thousands'."""
    rows = [["DoD Budget", "in thousands", None], ["Account", "Title"]]
    assert _detect_amount_unit(rows, 1) == "thousands"


def test_detect_amount_unit_millions():
    """'in millions' label returns 'millions'."""
    rows = [["$ millions"], ["Account", "Title"]]
    assert _detect_amount_unit(rows, 1) == "millions"


def test_detect_amount_unit_millions_in_header_row():
    """Unit keyword in the header row itself is detected."""
    rows = [["Account", "($ millions)", "FY2026"]]
    assert _detect_amount_unit(rows, 0) == "millions"


def test_detect_amount_unit_empty_rows():
    """Empty/None cells are skipped without error."""
    rows = [[None, None], [None]]
    assert _detect_amount_unit(rows, 1) == "thousands"


def test_detect_amount_unit_millions_priority():
    """Millions keyword takes precedence when detected before thousands."""
    rows = [["in millions of dollars, prior amounts in thousands"]]
    # 'in millions' appears first in the keyword scan → millions wins
    assert _detect_amount_unit(rows, 0) == "millions"
