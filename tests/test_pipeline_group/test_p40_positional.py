"""Positional recovery of the P-1 line item number from a P-40 page header.

The header is two columns printed side by side, and extract_text() flattens
them into one string. Recovering the boundary from that string does not work:
the layout varies (Navy lines carry no BSA segment), line item numbers are
alphanumeric (CY01, 7001SA1000, TITLE3), and titles contain slashes
(AC/MC-130J). Text heuristics plateaued at ~94% and could not tell a parsing
error from a genuine PDF/Excel difference.

Word x-coordinates make the split exact. Validated over the corpus: 1,830
P-40 pages, 1,812 line items matching the Excel P-1 rows (99.0%), zero
extraction failures. The 18 non-matches carry real titles ("Pollution Control
Equipment") and are source differences, not parse errors.

These tests use a stub page rather than a PDF fixture so the geometry under
test is explicit and readable.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.p40_positional import extract_header_columns  # noqa: E402


def word(text: str, x0: float, top: float) -> dict:
    return {"text": text, "x0": x0, "x1": x0 + 5 * len(text), "top": top, "bottom": top + 9}


class StubPage:
    """Minimal stand-in for a pdfplumber page."""

    def __init__(self, words: list[dict], raises: bool = False):
        self._words = words
        self._raises = raises

    def extract_words(self) -> list[dict]:
        if self._raises:
            raise RuntimeError("pdfplumber failure")
        return self._words


# Geometry mirroring a real page: the right column begins at x=398.
def _standard_page(right_line: list[tuple[str, float]]) -> StubPage:
    words = [
        # Left column header
        word("Appropriation", 40, 92), word("/", 110, 92), word("Budget", 120, 92),
        # Right column header — the anchor
        word("P-1", 398, 92), word("Line", 420, 92), word("Item", 445, 92),
        word("Number", 470, 92), word("/", 515, 92), word("Title:", 525, 92),
        # Left column value row
        word("0300D:", 40, 104), word("Procurement,", 80, 104),
        word("BSA", 300, 104), word("9:", 325, 104), word("Major", 345, 104),
        # Left column wrapped continuation
        word("Equipment,", 40, 116), word("DCSA", 100, 116),
    ]
    words += [word(t, x, 104) for t, x in right_line]
    return StubPage(words)


class TestLineItemExtraction:
    def test_splits_the_right_column_by_position(self):
        page = _standard_page([("20", 398), ("/", 415), ("Major", 425),
                               ("Equipment,", 465), ("DCSA", 520)])
        result = extract_header_columns(page)
        assert result.line_item == "20"
        assert result.line_item_title == "Major Equipment, DCSA"

    def test_left_column_text_never_leaks_into_the_line_item(self):
        """The flattened text ends "...BSA 9: Major 20 / ..." — "Major" must not win."""
        page = _standard_page([("20", 398), ("/", 415), ("Major", 425)])
        assert extract_header_columns(page).line_item == "20"

    @pytest.mark.parametrize("number", ["CY01", "7001SA1000", "TITLE3", "0201ARMOWT"])
    def test_alphanumeric_line_item_numbers(self, number):
        """Digit-only patterns truncated these; positional splitting does not."""
        page = _standard_page([(number, 398), ("/", 460), ("Something", 470)])
        assert extract_header_columns(page).line_item == number

    def test_title_containing_a_slash_is_kept_whole(self):
        """"AC/MC-130J" defeated last-slash heuristics."""
        page = _standard_page([("2012C130J", 398), ("/", 455), ("AC/MC-130J", 465)])
        result = extract_header_columns(page)
        assert result.line_item == "2012C130J"
        assert result.line_item_title == "AC/MC-130J"

    def test_wrapped_left_column_line_is_not_read_as_the_value(self):
        """The BSA title wraps onto the next line, entirely in the left column."""
        page = _standard_page([("20", 398), ("/", 415), ("Major", 425)])
        assert extract_header_columns(page).line_item_title == "Major"


class TestAbsentOrUnreadable:
    def test_no_anchor_returns_empty(self):
        """A continuation page has no "P-1 Line Item Number" header."""
        page = StubPage([word("Project:", 40, 92), word("ICM", 90, 92)])
        result = extract_header_columns(page)
        assert result.line_item is None and result.raw_right_column is None

    def test_anchor_without_a_value_row_returns_empty(self):
        page = StubPage([
            word("P-1", 398, 92), word("Line", 420, 92), word("Item", 445, 92),
        ])
        assert extract_header_columns(page).line_item is None

    def test_p1_token_not_followed_by_line_is_not_an_anchor(self):
        """"P-1" appears in "Net Procurement (P-1)" too."""
        page = StubPage([
            word("Net", 40, 92), word("Procurement", 70, 92), word("(P-1)", 140, 92),
            word("21.909", 200, 92),
        ])
        assert extract_header_columns(page).line_item is None

    def test_extract_words_failure_is_contained(self):
        """A malformed page must not abort a corpus-wide run."""
        assert extract_header_columns(StubPage([], raises=True)).line_item is None

    def test_right_column_without_a_slash_reports_raw_text(self):
        """Report what was seen rather than inventing a split."""
        page = _standard_page([("SomethingOdd", 398)])
        result = extract_header_columns(page)
        assert result.raw_right_column == "SomethingOdd"
        assert result.line_item is None
