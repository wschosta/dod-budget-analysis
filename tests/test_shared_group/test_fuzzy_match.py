"""Tests for utils/fuzzy_match.py — fuzzy keyword matching."""

import pytest

from utils.fuzzy_match import (
    levenshtein_distance,
    _max_edit_distance,
    expand_keywords,
    find_matched_keywords_fuzzy,
    find_matched_keywords_simple,
    fuzzy_match_keyword,
)


class TestLevenshteinDistance:
    def test_identical_strings(self):
        assert levenshtein_distance("abc", "abc") == 0

    def test_empty_strings(self):
        assert levenshtein_distance("", "") == 0

    def test_one_empty(self):
        assert levenshtein_distance("abc", "") == 3
        assert levenshtein_distance("", "xyz") == 3

    def test_single_substitution(self):
        assert levenshtein_distance("cat", "bat") == 1

    def test_single_insertion(self):
        assert levenshtein_distance("cat", "cats") == 1

    def test_single_deletion(self):
        assert levenshtein_distance("cats", "cat") == 1

    def test_symmetric(self):
        """Distance should be the same regardless of argument order."""
        assert levenshtein_distance("kitten", "sitting") == levenshtein_distance(
            "sitting", "kitten"
        )

    def test_known_distance(self):
        # "kitten" → "sitting": 3 operations
        assert levenshtein_distance("kitten", "sitting") == 3

    def test_completely_different(self):
        assert levenshtein_distance("abc", "xyz") == 3


class TestMaxEditDistance:
    @pytest.mark.parametrize(
        "keyword, expected",
        [
            ("a", 1),       # 1 char → 1
            ("ab", 1),      # 2 chars → 1
            ("abcd", 1),    # 4 chars → 1 (boundary)
            ("abcde", 2),   # 5 chars → 2 (boundary)
            ("abcdefgh", 2),  # 8 chars → 2 (boundary)
            ("abcdefghi", 3),  # 9 chars → 3 (boundary)
            ("hypersonic", 3),  # 10 chars → 3
        ],
    )
    def test_thresholds(self, keyword, expected):
        assert _max_edit_distance(keyword) == expected


class TestFuzzyMatchKeyword:
    def test_exact_substring(self):
        assert fuzzy_match_keyword("missile", "advanced missile system") == "exact"

    def test_exact_case_insensitive(self):
        assert fuzzy_match_keyword("MISSILE", "advanced missile system") == "exact"

    def test_fuzzy_typo_match(self):
        # "missle" is 1 edit from "missile" (6 chars → max_dist=2)
        assert fuzzy_match_keyword("missle", "advanced missile system") == "fuzzy"

    def test_no_match(self):
        assert fuzzy_match_keyword("submarine", "advanced missile system") is None

    def test_short_keyword_no_fuzzy(self):
        """Keywords < 3 chars should not attempt fuzzy matching."""
        # "ab" is not a substring, and fuzzy is disabled for <3 chars
        assert fuzzy_match_keyword("ab", "xyz foo bar") is None

    def test_short_keyword_exact_still_works(self):
        """Short keywords still match via exact substring."""
        assert fuzzy_match_keyword("ab", "abc def") == "exact"

    def test_token_length_filter(self):
        """Tokens differing too much in length from keyword are skipped."""
        # "ARRW" (4 chars, max_dist=1) should not fuzzy-match "hypersonic" (10 chars)
        assert fuzzy_match_keyword("ARRW", "hypersonic weapons") is None

    def test_whole_text_exact(self):
        """Exact match on entire text."""
        assert fuzzy_match_keyword("test", "test") == "exact"


class TestExpandKeywords:
    def test_basic_expansion(self):
        result = expand_keywords(["UAV"])
        assert "UAV" in result
        # Should include the expansion
        assert any("unmanned" in kw for kw in result)

    def test_deduplication(self):
        result = expand_keywords(["UAV", "uav"])
        # Only one of UAV/uav should appear (case-insensitive dedup)
        lower_list = [kw.lower() for kw in result]
        assert lower_list.count("uav") == 1

    def test_preserves_original_order(self):
        result = expand_keywords(["DARPA", "MDA"])
        # Originals should come before expansions
        darpa_idx = next(i for i, kw in enumerate(result) if kw == "DARPA")
        mda_idx = next(i for i, kw in enumerate(result) if kw == "MDA")
        assert darpa_idx < mda_idx

    def test_unknown_keyword_passthrough(self):
        result = expand_keywords(["xyznotanacronym"])
        assert "xyznotanacronym" in result

    def test_empty_list(self):
        assert expand_keywords([]) == []

    def test_bidirectional_expansion(self):
        """Expanding an expansion should yield the acronym."""
        result = expand_keywords(["unmanned aerial vehicle"])
        lower_result = [kw.lower() for kw in result]
        assert "uav" in lower_result


class TestFindMatchedKeywordsFuzzy:
    def test_exact_match(self):
        results = find_matched_keywords_fuzzy(
            ["advanced missile defense system"],
            ["missile"],
        )
        assert len(results) == 1
        assert results[0]["keyword"] == "missile"
        assert results[0]["match_type"] == "exact"

    def test_acronym_expansion_match(self):
        results = find_matched_keywords_fuzzy(
            ["unmanned aerial vehicle program"],
            ["UAV"],
        )
        # Should match "UAV" via exact substring of "unmanned aerial vehicle"
        assert len(results) >= 1
        types = {r["match_type"] for r in results}
        assert types & {"exact", "acronym"}

    def test_no_match(self):
        results = find_matched_keywords_fuzzy(
            ["completely unrelated text"],
            ["hypersonic"],
        )
        assert len(results) == 0

    def test_empty_text_fields(self):
        results = find_matched_keywords_fuzzy([None, "", None], ["missile"])
        assert len(results) == 0

    def test_use_fuzzy_false_disables_edit_distance(self):
        # "missle" (typo) should NOT match when fuzzy is disabled
        results = find_matched_keywords_fuzzy(
            ["advanced missle system"],
            ["missile"],
            use_fuzzy=False,
        )
        # "missile" is not a substring of "missle", so no match
        assert len(results) == 0

    def test_deduplication(self):
        """Same keyword shouldn't appear twice in results."""
        results = find_matched_keywords_fuzzy(
            ["missile missile missile"],
            ["missile"],
        )
        assert len(results) == 1

    def test_multiple_keywords(self):
        results = find_matched_keywords_fuzzy(
            ["hypersonic missile defense program"],
            ["hypersonic", "missile", "submarine"],
        )
        matched_kws = {r["keyword"] for r in results}
        assert "hypersonic" in matched_kws
        assert "missile" in matched_kws
        assert "submarine" not in matched_kws


class TestFindMatchedKeywordsSimple:
    def test_returns_list_of_strings(self):
        result = find_matched_keywords_simple(
            ["hypersonic weapons"], ["hypersonic"]
        )
        assert isinstance(result, list)
        assert all(isinstance(kw, str) for kw in result)
        assert "hypersonic" in result

    def test_no_match_returns_empty(self):
        result = find_matched_keywords_simple(
            ["unrelated text"], ["hypersonic"]
        )
        assert result == []
