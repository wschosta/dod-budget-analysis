# Remaining TODOs

Updated: 2026-02-19

This document catalogs all TODO items across the codebase, organized by agent
group assignment and priority. Each TODO is sized for an agent to work through
without user intervention (except `OH MY` group items).

---

## Agent Group Assignments

| Group | Focus Area | File Ownership | Agent Can Run Autonomously |
|-------|-----------|----------------|---------------------------|
| **LION** | Frontend & User Experience | `templates/`, `static/`, charts | Yes |
| **TIGER** | API, Backend & Data Layer | `api/`, `utils/`, `schema_design.py` | Yes |
| **BEAR** | Infrastructure, Testing & Pipeline | `tests/`, `.github/`, `Dockerfile`, `build_budget_db.py`, `refresh_data.py`, `deployment_design.py`, docs | Yes |
| **OH MY** | Requires User / External Resources | Various (network, cloud, corpus) | **No — needs human** |

---

## Summary by Group

| Group | Count | Est. Total Tokens | Autonomous |
|-------|-------|-------------------|------------|
| LION | 0 remaining (27/27 ✅ DONE) | ~32,300 | Yes |
| TIGER | 0 remaining (35/35 ✅ DONE) | ~56,300 | Yes |
| BEAR | 25 | ~39,500 | Yes |
| OH MY | 12 | ~18,500 | No |
| **Total** | **94** | **~146,600** | |

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
| BUILD-001 | 1.A6-a | `build_budget_db.py` | MEDIUM | ~3000 | Implement structured failure log + `--retry-failures` |
| BUILD-002 | 1.B3-d | `build_budget_db.py` | MEDIUM | ~4000 | Make fiscal year columns dynamic (auto ALTER TABLE) |
| BUILD-003 | 1.B5-d | `build_budget_db.py` | LOW | ~2000 | Add configurable PDF extraction timeout per page |
| OPT-BUILD-001 | — | `build_budget_db.py` | MEDIUM | ~3500 | Parallelize Excel ingestion with ProcessPoolExecutor |

### Refresh Pipeline (refresh_data.py)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| REFRESH-003 | — | `refresh_data.py` | MEDIUM | ~2500 | Add automatic rollback on failed refresh |
| REFRESH-004 | — | `refresh_data.py` | LOW | ~1500 | Add refresh progress file for external monitoring |
| REFRESH-005 | — | `refresh_data.py` | LOW | ~1000 | Add `--schedule` flag for periodic refresh |

### Testing (tests/conftest.py, new test files)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| TEST-001 | — | new `tests/test_frontend_routes.py` | MEDIUM | ~3000 | End-to-end frontend route tests with TestClient |
| TEST-002 | — | new `tests/test_charts_data.py` | MEDIUM | ~2500 | Chart data contract tests + edge cases |
| TEST-003 | — | new `tests/test_download_streaming.py` | LOW | ~1500 | Download endpoint streaming tests |
| TEST-004 | — | new `tests/test_rate_limiter.py` | LOW | ~1500 | Rate limiter behavior tests |
| TEST-005 | — | new `tests/test_performance.py` | MEDIUM | ~2000 | Performance regression smoke tests |
| TEST-006 | — | new `tests/test_accessibility.py` | LOW | ~1500 | Static accessibility checks on HTML output |

### Deployment & Docker

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| DEPLOY-001 | 4.C7-a | `deployment_design.py` | MEDIUM | ~2500 | Add /health/detailed metrics endpoint |
| DEPLOY-002 | 4.C7-b | new `scripts/backup_db.py` | LOW | ~1500 | Add database backup script |
| DEPLOY-003 | 4.C8-a | `api/app.py` | LOW | ~1500 | Add Content Security Policy headers |
| DEPLOY-004 | 4.B4-a | `docker-compose.staging.yml` | MEDIUM | ~2000 | Add staging environment configuration |
| DEPLOY-005 | 4.C6-b | new `CONTRIBUTING.md` | LOW | ~2000 | Write CONTRIBUTING.md with dev guidelines |
| DOCKER-001 | — | `Dockerfile` | LOW | ~1000 | Add templates/ and static/ to COPY |
| DOCKER-002 | — | `Dockerfile` | LOW | ~1000 | Add production security hardening |
| DOCKER-003 | — | `docker-compose.yml` | LOW | ~1000 | Add templates/static volume mounts for hot-reload |
| DOCKER-004 | — | `docker-compose.yml` | LOW | ~1000 | Remove deprecated version key |

### CI/CD (.github/workflows/)

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| CI-001 | — | `.github/workflows/ci.yml` | LOW | ~1500 | Add test coverage reporting |
| CI-002 | — | `.github/workflows/ci.yml` | LOW | ~1000 | Add mypy type checking step |
| CI-003 | — | `.github/workflows/ci.yml` | LOW | ~1000 | Add Docker build validation step |

### Documentation

| ID | Roadmap | File(s) | Complexity | Tokens | Description |
|----|---------|---------|------------|--------|-------------|
| DOC-001 | 3.C4-a | `docs/wiki/API-Reference.md` | MEDIUM | ~4000 | Populate API Reference with endpoint docs + examples |

---

## OH MY — Requires User Intervention / External Resources

These TODOs **cannot be completed by an autonomous agent**. They require network
access to DoD websites, cloud accounts, domain registration, a downloaded document
corpus, or community review.

### Data Source Auditing (dod_budget_downloader.py) — Requires Network

| ID | Roadmap | File(s) | Complexity | Tokens | Blocker |
|----|---------|---------|------------|--------|---------|
| — | 1.A1-a | `dod_budget_downloader.py` | LOW | ~1500 | Needs network + live DoD sites |
| — | 1.A1-b | `dod_budget_downloader.py` | MEDIUM | ~2500 | Needs web browsing of agency sites |
| — | 1.A1-c | `dod_budget_downloader.py` | LOW | ~1000 | Needs network access |
| — | 1.A2-a | `dod_budget_downloader.py` | LOW | ~1000 | Needs network access |
| — | 1.A2-b | `dod_budget_downloader.py` | MEDIUM | ~2000 | Depends on 1.A2-a; needs network |
| — | 1.A2-c | `dod_budget_downloader.py` | MEDIUM | ~2500 | Needs network access |

### Exhibit Inventory (exhibit_catalog.py) — Requires Downloaded Corpus

| ID | Roadmap | File(s) | Complexity | Tokens | Blocker |
|----|---------|---------|------------|--------|---------|
| — | 1.B1-a | `exhibit_catalog.py` | LOW | ~1500 | Needs downloaded document corpus |

### Accessibility Audit (frontend_design.py) — Requires Running UI

| ID | Roadmap | File(s) | Complexity | Tokens | Blocker |
|----|---------|---------|------------|--------|---------|
| — | 3.A7-b | `frontend_design.py` | LOW | ~1000 | Needs Lighthouse/axe-core + running UI |

### Deployment & Launch — Requires Cloud/Domain/Community

| ID | Roadmap | File(s) | Complexity | Tokens | Blocker |
|----|---------|---------|------------|--------|---------|
| — | 4.A3-a | `deployment_design.py` | MEDIUM | ~2000 | Needs cloud account |
| — | 4.B2-a | `deployment_design.py` | MEDIUM | ~2000 | Needs secrets; depends on 4.A3-a |
| — | 4.C1-a | `deployment_design.py` | LOW | ~1000 | Needs domain registration |
| — | 4.C6-a | `deployment_design.py` | LOW | ~1500 | Needs community review |

### Documentation Verification — Depends on 1.A1 Audit

| File | Description |
|------|-------------|
| `DATA_SOURCES.md` lines 44, 62, 81, 100, 120, 140, 200 | Verify FY ranges after running 1.A1 source audit |
| `docs/wiki/Data-Sources.md` line 79 | Fill in after running downloader audit |

---

## Dependency Graph

```
OH MY Dependencies (sequential):
  1.A1-a ──► 1.A2-a ──► 1.A2-b
    │                      │
    ▼                      ▼
  DATA_SOURCES.md      1.A2-c
  verification

  4.A3-a ──► 4.B2-a ──► 4.C1-a ──► 4.C6-a

LION Suggested Order:
  CSS-001,002,003 ──► FE-004 (skip link needs CSS-002)
  FE-001,002 ──► FE-003 (chips need filters to exist)
  FE-008,009 (independent, do early)
  VIZ-002 ──► VIZ-001 ──► VIZ-003 (error handling before dynamic FY)

TIGER Suggested Order:
  UTIL-001,002 ──► OPT-FE-001,002 (shared utils before route refactors)
  OPT-DBUTIL-001 ──► AGG-001 (schema introspection before dynamic agg)
  SEARCH-001 ──► SEARCH-002 ──► SEARCH-003 (scoring before filters before snippets)
  OPT-CFG-001 ──► APP-001,003 (config consolidation before middleware changes)
  SCHEMA-001 ──► SCHEMA-002a ──► SCHEMA-002b ──► SCHEMA-002c

BEAR Suggested Order:
  DOCKER-001,004 ──► DOCKER-002,003 (basic fixes before hardening)
  BUILD-003 ──► BUILD-001 ──► BUILD-002 (small fixes before big refactors)
  TEST-001,003 ──► TEST-002 ──► TEST-004,005,006 (basic tests before advanced)
  CI-001 ──► CI-002 ──► CI-003 (coverage before type checks before Docker)
  DOC-001 (independent, can be done anytime)
```

---

## Cross-File Coordination Notes

Some TODOs span files owned by different groups. Coordinate as follows:

| TODO | Primary Group | Touches Other Group's Files | Resolution |
|------|--------------|----------------------------|------------|
| FE-001 | LION | `api/routes/frontend.py` (TIGER) | LION implements frontend.py filter changes since they own the feature |
| FE-006 | LION | `api/routes/frontend.py` (TIGER) | LION adds related items query to frontend.py |
| JS-001/DL-001 | LION/TIGER | Both need xlsx export | TIGER implements DL-001 endpoint; LION wires JS-001 button |
| VIZ-001 | LION | `api/routes/aggregations.py` (TIGER) | TIGER does AGG-001 first; LION adapts charts |
| OPT-FE-001 | TIGER | Shared utility used by LION's frontend.py | TIGER creates utils/query.py; LION adopts it |

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
