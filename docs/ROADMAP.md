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
| **1.A1** | Audit existing downloader coverage | Catalog every source the current `dod_budget_downloader.py` supports (Comptroller, Defense-Wide, Army, Navy/USMC, Air Force/Space Force). Identify gaps — e.g., Defense Logistics Agency, MDA standalone exhibits, or SOCOM. | ✅ **Complete** — 5 main sources implemented; network audit completed (OH-MY-001/002/003 done 2026-02-19). Additional DoD component sources (DLA, MDA, SOCOM) identified but not yet added. |
| **1.A2** | Expand fiscal-year coverage | Ensure the downloader can discover and retrieve documents for all publicly available fiscal years (currently dynamic discovery works for recent years; verify historical reach back to at least FY2017). | ✅ **Complete** — FY2025-2026 confirmed; historical reach tested (OH-MY-004/005 done 2026-02-19). FY2000-2009 gap remains (documents not publicly available in structured format). |
| **1.A3** | Harden download reliability | Improve retry logic, handle WAF/CAPTCHA changes on government sites, add checksum or size verification for downloaded files, and implement a manifest of expected vs. actual downloads. | ✅ Partially Complete — Smart file skipping, 3-attempt retry with exponential backoff, WAF/bot detection helper; hash verification stub remaining |
| **1.A4** | Automate download scheduling | Create a repeatable, scriptable download pipeline (CLI-only, no GUI dependency) that can be run via cron or CI to keep data current when new fiscal-year documents are published. | ✅ **Complete** — CLI `--no-gui` mode, `scripts/scheduled_download.py` orchestrator with dry-run support |
| **1.A5** | Document all data sources | Create a data sources reference listing every URL pattern, document type, file format, and fiscal-year availability for each service and agency. | 🔄 In Progress — `docs/user-guide/data-sources.md` exists; coverage matrix needs live audit (depends on 1.A1) |
| **1.A6** | Retry failed downloads | Write a structured failure log (`failed_downloads.json`) with URL, dest path, and browser flag for each failed file. Add a `--retry-failures` CLI flag that reads the log and re-attempts only those files. Update the GUI completion dialog to show failure URLs and a copy-retry-command button. | 🔄 Partially Started — `_failed_files` list stub exists in `downloader/gui.py`; CLI flag and JSON log not yet implemented |

### 1.B — Parsing & Normalization

| ID | Task | Details | Status |
|----|------|---------|--------|
| **1.B1** | Catalog all exhibit types | Enumerate every exhibit type encountered (P-1, R-1, O-1, M-1, C-1, P-5, R-2, R-3, R-4, etc.) and document the column layout and semantics for each. | ✅ **Complete** — `exhibit_catalog.py` (429 lines) defines column layouts for P-1, P-5, R-1, R-2, O-1, M-1, C-1, P-1R, RF-1 with `ExhibitCatalog` class; `scripts/exhibit_audit.py` scans corpus; cross-validated against corpus (OH-MY-006 done 2026-02-19) |
| **1.B2** | Standardize column mappings | Extend `build_budget_db.py` column-mapping logic to handle all known exhibit formats consistently; add unit tests for each exhibit type with sample data. | ✅ Mostly Complete — Data-driven catalog approach implemented in `exhibit_catalog.py`; `_map_columns()`, `_merge_header_rows()`, catalog-driven detection all tested; multi-row header handling implemented |
| **1.B3** | Normalize monetary values | Ensure all dollar amounts use a consistent unit (thousands of dollars), currency-year label, and handle the distinction between Budget Authority (BA), Appropriations, and Outlays. | ✅ Mostly Complete — FY2024-2026 columns with `_safe_float()` normalization; `amount_type` field tracks BA vs appropriation; currency-year detection implemented (`_detect_currency_year`, DONE 1.B3-b); exhibit→budget_type mapping implemented (`_EXHIBIT_BUDGET_TYPE`, DONE 1.B3-d); amount-unit detection and normalization (DONE 1.B3-a/c) |
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
| **3.C1** | Write a "Getting Started" guide | A plain-language guide explaining what the tool does, what data is included, and how to perform a basic search and download. | ✅ **Complete** — `docs/user-guide/getting-started.md` written for staffers, journalists, and researchers |
| **3.C2** | Write a data dictionary | Define every field visible in the UI and API: what it means, where it comes from, and known caveats (e.g., fiscal-year transitions, restated figures). | ✅ **Complete** — `docs/user-guide/data-dictionary.md` with all fields, reference tables, naming conventions, and data quality caveats |
| **3.C3** | Write an FAQ | Address common questions: data freshness, coverage gaps, unit of measure (thousands of dollars), difference between PB/enacted/request, etc. | ✅ **Complete** — `docs/user-guide/faq.md` covering data currency, missing years, $K meaning, PB vs enacted, reconciliation, and more |
| **3.C4** | Write API documentation | If the API is publicly accessible, provide OpenAPI/Swagger docs with example requests and responses. | ✅ **Complete** — `docs/developer/api-reference.md` with all endpoints, parameters, response schemas, and curl examples; OpenAPI metadata in `api/app.py` |
| **3.C5** | Add contextual help to the UI | Tooltips, info icons, and inline explanations on the search/filter page so users understand each filter without leaving the page. | ✅ **Complete** — CSS-based data-tooltip attributes on all filter labels and column headers in templates |
| **3.C6** | Write a methodology & limitations page | Explain how data is collected, parsed, and loaded; known limitations (e.g., PDF extraction accuracy); and how to report errors. | ✅ **Complete** — `docs/user-guide/methodology.md` with data sources, collection process, parsing approach, known limitations, and error reporting |

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
| **4.A6** | Implement backup & recovery | Automate database backups and document the recovery procedure. | ✅ **Complete** — `scripts/backup_db.py` with SQLite online backup API, `--keep N` pruning; staging docker-compose backup sidecar (6-hour cycle); `docs/developer/deployment.md` documents recovery procedure |

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
| **4.C3** | Keyword Explorer page | Generalized keyword search tool (`/explorer`). User-supplied keywords with fuzzy matching (prefix, acronym expansion, edit-distance). Async cache build with progress polling. PE-level preview. Drag-and-drop column picker for XLSX export. Shared backend extracted from hypersonics page. | ✅ **Complete** |
| **4.C3** | Automate annual data refresh | When new President's Budget or enacted appropriations are published, the pipeline should detect and ingest them with minimal manual intervention. | ✅ **Complete** — `refresh_data.py` with 4-stage pipeline (download → build → validate → report), automatic rollback, progress tracking, `--schedule` flag; `.github/workflows/refresh-data.yml` with weekly cron |
| **4.C4** | Performance optimization | Profile and optimize slow queries, large downloads, and page-load times based on real usage patterns. | ✅ Mostly Complete — Connection pooling, FTS5 indexing, rate limiting, pagination, in-memory TTL cache, streaming exports, BM25 relevance scoring; profiling-based tuning pending real traffic |
| **4.C5** | Ongoing documentation updates | Keep the data dictionary, FAQ, and methodology page current as the data and features evolve. | ✅ Mostly Complete — Comprehensive docs in `docs/user-guide/` and `docs/developer/` (20+ files); ongoing updates needed as features evolve |
| **4.C6** | Community contribution guidelines | If the project attracts contributors, publish `CONTRIBUTING.md` with development setup, coding standards, and PR process. | ✅ **Complete** — `CONTRIBUTING.md` (261 lines) with prerequisites, dev setup, code standards, testing guide, PR process, and architecture overview |

---

## Current Project Status

**Phase 0 (Documentation):** ✅ **COMPLETE**
- README updated with features and project status
- Wiki skeleton created with performance optimizations documented (3-6x speedup achieved)
- ROADMAP established with 57 tasks across 4 phases

**Phase 1 (Data Extraction & Normalization):** ✅ **~95% COMPLETE**
- All testing tasks (1.C1-1.C3) complete with 1,248+ tests across 63+ test files
- Parsing, normalization, and validation fully functional
- Network audits completed (OH-MY-001 through OH-MY-006, 2026-02-19)
- Remaining: retry-failures CLI (1.A6 partial), data source doc update (1.A5 minor)

**Phase 2 (Database Design & Population):** ✅ **COMPLETE**
- All schema design tasks (2.A1-2.A5) implemented in `schema_design.py`
- All data loading tasks (2.B1-2.B4) implemented with reconciliation and refresh workflow
- All API tasks (2.C1-2.C6) implemented with FastAPI — 6 route modules, 11 Pydantic models, 115 API-related tests

**Phase 3 (Front-End & Documentation):** ✅ **COMPLETE**
- Frontend technology decision: HTMX + Jinja2 (`docs/FRONTEND_TECHNOLOGY_DECISION.md`)
- Full web UI implemented: search/filter interface, results table, detail panel, download modal, charts page
- All 3 data visualization charts implemented (year-over-year, service comparison, top-N dashboard)
- All 6 user documentation pages complete (getting started, data dictionary, FAQ, API reference, contextual help, methodology)
- **Round 4 UI/UX fixes:** Shared budget type donut utility, stacked YoY chart by service, multi-entity comparison (2-6), faceted filter counts with cross-filtering, service dropdown sorted by count, FY dropdown ordered newest-first, chart click-through scroll anchors, dashboard loading feedback, consolidated view total program value, sub-PE tag visibility
- Remaining: Lighthouse/axe-core accessibility audit (requires running UI)

**Phase 4 (Publish, Feedback & Iteration):** 🔄 **~50% COMPLETE**
- Containerization complete: `Dockerfile`, `Dockerfile.multistage`, `docker-compose.yml`, `docker-compose.staging.yml`
- CI pipeline complete: matrix testing, linting, type checking, coverage, Docker build validation
- Monitoring & backup complete: `/health/detailed` metrics, `scripts/backup_db.py`, structured logging
- Automated data refresh complete: `refresh_data.py` + GitHub Actions weekly cron
- `CONTRIBUTING.md` with full development guidelines
- **Round 4 backend fixes:** `budget_type` column backfill, composite DB indexes, `exclude_summary` parameter, related programs confidence ≥0.8, PE search prefix matching, faceted counts endpoint (`/api/v1/facets`), cache TTL tuning
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
| **REST API** | `api/` (app, models, routes) | 1,239 | ✅ Complete — FastAPI with 8 route modules, CORS, CSP headers, rate limiting, connection pooling |
| **Web UI** | `templates/` + `static/` | — | ✅ Complete — HTMX + Jinja2 with search, filters, results, detail panel, download modal, charts |
| **User documentation** | `docs/` (6 guides) | — | ✅ Complete — getting started, data dictionary, FAQ, API reference, methodology, deployment |
| **Utility libraries** | `utils/` (14 modules) | 2,093 | ✅ Complete — config, database, HTTP, patterns, strings, validation, cache, query, formatting |
| **Test suite** | `tests/` (63 files) | — | ✅ **1,248 tests** — comprehensive coverage across all modules |
| **CI/CD** | `.github/workflows/` (4 files) | — | ✅ Complete — CI pipeline, data refresh, optimization tests, scheduled downloads |
| **Containerization** | `Dockerfile*`, `docker-compose*.yml` | — | ✅ Complete — production, multistage, dev, staging configurations |
| **Backup & monitoring** | `scripts/backup_db.py`, `api/app.py` | — | ✅ Complete — automated backups, /health/detailed, structured logging |

### Remaining TODOs (as of 2026-04-02)

**LION / TIGER / BEAR agent groups:** ✅ **ALL COMPLETE** (33/33 tasks done)

**Active work items (11 items) — see [`docs/TODO_PLAN.md`](TODO_PLAN.md) for full specifications:**

| Priority | ID | Task | Files |
|----------|----|------|-------|
| **HIGH** | TODO-H1 | Fix R-1 title for PDF-only PEs | `api/routes/keyword_search.py` |
| **HIGH** | TODO-H2 | Fix R-1 funding for D8Z PEs | `api/routes/keyword_search.py` |
| **MEDIUM** | TODO-M1 | Verify Explorer PE number search | `api/routes/keyword_search.py` |
| ~~**LOW**~~ | ~~TODO-L1~~ | ~~Enricher progress reporting~~ | ~~`pipeline/enricher.py`~~ | **DONE** |
| **LOW** | TODO-L2 | Fix RuntimeWarning on enricher | `pipeline/__init__.py` |
| **LOW** | TODO-L3 | Fix `--with-llm` Phase 3 | `pipeline/enricher.py` |
| **LOW** | TODO-L4 | Fix non-LLM tagging (0 rows) | `pipeline/enricher.py` |
| ~~**LOW**~~ | ~~TODO-L5~~ | ~~Rebuild Cache button on Hypersonics~~ | ~~`templates/hypersonics.html`~~ | **DONE** |

**Deferred items requiring external resources (6 items):**

| ID | Task | Blocker |
|----|------|---------|
| OH-MY-007 | Choose hosting platform | Cloud account setup |
| OH-MY-008 | Configure CD deployment | Depends on OH-MY-007 + secrets |
| OH-MY-009 | Domain + TLS | Domain registration |
| OH-MY-010 | Accessibility audit | Running UI instance |
| OH-MY-011 | Soft launch | Deployed application |
| OH-MY-012 | Public launch | Depends on OH-MY-011 |

See [REMAINING_TODOS.md](archive/implementation-logs/REMAINING_TODOS.md) for historical context.
See [`docs/TODO_PLAN.md`](TODO_PLAN.md) for sub-agent execution plan.

---

## Active TODOs (2026-04-01)

These are prioritized work items ready to be picked up by agents. Each item includes enough context to be completed independently.

### HIGH — Data Quality & Correctness

| ID | Task | Details |
|----|------|---------|
| **TODO-H1** | Fix R-1 title/description for PDF-only PEs | **Problem:** PEs that exist only in PDFs (not in Excel `budget_lines`) get stub R-1 rows in `keyword_search.py` `build_cache_table()` (~line 885) with `line_item_title` set to the raw PE number (e.g., `0603183D8Z`) and no description. The actual R-1 title (e.g., "Joint Hypersonic Technology Development") is available in the R-1 PDF pages but isn't being extracted. **Where to look:** `pdf_pe_numbers` links PE numbers to `pdf_pages` via `pdf_page_id`. R-1 pages contain lines like `PE 0603183D8Z / Joint Hypersonic Technology Development` in the first 10 lines. The R-2 parser in `parse_r2_cost_block()` (`api/routes/keyword_search.py` ~line 291) already extracts PE title from this pattern — reuse this approach for R-1 pages. **What to do:** (1) After inserting stub rows for PDF-only PEs, scan `pdf_pages` for R-1 summary pages (contain `Exhibit R-1` in `page_text`, join via `pdf_pe_numbers`) for each stub PE. (2) Extract the PE title using the regex `PE\s+(\d{7}PE_SUFFIX_PATTERN)\s*[/:]\s*(.+)` from `utils.patterns.PE_SUFFIX_PATTERN`. (3) UPDATE the stub row's `line_item_title` with the extracted title. (4) **Cross-check opportunity:** For PEs that exist in BOTH Excel and PDFs, compare `budget_lines.line_item_title` against the PDF-extracted title and log mismatches (don't auto-correct, just log). **Files:** `api/routes/keyword_search.py` (stub insertion ~line 885, add title extraction), `utils/patterns.py` (PE_SUFFIX_PATTERN already available). **Test:** After rebuild, `SELECT pe_number, line_item_title FROM hypersonics_cache WHERE pe_number LIKE '%D8Z' AND exhibit_type='r1'` should show real titles, not raw PE numbers. |
| **TODO-H2** | Fix missing R-1 rows for Defense-Wide D8Z PEs on hypersonics page | **Problem:** The hypersonics cache shows D8Z PEs as having only R-2 sub-element rows with no top-level R-1 summary row. Every PE should have at least one R-1 row showing the PE-level title, organization, and total funding across FY columns. Currently, the stub R-1 rows inserted for PDF-only PEs have NULL funding amounts because the budget_lines pivot query (`api/routes/keyword_search.py` ~line 806) returns zero rows for PEs not in `budget_lines`. **Where to look:** R-1 summary PDFs are at paths like `FY2026\PB\Comptroller\summary\FY2026_r1.pdf`. These contain tables with PE-level totals. Also, `pdf_pe_numbers` has entries for D8Z PEs on R-1 pages (e.g., `0603183D8Z` has 2 entries per FY in Comptroller summary files). **What to do:** (1) After inserting stub R-1 rows and after the R-2 PDF mining step, aggregate the R-2 sub-element funding amounts per PE into the R-1 stub row. Specifically: `UPDATE {cache_table} SET fy2024 = (SELECT SUM(fy2024) FROM {cache_table} WHERE pe_number = ? AND exhibit_type = 'r2'), ... WHERE pe_number = ? AND exhibit_type = 'r1'` for each stub PE. (2) Alternatively, parse R-1 PDF pages for PE-level totals (more accurate but more work). Option 1 is simpler and sufficient for now. **Files:** `api/routes/keyword_search.py` — add aggregation step after R-2 mining (~line 993, before index creation). **Test:** `SELECT pe_number, fy2024, fy2025, fy2026 FROM hypersonics_cache WHERE pe_number='0603183D8Z' AND exhibit_type='r1'` should show non-NULL totals matching the sum of its R-2 rows. |

### MEDIUM — Feature Parity & UX

| ID | Task | Details |
|----|------|---------|
| **TODO-M1** | Explorer page: PE number search returns matching PE in results | **Problem:** On the Keyword Explorer page (`/explorer`), if a user enters a PE number like `0604030N` as a keyword, it may or may not appear in results depending on whether the PE's text fields match. The hypersonics page has `_EXTRA_PES` for forced inclusion, but Explorer has no equivalent. **Current state:** `collect_matching_pe_numbers_split()` in `api/routes/keyword_search.py` (~line 143) already has a `pe_pattern` check that detects PE-number-shaped keywords and searches `budget_lines` for exact matches. This was added recently. **What to verify:** (1) Start the dev server (`uvicorn api.app:app --reload --port 8000`). (2) Go to `/explorer`, enter `0604030N` as a keyword, and trigger a search. (3) Confirm that `0604030N` appears in the results table. (4) If it doesn't, check that `collect_matching_pe_numbers_split()` is being called with the PE keyword and that `bl_matched` includes the PE. Debug the `build_cache_table()` flow. **If it works but only returns that one PE:** This is the "mixed feelings" scenario. The current behavior includes the PE alongside any keyword-matched PEs, which is correct. No change needed unless the user requests otherwise. **If it does NOT work:** The likely issue is that `build_cache_table()` calls `collect_matching_pe_numbers_split()` with keywords, but the PE detection regex at line 147 (`pe_pattern = re.compile(rf"^\d{{7}}{PE_SUFFIX_PATTERN}$", re.IGNORECASE)`) might not match because the keyword has surrounding whitespace or is mixed with other keywords. Ensure `kw.strip()` is applied before matching. Also check that the PE is in `budget_lines` — if it's PDF-only, it won't be found by the current query on `budget_lines`. Add a fallback to `pe_index` (same pattern as `extra_pes` logic at ~line 740). **Files:** `api/routes/keyword_search.py` (~line 143-160), `api/routes/explorer.py` (verify `start_build` passes keywords correctly). **Test:** `python -m pytest tests/ -k explorer -v` should pass; manual test on `/explorer` with PE number keyword. |

### LOW — Pipeline & Infrastructure

| ID | Task | Details |
|----|------|---------|
| **TODO-L1** | Pipeline enricher progress reporting | **Problem:** The pipeline enricher (`pipeline/enricher.py`) has inconsistent progress messages across its 5 phases. Some phases show row counts, others show nothing. **What to do:** For each phase's main loop, add a progress reporter that prints every N iterations (or every 5 seconds): `Phase X: {completed}/{total} ({pct:.1f}%) | Elapsed: {elapsed} | ETA: {eta} | {rate:.0f} items/s`. Use `time.monotonic()` for timing. Phases to update: Phase 1 (`_build_pe_index`, ~line 150), Phase 2 (`_extract_descriptions`, ~line 640), Phase 3 (`_tag_programs`, ~line 850), Phase 4 (`_build_cross_refs`, ~line 1050), Phase 5 (`_compute_metrics`, ~line 1200). **Files:** `pipeline/enricher.py`. **Test:** Run `python -m pipeline.enricher --phases 1 2>&1 | head -20` and verify progress lines appear. |
| **TODO-L2** | Fix RuntimeWarning on `python -m pipeline.enricher` | **Problem:** Running `python -m pipeline.enricher` produces a `RuntimeWarning: 'pipeline.enricher' found in sys.modules after import of package 'pipeline'`. **Cause:** `pipeline/__init__.py` likely imports from `enricher` at module level, and running `enricher` as `__main__` creates a duplicate module entry. **Fix:** In `pipeline/__init__.py`, either remove the eager import of `enricher` or guard it with `if 'pipeline.enricher' not in sys.modules`. **Files:** `pipeline/__init__.py`. **Test:** `python -m pipeline.enricher --help 2>&1 | grep -i warning` should produce no output. |
| **TODO-L3** | Fix `--with-llm` in Phase 3 | **Problem:** Running `python -m pipeline.enricher --phases 3 --with-llm` reports `anthropic package not installed` partway through, despite some LLM batches succeeding earlier. **Likely cause:** A `try/except ImportError` block around `import anthropic` in the LLM tagging function catches a transient import issue or there's a code path that re-checks the import and fails. **What to do:** Search `pipeline/enricher.py` for `import anthropic` or `anthropic` — there may be multiple import attempts. Consolidate to a single top-of-file import with a clear flag: `_HAS_ANTHROPIC = False; try: import anthropic; _HAS_ANTHROPIC = True; except ImportError: pass`. Then check `_HAS_ANTHROPIC` in the phase 3 entry point, not in each batch. **Files:** `pipeline/enricher.py`. **Test:** `python -m pipeline.enricher --phases 3 --with-llm --dry-run` (if dry-run exists) or run on a small subset. |
| **TODO-L4** | Fix Phase 3 non-LLM tagging (0 rows) | **Problem:** Running `python -m pipeline.enricher --phases 3` (without `--with-llm`) completes but inserts 0 tag rows for 85 PEs. The rule-based tagger produces no output. **What to do:** Find the rule-based tagging function in `pipeline/enricher.py` (search for `tag` or `classify` in phase 3 code). Check (1) whether the rules actually match any PE descriptions (they may be too narrow), (2) whether results are being inserted into the correct table, (3) whether the INSERT statement has a bug (wrong column count, constraint violation silently caught). Add debug logging: `logger.debug("Rule-based tagger: PE %s matched tags %s", pe, tags)`. **Files:** `pipeline/enricher.py`. **Test:** After fix, `python -m pipeline.enricher --phases 3` should report >0 tags inserted. |
| **TODO-L5** | Add Rebuild Cache button to Hypersonics page | **Problem:** Currently the only way to rebuild the hypersonics cache is via API call or Python script. Users need a UI button. **What to do:** (1) In `templates/hypersonics.html`, add a button in the controls area: `<button class="btn btn-secondary" id="rebuild-cache-btn" onclick="rebuildCache()">Rebuild Cache</button>`. (2) Add JS function `rebuildCache()` that calls `POST /api/v1/hypersonics/rebuild` via fetch, shows a spinner, and reloads the page on completion. (3) The endpoint already exists in `api/routes/hypersonics.py` as `rebuild_hypersonics_cache_endpoint` (search for `@router.post`). If it doesn't exist, create it: call `rebuild_hypersonics_cache(conn)` and return `{"status": "ok", "rows": count}`. **Files:** `templates/hypersonics.html` (button + JS), `api/routes/hypersonics.py` (verify or create POST endpoint). **Test:** Click the button on `/hypersonics` — should show progress and reload with fresh data. |

### Notes for agents

- **`PE_SUFFIX_PATTERN`** is defined in `utils/patterns.py` as `r'(?:[A-Z]{1,2}|[A-Z]\d[A-Z])'`. Use it for all PE regex construction — never hardcode the suffix pattern.
- **Cache table name** for hypersonics is `hypersonics_cache`. Explorer caches use `kw_cache_{hash}`.
- **`_EXTRA_PES`** in `api/routes/hypersonics.py` lists 25 PE numbers that are always included in the hypersonics cache regardless of keyword matching.
- Run `python -m pytest tests/ --ignore=tests/test_gui_tracker.py --ignore=tests/optimization_validation -q` to verify changes don't break existing tests (21 pre-existing GUI test failures are expected).

## Recent Improvements

### Round 5 — Database Data Quality Fixes (2026-02-27)

Ran a 9-step migration (`scripts/fix_data_quality.py`) and hardened the ingestion
pipeline to eliminate duplicates, fill NULL fields, and clean reference tables.

| Change | Result |
|--------|--------|
| Cross-file deduplication (`pipeline/builder.py` + migration) | 124,670 rows to 47,531 (62% reduction) |
| Appropriation code backfill (`repair_database.py`) | NULL appropriation_code: 17.5% to 7.4% |
| Budget type expansion (`scripts/fix_budget_types.py`) | NULL budget_type: 388 to 116 |
| Organization name fill (migration step 5) | Empty organization_name: 311 to 0 |
| Footnote cleanup (`pipeline/backfill.py`) | Reference table footnotes: 31 to 0 |
| `*a.xlsx` exclusion in builder | Prevents amendment file duplicates at ingestion |

**New files:** `scripts/fix_data_quality.py`, `tests/test_pipeline_group/test_data_quality_fixes.py` (34 tests)

**Modified:** `pipeline/builder.py`, `repair_database.py`, `scripts/fix_budget_types.py`, `pipeline/backfill.py`

See [NOTICED_ISSUES.md](NOTICED_ISSUES.md) Round 5 for full details.

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
