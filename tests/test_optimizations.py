"""
Optimization Test Suite — Module Imports, Backward Compatibility, Performance Benchmarks

Validates that:
- All key modules import correctly and expose expected utilities
- Refactored code maintains backward compatibility
- Performance benchmarks for regression detection

Functional correctness tests for individual utilities live in their own files:
- test_patterns.py — regex patterns (DOWNLOADABLE_EXTENSIONS, PE_NUMBER, etc.)
- test_common_utils.py — format_bytes, elapsed, sanitize_filename, get_connection
- test_strings_edge_cases.py — safe_float, normalize_whitespace, sanitize_fts5_query

Run with: pytest tests/test_optimizations.py -v --tb=short
"""

import re
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from utils import (
    safe_float,
    normalize_whitespace,
)
from utils.patterns import DOWNLOADABLE_EXTENSIONS

# Optional: bs4 is needed by dod_budget_downloader but may not be installed
_bs4_available = True
try:
    import bs4  # noqa: F401
except ImportError:
    _bs4_available = False

_skip_bs4 = pytest.mark.skipif(not _bs4_available, reason="bs4 not installed")


class TestModuleImports:
    """Verify all modules import correctly and have expected exports."""

    def test_utils_module_imports(self):
        """Test that utils package imports all expected utilities."""
        import utils

        assert hasattr(utils, "format_bytes")
        assert hasattr(utils, "elapsed")
        assert hasattr(utils, "sanitize_filename")
        assert hasattr(utils, "get_connection")
        assert hasattr(utils, "safe_float")
        assert hasattr(utils, "normalize_whitespace")
        assert hasattr(utils, "sanitize_fts5_query")

    def test_patterns_module_imports(self):
        """Test that patterns module has all expected patterns."""
        import utils.patterns

        expected_patterns = [
            "DOWNLOADABLE_EXTENSIONS",
            "PE_NUMBER",
            "FTS5_SPECIAL_CHARS",
            "FISCAL_YEAR",
            "ACCOUNT_CODE_TITLE",
            "WHITESPACE",
            "CURRENCY_SYMBOLS",
        ]

        for pattern_name in expected_patterns:
            assert hasattr(utils.patterns, pattern_name)
            pattern = getattr(utils.patterns, pattern_name)
            assert isinstance(pattern, type(re.compile("")))

    @_skip_bs4
    def test_main_modules_use_shared_utilities(self):
        """Test that main modules properly import shared utilities."""
        import dod_budget_downloader
        import search_budget
        import validate_budget_db
        import build_budget_db

        assert hasattr(dod_budget_downloader, "format_bytes")
        assert hasattr(dod_budget_downloader, "elapsed")
        assert hasattr(dod_budget_downloader, "sanitize_filename")

        assert hasattr(search_budget, "get_connection")
        assert hasattr(search_budget, "sanitize_fts5_query")

        assert hasattr(validate_budget_db, "get_connection")

        assert hasattr(build_budget_db, "safe_float")


class TestBackwardCompatibility:
    """Ensure refactored code maintains backward compatibility."""

    @_skip_bs4
    def test_dod_downloader_patterns_available(self):
        """Verify dod_budget_downloader has DOWNLOADABLE_PATTERN."""
        import dod_budget_downloader

        assert hasattr(dod_budget_downloader, "DOWNLOADABLE_PATTERN")
        assert dod_budget_downloader.DOWNLOADABLE_PATTERN.search("file.pdf")

    def test_build_db_pe_pattern_available(self):
        """Verify build_budget_db has _PE_PATTERN for backward compatibility."""
        import build_budget_db

        assert hasattr(build_budget_db, "_PE_PATTERN")
        assert build_budget_db._PE_PATTERN.search("0602702E")

    def test_search_budget_function_behavior(self):
        """Verify search_budget functions work as before."""
        import search_budget

        result = search_budget.sanitize_fts5_query("test query")
        assert isinstance(result, str)
        assert "test" in result.lower() or "query" in result.lower()


# ── Performance thresholds (assertion-based) ─────────────────────────────────

class TestPerformanceThresholds:
    """Performance threshold tests to catch O(n^2) regressions."""

    def test_pattern_compilation_time(self):
        """Pre-compiled patterns should be near-instant (10k searches < 10ms)."""
        start = time.perf_counter()
        for _ in range(10000):
            DOWNLOADABLE_EXTENSIONS.search("file.pdf")
        elapsed_time = (time.perf_counter() - start) * 1000
        assert elapsed_time < 10, f"Pattern search took {elapsed_time:.1f}ms (expected <10ms)"

    def test_safe_float_conversion_performance(self):
        """50k safe_float conversions should complete in < 500ms."""
        test_values = ["123.45", "$1,234.56", None, "invalid", "\u20ac5000"]
        start = time.perf_counter()
        for _ in range(10000):
            for val in test_values:
                safe_float(val)
        elapsed_time = (time.perf_counter() - start) * 1000
        assert elapsed_time < 500, f"Conversions took {elapsed_time:.1f}ms (expected <500ms)"


# ── Performance benchmarks (informational, no assertions) ────────────────────

class TestPerformanceBenchmarks:
    """Benchmarks for performance regression detection (informational only)."""

    def test_regex_pattern_search_performance(self):
        """Benchmark pre-compiled regex search performance."""
        test_string = "download_file_FY2026_budget_0602702E.pdf"
        start = time.perf_counter()
        for _ in range(100000):
            DOWNLOADABLE_EXTENSIONS.search(test_string)
        elapsed_time = (time.perf_counter() - start) * 1_000_000
        avg_time = elapsed_time / 100000
        print(f"\nPattern search: {avg_time:.3f} \u00b5s per operation")

    def test_safe_float_performance(self):
        """Benchmark safe_float on typical budget values."""
        test_values = ["1,234,567.89", "$5,000,000", "100.50", None, "0"]
        start = time.perf_counter()
        for _ in range(100000):
            for val in test_values:
                safe_float(val)
        elapsed_time = (time.perf_counter() - start) * 1_000_000
        avg_time = elapsed_time / (100000 * len(test_values))
        print(f"\nSafe float: {avg_time:.3f} \u00b5s per conversion")

    def test_string_normalization_performance(self):
        """Benchmark whitespace normalization."""
        test_string = "Aircraft   Procurement\n\nAir   Force\t\tProgram"
        start = time.perf_counter()
        for _ in range(100000):
            normalize_whitespace(test_string)
        elapsed_time = (time.perf_counter() - start) * 1_000_000
        avg_time = elapsed_time / 100000
        print(f"\nWhitespace normalization: {avg_time:.3f} \u00b5s per operation")


class TestApiConnectionPool:
    """Verify API connection pool acquires and releases connections."""

    @staticmethod
    def _create_test_db(tmpdir):
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.commit()
        conn.close()
        return db_path

    def test_pool_acquire_release(self):
        """Pool reuses connections after release."""
        from api.database import _ConnectionPool

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = self._create_test_db(tmpdir)
            pool = _ConnectionPool(db_path, max_size=2)
            c1 = pool.acquire()
            assert isinstance(c1, sqlite3.Connection)
            pool.release(c1)
            c2 = pool.acquire()
            # Should get the same connection back from the pool
            assert c2 is c1
            pool.release(c2)
            pool.close_all()

    def test_pool_busy_timeout(self):
        """Connections from pool have busy_timeout set."""
        from api.database import _ConnectionPool

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = self._create_test_db(tmpdir)
            pool = _ConnectionPool(db_path, max_size=2)
            c = pool.acquire()
            timeout = c.execute("PRAGMA busy_timeout").fetchone()[0]
            assert timeout == 5000
            pool.release(c)
            pool.close_all()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
