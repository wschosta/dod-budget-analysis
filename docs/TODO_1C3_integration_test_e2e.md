# Step 1.C3 — Integration Test: End-to-End Pipeline

**Status:** Not started
**Type:** Code creation (AI-agent completable, needs fixtures)
**Depends on:** 1.C1 (fixtures), 1.C2 (unit tests passing)

## Task

Test the full flow from raw files to SQLite database to search query,
verifying row counts and known values.

## Agent Instructions

1. Create `tests/test_e2e_pipeline.py` with:

### test_build_from_fixtures
- Copy fixture files to a temp directory matching the expected structure:
  `{tmpdir}/FY2026/Comptroller/file.xlsx`, etc.
- Run `build_database(docs_dir=tmpdir, db_path=tmpdb, rebuild=True)`
- Assert: database file exists, row counts match expected, no errors

### test_search_after_build
- After building from fixtures, run search queries:
  - `search_budget_lines(conn, "Army")` returns results
  - `search_pdf_pages(conn, "procurement")` returns results
  - Verify result fields are populated (not all NULL)

### test_incremental_update
- Build once, then add a new fixture file and build again (rebuild=False)
- Assert: new file is ingested, old data preserved, row count increases

### test_rebuild_cleans_state
- Build with fixtures, then rebuild with a subset
- Assert: removed files' data is cleaned up

2. Use `pytest` `tmp_path` fixture for isolation
3. Estimated tokens: ~1500 output tokens

## Annotations

- **DATA PROCESSING:** Requires fixture files from 1.C1. If fixtures don't
  exist yet, write the test structure with `pytest.mark.skipif` guards so
  tests are skipped gracefully
- **ENVIRONMENT TESTING:** Requires `openpyxl`, `pdfplumber`, and `pandas`
  to be installed. The test should skip cleanly if dependencies are missing.
- This is the most important test — it validates that the entire pipeline
  produces correct, queryable output
