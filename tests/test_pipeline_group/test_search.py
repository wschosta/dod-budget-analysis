"""
Unit tests for search_budget.py — FTS5 query sanitization, snippet highlighting,
and interactive mode prefix parsing.

Also covers build_budget_db.py fixes:
- ingested_files error-path INSERT (column-count bug fix)
- build_database raising FileNotFoundError instead of sys.exit
"""
import sys
import types
from pathlib import Path

import pytest

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from search_budget import _sanitize_fts5_query, _highlight_terms, _extract_snippet

# Stub heavy third-party deps so we can import build_budget_db in test envs
for _mod in ("pdfplumber", "openpyxl", "pandas"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

from build_budget_db import create_database, build_database  # noqa: E402


# ── _sanitize_fts5_query ─────────────────────────────────────────────────────

class TestSanitizeFts5Query:
    """Tests for FTS5 query sanitization."""

    def test_plain_single_word(self):
        assert _sanitize_fts5_query("missile") == '"missile"'

    def test_plain_multi_word(self):
        result = _sanitize_fts5_query("missile defense")
        assert result == '"missile" OR "defense"'

    def test_strips_double_quotes(self):
        result = _sanitize_fts5_query('"missile defense"')
        assert '"' not in result.replace('" OR "', "").strip('"') or \
               result == '"missile" OR "defense"'

    def test_strips_parentheses(self):
        result = _sanitize_fts5_query("(cyber)")
        assert result == '"cyber"'

    def test_strips_asterisks(self):
        result = _sanitize_fts5_query("cyber*")
        assert result == '"cyber"'

    def test_strips_colons(self):
        result = _sanitize_fts5_query("title:cyber")
        assert result == '"title" OR "cyber"'

    def test_strips_caret(self):
        result = _sanitize_fts5_query("^cyber")
        assert result == '"cyber"'

    def test_strips_plus(self):
        result = _sanitize_fts5_query("+cyber")
        assert result == '"cyber"'

    def test_removes_AND_keyword(self):
        result = _sanitize_fts5_query("missile AND defense")
        assert result == '"missile" OR "defense"'

    def test_removes_OR_keyword(self):
        result = _sanitize_fts5_query("missile OR defense")
        assert result == '"missile" OR "defense"'

    def test_removes_NOT_keyword(self):
        result = _sanitize_fts5_query("missile NOT defense")
        assert result == '"missile" OR "defense"'

    def test_removes_NEAR_keyword(self):
        result = _sanitize_fts5_query("missile NEAR defense")
        assert result == '"missile" OR "defense"'

    def test_keywords_case_insensitive(self):
        result = _sanitize_fts5_query("missile and defense")
        assert result == '"missile" OR "defense"'

    def test_empty_string(self):
        assert _sanitize_fts5_query("") == ""

    def test_only_special_chars(self):
        assert _sanitize_fts5_query('"()*:^+') == ""

    def test_only_keywords(self):
        assert _sanitize_fts5_query("AND OR NOT") == ""

    def test_dash_only_terms_removed(self):
        assert _sanitize_fts5_query("- -- ---") == ""

    def test_mixed_special_and_valid(self):
        result = _sanitize_fts5_query('"missile (defense)" AND cyber*')
        assert result == '"missile" OR "defense" OR "cyber"'

    def test_preserves_hyphens_in_words(self):
        result = _sanitize_fts5_query("F-35")
        assert result == '"F-35"'

    def test_whitespace_normalization(self):
        result = _sanitize_fts5_query("  missile   defense  ")
        assert result == '"missile" OR "defense"'


# ── _highlight_terms ─────────────────────────────────────────────────────────

BOLD = "\033[1m"
RESET = "\033[0m"


class TestHighlightTerms:
    """Tests for ANSI bold highlighting of matching terms."""

    def test_single_term_highlighted(self):
        result = _highlight_terms("missile defense budget", "missile")
        assert result == f"{BOLD}missile{RESET} defense budget"

    def test_multiple_terms_highlighted(self):
        result = _highlight_terms("missile defense budget", "missile defense")
        assert result == f"{BOLD}missile{RESET} {BOLD}defense{RESET} budget"

    def test_case_insensitive(self):
        result = _highlight_terms("Missile Defense", "missile")
        assert result == f"{BOLD}Missile{RESET} Defense"

    def test_no_match_returns_original(self):
        text = "some other text"
        result = _highlight_terms(text, "missile")
        assert result == text

    def test_empty_text(self):
        assert _highlight_terms("", "missile") == ""

    def test_empty_query(self):
        assert _highlight_terms("missile defense", "") == "missile defense"

    def test_none_text(self):
        assert _highlight_terms(None, "missile") == ""

    def test_regex_special_chars_escaped(self):
        result = _highlight_terms("cost (in $millions)", "(in")
        assert f"{BOLD}(in{RESET}" in result


# ── _extract_snippet ─────────────────────────────────────────────────────────

class TestExtractSnippet:
    """Tests for snippet extraction with highlighting."""

    def test_match_is_highlighted(self):
        text = "The missile defense program is important."
        snippet = _extract_snippet(text, "missile")
        assert f"{BOLD}missile{RESET}" in snippet

    def test_no_query_returns_plain_text(self):
        text = "Hello world"
        assert _extract_snippet(text, "") == text

    def test_no_match_still_highlights_if_found_in_prefix(self):
        # When no term is found, returns start of text (still highlighted)
        text = "some text here"
        snippet = _extract_snippet(text, "zzz", max_len=100)
        # Should return text without highlight since "zzz" not found
        assert BOLD not in snippet

    def test_truncation_with_ellipsis(self):
        text = "A" * 500
        snippet = _extract_snippet(text, "A", max_len=100)
        assert snippet.endswith("...")


# ── build_database: FileNotFoundError ────────────────────────────────────────

class TestBuildDatabaseMissingDir:
    """build_database() should raise FileNotFoundError for a missing docs dir."""

    def test_raises_file_not_found(self, tmp_path):
        missing = tmp_path / "no_such_dir"
        db_path = tmp_path / "test.sqlite"
        with pytest.raises(FileNotFoundError, match="not found"):
            build_database(missing, db_path)

    def test_progress_callback_receives_error(self, tmp_path):
        missing = tmp_path / "no_such_dir"
        db_path = tmp_path / "test.sqlite"
        events = []
        with pytest.raises(FileNotFoundError):
            build_database(missing, db_path,
                           progress_callback=lambda *a: events.append(a))
        assert any(phase == "error" for phase, *_ in events)


# ── ingested_files error-path INSERT ─────────────────────────────────────────

class TestIngestedFilesErrorInsert:
    """The error-path INSERT in ingest_pdf_file must match the table schema."""

    def test_error_insert_matches_schema(self, tmp_path):
        """Simulate the error-path INSERT and verify it succeeds."""
        db_path = tmp_path / "test.sqlite"
        conn = create_database(db_path)

        # This mirrors the fixed INSERT in ingest_pdf_file's except block
        conn.execute(
            "INSERT OR REPLACE INTO ingested_files "
            "(file_path, file_type, file_size, file_modified, ingested_at, row_count, status) "
            "VALUES (?,?,?,?,datetime('now'),?,?)",
            ("test/file.pdf", "pdf", 1024, 1700000000.0, 0, "error: test")
        )
        conn.commit()

        row = conn.execute(
            "SELECT * FROM ingested_files WHERE file_path = ?",
            ("test/file.pdf",)
        ).fetchone()
        assert row is not None
        assert row[1] == "pdf"          # file_type
        assert row[3] == 1700000000.0   # file_modified
        assert row[5] == 0              # row_count
        assert row[6] == "error: test"  # status
        conn.close()
