"""
Tests for api/routes/search.py — _snippet() helper

Verifies snippet extraction logic for search result highlighting.
"""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.routes.search import _snippet


class TestSnippet:
    def test_match_at_beginning(self):
        text = "Missile defense program for next generation interceptors."
        result = _snippet(text, "missile", max_len=200)
        assert result is not None
        assert "Missile" in result or "missile" in result

    def test_match_in_middle(self):
        text = "X" * 200 + "MATCH TARGET" + "Y" * 200
        result = _snippet(text, "match target", max_len=200)
        assert result is not None
        assert "MATCH TARGET" in result
        assert result.startswith("...")  # start was truncated

    def test_no_match_returns_prefix(self):
        text = "Some text that doesn't match anything."
        result = _snippet(text, "zebra", max_len=200)
        assert result == text  # short text fully returned

    def test_none_text(self):
        assert _snippet(None, "query") is None

    def test_empty_text(self):
        assert _snippet("", "query") is None

    def test_none_query(self):
        assert _snippet("some text", None) is None

    def test_empty_query(self):
        assert _snippet("some text", "") is None

    def test_max_len_respected(self):
        text = "word " * 100  # 500 chars
        result = _snippet(text, "word", max_len=50)
        assert result is not None
        assert len(result) <= 60  # 50 + "..." prefix/suffix

    def test_ellipsis_suffix_for_long_text(self):
        text = "prefix " + "X" * 500
        result = _snippet(text, "prefix", max_len=100)
        assert result is not None
        assert result.endswith("...")
