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
| **1.A1** | Audit existing downloader coverage | Catalog every source the current `dod_budget_downloader.py` supports (Comptroller, Defense-Wide, Army, Navy/USMC, Air Force/Space Force). Identify gaps — e.g., Defense Logistics Agency, MDA standalone exhibits, or SOCOM. | ✅ Partially Complete — 5 main sources implemented; additional sources identified but not added |
| **1.A2** | Expand fiscal-year coverage | Ensure the downloader can discover and retrieve documents for all publicly available fiscal years (currently dynamic discovery works for recent years; verify historical reach back to at least FY2017). | 🔄 In Progress — FY2025-2026 confirmed; historical reach needs verification |
| **1.A3** | Harden download reliability | Improve retry logic, handle WAF/CAPTCHA changes on government sites, add checksum or size verification for downloaded files, and implement a manifest of expected vs. actual downloads. | ✅ Partially Complete — Smart file skipping, 3-attempt retry with exponential backoff; manifest and checksums TODO |
| **1.A4** | Automate download scheduling | Create a repeatable, scriptable download pipeline (CLI-only, no GUI dependency) that can be run via cron or CI to keep data current when new fiscal-year documents are published. | ✅ Partially Complete — CLI mode available; `--no-gui` flag supports headless scheduling |
| **1.A5** | Document all data sources | Create a `DATA_SOURCES.md` file listing every URL pattern, document type, file format, and fiscal-year availability for each service and agency. | 🔄 In Progress — `DATA_SOURCES.md` exists; coverage matrix TODO |
| **1.A6** | Retry failed downloads | Write a structured failure log (`failed_downloads.json`) with URL, dest path, and browser flag for each failed file. Add a `--retry-failures` CLI flag that reads the log and re-attempts only those files. Update the GUI completion dialog to show failure URLs and a copy-retry-command button. | ⚠️ Not started |

### 1.B — Parsing & Normalization

| ID | Task | Details | Status |
|----|------|---------|--------|
| **1.B1** | Catalog all exhibit types | Enumerate every exhibit type encountered (P-1, R-1, O-1, M-1, C-1, P-5, R-2, R-3, R-4, etc.) and document the column layout and semantics for each. | 🔄 In Progress — Core types (M-1, O-1, P-1, P-1R, R-1, RF-1, C-1) recognized; `exhibit_catalog.py` placeholder created |
| **1.B2** | Standardize column mappings | Extend `build_budget_db.py` column-mapping logic to handle all known exhibit formats consistently; add unit tests for each exhibit type with sample data. | 🔄 In Progress — Core heuristic-based mapping works; data-driven approach (via `exhibit_catalog.py`) TODO |
| **1.B3** | Normalize monetary values | Ensure all dollar amounts use a consistent unit (thousands of dollars), currency-year label, and handle the distinction between Budget Authority (BA), Appropriations, and Outlays. | 🔄 In Progress — FY2024-2026 columns supported; unit normalization and currency-year labeling TODO |
| **1.B4** | Extract and normalize program element (PE) and line-item metadata | Parse PE numbers, line-item numbers, budget activity codes, appropriation titles, and sub-activity groups into dedicated, queryable fields. | ⚠️ Not started — Current schema includes basic fields; advanced PE/code parsing TODO |
| **1.B5** | PDF text extraction quality audit | Review `pdfplumber` output for the most common PDF layouts; identify tables that extract poorly and implement targeted extraction improvements or fallback strategies. | 🔄 In Progress — Basic PDF table extraction works; fallback strategies and targeted improvements TODO |
| **1.B6** | Build validation suite | Create automated checks that flag anomalies: missing fiscal years for a service, duplicate rows, zero-sum line items, column misalignment, and unexpected exhibit formats. | ✅ **Complete** — `validate_budget_db.py` implements 10+ checks |

### 1.C — Data Pipeline Testing

| ID | Task | Details | Status |
|----|------|---------|--------|
| **1.C1** | Create representative test fixtures | Assemble a small set of real (or redacted) Excel and PDF files covering each exhibit type and each service to use in automated tests. | 🔄 In Progress — Basic fixtures in `tests/fixtures/`; expanded coverage TODO |
| **1.C2** | Unit tests for parsing logic | Write `pytest` tests for column detection, value normalization, exhibit-type identification, and PE/line-item extraction. | 🔄 In Progress — `tests/test_parsing.py` and `test_optimization.py` exist; comprehensive coverage TODO |
| **1.C3** | Integration test: end-to-end pipeline | Test the full flow from raw files → SQLite database → search query, verifying row counts and known values. | 🔄 In Progress — Basic e2e test in `test_e2e_pipeline.py`; expanded scenarios TODO |

---

## Phase 2 — Database Design & Population

**Goal:** Design a production-quality relational schema, load all extracted data, and expose it through a programmatic API.

### 2.A — Schema Design

| ID | Task | Details | Status |
|----|------|---------|--------|
| **2.A1** | Define the canonical data model | Design normalized tables that capture: fiscal year, service/agency, appropriation, budget activity, program element, line item, exhibit type, dollar amounts (by budget cycle: PB, enacted, request), and document source metadata. | Not started |
| **2.A2** | Design lookup/reference tables | Create reference tables for: services & agencies, appropriation titles, exhibit types, budget cycles, and fiscal years — with human-readable labels and codes. | Not started |
| **2.A3** | Design full-text search strategy | Decide whether to continue with SQLite FTS5 for the web deployment or migrate to PostgreSQL with `tsvector`/`tsquery`, or use an external search engine (e.g., Meilisearch). Document trade-offs. | Not started |
| **2.A4** | Design PDF/document metadata tables | Schema for storing page-level PDF text, table extractions, and links back to the original source document URL for provenance. | Not started |
| **2.A5** | Write and version database migrations | Use a migration tool (e.g., Alembic) or versioned SQL scripts so the schema can evolve without data loss. | Not started |

### 2.B — Data Loading & Quality

| ID | Task | Details | Status |
|----|------|---------|--------|
| **2.B1** | Build the production data-load pipeline | Refactor `build_budget_db.py` to target the new canonical schema. Support incremental and full-rebuild modes. | Not started |
| **2.B2** | Cross-service data reconciliation | Verify that totals from service-level exhibits roll up to Comptroller summary exhibits; flag discrepancies. | Not started |
| **2.B3** | Generate data-quality reports | After each load, produce a summary report: row counts by service/year/exhibit, missing data, and validation warnings. | Not started |
| **2.B4** | Establish a data refresh workflow | Document and script the process for incorporating new fiscal-year data as it becomes available (download → parse → load → validate). | Not started |

### 2.C — API Layer

| ID | Task | Details | Status |
|----|------|---------|--------|
| **2.C1** | Choose a web framework | Evaluate options (FastAPI, Flask, Django REST Framework) based on project needs: query flexibility, authentication (if any), and ease of deployment. Recommend and document the choice. | Not started |
| **2.C2** | Design REST API endpoints | Define endpoints for: search (full-text), filtered queries (by service, year, appropriation, PE, exhibit type), aggregations (totals by service/year), and data download (CSV/JSON export). | Not started |
| **2.C3** | Implement core query endpoints | Build the `/search`, `/budget-lines`, `/aggregations` endpoints with pagination, sorting, and filtering parameters. | Not started |
| **2.C4** | Implement export/download endpoint | Build a `/download` endpoint that accepts the same filters as the query endpoints and returns results as CSV or JSON. Handle large result sets with streaming. | Not started |
| **2.C5** | Add API input validation & error handling | Validate query parameters, return meaningful error messages, and set rate limits to prevent abuse. | Not started |
| **2.C6** | Write API tests | Automated tests for each endpoint covering happy-path queries, edge cases (empty results, invalid parameters), and export formats. | Not started |

---

## Phase 3 — Front-End & Documentation

**Goal:** Build an intuitive web interface that lets non-technical users search, filter, explore, and download DoD budget data — with clear documentation.

### 3.A — UI Design & Core Features

| ID | Task | Details | Status |
|----|------|---------|--------|
| **3.A1** | Choose front-end technology | Evaluate options (React, Vue, Svelte, or server-rendered templates via Jinja2/HTMX). Consider team familiarity, bundle size, and accessibility. Document the choice. | Not started |
| **3.A2** | Design wireframes / mockups | Create low-fidelity wireframes for: landing page, search/filter interface, results table, detail view, and download flow. | Not started |
| **3.A3** | Build the search & filter interface | Implement a form with filters for: fiscal year, service/agency, appropriation, program element, exhibit type, and free-text search. Filters should be combinable. | Not started |
| **3.A4** | Build the results table | Display query results in a sortable, paginated table. Show key columns (service, fiscal year, program, amount, exhibit type). Allow column toggling. | Not started |
| **3.A5** | Build the download feature | Allow users to download their current filtered result set as CSV or JSON. Include a "Download" button that triggers the API export endpoint. Show download progress for large files. | Not started |
| **3.A6** | Build a detail/drill-down view | When a user clicks a budget line, show full details: all available fields, the source document (link to original PDF on DoD site), and related line items across fiscal years. | Not started |
| **3.A7** | Responsive design & accessibility | Ensure the UI works on mobile and tablet; meet WCAG 2.1 AA accessibility standards (keyboard navigation, screen reader support, sufficient contrast). | Not started |

### 3.B — Data Visualization (Stretch)

| ID | Task | Details | Status |
|----|------|---------|--------|
| **3.B1** | Year-over-year trend charts | For a selected program element or appropriation, display a line/bar chart showing budget amounts across fiscal years. | Not started |
| **3.B2** | Service/agency comparison charts | Visual comparison of budget allocations across services for a selected fiscal year. | Not started |
| **3.B3** | Top-N budget items dashboard | A summary dashboard showing the largest budget line items by various cuts (service, appropriation, program). | Not started |

### 3.C — User Documentation

| ID | Task | Details | Status |
|----|------|---------|--------|
| **3.C1** | Write a "Getting Started" guide | A plain-language guide explaining what the tool does, what data is included, and how to perform a basic search and download. | Not started |
| **3.C2** | Write a data dictionary | Define every field visible in the UI and API: what it means, where it comes from, and known caveats (e.g., fiscal-year transitions, restated figures). | Not started |
| **3.C3** | Write an FAQ | Address common questions: data freshness, coverage gaps, unit of measure (thousands of dollars), difference between PB/enacted/request, etc. | Not started |
| **3.C4** | Write API documentation | If the API is publicly accessible, provide OpenAPI/Swagger docs with example requests and responses. | Not started |
| **3.C5** | Add contextual help to the UI | Tooltips, info icons, and inline explanations on the search/filter page so users understand each filter without leaving the page. | Not started |
| **3.C6** | Write a methodology & limitations page | Explain how data is collected, parsed, and loaded; known limitations (e.g., PDF extraction accuracy); and how to report errors. | Not started |

---

## Phase 4 — Publish, Feedback & Iteration

**Goal:** Deploy the application publicly, gather real-world feedback, and improve based on what users actually need.

### 4.A — Deployment & Infrastructure

| ID | Task | Details | Status |
|----|------|---------|--------|
| **4.A1** | Choose a hosting platform | Evaluate options (AWS, GCP, Azure, Fly.io, Railway, Render, etc.) based on cost, reliability, and ease of deployment. Document the decision. | Not started |
| **4.A2** | Containerize the application | Create a `Dockerfile` (and `docker-compose.yml` if needed) that bundles the API, front-end, and database for reproducible deployment. | Not started |
| **4.A3** | Set up CI/CD pipeline | Configure GitHub Actions (or equivalent) to run tests, build the container, and deploy on push to the main branch. | Not started |
| **4.A4** | Configure a custom domain & TLS | Register or configure a domain name and set up HTTPS with automatic certificate renewal. | Not started |
| **4.A5** | Set up monitoring & alerting | Implement uptime monitoring, error tracking (e.g., Sentry), and basic usage analytics (privacy-respecting) to detect problems early. | Not started |
| **4.A6** | Implement backup & recovery | Automate database backups and document the recovery procedure. | Not started |

### 4.B — Launch & Outreach

| ID | Task | Details | Status |
|----|------|---------|--------|
| **4.B1** | Soft launch to a small group | Share the tool with a small set of known users (analysts, researchers, journalists) and collect structured feedback. | Not started |
| **4.B2** | Create a feedback mechanism | Add a "Feedback" button or form in the UI that lets users report bugs, request features, or note data issues. Route submissions to GitHub Issues. | Not started |
| **4.B3** | Write a launch announcement | Draft a blog post or README update explaining what the tool does, who it's for, and how to use it. | Not started |
| **4.B4** | Public launch | Announce on relevant forums, social media, and communities (defense policy, open data, civic tech). | Not started |

### 4.C — Iteration & Maintenance

| ID | Task | Details | Status |
|----|------|---------|--------|
| **4.C1** | Triage and prioritize feedback | Review all feedback, categorize (bug, feature request, data quality, UX), and prioritize for the next development cycle. | Not started |
| **4.C2** | Implement high-priority improvements | Address the most impactful issues identified during the soft launch and public feedback rounds. | Not started |
| **4.C3** | Automate annual data refresh | When new President's Budget or enacted appropriations are published, the pipeline should detect and ingest them with minimal manual intervention. | Not started |
| **4.C4** | Performance optimization | Profile and optimize slow queries, large downloads, and page-load times based on real usage patterns. | Not started |
| **4.C5** | Ongoing documentation updates | Keep the data dictionary, FAQ, and methodology page current as the data and features evolve. | Not started |
| **4.C6** | Community contribution guidelines | If the project attracts contributors, publish `CONTRIBUTING.md` with development setup, coding standards, and PR process. | Not started |

---

## Current Project Status

**Phase 0 (Documentation):** ✅ **COMPLETE**
- README updated with features and project status
- Wiki skeleton created with performance optimizations documented (3-6x speedup achieved)
- ROADMAP established with 57 tasks across 4 phases

**Phase 1 (Data Extraction & Normalization):** 🔄 **IN PROGRESS (60-70% complete)**

The following components provide the foundation for Phase 1:

| Component | File | Lines | Status | Phase Coverage |
|-----------|------|-------|--------|-----------------|
| **Document downloader** | `dod_budget_downloader.py` | 1476 | ✅ Functional | 1.A (1-5 sources, multi-year, parallel, optimized) |
| **Database builder** | `build_budget_db.py` | 1011+ | ✅ Functional | 1.B1-1.B5 (core parsing, incremental updates) |
| **Database GUI** | `build_budget_gui.py` | 14k+ | ✅ Functional | 1.B (tkinter interface for db builder) |
| **Validation suite** | `validate_budget_db.py` | 332 | ✅ Complete | 1.B6 (10+ quality checks) |
| **Search interface** | `search_budget.py` | 549 | ✅ Functional | 2.C (FTS5 full-text search prototype) |
| **Test suite** | `tests/` | — | 🔄 In Progress | 1.C (parsing, optimization, search tests) |
| **Exhibit catalog** | `exhibit_catalog.py` | 69 | ⚠️ Placeholder | 1.B1 (to be populated) |

**Phase 2–4:** 📋 **NOT STARTED**
- Database schema design (2.A)
- API layer design and implementation (2.C)
- Web UI and user documentation (3.A–3.C)
- Deployment and launch (4.A–4.C)

The existing code handles the happy path for several services and exhibit types (core functionality). The roadmap above focuses on completeness, edge cases, hardening, testing, and building the web-facing product.

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
