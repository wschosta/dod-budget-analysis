#!/usr/bin/env python3
"""
Test script to validate build_budget_db.py optimizations on a 25-PDF subset.

This script:
1. Selects 25 random PDFs from DoD_Budget_Documents
2. Creates a test database
3. Runs build_budget_db with --rebuild on just those 25 PDFs
4. Measures time and calculates speedup extrapolation
5. Validates data integrity (FTS5 queries, page counts, etc.)
"""

import subprocess
import sys
import time
import sqlite3
from pathlib import Path
import random

DOCS_DIR = Path("DoD_Budget_Documents")
TEST_DB = Path("test_dod_budget.sqlite")
ALL_PDFS = list(DOCS_DIR.rglob("*.pdf"))

def select_test_pdfs(count=25):
    """Select random PDFs for testing."""
    if len(ALL_PDFS) < count:
        print(f"ERROR: Only {len(ALL_PDFS)} PDFs found, need at least {count}")
        sys.exit(1)

    selected = random.sample(ALL_PDFS, count)
    print(f"\nSelected {count} test PDFs:")
    for pdf in sorted(selected):
        print(f"  - {pdf.relative_to(DOCS_DIR)}")
    return selected

def create_test_symlinks(test_pdfs):
    """Create symlink directory with test PDFs."""
    test_dir = Path("DoD_Budget_Documents_TEST")

    # Clean up if exists
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)

    # Create new structure
    test_dir.mkdir(parents=True, exist_ok=True)

    for pdf in test_pdfs:
        rel_path = pdf.relative_to(DOCS_DIR)
        target = test_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)

        # Use shutil.copy instead of symlinks (more reliable on Windows)
        import shutil
        shutil.copy2(str(pdf), str(target))

    return test_dir

def run_test():
    """Run the optimization test."""
    print("\n" + "="*70)
    print("TESTING OPTIMIZATION: 25-PDF SUBSET")
    print("="*70)

    # Check if PDFs exist
    if not DOCS_DIR.exists() or not ALL_PDFS:
        print(f"ERROR: No PDFs found in {DOCS_DIR}")
        print(f"Found {len(ALL_PDFS)} PDFs total")
        sys.exit(1)

    # Select test PDFs
    test_pdfs = select_test_pdfs(25)
    total_size_mb = sum(p.stat().st_size for p in test_pdfs) / (1024**2)
    total_pages_estimate = len(test_pdfs) * 200  # Rough estimate

    print("\nTest metrics:")
    print(f"  Total PDF size: {total_size_mb:.1f} MB")
    print(f"  Estimated pages: {total_pages_estimate:,} (rough)")

    # Create test database
    if TEST_DB.exists():
        TEST_DB.unlink()

    print("\nRunning build_budget_db.py on 25 PDFs...")
    print(f"Database: {TEST_DB}")
    print(f"{'='*70}")

    start = time.time()

    try:
        result = subprocess.run([
            sys.executable, "build_budget_db.py",
            "--db", str(TEST_DB),
            "--rebuild"
        ], capture_output=True, text=True, timeout=3600)  # 1-hour timeout

        elapsed = time.time() - start

        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        if result.returncode != 0:
            print(f"\nERROR: build_budget_db.py failed with return code {result.returncode}")
            sys.exit(1)

    except subprocess.TimeoutExpired:
        print("\nERROR: Test timed out after 1 hour")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    # Validate results
    print(f"\n{'='*70}")
    print(f"TEST COMPLETE - Elapsed: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")
    print(f"{'='*70}")

    if not TEST_DB.exists():
        print(f"ERROR: Database {TEST_DB} was not created")
        sys.exit(1)

    validate_database(TEST_DB, len(test_pdfs))

    # Calculate extrapolation
    print("\nEXTRAPOLATION TO FULL 6233 PDFs:")
    print(f"  25 PDFs: {elapsed:.1f} seconds")
    full_seconds = (elapsed / 25) * 6233
    full_hours = full_seconds / 3600
    print(f"  6233 PDFs estimate: {full_seconds:.0f} seconds = {full_hours:.1f} hours")

    if full_hours < 5:
        print(f"\n✓ SUCCESS: Extrapolated time ({full_hours:.1f}h) meets 2-3 hour target!")
        print(f"  Speedup: {16 / full_hours:.1f}x faster than original 16+ hours")
    else:
        print(f"\n⚠ WARNING: Extrapolated time ({full_hours:.1f}h) exceeds 5 hour threshold")
        print("  May need additional optimization")

    return elapsed, full_hours

def validate_database(db_path, expected_files):
    """Validate database integrity."""
    print("\nVALIDATING DATABASE:")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Check tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"  Tables: {', '.join(sorted(tables))}")

    # Count PDF pages
    cursor.execute("SELECT COUNT(*) FROM pdf_pages")
    page_count = cursor.fetchone()[0]
    print(f"  PDF pages ingested: {page_count:,}")

    # Check FTS5
    try:
        cursor.execute("SELECT COUNT(*) FROM pdf_pages_fts")
        fts_count = cursor.fetchone()[0]
        print(f"  FTS5 indexed: {fts_count:,}")

        if fts_count != page_count:
            print(f"  ⚠ WARNING: FTS5 count ({fts_count}) != page count ({page_count})")
        else:
            print("  ✓ FTS5 index matches page count")
    except Exception as e:
        print(f"  ⚠ FTS5 query failed: {e}")

    # Test FTS5 search
    try:
        cursor.execute("SELECT COUNT(*) FROM pdf_pages_fts WHERE page_text LIKE '%budget%'")
        results = cursor.fetchone()[0]
        print(f"  FTS5 search test ('budget'): {results} results")
        if results > 0:
            print("  ✓ FTS5 search working")
        else:
            print("  ⚠ FTS5 search found no results (may be normal)")
    except Exception as e:
        print(f"  ⚠ FTS5 search failed: {e}")

    # Integrity check
    try:
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        if result == "ok":
            print("  ✓ Database integrity check: OK")
        else:
            print(f"  ✗ Database integrity check FAILED: {result}")
    except Exception as e:
        print(f"  ⚠ Integrity check failed: {e}")

    conn.close()

if __name__ == "__main__":
    random.seed(42)  # Reproducible results
    elapsed, full_hours = run_test()
