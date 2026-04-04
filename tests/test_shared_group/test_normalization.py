"""Tests for utils/normalization.py — organization name and appropriation code normalization."""

import pytest

from utils.normalization import (
    APPROPRIATION_KEYWORDS,
    ORG_NORMALIZE,
    TITLE_TO_CODE,
    normalize_org_loose,
    normalize_org_name,
    parse_appropriation,
)


# ── normalize_org_name ───────────────────────────────────────────────────────


class TestNormalizeOrgName:
    """Tests for the exact-match organization name normalizer."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("A", "Army"),
            ("N", "Navy"),
            ("F", "Air Force"),
            ("S", "Space Force"),
            ("D", "Defense-Wide"),
            ("M", "Marine Corps"),
            ("J", "Joint Staff"),
        ],
    )
    def test_single_letter_codes(self, raw, expected):
        assert normalize_org_name(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("ARMY", "Army"),
            ("AF", "Air Force"),
            ("NAVY", "Navy"),
            ("USAF", "Air Force"),
            ("USN", "Navy"),
            ("USMC", "Marine Corps"),
            ("DW", "Defense-Wide"),
            ("DEFENSEWIDE", "Defense-Wide"),
        ],
    )
    def test_multi_letter_uppercase(self, raw, expected):
        assert normalize_org_name(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Army", "Army"),
            ("Navy", "Navy"),
            ("Air Force", "Air Force"),
        ],
    )
    def test_title_case_identity(self, raw, expected):
        assert normalize_org_name(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        ["DARPA", "SOCOM", "DISA", "DLA", "MDA", "DHA", "NRO", "NSA"],
    )
    def test_defense_agencies_identity(self, raw):
        assert normalize_org_name(raw) == raw

    def test_ussocom_maps_to_socom(self):
        assert normalize_org_name("USSOCOM") == "SOCOM"

    def test_unknown_returns_unchanged(self):
        assert normalize_org_name("UnknownOrg") == "UnknownOrg"
        assert normalize_org_name("") == ""

    def test_case_sensitive(self):
        """Exact-match normalizer is case-sensitive."""
        assert normalize_org_name("army") == "army"  # no match → returned as-is
        assert normalize_org_name("ARMY") == "Army"   # uppercase variant matches


# ── normalize_org_loose ──────────────────────────────────────────────────────


class TestNormalizeOrgLoose:
    """Tests for the case-insensitive org normalizer with historical aliases."""

    @pytest.mark.parametrize(
        "name, expected",
        [
            ("army", "Army"),
            ("ARMY", "Army"),
            ("Army", "Army"),
            ("  army  ", "Army"),
            ("navy", "Navy"),
            ("usaf", "Air Force"),
        ],
    )
    def test_case_insensitive(self, name, expected):
        assert normalize_org_loose(name) == expected

    @pytest.mark.parametrize(
        "historical, expected",
        [
            ("DSS", "DCSA"),
            ("dss", "DCSA"),
            ("DHP", "DHA"),
            ("dhp", "DHA"),
            ("TMA", "DHA"),
            ("tma", "DHA"),
            ("DPMO", "DPAA"),
            ("dpmo", "DPAA"),
        ],
    )
    def test_historical_renames(self, historical, expected):
        assert normalize_org_loose(historical) == expected

    def test_strips_whitespace(self):
        assert normalize_org_loose("  darpa  ") == "DARPA"

    def test_unknown_returns_unchanged(self):
        assert normalize_org_loose("SomeNewAgency") == "SomeNewAgency"


# ── parse_appropriation ──────────────────────────────────────────────────────


class TestParseAppropriation:
    """Tests for the 3-strategy appropriation parser."""

    # Strategy 0: empty / None input
    @pytest.mark.parametrize("val", [None, "", "   "])
    def test_empty_input_returns_none_none(self, val):
        code, title = parse_appropriation(val)
        assert code is None
        assert title is None

    # Strategy 1: exact title match
    @pytest.mark.parametrize(
        "title, expected_code",
        [
            ("Operation & Maintenance, Army", "O&M"),
            ("Operation & Maintenance, Navy", "O&M"),
            ("RDT&E, Army", "RDTE"),
            ("RDT&E, Defense-Wide", "RDTE"),
            ("Aircraft Procurement, Army", "APAF"),
            ("Shipbuilding & Conversion, Navy", "SCN"),
            ("Defense Health Program", "DHP"),
            ("Mil Con, Army", "MILCON"),
            ("Working Capital Fund, Army", "RFUND"),
            ("Chem Agents & Munitions Destruction", "CHEM"),
        ],
    )
    def test_strategy1_exact_title(self, title, expected_code):
        code, returned_title = parse_appropriation(title)
        assert code == expected_code
        assert returned_title == title

    # Strategy 2: leading numeric code
    @pytest.mark.parametrize(
        "account_title, expected_code, expected_title",
        [
            ("2035 Aircraft Procurement, Army", "2035", "Aircraft Procurement, Army"),
            ("1300 RDT&E, Army", "1300", "RDT&E, Army"),
            ("2100 Military Construction", "2100", "Military Construction"),
        ],
    )
    def test_strategy2_numeric_prefix(self, account_title, expected_code, expected_title):
        code, title = parse_appropriation(account_title)
        assert code == expected_code
        assert title == expected_title

    def test_strategy2_single_token_numeric_no_match(self):
        """A standalone number with no second token doesn't match strategy 2."""
        code, title = parse_appropriation("2035")
        # Falls through to strategy 3 (keyword) or returns None
        assert title is not None

    # Strategy 3: keyword substring match
    @pytest.mark.parametrize(
        "text, expected_code",
        [
            ("Some aircraft procurement budget", "APAF"),
            ("military construction project", "MILCON"),
            ("rdt&e programs", "RDTE"),
            ("operation & maintenance funds", "O&M"),
            ("working capital fund allocation", "RFUND"),
            ("defense health program", "DHP"),
        ],
    )
    def test_strategy3_keyword_match(self, text, expected_code):
        code, title = parse_appropriation(text)
        assert code == expected_code
        assert title == text

    def test_strategy3_case_insensitive(self):
        code, _ = parse_appropriation("MILITARY CONSTRUCTION PROJECT")
        assert code == "MILCON"

    # Strategy priority: exact > numeric > keyword
    def test_exact_takes_priority_over_keyword(self):
        """Exact title match should take priority."""
        # "RDT&E, Army" is in TITLE_TO_CODE
        code, title = parse_appropriation("RDT&E, Army")
        assert code == "RDTE"
        assert title == "RDT&E, Army"

    def test_numeric_takes_priority_over_keyword(self):
        """Leading numeric code takes priority over keyword."""
        code, title = parse_appropriation("9999 Something with procurement")
        assert code == "9999"
        assert title == "Something with procurement"

    # Fallback: no match
    def test_no_match_returns_none_code(self):
        code, title = parse_appropriation("Completely unrecognized title")
        assert code is None
        assert title == "Completely unrecognized title"


# ── Data integrity ───────────────────────────────────────────────────────────


class TestDataIntegrity:
    """Verify mapping data structures are internally consistent."""

    def test_org_normalize_has_expected_services(self):
        values = set(ORG_NORMALIZE.values())
        for svc in ("Army", "Navy", "Air Force", "Marine Corps", "Space Force", "Defense-Wide"):
            assert svc in values

    def test_title_to_code_all_values_are_strings(self):
        for title, code in TITLE_TO_CODE.items():
            assert isinstance(title, str)
            assert isinstance(code, str)
            assert len(code) > 0

    def test_appropriation_keywords_all_lowercase_keys(self):
        for key in APPROPRIATION_KEYWORDS:
            assert key == key.lower(), f"Key should be lowercase: {key!r}"
