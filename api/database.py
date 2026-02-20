"""
Database connection management for the API (Step 2.C7-a).

Provides a get_db() dependency that opens a per-request SQLite connection and
closes it after the response is sent.  The database path is resolved once at
startup from the APP_DB_PATH environment variable (default: dod_budget.sqlite).

OPT-DB-001: Connection pooling with configurable pool size.
OPT-DB-002: Read-only connection mode via SQLite URI.
OPT-DB-003: Friendly 503 error when database file is missing.
"""

import os
import queue
import sqlite3
import threading
from collections.abc import Generator
from pathlib import Path

from fastapi import HTTPException

_DB_PATH: Path = Path(os.getenv("APP_DB_PATH", "dod_budget.sqlite"))
_POOL_SIZE: int = int(os.getenv("APP_DB_POOL_SIZE", "10"))


def get_db_path() -> Path:
    """Return the configured database path."""
    return _DB_PATH


# ── OPT-DB-001: Connection Pool ───────────────────────────────────────────────

class _ClosedConnection:
    """Sentinel wrapper that raises ProgrammingError for any attribute access.

    Replaces a pooled connection reference in the caller's scope once the
    connection has been returned to the pool, so callers cannot accidentally
    use a released connection.
    """
    __slots__ = ("_msg",)

    def __init__(self, msg: str = "Connection has been released to the pool"):
        object.__setattr__(self, "_msg", msg)

    def __getattr__(self, name: str):
        raise sqlite3.ProgrammingError(object.__getattribute__(self, "_msg"))


class _ConnectionPool:
    """Simple SQLite connection pool using a queue for thread-safety.

    Connections are created lazily up to ``max_size``.  When a connection is
    released it is returned to the pool (not closed) so subsequent requests
    can reuse it without the open/pragma overhead.
    """

    def __init__(self, db_path: Path, max_size: int = 10) -> None:
        self._db_path = db_path
        self._max_size = max_size
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=max_size)
        self._active = 0
        self._lock = threading.Lock()

    def _make_conn(self) -> sqlite3.Connection:
        """Open a new read-only connection with standard pragmas."""
        # OPT-DB-002: open read-only via URI
        uri = f"file:{self._db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False,
                               timeout=10)
        conn.row_factory = sqlite3.Row
        # WAL journal_mode may fail on read-only connections for databases
        # not already in WAL mode — ignore errors gracefully.
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.OperationalError:
            pass
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def acquire(self) -> sqlite3.Connection:
        """Acquire a connection from the pool (create if needed, block if full)."""
        try:
            return self._pool.get_nowait()
        except queue.Empty:
            pass
        with self._lock:
            if self._active < self._max_size:
                self._active += 1
                return self._make_conn()
        # Pool is full — wait for one to be released
        return self._pool.get(timeout=30)

    def release(self, conn: sqlite3.Connection) -> None:
        """Return a connection to the pool."""
        try:
            self._pool.put_nowait(conn)
        except queue.Full:
            conn.close()
            with self._lock:
                self._active -= 1

    def close_all(self) -> None:
        """Close all pooled connections (call on shutdown)."""
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except queue.Empty:
                break
        with self._lock:
            self._active = 0


_pool: _ConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> _ConnectionPool:
    """Return the singleton connection pool, creating it if needed."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = _ConnectionPool(_DB_PATH, _POOL_SIZE)
    return _pool


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
    """FastAPI dependency: yield a SQLite connection, close on exit.

    OPT-DB-002: Connections opened with WAL mode, busy_timeout, and
    NORMAL synchronous for resilience under concurrent access.
    OPT-DB-003: Raises HTTP 503 with a friendly message if the database file
    is missing, instead of a cryptic SQLite error.

    Usage in a route::

        from api.database import get_db
        from fastapi import Depends

        @router.get("/example")
        def example(conn=Depends(get_db)):
            ...
    """
    # OPT-DB-003: friendly error on missing database
    if not _DB_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Database not found at '{_DB_PATH}'. "
                "Run 'python build_budget_db.py' to build it."
            ),
        )
    conn = _make_conn(_DB_PATH)
    try:
        yield conn
    finally:
        conn.close()
