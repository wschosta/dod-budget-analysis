"""
Tests for utils/strings.py — edge cases not covered by test_utils.py

Covers NaN/Inf handling, multi-currency, and FTS5 edge cases.
"""
import math
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.strings import safe_float, normalize_whitespace, sanitize_fts5_query


class TestSafeFloatEdgeCases:
    def test_nan_string(self):
        result = safe_float("nan")
        assert math.isnan(result)

    def test_inf_string(self):
        result = safe_float("inf")
        assert math.isinf(result)

    def test_negative_inf(self):
        result = safe_float("-inf")
        assert math.isinf(result) and result < 0

    def test_float_nan_passthrough(self):
        result = safe_float(float("nan"))
        assert math.isnan(result)

    def test_float_inf_passthrough(self):
        result = safe_float(float("inf"))
        assert math.isinf(result)

    def test_whitespace_only(self):
        assert safe_float("   ") == 0.0

    def test_currency_euro(self):
        assert safe_float("€1,234.56") == 1234.56

    def test_currency_pound(self):
        assert safe_float("£500") == 500.0

    def test_currency_yen(self):
        assert safe_float("¥10000") == 10000.0

    def test_multiple_commas(self):
        assert safe_float("1,234,567.89") == 1234567.89

    def test_negative_with_currency(self):
        assert safe_float("$-500.00") == -500.0

    def test_parenthetical_negative(self):
        # Parenthetical negatives are accounting notation, not handled
        result = safe_float("(500)")
        assert result == 0.0  # Not parsed as -500

    def test_custom_default(self):
        assert safe_float(None, default=-999.0) == -999.0
        assert safe_float("invalid", default=42.0) == 42.0

    def test_boolean_input(self):
        # bool is subclass of int
        assert safe_float(True) == 1.0
        assert safe_float(False) == 0.0

    def test_very_large_number(self):
        assert safe_float("999999999999999") == 999999999999999.0

    def test_scientific_notation(self):
        assert safe_float("1.5e6") == 1500000.0
        assert safe_float("2.3E-4") == 0.00023


class TestNormalizeWhitespaceEdgeCases:
    def test_only_whitespace(self):
        assert normalize_whitespace("   \t\n  ") == ""

    def test_mixed_unicode_spaces(self):
        # \u00a0 is non-breaking space
        result = normalize_whitespace("hello\u00a0world")
        assert "hello" in result
        assert "world" in result

    def test_very_long_string(self):
        text = "word " * 10000
        result = normalize_whitespace(text)
        assert len(result) == len("word " * 10000) - 1  # trailing space stripped


class TestSanitizeFts5EdgeCases:
    def test_all_special_chars(self):
        result = sanitize_fts5_query('"()*:^+')
        assert result == ""  # All characters stripped, no terms left

    def test_mixed_keywords_and_terms(self):
        result = sanitize_fts5_query("army AND navy OR air NOT force")
        assert '"army"' in result
        assert '"navy"' in result
        assert '"air"' in result
        assert '"force"' in result
        assert "AND" not in result.replace('"', "")

    def test_single_term(self):
        result = sanitize_fts5_query("procurement")
        assert result == '"procurement"'

    def test_dashes_stripped(self):
        result = sanitize_fts5_query("---")
        assert result == ""

    def test_preserves_alphanumeric(self):
        result = sanitize_fts5_query("FY2026 budget")
        assert '"FY2026"' in result
        assert '"budget"' in result

    def test_near_keyword_removed(self):
        result = sanitize_fts5_query("NEAR missile")
        assert "NEAR" not in result.replace('"', "")
        assert '"missile"' in result
