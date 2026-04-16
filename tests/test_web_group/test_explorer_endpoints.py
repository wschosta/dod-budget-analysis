"""Tests for api/routes/explorer.py — helper functions and endpoint logic.

Covers: _keyword_set_id, _cache_table_name, _parse_keywords, _parse_extra_pes,
_resolve_keyword_set, _ensure_meta_table, _prune_old_caches, _prune_stale_progress,
and the explorer API endpoints (build, status, list, download, presets).
"""
import hashlib
import sqlite3
import sys
import time
import types
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Stub optional deps
for _mod in ("pdfplumber", "openpyxl", "pandas"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

from fastapi.testclient import TestClient  # noqa: E402

from api.routes.explorer import (
    _keyword_set_id,
    _cache_table_name,
    _parse_keywords,
    _parse_extra_pes,
    _resolve_keyword_set,
    _ensure_meta_table,
    _prune_old_caches,
    _prune_stale_progress,
    _extract_column_value,
    _build_progress,
    _build_lock,
    MAX_KEYWORDS,
    MAX_CACHE_TABLES,
    _HYPERSONICS_KEYWORDS,
    _EXTRA_PES,
)


# ── _keyword_set_id ──────────────────────────────────────────────────────────


class TestKeywordSetId:
    def test_deterministic(self):
        """Same keywords produce same ID."""
        id1 = _keyword_set_id(["missile", "defense"])
        id2 = _keyword_set_id(["missile", "defense"])
        assert id1 == id2

    def test_order_independent(self):
        """Keyword order doesn't affect the ID."""
        id1 = _keyword_set_id(["missile", "defense"])
        id2 = _keyword_set_id(["defense", "missile"])
        assert id1 == id2

    def test_case_independent(self):
        """Case doesn't affect the ID."""
        id1 = _keyword_set_id(["MISSILE"])
        id2 = _keyword_set_id(["missile"])
        assert id1 == id2

    def test_whitespace_stripped(self):
        id1 = _keyword_set_id(["  missile  "])
        id2 = _keyword_set_id(["missile"])
        assert id1 == id2

    def test_different_keywords_different_ids(self):
        id1 = _keyword_set_id(["missile"])
        id2 = _keyword_set_id(["defense"])
        assert id1 != id2

    def test_extra_pes_changes_id(self):
        id_no_pes = _keyword_set_id(["missile"])
        id_with_pes = _keyword_set_id(["missile"], ["0602120A"])
        assert id_no_pes != id_with_pes

    def test_extra_pes_order_independent(self):
        id1 = _keyword_set_id(["missile"], ["0602120A", "0603285E"])
        id2 = _keyword_set_id(["missile"], ["0603285E", "0602120A"])
        assert id1 == id2

    def test_returns_hex_string(self):
        result = _keyword_set_id(["test"])
        assert len(result) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in result)

    def test_empty_keywords_filtered(self):
        id1 = _keyword_set_id(["missile", "", "  "])
        id2 = _keyword_set_id(["missile"])
        assert id1 == id2

    def test_deduplicates_keywords(self):
        id1 = _keyword_set_id(["missile", "missile", "missile"])
        id2 = _keyword_set_id(["missile"])
        assert id1 == id2


# ── _cache_table_name ────────────────────────────────────────────────────────


class TestCacheTableName:
    def test_format(self):
        name = _cache_table_name("abc123def456ghi789")
        assert name == "explorer_cache_abc123def456ghi7"

    def test_truncates_to_16_chars(self):
        name = _cache_table_name("a" * 64)
        assert name == "explorer_cache_" + "a" * 16


# ── _parse_keywords ──────────────────────────────────────────────────────────


class TestParseKeywords:
    def test_basic_parsing(self):
        result = _parse_keywords("missile, defense, hypersonic")
        assert result == ["missile", "defense", "hypersonic"]

    def test_strips_whitespace(self):
        result = _parse_keywords("  missile  ,  defense  ")
        assert result == ["missile", "defense"]

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="No keywords"):
            _parse_keywords("")

    def test_none_raises(self):
        with pytest.raises(ValueError, match="No keywords"):
            _parse_keywords(None)

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="No keywords"):
            _parse_keywords("   ")

    def test_too_many_keywords_raises(self):
        kws = ", ".join(f"keyword{i}" for i in range(MAX_KEYWORDS + 1))
        with pytest.raises(ValueError, match="Too many keywords"):
            _parse_keywords(kws)

    def test_too_short_keyword_raises(self):
        with pytest.raises(ValueError, match="too short"):
            _parse_keywords("a")

    def test_too_long_keyword_raises(self):
        with pytest.raises(ValueError, match="too long"):
            _parse_keywords("x" * 101)

    def test_invalid_characters_raises(self):
        with pytest.raises(ValueError, match="invalid characters"):
            _parse_keywords("missile; DROP TABLE")

    def test_valid_special_chars(self):
        # Hyphens, slashes, ampersands, dots are allowed
        result = _parse_keywords("R&D, boost-glide, SM-6/Block")
        assert len(result) == 3

    def test_single_keyword(self):
        result = _parse_keywords("hypersonic")
        assert result == ["hypersonic"]

    def test_empty_segments_filtered(self):
        result = _parse_keywords("missile,,defense,,,")
        assert result == ["missile", "defense"]


# ── _parse_extra_pes ─────────────────────────────────────────────────────────


class TestParseExtraPes:
    def test_basic(self):
        result = _parse_extra_pes("0602120A, 0603285E")
        assert result == ["0602120A", "0603285E"]

    def test_uppercased(self):
        result = _parse_extra_pes("0602120a")
        assert result == ["0602120A"]

    def test_empty_string(self):
        assert _parse_extra_pes("") == []

    def test_none(self):
        assert _parse_extra_pes(None) == []

    def test_strips_whitespace(self):
        result = _parse_extra_pes("  0602120A  ")
        assert result == ["0602120A"]


# ── _resolve_keyword_set ─────────────────────────────────────────────────────


class TestResolveKeywordSet:
    def test_returns_tuple_of_three(self):
        keywords, pes, kw_id = _resolve_keyword_set("missile, defense")
        assert keywords == ["missile", "defense"]
        assert pes is None
        assert isinstance(kw_id, str)

    def test_with_extra_pes(self):
        keywords, pes, kw_id = _resolve_keyword_set("missile", "0602120A")
        assert keywords == ["missile"]
        assert pes == ["0602120A"]

    def test_invalid_keywords_raises(self):
        with pytest.raises(ValueError):
            _resolve_keyword_set("")


# ── _ensure_meta_table ───────────────────────────────────────────────────────


class TestEnsureMetaTable:
    def test_creates_table(self):
        conn = sqlite3.connect(":memory:")
        _ensure_meta_table(conn)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert any("explorer_cache_meta" in t[0] for t in tables)
        conn.close()

    def test_idempotent(self):
        conn = sqlite3.connect(":memory:")
        _ensure_meta_table(conn)
        _ensure_meta_table(conn)  # Should not raise
        conn.close()


# ── _prune_old_caches ────────────────────────────────────────────────────────


class TestPruneOldCaches:
    def test_no_pruning_below_limit(self):
        conn = sqlite3.connect(":memory:")
        _ensure_meta_table(conn)
        # Insert a few entries below MAX_CACHE_TABLES
        for i in range(3):
            table_name = f"explorer_cache_test{i}"
            conn.execute(f"CREATE TABLE {table_name} (id INTEGER)")
            conn.execute(
                "INSERT INTO explorer_cache_meta VALUES (?, ?, ?, ?, ?, ?)",
                (f"id{i}", "[]", table_name, time.time(), time.time() - i, 10),
            )
        conn.commit()
        _prune_old_caches(conn)
        count = conn.execute("SELECT COUNT(*) FROM explorer_cache_meta").fetchone()[0]
        assert count == 3
        conn.close()

    def test_prunes_oldest_when_over_limit(self):
        conn = sqlite3.connect(":memory:")
        _ensure_meta_table(conn)
        # Create MAX_CACHE_TABLES + 2 entries
        for i in range(MAX_CACHE_TABLES + 2):
            table_name = f"explorer_cache_test{i:03d}"
            conn.execute(f"CREATE TABLE {table_name} (id INTEGER)")
            conn.execute(
                "INSERT INTO explorer_cache_meta VALUES (?, ?, ?, ?, ?, ?)",
                (f"id{i:03d}", "[]", table_name, time.time(),
                 time.time() - i,  # older items have lower last_accessed_at
                 10),
            )
        conn.commit()
        _prune_old_caches(conn)
        count = conn.execute("SELECT COUNT(*) FROM explorer_cache_meta").fetchone()[0]
        assert count == MAX_CACHE_TABLES
        conn.close()


# ── _prune_stale_progress ───────────────────────────────────────────────────


class TestPruneStaleProgress:
    def test_removes_old_finished_entries(self):
        with _build_lock:
            _build_progress["old_ready"] = {
                "state": "ready", "_ts": time.time() - 100_000,
            }
            _build_progress["old_error"] = {
                "state": "error", "_ts": time.time() - 100_000,
            }
            _build_progress["recent_ready"] = {
                "state": "ready", "_ts": time.time(),
            }
            _build_progress["still_building"] = {
                "state": "building",
            }
        _prune_stale_progress()
        assert "old_ready" not in _build_progress
        assert "old_error" not in _build_progress
        assert "recent_ready" in _build_progress
        assert "still_building" in _build_progress
        # Clean up
        _build_progress.clear()


# ── Explorer API endpoints ──────────────────────────────────────────────────


@pytest.fixture()
def explorer_client(tmp_path):
    """TestClient with a database that has budget_lines + pe_index."""
    db = tmp_path / "explorer_test.sqlite"
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            pe_number TEXT,
            line_item_title TEXT,
            account_title TEXT,
            budget_activity_title TEXT,
            organization_name TEXT,
            exhibit_type TEXT,
            fiscal_year TEXT
        );
        CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY);
        CREATE TABLE ingested_files (
            file_path TEXT PRIMARY KEY, file_type TEXT,
            file_size INTEGER, file_modified REAL, ingested_at TEXT,
            row_count INTEGER, status TEXT
        );
        CREATE TABLE pe_index (
            pe_number TEXT PRIMARY KEY,
            display_title TEXT,
            organization_name TEXT
        );
        INSERT INTO budget_lines (pe_number, line_item_title, account_title,
            budget_activity_title, organization_name, exhibit_type, fiscal_year)
        VALUES ('0602120A', 'Missile Defense', 'Weapons', 'BA 2', 'Army', 'r1', 'FY 2026');
    """)
    conn.close()

    from api.app import create_app
    app = create_app(db_path=db)
    return TestClient(app)


class TestExplorerBuildEndpoint:
    def test_build_validates_empty_keywords(self, explorer_client):
        resp = explorer_client.post("/api/v1/explorer/build?keywords=")
        assert resp.status_code == 200
        body = resp.json()
        assert "error" in body

    def test_build_validates_invalid_chars(self, explorer_client):
        resp = explorer_client.post(
            "/api/v1/explorer/build?keywords=missile%3B+DROP+TABLE"
        )
        body = resp.json()
        assert "error" in body


class TestExplorerStatusEndpoint:
    def test_status_unknown_kw_id(self, explorer_client):
        resp = explorer_client.get(
            "/api/v1/explorer/status?keywords=nonexistentkeyword"
        )
        assert resp.status_code == 200
        body = resp.json()
        # Should return not_started or similar state
        assert "state" in body

    def test_status_requires_keywords(self, explorer_client):
        resp = explorer_client.get("/api/v1/explorer/status")
        # Should fail validation (missing required param)
        assert resp.status_code == 422


class TestExplorerPresetsEndpoint:
    def test_hypersonics_preset(self, explorer_client):
        resp = explorer_client.get("/api/v1/explorer/presets/hypersonics")
        assert resp.status_code == 200
        body = resp.json()
        assert "keywords" in body
        assert "extra_pes" in body
        assert len(body["keywords"]) > 0

    def test_unknown_preset_returns_error(self, explorer_client):
        resp = explorer_client.get("/api/v1/explorer/presets/nonexistent")
        assert resp.status_code == 200
        body = resp.json()
        assert "error" in body
        assert "available" in body


class TestExplorerDescEndpoint:
    def test_missing_pe_returns_empty(self, explorer_client):
        resp = explorer_client.get(
            "/api/v1/explorer/desc/9999999X?keywords=missile"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "description" in body

    def test_invalid_keywords_returns_null(self, explorer_client):
        resp = explorer_client.get("/api/v1/explorer/desc/0602120A?keywords=")
        assert resp.status_code == 200
        body = resp.json()
        assert body["description"] is None
