"""Tests for fiscal-year-agnostic defaults.

These cover the two helpers introduced to stop the codebase from pinning itself
to a single budget cycle. The concrete failure they guard against: the scheduled
refresh workflow and the search CLI both hardcoded FY2026, so a dormant
repository silently kept requesting a stale year after FY2027 published.
"""

from datetime import date

import pytest

from pipeline.search import _fy_of, _rank_columns
from utils.query import is_allowed_sort
from utils.validation import latest_budget_fiscal_year


class TestLatestBudgetFiscalYear:
    """The PB for FY N+1 publishes during calendar year N, from spring onward."""

    @pytest.mark.parametrize(
        "today,expected",
        [
            (date(2026, 1, 15), 2026),   # before release: newest set is still FY2026
            (date(2026, 2, 28), 2026),   # February slip — books routinely late
            (date(2026, 3, 1), 2027),    # roll-forward boundary
            (date(2026, 8, 10), 2027),   # mid-year: FY2027 books are out
            (date(2026, 12, 31), 2027),  # year end, still FY2027
            (date(2027, 1, 1), 2027),    # new calendar year, before FY2028 drops
            (date(2027, 6, 1), 2028),
        ],
    )
    def test_follows_the_budget_calendar(self, today, expected):
        assert latest_budget_fiscal_year(today) == expected

    def test_defaults_to_today(self):
        # Should track the real clock rather than any baked-in literal.
        assert latest_budget_fiscal_year() == latest_budget_fiscal_year(date.today())

    def test_never_returns_a_hardcoded_2026(self):
        # Regression guard for the original bug: any date well past the FY2026
        # cycle must advance rather than report 2026.
        assert latest_budget_fiscal_year(date(2030, 5, 1)) == 2031


class TestIsAllowedSort:
    def test_accepts_fixed_metadata_columns(self):
        assert is_allowed_sort("id")
        assert is_allowed_sort("organization_name")

    @pytest.mark.parametrize(
        "column",
        [
            "amount_fy2024_actual",
            "amount_fy2026_request",
            "amount_fy2027_request",  # the year that was previously unsortable
            "amount_fy2031_enacted",
        ],
    )
    def test_accepts_any_well_formed_amount_column(self, column):
        assert is_allowed_sort(column)

    @pytest.mark.parametrize(
        "column",
        [
            "amount_fy2027_request; DROP TABLE budget_lines",
            "amount_fy27_request",       # year must be four digits
            "amount_fyABCD_request",
            "amount_fy2027_",            # missing type
            "amount_fy2027_Request",     # uppercase not admitted
            "1=1",
            "",
        ],
    )
    def test_rejects_anything_else(self, column):
        assert not is_allowed_sort(column)


class TestSearchColumnRanking:
    def test_extracts_fiscal_year(self):
        assert _fy_of("amount_fy2027_request") == 2027

    def test_ranks_newest_request_first(self):
        cols = [
            "amount_fy2025_actual",
            "amount_fy2026_enacted",
            "amount_fy2027_request",
            "amount_fy2027_total",
        ]
        assert _rank_columns(cols) == [
            "amount_fy2027_request",
            "amount_fy2027_total",
            "amount_fy2026_enacted",
        ]

    def test_ranking_advances_with_the_schema(self):
        # Adding a newer fiscal year must displace the previous top rank without
        # any change to the ranking code.
        older = _rank_columns(["amount_fy2026_request", "amount_fy2025_enacted"])
        newer = _rank_columns(
            ["amount_fy2026_request", "amount_fy2025_enacted", "amount_fy2027_request"]
        )
        assert older[0] == "amount_fy2026_request"
        assert newer[0] == "amount_fy2027_request"

    def test_handles_empty_schema(self):
        assert _rank_columns([]) == []
