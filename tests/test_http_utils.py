"""
Tests for HTTP and download utilities — utils/http.py

Tests RetryStrategy, SessionManager, TimeoutManager, and CacheManager
without requiring actual network calls.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.http import RetryStrategy, SessionManager, TimeoutManager, CacheManager, download_file


# ── RetryStrategy tests ──────────────────────────────────────────────────────

class TestRetryStrategy:
    def test_defaults(self):
        rs = RetryStrategy()
        assert rs.max_retries == 3
        assert rs.backoff_factor == 2.0
        assert 429 in rs.status_forcelist
        assert 503 in rs.status_forcelist

    def test_custom_params(self):
        rs = RetryStrategy(max_retries=5, backoff_factor=1.0,
                           status_forcelist=[500, 502])
        assert rs.max_retries == 5
        assert rs.backoff_factor == 1.0
        assert rs.status_forcelist == [500, 502]

    def test_get_retry_object(self):
        rs = RetryStrategy(max_retries=4, backoff_factor=3.0)
        retry = rs.get_retry_object()
        assert retry.total == 4
        assert retry.backoff_factor == 3.0

    def test_retry_allowed_methods(self):
        rs = RetryStrategy()
        retry = rs.get_retry_object()
        allowed = retry.allowed_methods
        assert "GET" in allowed
        assert "HEAD" in allowed


# ── SessionManager tests ─────────────────────────────────────────────────────

class TestSessionManager:
    def test_creates_session(self):
        sm = SessionManager()
        session = sm.session
        assert session is not None
        sm.close()

    def test_session_cached(self):
        """Accessing .session twice returns the same object."""
        sm = SessionManager()
        s1 = sm.session
        s2 = sm.session
        assert s1 is s2
        sm.close()

    def test_close_resets_session(self):
        sm = SessionManager()
        _ = sm.session
        sm.close()
        assert sm._session is None

    def test_close_idempotent(self):
        sm = SessionManager()
        sm.close()  # no session yet
        sm.close()  # still fine

    def test_context_manager(self):
        with SessionManager() as sm:
            session = sm.session
            assert session is not None
        # After exit, session should be closed
        assert sm._session is None

    def test_custom_retry_strategy(self):
        rs = RetryStrategy(max_retries=5)
        sm = SessionManager(retry_strategy=rs)
        assert sm.retry_strategy.max_retries == 5
        sm.close()

    def test_custom_pool_settings(self):
        sm = SessionManager(pool_connections=5, pool_maxsize=10)
        assert sm.pool_connections == 5
        assert sm.pool_maxsize == 10
        sm.close()


# ── TimeoutManager tests ─────────────────────────────────────────────────────

class TestTimeoutManager:
    def test_defaults(self):
        tm = TimeoutManager()
        assert tm.base_timeout == 30
        assert tm.min_timeout == 10
        assert tm.max_timeout == 120

    def test_new_domain_returns_base_timeout(self):
        tm = TimeoutManager(base_timeout=25)
        timeout = tm.get_timeout("https://example.com/file.xlsx")
        assert timeout == 25

    def test_few_samples_returns_base(self):
        """With fewer than 3 data points, returns base_timeout."""
        tm = TimeoutManager(base_timeout=30)
        tm.record_time("https://example.com/a.xlsx", 5.0)
        tm.record_time("https://example.com/b.xlsx", 6.0)
        assert tm.get_timeout("https://example.com/c.xlsx") == 30

    def test_adaptive_timeout(self):
        """With enough data, returns adaptive timeout based on 95th pctl."""
        tm = TimeoutManager(base_timeout=30, min_timeout=5, max_timeout=120)
        # Record 10 fast responses + 1 slow one
        for _ in range(9):
            tm.record_time("https://example.com/file.xlsx", 2.0)
        tm.record_time("https://example.com/file.xlsx", 10.0)

        timeout = tm.get_timeout("https://example.com/next.xlsx")
        # 95th percentile of [2,2,2,2,2,2,2,2,2,10] is 10 -> * 1.5 = 15
        assert timeout >= 5  # at least min_timeout
        assert timeout <= 120  # at most max_timeout

    def test_respects_min_timeout(self):
        """Very fast responses still produce at least min_timeout."""
        tm = TimeoutManager(min_timeout=10)
        for _ in range(5):
            tm.record_time("https://fast.com/file.xlsx", 0.1)
        timeout = tm.get_timeout("https://fast.com/next.xlsx")
        assert timeout >= 10

    def test_respects_max_timeout(self):
        """Very slow responses are capped at max_timeout."""
        tm = TimeoutManager(max_timeout=60)
        for _ in range(5):
            tm.record_time("https://slow.com/file.xlsx", 100.0)
        timeout = tm.get_timeout("https://slow.com/next.xlsx")
        assert timeout <= 60

    def test_per_domain_tracking(self):
        """Different domains maintain separate histories."""
        tm = TimeoutManager(base_timeout=30)
        tm.record_time("https://fast.com/a.xlsx", 1.0)
        tm.record_time("https://slow.com/a.xlsx", 50.0)

        assert "fast.com" in tm.response_times
        assert "slow.com" in tm.response_times
        assert len(tm.response_times["fast.com"]) == 1
        assert len(tm.response_times["slow.com"]) == 1

    def test_history_size_limit(self):
        """Old entries are evicted when history_size is exceeded."""
        tm = TimeoutManager(history_size=5)
        for i in range(10):
            tm.record_time("https://example.com/file.xlsx", float(i))
        assert len(tm.response_times["example.com"]) == 5
        # Should keep the last 5: [5.0, 6.0, 7.0, 8.0, 9.0]
        assert tm.response_times["example.com"][0] == 5.0

    def test_get_domain(self):
        tm = TimeoutManager()
        assert tm._get_domain("https://comptroller.defense.gov/file.xlsx") == \
            "comptroller.defense.gov"
        assert tm._get_domain("http://localhost:8080/api") == "localhost:8080"


# ── CacheManager tests ───────────────────────────────────────────────────────

class TestCacheManager:
    def test_put_and_get(self, tmp_path):
        cm = CacheManager(cache_dir=tmp_path / "cache")
        cm.put("test_key", {"result": 42})
        data = cm.get("test_key")
        assert data == {"result": 42}

    def test_get_missing_key(self, tmp_path):
        cm = CacheManager(cache_dir=tmp_path / "cache")
        assert cm.get("nonexistent") is None

    def test_cache_expiry(self, tmp_path):
        cm = CacheManager(cache_dir=tmp_path / "cache", ttl_hours=1)
        # Manually write an expired cache entry
        cache_path = cm._get_cache_path("expired_key")
        old_timestamp = (datetime.now() - timedelta(hours=2)).isoformat()
        cache_path.write_text(json.dumps({
            "timestamp": old_timestamp,
            "data": "old data",
        }))
        assert cm.get("expired_key") is None

    def test_cache_fresh_within_ttl(self, tmp_path):
        cm = CacheManager(cache_dir=tmp_path / "cache", ttl_hours=24)
        cm.put("fresh_key", "fresh data")
        assert cm.get("fresh_key") == "fresh data"

    def test_clear_removes_all(self, tmp_path):
        cm = CacheManager(cache_dir=tmp_path / "cache")
        cm.put("key1", "data1")
        cm.put("key2", "data2")
        cm.clear()
        assert cm.get("key1") is None
        assert cm.get("key2") is None

    def test_clear_expired(self, tmp_path):
        cm = CacheManager(cache_dir=tmp_path / "cache", ttl_hours=1)
        # Add fresh entry
        cm.put("fresh", "still good")
        # Add expired entry manually
        expired_path = cm._get_cache_path("old")
        old_time = (datetime.now() - timedelta(hours=2)).isoformat()
        expired_path.write_text(json.dumps({
            "timestamp": old_time,
            "data": "expired",
        }))

        removed = cm.clear_expired()
        assert removed == 1
        assert cm.get("fresh") == "still good"
        assert cm.get("old") is None

    def test_invalid_json_returns_none(self, tmp_path):
        cm = CacheManager(cache_dir=tmp_path / "cache")
        cache_path = cm._get_cache_path("bad_json")
        cache_path.write_text("not valid json {{}")
        assert cm.get("bad_json") is None

    def test_no_timestamp_returns_none(self, tmp_path):
        cm = CacheManager(cache_dir=tmp_path / "cache")
        cache_path = cm._get_cache_path("no_ts")
        cache_path.write_text(json.dumps({"data": "no timestamp field"}))
        assert cm.get("no_ts") is None

    def test_creates_cache_dir(self, tmp_path):
        cache_dir = tmp_path / "deep" / "nested" / "cache"
        cm = CacheManager(cache_dir=cache_dir)
        assert cache_dir.exists()

    def test_cache_path_sanitized(self, tmp_path):
        cm = CacheManager(cache_dir=tmp_path / "cache")
        path = cm._get_cache_path("https://example.com/path?q=1&b=2")
        assert path.suffix == ".json"
        # No slashes or special URL chars in filename
        assert "/" not in path.name
        assert "?" not in path.name

    def test_complex_data_types(self, tmp_path):
        cm = CacheManager(cache_dir=tmp_path / "cache")
        data = {
            "urls": ["https://a.com", "https://b.com"],
            "counts": {"army": 10, "navy": 5},
            "active": True,
        }
        cm.put("complex", data)
        result = cm.get("complex")
        assert result == data


# ── download_file tests ──────────────────────────────────────────────────────

class TestDownloadFile:
    def _mock_session(self, content=b"file data", status=200, raise_exc=None):
        from unittest.mock import MagicMock
        import requests

        session = MagicMock()
        if raise_exc:
            session.get.side_effect = raise_exc
            return session

        response = MagicMock()
        response.status_code = status
        response.raise_for_status = MagicMock()
        if status >= 400:
            response.raise_for_status.side_effect = requests.HTTPError()
        response.iter_content = MagicMock(return_value=[content])
        session.get.return_value = response
        return session

    def test_success(self, tmp_path):
        dest = tmp_path / "out" / "file.pdf"
        session = self._mock_session(content=b"PDF content here")
        result = download_file("https://example.com/file.pdf", dest, session=session)
        assert result is True
        assert dest.exists()
        assert dest.read_bytes() == b"PDF content here"

    def test_creates_parent_dirs(self, tmp_path):
        dest = tmp_path / "a" / "b" / "c" / "file.pdf"
        session = self._mock_session()
        download_file("https://example.com/file.pdf", dest, session=session)
        assert dest.exists()

    def test_http_error_returns_false(self, tmp_path):
        import requests
        dest = tmp_path / "file.pdf"
        session = self._mock_session(raise_exc=requests.ConnectionError("failed"))
        result = download_file("https://example.com/file.pdf", dest, session=session)
        assert result is False

    def test_cleans_empty_file_on_error(self, tmp_path):
        import requests
        dest = tmp_path / "file.pdf"
        # Create an empty file to simulate partial download
        dest.write_bytes(b"")
        session = self._mock_session(raise_exc=requests.ConnectionError("failed"))
        download_file("https://example.com/file.pdf", dest, session=session)
        assert not dest.exists()  # Empty file should be cleaned up

    def test_timeout_passed_to_session(self, tmp_path):
        dest = tmp_path / "file.pdf"
        session = self._mock_session()
        download_file("https://example.com/f.pdf", dest, session=session, timeout=60)
        session.get.assert_called_once()
        _, kwargs = session.get.call_args
        assert kwargs["timeout"] == 60

    def test_streaming_enabled(self, tmp_path):
        dest = tmp_path / "file.pdf"
        session = self._mock_session()
        download_file("https://example.com/f.pdf", dest, session=session)
        _, kwargs = session.get.call_args
        assert kwargs["stream"] is True
