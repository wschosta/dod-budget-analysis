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
    # Page with many rectangles (typical table layout)
    page = MockPageWithTables(num_rects=20, num_curves=10)
    assert _likely_has_tables(page), "Page with 20 rects + 10 curves should be detected as table"

    # Page with exact threshold
    page = MockPageWithTables(num_rects=10, num_curves=1)
    assert _likely_has_tables(page), "Page with 10 rects + 1 curve (>10 total) should be detected as table"

    # Page below threshold
    page = MockPageWithTables(num_rects=5, num_curves=4)
    assert not _likely_has_tables(page), "Page with 5 rects + 4 curves (=9 total) should NOT be table"


def test_likely_has_tables_text_only():
    """Test that _likely_has_tables skips text-only pages."""
    page = MockPageTextOnly()
    assert not _likely_has_tables(page), "Text-only page should not be detected as table"


def test_likely_has_tables_missing_attributes():
    """Test that _likely_has_tables gracefully handles missing attributes."""
    page = MockPageWithoutAttrs()
    assert not _likely_has_tables(page), "Malformed page should return False"


def test_map_columns_empty_edge_cases():
    """Test _map_columns with edge cases and empty/None values."""
    from build_budget_db import _map_columns

    # Empty header list
    mapping = _map_columns([], "p1")
    assert mapping == {}, f"Empty header list should return empty mapping, got {mapping}"

    # Headers with None values
    headers = [None, "Account", None, "Account Title"]
    mapping = _map_columns(headers, "p1")
    assert "account" in mapping and "account_title" in mapping, \
        f"Headers with None values: failed to parse, got {mapping}"

    # Headers with whitespace-only strings
    headers = ["   ", "Account", "\t\n", "Account Title"]
    mapping = _map_columns(headers, "p1")
    assert "account" in mapping and "account_title" in mapping, \
        f"Headers with whitespace: failed to parse, got {mapping}"


def test_map_columns_quantity_vs_amount():
    """Test that _map_columns correctly distinguishes quantity from amount columns."""
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

    for field, expected_col in expected.items():
        assert field in mapping and mapping[field] == expected_col, \
            f"{field}: got {mapping.get(field, 'NOT FOUND')}, expected {expected_col}"


def test_map_columns_case_insensitivity():
    """Test that _map_columns handles case variations."""
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

    for field, expected_col in expected.items():
        assert field in mapping and mapping[field] == expected_col, \
            f"{field}: got {mapping.get(field, 'NOT FOUND')}, expected {expected_col}"


def test_extract_table_text_large_tables():
    """Test _extract_table_text with large/complex tables."""
    from build_budget_db import _extract_table_text

    # Create a large table with many rows
    large_table = []
    for i in range(100):
        row = [f"Cell_{i}_{j}" for j in range(10)]
        large_table.append(row)

    result = _extract_table_text([large_table])
    lines = result.strip().split("\n")
    assert len(lines) == 100, f"Large table: expected 100 lines, got {len(lines)}"

    # Table with many None values
    sparse_table = [
        [None, "A", None, "B", None],
        [None, None, None, None, None],
        ["X", None, "Y", None, "Z"],
    ]
    result = _extract_table_text([sparse_table])
    lines = result.strip().split("\n") if result.strip() else []
    assert len(lines) == 2, f"Sparse table: expected 2 lines, got {len(lines)}"


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
    run_all_advanced_tests()
