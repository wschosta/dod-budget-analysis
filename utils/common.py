"""Common utility functions used across the DoD budget tools.

──────────────────────────────────────────────────────────────────────────────
TODOs for this file
──────────────────────────────────────────────────────────────────────────────

TODO OPT-UTIL-001 [Group: TIGER] [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Consolidate get_connection() with api/database.py connection logic.
    Both this module and api/database.py create SQLite connections with
    similar pragma settings. Unify into a single create_connection() function:
      1. Add create_connection(path, read_only=False, pragmas=True) here
      2. Accept read_only flag that opens with "?mode=ro" URI
      3. Accept pragmas flag to apply WAL + NORMAL + cache settings
      4. Have api/database.py import and use this function
      5. Have build_budget_db.py use this for its DB connections too
    Acceptance: Single connection factory; all callers use it; tests pass.

TODO OPT-UTIL-002 [Group: TIGER] [Complexity: LOW] [Tokens: ~1000] [User: NO]
    Add elapsed() variants for different display formats.
    elapsed() returns a string like "1m 23s" but some callers need seconds
    (for JSON logging) or milliseconds (for response headers). Steps:
      1. Add elapsed_ms(start) -> int returning milliseconds
      2. Add elapsed_sec(start) -> float returning seconds with 2 decimals
      3. Keep existing elapsed() as the human-readable version
    Acceptance: All three variants available; existing callers unchanged.
"""

import sqlite3
import sys
import time
from pathlib import Path


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


def sanitize_filename(name: str) -> str:
    """Remove invalid filesystem characters and URL query parameters from filename."""
    if "?" in name:
        name = name.split("?")[0]
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    return name


def get_connection(db_path: Path, cached: bool = False) -> sqlite3.Connection:
    """Get or create a SQLite connection.

    Args:
        db_path: Path to the SQLite database file.
        cached: If True, cache and reuse connection. Use cached=True for bulk
                operations (like build_budget_db.py) to avoid repeated open/close
                overhead. Use cached=False (default) for CLI tools doing single
                queries (like search_budget.py).

    Returns:
        sqlite3.Connection with row_factory set to sqlite3.Row for dict-like access.

    Raises:
        SystemExit: If database file does not exist.

    Performance Notes:
        - Cached connections: ~20-30% faster for bulk operations with thousands
          of transactions. Uses check_same_thread=False for thread safety.
        - Non-cached connections: Suitable for one-off queries or CLI tools.
    """
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        print("Run 'python build_budget_db.py' first to build the database.")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
