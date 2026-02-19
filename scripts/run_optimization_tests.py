#!/usr/bin/env python
"""
Standalone Optimization Test Runner

Runs the optimization test suite without pytest dependency.
Verifies that performance optimizations are working correctly.

Usage:
    python run_optimization_tests.py              # Run all tests
    python run_optimization_tests.py --verbose    # Show detailed output
    python run_optimization_tests.py --benchmark  # Include performance benchmarks
"""

import argparse
import re
import sqlite3
import sys
import tempfile
import time
import traceback
from pathlib import Path

# Import shared utilities
from utils import (
    format_bytes,
    elapsed,
    sanitize_filename,
    get_connection,
    safe_float,
    normalize_whitespace,
    sanitize_fts5_query,
)
from utils.patterns import (
    DOWNLOADABLE_EXTENSIONS,
    PE_NUMBER,
    FTS5_SPECIAL_CHARS,
    FISCAL_YEAR,
    ACCOUNT_CODE_TITLE,
    WHITESPACE,
    CURRENCY_SYMBOLS,
)


class TestRunner:
    """Simple test runner for optimization tests."""

    def __init__(self, verbose=False, run_benchmarks=False):
        self.verbose = verbose
        self.run_benchmarks = run_benchmarks
        self.passed = 0
        self.failed = 0
        self.tests = []

    def test(self, name, func):
        """Register and run a test."""
        try:
            func()
            self.passed += 1
            status = "[PASS]"
            if self.verbose:
                print(f"{status} {name}")
            else:
                print(".", end="", flush=True)
        except AssertionError as e:
            self.failed += 1
            status = "[FAIL]"
            print(f"\n{status} {name}")
            print(f"  Error: {e}")
            if self.verbose:
                traceback.print_exc()
        except Exception as e:
            self.failed += 1
            status = "[ERROR]"
            print(f"\n{status} {name}")
            print(f"  Error: {e}")
            if self.verbose:
                traceback.print_exc()

    def benchmark(self, name, func):
        """Run a benchmark test."""
        if not self.run_benchmarks:
            return

        try:
            result = func()
            print(f"\n[BENCHMARK] {name}")
            print(f"  {result}")
            self.passed += 1
        except Exception as e:
            self.failed += 1
            print(f"\n[BENCHMARK ERROR] {name}")
            print(f"  Error: {e}")

    def summary(self):
        """Print test summary."""
        total = self.passed + self.failed
        print()
        print("=" * 70)
        print(f"Test Results: {self.passed} passed, {self.failed} failed ({total} total)")
        print("=" * 70)
        return self.failed == 0


def test_precompiled_patterns(runner):
    """Test pre-compiled regex patterns."""
    print("\nTesting Pre-compiled Regex Patterns...")

    runner.test("DOWNLOADABLE_EXTENSIONS matches PDF", lambda: (
        DOWNLOADABLE_EXTENSIONS.search("document.pdf") and True or (_ for _ in ()).throw(AssertionError("No match"))
    ))

    runner.test("DOWNLOADABLE_EXTENSIONS matches Excel", lambda: (
        DOWNLOADABLE_EXTENSIONS.search("budget.XLSX") and True or (_ for _ in ()).throw(AssertionError("No match"))
    ))

    runner.test("PE_NUMBER matches standard format", lambda: (
        PE_NUMBER.search("0602702E") and True or (_ for _ in ()).throw(AssertionError("No match"))
    ))

    runner.test("PE_NUMBER rejects invalid format", lambda: (
        not PE_NUMBER.search("602702E") and True or (_ for _ in ()).throw(AssertionError("Should not match"))
    ))

    runner.test("FISCAL_YEAR matches FY2026", lambda: (
        FISCAL_YEAR.search("FY2026") and True or (_ for _ in ()).throw(AssertionError("No match"))
    ))

    runner.test("ACCOUNT_CODE_TITLE parses correctly", lambda: (
        ACCOUNT_CODE_TITLE.match("2035 Aircraft Procurement, Air Force").groups() == ("2035", "Aircraft Procurement, Air Force")
        or (_ for _ in ()).throw(AssertionError("No match"))
    ))

    runner.test("FTS5_SPECIAL_CHARS detects quotes", lambda: (
        FTS5_SPECIAL_CHARS.search('query"with"quotes') and True or (_ for _ in ()).throw(AssertionError("No match"))
    ))

    # Benchmark pattern performance
    def pattern_benchmark():
        start = time.perf_counter()
        for _ in range(100000):
            DOWNLOADABLE_EXTENSIONS.search("file.pdf")
        elapsed_time = (time.perf_counter() - start) * 1_000_000
        avg = elapsed_time / 100000
        return f"{avg:.3f} µs per search (100k searches in {elapsed_time/1000:.1f}ms)"

    runner.benchmark("Pre-compiled pattern search performance", pattern_benchmark)


def test_safe_float(runner):
    """Test safe_float conversion."""
    print("\nTesting Safe Float Conversion...")

    runner.test("safe_float converts integer", lambda: safe_float(42) == 42.0 or (_ for _ in ()).throw(AssertionError("Failed")))
    runner.test("safe_float converts string", lambda: safe_float("123.45") == 123.45 or (_ for _ in ()).throw(AssertionError("Failed")))
    runner.test("safe_float strips currency", lambda: safe_float("$1000") == 1000.0 or (_ for _ in ()).throw(AssertionError("Failed")))
    runner.test("safe_float handles commas", lambda: safe_float("1,234.56") == 1234.56 or (_ for _ in ()).throw(AssertionError("Failed")))
    runner.test("safe_float handles None", lambda: safe_float(None) == 0.0 or (_ for _ in ()).throw(AssertionError("Failed")))
    runner.test("safe_float handles invalid input", lambda: safe_float("not a number") == 0.0 or (_ for _ in ()).throw(AssertionError("Failed")))
    runner.test("safe_float uses custom default", lambda: safe_float(None, default=99.0) == 99.0 or (_ for _ in ()).throw(AssertionError("Failed")))

    # Benchmark performance
    def float_benchmark():
        test_values = ["123.45", "$1,234.56", None, "invalid", "€5000"]
        start = time.perf_counter()
        for _ in range(100000):
            for val in test_values:
                safe_float(val)
        elapsed_time = (time.perf_counter() - start) * 1_000_000
        total_ops = 100000 * len(test_values)
        avg = elapsed_time / total_ops
        return f"{avg:.3f} µs per conversion ({total_ops} conversions in {elapsed_time/1000:.1f}ms)"

    runner.benchmark("Safe float conversion performance", float_benchmark)


def test_string_utilities(runner):
    """Test string utility functions."""
    print("\nTesting String Utilities...")

    runner.test("normalize_whitespace removes extra spaces", lambda: (
        normalize_whitespace("  text  ") == "text" or (_ for _ in ()).throw(AssertionError("Failed"))
    ))

    runner.test("normalize_whitespace handles newlines", lambda: (
        normalize_whitespace("text\n\nmore") == "text more" or (_ for _ in ()).throw(AssertionError("Failed"))
    ))

    runner.test("sanitize_fts5_query quotes terms", lambda: (
        '"missile"' in sanitize_fts5_query("missile defense") or (_ for _ in ()).throw(AssertionError("Failed"))
    ))

    runner.test("sanitize_fts5_query removes keywords", lambda: (
        "AND" not in sanitize_fts5_query("missile AND defense") or (_ for _ in ()).throw(AssertionError("Failed"))
    ))

    runner.test("sanitize_filename removes invalid chars", lambda: (
        sanitize_filename("file<>name.xlsx") == "file__name.xlsx" or (_ for _ in ()).throw(AssertionError("Failed"))
    ))

    runner.test("sanitize_filename strips query strings", lambda: (
        "?" not in sanitize_filename("file.pdf?id=123") or (_ for _ in ()).throw(AssertionError("Failed"))
    ))


def test_format_utilities(runner):
    """Test formatting utilities."""
    print("\nTesting Format Utilities...")

    runner.test("format_bytes displays KB", lambda: (
        format_bytes(512 * 1024) == "512 KB" or (_ for _ in ()).throw(AssertionError("Failed"))
    ))

    runner.test("format_bytes displays MB", lambda: (
        "MB" in format_bytes(5 * 1024 * 1024) or (_ for _ in ()).throw(AssertionError("Failed"))
    ))

    runner.test("format_bytes displays GB", lambda: (
        "GB" in format_bytes(2 * 1024 * 1024 * 1024) or (_ for _ in ()).throw(AssertionError("Failed"))
    ))

    runner.test("elapsed formats seconds correctly", lambda: (
        "m" in elapsed(time.time() - 30) or (_ for _ in ()).throw(AssertionError("Failed"))
    ))

    runner.test("elapsed formats minutes correctly", lambda: (
        "m" in elapsed(time.time() - 150) or (_ for _ in ()).throw(AssertionError("Failed"))
    ))


def test_module_imports(runner):
    """Test that modules import correctly."""
    print("\nTesting Module Imports...")

    def test_utils_exports():
        import utils
        for attr in ["format_bytes", "elapsed", "sanitize_filename", "get_connection"]:
            if not hasattr(utils, attr):
                raise AssertionError(f"utils missing {attr}")

    runner.test("utils package exports required functions", test_utils_exports)

    def test_patterns_exports():
        import utils.patterns
        for attr in ["DOWNLOADABLE_EXTENSIONS", "PE_NUMBER", "FTS5_SPECIAL_CHARS"]:
            if not hasattr(utils.patterns, attr):
                raise AssertionError(f"utils.patterns missing {attr}")

    runner.test("utils.patterns exports required patterns", test_patterns_exports)

    def test_main_modules():
        import dod_budget_downloader
        import search_budget
        import validate_budget_db
        import build_budget_db

        if not hasattr(dod_budget_downloader, "format_bytes"):
            raise AssertionError("dod_budget_downloader missing format_bytes")
        if not hasattr(search_budget, "get_connection"):
            raise AssertionError("search_budget missing get_connection")

    runner.test("main modules import utilities correctly", test_main_modules)


def main():
    parser = argparse.ArgumentParser(description="Run optimization tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    parser.add_argument("--benchmark", "-b", action="store_true", help="Include performance benchmarks")
    args = parser.parse_args()

    runner = TestRunner(verbose=args.verbose, run_benchmarks=args.benchmark)

    print("\n" + "=" * 70)
    print("OPTIMIZATION TEST SUITE")
    print("=" * 70)

    # Run all test groups
    test_precompiled_patterns(runner)
    test_safe_float(runner)
    test_string_utilities(runner)
    test_format_utilities(runner)
    test_module_imports(runner)

    # Print summary and exit
    success = runner.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
