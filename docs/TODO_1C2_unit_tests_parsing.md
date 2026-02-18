# Step 1.C2 — Unit Tests for Parsing Logic

**Status:** Mostly Complete (1.C2-a ✅, 1.C2-b ✅, 1.C2-c ✅, 1.C2-d ✅, 1.C2-g ✅ done; 1.C2-e/f deferred — depend on working fpdf2/pdfplumber environment)
**Type:** Code creation (AI-agent completable)
**Depends on:** 1.B2 (column mapping changes should update tests)

## Overview

Extend `tests/test_parsing.py` with additional coverage and create any missing
test modules. Many tests can be written purely from reading source code.

### Already Implemented
- `test_detect_exhibit_type` — 11 parametrized cases
- `test_safe_float` — 12 parametrized cases
- `test_determine_category` — 6 parametrized cases
- `test_extract_table_text` — 3 test functions
- `test_map_columns` — 3 test functions (P-1, C-1, empty)

---

## Sub-tasks

### 1.C2-a — Expand _map_columns() test coverage
**Type:** AI-agent
**Estimated tokens:** ~600 output

The existing tests cover P-1, C-1, and empty headers. Add tests for:
1. R-1 headers (research-specific columns)
2. O-1 headers (operation & maintenance columns)
3. M-1 headers (military personnel columns)
4. RF-1 headers (revolving fund columns)
5. P-1R headers (should map same as P-1 with minor variations)
6. Headers with multi-line cells (newline-separated like `"FY2026 Request\nAmount"`)
7. Headers with inconsistent capitalization

**File:** `tests/test_parsing.py`

**Token-efficient tip:** Read `_map_columns()` in `build_budget_db.py` (~lines 284-400)
to extract the exact patterns each branch looks for, then write headers that match.

---

### 1.C2-b — Add _sanitize_filename tests
**Type:** AI-agent
**Estimated tokens:** ~300 output

1. Import `_sanitize_filename` from `dod_budget_downloader.py`
2. Test cases:
   - Normal filename — unchanged
   - Path separators (`/`, `\`) — replaced
   - Query strings (`?key=val`) — stripped
   - Very long filenames — truncated to OS limit
   - Unicode characters — handled gracefully
   - Empty string — returns something sensible

**File:** `tests/test_parsing.py` or `tests/test_downloader.py` (new file, ~40 lines)

---

### 1.C2-c — Add _detect_amount_unit tests (after 1.B3-a)
**Type:** AI-agent
**Estimated tokens:** ~300 output
**Depends on:** 1.B3-a (function doesn't exist yet)

Once `_detect_amount_unit()` is implemented:
1. Test with header rows containing "in thousands" — returns "thousands"
2. Test with "in millions" — returns "millions"
3. Test with "($ thousands)" — returns "thousands"
4. Test with no unit indicator — returns "unknown" with warning
5. Test with mixed case variants

**File:** `tests/test_parsing.py`

---

### 1.C2-d — Add PE extraction tests (after 1.B4-a)
**Type:** AI-agent
**Estimated tokens:** ~300 output
**Depends on:** 1.B4-a (PE extraction function doesn't exist yet)

Once PE extraction is implemented:
1. Test regex `r'\d{7}[A-Z]'` against valid PE numbers
2. Test with PE embedded in longer strings
3. Test with no PE match — returns None
4. Test with multiple PE numbers in one field

**File:** `tests/test_parsing.py`

---

### 1.C2-e — Test ingest_excel_file with generated fixtures
**Type:** AI-agent
**Estimated tokens:** ~500 output
**Depends on:** 1.C1-a (generated Excel fixtures), 1.C1-c (test_db fixture)

1. Write `test_ingest_excel_file_p1()` using a generated P-1 fixture
2. Assert: correct row count, correct exhibit_type, correct organization
3. Spot-check specific field values against expected JSON from 1.C1-e
4. Add `pytest.mark.skipif` guard if fixtures don't exist

**File:** `tests/test_parsing.py`

---

### 1.C2-f — Test ingest_pdf_file with generated fixtures
**Type:** AI-agent
**Estimated tokens:** ~400 output
**Depends on:** 1.C1-b (generated PDF fixtures)

1. Write `test_ingest_pdf_file_text()` using the text-extractable PDF fixture
2. Assert: pdf_pages table has entries, content is non-empty
3. Write `test_ingest_pdf_file_table()` using the table PDF fixture
4. Assert: table_data field is populated
5. Add `pytest.mark.skipif` guard if fixtures don't exist

**File:** `tests/test_parsing.py`

---

### 1.C2-g — Clean up legacy TODO comments in test files
**Type:** AI-agent
**Estimated tokens:** ~200 output

1. Remove the block comments at the bottom of `test_parsing.py` (lines 162-171)
   that describe already-implemented test groups
2. Remove the block comments at the bottom of `conftest.py` (lines 62-70)
   that duplicate the TODOs in the docstring
3. Ensure remaining TODO comments reference correct sub-task IDs

**File:** `tests/test_parsing.py`, `tests/conftest.py`

---

## Annotations

- 1.C2-a is immediately completable (no dependencies, no data needed)
- 1.C2-b is immediately completable (just imports from downloader)
- 1.C2-c and 1.C2-d depend on future parsing functions being implemented
- 1.C2-e and 1.C2-f depend on test fixtures from 1.C1
- 1.C2-g is a cleanup task — do anytime
- The `pdfplumber` stub pattern in test_parsing.py line 21-22 is critical — keep it
- `test_validation.py` is a separate, complete test module — no changes needed
- TOKEN EFFICIENCY: Tests for pure functions (_detect_exhibit_type, _safe_float, etc.)
  need zero data files — just read function source and write assertions
