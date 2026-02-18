"""
Unit tests for exhibit_catalog.py public functions.

Tests the catalog lookup, column spec retrieval, and header matching
functions. No database, network, or file I/O required.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from exhibit_catalog import (
    EXHIBIT_CATALOG,
    get_exhibit_spec,
    get_column_spec_for_exhibit,
    find_matching_columns,
    list_all_exhibit_types,
    describe_catalog,
)


# ── EXHIBIT_CATALOG structure ─────────────────────────────────────────────────

def test_catalog_contains_known_exhibit_types():
    """EXHIBIT_CATALOG has at minimum the standard summary exhibits."""
    known = {"p1", "r1", "m1", "o1", "c1"}
    for exhibit in known:
        assert exhibit in EXHIBIT_CATALOG, f"Expected '{exhibit}' in catalog"


def test_catalog_entries_have_required_keys():
    """Every catalog entry has name, description, column_spec, known_variations."""
    for key, spec in EXHIBIT_CATALOG.items():
        assert "name" in spec, f"Entry '{key}' missing 'name'"
        assert "description" in spec, f"Entry '{key}' missing 'description'"
        assert "column_spec" in spec, f"Entry '{key}' missing 'column_spec'"
        assert isinstance(spec["column_spec"], list), "column_spec should be a list"


def test_catalog_column_specs_have_required_fields():
    """Each column spec entry has 'field' and 'header_patterns'."""
    for exhibit_key, spec in EXHIBIT_CATALOG.items():
        for col in spec["column_spec"]:
            assert "field" in col, f"Column in '{exhibit_key}' missing 'field'"
            assert "header_patterns" in col, (
                f"Column '{col.get('field', '?')}' in '{exhibit_key}' "
                f"missing 'header_patterns'"
            )
            assert isinstance(col["header_patterns"], list)


# ── get_exhibit_spec ──────────────────────────────────────────────────────────

def test_get_exhibit_spec_known():
    spec = get_exhibit_spec("p1")
    assert spec is not None
    assert "Procurement" in spec["name"]


def test_get_exhibit_spec_case_insensitive():
    assert get_exhibit_spec("P1") == get_exhibit_spec("p1")


def test_get_exhibit_spec_unknown():
    assert get_exhibit_spec("zz_unknown") is None


def test_get_exhibit_spec_all_standard():
    """All standard exhibit types return a non-None spec."""
    for exhibit in ["p1", "r1", "m1", "o1"]:
        assert get_exhibit_spec(exhibit) is not None, f"Missing spec for {exhibit}"


# ── get_column_spec_for_exhibit ───────────────────────────────────────────────

def test_get_column_spec_p1_has_account():
    cols = get_column_spec_for_exhibit("p1")
    fields = [c["field"] for c in cols]
    assert "account" in fields


def test_get_column_spec_unknown_returns_empty():
    assert get_column_spec_for_exhibit("zz_unknown") == []


def test_get_column_spec_returns_list():
    result = get_column_spec_for_exhibit("m1")
    assert isinstance(result, list)


# ── find_matching_columns ─────────────────────────────────────────────────────

def test_find_matching_columns_p1_account():
    """Header 'Account' matches the account field in P-1."""
    headers = ["Account", "Account Title", "Budget Activity"]
    matched = find_matching_columns("p1", headers)
    # Index 0 ('Account') should match to 'account'
    assert 0 in matched
    assert matched[0] == "account"


def test_find_matching_columns_no_matches():
    """Headers with no overlap with catalog patterns → empty dict."""
    # Avoid substrings of any header_patterns (e.g. 'BA' is in 'Bar')
    headers = ["Zulu", "Xray", "Foxtrot999"]
    matched = find_matching_columns("p1", headers)
    assert matched == {}


def test_find_matching_columns_unknown_exhibit():
    """Unknown exhibit type → empty dict."""
    headers = ["Account", "Title"]
    matched = find_matching_columns("zz_unknown", headers)
    assert matched == {}


def test_find_matching_columns_case_insensitive():
    """Header matching is case-insensitive."""
    headers = ["ACCOUNT", "ACCOUNT TITLE"]
    matched = find_matching_columns("p1", headers)
    assert 0 in matched


def test_find_matching_columns_empty_headers():
    """Empty header list → empty dict."""
    matched = find_matching_columns("p1", [])
    assert matched == {}


def test_find_matching_columns_none_headers():
    """None values in headers are handled without error."""
    headers = [None, "Account", None]
    matched = find_matching_columns("p1", headers)
    assert isinstance(matched, dict)


# ── list_all_exhibit_types ────────────────────────────────────────────────────

def test_list_all_exhibit_types_returns_list():
    types = list_all_exhibit_types()
    assert isinstance(types, list)
    assert len(types) > 0


def test_list_all_exhibit_types_sorted():
    types = list_all_exhibit_types()
    assert types == sorted(types)


def test_list_all_exhibit_types_lowercase():
    types = list_all_exhibit_types()
    for t in types:
        assert t == t.lower(), f"Exhibit type '{t}' should be lowercase"


def test_list_all_exhibit_types_includes_known():
    types = list_all_exhibit_types()
    for exhibit in ["p1", "r1", "m1"]:
        assert exhibit in types


# ── describe_catalog ──────────────────────────────────────────────────────────

def test_describe_catalog_returns_string():
    result = describe_catalog()
    assert isinstance(result, str)
    assert len(result) > 0


def test_describe_catalog_contains_exhibit_names():
    result = describe_catalog()
    # Should contain P1 and M1
    assert "P1" in result or "p1" in result.lower()


def test_describe_catalog_contains_column_counts():
    result = describe_catalog()
    # Should mention "columns" somewhere
    assert "columns" in result


# ── DONE 1.B1-f: All catalog entries return valid mappings ────────────────────

def _build_realistic_header(exhibit_key: str) -> list[str]:
    """Build a synthetic header row using the first pattern from each column spec."""
    col_specs = get_column_spec_for_exhibit(exhibit_key)
    return [col["header_patterns"][0] for col in col_specs if col.get("header_patterns")]


@pytest.mark.parametrize("exhibit_key", list(EXHIBIT_CATALOG.keys()))
def test_find_matching_columns_non_empty_for_each_catalog_type(exhibit_key):
    """Every catalog exhibit type returns at least one matched column for a
    realistic header row constructed from its own header_patterns (1.B1-f).
    """
    headers = _build_realistic_header(exhibit_key)
    assert headers, f"No header patterns found for '{exhibit_key}'"
    matched = find_matching_columns(exhibit_key, headers)
    assert len(matched) > 0, (
        f"find_matching_columns('{exhibit_key}', {headers}) returned empty dict — "
        f"header_patterns in EXHIBIT_CATALOG may not match find_matching_columns logic"
    )


@pytest.mark.parametrize("exhibit_key", list(EXHIBIT_CATALOG.keys()))
def test_catalog_entry_column_count(exhibit_key):
    """Every catalog entry has at least one column spec (1.B1-f basic sanity)."""
    cols = get_column_spec_for_exhibit(exhibit_key)
    assert len(cols) >= 1, f"Exhibit '{exhibit_key}' has no column specs"


def test_find_matching_columns_r1_realistic_header():
    """R-1 header with PE/BLI patterns maps at least program_element (1.B1-f)."""
    headers = ["Account", "Account Title", "Organization",
               "Budget Activity", "Program Element",
               "Prior Year", "Current Year", "Budget Estimate"]
    matched = find_matching_columns("r1", headers)
    fields = set(matched.values())
    assert "account" in fields or "program_element" in fields


def test_find_matching_columns_c1_authorization():
    """C-1 header includes Authorization and Appropriation patterns (1.B1-f)."""
    headers = ["Account", "Project Number", "Project Title",
               "Location", "Authorization Amount", "Appropriation Amount",
               "Estimate Amount"]
    matched = find_matching_columns("c1", headers)
    fields = set(matched.values())
    assert "authorization_amount" in fields
    assert "appropriation_amount" in fields
