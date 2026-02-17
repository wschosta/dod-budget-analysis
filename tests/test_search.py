"""
Unit tests for search_budget.py — FTS5 query sanitization.
"""
import sys
from pathlib import Path

import pytest

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from search_budget import _sanitize_fts5_query


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
