"""
TEST-005: Performance regression smoke tests.

Tests that key API endpoints complete within acceptable time bounds on a
1000-row SQLite database.  Uses time.monotonic() — not pytest-benchmark —
so no additional dependencies are required.

Thresholds (generous enough for CI but tight enough to catch O(n²) regressions):
  /api/v1/search         < 100 ms
  /api/v1/aggregations   < 200 ms
  /api/v1/budget-lines   <  50 ms
  /api/v1/download       < 200 ms
"""
import sqlite3
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import api.app as app_module
from fastapi.testclient import TestClient
from api.app import create_app

# ── Fixtures ──────────────────────────────────────────────────────────────────

_ROW_COUNT = 1000


@pytest.fixture(scope="module")
def perf_client(tmp_path_factory):
    """App client backed by a 1000-row SQLite database."""
    tmp = tmp_path_factory.mktemp("perf_test")
    db_path = tmp / "perf.sqlite"

    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT, exhibit_type TEXT, sheet_name TEXT,
            fiscal_year TEXT, account TEXT, account_title TEXT,
            organization TEXT, organization_name TEXT,
            budget_activity TEXT, budget_activity_title TEXT,
            sub_activity TEXT, sub_activity_title TEXT,
            line_item TEXT, line_item_title TEXT,
            pe_number TEXT, appropriation_code TEXT, appropriation_title TEXT,
            currency_year TEXT, amount_unit TEXT, amount_type TEXT,
            amount_fy2024_actual REAL, amount_fy2025_enacted REAL,
            amount_fy2025_supplemental REAL, amount_fy2025_total REAL,
            amount_fy2026_request REAL, amount_fy2026_reconciliation REAL,
            amount_fy2026_total REAL,
            quantity_fy2024 REAL, quantity_fy2025 REAL,
            quantity_fy2026_request REAL, quantity_fy2026_total REAL,
            classification TEXT, extra_fields TEXT, budget_type TEXT
        );
        CREATE TABLE pdf_pages (
            id INTEGER PRIMARY KEY, source_file TEXT,
            source_category TEXT, page_number INTEGER,
            page_text TEXT, has_tables INTEGER, table_data TEXT
        );
        CREATE TABLE ingested_files (
            id INTEGER PRIMARY KEY, file_path TEXT, file_type TEXT,
            row_count INTEGER, ingested_at TEXT, status TEXT
        );
        CREATE VIRTUAL TABLE budget_lines_fts USING fts5(
            account_title, line_item_title, budget_activity_title,
            content=budget_lines
        );
        CREATE VIRTUAL TABLE pdf_pages_fts USING fts5(
            page_text, content=pdf_pages
        );
    """)

    # Insert 1000 rows across a variety of services, exhibit types, and years
    _SERVICES = ["Army", "Navy", "Air Force", "Marine Corps", "Space Force"]
    _EXHIBITS = ["p1", "r1", "p5", "r2"]
    _YEARS = ["FY 2024", "FY 2025", "FY 2026"]
    _ACCOUNTS = [
        "Aircraft Procurement", "Ship Procurement", "RDT&E",
        "Missile Procurement", "Satellite Systems",
    ]
    _LINE_ITEMS = [
        "Apache AH-64", "DDG-51 Destroyer", "F-35 Development",
        "Hypersonic Research", "GPS III", "Cyber Operations",
        "C-130J Transport", "V-22 Osprey", "HIMARS System",
        "Trident II D5",
    ]

    rows = []
    for i in range(_ROW_COUNT):
        service = _SERVICES[i % len(_SERVICES)]
        exhibit = _EXHIBITS[i % len(_EXHIBITS)]
        year = _YEARS[i % len(_YEARS)]
        account = _ACCOUNTS[i % len(_ACCOUNTS)]
        line_item = _LINE_ITEMS[i % len(_LINE_ITEMS)]
        amount = float(100 + i * 10)
        rows.append((
            f"file_{i}.xlsx", exhibit, year, service, account, line_item,
            amount, amount * 1.1, amount * 1.2,
        ))

    conn.executemany(
        """INSERT INTO budget_lines
               (source_file, exhibit_type, fiscal_year, organization_name,
                account_title, line_item_title,
                amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()

    # Rebuild FTS index
    conn.execute(
        "INSERT INTO budget_lines_fts(rowid, account_title, line_item_title, "
        "budget_activity_title) "
        "SELECT id, account_title, line_item_title, budget_activity_title "
        "FROM budget_lines"
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_counters():
    app_module._rate_counters.clear()
    yield
    app_module._rate_counters.clear()


# ── Helper ────────────────────────────────────────────────────────────────────

def _elapsed_ms(client, method: str, url: str) -> float:
    """Return elapsed time in milliseconds for a single request."""
    t0 = time.monotonic()
    resp = getattr(client, method)(url)
    elapsed = (time.monotonic() - t0) * 1000
    assert resp.status_code in (200, 206), (
        f"Unexpected status {resp.status_code} for {url}"
    )
    return elapsed


# ── Search performance ────────────────────────────────────────────────────────

class TestSearchPerformance:
    _THRESHOLD_MS = 100

    def test_search_completes_within_threshold(self, perf_client):
        """/api/v1/search with a keyword should finish in < 100 ms."""
        elapsed = _elapsed_ms(perf_client, "get", "/api/v1/search?q=Apache")
        assert elapsed < self._THRESHOLD_MS, (
            f"Search took {elapsed:.1f} ms (threshold {self._THRESHOLD_MS} ms)"
        )

    def test_search_common_term_completes_within_threshold(self, perf_client):
        """/api/v1/search with a common keyword should finish in < 100 ms."""
        elapsed = _elapsed_ms(perf_client, "get", "/api/v1/search?q=procurement")
        assert elapsed < self._THRESHOLD_MS, (
            f"Search (common term) took {elapsed:.1f} ms "
            f"(threshold {self._THRESHOLD_MS} ms)"
        )

    def test_search_with_filters_completes_within_threshold(self, perf_client):
        """Filtered search should finish in < 100 ms."""
        url = "/api/v1/search?q=procurement&fiscal_year=FY+2026"
        elapsed = _elapsed_ms(perf_client, "get", url)
        assert elapsed < self._THRESHOLD_MS, (
            f"Filtered search took {elapsed:.1f} ms (threshold {self._THRESHOLD_MS} ms)"
        )


# ── Aggregation performance ───────────────────────────────────────────────────

class TestAggregationPerformance:
    _THRESHOLD_MS = 200

    def test_aggregation_by_service_completes_within_threshold(self, perf_client):
        """Aggregation by service should finish in < 200 ms."""
        elapsed = _elapsed_ms(
            perf_client, "get", "/api/v1/aggregations?group_by=service"
        )
        assert elapsed < self._THRESHOLD_MS, (
            f"Aggregation (service) took {elapsed:.1f} ms "
            f"(threshold {self._THRESHOLD_MS} ms)"
        )

    def test_aggregation_by_fiscal_year_completes_within_threshold(self, perf_client):
        """Aggregation by fiscal year should finish in < 200 ms."""
        elapsed = _elapsed_ms(
            perf_client, "get", "/api/v1/aggregations?group_by=fiscal_year"
        )
        assert elapsed < self._THRESHOLD_MS, (
            f"Aggregation (fiscal_year) took {elapsed:.1f} ms "
            f"(threshold {self._THRESHOLD_MS} ms)"
        )

    def test_aggregation_by_exhibit_type_completes_within_threshold(self, perf_client):
        """Aggregation by exhibit_type should finish in < 200 ms."""
        elapsed = _elapsed_ms(
            perf_client, "get", "/api/v1/aggregations?group_by=exhibit_type"
        )
        assert elapsed < self._THRESHOLD_MS, (
            f"Aggregation (exhibit_type) took {elapsed:.1f} ms "
            f"(threshold {self._THRESHOLD_MS} ms)"
        )


# ── Budget-lines first page performance ───────────────────────────────────────

class TestBudgetLinesPerformance:
    _THRESHOLD_MS = 50

    def test_budget_lines_first_page_completes_within_threshold(self, perf_client):
        """/api/v1/budget-lines first page should finish in < 50 ms."""
        elapsed = _elapsed_ms(
            perf_client, "get", "/api/v1/budget-lines?limit=25&offset=0"
        )
        assert elapsed < self._THRESHOLD_MS, (
            f"Budget-lines first page took {elapsed:.1f} ms "
            f"(threshold {self._THRESHOLD_MS} ms)"
        )

    def test_budget_lines_sorted_page_completes_within_threshold(self, perf_client):
        """Sorted budget-lines should finish in < 50 ms."""
        url = "/api/v1/budget-lines?limit=25&offset=0&sort_by=amount_fy2026_request&sort_dir=desc"
        elapsed = _elapsed_ms(perf_client, "get", url)
        assert elapsed < self._THRESHOLD_MS, (
            f"Budget-lines (sorted) took {elapsed:.1f} ms "
            f"(threshold {self._THRESHOLD_MS} ms)"
        )


# ── Download streaming performance ────────────────────────────────────────────

class TestDownloadPerformance:
    _THRESHOLD_MS = 200

    def test_csv_download_starts_within_threshold(self, perf_client):
        """/api/v1/download CSV should complete in < 200 ms."""
        elapsed = _elapsed_ms(
            perf_client, "get", "/api/v1/download?fmt=csv&limit=100"
        )
        assert elapsed < self._THRESHOLD_MS, (
            f"CSV download took {elapsed:.1f} ms (threshold {self._THRESHOLD_MS} ms)"
        )

    def test_json_download_starts_within_threshold(self, perf_client):
        """/api/v1/download JSON should complete in < 200 ms."""
        elapsed = _elapsed_ms(
            perf_client, "get", "/api/v1/download?fmt=json&limit=100"
        )
        assert elapsed < self._THRESHOLD_MS, (
            f"JSON download took {elapsed:.1f} ms (threshold {self._THRESHOLD_MS} ms)"
        )
