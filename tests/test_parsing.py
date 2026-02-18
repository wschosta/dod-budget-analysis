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
    _merge_header_rows,
    _normalise_fiscal_year,
    _parse_appropriation,
    _detect_currency_year,
)
from utils.common import sanitize_filename
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
    # Step 1.B1-g: detail exhibit types
    ("p5_display.xlsx", "p5"),
    ("r2_display.xlsx", "r2"),
    ("r3_display.xlsx", "r3"),
    ("r4_display.xlsx", "r4"),
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


# ── 1.B2-c: _merge_header_rows tests ─────────────────────────────────────────

def test_merge_header_rows_two_row_split():
    """Two-row split headers (e.g. 'FY 2026' / 'Request Amount') are merged."""
    header = ["Account", "Account Title", "FY 2026", "FY 2025"]
    sub    = [None,      None,            "Request Amount", "Enacted Amount"]
    merged = _merge_header_rows(header, sub)
    assert merged[0] == "Account"          # unchanged
    assert merged[1] == "Account Title"    # unchanged
    assert "FY 2026" in merged[2] and "Request Amount" in merged[2]
    assert "FY 2025" in merged[3] and "Enacted Amount" in merged[3]


def test_merge_header_rows_all_blank_sub():
    """All-blank sub-row returns the header row unchanged."""
    header = ["Account", "FY2026 Request"]
    sub    = [None, None]
    merged = _merge_header_rows(header, sub)
    assert merged == list(header)


def test_merge_header_rows_numeric_sub_not_merged():
    """Sub-row with numeric values is treated as a data row — not merged."""
    header = ["Account", "Title", "FY2026 Request"]
    sub    = ["001",     "Widget", "1234.0"]
    merged = _merge_header_rows(header, sub)
    assert merged == list(header)


def test_merge_header_rows_long_text_not_merged():
    """Sub-row with long narrative text is not merged (data row heuristic)."""
    header = ["Account", "Description"]
    sub    = ["A", "This is a very long narrative description that exceeds 50 characters and represents real data"]
    merged = _merge_header_rows(header, sub)
    assert merged == list(header)


def test_merge_header_rows_two_row_map_columns():
    """After merging two-row headers, _map_columns produces correct mapping."""
    header = ["Account", "Account Title", "FY2026", "FY2025", "FY2024"]
    sub    = [None,       None,           "Request Amount", "Enacted Amount", "Actual Amount"]
    merged = _merge_header_rows(header, sub)
    mapping = _map_columns(merged, "p1")
    assert "account" in mapping
    assert "amount_fy2026_request" in mapping
    assert "amount_fy2025_enacted" in mapping
    assert "amount_fy2024_actual" in mapping


# ── 1.B2-d: _normalise_fiscal_year tests ─────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("2026",          "FY 2026"),  # bare year → canonical
    ("FY2026",        "FY 2026"),  # no space → canonical
    ("FY 2026",       "FY 2026"),  # already canonical
    ("FY2024",        "FY 2024"),
    ("fy 2025",       "FY 2025"),  # lowercase
    ("Sheet FY2026",  "FY 2026"),  # embedded in sheet name
    ("no year here",  "no year here"),  # no year → unchanged
])
def test_normalise_fiscal_year(raw, expected):
    assert _normalise_fiscal_year(raw) == expected


# ── 1.B4-c: _parse_appropriation tests ───────────────────────────────────────

@pytest.mark.parametrize("account_title, exp_code, exp_title", [
    ("2035 Aircraft Procurement, Army",  "2035", "Aircraft Procurement, Army"),
    ("1300 RDT&E, Army",                 "1300", "RDT&E, Army"),
    ("2100 Military Construction, Army", "2100", "Military Construction, Army"),
    ("No Code Title",                    None,   "No Code Title"),
    ("",                                 None,   None),
    (None,                               None,   None),
    ("1234",                             None,   "1234"),   # only code, no title
    ("ABC 1234 Title",                   None,   "ABC 1234 Title"),  # non-numeric prefix
])
def test_parse_appropriation(account_title, exp_code, exp_title):
    code, title = _parse_appropriation(account_title)
    assert code == exp_code
    assert title == exp_title


# ── 1.B3-b: _detect_currency_year tests ──────────────────────────────────────

@pytest.mark.parametrize("sheet_name, filename, expected", [
    ("FY 2026",          "p1_army.xlsx",             "then-year"),  # default
    ("Constant Dollars", "r1.xlsx",                  "constant"),   # keyword in sheet
    ("FY 2026",          "r1_constant_dollars.xlsx", "constant"),   # keyword in filename
    ("Then-Year",        "p1.xlsx",                  "then-year"),  # explicit then-year
    ("Then Year Prices", "m1.xlsx",                  "then-year"),  # alternate phrasing
    ("",                 "budget.xlsx",              "then-year"),  # empty → default
])
def test_detect_currency_year(sheet_name, filename, expected):
    assert _detect_currency_year(sheet_name, filename) == expected
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
