"""
Tests for query performance logging (TIGER-011).
"""
import sqlite3
import sys
import time
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Stub optional dependencies
for _mod in ("pdfplumber", "openpyxl", "pandas"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

from utils.database import (
    timed_execute,
    get_slow_queries,
    get_query_stats,
    _query_stats,
    _slow_queries,
    _query_stats_lock,
    _SLOW_QUERY_THRESHOLD_MS,
)


@pytest.fixture(autouse=True)
def reset_stats():
    """Reset query stats between tests."""
    with _query_stats_lock:
        _query_stats["total_queries"] = 0
        _query_stats["slow_query_count"] = 0
        _query_stats["total_time_ms"] = 0.0
        _slow_queries.clear()
    yield


@pytest.fixture
def conn():
    """In-memory database for testing."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, value TEXT)")
    c.execute("INSERT INTO test_data VALUES (1, 'hello')")
    c.execute("INSERT INTO test_data VALUES (2, 'world')")
    c.commit()
    yield c
    c.close()


class TestTimedExecute:
    def test_returns_cursor(self, conn):
        """timed_execute returns a valid cursor with results."""
        cursor = timed_execute(conn, "SELECT * FROM test_data")
        rows = cursor.fetchall()
        assert len(rows) == 2

    def test_increments_query_count(self, conn):
        """Each timed_execute increments total_queries."""
        timed_execute(conn, "SELECT * FROM test_data")
        timed_execute(conn, "SELECT * FROM test_data WHERE id = ?", (1,))
        stats = get_query_stats()
        assert stats["total_queries"] == 2

    def test_tracks_total_time(self, conn):
        """Total time is accumulated across queries."""
        timed_execute(conn, "SELECT * FROM test_data")
        stats = get_query_stats()
        assert stats["avg_query_time_ms"] >= 0

    def test_with_params(self, conn):
        """timed_execute works with parameterized queries."""
        cursor = timed_execute(conn, "SELECT * FROM test_data WHERE id = ?", (1,))
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["value"] == "hello"


class TestSlowQueryLog:
    def test_get_slow_queries_empty(self):
        """Initially no slow queries."""
        assert get_slow_queries() == []

    def test_get_query_stats_initial(self):
        """Initial stats are zeroed."""
        stats = get_query_stats()
        assert stats["total_queries"] == 0
        assert stats["slow_query_count"] == 0
        assert stats["avg_query_time_ms"] == 0.0


class TestHealthQueriesEndpoint:
    def test_health_queries_endpoint(self, tmp_path):
        """GET /api/v1/health/queries returns stats and slow_queries."""
        db = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db))
        conn.executescript("""
            CREATE TABLE budget_lines (id INTEGER PRIMARY KEY, source_file TEXT);
            CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY);
            CREATE TABLE ingested_files (file_path TEXT PRIMARY KEY, file_type TEXT,
                file_size INTEGER, file_modified REAL, ingested_at TEXT,
                row_count INTEGER, status TEXT);
        """)
        conn.close()

        from fastapi.testclient import TestClient
        from api.app import create_app
        app = create_app(db_path=db)
        client = TestClient(app)

        response = client.get("/api/v1/health/queries")
        assert response.status_code == 200
        data = response.json()
        assert "stats" in data
        assert "slow_queries" in data
        assert "total_queries" in data["stats"]
        assert "slow_query_count" in data["stats"]

    def test_health_detailed_includes_query_stats(self, tmp_path):
        """GET /health/detailed includes slow_query_count and avg_query_time_ms."""
        db = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db))
        conn.executescript("""
            CREATE TABLE budget_lines (id INTEGER PRIMARY KEY, source_file TEXT);
            CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY);
            CREATE TABLE ingested_files (file_path TEXT PRIMARY KEY, file_type TEXT,
                file_size INTEGER, file_modified REAL, ingested_at TEXT,
                row_count INTEGER, status TEXT);
        """)
        conn.close()

        from fastapi.testclient import TestClient
        from api.app import create_app
        app = create_app(db_path=db)
        client = TestClient(app)

        response = client.get("/health/detailed")
        assert response.status_code == 200
        data = response.json()
        assert "slow_query_count" in data
        assert "avg_query_time_ms" in data
