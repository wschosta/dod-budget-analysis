# Step 1.C2 — Unit Tests for Parsing Logic

**Status:** Not started
**Type:** Code creation (AI-agent completable)
**Depends on:** 1.C1 (test fixtures), 1.B2 (column mappings)

## Task

Write `pytest` tests for column detection, value normalization, exhibit-type
identification, and PE/line-item extraction.

## Agent Instructions

1. Create `tests/test_parsing.py` with the following test groups:

### test_detect_exhibit_type
- Test `_detect_exhibit_type()` with various filenames
- Cover all entries in `EXHIBIT_TYPES` plus edge cases (unknown, mixed case)

### test_map_columns
- Test `_map_columns()` with sample header rows for each exhibit type
- Verify returned mapping contains expected field names
- Test with incomplete headers (missing optional columns)

### test_safe_float
- Test `_safe_float()` with: integers, floats, strings, None, empty string,
  whitespace, non-numeric strings

### test_sanitize_filename (from downloader)
- Test `_sanitize_filename()` with special characters, query strings, long names

### test_ingest_excel_file (integration, needs fixtures)
- Test `ingest_excel_file()` with a fixture file
- Verify row count and spot-check field values against expected output

2. Create `tests/conftest.py` with shared fixtures:
   - `tmp_db` fixture that creates a temporary SQLite database
   - `sample_xlsx` fixture that returns path to a test Excel file

3. Add `pytest` to `requirements.txt` if not present
4. Estimated tokens: ~1800 output tokens

## Annotations

- Tests for `_detect_exhibit_type`, `_map_columns`, and `_safe_float` can be
  written purely from reading the source code — no data files needed
- Tests for `ingest_excel_file` need fixture files from 1.C1
- Structure tests so the no-fixture tests can run independently
