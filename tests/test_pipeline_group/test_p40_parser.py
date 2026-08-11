"""Exhibit P-40 (Budget Line Item Justification) page parsing.

Measured over the corpus: 5,350 pages carry a P-40 header, 1,830 of those
carry a Resource Summary (the rest are narrative continuations of a preceding
P-40), and 1,826 of those expose a twelve-value Net Procurement row.

The unit conversion is the highest-consequence detail in this module — P-40
prints millions and budget_lines stores thousands, so a missed x1000 produces
a number that looks entirely plausible in a chart.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.p40_parser import parse_p40_page  # noqa: E402

# A realistic page, trimmed. Column layout for a PB 2024 book:
#   Prior Years | FY2022 | FY2023 | FY2024 Base | FY2024 OCO | FY2024 Total
#               | FY2025 | FY2026 | FY2027 | FY2028 | To Complete | Total
PAGE = """UNCLASSIFIED
Exhibit P-40, Budget Line Item Justification: PB 2024 Defense Counterintelligence and Security Agency Date: March 2023
Appropriation / Budget Activity / Budget Sub Activity: P-1 Line Item Number / Title:
0300D: Procurement, Defense-Wide / BA 01: Major Equipment / BSA 9: Major 20 / Major Equipment, DCSA
Equipment, DCSA
ID Code (A=Service Ready, B=Not Service Ready): Program Elements for Code B Items: 0901220SE Other Related Program Elements: N/A
Line Item MDAP/MAIS Code: N/A
Prior FY 2024 FY 2024 FY 2024 To
Resource Summary Years FY 2022 FY 2023 Base OCO Total FY 2025 FY 2026 FY 2027 FY 2028 Complete Total
Procurement Quantity (Units in Each) - - - - - - - - - - - -
Gross/Weapon System Cost ($ in Millions) 21.909 3.014 2.346 2.135 - 2.135 2.187 2.233 2.279 2.327 Continuing Continuing
Less PY Advance Procurement ($ in Millions) - - - - - - - - - - - -
Net Procurement (P-1) ($ in Millions) 21.909 3.014 2.346 2.135 - 2.135 2.187 2.233 2.279 2.327 Continuing Continuing
Plus CY Advance Procurement ($ in Millions) - - - - - - - - - - - -
Total Obligation Authority ($ in Millions) 21.909 3.014 2.346 2.135 - 2.135 2.187 2.233 2.279 2.327 Continuing Continuing
(The following Resource Summary rows are for informational purposes only. The corresponding budget requests are documented elsewhere.)
Initial Spares ($ in Millions) - - - 9.999 - 9.999 - - - - - -
Description:
Program Overview:
The agency does things.
"""

CONTINUATION_PAGE = """UNCLASSIFIED
Exhibit P-40, Budget Line Item Justification: PB 2024 DoD Human Resources Activity Date: March 2023
Appropriation / Budget Activity / Budget Sub Activity: P-1 Line Item Number / Title:
0300D: Procurement, Defense-Wide / BA 01: Major Equipment / BSA 20: Major 500 / Personnel Administration
Project: ICM (formerly RAPIDS/CAC). FY 2024 investment supports lifecycle replacement.
"""


class TestHeaderFields:
    def test_extracts_budget_year_and_organization(self):
        r = parse_p40_page(PAGE)
        assert r.fiscal_year == "2024"
        assert r.organization == "Defense Counterintelligence and Security Agency"

    def test_extracts_appropriation_and_budget_activity(self):
        r = parse_p40_page(PAGE)
        assert r.appropriation_code == "0300D"
        assert r.appropriation_title == "Procurement, Defense-Wide"
        assert r.budget_activity == "01"
        assert r.budget_activity_title == "Major Equipment"

    def test_extracts_code_b_program_element(self):
        """Phase 11 mines the same relationship from P-5 headers."""
        assert parse_p40_page(PAGE).pe_number == "0901220SE"

    def test_pe_is_none_when_marked_na(self):
        page = PAGE.replace("Code B Items: 0901220SE", "Code B Items: N/A")
        assert parse_p40_page(page).pe_number is None


class TestResourceSummary:
    def test_converts_millions_to_thousands(self):
        """P-40 prints millions; budget_lines stores thousands."""
        r = parse_p40_page(PAGE)
        assert r.amounts["prior_years"] == pytest.approx(21_909.0)
        assert r.amounts["fy2024_base"] == pytest.approx(2_135.0)

    def test_column_labels_derive_from_the_budget_year(self):
        r = parse_p40_page(PAGE)
        assert set(r.amounts) == {
            "prior_years", "fy2022", "fy2023",
            "fy2024_base", "fy2024_oco", "fy2024_total",
            "fy2025", "fy2026", "fy2027", "fy2028",
            "to_complete", "total",
        }

    def test_dash_is_absent_not_zero(self):
        """"-" means the source printed nothing, which is not the same as 0."""
        assert parse_p40_page(PAGE).amounts["fy2024_oco"] is None

    def test_continuing_is_flagged_not_zeroed(self):
        """"Continuing" means funding runs past the horizon."""
        r = parse_p40_page(PAGE)
        assert r.amounts["to_complete"] is None
        assert "to_complete" in r.continuing_columns
        assert "total" in r.continuing_columns

    def test_reads_net_procurement_not_gross_cost(self):
        """Net Procurement (P-1) is the figure the P-1 exhibit carries.

        Gross cost differs by advance-procurement adjustments; mixing them
        would make the two sources incomparable.
        """
        page = PAGE.replace(
            "Net Procurement (P-1) ($ in Millions) 21.909",
            "Net Procurement (P-1) ($ in Millions) 11.111",
        )
        assert parse_p40_page(page).amounts["prior_years"] == pytest.approx(11_111.0)

    def test_ignores_rows_below_the_informational_note(self):
        """Initial Spares repeats the grid shape but is documented elsewhere."""
        r = parse_p40_page(PAGE)
        # 9.999 appears only in the informational Initial Spares row.
        assert 9_999.0 not in [v for v in r.amounts.values() if v is not None]

    def test_quantities_are_not_scaled(self):
        page = PAGE.replace(
            "Procurement Quantity (Units in Each) - - - - - - - - - - - -",
            "Procurement Quantity (Units in Each) 4 2 1 3 - 3 - - - - - -",
        )
        r = parse_p40_page(page)
        assert r.quantities["prior_years"] == 4
        assert r.quantities["fy2024_base"] == 3


class TestNonParseablePages:
    def test_continuation_page_yields_nothing(self):
        """Same header, narrative only — not an empty record."""
        assert parse_p40_page(CONTINUATION_PAGE) is None

    @pytest.mark.parametrize("text", ["", None, "Exhibit R-2A, RDT&E Project Justification"])
    def test_non_p40_input(self, text):
        assert parse_p40_page(text) is None

    def test_unexpected_column_count_is_reported_not_guessed(self):
        """Navy's SCN book omits the Base/OCO split.

        Mapping its columns onto the standard layout would attribute money to
        the wrong fiscal years, so the record carries a warning and no amounts.
        """
        page = PAGE.replace(
            "Net Procurement (P-1) ($ in Millions) 21.909 3.014 2.346 2.135 - 2.135 2.187 2.233 2.279 2.327 Continuing Continuing",
            "Net Procurement (P-1) ($ in Millions) 21.909 3.014 2.346 2.135 2.187 Continuing Continuing",
        ).replace(
            "Procurement Quantity (Units in Each) - - - - - - - - - - - -",
            "Procurement Quantity (Units in Each) - - - - - - -",
        )
        r = parse_p40_page(page)
        assert r.amounts == {}
        assert any("layout" in w for w in r.warnings)
