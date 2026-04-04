"""Tests for utils/dod_acronyms.py — bidirectional acronym lookup."""

import pytest

from utils.dod_acronyms import ACRONYM_LOOKUP, _ACRONYM_PAIRS, build_acronym_lookup


class TestBuildAcronymLookup:
    def test_returns_dict(self):
        lookup = build_acronym_lookup()
        assert isinstance(lookup, dict)

    def test_bidirectional(self):
        """Every acronym pair should be accessible in both directions."""
        lookup = build_acronym_lookup()
        for acronym, expansion in _ACRONYM_PAIRS:
            acr_lower = acronym.lower()
            exp_lower = expansion.lower()
            assert exp_lower in lookup[acr_lower], f"{acronym} → {expansion} missing"
            assert acr_lower in lookup[exp_lower], f"{expansion} → {acronym} missing"

    def test_all_keys_lowercase(self):
        lookup = build_acronym_lookup()
        for key in lookup:
            assert key == key.lower(), f"Key {key!r} is not lowercase"

    def test_values_are_lists(self):
        lookup = build_acronym_lookup()
        for key, val in lookup.items():
            assert isinstance(val, list), f"Value for {key!r} should be list"
            assert len(val) > 0, f"Value for {key!r} should not be empty"


class TestAcronymLookupSingleton:
    def test_singleton_is_populated(self):
        assert len(ACRONYM_LOOKUP) > 0

    def test_singleton_matches_fresh_build(self):
        fresh = build_acronym_lookup()
        assert ACRONYM_LOOKUP == fresh


class TestKnownAcronyms:
    @pytest.mark.parametrize(
        "acronym, expansion_fragment",
        [
            ("uav", "unmanned aerial vehicle"),
            ("icbm", "intercontinental ballistic missile"),
            ("darpa", "defense advanced research projects agency"),
            ("f-35", "joint strike fighter"),
            ("thaad", "terminal high altitude area defense"),
            ("arrw", "air launched rapid response weapon"),
            ("ai", "artificial intelligence"),
        ],
    )
    def test_acronym_to_expansion(self, acronym, expansion_fragment):
        alternatives = ACRONYM_LOOKUP.get(acronym, [])
        assert any(
            expansion_fragment in alt for alt in alternatives
        ), f"{acronym} should map to something containing {expansion_fragment!r}"

    @pytest.mark.parametrize(
        "expansion, expected_acronym",
        [
            ("unmanned aerial vehicle", "uav"),
            ("missile defense agency", "mda"),
            ("artificial intelligence", "ai"),
        ],
    )
    def test_expansion_to_acronym(self, expansion, expected_acronym):
        alternatives = ACRONYM_LOOKUP.get(expansion, [])
        assert expected_acronym in alternatives

    def test_missing_key_returns_none(self):
        assert ACRONYM_LOOKUP.get("nonexistent_key_xyz") is None
