"""
Tests for utils/patterns.py — pre-compiled regex patterns

Validates that all regex patterns match expected inputs and reject invalid ones.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.patterns import (
    DOWNLOADABLE_EXTENSIONS,
    PE_NUMBER,
    FTS5_SPECIAL_CHARS,
    FISCAL_YEAR,
    ACCOUNT_CODE_TITLE,
    WHITESPACE,
    CURRENCY_SYMBOLS,
)


class TestDownloadableExtensions:
    @pytest.mark.parametrize("name", [
        "file.pdf", "file.xlsx", "file.xls", "file.zip", "file.csv",
        "file.PDF", "file.XLSX", "budget.Pdf",
    ])
    def test_matches_valid(self, name):
        assert DOWNLOADABLE_EXTENSIONS.search(name)

    @pytest.mark.parametrize("name", [
        "file.doc", "file.txt", "file.html", "file.json", "no_ext",
    ])
    def test_rejects_invalid(self, name):
        assert not DOWNLOADABLE_EXTENSIONS.search(name)


class TestPeNumber:
    @pytest.mark.parametrize("text,expected", [
        ("0602702E", "0602702E"),
        ("0801273F", "0801273F"),
        ("PE 0603114N funding", "0603114N"),
        ("1234567AB end", "1234567AB"),
    ])
    def test_matches_valid(self, text, expected):
        m = PE_NUMBER.search(text)
        assert m is not None
        assert m.group() == expected

    @pytest.mark.parametrize("text", [
        "12345A",       # too few digits
        "12345678A",    # too many digits
        "1234567",      # no letter suffix
        "1234567ABC",   # too many letters
        "abcdefgH",     # not digits
    ])
    def test_rejects_invalid(self, text):
        assert not PE_NUMBER.search(text)


class TestFts5SpecialChars:
    @pytest.mark.parametrize("char", ['"', '(', ')', '*', ':', '^', '+'])
    def test_finds_special(self, char):
        assert FTS5_SPECIAL_CHARS.search(f"test{char}query")

    def test_no_special(self):
        assert not FTS5_SPECIAL_CHARS.search("normal query text")


class TestFiscalYear:
    @pytest.mark.parametrize("text,expected", [
        ("FY2026", "FY2026"),
        ("FY 2025", "FY 2025"),
        ("fy2024", "fy2024"),
        ("Budget for 2026", "2026"),
        ("FY1999", "FY1999"),       # Navy archive historical
        ("FY 1998", "FY 1998"),     # Navy archive historical
        ("1990", "1990"),           # Lower bound
    ])
    def test_matches_valid(self, text, expected):
        m = FISCAL_YEAR.search(text)
        assert m is not None
        assert m.group() == expected

    def test_no_match(self):
        assert not FISCAL_YEAR.search("FY1899")
        assert not FISCAL_YEAR.search("no year here")


class TestAccountCodeTitle:
    def test_matches_code_title(self):
        m = ACCOUNT_CODE_TITLE.match("1234 Aircraft Procurement, Air Force")
        assert m is not None
        assert m.group(1) == "1234"
        assert m.group(2) == "Aircraft Procurement, Air Force"

    def test_no_match_text_only(self):
        assert not ACCOUNT_CODE_TITLE.match("No leading digits")

    def test_no_match_digits_only(self):
        # Must have space + title after digits
        assert not ACCOUNT_CODE_TITLE.match("1234")


class TestWhitespace:
    def test_collapses_multiple_spaces(self):
        assert WHITESPACE.sub(" ", "hello   world") == "hello world"

    def test_collapses_tabs_newlines(self):
        assert WHITESPACE.sub(" ", "hello\t\n\rworld") == "hello world"

    def test_single_space_unchanged(self):
        assert WHITESPACE.sub(" ", "hello world") == "hello world"


class TestCurrencySymbols:
    @pytest.mark.parametrize("symbol", ["$", "€", "£", "¥", "₹", "₽"])
    def test_strips_symbol(self, symbol):
        assert CURRENCY_SYMBOLS.sub("", f"{symbol}100") == "100"

    def test_no_symbols(self):
        assert CURRENCY_SYMBOLS.sub("", "100.50") == "100.50"
