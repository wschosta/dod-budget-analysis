"""
Tests for api/database.py — get_db() and get_db_path()

Verifies the FastAPI database dependency yields a properly configured
SQLite connection and closes it on exit.
"""
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.database import get_db, get_db_path


class TestGetDbPath:
    def test_returns_path(self):
        result = get_db_path()
        assert isinstance(result, Path)

    def test_default_path(self):
        # Default is dod_budget.sqlite when APP_DB_PATH not set
        result = get_db_path()
        assert result.name.endswith(".sqlite")


class TestGetDb:
    def test_yields_connection(self, tmp_path):
        db_path = tmp_path / "test.sqlite"
        # Create the DB file
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.close()

        with patch("api.database._DB_PATH", db_path):
            gen = get_db()
            conn = next(gen)
            assert isinstance(conn, sqlite3.Connection)
            # Should have row_factory set
            row = conn.execute("SELECT 1 as val").fetchone()
            assert row["val"] == 1
            # Clean up
            try:
                next(gen)
            except StopIteration:
                pass

    def test_connection_closed_after_yield(self, tmp_path):
        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.close()

        with patch("api.database._DB_PATH", db_path):
            gen = get_db()
            conn = next(gen)
            # Exhaust the generator to trigger finally block
            try:
                next(gen)
            except StopIteration:
                pass
            # Connection should be closed (attempting to use it should fail)
            with pytest.raises(Exception):
                conn.execute("SELECT 1")

    def test_wal_mode_set(self, tmp_path):
        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.close()

        with patch("api.database._DB_PATH", db_path):
            gen = get_db()
            conn = next(gen)
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == "wal"
            try:
                next(gen)
            except StopIteration:
                pass
