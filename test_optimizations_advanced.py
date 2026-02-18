#!/usr/bin/env python3
"""
Advanced tests for build_budget_db.py optimizations.
Tests the streaming row logic and PDF table detection heuristic logic.
"""

import sys
import types
from pathlib import Path

# Stub heavy dependencies
for _mod in ("openpyxl", "pdfplumber"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

from build_budget_db import _likely_has_tables


class MockPageWithTables:
    """Mock PDF page object with table-like structures."""
    def __init__(self, num_rects=15, num_curves=5):
        self.rects = list(range(num_rects))  # Mock rectangles
        self.curves = list(range(num_curves))  # Mock curves


class MockPageTextOnly:
    """Mock PDF page object with no table-like structures."""
    def __init__(self):
        self.rects = []
        self.curves = []


class MockPageWithoutAttrs:
    """Mock PDF page that doesn't have rects/curves attributes."""
    pass


def test_likely_has_tables_with_structure():
    """Test that _likely_has_tables detects pages with table structures."""
    print("\n" + "="*70)
    print("TEST 1: _likely_has_tables with Table Structures")
    print("="*70)

    # Page with many rectangles (typical table layout)
    page = MockPageWithTables(num_rects=20, num_curves=10)
    result = _likely_has_tables(page)
    if result:
        print(f"  ✓ Page with 20 rects + 10 curves: detected as table (result=True)")
    else:
        print(f"  ✗ Page with 20 rects + 10 curves: should be table (result=False)")
        return False

    # Page with exact threshold
    page = MockPageWithTables(num_rects=10, num_curves=1)
    result = _likely_has_tables(page)
    if result:
        print(f"  ✓ Page with 10 rects + 1 curve (>10 total): detected as table (result=True)")
    else:
        print(f"  ✗ Page with 10 rects + 1 curve (>10 total): should be table")
        return False

    # Page below threshold
    page = MockPageWithTables(num_rects=5, num_curves=4)
    result = _likely_has_tables(page)
    if not result:
        print(f"  ✓ Page with 5 rects + 4 curves (=9 total): not detected as table (result=False)")
    else:
        print(f"  ✗ Page with 5 rects + 4 curves (=9 total): should NOT be table")
        return False

    return True


def test_likely_has_tables_text_only():
    """Test that _likely_has_tables skips text-only pages."""
    print("\n" + "="*70)
    print("TEST 2: _likely_has_tables Text-Only Pages")
    print("="*70)

    # Page with no rects or curves (pure text)
    page = MockPageTextOnly()
    result = _likely_has_tables(page)
    if not result:
        print(f"  ✓ Text-only page (0 rects, 0 curves): skipped (result=False)")
    else:
        print(f"  ✗ Text-only page: should be skipped (result=False)")
        return False

    return True


def test_likely_has_tables_missing_attributes():
    """Test that _likely_has_tables gracefully handles missing attributes."""
    print("\n" + "="*70)
    print("TEST 3: _likely_has_tables Error Handling")
    print("="*70)

    # Page without rects/curves attributes (malformed PDF)
    page = MockPageWithoutAttrs()
    result = _likely_has_tables(page)
    if not result:
        print(f"  ✓ Malformed page (missing attributes): gracefully returns False")
    else:
        print(f"  ✗ Malformed page: should return False on error")
        return False

    return True


def test_map_columns_empty_edge_cases():
    """Test _map_columns with edge cases and empty/None values."""
    print("\n" + "="*70)
    print("TEST 4: _map_columns Edge Cases")
    print("="*70)

    from build_budget_db import _map_columns

    # Empty header list
    mapping = _map_columns([], "p1")
    if mapping == {}:
        print(f"  ✓ Empty header list: returns empty mapping")
    else:
        print(f"  ✗ Empty header list: expected {{}}, got {mapping}")
        return False

    # Headers with None values
    headers = [None, "Account", None, "Account Title"]
    mapping = _map_columns(headers, "p1")
    if "account" in mapping and "account_title" in mapping:
        print(f"  ✓ Headers with None values: correctly identified valid headers")
    else:
        print(f"  ✗ Headers with None values: failed to parse")
        return False

    # Headers with whitespace-only strings
    headers = ["   ", "Account", "\t\n", "Account Title"]
    mapping = _map_columns(headers, "p1")
    if "account" in mapping and "account_title" in mapping:
        print(f"  ✓ Headers with whitespace: correctly identified valid headers")
    else:
        print(f"  ✗ Headers with whitespace: failed to parse")
        return False

    return True


def test_map_columns_quantity_vs_amount():
    """Test that _map_columns correctly distinguishes quantity from amount columns."""
    print("\n" + "="*70)
    print("TEST 5: _map_columns Quantity vs Amount Distinction")
    print("="*70)

    from build_budget_db import _map_columns

    headers = [
        "Account",
        "FY2024 Actual Quantity",
        "FY2024 Actual Amount",
        "FY2025 Enacted Quantity",
        "FY2025 Enacted Amount",
        "FY2026 Request Quantity",
        "FY2026 Request Amount",
    ]

    mapping = _map_columns(headers, "p1")

    expected = {
        "quantity_fy2024": 1,
        "amount_fy2024_actual": 2,
        "quantity_fy2025": 3,
        "amount_fy2025_enacted": 4,
        "quantity_fy2026_request": 5,
        "amount_fy2026_request": 6,
    }

    success = True
    for field, expected_col in expected.items():
        if field in mapping and mapping[field] == expected_col:
            print(f"  ✓ {field}: column {mapping[field]}")
        else:
            actual = mapping.get(field, "NOT FOUND")
            print(f"  ✗ {field}: got {actual}, expected {expected_col}")
            success = False

    return success


def test_map_columns_case_insensitivity():
    """Test that _map_columns handles case variations."""
    print("\n" + "="*70)
    print("TEST 6: _map_columns Case Insensitivity")
    print("="*70)

    from build_budget_db import _map_columns

    headers = [
        "ACCOUNT", "ACCOUNT TITLE", "Organization",
        "FY2024 ACTUAL AMOUNT", "fy2025 enacted amount",
    ]

    mapping = _map_columns(headers, "p1")

    expected = {
        "account": 0,
        "account_title": 1,
        "organization": 2,
        "amount_fy2024_actual": 3,
        "amount_fy2025_enacted": 4,
    }

    success = True
    for field, expected_col in expected.items():
        if field in mapping and mapping[field] == expected_col:
            print(f"  ✓ {field}: column {mapping[field]} (case-insensitive)")
        else:
            actual = mapping.get(field, "NOT FOUND")
            print(f"  ✗ {field}: got {actual}, expected {expected_col}")
            success = False

    return success


def test_extract_table_text_large_tables():
    """Test _extract_table_text with large/complex tables."""
    print("\n" + "="*70)
    print("TEST 7: _extract_table_text Large Tables")
    print("="*70)

    from build_budget_db import _extract_table_text

    # Create a large table with many rows
    large_table = []
    for i in range(100):
        row = [f"Cell_{i}_{j}" for j in range(10)]
        large_table.append(row)

    result = _extract_table_text([large_table])
    lines = result.strip().split("\n")

    if len(lines) == 100:
        print(f"  ✓ Large table (100x10): correctly processed {len(lines)} lines")
    else:
        print(f"  ✗ Large table: expected 100 lines, got {len(lines)}")
        return False

    # Table with many None values
    sparse_table = [
        [None, "A", None, "B", None],
        [None, None, None, None, None],
        ["X", None, "Y", None, "Z"],
    ]
    result = _extract_table_text([sparse_table])
    lines = result.strip().split("\n") if result.strip() else []

    if len(lines) == 2:  # Empty row should be skipped
        print(f"  ✓ Sparse table with None values: {len(lines)} non-empty lines")
    else:
        print(f"  ✗ Sparse table: expected 2 lines, got {len(lines)}")
        return False

    return True


def run_all_advanced_tests():
    """Run all advanced tests."""
    print("\n" + "="*70)
    print("ADVANCED OPTIMIZATION TEST SUITE")
    print("="*70)

    tests = [
        test_likely_has_tables_with_structure,
        test_likely_has_tables_text_only,
        test_likely_has_tables_missing_attributes,
        test_map_columns_empty_edge_cases,
        test_map_columns_quantity_vs_amount,
        test_map_columns_case_insensitivity,
        test_extract_table_text_large_tables,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"\n  ✗ EXCEPTION in {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            results.append((test.__name__, False))

    # Summary
    print("\n" + "="*70)
    print("ADVANCED TEST SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n✓ All advanced tests passed!")
        return True
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = run_all_advanced_tests()
    sys.exit(0 if success else 1)
