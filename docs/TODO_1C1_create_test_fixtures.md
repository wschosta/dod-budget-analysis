# Step 1.C1 — Create Representative Test Fixtures

**Status:** Mostly Complete (1.C1-a ✅, 1.C1-b ✅, 1.C1-c ✅, 1.C1-d ✅, 1.C1-f ✅ done; 1.C1-e deferred — needs working pipeline environment)
**Type:** Data preparation (AI-agent for generators, ENVIRONMENT TESTING for real files)
**Depends on:** Downloaded budget documents in `DoD_Budget_Documents/`

## Overview

Assemble a small set of test fixtures — both programmatically generated and
extracted from real files — covering each exhibit type and service for use in
automated tests.

---

## Sub-tasks

### 1.C1-a — Create programmatic Excel fixture generators
**Type:** AI-agent
**Estimated tokens:** ~800 output

Write `tests/fixtures/generate_fixtures.py` that:
1. Uses `openpyxl` to generate small `.xlsx` files (~5-10 data rows each)
2. Creates one fixture per summary exhibit type: P-1, R-1, O-1, M-1
3. Each fixture has realistic column headers matching `_map_columns()` expectations
4. Data values are deterministic (no randomness) so assertions are stable
5. Generates fixtures into `tests/fixtures/` with naming: `{service}_{exhibit_type}_fy2026.xlsx`
6. **Update:** `conftest.py` session-scoped `fixtures_dir` to call these generators

**File:** `tests/fixtures/generate_fixtures.py`, `tests/conftest.py`

**Token-efficient tip:** Write one `create_exhibit_xlsx(exhibit_type, service, rows)` helper
and call it once per exhibit type. Reuse `_map_columns()` header lists from test_parsing.py.

---

### 1.C1-b — Create programmatic PDF fixtures
**Type:** AI-agent
**Estimated tokens:** ~400 output

1. Use `fpdf2` (lightweight, ~15 lines per fixture) to generate 2-3 small PDFs:
   - One with extractable text paragraphs
   - One with a tabular layout (pipe-delimited rows)
   - One with mixed content (narrative + table)
2. Store in `tests/fixtures/`
3. **Update:** Add `fpdf2` to `requirements-dev.txt`

**File:** `tests/fixtures/generate_fixtures.py` (extend), `requirements-dev.txt`

---

### 1.C1-c — Create pre-populated test database fixture
**Type:** AI-agent
**Estimated tokens:** ~400 output
**Depends on:** 1.C1-a, 1.C1-b

1. Add a `test_db` session-scoped fixture to `conftest.py` that:
   - Uses generated fixtures from 1.C1-a and 1.C1-b
   - Copies them into a temp directory mimicking `DoD_Budget_Documents/FY2026/{Service}/` structure
   - Calls `build_database(docs_dir=tmpdir, db_path=tmpdb, rebuild=True)`
   - Yields the connection for all tests to share
2. This replaces the stub `test_db` fixture currently in `conftest.py`

**Note:** `test_validation.py` already has a working in-memory DB fixture with
`_insert_budget_line()` helper — keep that pattern for validation tests but add
this fuller fixture for integration tests.

**File:** `tests/conftest.py`

---

### 1.C1-d — Create "known bad" fixture files
**Type:** AI-agent
**Estimated tokens:** ~300 output

Generate `.xlsx` files with intentionally broken formatting for error-handling tests:
1. Missing header row (data starts at row 1)
2. Extra blank columns interspersed
3. Zero-byte file (renamed to `.xlsx`)
4. Non-Excel file renamed to `.xlsx`
5. Store in `tests/fixtures/bad/`

**File:** `tests/fixtures/generate_fixtures.py` (extend)

---

### 1.C1-e — Create expected output JSON files
**Type:** AI-agent
**Estimated tokens:** ~400 output
**Depends on:** 1.C1-a, 1.C1-c

For each good fixture file:
1. Run the ingestion pipeline once
2. Extract: row count, exhibit_type, column names found, sample field values
3. Save as `tests/fixtures/expected/{fixture_name}.json`
4. These serve as "golden" outputs for regression tests in 1.C3

**Token-efficient tip:** Write a small script that builds the DB, queries it,
and dumps expected JSON. Run once, check in the JSON files.

**File:** `tests/fixtures/expected/*.json`

---

### 1.C1-f — Create requirements-dev.txt
**Type:** AI-agent
**Estimated tokens:** ~100 output

Create `requirements-dev.txt` with test-only dependencies:
```
pytest
pytest-cov
fpdf2
```
**Update:** `docs/wiki/Contributing.md` — add test setup instructions.

**File:** `requirements-dev.txt`, `docs/wiki/Contributing.md`

---

## Annotations

- 1.C1-a can be written purely from reading `_map_columns()` source — no downloaded files needed
- 1.C1-b requires `fpdf2` (pip install, ~2 MB)
- 1.C1-c needs 1.C1-a and 1.C1-b outputs to exist
- 1.C1-e depends on the full pipeline working against generated fixtures
- `test_validation.py` already has a working in-memory DB pattern — reuse that approach
- The existing `conftest.py` has stubs for fixtures_dir and test_db — replace them
- TOKEN EFFICIENCY: Generated fixtures are small and deterministic. No need to read
  real budget files into context.
