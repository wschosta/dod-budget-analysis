"""
Unit tests for parsing logic — Step 1.C2

Tests for column detection, value normalization, exhibit-type identification,
and PE/line-item extraction.  Each test function should be self-contained and
not depend on external files (use fixtures from conftest.py or inline data).

──────────────────────────────────────────────────────────────────────────────
TODOs — each is an independent test or small group of tests
──────────────────────────────────────────────────────────────────────────────

TODO 1.C2-a: Test _detect_exhibit_type() with known filenames.
    Cases: "p1_display.xlsx" → "p1", "r1.xlsx" → "r1", "c1_display.xlsx" → "c1",
    "p1r_display.xlsx" → "p1r", "unknown_file.xlsx" → "unknown",
    "m1_something_else.xlsx" → "m1".
    Standalone — no fixtures needed, just import and call.

TODO 1.C2-b: Test _map_columns() for each exhibit type.
    For each exhibit in EXHIBIT_CATALOG (once populated), construct a sample
    header list and assert the returned mapping contains the expected keys.
    Include edge cases: extra columns, missing optional columns, different
    capitalization.
    Dependency: exhibit_catalog.py must have at least sample headers.
    Token-efficient tip: parametrize with @pytest.mark.parametrize over a list
    of (headers, exhibit_type, expected_keys) tuples.

TODO 1.C2-c: Test _safe_float() edge cases.
    Cases: None→None, ""→None, " "→None, "123"→123.0, 123→123.0,
    "abc"→None, 0→0.0, "-5.5"→-5.5.
    Standalone — ~10 lines.

TODO 1.C2-d: Test _determine_category() path mapping.
    Feed in Path objects with various directory structures and assert correct
    category strings.  E.g., Path("FY2026/US_Army/file.pdf") → "Army".
    Standalone — ~15 lines.

TODO 1.C2-e: Test _extract_table_text() formatting.
    Feed in sample table data (list of lists) and verify the output string
    format: cells joined by " | ", rows joined by newlines, empty cells skipped.
    Standalone — ~10 lines.

TODO 1.C2-f: Test header row detection in ingest_excel_file().
    Create a minimal .xlsx (using openpyxl in the test) with the header row at
    position 0, 1, 2, and 3 — verify that each is correctly detected.
    Token-efficient tip: use a helper that writes a workbook to tmp_path, then
    call ingest_excel_file() with an in-memory SQLite db and check row counts.

TODO 1.C2-g: Test that blank/empty rows are skipped.
    Create an .xlsx with data rows interspersed with fully-blank rows and
    rows where only whitespace is present.  Verify they don't produce
    budget_lines entries.

TODO 1.C2-h: Test fiscal year detection from sheet names.
    Cases: "FY 2026" → "FY 2026", "FY2025" → "FY 2025", "Sheet1" → "Sheet1",
    "Exhibit FY 2024" → "FY 2024".
    Token-efficient tip: extract the FY regex logic into a small testable
    function if it isn't already.
"""

# TODO: implement tests per TODOs above
