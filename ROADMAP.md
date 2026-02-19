# DoD Budget Analysis — Project Roadmap

> **Objective:** Build a public, web-facing, user-queryable database of Department of Defense budget data that allows users to filter, explore, and download results.

This roadmap is organized into four phases. Every task has a reference ID (e.g., **Step 1.A1**) so individual items can be tracked, assigned, and discussed in issues and pull requests.

---

## Phase Overview

| Phase | Title | Description |
|-------|-------|-------------|
| **0** | Project Description and Creation of Documentation | Creation of an updated readme file incorporating this roadmap as well as the appropriate skeleton for future documentation |
| **1** | Data Extraction & Normalization | Download, parse, and normalize DoD budget documents into clean, structured data |
| **2** | Database Design & Population | Design the production schema, load all data, and expose it through an API |
| **3** | Front-End & Documentation | Build a web UI for querying, filtering, and downloading data, plus user-facing docs |
| **4** | Publish, Feedback & Iteration | Deploy publicly, collect user feedback, and iterate on improvements |

---

## Phase 0 - Project Description and Creation of Documentation

**Goal:** Create a clear outline of the project and how to use it such that other parties can contribute to the development and/or easily use the results.

### 0.A — Phase 0 Tasks
| ID | Task | Details | Status |
|----|------|---------|--------|
| **0.A1** | Merge ROADMAP into README | Merge ROADMAP into README for clarity in the path forward for the project | **Complete** |
| **0.A2** | Create Wiki Skeleton | Create skeleton of wiki pages for completion as supsequent phases and tasks complete | **Complete** |

---

## Phase 1 — Data Extraction & Normalization

**Goal:** Reliably download every relevant DoD budget document and transform it into clean, structured, machine-readable data.

### 1.A — Source Coverage & Download Pipeline

| ID | Task | Details | Status |
|----|------|---------|--------|
| **1.A1** | Audit existing downloader coverage | Catalog every source the current `dod_budget_downloader.py` supports (Comptroller, Defense-Wide, Army, Navy/USMC, Air Force/Space Force). Identify gaps — e.g., Defense Logistics Agency, MDA standalone exhibits, or SOCOM. | ✅ Partially Complete — 5 main sources implemented; additional sources identified but not added. Remaining: network audit needed (TODO 1.A1-a/b/c) |
| **1.A2** | Expand fiscal-year coverage | Ensure the downloader can discover and retrieve documents for all publicly available fiscal years (currently dynamic discovery works for recent years; verify historical reach back to at least FY2017). | 🔄 In Progress — FY2025-2026 confirmed; historical reach needs network verification (TODO 1.A2-a/b/c) |
| **1.A3** | Harden download reliability | Improve retry logic, handle WAF/CAPTCHA changes on government sites, add checksum or size verification for downloaded files, and implement a manifest of expected vs. actual downloads. | ✅ Partially Complete — Smart file skipping, 3-attempt retry with exponential backoff, WAF/bot detection helper; hash verification stub remaining |
| **1.A4** | Automate download scheduling | Create a repeatable, scriptable download pipeline (CLI-only, no GUI dependency) that can be run via cron or CI to keep data current when new fiscal-year documents are published. | ✅ **Complete** — CLI `--no-gui` mode, `scripts/scheduled_download.py` orchestrator with dry-run support |
| **1.A5** | Document all data sources | Create a `DATA_SOURCES.md` file listing every URL pattern, document type, file format, and fiscal-year availability for each service and agency. | 🔄 In Progress — `DATA_SOURCES.md` exists; coverage matrix needs live audit (depends on 1.A1) |
| **1.A6** | Retry failed downloads | Write a structured failure log (`failed_downloads.json`) with URL, dest path, and browser flag for each failed file. Add a `--retry-failures` CLI flag that reads the log and re-attempts only those files. Update the GUI completion dialog to show failure URLs and a copy-retry-command button. | ⚠️ Not started |

### 1.B — Parsing & Normalization

| ID | Task | Details | Status |
|----|------|---------|--------|
| **1.B1** | Catalog all exhibit types | Enumerate every exhibit type encountered (P-1, R-1, O-1, M-1, C-1, P-5, R-2, R-3, R-4, etc.) and document the column layout and semantics for each. | ✅ Mostly Complete — `exhibit_catalog.py` (429 lines) defines column layouts for P-1, P-5, R-1, R-2, O-1, M-1, C-1, P-1R, RF-1 with `ExhibitCatalog` class; `scripts/exhibit_audit.py` scans corpus; remaining: inventory against downloaded files (needs corpus) |
| **1.B2** | Standardize column mappings | Extend `build_budget_db.py` column-mapping logic to handle all known exhibit formats consistently; add unit tests for each exhibit type with sample data. | ✅ Mostly Complete — Data-driven catalog approach implemented in `exhibit_catalog.py`; `_map_columns()`, `_merge_header_rows()`, catalog-driven detection all tested; multi-row header handling implemented |
| **1.B3** | Normalize monetary values | Ensure all dollar amounts use a consistent unit (thousands of dollars), currency-year label, and handle the distinction between Budget Authority (BA), Appropriations, and Outlays. | 🔄 In Progress — FY2024-2026 columns supported with `_safe_float()` normalization; `amount_type` field tracks BA vs appropriation; full currency-year labeling TODO |
| **1.B4** | Extract and normalize program element (PE) and line-item metadata | Parse PE numbers, line-item numbers, budget activity codes, appropriation titles, and sub-activity groups into dedicated, queryable fields. | ✅ Mostly Complete — `pe_number`, `line_item`, `budget_activity_title`, `sub_activity_title`, `appropriation_code`, `appropriation_title` all extracted; regex patterns validated in `utils/patterns.py` |
| **1.B5** | PDF text extraction quality audit | Review `pdfplumber` output for the most common PDF layouts; identify tables that extract poorly and implement targeted extraction improvements or fallback strategies. | ✅ Mostly Complete — `scripts/pdf_quality_audit.py` (312 lines) implements automated audit; `utils/pdf_sections.py` handles R-2/R-3 narrative sections; remaining: targeted improvements for identified poor extractions |
| **1.B6** | Build validation suite | Create automated checks that flag anomalies: missing fiscal years for a service, duplicate rows, zero-sum line items, column misalignment, and unexpected exhibit formats. | ✅ **Complete** — `validate_budget_db.py` (522 lines) + `utils/validation.py` (255 lines) with `ValidationRegistry`, 10+ checks, and cross-service/cross-exhibit reconciliation in `scripts/reconcile_budget_data.py` |

### 1.C — Data Pipeline Testing

| ID | Task | Details | Status |
|----|------|---------|--------|
| **1.C1** | Create representative test fixtures | Assemble a small set of real (or redacted) Excel and PDF files covering each exhibit type and each service to use in automated tests. | ✅ **Complete** — `scripts/generate_expected_output.py` creates synthetic .xlsx fixtures + expected JSON; 14 integration tests in `tests/test_fixture_integration.py`; fixtures for P-1, P-5, R-1, R-2, O-1, M-1, C-1 |
| **1.C2** | Unit tests for parsing logic | Write `pytest` tests for column detection, value normalization, exhibit-type identification, and PE/line-item extraction. | ✅ **Complete** — 1183 tests across 49 test files covering all parsing modules: `_detect_exhibit_type`, `_map_columns`, `_safe_float`, `_determine_category`, `_extract_table_text`, regex patterns, string utilities, config classes, and more |
| **1.C3** | Integration test: end-to-end pipeline | Test the full flow from raw files → SQLite database → search query, verifying row counts and known values. | ✅ **Complete** — `test_e2e_pipeline.py` + `test_fixture_integration.py` (14 tests) + API endpoint integration tests (`test_budget_lines_endpoint.py`, `test_search_endpoint.py`) |

---

## Phase 2 — Database Design & Population

**Goal:** Design a production-quality relational schema, load all extracted data, and expose it through a programmatic API.

### 2.A — Schema Design

| ID | Task | Details | Status |
|----|------|---------|--------|
| **2.A1** | Define the canonical data model | Design normalized tables that capture: fiscal year, service/agency, appropriation, budget activity, program element, line item, exhibit type, dollar amounts (by budget cycle: PB, enacted, request), and document source metadata. | ✅ **Complete** — `schema_design.py` (482 lines) defines `budget_line_items` with 29+ columns; `budget_lines` and `pdf_pages` tables in production schema |
| **2.A2** | Design lookup/reference tables | Create reference tables for: services & agencies, appropriation titles, exhibit types, budget cycles, and fiscal years — with human-readable labels and codes. | ✅ **Complete** — `services_agencies`, `appropriation_titles`, `exhibit_types`, `budget_cycles` tables created and seeded via migration; `backfill_reference_tables.py` populates from live data |
| **2.A3** | Design full-text search strategy | Decide whether to continue with SQLite FTS5 for the web deployment or migrate to PostgreSQL with `tsvector`/`tsquery`, or use an external search engine (e.g., Meilisearch). Document trade-offs. | ✅ **Complete** — SQLite FTS5 chosen; `budget_lines_fts` and `pdf_pages_fts` content-sync tables with INSERT/UPDATE/DELETE triggers; `sanitize_fts5_query()` for safe user input |
| **2.A4** | Design PDF/document metadata tables | Schema for storing page-level PDF text, table extractions, and links back to the original source document URL for provenance. | ✅ **Complete** — `pdf_pages` table with `source_file`, `source_category`, `page_number`, `page_text`, `has_tables` columns; FTS5 full-text index on page text |
| **2.A5** | Write and version database migrations | Use a migration tool (e.g., Alembic) or versioned SQL scripts so the schema can evolve without data loss. | ✅ **Complete** — `schema_design.py` implements versioned migration framework with `schema_version` table, `_current_version()`, `migrate()` (idempotent), and `create_normalized_db()` |

### 2.B — Data Loading & Quality

| ID | Task | Details | Status |
|----|------|---------|--------|
| **2.B1** | Build the production data-load pipeline | Refactor `build_budget_db.py` to target the new canonical schema. Support incremental and full-rebuild modes. | ✅ **Complete** — `build_budget_db.py` (1957 lines) supports full-rebuild and incremental modes; `build_budget_gui.py` provides tkinter interface with progress tracking |
| **2.B2** | Cross-service data reconciliation | Verify that totals from service-level exhibits roll up to Comptroller summary exhibits; flag discrepancies. | ✅ **Complete** — `scripts/reconcile_budget_data.py` (481 lines) implements `reconcile_cross_service()` and `reconcile_cross_exhibit()` (P-1 vs P-5, R-1 vs R-2) |
| **2.B3** | Generate data-quality reports | After each load, produce a summary report: row counts by service/year/exhibit, missing data, and validation warnings. | ✅ **Complete** — `validate_budget_db.py` generates `data_quality_report.json`; `scripts/pdf_quality_audit.py` audits PDF extraction quality |
| **2.B4** | Establish a data refresh workflow | Document and script the process for incorporating new fiscal-year data as it becomes available (download → parse → load → validate). | ✅ **Complete** — `refresh_data.py` implements `RefreshWorkflow` class with staged pipeline (download → parse → load → validate), dry-run support, and webhook notifications |

### 2.C — API Layer

| ID | Task | Details | Status |
|----|------|---------|--------|
| **2.C1** | Choose a web framework | Evaluate options (FastAPI, Flask, Django REST Framework) based on project needs: query flexibility, authentication (if any), and ease of deployment. Recommend and document the choice. | ✅ **Complete** — FastAPI chosen; decision documented in `docs/API_FRAMEWORK_DECISION.md` |
| **2.C2** | Design REST API endpoints | Define endpoints for: search (full-text), filtered queries (by service, year, appropriation, PE, exhibit type), aggregations (totals by service/year), and data download (CSV/JSON export). | ✅ **Complete** — Endpoint specification in `docs/API_ENDPOINT_SPECIFICATION.md`; 11 Pydantic models in `api/models.py` |
| **2.C3** | Implement core query endpoints | Build the `/search`, `/budget-lines`, `/aggregations` endpoints with pagination, sorting, and filtering parameters. | ✅ **Complete** — `api/routes/search.py` (FTS5), `api/routes/budget_lines.py` (filtered + paginated), `api/routes/aggregations.py`, `api/routes/reference.py`, `api/routes/frontend.py` |
| **2.C4** | Implement export/download endpoint | Build a `/download` endpoint that accepts the same filters as the query endpoints and returns results as CSV or JSON. Handle large result sets with streaming. | ✅ **Complete** — `api/routes/download.py` with `_iter_rows()` streaming, CSV export, configurable sort |
| **2.C5** | Add API input validation & error handling | Validate query parameters, return meaningful error messages, and set rate limits to prevent abuse. | ✅ **Complete** — FastAPI Query() validators with min/max/pattern constraints; Pydantic model validation; meaningful HTTPException messages |
| **2.C6** | Write API tests | Automated tests for each endpoint covering happy-path queries, edge cases (empty results, invalid parameters), and export formats. | ✅ **Complete** — `test_budget_lines_endpoint.py` (15), `test_search_endpoint.py` (8), `test_build_where.py` (11), `test_api_models.py` (20), `test_api_database.py` (5), `test_api_search_snippet.py` (9), `test_download_route.py` (7), `test_app_factory.py` (5), `test_frontend_helpers.py` (17), `test_reference_aggregation.py` (18) |

---

## Phase 3 — Front-End & Documentation

**Goal:** Build an intuitive web interface that lets non-technical users search, filter, explore, and download DoD budget data — with clear documentation.

### 3.A — UI Design & Core Features

| ID | Task | Details | Status |
|----|------|---------|--------|
| **3.A1** | Choose front-end technology | Evaluate options (React, Vue, Svelte, or server-rendered templates via Jinja2/HTMX). Consider team familiarity, bundle size, and accessibility. Document the choice. | ✅ **Complete** — HTMX + Jinja2 chosen; decision documented in `docs/FRONTEND_TECHNOLOGY_DECISION.md` |
| **3.A2** | Design wireframes / mockups | Create low-fidelity wireframes for: landing page, search/filter interface, results table, detail view, and download flow. | ✅ **Complete** — 8 views wireframed in `docs/UI_WIREFRAMES.md`; all templates implemented |
| **3.A3** | Build the search & filter interface | Implement a form with filters for: fiscal year, service/agency, appropriation, program element, exhibit type, and free-text search. Filters should be combinable. | ✅ **Complete** — `templates/index.html` with keyword, fiscal year, service, exhibit type, appropriation, and amount range filters; HTMX-driven updates |
| **3.A4** | Build the results table | Display query results in a sortable, paginated table. Show key columns (service, fiscal year, program, amount, exhibit type). Allow column toggling. | ✅ **Complete** — `templates/partials/results.html` with sortable columns, pagination, page-size selector, and column toggle |
| **3.A5** | Build the download feature | Allow users to download their current filtered result set as CSV or JSON. Include a "Download" button that triggers the API export endpoint. Show download progress for large files. | ✅ **Complete** — Download modal with CSV, JSON (NDJSON), and Excel (.xlsx) formats; streaming export; column subset support |
| **3.A6** | Build a detail/drill-down view | When a user clicks a budget line, show full details: all available fields, the source document (link to original PDF on DoD site), and related line items across fiscal years. | ✅ **Complete** — `templates/partials/detail.html` with full metadata, funding breakdown, related fiscal years, source document links |
| **3.A7** | Responsive design & accessibility | Ensure the UI works on mobile and tablet; meet WCAG 2.1 AA accessibility standards (keyboard navigation, screen reader support, sufficient contrast). | ✅ Mostly Complete — Skip-to-content, ARIA live regions, focus-visible styles, keyboard shortcuts, responsive breakpoints, print styles; remaining: Lighthouse/axe-core audit (needs running UI) |

### 3.B — Data Visualization (Stretch)

| ID | Task | Details | Status |
|----|------|---------|--------|
| **3.B1** | Year-over-year trend charts | For a selected program element or appropriation, display a line/bar chart showing budget amounts across fiscal years. | ✅ **Complete** — Chart.js grouped bar chart in `templates/charts.html` with dynamic FY columns |
| **3.B2** | Service/agency comparison charts | Visual comparison of budget allocations across services for a selected fiscal year. | ✅ **Complete** — Horizontal bar chart with service filter dropdown on charts page |
| **3.B3** | Top-N budget items dashboard | A summary dashboard showing the largest budget line items by various cuts (service, appropriation, program). | ✅ **Complete** — Top-10 horizontal bar chart plus budget comparison interactive chart |

### 3.C — User Documentation

| ID | Task | Details | Status |
|----|------|---------|--------|
| **3.C1** | Write a "Getting Started" guide | A plain-language guide explaining what the tool does, what data is included, and how to perform a basic search and download. | ✅ **Complete** — `docs/getting_started.md` (205 lines) written for staffers, journalists, and researchers |
| **3.C2** | Write a data dictionary | Define every field visible in the UI and API: what it means, where it comes from, and known caveats (e.g., fiscal-year transitions, restated figures). | ✅ **Complete** — `docs/data_dictionary.md` (573 lines) with all fields, reference tables, naming conventions, and 8 data quality caveats |
| **3.C3** | Write an FAQ | Address common questions: data freshness, coverage gaps, unit of measure (thousands of dollars), difference between PB/enacted/request, etc. | ✅ **Complete** — `docs/faq.md` (181 lines) covering data currency, missing years, $K meaning, PB vs enacted, reconciliation, and more |
| **3.C4** | Write API documentation | If the API is publicly accessible, provide OpenAPI/Swagger docs with example requests and responses. | ✅ **Complete** — `docs/wiki/API-Reference.md` (528 lines) with all endpoints, parameters, response schemas, and curl examples; OpenAPI metadata in `api/app.py` |
| **3.C5** | Add contextual help to the UI | Tooltips, info icons, and inline explanations on the search/filter page so users understand each filter without leaving the page. | ✅ **Complete** — CSS-based data-tooltip attributes on all filter labels and column headers in templates |
| **3.C6** | Write a methodology & limitations page | Explain how data is collected, parsed, and loaded; known limitations (e.g., PDF extraction accuracy); and how to report errors. | ✅ **Complete** — `docs/methodology.md` (207 lines) with data sources, collection process, parsing approach, 8 known limitations, and error reporting |

---

## Phase 4 — Publish, Feedback & Iteration

**Goal:** Deploy the application publicly, gather real-world feedback, and improve based on what users actually need.

### 4.A — Deployment & Infrastructure

| ID | Task | Details | Status |
|----|------|---------|--------|
| **4.A1** | Choose a hosting platform | Evaluate options (AWS, GCP, Azure, Fly.io, Railway, Render, etc.) based on cost, reliability, and ease of deployment. Document the decision. | ⚠️ Not started — requires cloud account setup |
| **4.A2** | Containerize the application | Create a `Dockerfile` (and `docker-compose.yml` if needed) that bundles the API, front-end, and database for reproducible deployment. | ✅ **Complete** — `Dockerfile` (non-root user, HEALTHCHECK), `Dockerfile.multistage` (2-stage build), `docker-compose.yml` with volume mounts and hot-reload |
| **4.A3** | Set up CI/CD pipeline | Configure GitHub Actions (or equivalent) to run tests, build the container, and deploy on push to the main branch. | ✅ Partially Complete — CI pipeline done (`ci.yml`: matrix testing, ruff, pytest+coverage, mypy, Docker build); CD deployment workflow pending (needs hosting platform) |
| **4.A4** | Configure a custom domain & TLS | Register or configure a domain name and set up HTTPS with automatic certificate renewal. | ⚠️ Not started — requires domain registration |
| **4.A5** | Set up monitoring & alerting | Implement uptime monitoring, error tracking (e.g., Sentry), and basic usage analytics (privacy-respecting) to detect problems early. | ✅ **Complete** — `/health` + `/health/detailed` endpoints with uptime, request/error counts, DB metrics, response time tracking; structured access logging middleware; rate limiting with per-IP tracking |
| **4.A6** | Implement backup & recovery | Automate database backups and document the recovery procedure. | ✅ **Complete** — `scripts/backup_db.py` with SQLite online backup API, `--keep N` pruning; staging docker-compose backup sidecar (6-hour cycle); `docs/deployment.md` documents recovery procedure |

### 4.B — Launch & Outreach

| ID | Task | Details | Status |
|----|------|---------|--------|
| **4.B1** | Soft launch to a small group | Share the tool with a small set of known users (analysts, researchers, journalists) and collect structured feedback. | ⚠️ Not started — requires deployed application |
| **4.B2** | Create a feedback mechanism | Add a "Feedback" button or form in the UI that lets users report bugs, request features, or note data issues. Route submissions to GitHub Issues. | ⚠️ Not started — requires secrets/deployment |
| **4.B3** | Write a launch announcement | Draft a blog post or README update explaining what the tool does, who it's for, and how to use it. | ⚠️ Not started |
| **4.B4** | Public launch | Announce on relevant forums, social media, and communities (defense policy, open data, civic tech). | ⚠️ Not started — `docker-compose.staging.yml` ready for staging deployment |

### 4.C — Iteration & Maintenance

| ID | Task | Details | Status |
|----|------|---------|--------|
| **4.C1** | Triage and prioritize feedback | Review all feedback, categorize (bug, feature request, data quality, UX), and prioritize for the next development cycle. | ⚠️ Not started — requires public launch and user feedback |
| **4.C2** | Implement high-priority improvements | Address the most impactful issues identified during the soft launch and public feedback rounds. | ⚠️ Not started — depends on user feedback |
| **4.C3** | Automate annual data refresh | When new President's Budget or enacted appropriations are published, the pipeline should detect and ingest them with minimal manual intervention. | ✅ **Complete** — `refresh_data.py` with 4-stage pipeline (download → build → validate → report), automatic rollback, progress tracking, `--schedule` flag; `.github/workflows/refresh-data.yml` with weekly cron |
| **4.C4** | Performance optimization | Profile and optimize slow queries, large downloads, and page-load times based on real usage patterns. | ✅ Mostly Complete — Connection pooling, FTS5 indexing, rate limiting, pagination, in-memory TTL cache, streaming exports, BM25 relevance scoring; profiling-based tuning pending real traffic |
| **4.C5** | Ongoing documentation updates | Keep the data dictionary, FAQ, and methodology page current as the data and features evolve. | ✅ Mostly Complete — Comprehensive docs in `docs/` and `docs/wiki/` (20+ files); ongoing updates needed as features evolve |
| **4.C6** | Community contribution guidelines | If the project attracts contributors, publish `CONTRIBUTING.md` with development setup, coding standards, and PR process. | ✅ **Complete** — `CONTRIBUTING.md` (261 lines) with prerequisites, dev setup, code standards, testing guide, PR process, and architecture overview |

---

## Current Project Status

**Phase 0 (Documentation):** ✅ **COMPLETE**
- README updated with features and project status
- Wiki skeleton created with performance optimizations documented (3-6x speedup achieved)
- ROADMAP established with 57 tasks across 4 phases

**Phase 1 (Data Extraction & Normalization):** ✅ **~90% COMPLETE**
- All testing tasks (1.C1-1.C3) complete with 1183 tests across 63 test files
- Parsing, normalization, and validation fully functional
- Remaining items require network access / downloaded corpus (see Remaining TODOs below)

**Phase 2 (Database Design & Population):** ✅ **COMPLETE**
- All schema design tasks (2.A1-2.A5) implemented in `schema_design.py`
- All data loading tasks (2.B1-2.B4) implemented with reconciliation and refresh workflow
- All API tasks (2.C1-2.C6) implemented with FastAPI — 6 route modules, 11 Pydantic models, 115 API-related tests

**Phase 3 (Front-End & Documentation):** ✅ **COMPLETE**
- Frontend technology decision: HTMX + Jinja2 (`docs/FRONTEND_TECHNOLOGY_DECISION.md`)
- Full web UI implemented: search/filter interface, results table, detail panel, download modal, charts page
- All 3 data visualization charts implemented (year-over-year, service comparison, top-N dashboard)
- All 6 user documentation pages complete (getting started, data dictionary, FAQ, API reference, contextual help, methodology)
- Remaining: Lighthouse/axe-core accessibility audit (requires running UI)

**Phase 4 (Publish, Feedback & Iteration):** 🔄 **~50% COMPLETE**
- Containerization complete: `Dockerfile`, `Dockerfile.multistage`, `docker-compose.yml`, `docker-compose.staging.yml`
- CI pipeline complete: matrix testing, linting, type checking, coverage, Docker build validation
- Monitoring & backup complete: `/health/detailed` metrics, `scripts/backup_db.py`, structured logging
- Automated data refresh complete: `refresh_data.py` + GitHub Actions weekly cron
- `CONTRIBUTING.md` with full development guidelines
- Remaining: hosting platform selection, domain/TLS, CD deployment workflow, feedback mechanism, public launch

### Component Summary

| Component | File(s) | Lines | Status |
|-----------|---------|-------|--------|
| **Document downloader** | `dod_budget_downloader.py` | 2,442 | ✅ Functional — 5 sources, multi-year, parallel, Playwright |
| **Database builder (CLI)** | `build_budget_db.py` | 1,957 | ✅ Functional — Excel/PDF parsing, incremental updates, dynamic FY columns, failure log + retry |
| **Database builder (GUI)** | `build_budget_gui.py` | 497 | ✅ Functional — tkinter interface with progress/ETA |
| **Schema & migrations** | `schema_design.py` | 482 | ✅ Complete — versioned migrations, reference table seeding |
| **Exhibit catalog** | `exhibit_catalog.py` | 429 | ✅ Complete — 9 exhibit types with column layouts |
| **Validation suite** | `validate_budget_db.py` + `utils/validation.py` | 777 | ✅ Complete — 10+ checks, ValidationRegistry, cross-exhibit consistency, outlier detection |
| **Search interface** | `search_budget.py` | 582 | ✅ Functional — FTS5 full-text search, BM25 scoring, export |
| **Data reconciliation** | `scripts/reconcile_budget_data.py` | 481 | ✅ Complete — cross-service + cross-exhibit checks |
| **PDF quality audit** | `scripts/pdf_quality_audit.py` | 312 | ✅ Complete — automated extraction quality scoring |
| **Refresh workflow** | `refresh_data.py` | — | ✅ Complete — staged pipeline with dry-run, webhooks, rollback, progress tracking, scheduling |
| **REST API** | `api/` (app, models, routes) | 1,239 | ✅ Complete — FastAPI with 6 route modules, CORS, CSP headers, rate limiting, connection pooling |
| **Web UI** | `templates/` + `static/` | — | ✅ Complete — HTMX + Jinja2 with search, filters, results, detail panel, download modal, charts |
| **User documentation** | `docs/` (6 guides) | — | ✅ Complete — getting started, data dictionary, FAQ, API reference, methodology, deployment |
| **Utility libraries** | `utils/` (14 modules) | 2,093 | ✅ Complete — config, database, HTTP, patterns, strings, validation, cache, query, formatting |
| **Test suite** | `tests/` (63 files) | — | ✅ **1,183 tests** — comprehensive coverage across all modules |
| **CI/CD** | `.github/workflows/` (4 files) | — | ✅ Complete — CI pipeline, data refresh, optimization tests, scheduled downloads |
| **Containerization** | `Dockerfile*`, `docker-compose*.yml` | — | ✅ Complete — production, multistage, dev, staging configurations |
| **Backup & monitoring** | `scripts/backup_db.py`, `api/app.py` | — | ✅ Complete — automated backups, /health/detailed, structured logging |

### Remaining TODOs (12 items)

All remaining items require external resources (network access, downloaded corpus, or cloud accounts):

| Category | Count | Blocker |
|----------|-------|---------|
| Data Source Auditing (1.A) | 6 | Network access to DoD websites |
| Exhibit Inventory (1.B) | 1 | Downloaded document corpus |
| Accessibility Audit (3.A) | 1 | Running UI + Lighthouse/axe-core |
| Hosting & Domain (4.A) | 2 | Cloud account + domain registration |
| Launch & Feedback (4.B) | 2 | Deployed application + secrets |
| **Total** | **12** | |

See [REMAINING_TODOS.md](REMAINING_TODOS.md) for detailed descriptions of each item.

---

## How to Reference Tasks

Use the ID column when referencing tasks in issues, PRs, or discussions:

- **In a GitHub Issue title:** `[Step 1.B2] Standardize column mappings for all exhibit types`
- **In a PR description:** `Closes Step 2.C3 — implements core query endpoints`
- **In a commit message:** `feat(api): add /budget-lines endpoint (Step 2.C3)`
- **In a discussion comment:** `This relates to Step 3.A5 — we should stream large CSV exports`

---

## Summary Statistics

| Phase | Tasks |
|-------|-------|
| Phase 1 — Data Extraction & Normalization | 15 |
| Phase 2 — Database Design & Population | 15 |
| Phase 3 — Front-End & Documentation | 15 |
| Phase 4 — Publish, Feedback & Iteration | 12 |
| **Total** | **57** |
