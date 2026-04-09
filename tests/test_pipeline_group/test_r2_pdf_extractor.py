"""
Tests for pipeline/r2_pdf_extractor.py

Verifies R-2 cost table parsing, row-label skip logic, organization
inference (filename + page-text fallback), and CLI service filter.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pipeline.r2_pdf_extractor import (
    parse_r2_cost_table,
    infer_org,
    SKIP_LINE_LABELS,
    SKIP_LABEL_PREFIXES,
)


# ── Sample R-2 cost table text ──────────────────────────────────────────────

_SAMPLE_R2_PAGE = """\
UNCLASSIFIED
PE 0602301E: Basic Operational Research
Appropriation: 0400 / Research, Development, Test & Eval, Defense-Wide
COST ($ in Millions)
                        FY 2023   FY 2024   FY 2025
Total Program Element    100.000   110.000   120.000
Project ABC              50.000    55.000    60.000
Project DEF              50.000    55.000    60.000
# FY 2023 Program is from the FY 2023 President's Budget
MDAP/MAIS Code: none
B. Accomplishments/Planned Programs
"""

_SAMPLE_R2_THOUSANDS = """\
PE 0603123A: Advanced Targeting
COST ($ in Thousands)
                        FY 2024   FY 2025
RDT&E Cost              5,000     6,000
"""


# ── parse_r2_cost_table ─────────────────────────────────────────────────────

class TestParseR2CostTable:
    def test_basic_parse(self):
        """Well-formed COST table parses correctly."""
        result = parse_r2_cost_table(_SAMPLE_R2_PAGE)
        assert result is not None
        assert result["pe_number"] == "0602301E"
        assert result["unit_multiplier"] == 1000.0  # millions -> *1000

    def test_skip_total_program_element(self):
        """'Total Program Element' row must be excluded."""
        result = parse_r2_cost_table(_SAMPLE_R2_PAGE)
        assert result is not None
        assert "Total Program Element" not in result["fy_amounts"]

    def test_skip_fy_comment_rows(self):
        """'# FY 2023 ...' comment rows must be excluded."""
        result = parse_r2_cost_table(_SAMPLE_R2_PAGE)
        assert result is not None
        for label in result["fy_amounts"]:
            assert not label.startswith("# FY")

    def test_skip_mdap_rows(self):
        """'MDAP/MAIS Code' metadata rows must be excluded."""
        result = parse_r2_cost_table(_SAMPLE_R2_PAGE)
        assert result is not None
        for label in result["fy_amounts"]:
            assert "MDAP" not in label

    def test_keeps_project_rows(self):
        """Actual project rows like 'Project ABC' are kept."""
        result = parse_r2_cost_table(_SAMPLE_R2_PAGE)
        assert result is not None
        assert "Project ABC" in result["fy_amounts"]
        assert "Project DEF" in result["fy_amounts"]

    def test_thousands_unit(self):
        """COST ($ in Thousands) uses multiplier 1.0."""
        result = parse_r2_cost_table(_SAMPLE_R2_THOUSANDS)
        assert result is not None
        assert result["unit_multiplier"] == 1.0

    def test_no_cost_header_returns_none(self):
        """Text without COST header returns None."""
        assert parse_r2_cost_table("Just some random text without a cost table.") is None

    def test_no_pe_number_returns_none(self):
        """COST header without PE number returns None."""
        text = "COST ($ in Millions)\nFY 2024\nSomething 100.000"
        assert parse_r2_cost_table(text) is None


# ── Skip label constants ─────────────────────────────────────────────────────

class TestSkipLabels:
    def test_total_pe_in_skip_labels(self):
        assert "Total Program Element" in SKIP_LINE_LABELS
        assert "Total PE Cost" in SKIP_LINE_LABELS
        assert "Total Cost" in SKIP_LINE_LABELS

    def test_skip_prefixes(self):
        assert any(p.startswith("# FY") for p in SKIP_LABEL_PREFIXES)
        assert any("MDAP" in p for p in SKIP_LABEL_PREFIXES)
        assert any("Quantity" in p for p in SKIP_LABEL_PREFIXES)


# ── infer_org ───────────────────────────────────────────────────────────────

class TestInferOrg:
    def test_defense_wide_patterns(self):
        assert infer_org("FY2024/Defense_Wide/RDTE_OSD/file.pdf") == "OSD"
        assert infer_org("FY2024/Defense_Wide/RDTE_DARPA/file.pdf") == "DARPA"
        assert infer_org("FY2024/Defense_Wide/RDTE_SOCOM/file.pdf") == "SOCOM"
        assert infer_org("FY2024/Defense_Wide/RDTE_MDA/file.pdf") == "MDA"

    def test_service_patterns(self):
        assert infer_org("FY2024/US_Army/detail/file.pdf") == "Army"
        assert infer_org("FY2024/US_Navy/detail/file.pdf") == "Navy"
        assert infer_org("FY2024/US_Air_Force/detail/file.pdf") == "Air Force"

    def test_page_text_fallback_army(self):
        """When filename has no match, page text 'DEPARTMENT OF THE ARMY' works."""
        result = infer_org(
            "FY2024/other/unknown_file.pdf",
            page_text="UNCLASSIFIED\nDEPARTMENT OF THE ARMY\nExhibit R-2",
        )
        assert result == "Army"

    def test_page_text_fallback_navy(self):
        result = infer_org(
            "FY2024/other/file.pdf",
            page_text="Department of the Navy\nR-2 Budget",
        )
        assert result == "Navy"

    def test_r2_exhibit_header_agency_extraction(self):
        """Modern R-2 header: 'PB 2024 <Agency> Date:' extracts agency."""
        result = infer_org(
            "FY2024/Defense_Wide/other/PB_2024_RDTE_VOL_5.pdf",
            page_text=(
                "UNCLASSIFIED Exhibit R-2, RDT&E Budget Item Justification: "
                "PB 2024 Defense Contract Audit Agency Date: March 2023"
            ),
        )
        assert result == "DCAA"

    def test_r2_header_osd(self):
        result = infer_org(
            "FY2024/Defense_Wide/other/file.pdf",
            page_text=(
                "Exhibit R-2, RDT&E Budget Item Justification: "
                "PB 2024 Office of Secretary Of Defense Date: March 2023"
            ),
        )
        assert result == "OSD"

    def test_r2_header_strips_trailing_justification(self):
        """Agency names sometimes include 'RDT&E Budget Item Justification'."""
        result = infer_org(
            "FY2015/Defense_Wide/other/file.pdf",
            page_text=(
                "Exhibit R-2, RDT&E Budget Item Justification: "
                "PB 2015 DoD Human Resources Activity RDT&E Budget Item "
                "Justification Date: March 2014"
            ),
        )
        assert result == "DHRA"

    def test_older_bmdo_header(self):
        """Older format: 'BMDO RDT&E BUDGET ITEM JUSTIFICATION'."""
        result = infer_org(
            "FY2002/Defense_Wide/detail/vol2_bmdo.pdf",
            page_text="UNCLASSIFIED BMDO RDT&E BUDGET ITEM JUSTIFICATION (R-2 Exhibit)",
        )
        assert result == "MDA"

    def test_unknown_returns_none(self):
        assert infer_org("FY2024/other/mystery.pdf") is None

    def test_unknown_with_no_page_text(self):
        assert infer_org("FY2024/other/mystery.pdf", page_text=None) is None

    def test_filename_takes_precedence_over_page_text(self):
        """Filename match should be returned even if page text says different."""
        result = infer_org(
            "FY2024/US_Army/file.pdf",
            page_text="DEPARTMENT OF THE NAVY\nR-2 Budget",
        )
        assert result == "Army"
