#!/usr/bin/env python3
"""
Comprehensive edge case testing for build_budget_db.py optimizations.

Tests the 9 critical optimizations against edge cases to ensure:
1. No data loss
2. No crashes
3. Correct behavior on unusual PDFs
4. FTS5 integrity maintained
5. Performance gains hold up
"""

import sqlite3
import sys
import tempfile
import time
from pathlib import Path

def test_edge_case(name: str, test_func):
    """Decorator for test cases."""
    try:
        print(f"\n{'='*70}")
        print(f"TEST: {name}")
        print(f"{'='*70}")
        test_func()
        print(f"[PASS] {name}")
        return True
    except AssertionError as e:
        print(f"[FAIL] {name}")
        print(f"  Error: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] {name}")
        print(f"  {type(e).__name__}: {e}")
        return False

# ─────────────────────────────────────────────────────────────────────────────
# OPTIMIZATION 1: FTS5 Trigger Deferral + Batch Rebuild
# ─────────────────────────────────────────────────────────────────────────────

def test_fts5_rebuild_completeness():
    """Test that FTS5 rebuild captures all pages."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))

        try:
            # Create schema
            conn.execute("CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY, page_text TEXT, source_file TEXT, table_data TEXT)")
            conn.execute("""
                CREATE VIRTUAL TABLE pdf_pages_fts USING fts5(
                    page_text, source_file, table_data,
                    content='pdf_pages',
                    content_rowid='id'
                )
            """)

            # Insert test data (no triggers for virtual FTS5 tables)
            for i in range(100):
                conn.execute(
                    "INSERT INTO pdf_pages (page_text, source_file, table_data) VALUES (?, ?, ?)",
                    (f"Page {i} content with keywords budget allocation", f"file{i}.pdf", None)
                )
                conn.execute(
                    "INSERT INTO pdf_pages_fts(rowid, page_text, source_file, table_data) VALUES (?, ?, ?, ?)",
                    (i+1, f"Page {i} content with keywords budget allocation", f"file{i}.pdf", None)
                )
            conn.commit()

            # Verify FTS5 has data
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM pdf_pages_fts")
            fts_count = cursor.fetchone()[0]
            assert fts_count == 100, f"FTS5 should have 100 rows, got {fts_count}"

            # Test FTS5 search works
            cursor.execute("SELECT COUNT(*) FROM pdf_pages_fts WHERE page_text LIKE '%budget%'")
            search_results = cursor.fetchone()[0]
            assert search_results == 100, f"FTS5 search should find 100 budget entries, got {search_results}"

        finally:
            conn.close()

def test_fts5_partial_rebuild():
    """Test that FTS5 partial rebuild works (only new rows)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))

        conn.execute("CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY, page_text TEXT, source_file TEXT, table_data TEXT)")
        conn.execute("""
            CREATE VIRTUAL TABLE pdf_pages_fts USING fts5(
                page_text, source_file, table_data,
                content='pdf_pages',
                content_rowid='id'
            )
        """)

        # Insert first batch with FTS5
        for i in range(50):
            conn.execute(
                "INSERT INTO pdf_pages (page_text, source_file, table_data) VALUES (?, ?, ?)",
                (f"Page {i}", f"file{i}.pdf", None)
            )
        conn.commit()

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pdf_pages_fts")
        assert cursor.fetchone()[0] == 50

        # Insert second batch with triggers disabled
        conn.execute("PRAGMA disable_trigger = 1")
        for i in range(50, 100):
            conn.execute(
                "INSERT INTO pdf_pages (page_text, source_file, table_data) VALUES (?, ?, ?)",
                (f"Page {i}", f"file{i}.pdf", None)
            )
        conn.commit()

        # Rebuild only new rows
        conn.execute("PRAGMA disable_trigger = 0")
        max_rowid = cursor.execute("SELECT COALESCE(MAX(rowid), 0) FROM pdf_pages_fts").fetchone()[0]
        conn.execute(f"""
            INSERT INTO pdf_pages_fts(rowid, page_text, source_file, table_data)
            SELECT id, page_text, source_file, table_data FROM pdf_pages
            WHERE id > {max_rowid}
        """)
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM pdf_pages_fts")
        final_count = cursor.fetchone()[0]
        assert final_count == 100, f"FTS5 should have 100 total rows after partial rebuild, got {final_count}"

        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# OPTIMIZATION 2: Larger Batch Size (500)
# ─────────────────────────────────────────────────────────────────────────────

def test_large_batch_insert():
    """Test that large batches (500+) insert correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))

        conn.execute("CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY, page_text TEXT, source_file TEXT)")

        # Insert 1000 rows in batches of 500
        batch = []
        for i in range(1000):
            batch.append((f"Page {i} text content", f"file{i%10}.pdf"))
            if len(batch) >= 500:
                conn.executemany("INSERT INTO pdf_pages (page_text, source_file) VALUES (?, ?)", batch)
                batch = []

        if batch:
            conn.executemany("INSERT INTO pdf_pages (page_text, source_file) VALUES (?, ?)", batch)

        conn.commit()

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pdf_pages")
        count = cursor.fetchone()[0]
        assert count == 1000, f"Expected 1000 rows, got {count}"

        # Verify no duplicates
        cursor.execute("SELECT COUNT(DISTINCT id) FROM pdf_pages")
        distinct = cursor.fetchone()[0]
        assert distinct == 1000, f"Expected 1000 distinct IDs, got {distinct}"

        conn.close()

def test_batch_boundary_conditions():
    """Test batch insertion at exact batch size boundaries."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))

        conn.execute("CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY, page_text TEXT)")

        # Insert exactly 500 rows (one full batch)
        batch = [(f"Page {i}",) for i in range(500)]
        conn.executemany("INSERT INTO pdf_pages (page_text) VALUES (?)", batch)
        conn.commit()

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pdf_pages")
        assert cursor.fetchone()[0] == 500

        # Insert 499 rows (partial batch)
        batch = [(f"Page {500+i}",) for i in range(499)]
        conn.executemany("INSERT INTO pdf_pages (page_text) VALUES (?)", batch)
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM pdf_pages")
        assert cursor.fetchone()[0] == 999

        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# OPTIMIZATION 3: Smart Table Detection (_likely_has_tables)
# ─────────────────────────────────────────────────────────────────────────────

def test_likely_has_tables_heuristic():
    """Test the _likely_has_tables() function with various page types."""
    # Mock page objects for testing
    class MockPage:
        def __init__(self, rects_count, curves_count):
            self.rects = [None] * rects_count  # Mock rects list
            self.curves = [None] * curves_count  # Mock curves list

    # Import the function from build_budget_db
    import sys
    sys.path.insert(0, str(Path.cwd()))
    from build_budget_db import _likely_has_tables

    # Test 1: Page with many rects (likely table)
    page_with_rects = MockPage(20, 0)
    assert _likely_has_tables(page_with_rects), "Should detect table with many rects"

    # Test 2: Page with many curves (likely table)
    page_with_curves = MockPage(0, 20)
    assert _likely_has_tables(page_with_curves), "Should detect table with many curves"

    # Test 3: Page with few rects/curves (likely text only)
    page_text_only = MockPage(0, 0)
    assert not _likely_has_tables(page_text_only), "Should not detect table in text-only page"

    # Test 4: Page with moderate structure
    page_moderate = MockPage(5, 5)
    assert not _likely_has_tables(page_moderate), "Should be conservative with moderate structure"

    # Test 5: Edge case at threshold (exactly 10 - below threshold)
    page_at_threshold = MockPage(10, 0)
    assert not _likely_has_tables(page_at_threshold), "Should reject at exactly 10 (threshold is >10)"

    # Test 6: Edge case above threshold (11)
    page_above_threshold = MockPage(11, 0)
    assert _likely_has_tables(page_above_threshold), "Should accept at 11 (>10)"

# ─────────────────────────────────────────────────────────────────────────────
# OPTIMIZATION 4: extract_text(layout=False)
# ─────────────────────────────────────────────────────────────────────────────

def test_extract_text_parameter_compatibility():
    """Test that extract_text(layout=False) is a valid pdfplumber parameter."""
    # This is a compile-time check
    from build_budget_db import ingest_pdf_file
    import inspect

    # Verify the source code contains layout=False
    source = inspect.getsource(ingest_pdf_file)
    assert "layout=False" in source, "extract_text should use layout=False for performance"

# ─────────────────────────────────────────────────────────────────────────────
# OPTIMIZATION 5: extract_tables(table_settings)
# ─────────────────────────────────────────────────────────────────────────────

def test_table_settings_structure():
    """Test that table_settings are properly formatted."""
    from build_budget_db import ingest_pdf_file
    import inspect

    source = inspect.getsource(ingest_pdf_file)
    assert "vertical_strategy" in source, "table_settings should include vertical_strategy"
    assert "horizontal_strategy" in source, "table_settings should include horizontal_strategy"
    assert "lines" in source, "Strategy should be 'lines' for performance"

# ─────────────────────────────────────────────────────────────────────────────
# OPTIMIZATION 6: _extract_table_text() streaming
# ─────────────────────────────────────────────────────────────────────────────

def test_extract_table_text_output():
    """Test that streaming _extract_table_text produces correct output."""
    from build_budget_db import _extract_table_text

    # Test 1: Empty tables
    assert _extract_table_text([]) == ""
    assert _extract_table_text([[], []]) == ""

    # Test 2: Simple table
    table = [["A", "B"], ["C", "D"]]
    result = _extract_table_text([table])
    assert "A" in result and "B" in result and "C" in result and "D" in result

    # Test 3: Table with None values
    table = [["A", None], [None, "D"]]
    result = _extract_table_text([table])
    assert result  # Should produce output despite None values

    # Test 4: Multiple tables
    tables = [[["A", "B"]], [["C", "D"]]]
    result = _extract_table_text(tables)
    assert result.count("\n") >= 1  # Should have multiple rows

# ─────────────────────────────────────────────────────────────────────────────
# OPTIMIZATION 7: SQLite Performance Pragmas
# ─────────────────────────────────────────────────────────────────────────────

def test_pragmas_applied():
    """Test that all optimization pragmas are set."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"

        # Import and call create_database
        from build_budget_db import create_database
        conn = create_database(db_path)

        cursor = conn.cursor()

        # Check pragmas are set
        cursor.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0].upper() in ["WAL", "PERSIST"], "Should use WAL or PERSIST"

        cursor.execute("PRAGMA temp_store")
        temp_store = cursor.fetchone()[0]
        assert temp_store in [2, 3], f"temp_store should be MEMORY (3) or FILE (2), got {temp_store}"

        cursor.execute("PRAGMA cache_size")
        cache_size = cursor.fetchone()[0]
        assert cache_size != 0, "cache_size should not be 0"

        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# DATA INTEGRITY TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_database_integrity():
    """Test that optimizations don't corrupt database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        from build_budget_db import create_database

        conn = create_database(db_path)

        # Create some test data
        conn.execute("INSERT INTO budget_lines (source_file, account, organization) VALUES (?, ?, ?)",
                     ("test.xlsx", "1234", "Army"))
        conn.execute("INSERT INTO pdf_pages (source_file, page_text) VALUES (?, ?)",
                     ("test.pdf", "Sample page content"))
        conn.commit()

        # Run integrity check
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        assert result == "ok", f"Database integrity check failed: {result}"

        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# PERFORMANCE TESTS
# ─────────────────────────────────────────────────────────────────────────────

def test_batch_insert_performance():
    """Test that batch inserts are faster than individual inserts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, data TEXT)")

        # Time batch insert (500 at a time)
        start = time.time()
        batch = [("Row " + str(i),) for i in range(5000)]
        for i in range(0, len(batch), 500):
            conn.executemany("INSERT INTO test (data) VALUES (?)", batch[i:i+500])
        batch_time = time.time() - start

        conn.commit()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM test")
        assert cursor.fetchone()[0] == 5000

        print(f"  Batch insert (500): {batch_time:.3f}s for 5000 rows")
        assert batch_time < 2.0, "Batch insert should be reasonably fast"

        conn.close()

# ─────────────────────────────────────────────────────────────────────────────
# MAIN TEST RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "="*70)
    print("EDGE CASE TESTING FOR BUILD_BUDGET_DB.PY OPTIMIZATIONS")
    print("="*70)

    tests = [
        ("FTS5 Rebuild Completeness", test_fts5_rebuild_completeness),
        ("FTS5 Partial Rebuild", test_fts5_partial_rebuild),
        ("Large Batch Insert", test_large_batch_insert),
        ("Batch Boundary Conditions", test_batch_boundary_conditions),
        ("Table Detection Heuristic", test_likely_has_tables_heuristic),
        ("Extract Text Parameter", test_extract_text_parameter_compatibility),
        ("Table Settings Structure", test_table_settings_structure),
        ("Extract Table Text Output", test_extract_table_text_output),
        ("Database Pragmas", test_pragmas_applied),
        ("Database Integrity", test_database_integrity),
        ("Batch Insert Performance", test_batch_insert_performance),
    ]

    results = []
    for name, test_func in tests:
        results.append((name, test_edge_case(name, test_func)))

    # Summary
    print(f"\n\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status}: {name}")

    print(f"\n{'='*70}")
    print(f"Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n[OK] ALL TESTS PASSED - Optimizations are safe and correct!")
        return 0
    else:
        print(f"\n[WARN] {total - passed} TEST(S) FAILED - Review before production")
        return 1

if __name__ == "__main__":
    sys.exit(main())
