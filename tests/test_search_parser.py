"""Tests for HAWK-4: Advanced search query parser.

Tests the structured query parsing in utils/search_parser.py.
"""

import pytest

from utils.search_parser import ParsedQuery, parse_search_query, apply_parsed_filters


class TestParseSearchQuery:
    """Tests for the parse_search_query function."""

    def test_plain_text_query(self):
        """Plain text query has no filters, produces FTS5 query."""
        result = parse_search_query("stealth aircraft")
        assert result.filters == {}
        assert result.text_query == "stealth aircraft"
        assert result.fts5_query  # Should produce FTS5 terms
        assert result.has_text
        assert not result.has_filters

    def test_pe_filter(self):
        """pe: prefix extracts PE number filter."""
        result = parse_search_query("pe:0602120A")
        assert result.filters == {"pe_number": ["0602120A"]}
        assert result.text_query == ""
        assert not result.has_text
        assert result.has_filters

    def test_service_filter(self):
        """service: prefix extracts service filter."""
        result = parse_search_query("service:army")
        assert result.filters == {"service": ["army"]}

    def test_exhibit_filter(self):
        """exhibit: prefix extracts exhibit type filter."""
        result = parse_search_query("exhibit:R-2")
        assert result.filters == {"exhibit_type": ["R-2"]}

    def test_fiscal_year_filter(self):
        """fy: prefix extracts fiscal year filter."""
        result = parse_search_query("fy:2026")
        assert result.filters == {"fiscal_year": ["2026"]}

    def test_year_alias(self):
        """year: is an alias for fy:."""
        result = parse_search_query("year:2025")
        assert result.filters == {"fiscal_year": ["2025"]}

    def test_tag_filter(self):
        """tag: prefix extracts tag filter."""
        result = parse_search_query("tag:stealth")
        assert result.filters == {"tag": ["stealth"]}

    def test_org_alias(self):
        """org: is an alias for service:."""
        result = parse_search_query("org:navy")
        assert result.filters == {"service": ["navy"]}

    def test_approp_filter(self):
        """approp: prefix extracts appropriation_code filter."""
        result = parse_search_query("approp:3600")
        assert result.filters == {"appropriation_code": ["3600"]}

    def test_combined_filters_and_text(self):
        """Multiple filters plus free-text works together."""
        result = parse_search_query("pe:0602120A service:army stealth aircraft")
        assert result.filters == {
            "pe_number": ["0602120A"],
            "service": ["army"],
        }
        assert "stealth" in result.text_query
        assert "aircraft" in result.text_query
        assert result.has_filters
        assert result.has_text

    def test_quoted_phrase(self):
        """Quoted phrases are preserved as exact phrases."""
        result = parse_search_query('"stealth aircraft"')
        assert '"stealth aircraft"' in result.text_query

    def test_quoted_phrase_with_filters(self):
        """Quoted phrases work alongside structured filters."""
        result = parse_search_query('pe:0602120A "stealth aircraft"')
        assert result.filters == {"pe_number": ["0602120A"]}
        assert '"stealth aircraft"' in result.text_query

    def test_multiple_filters_same_type(self):
        """Multiple values for the same filter key accumulate in a list."""
        result = parse_search_query("service:army service:navy")
        assert result.filters == {"service": ["army", "navy"]}

    def test_amount_greater_than(self):
        """amount>N extracts min_amount filter."""
        result = parse_search_query("amount>1000")
        assert result.amount_filters == [(">", 1000.0)]
        assert result.has_filters

    def test_amount_less_than(self):
        """amount<N extracts max_amount filter."""
        result = parse_search_query("amount<5000")
        assert result.amount_filters == [("<", 5000.0)]

    def test_amount_greater_equal(self):
        """amount>=N extracts filter with >= operator."""
        result = parse_search_query("amount>=500.5")
        assert result.amount_filters == [(">=", 500.5)]

    def test_amount_less_equal(self):
        """amount<=N extracts filter with <= operator."""
        result = parse_search_query("amount<=2000")
        assert result.amount_filters == [("<=", 2000.0)]

    def test_amount_with_text(self):
        """Amount filter works alongside text search."""
        result = parse_search_query("amount>1000 radar systems")
        assert result.amount_filters == [(">", 1000.0)]
        assert "radar" in result.text_query
        assert "systems" in result.text_query

    def test_empty_query(self):
        """Empty query returns empty ParsedQuery."""
        result = parse_search_query("")
        assert result.filters == {}
        assert result.text_query == ""
        assert result.fts5_query == ""
        assert not result.has_text
        assert not result.has_filters

    def test_none_query(self):
        """None query returns empty ParsedQuery."""
        result = parse_search_query(None)
        assert result.filters == {}

    def test_whitespace_only(self):
        """Whitespace-only query returns empty ParsedQuery."""
        result = parse_search_query("   ")
        assert not result.has_text
        assert not result.has_filters

    def test_case_insensitive_prefix(self):
        """Filter prefixes are case-insensitive."""
        result = parse_search_query("PE:0602120A SERVICE:army")
        assert result.filters == {
            "pe_number": ["0602120A"],
            "service": ["army"],
        }

    def test_raw_query_preserved(self):
        """The original query string is preserved in raw_query."""
        q = 'pe:0602120A "stealth aircraft"'
        result = parse_search_query(q)
        assert result.raw_query == q

    def test_quoted_filter_value(self):
        """Filter values can be quoted to include spaces."""
        result = parse_search_query('service:"Air Force"')
        assert result.filters == {"service": ["Air Force"]}

    def test_complex_query(self):
        """Complex query with multiple filter types, amounts, and text."""
        result = parse_search_query(
            'pe:0602120A service:army fy:2026 amount>500 "stealth aircraft" radar'
        )
        assert result.filters == {
            "pe_number": ["0602120A"],
            "service": ["army"],
            "fiscal_year": ["2026"],
        }
        assert result.amount_filters == [(">", 500.0)]
        assert '"stealth aircraft"' in result.text_query
        assert "radar" in result.text_query


class TestApplyParsedFilters:
    """Tests for the apply_parsed_filters helper."""

    def test_basic_filters(self):
        """Filters are converted to build_where_clause kwargs."""
        parsed = parse_search_query("pe:0602120A service:army")
        params = apply_parsed_filters(parsed)
        assert params == {
            "pe_number": ["0602120A"],
            "service": ["army"],
        }

    def test_merge_with_base_params(self):
        """Parsed filters merge with existing base parameters."""
        parsed = parse_search_query("pe:0602120A")
        params = apply_parsed_filters(parsed, {"service": ["navy"]})
        assert params == {
            "pe_number": ["0602120A"],
            "service": ["navy"],
        }

    def test_amount_to_min_max(self):
        """Amount filters convert to min_amount/max_amount."""
        parsed = parse_search_query("amount>1000 amount<5000")
        params = apply_parsed_filters(parsed)
        assert params["min_amount"] == 1000.0
        assert params["max_amount"] == 5000.0

    def test_amount_keeps_largest_min(self):
        """When multiple > filters exist, the largest min is kept."""
        parsed = parse_search_query("amount>500 amount>1000")
        params = apply_parsed_filters(parsed)
        assert params["min_amount"] == 1000.0

    def test_amount_keeps_smallest_max(self):
        """When multiple < filters exist, the smallest max is kept."""
        parsed = parse_search_query("amount<5000 amount<3000")
        params = apply_parsed_filters(parsed)
        assert params["max_amount"] == 3000.0

    def test_empty_parsed_query(self):
        """Empty parsed query produces empty params."""
        parsed = parse_search_query("")
        params = apply_parsed_filters(parsed)
        assert params == {}
