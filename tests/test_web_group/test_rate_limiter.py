"""
TEST-004: Rate limiter behavior tests.

Tests the per-IP rate limiting middleware in api/app.py.
Rate limits:
    /api/v1/search:   60 req/min
    /api/v1/download: 10 req/min
    all others:       120 req/min (default)
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import api.app as app_module
from fastapi.testclient import TestClient
from api.app import create_app


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    """Create a minimal test database."""
    tmp = tmp_path_factory.mktemp("ratelimit_test")
    path = tmp / "test.sqlite"
    conn = sqlite3.connect(str(path))
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
        INSERT INTO budget_lines (source_file, exhibit_type, fiscal_year,
            organization_name, amount_fy2026_request)
        VALUES ('test.xlsx', 'p1', 'FY 2026', 'Army', 100000);
    """)
    conn.commit()
    conn.close()
    return path


@pytest.fixture(autouse=True)
def reset_rate_counters():
    """Clear rate-limit counters between tests for isolation."""
    app_module._rate_counters.clear()
    yield
    app_module._rate_counters.clear()


@pytest.fixture(scope="module")
def app(db_path):
    return create_app(db_path=db_path)


@pytest.fixture(scope="module")
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# ── /api/v1/search rate limit (60/min) ───────────────────────────────────────

class TestSearchRateLimit:
    def test_search_below_limit_returns_200(self, client):
        """Requests below the limit should succeed."""
        app_module._rate_counters.clear()
        for _ in range(5):
            resp = client.get("/api/v1/search?q=test")
            assert resp.status_code in (200, 422), (
                f"Expected 200/422, got {resp.status_code}"
            )

    def test_search_at_limit_returns_429(self, client):
        """The 61st request to /api/v1/search should return 429."""
        app_module._rate_counters.clear()
        for i in range(60):
            client.get("/api/v1/search?q=test")
        # 61st request should be rate-limited
        resp = client.get("/api/v1/search?q=test")
        assert resp.status_code == 429

    def test_search_429_has_retry_after_header(self, client):
        """429 response should include Retry-After header."""
        app_module._rate_counters.clear()
        for _ in range(60):
            client.get("/api/v1/search?q=test")
        resp = client.get("/api/v1/search?q=test")
        assert resp.status_code == 429
        assert "retry-after" in resp.headers or "Retry-After" in resp.headers

    def test_search_429_response_body(self, client):
        """429 response body should contain error info."""
        app_module._rate_counters.clear()
        for _ in range(60):
            client.get("/api/v1/search?q=test")
        resp = client.get("/api/v1/search?q=test")
        assert resp.status_code == 429
        data = resp.json()
        assert "error" in data


# ── /api/v1/download rate limit (10/min) ────────────────────────────────────

class TestDownloadRateLimit:
    def test_download_below_limit_returns_200(self, client):
        """Requests below the download limit should succeed."""
        app_module._rate_counters.clear()
        for _ in range(5):
            resp = client.get("/api/v1/download?fmt=csv&limit=1")
            assert resp.status_code == 200

    def test_download_at_limit_returns_429(self, client):
        """The 11th request to /api/v1/download should return 429."""
        app_module._rate_counters.clear()
        for _ in range(10):
            client.get("/api/v1/download?fmt=csv&limit=1")
        resp = client.get("/api/v1/download?fmt=csv&limit=1")
        assert resp.status_code == 429

    def test_download_429_has_retry_after(self, client):
        """Download 429 response should include Retry-After header."""
        app_module._rate_counters.clear()
        for _ in range(10):
            client.get("/api/v1/download?fmt=csv&limit=1")
        resp = client.get("/api/v1/download?fmt=csv&limit=1")
        assert resp.status_code == 429
        headers_lower = {k.lower(): v for k, v in resp.headers.items()}
        assert "retry-after" in headers_lower


# ── /health — not rate limited below default threshold ──────────────────────

class TestHealthNotRateLimited:
    def test_health_many_requests_not_rate_limited(self, client):
        """Health endpoint should not be rate-limited below the default limit."""
        app_module._rate_counters.clear()
        for i in range(20):
            resp = client.get("/health")
            # Health should return 200 or 503 (no DB), never 429
            assert resp.status_code in (200, 503), (
                f"Request {i+1}: expected 200/503, got {resp.status_code}"
            )


# ── Rate limit isolation ─────────────────────────────────────────────────────

class TestRateLimitIsolation:
    def test_different_paths_have_independent_limits(self, client):
        """Exhausting the search limit should not affect download limit."""
        app_module._rate_counters.clear()
        # Exhaust search limit
        for _ in range(60):
            client.get("/api/v1/search?q=test")
        # Search should now be rate limited
        resp_search = client.get("/api/v1/search?q=test")
        assert resp_search.status_code == 429
        # Download should still be OK (independent counter)
        resp_download = client.get("/api/v1/download?fmt=csv&limit=1")
        assert resp_download.status_code == 200

    def test_rate_limit_counters_cleared_on_reset(self, client):
        """After clearing counters, requests succeed again."""
        app_module._rate_counters.clear()
        # Exhaust download limit
        for _ in range(10):
            client.get("/api/v1/download?fmt=csv&limit=1")
        resp = client.get("/api/v1/download?fmt=csv&limit=1")
        assert resp.status_code == 429
        # Clear and retry
        app_module._rate_counters.clear()
        resp = client.get("/api/v1/download?fmt=csv&limit=1")
        assert resp.status_code == 200
