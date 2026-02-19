# TIGER Agent Instructions — API, Data Quality & Backend

You are a Claude agent assigned to the **TIGER** group for the DoD Budget Analysis project. Your focus is **data quality validation, API enhancements, and backend utilities**. You work autonomously — do not request user input.

---

## Project Context

This is a FastAPI application serving DoD budget data from a SQLite database. The validation suite is in `validate_budget_db.py` + `utils/validation.py`. The API is in `api/`. Reference data and schema definitions are in `schema_design.py` and `exhibit_catalog.py`.

**Your files:** `validate_budget_db.py`, `validate_budget_data.py`, `utils/validation.py`, `utils/database.py`, `utils/formatting.py`, `utils/query.py`, `utils/cache.py`, `api/routes/search.py`, `api/routes/aggregations.py`, `api/routes/download.py`, `api/routes/reference.py`, `api/models.py`, `api/app.py`, `schema_design.py`, `exhibit_catalog.py`

---

## Constraints

- **DO NOT** change the code architecture (FastAPI + SQLite FTS5).
- **DO NOT** reduce data quality — your job is to INCREASE it.
- **DO NOT** modify files owned by LION (`templates/`, `static/`, `docs/getting_started.md`, `docs/faq.md`) or BEAR (`tests/`, `.github/`, `Dockerfile*`, `build_budget_db.py`, `refresh_data.py`).
- **EXCEPTION:** You MAY create new test files in `tests/` for your validation checks (prefix with `test_tiger_`).
- Mark each TODO as DONE in-line when you complete it.
- Run `pytest tests/test_validate_budget_db.py tests/test_validation.py tests/test_api_models.py -v` after changes.

---

## Task List (execute in order)

### TIGER-001: Add cross-year budget consistency validation
**Roadmap:** 1.B6-i | **Files:** `validate_budget_db.py`, `utils/validation.py` | **Complexity:** MEDIUM | **Tokens:** ~2,500 | **Time:** ~15 min
**Dependencies:** None

Detect anomalous year-over-year budget changes:
1. Add `check_yoy_budget_anomalies()` to `validate_budget_db.py`
2. For each (organization, account, exhibit_type) group, compare adjacent fiscal years
3. Flag rows where `abs(amount_new - amount_old) / max(amount_old, 1)` > 10x (1000% change)
4. Severity: WARNING (large changes may be legitimate policy shifts)
5. Return list of ValidationIssue with sample values
6. Register in `validate_all()` check list
7. Write test in `tests/test_tiger_validation.py`

**Acceptance:** `python validate_budget_db.py` includes YoY anomaly check; test passes.

---

### TIGER-002: Add appropriation title consistency validation
**Roadmap:** 1.B6-j | **Files:** `validate_budget_db.py` | **Complexity:** LOW | **Tokens:** ~1,500 | **Time:** ~10 min
**Dependencies:** None

Detect the same appropriation code used with different titles:
1. Add `check_appropriation_title_consistency()` to `validate_budget_db.py`
2. Query: `SELECT account, COUNT(DISTINCT account_title) as title_count FROM budget_lines GROUP BY account HAVING title_count > 1`
3. For each inconsistent account, report the distinct titles found
4. Severity: WARNING
5. Register in `validate_all()` check list
6. Write test in `tests/test_tiger_validation.py`

**Acceptance:** Check finds title inconsistencies; test verifies detection.

---

### TIGER-003: Add line item rollup reconciliation
**Roadmap:** 1.B6-k | **Files:** `validate_budget_db.py` | **Complexity:** MEDIUM | **Tokens:** ~2,500 | **Time:** ~15 min
**Dependencies:** None

Verify that detail line items sum correctly to their budget activity totals:
1. Add `check_line_item_rollups()` to `validate_budget_db.py`
2. For each (organization, account, fiscal_year, exhibit_type), sum all line item amounts
3. Compare against the budget activity total row (where `budget_activity_title` indicates a total)
4. Flag discrepancies > $1M (to allow for rounding)
5. Severity: WARNING
6. Register in `validate_all()` check list
7. Write test in `tests/test_tiger_validation.py`

**Acceptance:** Check catches intentional test discrepancy; passes on clean data.

---

### TIGER-004: Add referential integrity validation
**Roadmap:** 1.B6-l | **Files:** `validate_budget_db.py` | **Complexity:** LOW | **Tokens:** ~1,500 | **Time:** ~10 min
**Dependencies:** None

Verify all referenced values exist in lookup tables:
1. Add `check_referential_integrity()` to `validate_budget_db.py`
2. Check that all `organization_name` values in `budget_lines` exist in `services_agencies`
3. Check that all `exhibit_type` values in `budget_lines` exist in `exhibit_types`
4. Severity: ERROR for missing references
5. Register in `validate_all()` check list
6. Write test in `tests/test_tiger_validation.py`

**Acceptance:** Check detects orphaned references; passes when lookup tables are complete.

---

### TIGER-005: Add FY column completeness check
**Roadmap:** 1.B6-m | **Files:** `validate_budget_db.py` | **Complexity:** LOW | **Tokens:** ~1,000 | **Time:** ~5 min
**Dependencies:** None

Verify expected fiscal year columns exist in the schema:
1. Add `check_expected_fy_columns()` to `validate_budget_db.py`
2. Query PRAGMA table_info('budget_lines') for columns matching `amount_fy*`
3. Compare against expected set: FY2024 (actual), FY2025 (enacted + supplemental + total), FY2026 (request + reconciliation + total)
4. Severity: ERROR for missing expected columns
5. Register in `validate_all()` check list
6. Write test in `tests/test_tiger_validation.py`

**Acceptance:** Check passes on complete schema; fails when expected column is missing.

---

### TIGER-006: Integrate PDF quality metrics into validation report
**Roadmap:** 1.B5-e | **Files:** `validate_budget_db.py`, `scripts/pdf_quality_audit.py` | **Complexity:** MEDIUM | **Tokens:** ~2,000 | **Time:** ~15 min
**Dependencies:** None

Export PDF extraction quality to the main validation report:
1. Add `check_pdf_extraction_quality()` to `validate_budget_db.py`
2. Query `pdf_pages` for pages with suspiciously short text (< 50 chars excluding whitespace)
3. Query for pages where `has_tables = 1` but extracted table text is empty
4. Calculate overall extraction quality score: `good_pages / total_pages`
5. Severity: WARNING if quality score < 0.9; INFO otherwise
6. Include quality score in `data_quality_report.json` output
7. Write test in `tests/test_tiger_validation.py`

**Acceptance:** `validate_budget_db.py --json` includes `pdf_quality_score` field.

---

### TIGER-007: Add validation result export improvements
**Roadmap:** 1.B6-n | **Files:** `validate_budget_db.py` | **Complexity:** LOW | **Tokens:** ~1,500 | **Time:** ~10 min
**Dependencies:** TIGER-001 through TIGER-006

Enhance the validation JSON output:
1. Add `--html` flag that produces a styled HTML report (single file, inline CSS)
2. HTML report should show: pass/fail summary table, check details with expandable sections, timestamp
3. Add severity-based coloring (red=error, yellow=warning, blue=info)
4. Add `--threshold` flag: exit non-zero if any checks exceed threshold severity (default: error)
5. Make output format suitable for embedding in GitHub Actions step summary

**Acceptance:** `validate_budget_db.py --html > report.html` produces readable report.

---

### TIGER-008: Add feedback API endpoint stub
**Roadmap:** 4.B2-c | **Files:** `api/routes/feedback.py`, `api/app.py`, `api/models.py` | **Complexity:** LOW | **Tokens:** ~1,500 | **Time:** ~10 min
**Dependencies:** None

Create the API endpoint for user feedback (LION builds the UI):
1. Create `api/routes/feedback.py` with `POST /api/v1/feedback`
2. Add Pydantic model `FeedbackSubmission` in `api/models.py`: type (enum: bug/feature/data-issue), description (str, min 10 chars), email (optional str), page_url (optional str)
3. For now, log the feedback to a local `feedback.json` file (append mode)
4. Return 201 with `{"status": "received", "id": uuid}` on success
5. Return 501 with `{"detail": "GitHub integration not yet configured"}` note in response
6. Register router in `api/app.py`
7. Write test in `tests/test_tiger_feedback.py`

**Acceptance:** POST /api/v1/feedback with valid body returns 201; invalid body returns 422.

---

### TIGER-009: Add API response caching headers
**Roadmap:** 4.C4-c | **Files:** `api/app.py`, `api/routes/reference.py`, `api/routes/aggregations.py` | **Complexity:** LOW | **Tokens:** ~1,500 | **Time:** ~10 min
**Dependencies:** None

Add HTTP cache headers to reduce load:
1. Add `Cache-Control: public, max-age=3600` to reference data endpoints (`/api/v1/reference/*`)
2. Add `Cache-Control: public, max-age=300` to aggregation endpoints (`/api/v1/aggregations`)
3. Add `Cache-Control: private, no-cache` to search and download endpoints
4. Add `ETag` header based on database modification time (from `os.path.getmtime`)
5. Handle `If-None-Match` header — return 304 Not Modified when ETag matches
6. Write test in `tests/test_tiger_caching.py`

**Acceptance:** Reference endpoints return Cache-Control headers; ETag/304 works.

---

### TIGER-010: Add OpenAPI example responses
**Roadmap:** 3.C4-b | **Files:** `api/models.py`, `api/routes/*.py` | **Complexity:** LOW | **Tokens:** ~2,000 | **Time:** ~15 min
**Dependencies:** None

Enhance Swagger/OpenAPI documentation with realistic examples:
1. Add `model_config = {"json_schema_extra": {"examples": [...]}}` to each Pydantic response model
2. Add example responses to each endpoint using FastAPI's `responses` parameter
3. Include realistic DoD budget data in examples (real PE numbers, realistic amounts)
4. Add error response examples (400, 404, 422, 429)
5. Verify at `/docs` (Swagger UI) and `/redoc` (ReDoc)

**Acceptance:** /docs shows example request/response for every endpoint.

---

### TIGER-011: Add query performance logging
**Roadmap:** 4.C4-d | **Files:** `api/app.py`, `utils/database.py` | **Complexity:** MEDIUM | **Tokens:** ~2,000 | **Time:** ~15 min
**Dependencies:** None

Track and log slow queries for performance monitoring:
1. Add query timing wrapper in `utils/database.py` that logs queries taking > 100ms
2. Log: query text (first 200 chars), parameters count, execution time, row count
3. Add `/api/v1/health/queries` endpoint (admin-only in production) returning last 50 slow queries
4. Include in `/health/detailed` response: `slow_query_count`, `avg_query_time_ms`
5. Write test in `tests/test_tiger_performance.py`

**Acceptance:** Slow queries logged; /health/detailed includes query metrics.

---

## After completing all tasks

1. Run: `pytest tests/test_validate_budget_db.py tests/test_validation.py tests/test_api_models.py tests/test_tiger_*.py -v`
2. Run: `python validate_budget_db.py --json` to verify all new checks execute
3. Mark all TODO items as DONE in-line where you added `[Group: TIGER]` annotations
4. Update `REMAINING_TODOS.md` to reflect completed items
