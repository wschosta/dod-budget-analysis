# Step 1.C3 — Integration Test: End-to-End Pipeline

**Status:** ✅ Complete (all 1.C3-a through 1.C3-h implemented; test_e2e_pipeline.py deleted per 1.C3-i; tests that need fpdf2 skip gracefully in broken environments)
**Type:** Code creation (AI-agent, needs fixtures from 1.C1)
**Depends on:** 1.C1 (fixtures), 1.C2 (unit tests passing)

## Overview

Test the full flow from raw files to SQLite database to search query, verifying
row counts and known values. Tests live in `tests/test_pipeline.py` (detailed TODOs
already exist) and `tests/test_e2e_pipeline.py` (stub).

### Already Existing
- `tests/test_pipeline.py` — detailed TODO specs for 8 test groups (1.C3-a through 1.C3-h)
- `tests/test_e2e_pipeline.py` — stub with 4 planned test groups

---

## Sub-tasks

### 1.C3-a — Test full Excel ingestion pipeline
**Type:** AI-agent
**Estimated tokens:** ~400 output
**Depends on:** 1.C1-a (Excel fixtures), 1.C1-c (test_db fixture)

In `tests/test_pipeline.py`:
1. Use the session-scoped `test_db` fixture from conftest.py
2. Assert: `ingested_files` table has one row per fixture file
3. Assert: `budget_lines` table has the expected total row count
4. Assert: each row in `budget_lines` has non-null `source_file` and `exhibit_type`
5. Add `pytest.mark.skipif` guard if fixtures don't exist

**File:** `tests/test_pipeline.py`

---

### 1.C3-b — Test full PDF ingestion pipeline
**Type:** AI-agent
**Estimated tokens:** ~300 output
**Depends on:** 1.C1-b (PDF fixtures), 1.C1-c (test_db fixture)

1. Assert: `pdf_pages` table has rows for each page of each fixture PDF
2. Assert: `content` column is non-empty for extractable PDFs
3. Assert: FTS index (`pdf_pages_fts`) returns results for known text via MATCH

**File:** `tests/test_pipeline.py`

---

### 1.C3-c — Test incremental update behavior
**Type:** AI-agent
**Estimated tokens:** ~500 output
**Depends on:** 1.C1-a (fixtures)

1. Build database from fixture files into tmp_path
2. Record `ingested_files` state (row count, file hashes)
3. Run build again without changes — assert no new rows added
4. Touch one fixture file (modify content slightly) — assert only that file re-ingested
5. Assert: total budget_lines count increased by the new file's row count

**Token-efficient tip:** Use `tmp_path`, `shutil.copy` fixtures in, build, then
copy one modified file and build again with `rebuild=False`.

**File:** `tests/test_pipeline.py`

---

### 1.C3-d — Test --rebuild flag
**Type:** AI-agent
**Estimated tokens:** ~300 output
**Depends on:** 1.C1-a (fixtures)

1. Build database from all fixtures
2. Rebuild with `rebuild=True` using only a subset of fixtures
3. Assert: only the subset's data exists in the rebuilt database
4. Assert: `ingested_at` timestamps are all from the second run

**File:** `tests/test_pipeline.py`

---

### 1.C3-e — Test search_budget.py query functions
**Type:** AI-agent
**Estimated tokens:** ~400 output
**Depends on:** 1.C1-c (test_db fixture)

Import search functions from `search_budget.py` and test against the test database:
1. Text search: search for a term known to be in fixtures — assert results
2. Filter by `exhibit_type` — assert only matching rows returned
3. Filter by `organization` — assert only matching rows returned
4. Empty search — assert no crash, returns empty list
5. Special characters in search — assert no SQL injection or FTS crash

**File:** `tests/test_pipeline.py`

---

### 1.C3-f — Test error handling for corrupt files
**Type:** AI-agent
**Estimated tokens:** ~300 output
**Depends on:** 1.C1-d (bad fixtures)

1. Place bad fixtures (zero-byte, truncated, non-Excel) in temp directory
2. Run `build_database()` against the directory
3. Assert: build completes without crashing
4. Assert: bad files are NOT in `ingested_files` table
5. Assert: warnings/errors were logged (capture with `caplog` fixture)

**File:** `tests/test_pipeline.py`

---

### 1.C3-g — Test FTS5 index integrity
**Type:** AI-agent
**Estimated tokens:** ~250 output
**Depends on:** 1.C1-c (test_db fixture)

Standalone test using raw SQL against the test database:
1. Query `budget_lines_fts` with MATCH for a known term — assert rows returned
2. Query `pdf_pages_fts` with MATCH for known text — assert rows returned
3. Verify FTS results match regular table queries for the same term

**File:** `tests/test_pipeline.py`

---

### 1.C3-h — Test database schema integrity
**Type:** AI-agent
**Estimated tokens:** ~200 output
**No dependencies — can be implemented immediately**

Standalone, no fixture data needed (just builds empty DB):
1. Call `create_database()` with a tmp_path
2. Query `sqlite_master` for all tables — assert expected set exists
3. Query `PRAGMA table_info(budget_lines)` — assert all expected columns present
4. Assert FTS virtual tables exist: `budget_lines_fts`, `pdf_pages_fts`
5. Assert `ingested_files` table exists with expected columns

**File:** `tests/test_pipeline.py`

**Token-efficient tip:** This can be implemented immediately — no fixtures needed.
Just needs `create_database()` from `build_budget_db.py`. ~15 lines of test code.

---

### 1.C3-i — Consolidate test_pipeline.py and test_e2e_pipeline.py
**Type:** AI-agent
**Estimated tokens:** ~200 output

Currently there are two stub files for integration tests:
1. `tests/test_pipeline.py` — has detailed TODO specs (8 groups)
2. `tests/test_e2e_pipeline.py` — has 4 planned test groups (subset of above)

Decision: **Merge into `test_pipeline.py`** (it has the more detailed specs).
Delete `test_e2e_pipeline.py` after ensuring no unique test ideas are lost.

**File:** `tests/test_pipeline.py`, `tests/test_e2e_pipeline.py` (delete)

---

## Annotations

- 1.C3-h can be implemented **immediately** (no fixtures needed, just schema check)
- 1.C3-i is a cleanup task — do early to avoid confusion
- 1.C3-a through 1.C3-g all need fixtures from 1.C1
- `test_pipeline.py` already has well-written TODO specs inline (1.C3-a through 1.C3-h)
- `test_validation.py` is separate and complete — it tests `validate_budget_data.py`
- ENVIRONMENT TESTING: Tests require `openpyxl`, `pdfplumber`, and `pandas`.
  Use `pytest.mark.skipif` for graceful skips.
- TOKEN EFFICIENCY: Schema integrity test (1.C3-h) needs ~15 lines. Start there.
