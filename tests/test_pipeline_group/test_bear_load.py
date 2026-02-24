"""
BEAR-004: Load testing for large datasets.

Verify the system handles large datasets without degradation:
1. Search query completes in < 500ms
2. Aggregation query completes in < 500ms
3. Pagination (page 100 of 1000) completes in < 200ms
4. CSV download of 10,000 rows starts streaming within < 1s
5. FTS5 search returns results in < 200ms

Uses time.monotonic() for timing assertions.
"""
# DONE [Group: BEAR] BEAR-004: Add load testing for 100K-row datasets (~2,500 tokens)

import sqlite3
import time
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from build_budget_db import create_database

# Organizations and exhibit types for realistic data distribution
_ORGS = ["Army", "Navy", "Air Force", "Space Force", "Marine Corps", "Defense-Wide"]
_EXHIBITS = ["p1", "r1", "o1", "m1"]
_ACCOUNTS = ["2035", "1300", "2040", "1506", "3010", "3600"]
_PE_NUMBERS = [
    "0205231A", "0602702E", "0305116BB", "0601102D",
    "0603000A", "0604000F", "0101122N", "0205219A",
]


@pytest.fixture(scope="module")
def large_db(tmp_path_factory):
    """Create a test database with 100,000 synthetic budget line items."""
    db_dir = tmp_path_factory.mktemp("load_test")
    db_path = db_dir / "load.sqlite"
    conn = create_database(db_path)
    conn.row_factory = sqlite3.Row

    # Batch-insert 100K rows using executemany for speed
    rows = []
    for i in range(100_000):
        org = _ORGS[i % len(_ORGS)]
        exhibit = _EXHIBITS[i % len(_EXHIBITS)]
        account = _ACCOUNTS[i % len(_ACCOUNTS)]
        pe = _PE_NUMBERS[i % len(_PE_NUMBERS)]
        fy = "2026" if i % 3 != 0 else "2025"
        rows.append((
            f"file_{i % 200}.xlsx",
            exhibit,
            fy,
            account,
            f"Account Title {account}",
            org,
            pe,
            f"Budget Activity {i % 10}",
            f"Line Item {i}",
            f"Description for line item {i} in {org}",
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

    # Verify row count
    count = conn.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0]
    assert count == 100_000, f"Expected 100K rows, got {count}"

    yield conn, db_path
    conn.close()


class TestLoadPerformance:
    """Performance tests with 100K-row dataset."""

    def test_search_query_under_500ms(self, large_db):
        """Basic WHERE query completes in < 500ms."""
        conn, _ = large_db
        start = time.monotonic()
        rows = conn.execute(
            "SELECT * FROM budget_lines "
            "WHERE organization_name = 'Army' AND exhibit_type = 'p1' "
            "LIMIT 20"
        ).fetchall()
        elapsed_ms = (time.monotonic() - start) * 1000

        assert len(rows) > 0
        assert elapsed_ms < 500, f"Search took {elapsed_ms:.0f}ms (limit: 500ms)"

    def test_aggregation_query_under_500ms(self, large_db):
        """GROUP BY aggregation completes in < 500ms."""
        conn, _ = large_db
        start = time.monotonic()
        rows = conn.execute(
            "SELECT organization_name, "
            "SUM(amount_fy2026_request) AS total "
            "FROM budget_lines "
            "GROUP BY organization_name "
            "ORDER BY total DESC"
        ).fetchall()
        elapsed_ms = (time.monotonic() - start) * 1000

        assert len(rows) > 0
        assert elapsed_ms < 500, f"Aggregation took {elapsed_ms:.0f}ms (limit: 500ms)"

    def test_pagination_page_100_under_200ms(self, large_db):
        """Paginating to page 100 (offset 9900) completes in < 200ms."""
        conn, _ = large_db
        start = time.monotonic()
        rows = conn.execute(
            "SELECT * FROM budget_lines "
            "ORDER BY id "
            "LIMIT 100 OFFSET 9900"
        ).fetchall()
        elapsed_ms = (time.monotonic() - start) * 1000

        assert len(rows) == 100
        assert elapsed_ms < 200, f"Pagination took {elapsed_ms:.0f}ms (limit: 200ms)"

    def test_csv_download_starts_within_1s(self, large_db):
        """Fetching first 10,000 rows for CSV starts within 1s."""
        conn, _ = large_db
        start = time.monotonic()
        rows = conn.execute(
            "SELECT source_file, exhibit_type, fiscal_year, account, "
            "account_title, organization_name, pe_number, "
            "amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request "
            "FROM budget_lines "
            "LIMIT 10000"
        ).fetchall()
        elapsed_ms = (time.monotonic() - start) * 1000

        assert len(rows) == 10_000
        assert elapsed_ms < 1000, f"CSV fetch took {elapsed_ms:.0f}ms (limit: 1000ms)"

    def test_fts5_search_under_200ms(self, large_db):
        """FTS5 full-text search returns results in < 200ms."""
        conn, _ = large_db
        start = time.monotonic()
        rows = conn.execute(
            "SELECT rowid, bm25(budget_lines_fts) AS score "
            "FROM budget_lines_fts "
            "WHERE budget_lines_fts MATCH 'Army' "
            "ORDER BY score "
            "LIMIT 20"
        ).fetchall()
        elapsed_ms = (time.monotonic() - start) * 1000

        assert len(rows) > 0
        assert elapsed_ms < 200, f"FTS5 search took {elapsed_ms:.0f}ms (limit: 200ms)"
