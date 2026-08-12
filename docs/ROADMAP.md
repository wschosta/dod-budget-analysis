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
| **1.A5** | Document all data sources | Create a data sources reference listing every URL pattern, document type, file format, and fiscal-year availability for each service and agency. | ✅ **Complete** — `docs/user-guide/data-sources.md` with 6 sources, URL patterns, FY coverage matrix, exhibit type catalog, and known gaps. |
| **1.A6** | Retry failed downloads | Write a structured failure log (`failed_downloads.json`) with URL, dest path, and browser flag for each failed file. Add a `--retry-failures` CLI flag that reads the log and re-attempts only those files. Update the GUI completion dialog to show failure URLs and a copy-retry-command button. | ✅ **Complete** — `--retry-failures` CLI flag, structured `failed_downloads.json` log, GUI completion dialog with retry command copy button. Implemented in `downloader/core.py` (CLI + JSON) and `downloader/gui.py` (GUI dialog). |

### 1.B — Parsing & Normalization

| ID | Task | Details | Status |
|----|------|---------|--------|
| **1.B1** | Catalog all exhibit types | Enumerate every exhibit type encountered (P-1, R-1, O-1, M-1, C-1, P-5, R-2, R-3, R-4, etc.) and document the column layout and semantics for each. | ✅ **Complete** — `pipeline/exhibit_catalog.py` (576 lines) defines column layouts for P-1, P-5, R-1, R-2, O-1, M-1, C-1, P-1R, RF-1 with `ExhibitCatalog` class; `scripts/exhibit_audit.py` scans corpus; cross-validated against corpus (OH-MY-006 done 2026-02-19) |
| **1.B2** | Standardize column mappings | Extend `pipeline/builder.py` column-mapping logic to handle all known exhibit formats consistently; add unit tests for each exhibit type with sample data. | ✅ Mostly Complete — Data-driven catalog approach implemented in `pipeline/exhibit_catalog.py`; `_map_columns()`, `_merge_header_rows()`, catalog-driven detection all tested; multi-row header handling implemented |
| **1.B3** | Normalize monetary values | Ensure all dollar amounts use a consistent unit (thousands of dollars), currency-year label, and handle the distinction between Budget Authority (BA), Appropriations, and Outlays. | ✅ Mostly Complete — FY2024-2026 columns with `_safe_float()` normalization; `amount_type` field tracks BA vs appropriation; currency-year detection implemented (`_detect_currency_year`, DONE 1.B3-b); exhibit→budget_type mapping implemented (`_EXHIBIT_BUDGET_TYPE`, DONE 1.B3-d); amount-unit detection and normalization (DONE 1.B3-a/c) |
| **1.B4** | Extract and normalize program element (PE) and line-item metadata | Parse PE numbers, line-item numbers, budget activity codes, appropriation titles, and sub-activity groups into dedicated, queryable fields. | ✅ Mostly Complete — `pe_number`, `line_item`, `budget_activity_title`, `sub_activity_title`, `appropriation_code`, `appropriation_title` all extracted; regex patterns validated in `utils/patterns.py` |
| **1.B5** | PDF text extraction quality audit | Review `pdfplumber` output for the most common PDF layouts; identify tables that extract poorly and implement targeted extraction improvements or fallback strategies. | ✅ Mostly Complete — `scripts/pdf_quality_audit.py` (312 lines) implements automated audit; `utils/pdf_sections.py` handles R-2/R-3 narrative sections; remaining: targeted improvements for identified poor extractions |
| **1.B6** | Build validation suite | Create automated checks that flag anomalies: missing fiscal years for a service, duplicate rows, zero-sum line items, column misalignment, and unexpected exhibit formats. | ✅ **Complete** — `pipeline/db_validator.py` (1,758 lines) + `utils/validation.py` (424 lines) with `ValidationRegistry`, 10+ checks, and cross-service/cross-exhibit reconciliation in `scripts/reconcile_budget_data.py` |

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
| **2.A1** | Define the canonical data model | Design normalized tables that capture: fiscal year, service/agency, appropriation, budget activity, program element, line item, exhibit type, dollar amounts (by budget cycle: PB, enacted, request), and document source metadata. | ✅ **Complete** — `pipeline/schema.py` (718 lines) defines `budget_line_items` with 29+ columns; `budget_lines` and `pdf_pages` tables in production schema |
| **2.A2** | Design lookup/reference tables | Create reference tables for: services & agencies, appropriation titles, exhibit types, budget cycles, and fiscal years — with human-readable labels and codes. | ✅ **Complete** — `services_agencies`, `appropriation_titles`, `exhibit_types`, `budget_cycles` tables created and seeded via migration; `backfill_reference_tables.py` populates from live data |
| **2.A3** | Design full-text search strategy | Decide whether to continue with SQLite FTS5 for the web deployment or migrate to PostgreSQL with `tsvector`/`tsquery`, or use an external search engine (e.g., Meilisearch). Document trade-offs. | ✅ **Complete** — SQLite FTS5 chosen; `budget_lines_fts` and `pdf_pages_fts` content-sync tables with INSERT/UPDATE/DELETE triggers; `sanitize_fts5_query()` for safe user input |
| **2.A4** | Design PDF/document metadata tables | Schema for storing page-level PDF text, table extractions, and links back to the original source document URL for provenance. | ✅ **Complete** — `pdf_pages` table with `source_file`, `source_category`, `page_number`, `page_text`, `has_tables` columns; FTS5 full-text index on page text |
| **2.A5** | Write and version database migrations | Use a migration tool (e.g., Alembic) or versioned SQL scripts so the schema can evolve without data loss. | ✅ **Complete** — `pipeline/schema.py` implements versioned migration framework with `schema_version` table, `_current_version()`, `migrate()` (idempotent), and `create_normalized_db()` |

### 2.B — Data Loading & Quality

| ID | Task | Details | Status |
|----|------|---------|--------|
| **2.B1** | Build the production data-load pipeline | Refactor `pipeline/builder.py` to target the new canonical schema. Support incremental and full-rebuild modes. | ✅ **Complete** — `pipeline/builder.py` (3,676 lines) supports full-rebuild and incremental modes; `pipeline/gui.py` provides tkinter interface with progress tracking |
| **2.B2** | Cross-service data reconciliation | Verify that totals from service-level exhibits roll up to Comptroller summary exhibits; flag discrepancies. | ✅ **Complete** — `scripts/reconcile_budget_data.py` (481 lines) implements `reconcile_cross_service()` and `reconcile_cross_exhibit()` (P-1 vs P-5, R-1 vs R-2) |
| **2.B3** | Generate data-quality reports | After each load, produce a summary report: row counts by service/year/exhibit, missing data, and validation warnings. | ✅ **Complete** — `pipeline/db_validator.py` generates `data_quality_report.json`; `scripts/pdf_quality_audit.py` audits PDF extraction quality |
| **2.B4** | Establish a data refresh workflow | Document and script the process for incorporating new fiscal-year data as it becomes available (download → parse → load → validate). | ✅ **Complete** — `pipeline/refresh.py` implements `RefreshWorkflow` class with staged pipeline (download → parse → load → validate), dry-run support, and webhook notifications |

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
| **3.A7** | Responsive design & accessibility | Ensure the UI works on mobile and tablet; meet WCAG 2.1 AA accessibility standards (keyboard navigation, screen reader support, sufficient contrast). | ✅ **Complete** — Skip-to-content, ARIA live regions, focus-visible styles, keyboard shortcuts, responsive breakpoints, print styles. axe-core audit run 2026-08-10 against all 7 page routes in both colour schemes: **0 violations**. Repeatable via `scripts/accessibility_audit.py`. |

### 3.B — Data Visualization (Stretch)

| ID | Task | Details | Status |
|----|------|---------|--------|
| **3.B1** | Year-over-year trend charts | For a selected program element or appropriation, display a line/bar chart showing budget amounts across fiscal years. | ✅ **Complete** — Chart.js grouped bar chart in `templates/charts.html` with dynamic FY columns |
| **3.B2** | Service/agency comparison charts | Visual comparison of budget allocations across services for a selected fiscal year. | ✅ **Complete** — Horizontal bar chart with service filter dropdown on charts page |
| **3.B3** | Top-N budget items dashboard | A summary dashboard showing the largest budget line items by various cuts (service, appropriation, program). | ✅ **Complete** — Top-10 horizontal bar chart plus budget comparison interactive chart |
| **3.B4** | Funding trend sparklines | Inline SVG bar charts in search result rows showing funding trajectory across all FY columns. Togglable, dark-mode aware, localStorage-persisted. | ✅ **Complete** — `static/js/sparkline.js`, column toggle in results table |

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
| **4.A1** | Choose a hosting platform | Evaluate options (AWS, GCP, Azure, Fly.io, Railway, Render, etc.) based on cost, reliability, and ease of deployment. Document the decision. | ✅ **Complete** — Fly.io, single machine + persistent volume. Decision and rationale in [`docs/HOSTING_DECISION.md`](HOSTING_DECISION.md); machine config in `fly.toml`. Driven by the runtime write path (the Explorer builds cache tables in the live DB) plus SQLite WAL's single-writer constraint, which rules out serverless and horizontal scaling. |
| **4.A2** | Containerize the application | Create a `Dockerfile` (and `docker-compose.yml` if needed) that bundles the API, front-end, and database for reproducible deployment. | ✅ **Complete** — `Dockerfile` (non-root user, HEALTHCHECK), `Dockerfile.multistage` (2-stage build), `docker-compose.yml` with volume mounts and hot-reload |
| **4.A3** | Set up CI/CD pipeline | Configure GitHub Actions (or equivalent) to run tests, build the container, and deploy on push to the main branch. | ✅ **Complete pending credential** — CI (`ci.yml`: matrix testing, ruff, pytest+coverage, mypy, Docker build) and CD (`deploy.yml`: CI gate → GHCR build/push → `flyctl deploy` → smoke test). The deploy job skips with a warning until `FLY_API_TOKEN` is added as a repository secret, so image builds still run. |
| **4.A4** | Configure a custom domain & TLS | Register or configure a domain name and set up HTTPS with automatic certificate renewal. | ⚠️ Not started — requires domain registration |
| **4.A5** | Set up monitoring & alerting | Implement uptime monitoring, error tracking (e.g., Sentry), and basic usage analytics (privacy-respecting) to detect problems early. | ✅ **Complete** — `/health` + `/health/detailed` endpoints with uptime, request/error counts, DB metrics, response time tracking; structured access logging middleware; rate limiting with per-IP tracking |
| **4.A6** | Implement backup & recovery | Automate database backups and document the recovery procedure. | ✅ **Complete** — `scripts/backup_db.py` with SQLite online backup API, `--keep N` pruning; staging docker-compose backup sidecar (6-hour cycle); `docs/developer/deployment.md` documents recovery procedure |

### 4.B — Launch & Outreach

| ID | Task | Details | Status |
|----|------|---------|--------|
| **4.B1** | Soft launch to a small group | Share the tool with a small set of known users (analysts, researchers, journalists) and collect structured feedback. | ⚠️ Not started — requires deployed application |
| **4.B2** | Create a feedback mechanism | Add a "Feedback" button or form in the UI that lets users report bugs, request features, or note data issues. Route submissions to GitHub Issues. | ✅ **Complete** — POST `/api/v1/feedback` endpoint, modal form in base template, 16 tests; stores to local `feedback.json` (GitHub Issues integration optional future work) |
| **4.B3** | Write a launch announcement | Draft a blog post or README update explaining what the tool does, who it's for, and how to use it. | ⚠️ Not started |
| **4.B4** | Public launch | Announce on relevant forums, social media, and communities (defense policy, open data, civic tech). | ⚠️ Not started — `docker-compose.staging.yml` ready for staging deployment |

### 4.C — Iteration & Maintenance

| ID | Task | Details | Status |
|----|------|---------|--------|
| **4.C1** | Triage and prioritize feedback | Review all feedback, categorize (bug, feature request, data quality, UX), and prioritize for the next development cycle. | ⚠️ Not started — requires public launch and user feedback |
| **4.C2** | Implement high-priority improvements | Address the most impactful issues identified during the soft launch and public feedback rounds. | ⚠️ Not started — depends on user feedback |
| **4.C3** | Keyword Explorer page | Generalized keyword search tool (`/explorer`). User-supplied keywords with fuzzy matching (prefix, acronym expansion, edit-distance). Async cache build with progress polling. PE-level preview. Drag-and-drop column picker for XLSX export. Hypersonics Preset button loads 27 keywords + 25 extra PEs. | ✅ **Complete** — Enhanced: xlsxwriter migration for dynamic array formulas; per-FY Y/N/P keyword matching; R-2 title cleanup (9K dirty titles fixed, 47% row reduction); merged FY headers; PE Summary/Dimension spill sheets; Keyword Matrix; Selected sheet; About sheet; Hypersonics Preset button; extra_pes support; 50 keyword limit. `/hypersonics` standalone page removed — Explorer preset replaces it. |
| **4.C3b** | Automate annual data refresh | When new President's Budget or enacted appropriations are published, the pipeline should detect and ingest them with minimal manual intervention. | ✅ **Complete (repaired 2026-08-10)** — `pipeline/refresh.py` with 4-stage pipeline (download → build → validate → report), automatic rollback, progress tracking, `--schedule` flag; `.github/workflows/refresh-data.yml` with weekly cron. **This was previously marked complete while broken:** the workflow invoked `python refresh_data.py`, which does not exist, so all 18 scheduled runs from 2026-02-22 to 2026-06-21 failed. Now invokes `python -m pipeline.refresh` and derives the target year from `latest_budget_fiscal_year()` instead of a hardcoded 2026. |
| **4.C4** | Performance optimization | Profile and optimize slow queries, large downloads, and page-load times based on real usage patterns. | ✅ Mostly Complete — Connection pooling, FTS5 indexing, rate limiting, pagination, in-memory TTL cache, streaming exports, BM25 relevance scoring; profiling-based tuning pending real traffic |
| **4.C5** | Ongoing documentation updates | Keep the data dictionary, FAQ, and methodology page current as the data and features evolve. | ✅ Mostly Complete — Comprehensive docs in `docs/user-guide/` and `docs/developer/` (20+ files); ongoing updates needed as features evolve |
| **4.C6** | Community contribution guidelines | If the project attracts contributors, publish `CONTRIBUTING.md` with development setup, coding standards, and PR process. | ✅ **Complete** — `CONTRIBUTING.md` with prerequisites, dev setup, code standards, testing guide, PR process, and architecture overview |

---

## Current Project Status

**Phase 0 (Documentation):** ✅ **COMPLETE**
- README updated with features and project status
- Wiki skeleton created with performance optimizations documented (3-6x speedup achieved)
- ROADMAP established with 57 tasks across 4 phases

**Phase 1 (Data Extraction & Normalization):** ✅ **~97% COMPLETE**
- All testing tasks (1.C1-1.C3) complete with 2,590+ tests across 104 test files
- Parsing, normalization, and validation fully functional
- Network audits completed (OH-MY-001 through OH-MY-006, 2026-02-19)
- Download retry (1.A6) complete with `--retry-failures` CLI flag and GUI dialog
- Remaining: data source doc update (1.A5 minor)

**Phase 2 (Database Design & Population):** ✅ **COMPLETE**
- All schema design tasks (2.A1-2.A5) implemented in `pipeline/schema.py`
- All data loading tasks (2.B1-2.B4) implemented with reconciliation and refresh workflow
- All API tasks (2.C1-2.C6) implemented with FastAPI — 15 route modules, 11 Pydantic models, 115 API-related tests

**Phase 3 (Front-End & Documentation):** ✅ **COMPLETE**
- Frontend technology decision: HTMX + Jinja2 (`docs/FRONTEND_TECHNOLOGY_DECISION.md`)
- Full web UI implemented: search/filter interface, results table, detail panel, download modal, charts page
- All 3 data visualization charts implemented (year-over-year, service comparison, top-N dashboard)
- All 6 user documentation pages complete (getting started, data dictionary, FAQ, API reference, contextual help, methodology)
- **Round 4 UI/UX fixes:** Shared budget type donut utility, stacked YoY chart by service, multi-entity comparison (2-6), faceted filter counts with cross-filtering, service dropdown sorted by count, FY dropdown ordered newest-first, chart click-through scroll anchors, dashboard loading feedback, consolidated view total program value, sub-PE tag visibility
- Remaining: Lighthouse/axe-core accessibility audit (requires running UI)

**Phase 4 (Publish, Feedback & Iteration):** 🔄 **~56% COMPLETE** (9/16 tasks)
- Containerization complete: `Dockerfile`, `Dockerfile.multistage`, `docker-compose.yml`, `docker-compose.staging.yml`
- CI pipeline complete: matrix testing, linting, type checking, coverage, Docker build validation
- Monitoring & backup complete: `/health/detailed` metrics, `scripts/backup_db.py`, structured logging
- Automated data refresh complete: `pipeline/refresh.py` + GitHub Actions weekly cron
- `CONTRIBUTING.md` with full development guidelines
- **Round 4 backend fixes:** `budget_type` column backfill, composite DB indexes, `exclude_summary` parameter, related programs confidence ≥0.8, PE search prefix matching, faceted counts endpoint (`/api/v1/facets`), cache TTL tuning
- Remaining: hosting platform selection, domain/TLS, CD deployment workflow, feedback mechanism, public launch

### Component Summary

| Component | File(s) | Lines | Status |
|-----------|---------|-------|--------|
| **Document downloader** | `downloader/` (6 modules) | 3,229 | ✅ Functional — 5 sources, multi-year, parallel, Playwright |
| **Database builder (CLI)** | `pipeline/builder.py` | 3,676 | ✅ Functional — Excel/PDF parsing, incremental updates, dynamic FY columns, failure log + retry |
| **Database builder (GUI)** | `pipeline/gui.py` | 496 | ✅ Functional — tkinter interface with progress/ETA |
| **Schema & migrations** | `pipeline/schema.py` | 718 | ✅ Complete — versioned migrations, reference table seeding |
| **Exhibit catalog** | `pipeline/exhibit_catalog.py` | 576 | ✅ Complete — 9 exhibit types with column layouts |
| **Validation suite** | `pipeline/db_validator.py` + `pipeline/validator.py` + `utils/validation.py` | 2,627 | ✅ Complete — 10+ checks, ValidationRegistry, cross-exhibit consistency, outlier detection |
| **Search interface** | `pipeline/search.py` | 569 | ✅ Functional — FTS5 full-text search, BM25 scoring, export |
| **Data reconciliation** | `scripts/reconcile_budget_data.py` | 481 | ✅ Complete — cross-service + cross-exhibit checks |
| **PDF quality audit** | `scripts/pdf_quality_audit.py` | 312 | ✅ Complete — automated extraction quality scoring |
| **Refresh workflow** | `pipeline/refresh.py` | — | ✅ Complete — staged pipeline with dry-run, webhooks, rollback, progress tracking, scheduling |
| **REST API** | `api/` (app, models, routes) | 8,421 | ✅ Complete — FastAPI with 15 route modules, CORS, CSP headers, rate limiting, connection pooling |
| **Web UI** | `templates/` + `static/` | — | ✅ Complete — HTMX + Jinja2 with search, filters, results, detail panel, download modal, charts |
| **User documentation** | `docs/` (6 guides) | — | ✅ Complete — getting started, data dictionary, FAQ, API reference, methodology, deployment |
| **Utility libraries** | `utils/` (19 modules) | 5,164 | ✅ Complete — config, database, HTTP, patterns, strings, validation, cache, query, formatting |
| **Test suite** | `tests/` (104 files) | — | ✅ **2,590 tests** — comprehensive coverage across all modules |
| **CI/CD** | `.github/workflows/` (4 files) | — | ✅ Complete — CI pipeline, data refresh, optimization tests, scheduled downloads |
| **Containerization** | `Dockerfile*`, `docker-compose*.yml` | — | ✅ Complete — production, multistage, dev, staging configurations |
| **Backup & monitoring** | `scripts/backup_db.py`, `api/app.py` | — | ✅ Complete — automated backups, /health/detailed, structured logging |

### Remaining Work

All code TODOs (H1, H2, M1, L1–L5) and agent groups (LION/TIGER/BEAR, 33/33) are
**resolved**. Data quality issues are catalogued in
[`docs/NOTICED_ISSUES.md`](NOTICED_ISSUES.md).

**Completed 2026-08-10 — enrichment phase set centralized (`enricher.ALL_PHASES`).**
`scripts/run_pipeline.py` still defaulted to a hardcoded `{1..10}`, so a full
`python scripts/run_pipeline.py` run never executed Phase 11 and left
`bli_pe_map` empty — the same drift already fixed once in `pipeline/refresh.py`
(commit c64057b). The dispatch table now lives in
`pipeline/enricher._build_phase_runners()`, the canonical set in
`pipeline.enricher.ALL_PHASES`, and both callers plus the `--phases` CLI default
derive from it. `tests/test_pipeline_group/test_enricher_phase_coverage.py`
fails if the constant, the dispatch table, or either caller drift apart.
Note: Phase 11 needs service-source documents (army/navy/airforce) — a
comptroller-only document set has no `exhibit_type='p5'` pages, so it correctly
reports 0 mappings at that scope.

**Completed 2026-04-16 — BLI narrative search (migration 6, `bli_descriptions_fts`).**
Adds an FTS5 virtual table over `bli_descriptions.description_text` so the
64,703 rows of P-5 procurement narrative text (populated by Phase 9) are
searchable via `/api/v1/search?source=descriptions`. Results appear with
`result_type="bli_description"`. Closes the searchability gap called out
in NOTICED_ISSUES §53 as BLI-side future work.

**Completed 2026-04-16 — P-5 PDF header BLI↔PE mining (enrichment Phase 11).**
Adds `bli_pe_map` table (migration 5) and a new phase that scans `pdf_pages`
with `exhibit_type='p5'` for Program Element references, cross-references
against `bli_index`, and backfills `budget_lines.pe_number` on P-1/P-1R rows
where a high-confidence mapping (≥0.8) exists. Addresses the procurement PE
coverage gap flagged in NOTICED_ISSUES §53. Dry-run yielded 2,759 (BLI, PE)
pairs across 275 distinct PEs, with 5,293 P-1/P-1R rows eligible for backfill.

**Completed 2026-08-11 — first full pipeline build, and the downloader fixes it
required.** The database had never been built in this checkout. Building it
surfaced three defects that only appear when the pipeline actually runs:

- **The downloader aborted on its first bad source.** Playwright raised inside
  Navy discovery and the exception propagated out of `main()`, killing a
  six-source, four-year run before one file was fetched. Both discovery loops
  now continue past a failing source.
- **Navy never needed a browser.** `secnav.navy.mil` serves its page and its
  justification books to plain `requests`; the browser path returned 0 files
  and then threw. Switching to HTTP-first yields 36 files in ~2 s per year.
- **The retry CLI could not be invoked.** `downloader/core.py` had a full
  `main()` but no `__main__` guard, and the message printed after a failed
  download named `dod_budget_downloader.py`, a file not in the repo. Group F
  was signed off because all 18 tests called `main()` directly.

Result: the corpus grew from 291 MB / 128 files to **3.4 GB / 786 files**, and
`pdf_pages` from 9,113 to **111,277**, including **27,284 P-5 pages** and
**19,520 R-2 pages** where there had been none. The database went from 119 MB
to 730 MB.

**Enrichment Phase 11 is now verified against real data** (previously it could
only be shown to return 0 at comptroller-only scope): 745 (BLI, PE) pairs
across 224 distinct PEs, and P-1/P-1R rows carrying a `pe_number` rose from
153 to 1,001. `bli_descriptions` went from 0 to 16,038 rows.

Still outstanding on the download side: **Army** returns HTTP 403 to plain
requests and 0 files via the browser; **saffm.hq.af.mil** (Air Force) fails TLS
negotiation outright. Both are now non-fatal but neither yields data.
**Navy is now complete for FY2024–2027** (34–36 files per year). It required
dropping to `--workers 1 --delay 2`: at 4 workers `secnav.navy.mil` began
timing out after ~1.2 GB, while the single-worker run fetched 106 files /
1.58 GB with zero failures. Use gentle concurrency for that host.

**Groups A–C verified against the full build (2026-08-11):** Group A passes
(32 `idx_bl_*` indexes, 0 NULL `budget_type`). Group C passes (43 distinct
organizations, 59 blank-org rows). **Group B remains scope-limited** —
`appropriation_titles` is 123 against an expected ~225, because `budget_lines`
is sourced from Excel exhibits and the Army/Air Force workbooks are still
missing. Do not mark Group B verified until those sources download.

**Completed 2026-08-12 — P-40 parsed and reconciled against the Excel P-1
rows; deliberately NOT ingested.**

`pipeline/p40_parser.py` reads the Budget Line Item Justification grid (1,826
of 1,830 Resource Summaries yield a clean twelve-value row) and
`pipeline/p40_positional.py` recovers the P-1 line item number from word
coordinates at 99.0% accuracy — text parsing cannot do it, because the header
is two printed columns pdfplumber concatenates and titles contain slashes.
`scripts/reconcile_p40_vs_p1.py` makes the comparison repeatable.

Result: **1,808 of 1,830 records match an Excel P-1 row, and 1,401 of 1,565
comparable values agree within 1% (89.5%).** Every remaining disagreement has
`pdf=0` against a real Excel value, from two understood causes:

- **Shipbuilding accounting.** For ship lines (1611N), "Net Procurement (P-1)"
  legitimately reads 0.000 in a year funded through advance procurement.
  Total Obligation Authority resolves only 9 of 29 such cases, so there is no
  single P-40 row that maps to P-1 across all accounts.
- **Multi-agency line items.** Defense-Wide line item 30 is "Major Equipment"
  for five agencies distinguished only by budget sub-activity, and the P-40
  text carries a BSA for only 66% of records (Navy prints none), so those
  compare one agency's page against Excel's summed rows.

**Recommendation: Excel P-1 stays authoritative for line-item funding.** P-40
should not be written into `budget_lines` — at 89.5% agreement with structural
exceptions, ingesting it would import ambiguity into totals that are currently
consistent. Its unique value is what Excel does *not* carry: out-year columns
(FY+1..FY+4, To Complete, Total), procurement quantities, Code B program
element numbers, and line item titles. Those belong in a separate table keyed
to the P-1 rows, not merged into them.

**Data-quality finding:** `add_non_add` reads "Add" on all 6,758 P-1 rows and
does not flag memo entries. 1,141 rows are "MEMO NON ADD" — visible only in
`cost_type_title` — and summing them double-counts. Any aggregate over
`budget_lines` P-1 rows must exclude `cost_type_title LIKE '%NON ADD%'`.

Remaining work is organized into groups A–G:

| Group | Focus | Code Status | What Remains |
|-------|-------|-------------|-------------|
| **A** | Verify prior fixes | ✅ Resolved (11/14 via test suite) | 3 items need `repair_database.py` on production |
| **B** | Reference tables & dropdowns | ✅ Resolved via test suite | — |
| **C** | Org name normalization | ✅ Resolved via test suite | — |
| **D** | FY attribution | ⚠️ Partial | Mismatch logs but no auto-correction (deferred) |
| **E** | Enrichment quality | ✅ Resolved via test suite | — |
| **F** | Download retry CLI | ✅ Complete (fixed 2026-08-11) | Was marked complete while unrunnable — see below |
| **G** | Deploy & launch | 🔄 In progress | G1/G2 done; G3–G6 need account credentials |

---

#### Groups A–C: DB Verification Queries

All fixes are implemented in code. Run these queries against `dod_budget.sqlite`,
then update [`docs/NOTICED_ISSUES.md`](NOTICED_ISSUES.md) status markers from
`[CODE COMPLETE]` to `[RESOLVED — verified YYYY-MM-DD]`.

**Group A — Prior Fixes** (NOTICED_ISSUES ~~#6~~, ~~#7~~, #9, #18, #26, ~~#52~~):
```sql
SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_bl_%';     -- #9: indexes
SELECT COUNT(*) FROM budget_lines WHERE budget_type IS NULL;                      -- expect ≤116
```
Code-only checks: FY sort (`api/routes/frontend.py:540`), z-index (`static/css/main.css`).

**Group B — Reference Tables** (NOTICED_ISSUES #1, #2, #4, ~~#5~~, #21, ~~#57~~):
```sql
SELECT COUNT(*) FROM budget_cycles;                                               -- expect 5
SELECT COUNT(*) FROM appropriation_titles;                                        -- expect ~225
SELECT COUNT(*) FROM services_agencies;                                           -- expect 22+
SELECT COUNT(*) FROM exhibit_types;                                               -- expect 11+
SELECT COUNT(*) FROM budget_lines WHERE appropriation_code IS NULL;               -- expect ~3,531
```

**Group C — Org Normalization** (NOTICED_ISSUES #3, #20, #38):
```sql
SELECT organization_name, COUNT(*) FROM budget_lines
GROUP BY organization_name ORDER BY 2 DESC;
-- expect canonical names only (Army, Navy, Air Force, etc.)
```

**Group E — Enrichment Quality** (NOTICED_ISSUES ~~#27~~, ~~#39~~, ~~#55~~):
```sql
SELECT tag, COUNT(*) c FROM pe_tags WHERE confidence >= 0.85
GROUP BY tag ORDER BY c DESC LIMIT 20;

SELECT COUNT(*) FROM pe_index
WHERE pe_number NOT IN (SELECT DISTINCT pe_number FROM pe_descriptions);          -- expect 0
```

---

#### Group D: Fiscal Year Attribution (Partial)

NOTICED_ISSUES refs: #10, #25, #56

**What exists:**
- FY extraction from file path: `pipeline/builder.py:1663-1673`
- FY mismatch detection: `pipeline/builder.py:1213-1222` (logs warning, prefers sheet value)
- FY validation at download: `downloader/metadata.py:273-285` (`validate_fy_match`)

**What's missing (deferred):**
- Auto-correction when file-path FY disagrees with content FY (currently only logs — the safer default)
- Investigation of PE FY gaps (#56) — needs production DB

```sql
SELECT pe_number, fiscal_year, COUNT(*) FROM budget_lines
WHERE pe_number IN (SELECT pe_number FROM pe_index WHERE fiscal_years LIKE '%2025%')
GROUP BY 1, 2 ORDER BY 1, 2;
```

---

#### Group G: Deploy & Launch (In progress)

Scaffolding in place:
- Docker: `Dockerfile` (production), `docker/Dockerfile.multistage` (embedded DB)
- CD pipeline: `.github/workflows/deploy.yml` — no TODO placeholders remain
- Platform config: `fly.toml` (single machine, `/data` volume, `/health` check)
- Health checks, monitoring, backup scripts all ready

Sub-tasks (sequential):
1. **G1** Choose hosting platform → ✅ **Complete** — [`docs/HOSTING_DECISION.md`](HOSTING_DECISION.md)
2. **G2** Configure CD workflow → ✅ **Complete** — `deploy.yml` gates on CI, pushes
   to GHCR, deploys via `flyctl deploy --image`, then smoke-tests the live URL
3. **G3** Register domain + TLS — ⚠️ needs a Fly account and registrar access
4. **G4** Accessibility audit → ✅ **Complete** — axe-core, WCAG 2.1 AA, all 7 pages,
   light and dark, 0 violations. Re-run against production data after G3 with
   `python scripts/accessibility_audit.py --base-url <url>`
5. **G5** Soft launch to 5–10 users — ⚠️ needs G3
6. **G6** Public launch + announcement — ⚠️ needs G5

**Operator actions required before the first deploy** (see
[`docs/HOSTING_DECISION.md`](HOSTING_DECISION.md) §6):

| Action | Command / location |
|---|---|
| Create the Fly app | `fly apps create dod-budget-explorer` |
| Create the volume | `fly volumes create dod_budget_data --size 10 --region iad` |
| Add the deploy token | Repository secret `FLY_API_TOKEN` |
| Seed the database | Build locally, then upload to `/data/dod_budget.sqlite` |

**Also required:** GitHub disables scheduled workflows after 60 days without
repository activity. `refresh-data.yml` and any other cron workflows must be
re-enabled by hand in the Actions tab — pushing commits alone does not restore
them.

---

### Known Limitations (not actionable)

Documented in `docs/PRD.md` §9 and `docs/NOTICED_ISSUES.md`:
- #8, #53: 67% of rows lack PE numbers (O-1/M-1/P-1 exhibits don't carry PE)
- #16, #19, #28: FY2000-2009 data gap (documents not publicly available)
- #49: Inline styles (ongoing gradual refactor)

### Future Refactoring Notes

Structural improvements identified during codebase review (April 2025). These are
not bugs — the current code works and is tested — but would reduce maintenance burden
if the API surface grows.

#### 1. API Route Parameter Sprawl — ✅ RESOLVED

Extracted a shared `FilterParams` dependency class in `api/models.py` with 10 common
query parameters (fiscal_year, service, exhibit_type, pe_number, appropriation_code,
budget_type, min_amount, max_amount, q, exclude_summary). All 5 route handlers now use
`filters: FilterParams = Depends()` instead of duplicated `Query()` definitions. The
class includes a `where_kwargs()` helper for passing filters to `build_where_clause()`.

Resolved routes:
- `api/routes/search.py` → `search()`
- `api/routes/budget_lines.py` → `list_budget_lines()`
- `api/routes/download.py` → `download()`
- `api/routes/aggregations.py` → `aggregate()`
- `api/routes/facets.py` → `get_facets()`

#### 2. Duplicate WHERE Clause Construction — ✅ RESOLVED

`build_where_clause()` now supports `exclude_summary` and `extra_conditions`
parameters, enabling routes with custom SQL conditions to use the shared builder.

**Migrated:**
- `api/routes/dashboard.py` — manual conditions replaced with `build_where_clause(exclude_summary=True, extra_conditions=[...])`
- `api/routes/budget_lines.py` — manual `EXCLUDE_SUMMARY_SQL` appending removed; handled via `FilterParams.where_kwargs()` which now passes `exclude_summary`
- `api/routes/aggregations.py` — `hierarchy()` manual conditions replaced with `build_where_clause(extra_conditions=[...])`

**Resolved via local helpers (Wave 2, commit `ada8745`):**
- `api/routes/pe.py` `list_pes()` — `build_where_clause()` was the wrong
  abstraction (PE-prefixed columns, JSON-array-LIKE filters, dynamic tag
  JOINs). Instead extracted two file-private helpers: `_pe_in_bl_like()`
  collapses three duplicate `p.pe_number IN (SELECT ... FROM budget_lines
  WHERE {col} LIKE ?)` subqueries into a loop, and `_json_array_contains()`
  handles the `col LIKE '%"value"%'` pattern. Tag JOIN loop rewritten with
  `enumerate()` for stable `pt_{i}` aliases.
- `api/routes/keyword_search.py` — ROADMAP line range `1156–1279` is stale;
  the file is now 939 lines (refactored into `keyword_r2.py` and
  `keyword_helpers.py` in an earlier pass). No migration target remains.

#### 3. Shared Query Helpers — ✅ RESOLVED (commits `57c7ebc`, `60e37e6`)

Consolidated duplicated patterns onto `utils/query.py`:
- `make_placeholders(n)` replaced inline `", ".join("?" …)` joins across
  `api/routes/{pe,keyword_search}.py`,
  `pipeline/{builder,schema,staging,r2_pdf_extractor}.py`, and
  `scripts/consolidate_pe_lines.py`. One call site in
  `utils/database.py:433` intentionally left inline to avoid a circular
  import (`utils.query` imports from `utils.database`).
- `compute_yoy_change(prev, curr, precision=2)` replaced 5 inline YoY
  calculations in `api/routes/pe.py`.
- A three-tier JSON-parsing family: `parse_json(val, default)` is the
  primitive; `parse_json_array(val) -> list` and
  `parse_json_list(val) -> list[str]` delegate to it. The deleted
  `safe_json_list()` in `api/routes/keyword_helpers.py` and the local
  `_parse_json` in `api/routes/frontend.py` both migrated to this family.
- Private `_add_in_condition` promoted to public `add_in_condition` and
  re-exported from `utils/__init__.py`.

---

### Completed Code TODOs

| ID | Task | Resolution |
|----|------|------------|
| TODO-H1 | R-1 titles for PDF-only PEs | `_extract_r1_titles_for_stubs()` in `keyword_search.py` |
| TODO-H2 | R-1 funding for D8Z PEs | `_aggregate_r2_funding_into_r1_stubs()` in `keyword_search.py` |
| TODO-M1 | Explorer PE number search | `pe_index` fallback + 8 tests |
| TODO-L1 | Enricher progress reporting | `_log_progress()` in all 5 phases |
| TODO-L2 | RuntimeWarning fix | Lazy `__getattr__` imports in `pipeline/__init__.py` |
| TODO-L3 | Anthropic import consolidation | Single `_HAS_ANTHROPIC` flag |
| TODO-L4 | Rule-based tagger fix | Expanded text sources + diagnostics |
| TODO-L5 | Rebuild Cache button | ~~`templates/hypersonics.html`~~ — page removed; explorer handles cache rebuilds via `/api/v1/explorer/build` |

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
| Phase 0 — Documentation | 2 |
| Phase 1 — Data Extraction & Normalization | 15 |
| Phase 2 — Database Design & Population | 15 |
| Phase 3 — Front-End & Documentation | 16 |
| Phase 4 — Publish, Feedback & Iteration | 17 |
| **Total** | **65** |
