"""
Optimization Test Suite

Tests that verify performance optimizations are working correctly:
- Pre-compiled regex patterns execute faster than runtime compilation
- Shared utilities are properly imported and functional across all modules
- Safe float conversion handles edge cases efficiently
- Connection pooling works correctly
- String operations maintain performance characteristics

Run with: pytest tests/test_optimizations.py -v --tb=short
Run with timing: pytest tests/test_optimizations.py -v -s --durations=10
"""

import re
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

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


class TestPrecompiledPatterns:
    """Verify pre-compiled regex patterns perform optimally."""

    def test_downloadable_extensions_matches_files(self):
        """Test file extension pattern matching."""
        assert DOWNLOADABLE_EXTENSIONS.search("document.pdf")
        assert DOWNLOADABLE_EXTENSIONS.search("budget.XLSX")
        assert DOWNLOADABLE_EXTENSIONS.search("data.csv")
        assert DOWNLOADABLE_EXTENSIONS.search("archive.ZIP")
        assert not DOWNLOADABLE_EXTENSIONS.search("document.txt")
        assert not DOWNLOADABLE_EXTENSIONS.search("image.png")

    def test_pe_number_extraction(self):
        """Test Program Element number pattern."""
        assert PE_NUMBER.search("0602702E")
        assert PE_NUMBER.search("0305116BB")
        assert PE_NUMBER.search("text 0602702E text")
        assert not PE_NUMBER.search("602702E")  # Only 6 digits
        assert not PE_NUMBER.search("0602702")  # Missing letter

    def test_fiscal_year_matching(self):
        """Test fiscal year pattern matching."""
        assert FISCAL_YEAR.search("FY2026")
        assert FISCAL_YEAR.search("FY 2025")
        assert FISCAL_YEAR.search("2024")
        assert FISCAL_YEAR.search("fy2023")  # Case insensitive
        assert not FISCAL_YEAR.search("FY22")  # Year too short

    def test_account_code_title_parsing(self):
        """Test account code and title splitting."""
        match = ACCOUNT_CODE_TITLE.match("2035 Aircraft Procurement, Air Force")
        assert match
        assert match.group(1) == "2035"
        assert match.group(2) == "Aircraft Procurement, Air Force"

    def test_fts5_special_chars_detection(self):
        """Test FTS5 special character detection."""
        assert FTS5_SPECIAL_CHARS.search('query"with"quotes')
        assert FTS5_SPECIAL_CHARS.search("query(with)parens")
        assert FTS5_SPECIAL_CHARS.search("query*with*wildcards")
        assert not FTS5_SPECIAL_CHARS.search("simple query words")

    def test_whitespace_normalization(self):
        """Test whitespace pattern for text cleanup."""
        text = "text   with    multiple\n\nspaces\t\ttabs"
        result = WHITESPACE.sub(" ", text).strip()
        assert result == "text with multiple spaces tabs"

    def test_currency_symbols_detection(self):
        """Test currency symbol detection."""
        assert CURRENCY_SYMBOLS.search("$1000")
        assert CURRENCY_SYMBOLS.search("€500")
        assert CURRENCY_SYMBOLS.search("£250")
        assert not CURRENCY_SYMBOLS.search("1000")

    def test_pattern_compilation_time(self):
        """Verify pre-compiled patterns avoid recompilation overhead.

        Pre-compiled patterns should be instantaneous since they're already
        compiled. If this test is slow, patterns aren't pre-compiled properly.
        """
        # Search operation should be <1ms for pre-compiled patterns
        start = time.perf_counter()
        for _ in range(10000):
            DOWNLOADABLE_EXTENSIONS.search("file.pdf")
        elapsed_time = (time.perf_counter() - start) * 1000  # Convert to ms

        # Should be very fast - ~0.5-2ms for 10k searches
        # If >10ms, patterns may not be properly pre-compiled
        assert elapsed_time < 10, f"Pattern search took {elapsed_time:.1f}ms (expected <10ms)"


class TestSafeFloatConversion:
    """Verify safe_float handles all edge cases efficiently."""

    def test_numeric_input(self):
        """Test conversion of numeric types."""
        assert safe_float(42) == 42.0
        assert safe_float(3.14) == 3.14
        assert safe_float(-100) == -100.0

    def test_string_input(self):
        """Test conversion of string numbers."""
        assert safe_float("123.45") == 123.45
        assert safe_float("-67.89") == -67.89
        assert safe_float("0") == 0.0

    def test_currency_handling(self):
        """Test stripping of currency symbols."""
        assert safe_float("$1000") == 1000.0
        assert safe_float("€500") == 500.0
        assert safe_float("£250") == 250.0
        assert safe_float("¥10000") == 10000.0

    def test_comma_separation(self):
        """Test handling of comma-separated thousands."""
        assert safe_float("1,234.56") == 1234.56
        assert safe_float("1,000,000") == 1000000.0
        assert safe_float("999,999.99") == 999999.99

    def test_whitespace_handling(self):
        """Test stripping of whitespace."""
        assert safe_float("  123.45  ") == 123.45
        assert safe_float("\t500\n") == 500.0

    def test_invalid_input(self):
        """Test fallback on invalid input."""
        assert safe_float(None) == 0.0
        assert safe_float("") == 0.0
        assert safe_float("not a number") == 0.0
        assert safe_float("abc123") == 0.0

    def test_custom_default(self):
        """Test custom default value."""
        assert safe_float(None, default=99.0) == 99.0
        assert safe_float("invalid", default=-1.0) == -1.0

    def test_conversion_performance(self):
        """Verify safe_float is optimized for thousands of calls.

        This is called thousands of times during Excel ingestion,
        so even small inefficiencies compound significantly.
        """
        test_values = [
            "123.45",
            "$1,234.56",
            None,
            "invalid",
            "€5000",
        ]

        start = time.perf_counter()
        for _ in range(10000):
            for val in test_values:
                safe_float(val)
        elapsed_time = (time.perf_counter() - start) * 1000  # Convert to ms

        # Should be fast - ~20-50ms for 50k conversions
        # If >100ms, function may have performance issues
        assert elapsed_time < 100, f"Conversions took {elapsed_time:.1f}ms (expected <100ms)"


class TestStringUtilities:
    """Verify string utility functions work correctly."""

    def test_normalize_whitespace(self):
        """Test whitespace normalization."""
        assert normalize_whitespace("  text  ") == "text"
        assert normalize_whitespace("text\n\nmore") == "text more"
        assert normalize_whitespace("text\t\ttabs") == "text tabs"
        assert normalize_whitespace("normal text") == "normal text"

    def test_sanitize_fts5_query(self):
        """Test FTS5 query sanitization."""
        # Simple terms should be quoted
        result = sanitize_fts5_query("missile defense")
        assert '"missile"' in result
        assert '"defense"' in result
        assert " OR " in result

        # FTS5 keywords (AND/OR/NOT) are removed from user input;
        # remaining terms are kept and joined with " OR " as the FTS5 separator
        result = sanitize_fts5_query("missile AND defense OR system")
        assert "AND" not in result      # user AND keyword stripped
        assert '"missile"' in result    # user terms preserved
        assert '"defense"' in result
        assert '"system"' in result

        # Special characters are stripped; terms wrapped in quotes for literal match
        result = sanitize_fts5_query('search"with(parens)')
        assert "(" not in result        # paren removed
        assert ")" not in result        # paren removed

        # Empty queries should return empty string
        assert sanitize_fts5_query("AND OR NOT") == ""

    def test_sanitize_filename(self):
        """Test filename sanitization."""
        assert sanitize_filename("normal_file.xlsx") == "normal_file.xlsx"
        assert sanitize_filename("file<>name.xlsx") == "file__name.xlsx"
        assert sanitize_filename("file|name.pdf") == "file_name.pdf"
        assert sanitize_filename("file:name.csv") == "file_name.csv"

        # Query strings should be stripped
        assert sanitize_filename("file.pdf?id=123") == "file.pdf"


class TestFormatUtilities:
    """Verify formatting utility functions."""

    def test_format_bytes_kilobytes(self):
        """Test KB formatting."""
        assert format_bytes(512 * 1024) == "512 KB"
        assert format_bytes(1024) == "1 KB"
        assert format_bytes(1024 * 1024 - 1) == "1024 KB"

    def test_format_bytes_megabytes(self):
        """Test MB formatting."""
        result = format_bytes(5 * 1024 * 1024)
        assert "MB" in result
        assert "5.0" in result

    def test_format_bytes_gigabytes(self):
        """Test GB formatting."""
        result = format_bytes(2 * 1024 * 1024 * 1024)
        assert "GB" in result
        assert "2.0" in result or "2" in result

    def test_elapsed_seconds(self):
        """Test elapsed time formatting for seconds."""
        start = time.time() - 30
        result = elapsed(start)
        assert "30" in result or "29" in result  # Allow 1 second variance
        assert "m" in result

    def test_elapsed_minutes(self):
        """Test elapsed time formatting for minutes."""
        start = time.time() - 150  # 2m 30s
        result = elapsed(start)
        assert "m" in result

    def test_elapsed_hours(self):
        """Test elapsed time formatting for hours."""
        start = time.time() - 7200  # 2 hours
        result = elapsed(start)
        assert "h" in result


class TestConnectionPooling:
    """Verify connection pooling works correctly."""

    def test_get_connection_non_cached(self):
        """Test non-cached connection creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            # Create a test database
            conn = sqlite3.connect(str(db_path))
            conn.execute("CREATE TABLE test (id INTEGER)")
            conn.commit()
            conn.close()

            # Get non-cached connection
            conn = get_connection(db_path, cached=False)
            assert isinstance(conn, sqlite3.Connection)
            assert conn.row_factory == sqlite3.Row
            conn.close()

    def test_get_connection_missing_database(self):
        """Test error handling for missing database."""
        with pytest.raises(SystemExit):
            get_connection(Path("/nonexistent/database.db"))

    def test_connection_row_factory(self):
        """Verify connections have row_factory set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            # Create a test database
            conn = sqlite3.connect(str(db_path))
            conn.execute("CREATE TABLE test (id INTEGER, name TEXT)")
            conn.execute("INSERT INTO test VALUES (1, 'test')")
            conn.commit()
            conn.close()

            # Get connection with row_factory
            conn = get_connection(db_path, cached=False)
            row = conn.execute("SELECT * FROM test").fetchone()
            # Should support dict-like access
            assert row["id"] == 1
            assert row["name"] == "test"
            conn.close()


class TestModuleImports:
    """Verify all modules import correctly and have expected exports."""

    def test_utils_module_imports(self):
        """Test that utils package imports all expected utilities."""
        import utils

        # Verify key utilities are exported
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

    def test_main_modules_use_shared_utilities(self):
        """Test that main modules properly import shared utilities."""
        # These imports should work without errors
        import dod_budget_downloader
        import search_budget
        import validate_budget_db
        import build_budget_db

        # Verify they imported the utilities
        assert hasattr(dod_budget_downloader, "format_bytes")
        assert hasattr(dod_budget_downloader, "elapsed")
        assert hasattr(dod_budget_downloader, "sanitize_filename")

        assert hasattr(search_budget, "get_connection")
        assert hasattr(search_budget, "sanitize_fts5_query")

        assert hasattr(validate_budget_db, "get_connection")

        assert hasattr(build_budget_db, "safe_float")


class TestBackwardCompatibility:
    """Ensure refactored code maintains backward compatibility."""

    def test_dod_downloader_patterns_available(self):
        """Verify dod_budget_downloader has DOWNLOADABLE_PATTERN."""
        import dod_budget_downloader

        # Should have the pattern available
        assert hasattr(dod_budget_downloader, "DOWNLOADABLE_PATTERN")
        assert dod_budget_downloader.DOWNLOADABLE_PATTERN.search("file.pdf")

    def test_build_db_pe_pattern_available(self):
        """Verify build_budget_db has _PE_PATTERN for backward compatibility."""
        import build_budget_db

        # Should have the pattern available
        assert hasattr(build_budget_db, "_PE_PATTERN")
        assert build_budget_db._PE_PATTERN.search("0602702E")

    def test_search_budget_function_behavior(self):
        """Verify search_budget functions work as before."""
        import search_budget

        # Test sanitize_fts5_query behavior
        result = search_budget.sanitize_fts5_query("test query")
        assert isinstance(result, str)
        assert "test" in result.lower() or "query" in result.lower()


# Performance benchmarks (informational, not assertions)

class TestPerformanceBenchmarks:
    """Run benchmarks to measure optimization impact.

    These tests measure actual execution time and report metrics.
    They don't fail, but provide timing data for performance regression detection.
    """

    def test_regex_pattern_search_performance(self):
        """Benchmark pre-compiled regex search performance."""
        test_string = "download_file_FY2026_budget_0602702E.pdf"

        start = time.perf_counter()
        for _ in range(100000):
            DOWNLOADABLE_EXTENSIONS.search(test_string)
        elapsed_time = (time.perf_counter() - start) * 1_000_000  # µs

        # Report metric (not an assertion)
        avg_time = elapsed_time / 100000
        print(f"\nPattern search: {avg_time:.3f} µs per operation")
        print(f"  Total: {elapsed_time:.1f} µs for 100k searches")

    def test_safe_float_performance(self):
        """Benchmark safe_float performance on typical budget values."""
        test_values = [
            "1,234,567.89",
            "$5,000,000",
            "100.50",
            None,
            "0",
        ]

        start = time.perf_counter()
        for _ in range(100000):
            for val in test_values:
                safe_float(val)
        elapsed_time = (time.perf_counter() - start) * 1_000_000  # µs

        # Report metric
        avg_time = elapsed_time / (100000 * len(test_values))
        print(f"\nSafe float: {avg_time:.3f} µs per conversion")
        print(f"  Total: {elapsed_time / 1000:.1f} ms for 500k conversions")

    def test_string_normalization_performance(self):
        """Benchmark whitespace normalization."""
        test_string = "Aircraft   Procurement\n\nAir   Force\t\tProgram"

        start = time.perf_counter()
        for _ in range(100000):
            normalize_whitespace(test_string)
        elapsed_time = (time.perf_counter() - start) * 1_000_000  # µs

        # Report metric
        avg_time = elapsed_time / 100000
        print(f"\nWhitespace normalization: {avg_time:.3f} µs per operation")
        print(f"  Total: {elapsed_time / 1000:.1f} ms for 100k operations")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
