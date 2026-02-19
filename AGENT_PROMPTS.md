# Agent Prompts — LION, TIGER, BEAR

These prompts are designed to be copy-pasted into three parallel Claude Code sessions.
Each agent works on its own branch (forked from `claude/add-implementation-todos-mWmoL`),
completes TODOs in a recommended order, commits after each one, and updates tracking docs.

---

## Shared Preamble (included in each prompt below)

The following context is embedded in all three prompts — you do **not** need to paste it separately.

---

## LION Agent Prompt

```
You are the LION agent. Your job is to implement all TODOs tagged [Group: LION] in this
codebase. These are frontend and user-experience tasks spanning templates/, static/css/,
static/js/, and templates/charts.html.

## Repository context

- Python 3.10+, FastAPI, SQLite (FTS5), HTMX + Jinja2 templates, Chart.js
- Tests: pytest (51 modules, 1100+ tests). Run with: pytest tests/
- Test fixtures: tests/conftest.py provides test_db, test_app, sample data
- Requirements: requirements.txt (runtime), requirements-dev.txt (test/dev)
- The API is fully functional. The frontend is partially built — you are enhancing it.
- FastAPI TestClient is available via httpx. Templates use Jinja2.
- CSS is in static/css/main.css, JS is in static/js/app.js
- HTMX powers partial page loads — templates/partials/ are HTMX fragments

## Your branch

Work on the current branch. All commits stay on this branch.

## Finding your TODOs

Run: grep -rn '\[Group: LION\]' --include='*.py' --include='*.html' --include='*.css' --include='*.js' .

Each TODO in the source files has a full description with numbered steps and acceptance
criteria. Read the full TODO comment before starting work.

The canonical list of all LION TODOs is in REMAINING_TODOS.md under "## LION".

## Execution order

Follow this dependency-aware order from REMAINING_TODOS.md:

1. CSS-001 — :focus-visible styles for keyboard nav
2. CSS-002 — .skip-link styles
3. CSS-003 — .filter-chip styles
4. OPT-CSS-001 — CSS custom property spacing scale
5. FE-004 — Skip-to-content link (needs CSS-002)
6. FE-008 — SRI integrity hashes on CDN scripts
7. FE-009 — Meta description and Open Graph tags
8. FE-001 — Amount range (min/max) filters
9. FE-002 — Appropriation filter dropdown
10. FE-003 — Active filter chips (needs FE-001, FE-002, CSS-003)
11. FE-005 — ARIA live regions for HTMX updates
12. FE-010 — Page-size selector
13. FE-012 — Contextual help tooltips
14. FE-006 — Related items section (MEDIUM — touches api/routes/frontend.py)
15. FE-007 — Download/source buttons on detail panel
16. FE-011 — Export visible columns option
17. JS-003 — Keyboard shortcut for search
18. JS-004 — Keyboard navigation for detail panel
19. OPT-JS-001 — Debounce filter form changes
20. JS-002 — Show estimated result count in download modal
21. JS-001 — Excel (.xlsx) export support (MEDIUM — touches api/routes/download.py)
22. VIZ-002 — Error handling and loading indicators for charts
23. VIZ-001 — Dynamic FY columns in charts (MEDIUM — may depend on TIGER's AGG-001)
24. VIZ-003 — Service filter on charts page
25. CSS-004 — @media print styles (MEDIUM)
26. VIZ-004 — Print-friendly chart styles (needs CSS-004)
27. VIZ-005 — Budget comparison interactive chart (MEDIUM)

## Cross-group coordination

- FE-001 and FE-006 touch api/routes/frontend.py — this is normally TIGER territory
  but you own the feature, so you make the backend changes for these filter/query additions.
- JS-001 (Excel export button) pairs with TIGER's DL-001 (Excel endpoint). If DL-001
  is not yet done when you reach JS-001, implement the JS wiring to call the endpoint
  and assume the endpoint will accept fmt=xlsx. TIGER will implement the backend.
- VIZ-001 (dynamic FY charts) pairs with TIGER's AGG-001. If AGG-001 isn't done yet,
  implement the chart-side changes to read FY columns dynamically from the JSON response
  rather than hardcoding them. The current response already includes the data.

## Workflow for each TODO

For every TODO, follow this exact cycle:

1. **Read** the full TODO comment in the source file(s) it references
2. **Implement** the change following the numbered steps in the TODO
3. **Verify** your change doesn't break anything:
   - Run: pytest tests/ -x -q
   - If you created new test-worthy behavior, add a quick test
4. **Remove the TODO comment** from the source file (the work is done)
5. **Update REMAINING_TODOS.md**: Mark the TODO's row in the LION table by changing the
   description to start with "~~" and end with "~~ ✅ DONE" (strikethrough). Example:
   | CSS-001 | 3.A7-g | `static/css/main.css` | LOW | ~1500 | ~~Add :focus-visible styles for keyboard nav~~ ✅ DONE |
6. **Commit** with a message like:
   `LION: Implement CSS-001 — :focus-visible styles for keyboard nav`
   The commit message should be a single line starting with "LION:" and the TODO ID.
7. **Compact your context** — use /compact before starting the next TODO.
   This prevents context window exhaustion across 27 tasks.

## Important rules

- Do NOT touch files primarily owned by TIGER (api/routes/search.py, api/routes/aggregations.py,
  api/routes/download.py, utils/*.py, schema_design.py) UNLESS the TODO description
  explicitly says to (FE-001, FE-006, JS-001 are the exceptions).
- Do NOT work on OH MY TODOs (they require user intervention).
- Do NOT modify test fixtures in tests/conftest.py (BEAR owns those).
- If a test fails that isn't related to your change, note it in the commit message
  but don't fix unrelated tests.
- Keep changes minimal and focused. Don't refactor surrounding code.
- Preserve existing indentation and code style.
- If you encounter a merge conflict (unlikely on isolated files), resolve it
  conservatively — prefer keeping both changes.

## When you're done

After completing all 27 TODOs (or as many as possible):
1. Run the full test suite: pytest tests/ -q
2. Update REMAINING_TODOS.md summary table: change LION count to reflect completed items
3. Final commit: "LION: Complete all LION group TODOs"
4. Push: git push
```

---

## TIGER Agent Prompt

```
You are the TIGER agent. Your job is to implement all TODOs tagged [Group: TIGER] in this
codebase. These are API, backend, and data layer tasks spanning api/, utils/, and
schema_design.py.

## Repository context

- Python 3.10+, FastAPI, SQLite (FTS5), HTMX + Jinja2 templates, Chart.js
- Tests: pytest (51 modules, 1100+ tests). Run with: pytest tests/
- Test fixtures: tests/conftest.py provides test_db, test_app, sample data
- Requirements: requirements.txt (runtime), requirements-dev.txt (test/dev)
- The API is fully functional at api/app.py with routes in api/routes/
- Database is SQLite with WAL mode, FTS5 indexes, denormalized FY columns
- Key files: api/app.py, api/database.py, api/models.py, api/routes/*.py
- Utils: utils/common.py, utils/database.py, utils/formatting.py, utils/validation.py,
  utils/config.py, utils/strings.py, utils/patterns.py
- Schema design: schema_design.py defines target normalized schema

## Your branch

Work on the current branch. All commits stay on this branch.

## Finding your TODOs

Run: grep -rn '\[Group: TIGER\]' --include='*.py' --include='*.html' --include='*.css' --include='*.js' .

Each TODO in the source files has a full description with numbered steps and acceptance
criteria. Read the full TODO comment before starting work.

The canonical list of all TIGER TODOs is in REMAINING_TODOS.md under "## TIGER".

## Execution order

Follow this dependency-aware order from REMAINING_TODOS.md:

### Phase 1: Shared utilities (foundations everything else builds on)
1. UTIL-001 — Create utils/query.py shared SQL query builder
2. UTIL-002 — Create utils/cache.py lightweight TTL cache
3. OPT-FE-001 — Extract _build_where() to use shared query builder
4. OPT-FE-002 — Cache reference data queries using TTL cache

### Phase 2: Database and config consolidation
5. OPT-UTIL-001 — Consolidate get_connection() across modules
6. OPT-UTIL-002 — Add elapsed_ms() and elapsed_sec() variants
7. OPT-CFG-001 — Consolidate env var config into Config class
8. OPT-CFG-002 — Make KnownValues.fiscal_years configurable
9. OPT-DB-001 — Implement connection pooling
10. OPT-DB-002 — Add read-only connection mode
11. OPT-DB-003 — Add friendly error on missing database
12. OPT-DBUTIL-001 — Dynamic schema introspection utility
13. OPT-DBUTIL-002 — batch_upsert() for incremental updates
14. OPT-DBUTIL-003 — QueryBuilder class for parameterized queries

### Phase 3: Formatting and DRY cleanup
15. OPT-FMT-001 — Consolidate fmt_amount() (remove API duplicate)
16. OPT-FMT-002 — Consolidate _snippet() into shared module

### Phase 4: Search API enhancements
17. SEARCH-001 — BM25 relevance scoring
18. SEARCH-002 — Structured filter support
19. SEARCH-003 — Improved snippet generation with HTML highlighting
20. SEARCH-004 — Search suggestions/autocomplete endpoint

### Phase 5: Aggregations and downloads
21. AGG-001 — Dynamic FY columns in aggregations (needs OPT-DBUTIL-001)
22. AGG-002 — Percentage and YoY delta calculations
23. OPT-AGG-001 — Server-side aggregation caching
24. DL-001 — Excel (.xlsx) export format
25. DL-002 — Keyword search filter for downloads
26. DL-003 — X-Total-Count header
27. OPT-DL-001 — DRY: Use shared WHERE builder in download route

### Phase 6: App middleware
28. APP-001 — Handle proxy/forwarded IPs in rate limiter
29. APP-002 — Rate limit memory cleanup
30. APP-003 — Structured JSON logging
31. APP-004 — CORS middleware

### Phase 7: Validation
32. VAL-001 — Cross-exhibit consistency validation
33. VAL-002 — Year-over-year outlier detection
34. VAL-003 — Validation result export to JSON

### Phase 8: Schema evolution (do last — highest risk)
35. SCHEMA-001 — FY2027+ schema migration support
36. SCHEMA-002a — Compatibility view for normalized tables
37. SCHEMA-002b — Update build pipeline for normalized tables
38. SCHEMA-002c — Migrate API routes to normalized tables
39. SCHEMA-003 — Database integrity check

## Cross-group coordination

- LION will touch api/routes/frontend.py for FE-001 and FE-006. Your OPT-FE-001
  (shared WHERE builder) should be done first so LION can use it. If there's a conflict,
  your utils/query.py is the source of truth.
- LION's JS-001 will call the xlsx endpoint you create in DL-001. Make sure
  /api/v1/download?fmt=xlsx works.
- LION's VIZ-001 depends on your AGG-001 (dynamic FY columns). Try to finish AGG-001
  before the halfway point.
- BEAR will add tests that exercise your endpoints. Your changes should not break
  existing test contracts.

## Workflow for each TODO

For every TODO, follow this exact cycle:

1. **Read** the full TODO comment in the source file(s) it references
2. **Implement** the change following the numbered steps in the TODO
3. **Test** your change:
   - Run: pytest tests/ -x -q
   - For new utilities (utils/query.py, utils/cache.py), write tests in a new
     test file (tests/test_query_utils.py, tests/test_cache_utils.py)
   - For API changes, verify with existing API tests
4. **Remove the TODO comment** from the source file (the work is done)
5. **Update REMAINING_TODOS.md**: Mark the TODO's row in the TIGER table by changing the
   description to start with "~~" and end with "~~ ✅ DONE" (strikethrough). Example:
   | UTIL-001 | OPT-FE-001 | `utils/__init__.py`, new `utils/query.py` | MEDIUM | ~2500 | ~~Create shared SQL query builder~~ ✅ DONE |
6. **Commit** with a message like:
   `TIGER: Implement UTIL-001 — shared SQL query builder`
   The commit message should be a single line starting with "TIGER:" and the TODO ID.
7. **Compact your context** — use /compact before starting the next TODO.
   This prevents context window exhaustion across 39 tasks.

## Important rules

- Do NOT touch files primarily owned by LION (templates/, static/) unless a TODO
  explicitly requires it.
- Do NOT touch files primarily owned by BEAR (tests/conftest.py, .github/, Dockerfile,
  docker-compose.yml, build_budget_db.py, refresh_data.py) unless a TODO explicitly
  requires it. Exception: SCHEMA-002b touches build_budget_db.py — that's expected.
- Do NOT work on OH MY TODOs.
- When creating new utility modules (utils/query.py, utils/cache.py), also update
  utils/__init__.py to export the new symbols and add them to __all__.
- For DRY refactors: after extracting shared code, update all call sites and verify
  tests still pass before committing.
- Keep existing public API signatures stable — don't rename functions that other
  modules import unless you update all importers.
- If you encounter a test failure unrelated to your change, note it in the commit
  message but don't fix unrelated tests.

## When you're done

After completing all 39 TODOs (or as many as possible):
1. Run the full test suite: pytest tests/ -q
2. Update REMAINING_TODOS.md summary table: change TIGER count to reflect completed items
3. Final commit: "TIGER: Complete all TIGER group TODOs"
4. Push: git push
```

---

## BEAR Agent Prompt

```
You are the BEAR agent. Your job is to implement all TODOs tagged [Group: BEAR] in this
codebase. These are infrastructure, testing, pipeline, and documentation tasks spanning
tests/, .github/, Dockerfile, docker-compose.yml, build_budget_db.py, refresh_data.py,
deployment_design.py, and docs/.

## Repository context

- Python 3.10+, FastAPI, SQLite (FTS5), HTMX + Jinja2 templates, Chart.js
- Tests: pytest (51 modules, 1100+ tests). Run with: pytest tests/
- Test fixtures: tests/conftest.py provides test_db, test_app, sample data
- Requirements: requirements.txt (runtime), requirements-dev.txt (test/dev)
- CI: .github/workflows/ci.yml runs pytest
- Docker: Dockerfile + docker-compose.yml for containerized deployment
- Build pipeline: build_budget_db.py ingests Excel/PDF into SQLite
- Refresh pipeline: refresh_data.py coordinates download + rebuild
- API docs: docs/wiki/API-Reference.md (currently placeholder)

## Your branch

Work on the current branch. All commits stay on this branch.

## Finding your TODOs

Run: grep -rn '\[Group: BEAR\]' --include='*.py' --include='*.html' --include='*.css' --include='*.js' --include='*.yml' --include='*.md' .

Each TODO in the source files has a full description with numbered steps and acceptance
criteria. Read the full TODO comment before starting work.

The canonical list of all BEAR TODOs is in REMAINING_TODOS.md under "## BEAR".

## Execution order

Follow this dependency-aware order from REMAINING_TODOS.md:

### Phase 1: Quick Docker fixes
1. DOCKER-004 — Remove deprecated "version" key from docker-compose.yml
2. DOCKER-001 — Add templates/ and static/ to Dockerfile COPY
3. DOCKER-003 — Add templates/static volume mounts for dev hot-reload
4. DOCKER-002 — Production security hardening in Dockerfile

### Phase 2: CI/CD improvements
5. CI-001 — Add test coverage reporting to ci.yml
6. CI-002 — Add mypy type checking step
7. CI-003 — Add Docker build validation step

### Phase 3: Build pipeline enhancements
8. BUILD-003 — Configurable PDF extraction timeout per page
9. BUILD-001 — Structured failure log + --retry-failures flag
10. BUILD-002 — Dynamic fiscal year columns (auto ALTER TABLE)
11. OPT-BUILD-001 — Parallelize Excel ingestion with ProcessPoolExecutor

### Phase 4: Refresh pipeline
12. REFRESH-004 — Refresh progress file for external monitoring
13. REFRESH-003 — Automatic rollback on failed refresh
14. REFRESH-005 — --schedule flag for periodic refresh

### Phase 5: Testing gaps (new test files)
15. TEST-001 — End-to-end frontend route tests (tests/test_frontend_routes.py)
16. TEST-003 — Download endpoint streaming tests (tests/test_download_streaming.py)
17. TEST-004 — Rate limiter behavior tests (tests/test_rate_limiter.py)
18. TEST-002 — Chart data contract tests (tests/test_charts_data.py)
19. TEST-005 — Performance regression smoke tests (tests/test_performance.py)
20. TEST-006 — Static accessibility checks (tests/test_accessibility.py)

### Phase 6: Deployment
21. DEPLOY-001 — /health/detailed metrics endpoint
22. DEPLOY-003 — Content Security Policy headers
23. DEPLOY-002 — Database backup script (scripts/backup_db.py)
24. DEPLOY-004 — Staging environment config (docker-compose.staging.yml)
25. DEPLOY-005 — Write CONTRIBUTING.md

### Phase 7: Documentation
26. DOC-001 — Populate API Reference wiki page with endpoint docs + examples

## Cross-group coordination

- TIGER is modifying api/ routes and utils/ concurrently. Your new tests (TEST-001
  through TEST-006) should test the API as it currently exists. If a test fails because
  TIGER changed an endpoint signature, that's expected — note it and move on.
- DEPLOY-001 (/health/detailed) and DEPLOY-003 (CSP headers) touch api/app.py which
  TIGER also modifies. Keep your changes minimal and additive (new endpoint, new
  middleware) to minimize merge conflicts.
- BUILD-002 (dynamic FY columns) overlaps conceptually with TIGER's OPT-DBUTIL-001
  and AGG-001. Your change is in build_budget_db.py (the ingestion side); TIGER's
  is in the query/API side. They're complementary, not conflicting.
- DOC-001 documents the API as it exists now. If TIGER adds new endpoints or parameters,
  those can be documented in a follow-up.

## Workflow for each TODO

For every TODO, follow this exact cycle:

1. **Read** the full TODO comment in the source file(s) it references
2. **Implement** the change following the numbered steps in the TODO
3. **Verify** your change:
   - For test files: Run the new test file specifically: pytest tests/test_NEW_FILE.py -v
   - Then run full suite: pytest tests/ -x -q
   - For Docker/CI changes: Validate syntax (yamllint or visual inspection)
   - For build_budget_db.py: Ensure imports work: python -c "import build_budget_db"
   - For docs: Verify markdown renders correctly (no broken links/tables)
4. **Remove the TODO comment** from the source file (the work is done)
5. **Update REMAINING_TODOS.md**: Mark the TODO's row in the BEAR table by changing the
   description to start with "~~" and end with "~~ ✅ DONE" (strikethrough). Example:
   | DOCKER-004 | — | `docker-compose.yml` | LOW | ~1000 | ~~Remove deprecated version key~~ ✅ DONE |
6. **Commit** with a message like:
   `BEAR: Implement DOCKER-004 — remove deprecated version key`
   The commit message should be a single line starting with "BEAR:" and the TODO ID.
7. **Compact your context** — use /compact before starting the next TODO.
   This prevents context window exhaustion across 26 tasks.

## Important rules

- Do NOT touch files primarily owned by LION (templates/, static/) unless a TODO
  explicitly requires it.
- Do NOT touch files primarily owned by TIGER (api/routes/, utils/) unless a TODO
  explicitly requires it. Exceptions: DEPLOY-001 and DEPLOY-003 add to api/app.py —
  use additive changes only (new routes, new middleware).
- Do NOT work on OH MY TODOs.
- When writing new test files, follow the patterns in existing tests:
  - Use the fixtures from conftest.py (test_db, test_app)
  - Use FastAPI TestClient for HTTP tests
  - Use descriptive test names: test_<what>_<expected_behavior>
- For CI yml changes: use proper GitHub Actions syntax and indent with 2 spaces.
- For Dockerfile changes: follow multi-stage build patterns if present.
- If pytest fails on import (missing dependency), note it but don't modify requirements.txt
  without verifying the dependency is appropriate.

## When you're done

After completing all 26 TODOs (or as many as possible):
1. Run the full test suite: pytest tests/ -q
2. Update REMAINING_TODOS.md summary table: change BEAR count to reflect completed items
3. Final commit: "BEAR: Complete all BEAR group TODOs"
4. Push: git push
```

---

## Launch Checklist

Before starting the three agents:

1. **Create three branches** from `claude/add-implementation-todos-mWmoL`:
   ```bash
   git checkout claude/add-implementation-todos-mWmoL
   git checkout -b lion/implement-todos
   git checkout -b tiger/implement-todos
   git checkout -b bear/implement-todos
   ```
   Or have each agent work on `claude/add-implementation-todos-mWmoL` directly and merge
   conflicts afterward (riskier but simpler).

2. **Install dev dependencies** (if not already):
   ```bash
   pip install -r requirements-dev.txt
   ```

3. **Verify tests pass** before starting:
   ```bash
   pytest tests/ -q
   ```

4. **After all three finish**, merge the branches:
   ```bash
   git checkout claude/add-implementation-todos-mWmoL
   git merge lion/implement-todos
   git merge tiger/implement-todos
   git merge bear/implement-todos
   # Resolve any conflicts (should be minimal — mostly REMAINING_TODOS.md)
   ```
