"""Recover the P-1 line item number from a P-40 page using word positions.

A P-40 header is two columns printed side by side::

    Appropriation / Budget Activity / Budget Sub Activity:   P-1 Line Item Number / Title:
    0300D: Procurement, Defense-Wide / BA 01: Major ...      20 / Major Equipment, DCSA
    Equipment, DCSA

``page.extract_text()`` flattens those into one line, so the boundary between
"...BSA 9: Major" and "20 / Major Equipment, DCSA" is lost. Recovering it from
the flattened string does not work: the layout varies (``BA 07: <title> / 8081
/ <title>`` carries no BSA segment), line item numbers are alphanumeric
(``CY01``, ``7001SA1000``, ``TITLE3``), and titles themselves contain slashes
(``AC/MC-130J``). Text heuristics plateaued near 94% and — the real problem —
could not distinguish a parsing error from a genuine difference between the
PDF and the Excel P-1 rows.

Word x-coordinates make the split exact instead of inferred: the right-hand
column header ("P-1 Line Item Number / Title:") announces where that column
starts, and every word at or beyond that x belongs to it.

The line item number is the join key for reconciling P-40 against the Excel
P-1 rows, so its accuracy governs whether any of this data can be trusted
enough to ingest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Gap subtracted from the right column's x0 so that a word starting a hair to
# the left of the header still lands in the right column.
_BOUNDARY_SLACK = 2.0

# Vertical distance below the column header within which the value row sits.
# The value is on the next printed line; 40pt covers it plus the wrapped
# continuation line without reaching the ID Code row.
_VALUE_BAND_PT = 40.0

_LINE_ITEM_SPLIT = re.compile(r"^\s*(?P<number>\S+)\s*/\s*(?P<title>.*)$")


@dataclass
class P40HeaderColumns:
    """The right-hand header column of a P-40 page, split by position."""

    line_item: str | None = None
    line_item_title: str | None = None
    raw_right_column: str | None = None


def _find_right_column_anchor(words: list[dict]) -> dict | None:
    """Locate the "P-1 Line Item Number / Title:" header word.

    Matched on the "P-1" token followed by "Line", rather than on the joined
    string, because the words arrive as separate tokens.
    """
    for i, word in enumerate(words):
        if not word["text"].startswith("P-1"):
            continue
        following = words[i + 1]["text"] if i + 1 < len(words) else ""
        if following == "Line":
            return word
    return None


def extract_header_columns(page) -> P40HeaderColumns:
    """Split a P-40 page header by x position and read the line item.

    Args:
        page: A ``pdfplumber`` page.

    Returns:
        A :class:`P40HeaderColumns`. Fields are None when the anchor or the
        value row is absent — a continuation page has neither — so the caller
        can tell "not found" from "found something odd" rather than receiving
        a plausible-looking guess.
    """
    try:
        words = page.extract_words()
    except Exception:  # pragma: no cover - pdfplumber failure on a bad page
        return P40HeaderColumns()

    anchor = _find_right_column_anchor(words)
    if anchor is None:
        return P40HeaderColumns()

    boundary = anchor["x0"] - _BOUNDARY_SLACK
    header_top = anchor["top"]

    # Group the words below the header into printed lines by their y position.
    rows: dict[int, list[dict]] = {}
    for word in words:
        top = word["top"]
        if top <= header_top + 1 or top > header_top + _VALUE_BAND_PT:
            continue
        if word["x0"] < boundary:
            continue
        rows.setdefault(round(top), []).append(word)

    if not rows:
        return P40HeaderColumns()

    # The value sits on the first printed line under the header.
    first_top = min(rows)
    ordered = sorted(rows[first_top], key=lambda w: w["x0"])
    raw = " ".join(w["text"] for w in ordered).strip()
    if not raw:
        return P40HeaderColumns()

    result = P40HeaderColumns(raw_right_column=raw)
    match = _LINE_ITEM_SPLIT.match(raw)
    if match:
        result.line_item = match.group("number").strip().rstrip(":")
        title = match.group("title").strip()
        result.line_item_title = title or None
    return result
