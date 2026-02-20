"""
Tests for utils/pdf_sections.py

Verifies R-2/R-3 narrative section parsing, header detection,
min-length filtering, and the is_narrative_exhibit helper.
"""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.pdf_sections import (
    parse_narrative_sections,
    is_narrative_exhibit,
    extract_sections_for_page,
    SECTION_PATTERN,
)


# ── SECTION_PATTERN regex ─────────────────────────────────────────────────────

class TestSectionPattern:
    def test_matches_accomplishments(self):
        assert SECTION_PATTERN.search("Accomplishments/Planned Programs")

    def test_matches_acquisition_strategy(self):
        assert SECTION_PATTERN.search("Acquisition Strategy")

    def test_matches_performance_metrics(self):
        assert SECTION_PATTERN.search("Performance Metrics")

    def test_matches_mission_description(self):
        assert SECTION_PATTERN.search("Mission Description")

    def test_matches_major_performers(self):
        assert SECTION_PATTERN.search("Major Performers")

    def test_matches_with_colon(self):
        assert SECTION_PATTERN.search("Notes:")

    def test_matches_fy_pattern(self):
        assert SECTION_PATTERN.search("FY2024 Accomplishments")

    def test_matches_numbered_prefix(self):
        assert SECTION_PATTERN.search("A. Accomplishments/Planned Programs")

    def test_no_match_for_random_text(self):
        assert SECTION_PATTERN.search("This is just a random paragraph about budgets.") is None


# ── parse_narrative_sections ──────────────────────────────────────────────────

_SAMPLE_R2_TEXT = """\
Some preamble text about the program element.

Accomplishments/Planned Programs
In FY2024, the program completed Phase II testing of the advanced sensor suite.
Testing demonstrated 95% detection rate under operational conditions.
The program transitioned to LRIP with 12 units delivered.

Acquisition Strategy
The program uses a competitive prototyping approach with two contractors
selected for EMD phase. Full-rate production decision expected in FY2027.

Performance Metrics
Metric 1: Detection range >= 50km (achieved: 62km)
Metric 2: False alarm rate < 5% (achieved: 3.2%)
"""

_SAMPLE_R3_TEXT = """\
Mission Description
Develops next-generation electronic warfare capability for tactical aircraft.

Major Performers
Raytheon Technologies, Tucson AZ
Northrop Grumman, Baltimore MD
"""


class TestParseNarrativeSections:
    def test_extracts_r2_sections(self):
        sections = parse_narrative_sections(_SAMPLE_R2_TEXT)
        headers = [s["header"] for s in sections]
        assert "Accomplishments/Planned Programs" in headers
        assert "Acquisition Strategy" in headers
        assert "Performance Metrics" in headers

    def test_r2_section_bodies(self):
        sections = parse_narrative_sections(_SAMPLE_R2_TEXT)
        by_header = {s["header"]: s["text"] for s in sections}
        assert "Phase II testing" in by_header["Accomplishments/Planned Programs"]
        assert "competitive prototyping" in by_header["Acquisition Strategy"]
        assert "Detection range" in by_header["Performance Metrics"]

    def test_extracts_r3_sections(self):
        sections = parse_narrative_sections(_SAMPLE_R3_TEXT)
        headers = [s["header"] for s in sections]
        assert "Mission Description" in headers
        assert "Major Performers" in headers

    def test_empty_input(self):
        assert parse_narrative_sections("") == []
        assert parse_narrative_sections(None) == []

    def test_no_sections_found(self):
        text = "This is just a plain paragraph with no recognized headers."
        assert parse_narrative_sections(text) == []

    def test_min_section_len_filters_short(self):
        text = """\
Acquisition Strategy
ok

Performance Metrics
This is a sufficiently long section body that should be included in the output list.
"""
        sections = parse_narrative_sections(text, min_section_len=20)
        headers = [s["header"] for s in sections]
        assert "Acquisition Strategy" not in headers  # "ok" is too short
        assert "Performance Metrics" in headers

    def test_min_section_len_zero(self):
        text = """\
Notes:
A

Acquisition Strategy
B
"""
        sections = parse_narrative_sections(text, min_section_len=0)
        assert len(sections) == 2

    def test_exhibit_type_param_accepted(self):
        # exhibit_type is currently unused but should not break anything
        sections = parse_narrative_sections(_SAMPLE_R2_TEXT, exhibit_type="R-2")
        assert len(sections) >= 2


# ── is_narrative_exhibit ──────────────────────────────────────────────────────

class TestIsNarrativeExhibit:
    def test_r2_returns_true(self):
        assert is_narrative_exhibit("R-2") is True
        assert is_narrative_exhibit("r2") is True
        assert is_narrative_exhibit("R2") is True

    def test_r3_returns_true(self):
        assert is_narrative_exhibit("R-3") is True
        assert is_narrative_exhibit("r3") is True

    def test_r2a_returns_true(self):
        assert is_narrative_exhibit("R-2A") is True
        assert is_narrative_exhibit("r2a") is True

    def test_non_narrative_returns_false(self):
        assert is_narrative_exhibit("P-1") is False
        assert is_narrative_exhibit("O-1") is False
        assert is_narrative_exhibit("M-1") is False

    def test_none_and_empty(self):
        assert is_narrative_exhibit(None) is False
        assert is_narrative_exhibit("") is False


# ── extract_sections_for_page ─────────────────────────────────────────────────

class TestExtractSectionsForPage:
    def test_returns_formatted_string(self):
        result = extract_sections_for_page(_SAMPLE_R2_TEXT)
        assert "[Accomplishments/Planned Programs]" in result
        assert "[Acquisition Strategy]" in result
        assert "Phase II testing" in result

    def test_empty_when_no_sections(self):
        result = extract_sections_for_page("Just a random paragraph.")
        assert result == ""

    def test_empty_input(self):
        assert extract_sections_for_page("") == ""
