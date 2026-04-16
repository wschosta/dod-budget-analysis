"""Tests for api/app.py — middleware, IP extraction, rate limiting, exception
handlers, and JSON formatting.

Covers the untested infrastructure portions of app.py.
"""
import json
import sqlite3
import sys
import types
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Stub optional deps before importing app
for _mod in ("pdfplumber", "openpyxl", "pandas"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def minimal_db(tmp_path):
    """Create a minimal database for app testing."""
    db = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE budget_lines (id INTEGER PRIMARY KEY, source_file TEXT);
        CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY);
        CREATE TABLE ingested_files (
            file_path TEXT PRIMARY KEY, file_type TEXT,
            file_size INTEGER, file_modified REAL, ingested_at TEXT,
            row_count INTEGER, status TEXT
        );
    """)
    conn.close()
    return db


@pytest.fixture()
def client(minimal_db):
    """TestClient wired to minimal DB."""
    from api.app import create_app
    app = create_app(db_path=minimal_db)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_rate_counters():
    """Clear rate limiter state between tests."""
    import api.app
    api.app._rate_counters.clear()
    yield
    api.app._rate_counters.clear()


# ── _get_client_ip ───────────────────────────────────────────────────────────


class TestGetClientIp:
    def test_direct_ip_no_proxies(self):
        """Without trusted proxies, returns direct client IP."""
        from api.app import _get_client_ip, _cfg
        original = _cfg.trusted_proxies
        _cfg.trusted_proxies = set()
        try:
            request = MagicMock()
            request.client.host = "192.168.1.100"
            assert _get_client_ip(request) == "192.168.1.100"
        finally:
            _cfg.trusted_proxies = original

    def test_untrusted_proxy_returns_direct_ip(self):
        """Request from non-trusted IP returns direct IP even with XFF header."""
        from api.app import _get_client_ip, _cfg
        original = _cfg.trusted_proxies
        _cfg.trusted_proxies = {"10.0.0.1"}
        try:
            request = MagicMock()
            request.client.host = "192.168.1.100"  # Not in trusted set
            request.headers.get.return_value = "203.0.113.50, 10.0.0.1"
            assert _get_client_ip(request) == "192.168.1.100"
        finally:
            _cfg.trusted_proxies = original

    def test_trusted_proxy_extracts_xff(self):
        """Request from trusted proxy extracts real IP from X-Forwarded-For."""
        from api.app import _get_client_ip, _cfg
        original = _cfg.trusted_proxies
        _cfg.trusted_proxies = {"10.0.0.1"}
        try:
            request = MagicMock()
            request.client.host = "10.0.0.1"
            request.headers.get.return_value = "203.0.113.50, 10.0.0.1"
            assert _get_client_ip(request) == "203.0.113.50"
        finally:
            _cfg.trusted_proxies = original

    def test_trusted_proxy_no_xff_returns_direct(self):
        """Trusted proxy without XFF header returns direct IP."""
        from api.app import _get_client_ip, _cfg
        original = _cfg.trusted_proxies
        _cfg.trusted_proxies = {"10.0.0.1"}
        try:
            request = MagicMock()
            request.client.host = "10.0.0.1"
            request.headers.get.return_value = ""
            assert _get_client_ip(request) == "10.0.0.1"
        finally:
            _cfg.trusted_proxies = original

    def test_no_client_returns_unknown(self):
        """When request.client is None, returns 'unknown'."""
        from api.app import _get_client_ip, _cfg
        original = _cfg.trusted_proxies
        _cfg.trusted_proxies = set()
        try:
            request = MagicMock()
            request.client = None
            assert _get_client_ip(request) == "unknown"
        finally:
            _cfg.trusted_proxies = original


# ── Exception handlers ───────────────────────────────────────────────────────


class TestExceptionHandlers:
    def test_health_endpoint(self, client):
        """Health endpoint returns structured response."""
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"

    def test_404_returns_json(self, client):
        """Nonexistent API path returns proper error."""
        resp = client.get("/api/v1/nonexistent-endpoint")
        assert resp.status_code in (404, 405)


# ── _JsonFormatter ───────────────────────────────────────────────────────────


class TestJsonFormatter:
    def test_format_basic_record(self):
        """JSON formatter produces valid JSON with required fields."""
        import logging
        from api.app import _JsonFormatter

        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="test_logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["level"] == "INFO"
        assert data["logger"] == "test_logger"
        assert data["message"] == "Test message"
        assert "timestamp" in data

    def test_format_with_extra_fields(self):
        """Extra fields (method, path, status) are included in JSON output."""
        import logging
        from api.app import _JsonFormatter

        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname="test.py", lineno=1,
            msg="Request", args=None, exc_info=None,
        )
        record.method = "GET"
        record.path = "/api/v1/search"
        record.status = 200
        record.duration_ms = 42.5

        output = formatter.format(record)
        data = json.loads(output)
        assert data["method"] == "GET"
        assert data["path"] == "/api/v1/search"
        assert data["status"] == 200
        assert data["duration_ms"] == 42.5

    def test_format_with_exception(self):
        """Exception info is included in JSON output."""
        import logging
        from api.app import _JsonFormatter

        formatter = _JsonFormatter()
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test", level=logging.ERROR,
            pathname="test.py", lineno=1,
            msg="Error occurred", args=None, exc_info=exc_info,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert "exc_info" in data
        assert "ValueError" in data["exc_info"]


# ── Rate limiting ────────────────────────────────────────────────────────────


class TestRateLimiting:
    def test_requests_within_limit_succeed(self, client):
        """Requests within rate limit should all succeed."""
        for _ in range(5):
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_cleanup_function(self):
        """_cleanup_rate_counters should remove stale entries."""
        import time
        from api.app import _rate_counters, _cleanup_rate_counters
        import api.app

        # Insert stale entries (timestamps from 2 minutes ago)
        stale_time = time.time() - 120
        _rate_counters["1.2.3.4"]["/api/v1/search"] = [stale_time]

        # Force cleanup by setting last_cleanup far in the past
        api.app._last_cleanup = 0.0
        _cleanup_rate_counters()

        # Stale entry should be removed
        assert "1.2.3.4" not in _rate_counters or \
            not _rate_counters["1.2.3.4"].get("/api/v1/search")
