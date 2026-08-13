"""Database size reporting must account for the write-ahead log.

The builder logs the database size at the end of a run, reading it from the
main file while the connection is still open in WAL mode. Recent writes live
in the ``-wal`` sidecar until a checkpoint, so a freshly built database reports
close to nothing: the first full build of this project logged
"Database: dod_budget.sqlite (0.0 MB)" for 119 MB of data it had just written.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from utils.database import database_size_mb  # noqa: E402


def test_missing_database_is_zero_not_an_error(tmp_path):
    """Called while logging a summary; it must not raise on a bad path."""
    assert database_size_mb(tmp_path / "nope.sqlite") == 0.0


def test_counts_a_plain_database(tmp_path):
    db = tmp_path / "plain.sqlite"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, blob TEXT)")
    conn.executemany(
        "INSERT INTO t (blob) VALUES (?)", [("x" * 500,) for _ in range(500)]
    )
    conn.commit()
    conn.close()
    assert database_size_mb(db) > 0


def test_counts_data_still_sitting_in_the_wal(tmp_path):
    """The regression: uncheckpointed writes must not read as an empty file.

    With the connection open in WAL mode and no checkpoint, the main file can
    be a fraction of the real size while the -wal holds the rest.
    """
    db = tmp_path / "wal.sqlite"
    # isolation_level=None (autocommit) so the writes land in the WAL rather
    # than sitting in an open transaction that never reaches it.
    conn = sqlite3.connect(str(db), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    # SQLite auto-checkpoints every 1000 pages, which would fold the WAL back
    # into the main file and hide the very condition under test. A long build
    # reaches the end of its run with plenty still uncheckpointed.
    conn.execute("PRAGMA wal_autocheckpoint=0")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, blob TEXT)")
    conn.executemany(
        "INSERT INTO t (blob) VALUES (?)", [("x" * 1000,) for _ in range(2000)]
    )
    # Everything must be observed while the connection is open: closing it
    # checkpoints the WAL into the main file and removes the sidecar, which is
    # exactly the state the builder is *not* in when it logs its summary.
    main_only = (tmp_path / "wal.sqlite").stat().st_size / (1024 * 1024)
    reported = database_size_mb(db)
    wal_existed = (tmp_path / "wal.sqlite-wal").exists()
    conn.close()

    assert wal_existed, "test did not produce a WAL; nothing was exercised"
    assert reported > main_only, (
        f"reported {reported:.2f} MB ignores the WAL "
        f"(main file alone is {main_only:.2f} MB)"
    )


def test_accepts_a_string_path(tmp_path):
    db = tmp_path / "str.sqlite"
    sqlite3.connect(str(db)).close()
    assert database_size_mb(str(db)) >= 0
