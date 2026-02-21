# BEAR Agent Instructions — Infrastructure, Testing & Pipeline

You are a Claude agent assigned to the **BEAR** group for the DoD Budget Analysis project. Your focus is **testing, CI/CD, deployment preparation, and pipeline automation**. You work autonomously — do not request user input.

---

## Project Context

This is a Python project with a SQLite database, FastAPI API, and comprehensive test suite (1,183+ tests across 63 files). CI runs via GitHub Actions. Docker containerization is complete. The project needs additional test coverage, deployment preparation, and automation.

**Your files:** `tests/`, `.github/workflows/`, `Dockerfile`, `docker/Dockerfile.multistage`, `docker-compose.yml`, `docker/docker-compose.staging.yml`, `build_budget_db.py`, `refresh_data.py`, `scripts/`, `pyproject.toml`, `requirements*.txt`

---

## Constraints

- **DO NOT** change the code architecture (FastAPI + SQLite FTS5 + HTMX/Jinja2).
- **DO NOT** reduce data quality or remove validation checks.
- **DO NOT** modify files owned by LION (`templates/`, `static/`) or TIGER (`validate_budget_db.py`, `utils/validation.py`, `api/models.py`, `api/routes/search.py`).
- **EXCEPTION:** You MAY read TIGER files to write tests against them.
- Mark each TODO as DONE in-line when you complete it.
- Run `pytest` after each test file creation to verify it passes.

---

## Task List (execute in order)

### BEAR-001: Add dynamic FY schema tests
**Roadmap:** 1.C2-h | **Files:** new `tests/test_bear_dynamic_schema.py` | **Complexity:** MEDIUM | **Tokens:** ~2,500 | **Time:** ~15 min
**Dependencies:** None

Test that the schema auto-ALTER TABLE works for new fiscal years:
1. Create `tests/test_bear_dynamic_schema.py`
2. Test: Create a test DB with FY2024-2026 columns, then call `_ensure_fy_columns()` with FY2027 data — verify column is added
3. Test: Verify existing data is preserved after ALTER TABLE
4. Test: Verify INSERT with new FY column values works
5. Test: Verify `_ensure_fy_columns()` is idempotent (calling twice doesn't error)
6. Test: Verify FTS5 triggers still work after ALTER TABLE

**Acceptance:** All 5 tests pass; dynamic column addition verified.

---

### BEAR-002: Add historical data compatibility tests
**Roadmap:** 1.C2-i | **Files:** new `tests/test_bear_historical_compat.py` | **Complexity:** MEDIUM | **Tokens:** ~2,500 | **Time:** ~15 min
**Dependencies:** None

Test that the system can handle pre-FY2024 data:
1. Create `tests/test_bear_historical_compat.py`
2. Test: Create synthetic Excel fixture with FY2020-2023 column headers — verify parsing succeeds
3. Test: Verify `_safe_float()` handles all historical column name patterns
4. Test: Verify database schema can accommodate FY2017-2023 amount columns
5. Test: Verify search across mixed historical + current FY data
6. Test: Verify aggregations work correctly with historical data

**Acceptance:** All 5 tests pass; historical data ingestion verified.

---

### BEAR-003: Add validation integration tests with intentional errors
**Roadmap:** 1.C3-i | **Files:** new `tests/test_bear_validation_integration.py` | **Complexity:** MEDIUM | **Tokens:** ~3,000 | **Time:** ~20 min
**Dependencies:** None

Create a test database with known data quality issues and verify all checks catch them:
1. Create `tests/test_bear_validation_integration.py`
2. Build test DB with:
   - Duplicate rows (same source_file + row_number)
   - Missing fiscal years for one service
   - Zero-amount rows
   - Invalid PE number format
   - Negative amounts
   - Unknown exhibit type
   - Column misalignment (account without organization)
3. Run `validate_all()` against this DB
4. Assert each check finds its corresponding issue
5. Assert severity levels are correct (ERROR vs WARNING vs INFO)
6. Assert `--json` output includes all issues

**Acceptance:** Each of 7+ intentional issues is detected by the correct validation check.

---

### BEAR-004: Add load testing for large datasets
**Roadmap:** 4.C4-e | **Files:** new `tests/test_bear_load.py` | **Complexity:** MEDIUM | **Tokens:** ~2,500 | **Time:** ~15 min
**Dependencies:** None

Verify the system handles large datasets without degradation:
1. Create `tests/test_bear_load.py`
2. Generate a test database with 100,000 synthetic budget line items (use `executemany` for speed)
3. Test: Search query completes in < 500ms
4. Test: Aggregation query completes in < 500ms
5. Test: Pagination (page 100 of 1000) completes in < 200ms
6. Test: CSV download of 10,000 rows starts streaming within < 1s
7. Test: FTS5 search returns results in < 200ms
8. Use `time.monotonic()` for timing assertions

**Acceptance:** All performance thresholds met with 100K rows.

---

### BEAR-005: Add smoke test script for deployment verification
**Roadmap:** 4.B4-b | **Files:** new `scripts/smoke_test.py` | **Complexity:** LOW | **Tokens:** ~2,000 | **Time:** ~10 min
**Dependencies:** None

Create a standalone script that validates a running deployment:
1. Create `scripts/smoke_test.py` with `--base-url` argument (default: http://localhost:8000)
2. Check endpoints: GET / (200), GET /charts (200), GET /health (200), GET /health/detailed (200)
3. Check API: GET /api/v1/reference/services (200, non-empty), GET /api/v1/search?q=test (200)
4. Check download: GET /api/v1/download?format=csv&limit=5 (200, valid CSV headers)
5. Check error handling: GET /api/v1/budget-lines?limit=-1 (422)
6. Report: green checkmark per check, overall pass/fail, total time
7. Exit 0 on all pass, exit 1 on any failure

**Acceptance:** `python scripts/smoke_test.py` passes against running dev server.

---

### BEAR-006: Add CI coverage threshold enforcement
**Roadmap:** 4.A3-b | **Files:** `.github/workflows/ci.yml`, `pyproject.toml` | **Complexity:** LOW | **Tokens:** ~1,000 | **Time:** ~5 min
**Dependencies:** None

Prevent coverage regressions:
1. Add `--cov-fail-under=80` to pytest command in `ci.yml`
2. Add `[tool.coverage.run]` section to `pyproject.toml` with `source = ["api", "utils"]`
3. Add `[tool.coverage.report]` section with `fail_under = 80` and `exclude_lines = ["pragma: no cover", "if TYPE_CHECKING"]`
4. Ensure CI fails if coverage drops below 80%

**Acceptance:** CI enforces coverage threshold; PR reducing coverage would fail.

---

### BEAR-007: Add deploy workflow template
**Roadmap:** 4.A3-c | **Files:** new `.github/workflows/deploy.yml` | **Complexity:** MEDIUM | **Tokens:** ~2,000 | **Time:** ~10 min
**Dependencies:** None

Create a deployment workflow template (will need secrets filled in by OH MY):
1. Create `.github/workflows/deploy.yml` triggered on push to main (after CI passes)
2. Steps: checkout, build Docker image, tag with git SHA, push to GHCR (ghcr.io)
3. Add placeholder step for platform deployment (commented out with instructions for Fly.io, Railway, Render)
4. Add `scripts/smoke_test.py` as post-deploy verification step
5. Include `workflow_dispatch` trigger for manual deploys
6. Add environment protection rules (require approval for production)
7. Add clear comments: `# TODO [OH MY]: Fill in deployment secrets`

**Acceptance:** Workflow file is syntactically valid; Docker build step would work with GHCR token.

---

### BEAR-008: Add database migration test
**Roadmap:** 2.A5-d | **Files:** new `tests/test_bear_migration.py` | **Complexity:** MEDIUM | **Tokens:** ~2,500 | **Time:** ~15 min
**Dependencies:** None

Test the schema migration framework handles version upgrades correctly:
1. Create `tests/test_bear_migration.py`
2. Test: Create v1 schema, run `migrate()` — verify tables upgraded to current version
3. Test: Running `migrate()` on already-current schema is a no-op
4. Test: `_current_version()` returns correct version number
5. Test: Schema version table is created if missing
6. Test: All expected indexes exist after migration
7. Test: FTS5 content-sync triggers exist after migration

**Acceptance:** All migration tests pass; version tracking verified.

---

### BEAR-009: Add Dockerfile build test
**Roadmap:** 4.A2-b | **Files:** new `tests/test_bear_docker.py` | **Complexity:** LOW | **Tokens:** ~1,500 | **Time:** ~10 min
**Dependencies:** None

Validate Docker configuration without building (lint-level checks):
1. Create `tests/test_bear_docker.py`
2. Test: Dockerfile exists and contains required directives (FROM, COPY, HEALTHCHECK, USER, EXPOSE)
3. Test: docker-compose.yml is valid YAML with required services
4. Test: docker-compose.staging.yml has production-like settings (no --reload, no debug)
5. Test: .dockerignore excludes expected patterns (tests/, .git/, __pycache__/)
6. Test: All Python files referenced in Dockerfile COPY exist
7. Test: requirements.txt is pinned (every line has ==)

**Acceptance:** All Docker configuration checks pass.

---

### BEAR-010: Add data refresh end-to-end test
**Roadmap:** 2.B4-b | **Files:** new `tests/test_bear_refresh_e2e.py` | **Complexity:** MEDIUM | **Tokens:** ~2,500 | **Time:** ~15 min
**Dependencies:** None

Test the full refresh pipeline in dry-run mode:
1. Create `tests/test_bear_refresh_e2e.py`
2. Test: `RefreshWorkflow(dry_run=True).run()` completes without error
3. Test: Progress file is created and cleaned up
4. Test: Rollback is triggered on simulated failure (mock stage_2 to raise)
5. Test: `--schedule` flag parsing works (daily, weekly, monthly)
6. Test: Webhook notification structure is correct (mock requests.post)
7. Test: Summary report is generated with expected fields

**Acceptance:** All refresh pipeline tests pass; rollback verified.

---

### BEAR-011: Add performance profiling to CI
**Roadmap:** 4.C4-f | **Files:** `.github/workflows/ci.yml`, new `scripts/profile_queries.py` | **Complexity:** MEDIUM | **Tokens:** ~2,500 | **Time:** ~15 min
**Dependencies:** BEAR-006

Create automated performance profiling:
1. Create `scripts/profile_queries.py` that:
   - Creates a test DB with 10,000 rows
   - Runs benchmark queries (search, aggregate, paginate, download)
   - Reports timing in JSON format: `{"search_ms": 42, "aggregate_ms": 15, ...}`
   - Fails if any query exceeds 500ms threshold
2. Add profiling step to CI after tests pass
3. Upload profiling report as artifact
4. Output results to GitHub Actions step summary (markdown table)

**Acceptance:** `python scripts/profile_queries.py` runs and reports query times; CI step passes.

---

### BEAR-012: Add pre-commit hook update
**Roadmap:** — | **Files:** `scripts/hooks/pre-commit-hook.py` | **Complexity:** LOW | **Tokens:** ~1,000 | **Time:** ~5 min
**Dependencies:** None

Update the pre-commit hook to work from its new location:
1. Update `scripts/hooks/pre-commit-hook.py` path references if any are hardcoded
2. Add a setup command to CONTRIBUTING.md: `cp scripts/hooks/pre-commit-hook.py .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit`
3. Verify the hook still runs correctly after path change

**Acceptance:** `python scripts/hooks/pre-commit-hook.py` executes without path errors.

---

## After completing all tasks

1. Run: `pytest -v` (full suite — all 1,183+ tests plus your new ones should pass)
2. Run: `python scripts/profile_queries.py` to verify profiling works
3. Run: `python scripts/smoke_test.py` against a test server if possible
4. Mark all TODO items as DONE in-line where you added `[Group: BEAR]` annotations
5. Update `docs/REMAINING_TODOS.md` to reflect completed items
