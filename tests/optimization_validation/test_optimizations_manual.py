#!/usr/bin/env python3
"""
Manual test suite for build_budget_db.py optimizations.
Tests the key optimized functions without requiring full dependencies.
"""

import sys
import types
from pathlib import Path

# Stub heavy dependencies to avoid import failures
for _mod in ("pdfplumber", "openpyxl"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

from build_budget_db import (  # noqa: E402
    _detect_exhibit_type,
    _safe_float,
    _extract_table_text,
    _determine_category,
    _map_columns,
)


def test_map_columns_single_pass():
    """
    Test that _map_columns correctly identifies all column types in a single pass.
    This validates the optimization that consolidated 4 loops into 1.
    """
    print("\n" + "="*70)
    print("TEST 1: _map_columns Single-Pass Optimization")
    print("="*70)

    headers = [
        "Account", "Account Title", "Organization",
        "Budget Activity", "Budget Activity Title",
        "Budget Line Item", "Budget Line Item (BLI) Title",
        "FY2024 Actual Amount", "FY2025 Enacted Amount",
        "FY2025 Supplemental", "FY2025 Total Amount",
        "FY2026 Request Amount", "FY2026 Reconciliation",
        "FY2026 Total Amount",
        "Classification",
    ]

    mapping = _map_columns(headers, "p1")

    # Verify all expected fields are found
    expected_fields = [
        "account", "account_title", "organization",
        "budget_activity", "budget_activity_title",
        "line_item", "line_item_title",
        "amount_fy2024_actual", "amount_fy2025_enacted",
        "amount_fy2025_supplemental", "amount_fy2025_total",
        "amount_fy2026_request", "amount_fy2026_reconciliation",
        "amount_fy2026_total",
        "classification",
    ]

    success = True
    for field in expected_fields:
        if field in mapping:
            print(f"  ✓ {field}: column {mapping[field]}")
        else:
            print(f"  ✗ MISSING: {field}")
            success = False

    if success:
        print(f"\n  ✓ All {len(expected_fields)} expected fields found in single pass")
    else:
        print("\n  ✗ Some fields were not found")

    assert success


def test_map_columns_with_spaces_and_newlines():
    """Test that _map_columns handles spaces and newlines correctly."""
    print("\n" + "="*70)
    print("TEST 2: _map_columns with Spaces and Newlines")
    print("="*70)

    headers = [
        "Account", "Account Title",
        "FY 2024\nActual\nAmount",  # Multi-line header
        "FY 2025 Enacted Amount",   # Spaces instead of tabs
        "FY2026RequestAmount",       # No spaces
    ]

    mapping = _map_columns(headers, "p1")

    expected_mappings = {
        "account": 0,
        "account_title": 1,
        "amount_fy2024_actual": 2,
        "amount_fy2025_enacted": 3,
        "amount_fy2026_request": 4,
    }

    success = True
    for field, expected_col in expected_mappings.items():
        if field in mapping and mapping[field] == expected_col:
            print(f"  ✓ {field}: column {mapping[field]} (expected {expected_col})")
        else:
            actual = mapping.get(field, "NOT FOUND")
            print(f"  ✗ {field}: got {actual}, expected {expected_col}")
            success = False

    assert success


def test_map_columns_c1_exhibit():
    """Test C-1 (Military Construction) special columns."""
    print("\n" + "="*70)
    print("TEST 3: _map_columns C-1 Exhibit Type")
    print("="*70)

    headers = [
        "Account", "Account Title",
        "Construction Project", "Construction Project Title",
        "Authorization Amount", "Appropriation Amount",
        "Total Obligation Authority",
    ]

    mapping = _map_columns(headers, "c1")

    # C-1 exhibits use construction project instead of line item
    expected_fields = [
        ("account", 0),
        ("line_item", 2),  # Construction Project maps to line_item
        ("line_item_title", 3),  # Construction Project Title
        ("amount_fy2026_request", 4),  # Authorization Amount
        ("amount_fy2025_enacted", 5),  # Appropriation Amount
        ("amount_fy2026_total", 6),  # Total Obligation Authority
    ]

    success = True
    for field, expected_col in expected_fields:
        if field in mapping and mapping[field] == expected_col:
            print(f"  ✓ {field}: column {mapping[field]}")
        else:
            actual = mapping.get(field, "NOT FOUND")
            print(f"  ✗ {field}: got {actual}, expected {expected_col}")
            success = False

    assert success


def test_extract_table_text_optimization():
    """Test that _extract_table_text works correctly with the optimized streaming approach."""
    print("\n" + "="*70)
    print("TEST 4: _extract_table_text Optimization")
    print("="*70)

    # Test empty tables
    result = _extract_table_text([])
    assert result == "", f"Empty table list: expected '', got '{result}'"
    print("  ✓ Empty table list returns empty string")

    # Test single table
    tables = [[
        ["Col1", "Col2", "Col3"],
        ["A", "B", "C"],
        ["D", None, "F"],
    ]]
    result = _extract_table_text(tables)
    lines = result.strip().split("\n")

    expected_line_count = 3
    assert len(lines) == expected_line_count, f"Single table: expected {expected_line_count} lines, got {len(lines)}"
    print(f"  ✓ Single table: {len(lines)} lines extracted")

    # Verify None cells are filtered out
    assert "Col1 | Col2 | Col3" in lines[0], f"Header row incorrect: {lines[0]}"
    print(f"  ✓ Header row: {lines[0]}")

    assert "D | F" in lines[2], f"Row with None: got '{lines[2]}'"
    print("  ✓ Row with None: correctly filtered to 'D | F'")

    # Test multiple tables
    tables = [
        [["A", "B"]],
        [["C", "D"]],
        None,  # None table should be skipped
        [[]],  # Empty table should be skipped
    ]
    result = _extract_table_text(tables)
    lines = result.strip().split("\n") if result.strip() else []

    assert len(lines) == 2, f"Multiple tables: expected 2 lines, got {len(lines)}"
    print(f"  ✓ Multiple tables: {len(lines)} valid lines extracted, empty/None tables skipped")


def test_safe_float():
    """Test _safe_float robustness."""
    print("\n" + "="*70)
    print("TEST 5: _safe_float Robustness")
    print("="*70)

    test_cases = [
        (None, 0.0),
        ("", 0.0),
        (" ", 0.0),
        ("123", 123.0),
        (123, 123.0),
        (0, 0.0),
        ("abc", 0.0),
        ("12.34", 12.34),
        ("-5.5", -5.5),
    ]

    success = True
    for val, expected in test_cases:
        result = _safe_float(val)
        if result == expected:
            print(f"  ✓ {repr(val):15} → {result}")
        else:
            print(f"  ✗ {repr(val):15} → {result} (expected {expected})")
            success = False

    assert success


def test_detect_exhibit_type():
    """Test exhibit type detection."""
    print("\n" + "="*70)
    print("TEST 6: _detect_exhibit_type")
    print("="*70)

    test_cases = [
        ("p1_display.xlsx", "p1"),
        ("r1.xlsx", "r1"),
        ("c1_display.xlsx", "c1"),
        ("p1r_display.xlsx", "p1r"),
        ("m1_something_else.xlsx", "m1"),
        ("P1_DISPLAY.xlsx", "p1"),  # case insensitive
        ("army_p1r_fy2026.xlsx", "p1r"),  # p1r before p1
        ("unknown_file.xlsx", "unknown"),
    ]

    success = True
    for filename, expected in test_cases:
        result = _detect_exhibit_type(filename)
        if result == expected:
            print(f"  ✓ {filename:30} → {result}")
        else:
            print(f"  ✗ {filename:30} → {result} (expected {expected})")
            success = False

    assert success


def test_determine_category():
    """Test category determination from file path."""
    print("\n" + "="*70)
    print("TEST 7: _determine_category")
    print("="*70)

    test_cases = [
        ("DoD_Budget_Documents/FY2026/Comptroller/file.pdf", "Comptroller"),
        ("DoD_Budget_Documents/FY2026/US_Army/file.xlsx", "Army"),
        ("DoD_Budget_Documents/FY2026/Defense_Wide/file.pdf", "Defense-Wide"),
        ("DoD_Budget_Documents/FY2026/Navy/file.xlsx", "Navy"),
        ("DoD_Budget_Documents/FY2026/Air_Force/file.pdf", "Air Force"),
    ]

    success = True
    for path_str, expected in test_cases:
        result = _determine_category(Path(path_str))
        if result == expected:
            print(f"  ✓ {path_str:50} → {result}")
        else:
            print(f"  ✗ {path_str:50} → {result} (expected {expected})")
            success = False

    assert success


def run_all_tests():
    """Run all manual tests and report results."""
    print("\n" + "="*70)
    print("MANUAL OPTIMIZATION TEST SUITE")
    print("="*70)

    tests = [
        test_map_columns_single_pass,
        test_map_columns_with_spaces_and_newlines,
        test_map_columns_c1_exhibit,
        test_extract_table_text_optimization,
        test_safe_float,
        test_detect_exhibit_type,
        test_determine_category,
    ]

    results = []
    for test in tests:
        try:
            test()
            results.append((test.__name__, True))
            print(f"  ✓ PASS: {test.__name__}")
        except Exception as e:
            print(f"  ✗ FAIL: {test.__name__}: {e}")
            results.append((test.__name__, False))

    passed = sum(1 for _, result in results if result)
    total = len(results)
    print(f"\nTotal: {passed}/{total} tests passed")


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
