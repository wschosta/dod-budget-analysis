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
    strip_exhibit_headers,
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


# ── strip_exhibit_headers ────────────────────────────────────────────────────

# Sample R-1 summary page header (Army, FY1998 format)
_ARMY_R1_HEADER = """\
UNCLASSIFIED
Department of the Army
FY 1998/1999 R D T & E Program Exhibit R-1
Appropriation: 2040 A Research Development Test & Eval Army Date: FEB 1997
---------------------------------------------------------------------------------------------------------------------------------
Thousands of Dollars
Program ---------------------------------------------------------S
Line Element e
No Number Item Act FY 1996 FY 1997 FY 1998 FY 1999 c
--- --------- --------- --------- ---------
1 0601101A In-House Laboratory Independent Research 1 13,657 14,393 15,113 15,828 U
2 0601102A Defense Research Sciences 1 207,610 175,274 187,155 192,345 U
"""

# Sample AF P-40 header with DESCRIPTION: marker followed by real content
_AF_P40_HEADER_WITH_CONTENT = """\
UNCLASSIFIED
BUDGET ITEM JUSTIFICATION (EXHIBIT P-40) DATE:
FEBRUARY 1998
APPROP CODE/BA: P-1 NOMENCLATURE:
OPAF/ELECTRONICS MILSATCOM SPACE
FY 1996 FY 1997 FY1998 FY1999
QUANTITY
COST
$ $58,422 $18,034 $28,233 $44,541
(in thousands)
DESCRIPTION:
MILSATCOM is a set of joint service satellite communications systems that provides
a broad range of satellite communication capabilities to meet essential strategic and
tactical requirements for the Department of Defense.
"""

# Navy OCR-split header with real content after
_NAVY_OCR_HEADER = """\
UN CLASSIFIED
FY 1998/1999 RDT&E,N BUDGET ITEM JUSTIFICATION SHEET DATE: February 1997
BUDGET ACTIVITY: 2 PROGRAM ELEMENT: 0602314N
PROGRAM ELEMENT TITLE: Undersea Warfare Surveillance Technology
Development of optical depth and heading sensors to support low cost all-optical
array designs both for towed and deployable applications.
"""


class TestStripExhibitHeaders:
    def test_full_r1_header_returns_empty(self):
        """A complete R-1 exhibit header block should yield empty string."""
        result = strip_exhibit_headers(_ARMY_R1_HEADER)
        assert result == ""

    def test_empty_input(self):
        assert strip_exhibit_headers("") == ""
        assert strip_exhibit_headers(None) == ""

    def test_plain_narrative_unchanged(self):
        """Normal narrative text should pass through with content preserved."""
        text = (
            "This program develops advanced targeting algorithms for "
            "precision-guided munitions. The FY2024 effort focuses on "
            "integration testing with existing fire control systems."
        )
        result = strip_exhibit_headers(text)
        assert len(result) > 50
        assert "targeting algorithms" in result

    def test_af_p40_keeps_description_content(self):
        """AF P-40 header should be stripped, keeping DESCRIPTION: content."""
        result = strip_exhibit_headers(_AF_P40_HEADER_WITH_CONTENT)
        assert result  # not empty
        assert "MILSATCOM" in result
        assert "satellite communication" in result

    def test_ocr_split_unclassified_stripped(self):
        """OCR-split 'UN CLASSIFIED' variant should be handled."""
        result = strip_exhibit_headers(_NAVY_OCR_HEADER)
        assert result  # not empty (has real content after header)
        assert "optical depth" in result

    def test_department_variants(self):
        """Department of the Army/Navy/Air Force headers all recognized."""
        for dept in ["Army", "Navy", "Air Force"]:
            header = (
                f"UNCLASSIFIED\n"
                f"Department of the {dept}\n"
                f"FY 2013 R D T & E Program Exhibit R-1\n"
                f"Appropriation: 2040\n"
                f"{'=' * 60}\n"
                f"Thousands of Dollars\n"
            )
            result = strip_exhibit_headers(header)
            assert result == "", f"Department of the {dept} header not fully stripped"

    def test_standalone_unclassified_stripped(self):
        """Standalone UNCLASSIFIED line is stripped."""
        text = "UNCLASSIFIED\nThis is real program description content here."
        result = strip_exhibit_headers(text)
        assert "UNCLASSIFIED" not in result
        assert "real program description" in result

    def test_short_residual_returns_empty(self):
        """Text shorter than 25 chars after stripping returns empty."""
        text = "UNCLASSIFIED\nTechnology\n\nTechnology"
        result = strip_exhibit_headers(text)
        assert result == ""
