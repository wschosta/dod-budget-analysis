# Remaining TODOs

Updated: 2026-02-19 (synced with actual implementation state)

This document catalogs all TODO items across the codebase, organized by agent
group assignment and priority. Each TODO is sized for an agent to work through
without user intervention (except `OH MY` group items).

---

## Agent Group Assignments

| Group | Focus Area | File Ownership | Agent Can Run Autonomously |
|-------|-----------|----------------|---------------------------|
| **LION** | Frontend & User Experience | `templates/`, `static/`, charts | Yes |
| **TIGER** | API, Backend & Data Layer | `api/`, `utils/`, `schema_design.py` | Yes |
| **BEAR** | Infrastructure, Testing & Pipeline | `tests/`, `.github/`, `Dockerfile`, `build_budget_db.py`, `refresh_data.py`, `docs/design/deployment_design.py`, docs | Yes |
| **OH MY** | Requires User / External Resources | Various (network, cloud, corpus) | **No — needs human** |

---

## Summary by Group

| Group | Previously Done | New Tasks | Est. New Tokens | Autonomous |
|-------|----------------|-----------|-----------------|------------|
| LION | 27/27 ✅ | 10 new | ~17,000 | Yes |
| TIGER | 35/35 ✅ | 11 new ✅ ALL DONE | ~20,500 | Yes |
| BEAR | 25/25 ✅ | 12 new | ~26,000 | Yes |
| OH MY | — | 12 (unchanged) | ~18,500 | **No — needs human** |
| **Total** | **87 done** | **45 new** | **~82,000** | |

**Instruction files:** See `LION_INSTRUCTIONS.md`, `TIGER_INSTRUCTIONS.md`, `BEAR_INSTRUCTIONS.md`, `OH_MY_INSTRUCTIONS.md` for prompt-ready agent instructions.

---

## LION — Frontend & User Experience

### Filters & Interaction (templates/index.html, api/routes/frontend.py)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| FE-001 | 3.A3-c | `templates/index.html`, `api/routes/frontend.py` | LOW | ~1500 | ~~Add amount range (min/max) filters to filter sidebar~~ ✅ DONE |
| FE-002 | 3.A3-d | `templates/index.html`, `api/routes/frontend.py` | LOW | ~1500 | ~~Add appropriation filter dropdown~~ ✅ DONE |
| FE-003 | 3.A3-e | `templates/partials/results.html`, `static/css/main.css` | LOW | ~1000 | ~~Add active filter chips above results~~ ✅ DONE |
| FE-010 | 3.A4-c | `templates/partials/results.html`, `api/routes/frontend.py` | LOW | ~1500 | ~~Add page-size selector to pagination~~ ✅ DONE |
| FE-011 | 3.A4-d | `templates/partials/results.html`, `api/routes/download.py` | LOW | ~1000 | ~~Export visible columns only option~~ ✅ DONE |
| FE-012 | 3.C5-a | `templates/index.html`, `templates/partials/results.html` | LOW | ~1500 | ~~Add contextual help tooltips to all labels~~ ✅ DONE |

### Detail Panel (templates/partials/detail.html, api/routes/frontend.py)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| FE-006 | 3.A6-b | `templates/partials/detail.html`, `api/routes/frontend.py` | MEDIUM | ~3000 | ~~Add "Related Items" section across fiscal years~~ ✅ DONE |
| FE-007 | 3.A6-c | `templates/partials/detail.html` | LOW | ~1000 | ~~Add "Download This Item" and "Source Document" buttons~~ ✅ DONE |

### Accessibility (templates/base.html, static/css/main.css)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| FE-004 | 3.A7-c | `templates/base.html`, `static/css/main.css` | LOW | ~1000 | ~~Add skip-to-content link~~ ✅ DONE |
| FE-005 | 3.A7-d | `templates/base.html`, `templates/index.html` | MEDIUM | ~2000 | ~~Add ARIA live regions for HTMX updates~~ ✅ DONE |
| FE-008 | 3.A7-e | `templates/base.html` | LOW | ~1000 | ~~Add SRI integrity hashes to CDN scripts~~ ✅ DONE |
| FE-009 | 3.A7-f | `templates/base.html` | LOW | ~800 | ~~Add meta description and Open Graph tags~~ ✅ DONE |

### CSS (static/css/main.css)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| CSS-001 | 3.A7-g | `static/css/main.css` | LOW | ~1500 | ~~Add :focus-visible styles for keyboard nav~~ ✅ DONE |
| CSS-002 | 3.A7-h | `static/css/main.css` | LOW | ~1000 | ~~Add .skip-link styles~~ ✅ DONE |
| CSS-003 | 3.A7-i | `static/css/main.css` | LOW | ~1500 | ~~Add .filter-chip styles~~ ✅ DONE |
| CSS-004 | 3.A7-j | `static/css/main.css` | MEDIUM | ~2000 | ~~Add @media print styles~~ ✅ DONE |
| OPT-CSS-001 | — | `static/css/main.css` | LOW | ~1000 | ~~Add CSS custom property spacing scale~~ ✅ DONE |

### JavaScript (static/js/app.js)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| JS-001 | 3.A5-b | `static/js/app.js`, `api/routes/download.py` | MEDIUM | ~2000 | ~~Add Excel (.xlsx) export support~~ ✅ DONE |
| JS-002 | 3.A5-c | `static/js/app.js` | LOW | ~1500 | ~~Show estimated result count in download modal~~ ✅ DONE |
| JS-003 | 3.A3-f | `static/js/app.js` | LOW | ~1000 | ~~Add keyboard shortcut for search (/ or Ctrl+K)~~ ✅ DONE |
| JS-004 | 3.A6-d | `static/js/app.js` | LOW | ~1000 | ~~Add keyboard navigation for detail panel~~ ✅ DONE |
| OPT-JS-001 | — | `static/js/app.js` | LOW | ~1000 | ~~Debounce filter form changes~~ ✅ DONE |

### Charts & Visualization (templates/charts.html)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| VIZ-001 | 3.B1-b | `templates/charts.html`, `api/routes/aggregations.py` | MEDIUM | ~2500 | ~~Make chart FY columns dynamic~~ ✅ DONE |
| VIZ-002 | 3.B1-c | `templates/charts.html` | LOW | ~1500 | ~~Add error handling and loading indicators~~ ✅ DONE |
| VIZ-003 | 3.B2-b | `templates/charts.html` | LOW | ~1500 | ~~Add service filter to charts page~~ ✅ DONE |
| VIZ-004 | 3.B3-b | `templates/charts.html`, `static/css/main.css` | MEDIUM | ~2000 | ~~Add print-friendly chart styles~~ ✅ DONE |
| VIZ-005 | 3.B4-a | `templates/charts.html` | MEDIUM | ~3000 | ~~Add budget comparison interactive chart~~ ✅ DONE |

---

## TIGER — API, Backend & Data Layer

### Search API (api/routes/search.py)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| SEARCH-001 | — | `api/routes/search.py` | MEDIUM | ~2500 | ~~Add BM25 relevance scoring~~ ✅ DONE |
| SEARCH-002 | — | `api/routes/search.py` | LOW | ~1500 | ~~Add structured filter support (FY, service, exhibit)~~ ✅ DONE |
| SEARCH-003 | — | `api/routes/search.py`, `utils/formatting.py` | LOW | ~1500 | ~~Improve snippet generation with HTML highlighting~~ ✅ DONE |
| SEARCH-004 | — | `api/routes/search.py` | MEDIUM | ~2000 | ~~Add search suggestions/autocomplete endpoint~~ ✅ DONE |

### Aggregations API (api/routes/aggregations.py)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| AGG-001 | — | `api/routes/aggregations.py`, `api/models.py` | MEDIUM | ~2500 | ~~Make aggregation FY columns dynamic~~ ✅ DONE |
| AGG-002 | — | `api/routes/aggregations.py`, `api/models.py` | LOW | ~1500 | ~~Add percentage and YoY delta calculations~~ ✅ DONE |
| OPT-AGG-001 | — | `api/routes/aggregations.py` | LOW | ~1000 | ~~Add server-side aggregation caching~~ ✅ DONE |

### Download API (api/routes/download.py)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| DL-001 | 3.A5-b | `api/routes/download.py` | MEDIUM | ~2500 | ~~Add Excel (.xlsx) export format~~ ✅ DONE |
| DL-002 | — | `api/routes/download.py` | LOW | ~1500 | ~~Add keyword search filter to downloads~~ ✅ DONE |
| DL-003 | — | `api/routes/download.py` | LOW | ~1000 | ~~Add X-Total-Count header for progress tracking~~ ✅ DONE |
| OPT-DL-001 | — | `api/routes/download.py` | MEDIUM | ~2000 | ~~DRY: Use shared WHERE builder~~ ✅ DONE |

### App & Middleware (api/app.py)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| APP-001 | 4.C4-b | `api/app.py` | MEDIUM | ~2000 | ~~Handle proxy/forwarded IPs in rate limiter~~ ✅ DONE |
| APP-002 | 4.C4-c | `api/app.py` | LOW | ~1500 | ~~Rate limit memory cleanup (prevent unbounded growth)~~ ✅ DONE |
| APP-003 | 4.C3-b | `api/app.py` | LOW | ~1500 | ~~Add structured JSON logging for production~~ ✅ DONE |
| APP-004 | — | `api/app.py` | LOW | ~1500 | ~~Add CORS middleware for external API consumers~~ ✅ DONE |

### Database (api/database.py)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| OPT-DB-001 | — | `api/database.py` | MEDIUM | ~2500 | ~~Implement connection pooling~~ ✅ DONE |
| OPT-DB-002 | — | `api/database.py` | LOW | ~1000 | ~~Add read-only connection mode~~ ✅ DONE |
| OPT-DB-003 | — | `api/database.py` | LOW | ~800 | ~~Add friendly error on missing database~~ ✅ DONE |

### Shared Utilities (utils/)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| UTIL-001 | OPT-FE-001 | `utils/__init__.py`, new `utils/query.py` | MEDIUM | ~2500 | ~~Create shared SQL query builder (DRY across 3 routes)~~ ✅ DONE |
| UTIL-002 | — | `utils/__init__.py`, new `utils/cache.py` | LOW | ~1500 | ~~Create lightweight in-memory TTL cache~~ ✅ DONE |
| OPT-FE-001 | — | `api/routes/frontend.py` | MEDIUM | ~2000 | ~~Extract _build_where() into shared utility~~ ✅ DONE |
| OPT-FE-002 | — | `api/routes/frontend.py` | LOW | ~1500 | ~~Cache reference data queries (TTL)~~ ✅ DONE |
| OPT-FMT-001 | — | `utils/formatting.py`, `api/app.py` | LOW | ~1000 | ~~Consolidate fmt_amount() (remove API inline duplicate)~~ ✅ DONE |
| OPT-FMT-002 | — | `utils/formatting.py`, `api/routes/search.py` | LOW | ~1000 | ~~Consolidate _snippet() into shared module~~ ✅ DONE |
| OPT-UTIL-001 | — | `utils/common.py`, `api/database.py` | LOW | ~1500 | ~~Consolidate get_connection() across modules~~ ✅ DONE |
| OPT-UTIL-002 | — | `utils/common.py` | LOW | ~1000 | ~~Add elapsed_ms() and elapsed_sec() variants~~ ✅ DONE |
| OPT-DBUTIL-001 | — | `utils/database.py` | MEDIUM | ~2500 | ~~Add dynamic schema introspection utility~~ ✅ DONE |
| OPT-DBUTIL-002 | — | `utils/database.py` | LOW | ~1500 | ~~Add batch_upsert() for incremental updates~~ ✅ DONE |
| OPT-DBUTIL-003 | — | `utils/database.py` | LOW | ~1000 | ~~Add QueryBuilder class for safe parameterized queries~~ ✅ DONE |

### Schema & Data Model (schema_design.py)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| SCHEMA-001 | 2.A5-c | `schema_design.py` | MEDIUM | ~3000 | ~~Add FY2027+ schema migration support~~ ✅ DONE |
| SCHEMA-002a | 2.B1-a-1 | `schema_design.py` | MEDIUM | ~3000 | ~~Create compatibility view for normalized tables~~ ✅ DONE |
| SCHEMA-002b | 2.B1-a-2 | `build_budget_db.py`, `schema_design.py` | MEDIUM | ~3000 | ~~Update build pipeline to write normalized tables~~ ✅ DONE |
| SCHEMA-002c | 2.B1-a-3 | `api/routes/*.py` | MEDIUM | ~2000 | ~~Migrate API routes to normalized tables~~ ✅ DONE |
| SCHEMA-003 | — | `validate_budget_db.py` | LOW | ~1500 | ~~Add database integrity check (PRAGMA + FTS sync)~~ ✅ DONE |

### Validation (utils/validation.py)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| VAL-001 | — | `utils/validation.py` | MEDIUM | ~2500 | ~~Add cross-exhibit consistency validation (P-1 vs P-5)~~ ✅ DONE |
| VAL-002 | — | `utils/validation.py` | LOW | ~1500 | ~~Add year-over-year outlier detection~~ ✅ DONE |
| VAL-003 | — | `utils/validation.py`, `validate_budget_db.py` | LOW | ~1000 | ~~Add validation result export to JSON~~ ✅ DONE |

### Configuration (utils/config.py)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| OPT-CFG-001 | — | `utils/config.py`, `api/app.py`, `api/database.py` | MEDIUM | ~2000 | ~~Consolidate all env var config into Config class~~ ✅ DONE |
| OPT-CFG-002 | — | `utils/config.py` | LOW | ~1000 | ~~Make KnownValues.fiscal_years configurable~~ ✅ DONE |

---

## BEAR — Infrastructure, Testing & Pipeline

### Build Pipeline (build_budget_db.py)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| BUILD-001 | 1.A6-a | `build_budget_db.py` | MEDIUM | ~3000 | ~~Implement structured failure log + `--retry-failures`~~ ✅ DONE |
| BUILD-002 | 1.B3-d | `build_budget_db.py` | MEDIUM | ~4000 | ~~Make fiscal year columns dynamic (auto ALTER TABLE)~~ ✅ DONE |
| BUILD-003 | 1.B5-d | `build_budget_db.py` | LOW | ~2000 | ~~Add configurable PDF extraction timeout per page~~ ✅ DONE |
| OPT-BUILD-001 | — | `build_budget_db.py` | MEDIUM | ~3500 | ~~Parallelize Excel ingestion with ProcessPoolExecutor~~ ✅ DONE |

### Refresh Pipeline (refresh_data.py)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| REFRESH-003 | — | `refresh_data.py` | MEDIUM | ~2500 | ~~Add automatic rollback on failed refresh~~ ✅ DONE |
| REFRESH-004 | — | `refresh_data.py` | LOW | ~1500 | ~~Add refresh progress file for external monitoring~~ ✅ DONE |
| REFRESH-005 | — | `refresh_data.py` | LOW | ~1000 | ~~Add `--schedule` flag for periodic refresh~~ ✅ DONE |

### Testing (tests/conftest.py, new test files)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| TEST-001 | — | `tests/test_frontend_routes.py` | MEDIUM | ~3000 | ~~End-to-end frontend route tests with TestClient~~ ✅ DONE |
| TEST-002 | — | `tests/test_charts_data.py` | MEDIUM | ~2500 | ~~Chart data contract tests + edge cases~~ ✅ DONE |
| TEST-003 | — | `tests/test_download_streaming.py` | LOW | ~1500 | ~~Download endpoint streaming tests~~ ✅ DONE |
| TEST-004 | — | `tests/test_rate_limiter.py` | LOW | ~1500 | ~~Rate limiter behavior tests~~ ✅ DONE |
| TEST-005 | — | `tests/test_performance.py` | MEDIUM | ~2000 | ~~Performance regression smoke tests~~ ✅ DONE |
| TEST-006 | — | `tests/test_accessibility.py` | LOW | ~1500 | ~~Static accessibility checks on HTML output~~ ✅ DONE |

### Deployment & Docker

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| DEPLOY-001 | 4.C7-a | `api/app.py` | MEDIUM | ~2500 | ~~Add /health/detailed metrics endpoint~~ ✅ DONE |
| DEPLOY-002 | 4.C7-b | `scripts/backup_db.py` | LOW | ~1500 | ~~Add database backup script~~ ✅ DONE |
| DEPLOY-003 | 4.C8-a | `api/app.py` | LOW | ~1500 | ~~Add Content Security Policy headers~~ ✅ DONE |
| DEPLOY-004 | 4.B4-a | `docker-compose.staging.yml` | MEDIUM | ~2000 | ~~Add staging environment configuration~~ ✅ DONE |
| DEPLOY-005 | 4.C6-b | `CONTRIBUTING.md` | LOW | ~2000 | ~~Write CONTRIBUTING.md with dev guidelines~~ ✅ DONE |
| DOCKER-001 | — | `Dockerfile` | LOW | ~1000 | ~~Add templates/ and static/ to COPY~~ ✅ DONE |
| DOCKER-002 | — | `Dockerfile` | LOW | ~1000 | ~~Add production security hardening~~ ✅ DONE |
| DOCKER-003 | — | `docker-compose.yml` | LOW | ~1000 | ~~Add templates/static volume mounts for hot-reload~~ ✅ DONE |
| DOCKER-004 | — | `docker-compose.yml` | LOW | ~1000 | ~~Remove deprecated version key~~ ✅ DONE |

### CI/CD (.github/workflows/)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| CI-001 | — | `.github/workflows/ci.yml` | LOW | ~1500 | ~~Add test coverage reporting~~ ✅ DONE |
| CI-002 | — | `.github/workflows/ci.yml` | LOW | ~1000 | ~~Add mypy type checking step~~ ✅ DONE |
| CI-003 | — | `.github/workflows/ci.yml` | LOW | ~1000 | ~~Add Docker build validation step~~ ✅ DONE |

### Documentation

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| DOC-001 | 3.C4-a | `docs/wiki/API-Reference.md` | MEDIUM | ~4000 | ~~Populate API Reference with endpoint docs + examples~~ ✅ DONE |

---

## NEW LION Tasks — Frontend Polish, Documentation & UX

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| LION-001 | 3.A3-g | `templates/errors/`, `api/routes/frontend.py` | LOW | ~1,500 | Add error page templates (404, 500) |
| LION-002 | 4.B2-b | `templates/partials/feedback.html`, `templates/base.html`, `static/js/app.js` | MEDIUM | ~2,500 | Add feedback form UI stub (modal in footer) |
| LION-003 | 3.A3-h | `templates/partials/results.html`, `static/css/main.css` | LOW | ~1,000 | Add loading skeleton for HTMX requests |
| LION-004 | 3.A3-i | `templates/partials/results.html`, `static/css/main.css` | LOW | ~800 | Add "No results" empty state with clear-filters |
| LION-005 | 3.C2-b | `scripts/generate_data_dictionary.py`, `docs/data_dictionary.md` | MEDIUM | ~3,000 | Auto-generate data dictionary from schema |
| LION-006 | 3.B1-d | `templates/charts.html`, `static/js/app.js` | LOW | ~1,500 | Add chart export (PNG download) |
| LION-007 | 3.A3-j | `templates/index.html`, `static/js/app.js` | LOW | ~1,200 | Add URL sharing for filtered views |
| LION-008 | 3.A4-e | `templates/partials/results.html`, `static/css/main.css` | LOW | ~1,000 | Add print-friendly results view |
| LION-009 | 3.B4-b | `templates/charts.html`, `static/js/app.js` | MEDIUM | ~2,000 | Enhance chart interactivity — click-to-filter |
| LION-010 | 3.A7-k | `templates/base.html`, `static/css/main.css`, `static/js/app.js` | MEDIUM | ~2,500 | Add dark mode toggle |

---

## NEW TIGER Tasks — Data Quality, API & Backend

### Data Quality Validation

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| TIGER-001 | 1.B6-i | `validate_budget_db.py`, `utils/validation.py` | MEDIUM | ~2,500 | ~~Add cross-year budget consistency validation (flag >10x YoY changes)~~ ✅ DONE |
| TIGER-002 | 1.B6-j | `validate_budget_db.py` | LOW | ~1,500 | ~~Add appropriation title consistency validation~~ ✅ DONE |
| TIGER-003 | 1.B6-k | `validate_budget_db.py` | MEDIUM | ~2,500 | ~~Add line item rollup reconciliation~~ ✅ DONE |
| TIGER-004 | 1.B6-l | `validate_budget_db.py` | LOW | ~1,500 | ~~Add referential integrity validation (budget_lines → lookup tables)~~ ✅ DONE |
| TIGER-005 | 1.B6-m | `validate_budget_db.py` | LOW | ~1,000 | ~~Add FY column completeness check~~ ✅ DONE |
| TIGER-006 | 1.B5-e | `validate_budget_db.py`, `scripts/pdf_quality_audit.py` | MEDIUM | ~2,000 | ~~Integrate PDF quality metrics into validation report~~ ✅ DONE |
| TIGER-007 | 1.B6-n | `validate_budget_db.py` | LOW | ~1,500 | ~~Add validation result export improvements (HTML report, --threshold)~~ ✅ DONE |

### API Enhancements

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| TIGER-008 | 4.B2-c | `api/routes/feedback.py`, `api/app.py`, `api/models.py` | LOW | ~1,500 | ~~Add feedback API endpoint stub (logs to feedback.json)~~ ✅ DONE |
| TIGER-009 | 4.C4-c | `api/app.py`, `api/routes/reference.py`, `api/routes/aggregations.py` | LOW | ~1,500 | ~~Add API response caching headers (Cache-Control, ETag, 304)~~ ✅ DONE |
| TIGER-010 | 3.C4-b | `api/models.py`, `api/routes/*.py` | LOW | ~2,000 | ~~Add OpenAPI example responses to all endpoints~~ ✅ DONE |
| TIGER-011 | 4.C4-d | `api/app.py`, `utils/database.py` | MEDIUM | ~2,000 | ~~Add query performance logging (slow query tracking)~~ ✅ DONE |

---

## NEW BEAR Tasks — Testing, CI/CD & Infrastructure

### New Test Suites

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| BEAR-001 | 1.C2-h | `tests/test_bear_dynamic_schema.py` | MEDIUM | ~2,500 | Add dynamic FY schema tests (ALTER TABLE, idempotency, FTS triggers) |
| BEAR-002 | 1.C2-i | `tests/test_bear_historical_compat.py` | MEDIUM | ~2,500 | Add historical data compatibility tests (FY2017-2023) |
| BEAR-003 | 1.C3-i | `tests/test_bear_validation_integration.py` | MEDIUM | ~3,000 | Add validation integration tests with 7+ intentional data errors |
| BEAR-004 | 4.C4-e | `tests/test_bear_load.py` | MEDIUM | ~2,500 | Add load testing for 100K-row datasets |
| BEAR-008 | 2.A5-d | `tests/test_bear_migration.py` | MEDIUM | ~2,500 | Add database migration framework tests |
| BEAR-009 | 4.A2-b | `tests/test_bear_docker.py` | LOW | ~1,500 | Add Dockerfile/docker-compose lint-level validation tests |
| BEAR-010 | 2.B4-b | `tests/test_bear_refresh_e2e.py` | MEDIUM | ~2,500 | Add data refresh end-to-end test (dry-run, rollback, webhook) |

### CI/CD & Deployment Prep

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| BEAR-005 | 4.B4-b | `scripts/smoke_test.py` | LOW | ~2,000 | Add smoke test script for deployment verification |
| BEAR-006 | 4.A3-b | `.github/workflows/ci.yml`, `pyproject.toml` | LOW | ~1,000 | Add CI coverage threshold enforcement (80%) |
| BEAR-007 | 4.A3-c | `.github/workflows/deploy.yml` | MEDIUM | ~2,000 | Add CD deploy workflow template (GHCR + platform placeholder) |
| BEAR-011 | 4.C4-f | `.github/workflows/ci.yml`, `scripts/profile_queries.py` | MEDIUM | ~2,500 | Add performance profiling to CI |
| BEAR-012 | — | `scripts/hooks/pre-commit-hook.py`, `CONTRIBUTING.md` | LOW | ~1,000 | Update pre-commit hook for new file location |

---

## OH MY — Requires User Intervention / External Resources

These TODOs **cannot be completed by an autonomous agent**. They require network
access to DoD websites, cloud accounts, domain registration, a downloaded document
corpus, or community review.

### Data Source Auditing — Requires Network

| ID | Roadmap | File(s) | Complexity | Tokens | Blocker |
|----|---------|---------|------------|--------|---------|
| OH-MY-001 | 1.A1-a | `dod_budget_downloader.py` | LOW | ~1,500 | Needs network + live DoD sites |
| OH-MY-002 | 1.A1-b | `dod_budget_downloader.py` | MEDIUM | ~2,500 | Needs web browsing of agency sites |
| OH-MY-003 | 1.A1-c | `dod_budget_downloader.py` | LOW | ~1,000 | Needs network access |
| OH-MY-004 | 1.A2-a | `dod_budget_downloader.py` | LOW | ~1,000 | Needs network access |
| OH-MY-005 | 1.A2-b | `dod_budget_downloader.py` | MEDIUM | ~2,000 | Depends on OH-MY-004; needs network |

### Exhibit Inventory — Requires Downloaded Corpus

| ID | Roadmap | File(s) | Complexity | Tokens | Blocker |
|----|---------|---------|------------|--------|---------|
| OH-MY-006 | 1.B1-a | `exhibit_catalog.py` | LOW | ~1,500 | Needs downloaded document corpus |

### Deployment & Launch — Requires Cloud/Domain/Community

| ID | Roadmap | File(s) | Complexity | Tokens | Blocker |
|----|---------|---------|------------|--------|---------|
| OH-MY-007 | 4.A1 | `docs/design/deployment_design.py` | MEDIUM | ~2,000 | **CRITICAL** — unblocks all deployment |
| OH-MY-008 | 4.A3-a | `.github/workflows/deploy.yml` | MEDIUM | ~2,000 | Depends on OH-MY-007; needs secrets |
| OH-MY-009 | 4.A4/4.C1-a | — | LOW | ~1,000 | Needs domain registration |
| OH-MY-010 | 3.A7-b | `docs/design/frontend_design.py` | LOW | ~1,000 | Needs running UI + Lighthouse |
| OH-MY-011 | 4.B1/4.B2-a | — | LOW | ~1,500 | Needs deployed app + secrets |
| OH-MY-012 | 4.B3/4.B4/4.C6-a | — | LOW | ~1,500 | Needs community channels |

### Documentation Verification — Depends on 1.A1 Audit

| File | Description |
|------|-------------|
| `DATA_SOURCES.md` lines 44, 62, 81, 100, 120, 140, 200 | Verify FY ranges after running 1.A1 source audit |
| `docs/wiki/Data-Sources.md` line 79 | Fill in after running downloader audit |

---

## Dependency Graph

```
NEW LION (all independent — can run in parallel):
  LION-001 through LION-010: No inter-dependencies
  LION-002 ←→ TIGER-008: Feedback form (LION) needs feedback endpoint (TIGER)
  LION-009 ←→ VIZ-005: Click-to-filter builds on existing chart interactivity

NEW TIGER (ALL DONE ✅):
  TIGER-001 through TIGER-007: Data quality tasks — ✅ ALL DONE
  TIGER-008: Feedback endpoint — ✅ DONE (pairs with LION-002)
  TIGER-009 through TIGER-011: API enhancements — ✅ ALL DONE

NEW BEAR (some sequential dependencies):
  BEAR-001 through BEAR-004: Test suites — independent of each other
  BEAR-005: Smoke test — independent
  BEAR-006: Coverage threshold — independent
  BEAR-007: Deploy workflow template — independent
  BEAR-008: Migration tests — depends on schema_design.py (already complete)
  BEAR-009: Docker lint tests — independent
  BEAR-010: Refresh e2e test — depends on refresh_data.py (already complete)
  BEAR-011: Performance profiling — independent
  BEAR-012: Pre-commit hook update — independent

Cross-group coordination:
  LION-002 + TIGER-008: Feedback form (UI) + feedback endpoint (API)
  BEAR-005 + BEAR-007: Smoke test used by deploy workflow

OH MY Dependencies (sequential) — remaining items:
  OH-MY-001 ──► OH-MY-002
       │              │
       ▼              ▼
  OH-MY-003      OH-MY-005
       │
       ▼
  OH-MY-004 ──► OH-MY-005
       │
       ▼
  OH-MY-006 (needs downloaded corpus from OH-MY-001)

  OH-MY-007 ──► OH-MY-008 ──► OH-MY-009
                    │
                    ▼
               OH-MY-010 ──► OH-MY-011 ──► OH-MY-012

Previously completed:
  LION: ✅ ALL 27/27 DONE
  TIGER: ✅ ALL 35/35 DONE
  BEAR: ✅ ALL 25/25 DONE
```

---

## Cross-File Coordination Notes

All cross-file coordination items have been resolved:

| TODO | Primary Group | Resolution |
|------|--------------|------------|
| FE-001 | LION | ✅ DONE — filter changes implemented in frontend.py |
| FE-006 | LION | ✅ DONE — related items query added to frontend.py |
| JS-001/DL-001 | LION/TIGER | ✅ DONE — TIGER endpoint + LION button both implemented |
| VIZ-001 | LION | ✅ DONE — aggregation dynamic FY + chart adaptation both done |
| OPT-FE-001 | TIGER | ✅ DONE — utils/query.py created and adopted |

---

## How to Find TODOs in Code

```bash
# All TODOs with group assignments
grep -rn 'TODO.*\[Group:' --include='*.py' --include='*.html' --include='*.css' --include='*.js' --include='*.yml' --include='*.md' .

# TODOs for a specific group
grep -rn '\[Group: LION\]' --include='*.py' --include='*.html' --include='*.css' --include='*.js' .
grep -rn '\[Group: TIGER\]' --include='*.py' --include='*.html' --include='*.css' --include='*.js' .
grep -rn '\[Group: BEAR\]' --include='*.py' --include='*.html' --include='*.css' --include='*.js' --include='*.yml' .
grep -rn '\[Group: OH MY\]' --include='*.py' .

# All TODOs by complexity
grep -rn '\[Complexity: HIGH\]' .
grep -rn '\[Complexity: MEDIUM\]' .
grep -rn '\[Complexity: LOW\]' .
```
