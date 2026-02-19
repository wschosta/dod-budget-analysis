"""
Database connection management for the API (Step 2.C7-a).

Provides a get_db() dependency that opens a per-request SQLite connection and
closes it after the response is sent.  The database path is resolved once at
startup from the APP_DB_PATH environment variable (default: dod_budget.sqlite).

──────────────────────────────────────────────────────────────────────────────
TODOs for this file
──────────────────────────────────────────────────────────────────────────────

TODO OPT-DB-001 [Group: TIGER] [Complexity: MEDIUM] [Tokens: ~2500] [User: NO]
    Implement connection pooling for the API.
    Currently each request opens a new SQLite connection and closes it after.
    For high-concurrency workloads, this is wasteful. Steps:
      1. Create a ConnectionPool class with max_size (default 10) connections
      2. get_db() acquires from pool; release on request completion
      3. Use threading.local() or contextvar for thread-safe pool access
      4. Add pool metrics: active connections, wait time, max concurrent
      5. Configure pool size via APP_DB_POOL_SIZE environment variable
    Note: SQLite WAL mode supports concurrent readers, so pooling is safe
    for read-heavy API workloads. Only one writer at a time is allowed.
    Acceptance: Pool reuses connections; no performance regression on tests.

TODO OPT-DB-002 [Group: TIGER] [Complexity: LOW] [Tokens: ~1000] [User: NO]
    Add read-only connection mode for API queries.
    All API endpoints are read-only but connections are opened read-write.
    Steps:
      1. Open connections with sqlite3.connect("file:path?mode=ro", uri=True)
      2. This prevents accidental writes and enables SQLite optimizations
      3. Keep a separate write connection path for admin endpoints (if any)
    Acceptance: API connections are read-only; write attempts raise errors.

TODO OPT-DB-003 [Group: TIGER] [Complexity: LOW] [Tokens: ~800] [User: NO]
    Add database file existence check with friendly error on startup.
    If APP_DB_PATH points to a non-existent file, requests fail with
    cryptic SQLite errors. Steps:
      1. In get_db(), check path.exists() before connecting
      2. Raise HTTPException(503, "Database not found. Run build_budget_db.py")
      3. Log a startup warning in the lifespan handler (partially done)
    Acceptance: Missing DB returns clear 503 error instead of 500 traceback.
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
