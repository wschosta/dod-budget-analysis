#!/usr/bin/env python3
"""
BEAR-011: Performance profiling for CI.

Creates a test database with 10,000 rows and runs benchmark queries.
Reports timing in JSON format and fails if any query exceeds its threshold.

Usage:
    python scripts/profile_queries.py           # Human-readable output
    python scripts/profile_queries.py --json    # JSON output + write profile_report.json
    python scripts/profile_queries.py --rows 50000  # Custom row count
"""
# DONE [Group: BEAR] BEAR-011: Add performance profiling to CI (~2,500 tokens)

import argparse
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

def create_database(db_path: Path) -> sqlite3.Connection:
    """Create a minimal SQLite database with budget_lines schema for profiling.

    This avoids importing build_budget_db.py (which pulls in pdfplumber and
    other heavy dependencies) when we only need the schema for benchmarking.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-262144")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            exhibit_type TEXT,
            sheet_name TEXT,
            fiscal_year TEXT,
            account TEXT,
            account_title TEXT,
            organization TEXT,
            organization_name TEXT,
            budget_activity TEXT,
            budget_activity_title TEXT,
            sub_activity TEXT,
            sub_activity_title TEXT,
            line_item TEXT,
            line_item_title TEXT,
            classification TEXT,
            amount_fy2024_actual REAL,
            amount_fy2025_enacted REAL,
            amount_fy2025_supplemental REAL,
            amount_fy2025_total REAL,
            amount_fy2026_request REAL,
            amount_fy2026_reconciliation REAL,
            amount_fy2026_total REAL,
            quantity_fy2024 REAL,
            quantity_fy2025 REAL,
            quantity_fy2026_request REAL,
            quantity_fy2026_total REAL,
            extra_fields TEXT,
            pe_number TEXT,
            currency_year TEXT,
            appropriation_code TEXT,
            appropriation_title TEXT,
            amount_unit TEXT DEFAULT 'thousands',
            budget_type TEXT,
            amount_type TEXT DEFAULT 'budget_authority'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS budget_lines_fts USING fts5(
            account_title,
            budget_activity_title,
            sub_activity_title,
            line_item_title,
            organization_name,
            pe_number,
            content='budget_lines',
            content_rowid='id'
        );

        CREATE TRIGGER IF NOT EXISTS budget_lines_ai AFTER INSERT ON budget_lines BEGIN
            INSERT INTO budget_lines_fts(rowid, account_title, budget_activity_title,
                sub_activity_title, line_item_title, organization_name, pe_number)
            VALUES (new.id, new.account_title, new.budget_activity_title,
                new.sub_activity_title, new.line_item_title, new.organization_name,
                new.pe_number);
        END;
    """)
    conn.commit()
    return conn

# Performance thresholds (milliseconds)
THRESHOLDS = {
    "search": 500,
    "aggregate": 500,
    "paginate": 200,
    "download": 500,
    "fts5_search": 200,
}

_ORGS = ["Army", "Navy", "Air Force", "Space Force", "Marine Corps", "Defense-Wide"]
_EXHIBITS = ["p1", "r1", "o1", "m1"]
_ACCOUNTS = ["2035", "1300", "2040", "1506", "3010"]
_PE_NUMBERS = ["0205231A", "0602702E", "0305116BB", "0601102D"]


def create_test_db(row_count: int = 10_000) -> tuple[sqlite3.Connection, Path]:
    """Create a temporary test database with synthetic data.

    Args:
        row_count: Number of rows to insert.

    Returns:
        (connection, db_path) tuple.
    """
    tmp_dir = tempfile.mkdtemp(prefix="profile_")
    db_path = Path(tmp_dir) / "profile.sqlite"
    conn = create_database(db_path)
    conn.row_factory = sqlite3.Row

    rows = []
    for i in range(row_count):
        rows.append((
            f"file_{i % 100}.xlsx",
            _EXHIBITS[i % len(_EXHIBITS)],
            "2026" if i % 3 != 0 else "2025",
            _ACCOUNTS[i % len(_ACCOUNTS)],
            f"Account Title {_ACCOUNTS[i % len(_ACCOUNTS)]}",
            _ORGS[i % len(_ORGS)],
            _PE_NUMBERS[i % len(_PE_NUMBERS)],
            f"Budget Activity {i % 10}",
            f"Line Item {i}",
            f"Description for line item {i} in {_ORGS[i % len(_ORGS)]}",
            float(1000 + (i % 50000)),
            float(1100 + (i % 50000)),
            float(1200 + (i % 50000)),
        ))

    conn.executemany(
        """INSERT INTO budget_lines
           (source_file, exhibit_type, fiscal_year, account, account_title,
            organization_name, pe_number, budget_activity_title,
            line_item, line_item_title,
            amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    return conn, db_path


def benchmark(conn: sqlite3.Connection) -> dict[str, float]:
    """Run benchmark queries and return timing in milliseconds.

    Args:
        conn: Open SQLite connection with test data.

    Returns:
        Dict mapping query name to elapsed time in milliseconds.
    """
    timings = {}

    # 1. Search query (filtered WHERE)
    start = time.monotonic()
    conn.execute(
        "SELECT * FROM budget_lines "
        "WHERE organization_name = 'Army' AND exhibit_type = 'p1' "
        "LIMIT 20"
    ).fetchall()
    timings["search"] = (time.monotonic() - start) * 1000

    # 2. Aggregation query (GROUP BY)
    start = time.monotonic()
    conn.execute(
        "SELECT organization_name, "
        "SUM(amount_fy2026_request) AS total "
        "FROM budget_lines "
        "GROUP BY organization_name "
        "ORDER BY total DESC"
    ).fetchall()
    timings["aggregate"] = (time.monotonic() - start) * 1000

    # 3. Pagination (deep page)
    start = time.monotonic()
    conn.execute(
        "SELECT * FROM budget_lines ORDER BY id LIMIT 100 OFFSET 5000"
    ).fetchall()
    timings["paginate"] = (time.monotonic() - start) * 1000

    # 4. Download simulation (fetch 5000 rows)
    start = time.monotonic()
    conn.execute(
        "SELECT source_file, exhibit_type, fiscal_year, account, "
        "account_title, organization_name, pe_number, "
        "amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request "
        "FROM budget_lines LIMIT 5000"
    ).fetchall()
    timings["download"] = (time.monotonic() - start) * 1000

    # 5. FTS5 search
    start = time.monotonic()
    conn.execute(
        "SELECT rowid, bm25(budget_lines_fts) AS score "
        "FROM budget_lines_fts "
        "WHERE budget_lines_fts MATCH 'Army' "
        "ORDER BY score LIMIT 20"
    ).fetchall()
    timings["fts5_search"] = (time.monotonic() - start) * 1000

    return timings


def main():
    parser = argparse.ArgumentParser(description="Profile DoD Budget DB query performance")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--rows", type=int, default=10_000, help="Number of test rows (default: 10000)")
    parser.add_argument("--output", type=Path, default=Path("profile_report.json"),
                        help="Output file for JSON report (default: profile_report.json)")
    args = parser.parse_args()

    # Create test DB
    if not args.json:
        print(f"Creating test database with {args.rows:,} rows...")
    conn, db_path = create_test_db(args.rows)

    # Run benchmarks
    if not args.json:
        print("Running benchmarks...")
    timings = benchmark(conn)
    conn.close()

    # Clean up
    try:
        db_path.unlink()
        db_path.parent.rmdir()
    except OSError:
        pass

    # Check thresholds
    all_passed = True
    failures = []
    for name, ms in timings.items():
        threshold = THRESHOLDS.get(name, 500)
        if ms > threshold:
            all_passed = False
            failures.append(name)

    # Output results
    report = {
        "rows": args.rows,
        "timings": {k: round(v, 1) for k, v in timings.items()},
        "thresholds": THRESHOLDS,
        "all_passed": all_passed,
        "failures": failures,
    }

    if args.json:
        print(json.dumps(report, indent=2))
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)
    else:
        print("\n" + "=" * 60)
        print("  PERFORMANCE PROFILING RESULTS")
        print("=" * 60)
        print(f"  Test rows: {args.rows:,}")
        print()
        print(f"  {'Query':<20} {'Time (ms)':>10} {'Threshold':>10} {'Status':>8}")
        print(f"  {'-'*20} {'-'*10} {'-'*10} {'-'*8}")
        for name, ms in timings.items():
            threshold = THRESHOLDS.get(name, 500)
            status = "PASS" if ms <= threshold else "FAIL"
            print(f"  {name:<20} {ms:>10.1f} {threshold:>10} {status:>8}")
        print()
        if all_passed:
            print("  Result: ALL PASSED")
        else:
            print(f"  Result: {len(failures)} FAILED ({', '.join(failures)})")
        print("=" * 60)

        # Write JSON report regardless
        with open(args.output, "w") as f:
            json.dump(report, f, indent=2)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
