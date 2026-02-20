"""
Tests for utils/common.py

Verifies format_bytes, elapsed, sanitize_filename, and get_connection.
"""
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.common import format_bytes, elapsed, sanitize_filename, get_connection


# ── format_bytes ──────────────────────────────────────────────────────────────

class TestFormatBytes:
    def test_kilobytes(self):
        assert format_bytes(512 * 1024) == "512 KB"

    def test_small_kb(self):
        assert format_bytes(1024) == "1 KB"

    def test_megabytes(self):
        result = format_bytes(1536 * 1024)  # 1.5 MB
        assert "1.5 MB" == result

    def test_gigabytes(self):
        result = format_bytes(2 * 1024 * 1024 * 1024)
        assert "2.00 GB" == result

    def test_zero(self):
        assert format_bytes(0) == "0 KB"


# ── elapsed ───────────────────────────────────────────────────────────────────

class TestElapsed:
    def test_seconds(self):
        with patch("utils.common.time.time", return_value=1000.0 + 30):
            result = elapsed(1000.0)
        assert result == "0m 30s"

    def test_minutes(self):
        with patch("utils.common.time.time", return_value=1000.0 + 135):
            result = elapsed(1000.0)
        assert result == "2m 15s"

    def test_hours(self):
        with patch("utils.common.time.time", return_value=1000.0 + 3930):
            result = elapsed(1000.0)
        assert result == "1h 05m 30s"


# ── sanitize_filename ────────────────────────────────────────────────────────

class TestSanitizeFilename:
    def test_strips_query_params(self):
        assert sanitize_filename("file.xlsx?v=2&sig=abc") == "file.xlsx"

    def test_replaces_special_chars(self):
        result = sanitize_filename('file<>:"/\\|?*name.txt')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "\\" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_normal_filename_unchanged(self):
        assert sanitize_filename("budget_fy2026.xlsx") == "budget_fy2026.xlsx"

    def test_empty_string(self):
        assert sanitize_filename("") == ""


# ── get_connection ────────────────────────────────────────────────────────────

class TestGetConnection:
    def test_returns_connection(self, tmp_path):
        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.close()

        result = get_connection(db_path)
        assert isinstance(result, sqlite3.Connection)
        # Row factory should be set
        row = result.execute("SELECT 1 as val").fetchone()
        assert row["val"] == 1
        result.close()

    def test_missing_db_exits(self, tmp_path):
        missing = tmp_path / "nonexistent.sqlite"
        with pytest.raises(SystemExit):
            get_connection(missing)
