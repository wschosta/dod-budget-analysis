"""
Tests for utils/database.py

Verifies database utilities: pragmas, batch inserts, table introspection,
FTS5 index creation/triggers, and query helpers.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.database import (
    init_pragmas,
    batch_insert,
    get_table_count,
    get_table_schema,
    table_exists,
    create_fts5_index,
    disable_fts5_triggers,
    enable_fts5_triggers,
    query_to_dicts,
    vacuum_database,
)


@pytest.fixture()
def db():
    """In-memory SQLite database with row_factory."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, value REAL)")
    conn.commit()
    yield conn
    conn.close()


# ── init_pragmas ──────────────────────────────────────────────────────────────

class TestInitPragmas:
    def test_sets_wal_mode(self, tmp_path):
        # WAL only works on file-based DBs
        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        init_pragmas(conn)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        conn.close()

    def test_sets_synchronous(self, db):
        init_pragmas(db)
        sync = db.execute("PRAGMA synchronous").fetchone()[0]
        assert sync == 1  # NORMAL = 1

    def test_sets_temp_store(self, db):
        init_pragmas(db)
        temp = db.execute("PRAGMA temp_store").fetchone()[0]
        assert temp == 2  # MEMORY = 2

    def test_sets_cache_size(self, db):
        init_pragmas(db)
        cache = db.execute("PRAGMA cache_size").fetchone()[0]
        assert cache == -64000


# ── batch_insert ──────────────────────────────────────────────────────────────

class TestBatchInsert:
    def test_inserts_all_rows(self, db):
        rows = [(i, f"item{i}", float(i)) for i in range(10)]
        count = batch_insert(db, "INSERT INTO items (id, name, value) VALUES (?, ?, ?)", rows)
        assert count == 10
        assert db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 10

    def test_empty_rows(self, db):
        count = batch_insert(db, "INSERT INTO items (id, name, value) VALUES (?, ?, ?)", [])
        assert count == 0

    def test_batch_size_smaller_than_total(self, db):
        rows = [(i, f"item{i}", float(i)) for i in range(25)]
        count = batch_insert(
            db, "INSERT INTO items (id, name, value) VALUES (?, ?, ?)",
            rows, batch_size=7,
        )
        assert count == 25
        assert db.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 25

    def test_single_row(self, db):
        count = batch_insert(
            db, "INSERT INTO items (id, name, value) VALUES (?, ?, ?)",
            [(1, "solo", 1.0)],
        )
        assert count == 1


# ── get_table_count ───────────────────────────────────────────────────────────

class TestGetTableCount:
    def test_empty_table(self, db):
        assert get_table_count(db, "items") == 0

    def test_populated_table(self, db):
        db.execute("INSERT INTO items (name, value) VALUES ('a', 1.0)")
        db.execute("INSERT INTO items (name, value) VALUES ('b', 2.0)")
        db.commit()
        assert get_table_count(db, "items") == 2


# ── get_table_schema ─────────────────────────────────────────────────────────

class TestGetTableSchema:
    def test_returns_column_info(self, db):
        schema = get_table_schema(db, "items")
        col_names = [c["name"] for c in schema]
        assert "id" in col_names
        assert "name" in col_names
        assert "value" in col_names

    def test_column_types(self, db):
        schema = get_table_schema(db, "items")
        by_name = {c["name"]: c for c in schema}
        assert by_name["id"]["type"] == "INTEGER"
        assert by_name["name"]["type"] == "TEXT"
        assert by_name["value"]["type"] == "REAL"


# ── table_exists ──────────────────────────────────────────────────────────────

class TestTableExists:
    def test_existing_table(self, db):
        assert table_exists(db, "items") is True

    def test_nonexistent_table(self, db):
        assert table_exists(db, "nonexistent") is False


# ── create_fts5_index ─────────────────────────────────────────────────────────

class TestCreateFts5Index:
    def test_creates_fts_table(self, db):
        db.execute("CREATE TABLE docs (id INTEGER PRIMARY KEY, content TEXT)")
        db.commit()
        create_fts5_index(db, "docs", "docs_fts", ["content"])
        assert table_exists(db, "docs_fts")

    def test_rebuild_repopulates(self, db):
        db.execute("CREATE TABLE docs (id INTEGER PRIMARY KEY, content TEXT)")
        db.execute("INSERT INTO docs (content) VALUES ('hello world')")
        db.execute("INSERT INTO docs (content) VALUES ('foo bar')")
        db.commit()
        create_fts5_index(db, "docs", "docs_fts", ["content"], rebuild=True)
        # FTS5 search should find the content
        results = db.execute(
            "SELECT * FROM docs_fts WHERE docs_fts MATCH 'hello'"
        ).fetchall()
        assert len(results) == 1


# ── disable_fts5_triggers / enable_fts5_triggers ─────────────────────────────

class TestFts5Triggers:
    def test_disable_drops_triggers(self, db):
        db.execute("CREATE TABLE docs (id INTEGER PRIMARY KEY, content TEXT)")
        # Create dummy triggers to confirm they get dropped
        for suffix in ["ai", "ad", "au"]:
            db.execute(
                f"CREATE TRIGGER docs_{suffix} AFTER INSERT ON docs "
                f"BEGIN SELECT 1; END"
            )
        db.commit()
        disable_fts5_triggers(db, "docs")
        triggers = db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'docs_%'"
        ).fetchall()
        assert len(triggers) == 0

    def test_enable_creates_triggers(self, db):
        db.execute("CREATE TABLE docs (id INTEGER PRIMARY KEY, content TEXT)")
        create_fts5_index(db, "docs", "docs_fts", ["content"])
        enable_fts5_triggers(db, "docs", "docs_fts")
        triggers = db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'docs_%'"
        ).fetchall()
        trigger_names = {t[0] for t in triggers}
        assert "docs_ai" in trigger_names
        assert "docs_ad" in trigger_names
        assert "docs_au" in trigger_names


# ── query_to_dicts ────────────────────────────────────────────────────────────

class TestQueryToDicts:
    def test_returns_list_of_dicts(self, db):
        db.execute("INSERT INTO items (name, value) VALUES ('a', 1.0)")
        db.execute("INSERT INTO items (name, value) VALUES ('b', 2.0)")
        db.commit()
        results = query_to_dicts(db, "SELECT name, value FROM items ORDER BY name")
        assert len(results) == 2
        assert results[0]["name"] == "a"
        assert results[1]["value"] == 2.0

    def test_empty_result(self, db):
        results = query_to_dicts(db, "SELECT * FROM items")
        assert results == []

    def test_with_params(self, db):
        db.execute("INSERT INTO items (name, value) VALUES ('target', 99.0)")
        db.commit()
        results = query_to_dicts(db, "SELECT name FROM items WHERE value = ?", (99.0,))
        assert len(results) == 1
        assert results[0]["name"] == "target"


# ── vacuum_database ───────────────────────────────────────────────────────────

class TestVacuumDatabase:
    def test_vacuum_runs(self, tmp_path):
        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (x INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.commit()
        conn.close()
        # Should not raise
        vacuum_database(db_path)
