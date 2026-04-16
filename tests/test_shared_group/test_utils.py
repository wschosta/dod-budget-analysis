"""
Tests for utils/pdf_sections.py — narrative section parsing.

This file previously contained duplicated tests from:
- test_strings_edge_cases.py (safe_float, normalize_whitespace, sanitize_fts5_query)
- test_validation_classes.py (ValidationIssue, ValidationResult, ValidationRegistry)
- test_database_utils.py (init_pragmas, batch_insert, etc.)
- test_config_classes.py (Config, KnownValues, ColumnMapping, FilePatterns)

Those duplicates have been removed. The PDF narrative section tests below
are the only unique content from the original file.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.pdf_sections import (
    parse_narrative_sections,
    extract_sections_for_page,
    is_narrative_exhibit,
    SECTION_PATTERN,
)


_R2_SAMPLE_PAGE = """\
PE 0602120A — Cybersecurity Research

Accomplishments/Planned Program:
In FY2024, the program completed initial prototype testing of the secure
enclave architecture. All major milestones were achieved on schedule.

FY2025 Plans:
Continue development of the cryptographic acceleration module.
Begin integration testing with the target platform hardware.

Acquisition Strategy:
The program uses competitive prototyping with two prime contractors.
A down-select is planned for the fourth quarter of FY2025.

Performance Metrics:
Metric 1: Encryption throughput >= 10 Gbps by end of FY2025.
Metric 2: Power consumption < 5W at full load.
"""

_R2_NO_SECTIONS = """\
This page contains only tabular data with no narrative headers.
Amount FY2024: 125,400
Amount FY2025: 131,200
Amount FY2026: 145,000
"""


def test_parse_narrative_sections_finds_r2_headers():
    sections = parse_narrative_sections(_R2_SAMPLE_PAGE)
    headers = [s["header"] for s in sections]
    assert any("Accomplishments" in h for h in headers), f"Expected Accomplishments, got {headers}"
    assert any("Acquisition Strategy" in h for h in headers), f"Expected Acquisition Strategy, got {headers}"
    assert any("Performance Metrics" in h for h in headers), f"Expected Performance Metrics, got {headers}"


def test_parse_narrative_sections_body_text_non_empty():
    sections = parse_narrative_sections(_R2_SAMPLE_PAGE)
    for sec in sections:
        assert len(sec["text"]) > 0, f"Section '{sec['header']}' has empty body"


def test_parse_narrative_sections_empty_input():
    assert parse_narrative_sections("") == []
    assert parse_narrative_sections(None) == []


def test_parse_narrative_sections_no_headers():
    result = parse_narrative_sections(_R2_NO_SECTIONS)
    assert result == []


def test_parse_narrative_sections_fy_plans_header():
    sections = parse_narrative_sections(_R2_SAMPLE_PAGE)
    headers = [s["header"] for s in sections]
    assert any("FY" in h and "Plans" in h for h in headers), \
        f"Expected FY Plans header, got {headers}"


def test_extract_sections_for_page_returns_formatted_string():
    result = extract_sections_for_page(_R2_SAMPLE_PAGE, exhibit_type="R-2")
    assert "[Accomplishments" in result
    assert "FY2024" in result


def test_extract_sections_for_page_empty_when_no_sections():
    result = extract_sections_for_page(_R2_NO_SECTIONS)
    assert result == ""


def test_is_narrative_exhibit():
    assert is_narrative_exhibit("R-2") is True
    assert is_narrative_exhibit("R-3") is True
    assert is_narrative_exhibit("r2") is True
    assert is_narrative_exhibit("P-5") is False
    assert is_narrative_exhibit("O-1") is False
    assert is_narrative_exhibit(None) is False
    assert is_narrative_exhibit("") is False


def test_section_pattern_matches_case_insensitive():
    text = "accomplishments/planned programs:\nSome text here"
    assert SECTION_PATTERN.search(text) is not None


def test_parse_narrative_sections_min_len_filter():
    short_text = "Accomplishments/Planned Program:\nOK"
    sections = parse_narrative_sections(short_text, min_section_len=20)
    # Body "OK" is only 2 chars, should be filtered out
    assert sections == []
    sections_no_filter = parse_narrative_sections(short_text, min_section_len=1)
    assert len(sections_no_filter) == 1
