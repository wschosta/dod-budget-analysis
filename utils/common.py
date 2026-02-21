"""Common utility functions used across the DoD budget tools."""

import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def format_bytes(b: int) -> str:
    """Format bytes into human-readable size string.

    Examples:
        512 KB, 1.5 MB, 2.34 GB
    """
    if b < 1024 * 1024:
        return f"{b / 1024:.0f} KB"
    if b < 1024 * 1024 * 1024:
        return f"{b / (1024 * 1024):.1f} MB"
    return f"{b / (1024 * 1024 * 1024):.2f} GB"


def elapsed(start_time: float) -> str:
    """Format elapsed time from start_time to now as human-readable string.

    Examples:
        30s, 2m 15s, 1h 05m 30s
    """
    secs = int(time.time() - start_time)
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


def elapsed_ms(start_time: float) -> int:
    """Return elapsed time in milliseconds since start_time.

    Args:
        start_time: Start time as returned by time.monotonic() or time.time().

    Returns:
        Elapsed milliseconds as an integer.
    """
    return int((time.monotonic() - start_time) * 1000)


def elapsed_sec(start_time: float) -> float:
    """Return elapsed time in seconds since start_time, rounded to 2 decimals.

    Args:
        start_time: Start time as returned by time.monotonic() or time.time().

    Returns:
        Elapsed seconds as a float with 2 decimal places.
    """
    return round(time.monotonic() - start_time, 2)


def sanitize_filename(name: str) -> str:
    """Remove invalid filesystem characters and URL query parameters from filename."""
    if "?" in name:
        name = name.split("?")[0]
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    return name


def create_connection(
    db_path: Path,
    read_only: bool = False,
    pragmas: bool = True,
) -> sqlite3.Connection:
    """Create a SQLite connection with optional read-only mode and pragmas.

    This is the unified connection factory used by all modules. It replaces
    the separate connection logic in utils/common.py and api/database.py.

    Args:
        db_path: Path to the SQLite database file.
        read_only: If True, open in read-only URI mode. Prevents accidental
                   writes and may enable SQLite read-path optimizations.
        pragmas: If True, apply WAL + NORMAL synchronous + cache settings.

    Returns:
        sqlite3.Connection with row_factory set to sqlite3.Row.

    Raises:
        FileNotFoundError: If the database file does not exist.
    """
    if not db_path.exists():
        raise FileNotFoundError(
            f"Database not found: {db_path}. "
            "Run 'python build_budget_db.py' to build it."
        )
    if read_only:
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if pragmas:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-64000")
    return conn


def get_connection(db_path: Path, cached: bool = False) -> sqlite3.Connection:
    """Get or create a SQLite connection.

    Args:
        db_path: Path to the SQLite database file.
        cached: Unused legacy parameter (kept for backward compatibility).

    Returns:
        sqlite3.Connection with row_factory set to sqlite3.Row.

    Raises:
        FileNotFoundError: If database file does not exist.
    """
    if not db_path.exists():
        raise FileNotFoundError(
            f"Database not found: {db_path}. "
            "Run 'python build_budget_db.py' first to build the database."
        )

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
