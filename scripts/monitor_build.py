#!/usr/bin/env python3
"""Monitor build_budget_db.py progress in real-time."""

import sqlite3
import sys
import time
from pathlib import Path
from datetime import datetime

def monitor_progress():
    """Display current build progress."""
    db = Path("../dod_budget.sqlite")
    if not db.exists():
        print("Database not found - build hasn't started yet")
        return

    try:
        conn = sqlite3.connect(str(db))
        cursor = conn.cursor()

        # Get PDF stats
        cursor.execute("SELECT COUNT(*) FROM ingested_files WHERE file_type='pdf' AND status='ok'")
        pdf_ok = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM ingested_files WHERE file_type='pdf' AND status='ok_with_issues'")
        pdf_issues = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM pdf_pages")
        pages = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM extraction_issues")
        total_issues = cursor.fetchone()[0]

        # Get extraction issue breakdown
        cursor.execute("SELECT issue_type, COUNT(*) FROM extraction_issues GROUP BY issue_type")
        issue_types = dict(cursor.fetchall())

        # Get timing info
        stat = db.stat()
        mod_time = datetime.fromtimestamp(stat.st_mtime)
        now = datetime.now()
        elapsed = (now - mod_time).total_seconds()

        # Get last file
        cursor.execute("SELECT file_path, ingested_at FROM ingested_files WHERE file_type='pdf' ORDER BY ingested_at DESC LIMIT 1")
        last_file_row = cursor.fetchone()

        conn.close()

        # Display results
        print("\n" + "="*70)
        print(f"  BUILD PROGRESS - {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70)

        pdf_total = pdf_ok + pdf_issues
        print("\n  PDF Files:")
        print(f"    Processed: {pdf_total:,} / 6,233 ({100*pdf_total/6233:.1f}%)")
        print(f"    - Successfully: {pdf_ok:,}")
        print(f"    - With timeout/issues: {pdf_issues:,}")

        print(f"\n  PDF Pages: {pages:,}")

        print(f"\n  Extraction Issues: {total_issues:,}")
        for issue_type, count in sorted(issue_types.items()):
            print(f"    - {issue_type}: {count:,}")

        print("\n  Timing:")
        print(f"    Elapsed: {elapsed/60:.1f} minutes")

        if pdf_total > 0:
            rate_files = pdf_total / (elapsed/60)
            rate_pages = pages / elapsed
            est_total_time = 6233 / rate_files

            print(f"    Rate: {rate_files:.1f} files/min, {rate_pages:.1f} pages/sec")
            print(f"    Est. completion: {est_total_time:.1f} minutes ({est_total_time/60:.2f} hours)")
            print(f"    Est. finish time: {(now.timestamp() + (est_total_time * 60)).__int__() and datetime.fromtimestamp(now.timestamp() + (est_total_time * 60)).strftime('%H:%M:%S')}")

        if last_file_row:
            print(f"\n  Last file: {last_file_row[0]}")
            print(f"  Timestamp: {last_file_row[1]}")

        print("\n" + "="*70 + "\n")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    try:
        while True:
            monitor_progress()
            if len(sys.argv) > 1 and sys.argv[1] == "--once":
                break
            time.sleep(30)  # Update every 30 seconds
    except KeyboardInterrupt:
        print("\nMonitoring stopped")
