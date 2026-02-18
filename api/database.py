"""
Database connection management for the API (Step 2.C7-a).

Provides a get_db() dependency that opens a per-request SQLite connection and
closes it after the response is sent.  The database path is resolved once at
startup from the APP_DB_PATH environment variable (default: dod_budget.sqlite).
"""

import os
import sqlite3
from collections.abc import Generator
from pathlib import Path

_DB_PATH: Path = Path(os.getenv("APP_DB_PATH", "dod_budget.sqlite"))


def get_db_path() -> Path:
    """Return the configured database path."""
    return _DB_PATH


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency: yield a SQLite connection, close on exit.

    Usage in a route:
        from api.database import get_db
        from fastapi import Depends
        @router.get("/example")
        def example(conn=Depends(get_db)):
            ...
    """
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
    finally:
        conn.close()
