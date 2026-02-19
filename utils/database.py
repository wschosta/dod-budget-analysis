"""Database utilities for DoD budget tools.

Provides reusable functions for:
- Database schema initialization and pragmas
- Batch insert operations
- Common database queries and aggregations
- Connection lifecycle management

──────────────────────────────────────────────────────────────────────────────
TODOs for this file
──────────────────────────────────────────────────────────────────────────────

# TODO [Group: TIGER] TIGER-011: Add query performance logging — slow query tracking (~2,000 tokens)
"""

import sqlite3
from pathlib import Path
from typing import List, Dict, Any


def init_pragmas(conn: sqlite3.Connection) -> None:
    """Initialize SQLite performance and reliability pragmas.

    These settings optimize for the DoD budget use case:
    - WAL mode for concurrent read/write
    - NORMAL synchronous mode for speed without data loss
    - Memory temp store for speed
    - Larger cache for better performance

    Args:
        conn: SQLite connection to configure
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-64000")


def batch_insert(conn: sqlite3.Connection, query: str, rows: List[tuple],
                 batch_size: int = 1000) -> int:
    """Execute batch insert operations efficiently.

    Inserts rows in batches to balance memory usage and performance.
    Commits after each batch to prevent transaction bloat.

    Args:
        conn: SQLite connection
        query: SQL INSERT query with ? placeholders
        rows: List of tuples to insert
        batch_size: Number of rows per batch (default: 1000)

    Returns:
        Total number of rows inserted

    Example:
        rows = [(1, 'name1'), (2, 'name2'), ...]
        batch_insert(conn, 'INSERT INTO table (id, name) VALUES (?, ?)', rows)
    """
    total_inserted = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        conn.executemany(query, batch)
        conn.commit()
        total_inserted += len(batch)

    return total_inserted


def get_table_count(conn: sqlite3.Connection, table: str) -> int:
    """Get row count for a table.

    Args:
        conn: SQLite connection
        table: Table name

    Returns:
        Number of rows in table
    """
    result = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
    return result['cnt'] if result else 0


def get_table_schema(conn: sqlite3.Connection, table: str) -> List[Dict[str, Any]]:
    """Get column information for a table.

    Args:
        conn: SQLite connection
        table: Table name

    Returns:
        List of column info dicts with keys: name, type, notnull, default_value, pk
    """
    cursor = conn.execute(f"PRAGMA table_info({table})")
    columns = cursor.fetchall()
    return [dict(col) for col in columns]


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Check if a table exists in the database.

    Args:
        conn: SQLite connection
        table: Table name

    Returns:
        True if table exists, False otherwise
    """
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    )
    return cursor.fetchone() is not None


def create_fts5_index(conn: sqlite3.Connection, table: str, fts_table: str,
                      columns: List[str], rebuild: bool = False) -> None:
    """Create or rebuild an FTS5 full-text search index.

    Args:
        conn: SQLite connection
        table: Source table name
        fts_table: FTS5 table name
        columns: List of column names to index
        rebuild: If True, drop and recreate the FTS5 table

    Example:
        create_fts5_index(conn, 'budget_lines', 'budget_lines_fts',
                         ['title', 'description'])
    """
    cols_str = ', '.join(columns)

    if rebuild:
        conn.execute(f"DROP TABLE IF EXISTS {fts_table}")

    # Create FTS5 table if it doesn't exist
    conn.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS {fts_table}
        USING fts5({cols_str}, content={table})
    """)

    # Populate FTS5 table with existing data
    if rebuild:
        conn.execute(f"""
            INSERT INTO {fts_table}(rowid, {cols_str})
            SELECT rowid, {cols_str} FROM {table}
        """)

    conn.commit()


def disable_fts5_triggers(conn: sqlite3.Connection, table: str) -> None:
    """Temporarily disable FTS5 triggers for bulk insert.

    Dropping triggers before bulk insert significantly speeds up ingestion.
    Must call enable_fts5_triggers() and rebuild the FTS5 table afterward.

    Args:
        conn: SQLite connection
        table: Source table name (triggers are named {table}_ai, {table}_ad, {table}_au)
    """
    for suffix in ['ai', 'ad', 'au']:
        conn.execute(f"DROP TRIGGER IF EXISTS {table}_{suffix}")


def enable_fts5_triggers(conn: sqlite3.Connection, table: str, fts_table: str) -> None:
    """Recreate FTS5 triggers after bulk insert.

    Args:
        conn: SQLite connection
        table: Source table name
        fts_table: FTS5 table name
    """
    # Insert trigger
    conn.execute(f"""
        CREATE TRIGGER {table}_ai AFTER INSERT ON {table} BEGIN
            INSERT INTO {fts_table}(rowid, content) VALUES (new.rowid, new.content);
        END
    """)

    # Delete trigger
    conn.execute(f"""
        CREATE TRIGGER {table}_ad AFTER DELETE ON {table} BEGIN
            INSERT INTO {fts_table}({fts_table}, rowid, content)
            VALUES('delete', old.rowid, old.content);
        END
    """)

    # Update trigger
    conn.execute(f"""
        CREATE TRIGGER {table}_au AFTER UPDATE ON {table} BEGIN
            INSERT INTO {fts_table}({fts_table}, rowid, content)
            VALUES('delete', old.rowid, old.content);
            INSERT INTO {fts_table}(rowid, content) VALUES (new.rowid, new.content);
        END
    """)

    conn.commit()


def query_to_dicts(conn: sqlite3.Connection, query: str,
                  params: tuple = ()) -> List[Dict[str, Any]]:
    """Execute query and return results as list of dicts.

    Args:
        conn: SQLite connection (must have row_factory set)
        query: SQL query string
        params: Query parameters tuple

    Returns:
        List of row dicts
    """
    cursor = conn.execute(query, params)
    return [dict(row) for row in cursor.fetchall()]


def vacuum_database(db_path: Path) -> None:
    """Optimize database file by rebuilding and defragmenting.

    Reclaims unused space and optimizes indexes. Should be run after
    large delete operations.

    Args:
        db_path: Path to SQLite database file
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("VACUUM")
    conn.close()


# ── OPT-DBUTIL-001: Dynamic schema introspection ──────────────────────────────

_column_cache: Dict[str, List[str]] = {}


def get_amount_columns(conn: sqlite3.Connection, table: str = "budget_lines") -> List[str]:
    """Return all amount_fy* columns present in the given table's schema.

    Results are cached per connection so repeated calls within a session
    are free.

    Args:
        conn: SQLite connection.
        table: Table name to inspect (default: "budget_lines").

    Returns:
        Sorted list of column names that start with "amount_fy".
    """
    cache_key = f"{id(conn)}:{table}:amount"
    if cache_key in _column_cache:
        return _column_cache[cache_key]
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    cols = sorted(
        r[1] for r in rows if r[1].startswith("amount_fy")
    )
    _column_cache[cache_key] = cols
    return cols


def get_quantity_columns(conn: sqlite3.Connection, table: str = "budget_lines") -> List[str]:
    """Return all quantity_fy* columns present in the given table's schema.

    Args:
        conn: SQLite connection.
        table: Table name to inspect (default: "budget_lines").

    Returns:
        Sorted list of column names that start with "quantity_fy".
    """
    cache_key = f"{id(conn)}:{table}:quantity"
    if cache_key in _column_cache:
        return _column_cache[cache_key]
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    cols = sorted(
        r[1] for r in rows if r[1].startswith("quantity_fy")
    )
    _column_cache[cache_key] = cols
    return cols


# ── OPT-DBUTIL-002: batch_upsert() for incremental updates ───────────────────

def batch_upsert(
    conn: sqlite3.Connection,
    table: str,
    columns: List[str],
    rows: List[tuple],
    conflict_columns: List[str],
    batch_size: int = 1000,
) -> int:
    """Execute batch upsert (INSERT OR REPLACE) operations.

    Uses INSERT ... ON CONFLICT(...) DO UPDATE SET ... semantics so that
    re-ingesting a source file updates existing rows instead of duplicating.

    Args:
        conn: SQLite connection.
        table: Target table name.
        columns: List of column names to insert.
        rows: List of value tuples matching ``columns``.
        conflict_columns: Columns forming the unique constraint to conflict on.
        batch_size: Number of rows per batch (default: 1000).

    Returns:
        Total number of rows upserted.
    """
    if not rows:
        return 0

    cols_str = ", ".join(columns)
    placeholders = ", ".join("?" * len(columns))
    conflict_str = ", ".join(conflict_columns)
    update_set = ", ".join(
        f"{c} = excluded.{c}"
        for c in columns
        if c not in conflict_columns
    )
    sql = (
        f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders}) "
        f"ON CONFLICT({conflict_str}) DO UPDATE SET {update_set}"
    )

    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        conn.executemany(sql, batch)
        conn.commit()
        total += len(batch)
    return total


# ── OPT-DBUTIL-003: QueryBuilder class ────────────────────────────────────────

class QueryBuilder:
    """Fluent SQL SELECT query builder producing safe parameterized queries.

    Builds a SELECT statement step by step.  Column names used in
    ``select()``, ``order_by()``, and ``from_table()`` are passed as-is
    (callers are responsible for validating them against allow-lists).
    WHERE conditions use ``?`` placeholders so values are never interpolated.

    Example::

        sql, params = (
            QueryBuilder()
            .from_table("budget_lines")
            .select(["id", "fiscal_year", "amount_fy2026_request"])
            .where("fiscal_year = ?", "FY2026")
            .where("organization_name LIKE ?", "%Army%")
            .order_by("amount_fy2026_request", "DESC")
            .limit(25)
            .offset(0)
            .build()
        )
    """

    def __init__(self) -> None:
        self._table: str = ""
        self._columns: List[str] = ["*"]
        self._conditions: List[str] = []
        self._params: List[Any] = []
        self._order: str = ""
        self._limit: int | None = None
        self._offset: int | None = None

    def from_table(self, table: str) -> "QueryBuilder":
        """Set the FROM table."""
        self._table = table
        return self

    def select(self, columns: List[str]) -> "QueryBuilder":
        """Set the SELECT column list."""
        self._columns = columns
        return self

    def where(self, condition: str, *values: Any) -> "QueryBuilder":
        """Add a WHERE condition with positional ``?`` placeholders.

        Args:
            condition: SQL condition fragment, e.g. "fiscal_year = ?".
            *values: Values for the ``?`` placeholders in ``condition``.
        """
        self._conditions.append(condition)
        self._params.extend(values)
        return self

    def order_by(self, column: str, direction: str = "ASC") -> "QueryBuilder":
        """Set ORDER BY clause."""
        direction = "DESC" if direction.upper() == "DESC" else "ASC"
        self._order = f"ORDER BY {column} {direction}"
        return self

    def limit(self, n: int) -> "QueryBuilder":
        """Set LIMIT."""
        self._limit = n
        return self

    def offset(self, n: int) -> "QueryBuilder":
        """Set OFFSET."""
        self._offset = n
        return self

    def build(self) -> tuple[str, List[Any]]:
        """Build and return (sql, params) tuple.

        Returns:
            A tuple of (sql_string, params_list).

        Raises:
            ValueError: If no table has been set.
        """
        if not self._table:
            raise ValueError("QueryBuilder: no table set — call .from_table() first")
        cols = ", ".join(self._columns)
        sql = f"SELECT {cols} FROM {self._table}"
        params = list(self._params)
        if self._conditions:
            sql += " WHERE " + " AND ".join(self._conditions)
        if self._order:
            sql += f" {self._order}"
        if self._limit is not None:
            sql += f" LIMIT {self._limit}"
        if self._offset is not None:
            sql += f" OFFSET {self._offset}"
        return sql, params
