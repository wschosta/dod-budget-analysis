"""Tests for api/routes/keyword_helpers.py — SQL utilities, normalization,
keyword matching, and garbage description filter.
"""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.routes.keyword_helpers import (
    in_clause,
    like_clauses,
    safe_json_list,
    cache_ddl,
    normalize_budget_activity,
    color_of_money,
    find_matched_keywords,
    is_garbage_description,
)


# ── in_clause ────────────────────────────────────────────────────────────────


class TestInClause:
    def test_basic_list(self):
        placeholders, params = in_clause(["a", "b", "c"])
        # Three placeholders separated by commas (exact whitespace may vary)
        assert placeholders.count("?") == 3
        assert params == ["a", "b", "c"]

    def test_single_element(self):
        placeholders, params = in_clause(["x"])
        assert placeholders == "?"
        assert params == ["x"]

    def test_empty_list(self):
        placeholders, params = in_clause([])
        assert placeholders == ""
        assert params == []

    def test_from_set(self):
        placeholders, params = in_clause({"a", "b"})
        assert placeholders.count("?") == 2
        assert len(params) == 2
        assert set(params) == {"a", "b"}


# ── like_clauses ─────────────────────────────────────────────────────────────


class TestLikeClauses:
    def test_single_column_single_keyword(self):
        clause, params = like_clauses(["title"], ["missile"])
        assert clause == "title LIKE ?"
        assert params == ["%missile%"]

    def test_multiple_columns_single_keyword(self):
        clause, params = like_clauses(["title", "desc"], ["cyber"])
        assert "title LIKE ?" in clause
        assert "desc LIKE ?" in clause
        assert "OR" in clause
        assert params == ["%cyber%", "%cyber%"]

    def test_single_column_multiple_keywords(self):
        clause, params = like_clauses(["title"], ["missile", "defense"])
        parts = clause.split(" OR ")
        assert len(parts) == 2
        assert params == ["%missile%", "%defense%"]

    def test_multiple_columns_multiple_keywords(self):
        clause, params = like_clauses(
            ["title", "desc"], ["missile", "defense"]
        )
        parts = clause.split(" OR ")
        assert len(parts) == 4  # 2 cols × 2 keywords
        assert len(params) == 4


# ── safe_json_list ───────────────────────────────────────────────────────────


class TestSafeJsonList:
    def test_valid_json_array(self):
        assert safe_json_list('["a", "b"]') == ["a", "b"]

    def test_already_list(self):
        assert safe_json_list(["x", "y"]) == ["x", "y"]

    def test_none(self):
        assert safe_json_list(None) == []

    def test_empty_string(self):
        assert safe_json_list("") == []

    def test_invalid_json(self):
        assert safe_json_list("not json") == []

    def test_json_object_not_list(self):
        # JSON object should trigger TypeError/decode path
        result = safe_json_list('{"key": "val"}')
        assert isinstance(result, dict)  # json.loads returns dict, not filtered

    def test_json_number(self):
        result = safe_json_list("42")
        assert result == 42  # json.loads returns int


# ── cache_ddl ────────────────────────────────────────────────────────────────


class TestCacheDDL:
    def test_contains_required_columns(self):
        ddl = cache_ddl("test_cache")
        assert "CREATE TABLE IF NOT EXISTS test_cache" in ddl
        assert "pe_number" in ddl
        assert "organization_name" in ddl
        assert "matched_keywords_row" in ddl
        assert "description_text" in ddl
        assert "lineage_note" in ddl

    def test_fy_columns_in_range(self):
        ddl = cache_ddl("cache", fy_start=2024, fy_end=2026)
        assert "fy2024 REAL" in ddl
        assert "fy2024_ref TEXT" in ddl
        assert "fy2025 REAL" in ddl
        assert "fy2026 REAL" in ddl
        # Should not include years outside range
        assert "fy2023" not in ddl
        assert "fy2027" not in ddl

    def test_single_fy(self):
        ddl = cache_ddl("c", fy_start=2026, fy_end=2026)
        assert "fy2026 REAL" in ddl
        assert "fy2025" not in ddl

    def test_default_range(self):
        ddl = cache_ddl("default_cache")
        assert "fy2015 REAL" in ddl
        assert "fy2026 REAL" in ddl


# ── normalize_budget_activity ────────────────────────────────────────────────


class TestNormalizeBudgetActivity:
    def test_known_ba_number(self):
        # BA_CANONICAL maps numeric strings to labels
        result = normalize_budget_activity("01", None)
        assert result.startswith("BA") or "1" in result

    def test_ba_number_with_whitespace(self):
        result = normalize_budget_activity("  01  ", None)
        assert result.startswith("BA") or "1" in result

    def test_falls_back_to_title(self):
        result = normalize_budget_activity("99", "Custom Activity")
        assert result == "Custom Activity"

    def test_title_stripped(self):
        result = normalize_budget_activity(None, "  Some Activity  ")
        assert result == "Some Activity"

    def test_both_none(self):
        assert normalize_budget_activity(None, None) == "Unknown"

    def test_empty_strings(self):
        assert normalize_budget_activity("", "") == "Unknown"


# ── color_of_money ───────────────────────────────────────────────────────────


class TestColorOfMoney:
    def test_rdte_keywords(self):
        assert color_of_money("Research, Development, Test & Evaluation") == "RDT&E"
        assert color_of_money("RDT&E, Army") == "RDT&E"
        assert color_of_money("R&D Special") == "RDT&E"

    def test_procurement(self):
        assert color_of_money("Aircraft Procurement, Army") == "Procurement"
        assert color_of_money("Procurement of Ammunition") == "Procurement"

    def test_om(self):
        assert color_of_money("Operation and Maintenance, Army") == "O&M"
        assert color_of_money("O&M, Navy") == "O&M"

    def test_milcon(self):
        assert color_of_money("Military Construction, Navy") == "MILCON"

    def test_milpers(self):
        assert color_of_money("Military Personnel, Army") == "Military Personnel"

    def test_unknown_returns_original(self):
        assert color_of_money("Special Programs") == "Special Programs"

    def test_none_input(self):
        assert color_of_money(None) == "Unknown"

    def test_empty_string(self):
        assert color_of_money("") == "Unknown"

    def test_case_insensitive(self):
        assert color_of_money("rdt&e, defense-wide") == "RDT&E"
        assert color_of_money("PROCUREMENT OF WEAPONS") == "Procurement"


# ── find_matched_keywords ────────────────────────────────────────────────────


class TestFindMatchedKeywords:
    def test_basic_match(self):
        result = find_matched_keywords(
            ["Hypersonic Missile Program"], ["missile"]
        )
        assert "missile" in result

    def test_no_match(self):
        result = find_matched_keywords(
            ["Aircraft Procurement"], ["submarine"]
        )
        assert result == []

    def test_word_boundary_prevents_partial_match(self):
        # "mach" should NOT match "machine"
        result = find_matched_keywords(["Machine Learning"], ["mach"])
        assert result == []

    def test_word_boundary_allows_exact_match(self):
        result = find_matched_keywords(["Mach number testing"], ["mach"])
        assert "mach" in result

    def test_case_insensitive(self):
        result = find_matched_keywords(
            ["MISSILE Defense System"], ["missile"]
        )
        assert "missile" in result

    def test_multiple_keywords(self):
        result = find_matched_keywords(
            ["Hypersonic Missile Defense"], ["missile", "defense", "submarine"]
        )
        assert "missile" in result
        assert "defense" in result
        assert "submarine" not in result

    def test_multiple_text_fields(self):
        result = find_matched_keywords(
            ["Aircraft Procurement", None, "Missile Systems"],
            ["missile"],
        )
        assert "missile" in result

    def test_all_none_fields(self):
        result = find_matched_keywords([None, None], ["missile"])
        assert result == []

    def test_empty_keyword_skipped(self):
        result = find_matched_keywords(
            ["Missile Program"], ["missile", "", "  "]
        )
        assert result == ["missile"]

    def test_empty_text_fields(self):
        result = find_matched_keywords(["", ""], ["missile"])
        assert result == []


# ── is_garbage_description ───────────────────────────────────────────────────


class TestIsGarbageDescription:
    def test_none_is_garbage(self):
        assert is_garbage_description(None) is True

    def test_empty_is_garbage(self):
        assert is_garbage_description("") is True

    def test_short_text_is_garbage(self):
        assert is_garbage_description("Short text under eighty characters") is True

    def test_long_valid_text_is_not_garbage(self):
        text = "A" * 100  # 100 chars, no garbage markers
        assert is_garbage_description(text) is False

    def test_exhibit_r1_marker(self):
        text = "Exhibit R-1 " + "x" * 100
        assert is_garbage_description(text) is True

    def test_presidents_budget_marker(self):
        text = "President's Budget " + "x" * 100
        assert is_garbage_description(text) is True

    def test_total_obligational_marker(self):
        text = "Total Obligational Authority " + "x" * 100
        assert is_garbage_description(text) is True

    def test_rdte_program_exhibit_marker(self):
        text = "RDT&E PROGRAM EXHIBIT " + "x" * 100
        assert is_garbage_description(text) is True

    def test_valid_description(self):
        desc = (
            "The Cybersecurity Research program develops advanced capabilities "
            "for protecting Department of Defense networks and systems from "
            "sophisticated cyber threats. This includes zero-trust architecture."
        )
        assert is_garbage_description(desc) is False

    def test_marker_after_300_chars_not_detected(self):
        # Marker beyond the first 300 chars shouldn't be flagged
        text = "A" * 301 + "Exhibit R-1"
        assert is_garbage_description(text) is False

    def test_whitespace_stripped(self):
        text = "   " + "A" * 100 + "   "
        assert is_garbage_description(text) is False
