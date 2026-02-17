#!/usr/bin/env python3
"""
Cleanup script: Delete slow database and restart with optimizations.

The issue: The existing database was created with FTS5 triggers ENABLED.
PRAGMA disable_trigger only works on triggers created AFTER it's set.

Solution: Delete the database and start fresh so PRAGMA disable_trigger
works properly on a newly created database.
"""

import subprocess
import sys
import time
from pathlib import Path

def main():
    db_files = [
        "dod_budget.sqlite",
        "dod_budget.sqlite-shm",
        "dod_budget.sqlite-wal",
    ]

    print("="*70)
    print("CLEANUP AND RESTART")
    print("="*70)

    print("\nRemoving old database files...")
    for db_file in db_files:
        path = Path(db_file)
        if path.exists():
            try:
                path.unlink()
                print(f"  [OK] Deleted: {db_file}")
            except Exception as e:
                print(f"  [ERROR] Failed to delete {db_file}: {e}")
                return 1
        else:
            print(f"  [SKIP] Not found: {db_file}")

    print("\n" + "="*70)
    print("STARTING FRESH BUILD WITH OPTIMIZATIONS")
    print("="*70)
    print("""
The script will now:
  1. Create a fresh database
  2. Disable FTS5 triggers BEFORE any inserts (via PRAGMA)
  3. Process all 6,233 PDFs WITHOUT trigger overhead
  4. Rebuild FTS5 indexes ONCE in batch at the end
  5. Expected duration: 1-2.5 hours (not 16+!)

Starting in 3 seconds...
""")

    time.sleep(3)

    print("\n" + "="*70)
    print("Running: python build_budget_db.py --rebuild")
    print("="*70 + "\n")

    result = subprocess.run([sys.executable, "build_budget_db.py", "--rebuild"])

    return result.returncode

if __name__ == "__main__":
    sys.exit(main())
