"""
Unit tests for scripts/exhibit_audit.py pure helper functions.

Tests _find_header_row, _header_signature, _deduplicate, and generate_report
without requiring openpyxl or any file I/O.
"""
import sys
from pathlib import Path


# Add both the scripts dir and the repo root to the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from exhibit_audit import (
    _find_header_row,
    _header_signature,
    _deduplicate,
    generate_report,
)


# ── _find_header_row ──────────────────────────────────────────────────────────

def test_find_header_row_first_row():
    rows = [
        ("Account", "Title", "FY2026"),
        (None, "Army", "100.0"),
    ]
    assert _find_header_row(rows) == 0


def test_find_header_row_second_row():
    rows = [
        ("DoD Budget Summary", None, None),
        ("Account", "Account Title", "Organization"),
        ("2035", "Aircraft", "Army"),
    ]
    assert _find_header_row(rows) == 1


def test_find_header_row_not_found():
    rows = [
        ("Name", "Value", "Other"),
        ("X", "Y", "Z"),
    ]
    assert _find_header_row(rows) is None


def test_find_header_row_case_insensitive():
    rows = [("ACCOUNT", "Title", None)]
    assert _find_header_row(rows) == 0


def test_find_header_row_empty():
    assert _find_header_row([]) is None


def test_find_header_row_beyond_ten():
    # Only scans first 10 rows
    rows = [(None,)] * 10 + [("Account", "Title")]
    assert _find_header_row(rows) is None


# ── _header_signature ─────────────────────────────────────────────────────────

def test_header_signature_basic():
    headers = ("Account", "Account Title", "FY2026", None, "")
    sig = _header_signature(headers)
    assert "Account" in sig
    assert "FY2026" in sig
    assert "None" not in sig


def test_header_signature_empty():
    sig = _header_signature(())
    assert sig == ""


def test_header_signature_all_none():
    sig = _header_signature((None, None, None))
    assert sig == ""


def test_header_signature_caps_at_six():
    headers = tuple(f"Col{i}" for i in range(10))
    sig = _header_signature(headers)
    # Should only include 6 items
    assert sig.count(" | ") == 5  # 6 items = 5 separators


def test_header_signature_strips_whitespace():
    headers = ("  Account  ", "  Title  ")
    sig = _header_signature(headers)
    assert "Account" in sig
    assert "Title" in sig
    assert "  " not in sig


# ── _deduplicate ──────────────────────────────────────────────────────────────

def test_deduplicate_no_duplicates():
    entries = [
        {"sheet": "Sheet1", "header_sig": "Account | Title", "file": "a.xlsx"},
        {"sheet": "Sheet2", "header_sig": "Account | Other", "file": "b.xlsx"},
    ]
    result = _deduplicate(entries)
    assert len(result) == 2


def test_deduplicate_removes_duplicates():
    entries = [
        {"sheet": "Sheet1", "header_sig": "Account | Title", "file": "a.xlsx"},
        {"sheet": "Sheet1", "header_sig": "Account | Title", "file": "b.xlsx"},  # dup
    ]
    result = _deduplicate(entries)
    assert len(result) == 1
    assert result[0]["file"] == "a.xlsx"  # keeps first occurrence


def test_deduplicate_empty():
    assert _deduplicate([]) == []


def test_deduplicate_different_sheets_same_sig():
    entries = [
        {"sheet": "S1", "header_sig": "X", "file": "a.xlsx"},
        {"sheet": "S2", "header_sig": "X", "file": "b.xlsx"},  # different sheet
    ]
    result = _deduplicate(entries)
    assert len(result) == 2  # different (sheet, sig) keys


# ── generate_report ───────────────────────────────────────────────────────────

def test_generate_report_returns_string():
    results = {}
    report = generate_report(results, Path("/tmp/docs"))
    assert isinstance(report, str)


def test_generate_report_has_title():
    results = {}
    report = generate_report(results, Path("/tmp/docs"))
    assert "Exhibit Type Audit Report" in report


def test_generate_report_shows_exhibit_type():
    results = {
        "p1": [
            {"sheet": "Sheet1", "header_sig": "Account | Title", "file": "a.xlsx", "error": None}
        ]
    }
    report = generate_report(results, Path("/tmp/docs"))
    assert "P1" in report


def test_generate_report_includes_total_count():
    results = {
        "m1": [{"sheet": "S", "header_sig": "X", "file": "f.xlsx", "error": None}],
        "o1": [{"sheet": "S", "header_sig": "Y", "file": "g.xlsx", "error": None}],
    }
    report = generate_report(results, Path("/tmp/docs"))
    assert "2" in report  # total_files = 2


def test_generate_report_handles_errors():
    results = {
        "p1": [{"sheet": "S", "header_sig": "", "file": "bad.xlsx",
                "error": "Corrupt file"}]
    }
    report = generate_report(results, Path("/tmp/docs"))
    assert "ERROR" in report


def test_generate_report_catalog_coverage_section():
    results = {}
    report = generate_report(results, Path("/tmp/docs"))
    assert "Catalog Coverage Summary" in report
