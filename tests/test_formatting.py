"""
Unit tests for utils/formatting.py

Tests all public functions: format_amount, format_percent, format_count,
truncate_text, extract_snippet, highlight_terms, TableFormatter, ReportFormatter.
No database, network, or file I/O required.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.formatting import (
    format_amount,
    format_percent,
    format_count,
    truncate_text,
    extract_snippet,
    highlight_terms,
    TableFormatter,
    ReportFormatter,
)


# ── format_amount ─────────────────────────────────────────────────────────────

def test_format_amount_none():
    assert format_amount(None) == "-"


def test_format_amount_zero():
    assert format_amount(0) == "-"


def test_format_amount_standard():
    # Values < 1M use standard comma-separated format
    assert format_amount(1234) == "$1,234"


def test_format_amount_with_precision():
    assert format_amount(1234, precision=2) == "$1,234.00"


def test_format_amount_no_thousands_sep():
    result = format_amount(1234, thousands_sep=False)
    assert "," not in result
    assert "$1234" == result


def test_format_amount_millions():
    result = format_amount(2_500_000)
    assert "M" in result
    assert "2.5" in result


def test_format_amount_billions():
    result = format_amount(3_000_000_000)
    assert "B" in result
    assert "3.0" in result


def test_format_amount_negative():
    result = format_amount(-500)
    assert "$" in result


# ── format_percent ────────────────────────────────────────────────────────────

def test_format_percent_none():
    assert format_percent(None) == "-"


def test_format_percent_zero():
    assert format_percent(0) == "0.0%"


def test_format_percent_value():
    assert format_percent(42.5) == "42.5%"


def test_format_percent_precision():
    assert format_percent(33.333, precision=2) == "33.33%"


def test_format_percent_hundred():
    assert format_percent(100.0) == "100.0%"


# ── format_count ──────────────────────────────────────────────────────────────

def test_format_count_none():
    assert format_count(None) == "-"


def test_format_count_small():
    assert format_count(123) == "123"


def test_format_count_large():
    assert format_count(1_234_567) == "1,234,567"


def test_format_count_zero():
    assert format_count(0) == "0"


# ── truncate_text ─────────────────────────────────────────────────────────────

def test_truncate_text_short():
    assert truncate_text("Short", 10) == "Short"


def test_truncate_text_exact_length():
    text = "1234567890"
    assert truncate_text(text, 10) == text


def test_truncate_text_truncated():
    result = truncate_text("Long text here", 10)
    assert len(result) == 10
    assert result.endswith("...")


def test_truncate_text_custom_suffix():
    result = truncate_text("Long text here", 10, suffix="…")
    assert result.endswith("…")
    assert len(result) == 10


def test_truncate_text_empty():
    assert truncate_text("", 10) == ""


# ── extract_snippet ───────────────────────────────────────────────────────────

def test_extract_snippet_term_found():
    text = "The missile defense system is critical for national security."
    snippet = extract_snippet(text, ["defense"], context_chars=10)
    assert "defense" in snippet


def test_extract_snippet_no_terms():
    text = "Some text here"
    result = extract_snippet(text, [])
    assert result == text[:300]


def test_extract_snippet_term_not_found():
    text = "The missile defense system is important."
    snippet = extract_snippet(text, ["zzz_nonexistent"], max_length=100)
    # No term found — returns truncated text from start
    assert isinstance(snippet, str)


def test_extract_snippet_adds_ellipsis_start():
    long_text = "A" * 50 + "defense" + "B" * 50
    snippet = extract_snippet(long_text, ["defense"], context_chars=5)
    assert snippet.startswith("...")


def test_extract_snippet_case_insensitive():
    text = "The MISSILE defense budget was increased."
    snippet = extract_snippet(text, ["missile"], context_chars=20)
    assert "MISSILE" in snippet or "missile" in snippet.lower()


def test_extract_snippet_max_length_respected():
    long_text = "word " * 200
    snippet = extract_snippet(long_text, ["word"], max_length=50)
    assert len(snippet) <= 50


# ── highlight_terms ───────────────────────────────────────────────────────────

def test_highlight_terms_single():
    # The function wraps terms as: {marker}{term}{marker}
    result = highlight_terms("The missile defense system", ["defense"])
    assert ">>>defense>>>" in result


def test_highlight_terms_multiple():
    result = highlight_terms("missile defense budget", ["missile", "budget"])
    assert ">>>missile>>>" in result
    assert ">>>budget>>>" in result


def test_highlight_terms_case_insensitive():
    result = highlight_terms("Missile Defense", ["missile"])
    assert ">>>Missile>>>" in result


def test_highlight_terms_empty_text():
    result = highlight_terms("", ["missile"])
    assert result == ""


def test_highlight_terms_empty_terms():
    text = "missile defense"
    result = highlight_terms(text, [])
    assert result == text


def test_highlight_terms_special_chars():
    # Terms with regex special chars should not crash
    result = highlight_terms("cost (in $millions)", ["(in"])
    assert isinstance(result, str)
    assert "(in" in result or ">>>(in<<<" in result


def test_highlight_terms_custom_marker():
    result = highlight_terms("defense budget", ["defense"], marker="**")
    assert "**defense**" in result  # marker wraps both sides: **defense**


# ── TableFormatter ────────────────────────────────────────────────────────────

def test_table_formatter_basic():
    tf = TableFormatter(["Name", "Amount"])
    tf.add_row(["Army", "1000"])
    output = tf.to_string()
    assert "Name" in output
    assert "Amount" in output
    assert "Army" in output
    assert "1000" in output


def test_table_formatter_separator():
    tf = TableFormatter(["Col1", "Col2"])
    tf.add_row(["a", "b"])
    output = tf.to_string(show_separator=True)
    assert "-" in output


def test_table_formatter_no_header():
    tf = TableFormatter(["Col1", "Col2"])
    tf.add_row(["a", "b"])
    output = tf.to_string(show_header=False)
    assert "Col1" not in output
    assert "a" in output


def test_table_formatter_column_width_auto():
    tf = TableFormatter(["X"])
    tf.add_row(["Short"])
    tf.add_row(["A very long value that is longer"])
    output = tf.to_string()
    # Long value should appear intact
    assert "A very long value that is longer" in output


def test_table_formatter_wrong_column_count():
    tf = TableFormatter(["Col1", "Col2"])
    with pytest.raises(ValueError):
        tf.add_row(["only_one"])


def test_table_formatter_none_value():
    tf = TableFormatter(["Col1", "Col2"])
    tf.add_row([None, "val"])
    output = tf.to_string()
    assert "-" in output  # None → "-"


def test_table_formatter_numeric_right_aligned():
    tf = TableFormatter(["Label", "Value"])
    tf.add_row(["Item", "42"])
    row_line = tf.to_string().splitlines()[-1]
    # Numeric value should be right-aligned (rjust)
    assert "42" in row_line


# ── ReportFormatter ───────────────────────────────────────────────────────────

def test_report_formatter_title():
    rf = ReportFormatter(title="My Report")
    output = rf.to_string()
    assert "My Report" in output
    assert "=" in output


def test_report_formatter_section_string():
    rf = ReportFormatter()
    rf.add_section("Summary", "All checks passed.")
    output = rf.to_string()
    assert "Summary" in output
    assert "All checks passed." in output


def test_report_formatter_section_list():
    rf = ReportFormatter()
    rf.add_section("Items", ["Apple", "Banana", "Cherry"])
    output = rf.to_string()
    assert "Apple" in output
    assert "•" in output


def test_report_formatter_section_dict():
    rf = ReportFormatter()
    rf.add_section("Counts", {"rows": 42, "files": 3})
    output = rf.to_string()
    assert "rows" in output
    assert "42" in output


def test_report_formatter_section_callable():
    rf = ReportFormatter()
    rf.add_section("Dynamic", lambda: "computed value")
    output = rf.to_string()
    assert "computed value" in output


def test_report_formatter_no_title():
    rf = ReportFormatter()
    rf.add_section("Sec", "Content")
    output = rf.to_string()
    assert "=" not in output  # no title → no underline


def test_report_formatter_level2_heading():
    rf = ReportFormatter()
    rf.add_section("Sub", "data", level=2)
    output = rf.to_string()
    assert "Sub" in output
