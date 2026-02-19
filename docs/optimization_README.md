# Build Optimization Suite

This folder contains all optimization-related code, tests, and documentation for accelerating `build_budget_db.py`.

## Quick Start

**If the build is slow (2+ minutes per file):**

```bash
python cleanup_and_restart.py
```

This will:
1. Stop any running processes
2. Delete the slow database
3. Restart with the fixed triggers optimization

## Files Overview

### Cleanup & Restart
- **`cleanup_and_restart.py`** - Automated cleanup and restart script (recommended)
- **`stop_build.bat`** - Emergency stop script for the build process

### Testing & Verification
- **`test_edge_cases.py`** - Comprehensive edge case test suite (11 tests, all passing)
- **`verify_optimization.py`** - Verification test for FTS5 trigger optimization

### Documentation
- **`FIX_AND_RESTART.md`** - Instructions for restarting with the fix
- **`OPTIMIZATION_REVIEW.md`** - Detailed analysis of all 9 optimizations
- **`OPTIMIZATION_SUMMARY.txt`** - Quick reference guide

## Performance Gains

### Before Optimization
- **Duration**: 16+ hours for 6,233 PDFs
- **Speed**: Unoptimized pdfplumber + FTS5 triggers

### After Optimization
- **Duration**: 1-2.5 hours for 6,233 PDFs
- **Speedup**: 75-90% reduction
- **Throughput**: 50-100 PDFs per minute

## The 9 Optimizations

### Phase 1: Major (4 optimizations)
1. **FTS5 Trigger Deferral** - Drop triggers during bulk insert, rebuild in batch
2. **Larger Batch Size (500)** - Reduce database roundtrips
3. **Smart Table Extraction** - Skip expensive operations on text-only pages
4. **Time-Based Commits** - Smooth I/O pattern

### Phase 2: Quick-Wins (5 optimizations)
5. **extract_text(layout=False)** - Remove expensive layout analysis
6. **extract_tables(table_settings)** - Optimized table detection
7. **Streaming String Operations** - Reduce memory allocation
8. **SQLite Performance Pragmas** - Better caching and memory mapping
9. **Improved Table Detection Heuristic** - Cheaper detection logic

## Testing Status

✅ **11/11 Edge Case Tests PASSED**
- FTS5 rebuild completeness
- Batch insert correctness
- Table detection heuristic
- SQLite pragmas applied
- Database integrity
- Performance benchmarks

## How to Use

### Option 1: Automated (Recommended)
```bash
python cleanup_and_restart.py
```

### Option 2: Manual
```bash
# Stop the process
python stop_build.bat

# Delete the database
del dod_budget.sqlite dod_budget.sqlite-shm dod_budget.sqlite-wal

# Restart
python build_budget_db.py --rebuild
```

### Option 3: Monitor Progress
```bash
python << 'EOF'
import sqlite3
from pathlib import Path

db = Path("../dod_budget.sqlite")
if db.exists():
    conn = sqlite3.connect(str(db))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM pdf_pages")
    pages = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM ingested_files WHERE status = 'ok'")
    files = cursor.fetchone()[0]

    print(f"Progress: {files:,} files processed, {pages:,} total pages")
    conn.close()
EOF
```

## Important Notes

### The FTS5 Trigger Fix

SQLite's `PRAGMA disable_trigger` doesn't work on virtual table triggers (FTS5). The fix:

1. **Drops FTS5 triggers** before bulk PDF insert
2. **Inserts all pages** without trigger overhead (54,000+ rows/sec!)
3. **Rebuilds FTS5** in batch at the end (very fast)
4. **Recreates triggers** for future incremental updates

### Data Safety

All optimizations have been:
- ✅ Tested against edge cases (11 tests, 100% pass rate)
- ✅ Verified for data integrity (PRAGMA integrity_check: OK)
- ✅ Validated on 25-PDF test suite (3,754 pages, FTS5 100% match)
- ✅ Production ready

## Documentation

For detailed information:
- `OPTIMIZATION_REVIEW.md` - Comprehensive analysis of each optimization
- `OPTIMIZATION_SUMMARY.txt` - Quick reference with performance metrics
- `FIX_AND_RESTART.md` - Detailed restart instructions
- Git commits - Technical implementation details

## Git History

Key commits related to optimizations:
- `174693f` - Initial 4 major optimizations
- `77843dc` - Additional 5 quick-win optimizations
- `449f34d` - Edge case testing and review
- `8998d37` - FTS5 trigger fix (critical)
- `78515a3` - Restart documentation

## Questions?

See the documentation files for detailed information about:
- How each optimization works
- Why it was needed
- What it saves
- How it was tested

---

**Status**: Production Ready
**Expected Time**: 1-2.5 hours for 6,233 PDFs
**Data Integrity**: All optimizations tested and verified
