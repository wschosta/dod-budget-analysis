"""
Database connection management for the API (Step 2.C7-a).

Provides a get_db() dependency that opens a per-request SQLite connection and
closes it after the response is sent.  The database path is resolved once at
startup from the APP_DB_PATH environment variable (default: dod_budget.sqlite).

OPT-DB-002: Read-only connection mode via SQLite URI.
"""

import os
import sqlite3
from collections.abc import Generator
from pathlib import Path

_DB_PATH: Path = Path(os.getenv("APP_DB_PATH", "dod_budget.sqlite"))


def get_db_path() -> Path:
    """Return the configured database path."""
    return _DB_PATH


def _make_conn(db_path: Path, read_only: bool = False) -> sqlite3.Connection:
    """Open a single SQLite connection with standard pragmas.

    OPT-DB-002: Supports optional read-only mode via SQLite URI.

    Args:
        db_path: Path to the SQLite database file.
        read_only: If True, open in read-only mode (no WAL pragma).
    """
    if read_only:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False,
                               timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        return conn
    conn = sqlite3.connect(str(db_path), check_same_thread=False,
                           timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency: yield a SQLite connection, close on exit."""
    conn = _make_conn(_DB_PATH)
    try:
        yield conn
    finally:
        conn.close()
