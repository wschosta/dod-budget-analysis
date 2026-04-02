# Program Requirements Document (PRD)

> **Version:** 1.2
> **Last Updated:** 2026-04-01
> **Update Policy:** This document must be updated whenever features are added, changed, or removed. It is the canonical description of what the system does. Reference this document before implementing new features to avoid duplicating or overwriting existing functionality.

---

## 1. Product Overview

**DoD Budget Explorer** is a searchable database of Department of Defense budget justification documents. It downloads thousands of Excel spreadsheets and PDF documents from official DoD websites, parses them into structured data, and serves them through a REST API and web interface. The system enables defense analysts, congressional staffers, journalists, and researchers to search, filter, compare, and export DoD budget data that would otherwise require manually navigating dozens of government websites and hundreds of individual files.

### Target Users

- **Congressional staffers** reviewing defense budget requests
- **Defense policy analysts** tracking program funding trends
- **Journalists** investigating defense spending patterns
- **Academic researchers** studying defense budget allocation
- **Government contractors** monitoring program funding levels

---

## 2. Data Pipeline

The system operates as a 5-step pipeline orchestrated by `run_pipeline.py`:

```
Download -> Build -> Repair -> Validate -> Enrich
```

### 2.1 Download

Downloads budget justification documents from official DoD sources.

- **6 data sources:** Comptroller (comptroller.defense.gov), Defense-Wide, Army, Navy, Navy Archive, Air Force
- **Access methods:** Direct HTTP for standard sites; Playwright browser automation for WAF-protected/SharePoint sites (Army, Navy, Air Force)
- **Parallel discovery and download** with configurable worker count and per-domain rate limiting
- **Smart file skipping** using hash-based change detection and file manifest tracking
- **Retry with exponential backoff** (3 attempts per file, configurable timeouts)
- **`--retry-failures` CLI flag** re-attempts only previously failed downloads from a structured `failed_downloads.json` log (records URL, destination, error, browser flag, and timestamp)
- **GUI completion dialog** shows failure count and a "Copy retry command" button for easy CLI retry
- **CLI and GUI modes** (`--no-gui` for automation/cron)
- **File formats downloaded:** Excel (.xlsx), PDF, CSV, ZIP
- **Output directory:** `DoD_Budget_Documents/` organized by fiscal year and source

### 2.2 Build

Parses downloaded documents into a normalized SQLite database.

- **Excel parsing:** 15+ exhibit types including P-1, P-5, R-1, R-2, R-3, R-4, O-1, M-1, C-1, RF-1, P-1R, plus OCO, OGSI, supplemental, amendment, ENL, TOA variants
- **Column mapping:** Data-driven catalog (`exhibit_catalog.py`) maps exhibit-specific column layouts to canonical field names
- **PDF extraction:** Text and table extraction via pdfplumber, stored page-by-page. PE numbers extracted from PDF text into `pdf_pe_numbers` table using shared `PE_NUMBER` regex from `utils/patterns.py`.
- **PE number format support:** Standard suffixes (1-2 letters, e.g., `0602702E`) and Defense-Wide D8Z suffixes (letter-digit-letter, e.g., `0603183D8Z`). All PE regex patterns derive from `PE_SUFFIX_PATTERN` in `utils/patterns.py`.
- **Incremental and full-rebuild modes** with checkpoint/resume for interrupted builds
- **Parallel PDF processing** using ProcessPoolExecutor with configurable worker count
- **FTS5 full-text search index** creation with content-sync triggers
- **Deduplication** of identical rows across exhibit sources
- **`_display` file exclusion** to prevent duplicate data from Comptroller display variants
- **GUI mode** via `build_budget_gui.py` with progress tracking and ETA

### 2.3 Repair

Post-build normalization and reference table population.

- **Organization name normalization** (e.g., standardize "ARMY"/"A"/"Army" to consistent values)
- **Reference table population:** `services_agencies`, `exhibit_types`, `appropriation_titles`, `budget_cycles`
- **Index creation** on frequently-queried columns
- **Appropriation code backfill** from reference data
- **FTS5 index rebuild** with trigger recreation

### 2.4 Validate

Automated data quality checks producing a JSON report.

- **8+ validation checks:** database statistics, duplicate detection, null-heavy rows (all amount columns), unknown exhibit types, value range validation, row count consistency, fiscal year coverage, column type verification
- **Dynamic column discovery** for amount validation (checks all `amount_fy*` and `quantity_fy*` columns)
- **Cross-service and cross-exhibit reconciliation** (P-1 vs P-5, R-1 vs R-2 totals)
- **JSON report output** (`data_quality_report.json`)

### 2.5 Enrich

Adds contextual metadata to program elements.

- **PE index:** Master list of all program elements across services and fiscal years
- **PE descriptions:** Narrative descriptions extracted from R-2 exhibits and PDF documents
- **PE tags:** Keyword-based categorization with confidence scoring (1.0 structured match, 0.9 budget-lines keyword, 0.85 project-level, 0.8 PDF narrative, 0.7 LLM-generated)
- **PE lineage:** Historical tracking of program element changes over time
- **Project descriptions:** Program-level detail decomposition
- **Uniform progress reporting** across all 5 phases: logs completed/total count, percentage, elapsed time, ETA, and throughput rate via `_log_progress()` helper

---

## 3. REST API

FastAPI application serving the database through versioned endpoints (`/api/v1`).

### 3.1 Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/search` | GET | Full-text search with FTS5 + BM25 relevance ranking, snippet highlighting, pagination |
| `/api/v1/budget-lines` | GET | Filtered, paginated budget line items with sorting |
| `/api/v1/budget-lines/{id}` | GET | Single budget line item with full detail |
| `/api/v1/aggregations` | GET | GROUP BY summaries for charts and dashboards |
| `/api/v1/download` | GET | Streaming CSV/NDJSON export with same filters as budget-lines |
| `/api/v1/reference/{type}` | GET | Reference data: services, exhibit types, fiscal years, appropriations |
| `/api/v1/metadata` | GET | Database statistics and dataset metadata |
| `/api/v1/pe/{pe_number}` | GET | Program element detail with funding history |
| `/api/v1/pe/{pe_number}/funding` | GET | PE funding data across fiscal years |
| `/api/v1/pe/{pe_number}/sub-elements` | GET | PE sub-element breakdown |
| `/api/v1/dashboard/summary` | GET | Dashboard summary statistics |
| `/api/v1/dashboard/top-programs` | GET | Top programs by funding amount |
| `/api/v1/facets` | GET | Faceted filter counts with cross-filtering per dimension |
| `/api/v1/hypersonics` | GET | Pivoted hypersonics PE lines: one row per sub-element, columns for FY2015–FY2026. Filters: service, exhibit, fy_from, fy_to. Includes 25 forced-inclusion PEs via `_EXTRA_PES` (including 9 D8Z Defense-Wide programs). |
| `/api/v1/hypersonics/download` | GET | CSV download of the pivoted hypersonics table (same filters). |
| `/api/v1/hypersonics/download/xlsx` | GET | XLSX download with per-FY description columns (`Desc FY{yr}`) sourced from `pe_descriptions` table, priority-ordered by section_header (Mission Description > Accomplishments > Acquisition Strategy). |
| `/api/v1/hypersonics/rebuild` | POST | Rebuild the hypersonics cache table from budget_lines + PDF mining. |
| `/api/v1/explorer/build` | POST | Start async cache build for user-supplied keywords. Returns keyword_set_id. |
| `/api/v1/explorer/status` | GET | Poll cache build progress (state, progress text, PE count). |
| `/api/v1/explorer` | GET | PE-level summary + available download columns for a built keyword set. |
| `/api/v1/explorer/download/xlsx` | POST | XLSX export with user-selected columns in chosen order. Supports matching-only filter. |
| `/api/v1/feedback` | POST | User feedback submission |
| `/health` | GET | Health check (DB connectivity) |
| `/health/detailed` | GET | Uptime, request/error counts, query stats, DB metrics |

### 3.2 Cross-Cutting Features

- **Pydantic v2 validation** for all request parameters and response schemas
- **Per-IP rate limiting** (search: 60/min, download: 10/min, default: 120/min, all configurable)
- **ETag caching** for conditional responses and bandwidth reduction
- **CORS middleware** with configurable origins
- **Security headers:** CSP, X-Content-Type-Options, X-Frame-Options
- **Connection pooling:** Queue-based, thread-safe pool (configurable size, default 10)
- **Auto-generated API docs:** OpenAPI/Swagger at `/docs`, ReDoc at `/redoc`
- **Structured access logging** middleware with response timing

---

## 4. Web Frontend

Server-side rendered HTML using Jinja2 templates with HTMX for dynamic updates.

### 4.1 Pages

| Page | Route | Description |
|------|-------|-------------|
| **Explorer** | `/explorer` (also `/`) | **Default landing page.** Generalized keyword search tool. Enter any keywords (comma-separated, max 20) or PE numbers (e.g., `0604030N`) to search budget lines and PE descriptions with fuzzy matching (prefix, acronym expansion, edit-distance). PE numbers entered as keywords are matched directly against `budget_lines` and `pe_index`. Async cache build with progress polling and elapsed-time display. Collapsible PE-level preview table showing match counts. Two-list drag-and-drop column picker for XLSX download with customizable column order. Toggle to filter to directly matching sub-elements only. XLSX export includes totals row for keyword-matched rows and italic styling for non-matching rows. |
| **Hypersonics** | `/hypersonics` | Pivoted table of all hypersonics-related PE lines and sub-programs, FY2015+. One row per unique PE + sub-element; one column per fiscal year showing primary requested/enacted funding ($K). Filter by service, exhibit type, and FY range. 25 forced-inclusion PEs (`_EXTRA_PES`) including 9 D8Z Defense-Wide programs. PDF-only PEs get stub R-1 rows with funding mined from R-2 detail PDFs. CSV and XLSX download; XLSX includes per-FY description columns from `pe_descriptions`. Filter presets with save/load/delete. **Rebuild Cache** button in the filter bar triggers `POST /api/v1/hypersonics/rebuild` and reloads the page with fresh data. |
| **Home (legacy)** | `/home` | Original full-text keyword search with filter sidebar: fiscal year, service/agency (sorted by count), exhibit type, budget type, amount range. Faceted filter counts, HTMX-driven results table. Still accessible but removed from nav. |
| **Charts** | `/charts` | Budget by service (horizontal bar), stacked budget totals by service & FY, Top-N programs (excludes summary exhibits), multi-entity comparison (2-6 services across all FY columns), budget hierarchy treemap, budget type breakdown (shared doughnut utility). FY selector (newest first) and multi-select service filter. Not in primary nav; accessible via direct URL. |
| **Dashboard** | `/dashboard` | Summary cards (FY totals, YOY change), budget-by-service bar chart, Top-10 programs, appropriation breakdown. Not in primary nav; accessible via direct URL. |
| **Programs** | `/programs` | Program element browsing with tag filters, search, and funding history table. Not in primary nav; accessible via direct URL. |
| **Program Detail** | `/programs/{pe}` | Individual PE detail: funding breakdown by FY, narrative descriptions, related exhibits, source documents. |
| **About** | `/about` | Project description, data coverage summary, methodology overview. |

### 4.2 HTMX Partials

- `results.html` — Search results table (loaded via AJAX)
- `detail.html` — Budget line detail panel (inline expand)
- `advanced-search.html` — Advanced search form
- `feedback.html` — Feedback submission form
- `glossary.html` — Budget glossary terms
- `program-list.html` — Program list for Programs page
- `program-descriptions.html` — PE description panel
- `toast.html` — Toast notification component

### 4.3 UI Features

- **Dark mode** with CSS custom properties, `localStorage` persistence, system `prefers-color-scheme` detection
- **Navigation:** Streamlined nav bar with Hypersonics, Explorer, About, and API Docs links. Legacy pages (Home, Charts, Dashboard, Programs, Consolidated) are still served but not in the primary nav. `/` redirects to `/explorer`.
- **Download modal** supporting CSV, JSON (NDJSON), and Excel (.xlsx) formats with column subset selection
- **Responsive design** with mobile, tablet, and desktop breakpoints
- **Keyboard shortcuts** for navigation
- **Accessibility:** Skip-to-content link, ARIA live regions, focus-visible styles, print styles
- **Custom checkbox-select dropdown** component for multi-value filters
- **Tooltips** on filter labels and column headers (CSS `data-tooltip` attributes)
- **Chart.js visualizations** fetching data from API aggregation endpoints

---

## 5. Database Schema

SQLite database (`dod_budget.sqlite`) with WAL mode for concurrent reads.

### 5.1 Core Tables

- **`budget_lines`** — Flat fact table (29+ columns): organization, fiscal_year, exhibit_type, pe_number, line_item, budget_activity_title, appropriation_code/title, amount columns per FY (actual, enacted, request, supplemental, reconciliation, total), quantity columns, category, source_file
- **`pdf_pages`** — Page-level PDF content: source_file, page_number, page_text, has_tables, source_category
- **`ingested_files`** — File manifest: path, type, size, modified_time, status, exhibit_type, budget_cycle, download_timestamp, service_org

### 5.2 Search Tables

- **`budget_lines_fts`** — FTS5 virtual table indexing line item titles and organization names
- **`pdf_pages_fts`** — FTS5 virtual table indexing PDF page text and table data
- Content-sync triggers maintain FTS indexes automatically

### 5.3 Reference Tables

- **`services_agencies`** — Service/agency codes and display names
- **`exhibit_types`** — Exhibit type codes, display names, and descriptions
- **`appropriation_titles`** — Appropriation codes and titles
- **`budget_cycles`** — Budget cycle identifiers (PB, enacted, CR)

### 5.4 Enrichment Tables

- **`pe_index`** — Master program element list with display_title, organization_name, budget_type, fiscal_years, exhibit_types, and source (budget_lines or pdf)
- **`pdf_pe_numbers`** — Links PE numbers found in PDF text to `pdf_pages` (via `pdf_page_id`), with source_file and fiscal_year. Populated during build step.
- **`pe_descriptions`** — Narrative descriptions from R-2/PDF sources, keyed by (pe_number, fiscal_year, section_header). Section headers include "Mission Description", "Accomplishments/Planned Programs", "Acquisition Strategy", etc. Rows with NULL section_header are R-1 page headers (not real descriptions).
- **`pe_tags`** — Keyword tags with confidence scores and `source_files` provenance
- **`pe_lineage`** — Historical PE change tracking
- **`project_descriptions`** — Project-level detail within PEs

### 5.5 Cache Tables

- **`hypersonics_cache`** — Pivoted cache for hypersonics page. Built by `build_cache_table()` in `api/routes/keyword_search.py`. Columns: pe_number, organization_name, exhibit_type, line_item_title, budget_activity, budget_activity_title, budget_activity_norm, appropriation_title, account_title, color_of_money, matched_keywords_row, matched_keywords_desc, description_text, plus per-FY amount and source reference columns.
- **`kw_cache_{hash}`** — Per-keyword-set caches for Explorer page. Same schema as hypersonics_cache.
- **`explorer_cache_meta`** — Tracks built Explorer caches with keyword_set_id, row_count, and built_at timestamp. Survives process restarts.

### 5.6 Schema Management

- Versioned via `schema_version` table
- Incremental `migrate()` function in `schema_design.py`
- Reference table seeding via migrations

---

## 6. CLI Tools

| Tool | Description |
|------|-------------|
| `run_pipeline.py` | Full 5-step pipeline orchestrator with skip/only flags per step |
| `dod_budget_downloader.py` | Multi-source document downloader (CLI + GUI) with `--retry-failures` support |
| `build_budget_db.py` | Database builder (CLI + GUI via `build_budget_gui.py`) |
| `repair_database.py` | Database repair/normalization |
| `validate_budget_data.py` | Data quality validation with JSON report output |
| `validate_budget_db.py` | Database-level validation suite |
| `enrich_budget_db.py` | PE enrichment pipeline |
| `search_budget.py` | CLI full-text search with filters, export (CSV/JSON), interactive REPL mode |
| `refresh_data.py` | Scheduled data refresh with automatic rollback, dry-run, webhook notifications |
| `stage_budget_data.py` | Optional Parquet staging layer (parse to Parquet, then load to SQLite) |
| `backfill_reference_tables.py` | Populate reference tables from existing flat data |

---

## 7. Infrastructure & Operations

### 7.1 Docker

- Production `Dockerfile` with non-root user (`appuser`), health check
- Multi-stage build (`Dockerfile.multistage`) for optimized image size
- Development `docker-compose.yml` with hot-reload and volume mounts
- Staging `docker-compose.staging.yml` with backup sidecar (6-hour cycle)

### 7.2 CI/CD

- **GitHub Actions CI:** Matrix testing (Python 3.11, 3.12), ruff lint, mypy type check, pytest with coverage (80% threshold on `api/` and `utils/`), Docker build validation
- **Automated data refresh:** Weekly cron via `refresh-data.yml`
- **Automated downloads:** Scheduled via `download.yml`
- **Deploy workflow:** Docker build/push to GHCR (template)

### 7.3 Monitoring & Backup

- `/health` and `/health/detailed` endpoints with uptime, request counts, error counts, DB metrics, response time tracking
- SQLite online backup via `scripts/backup_db.py` with `--keep N` pruning
- Structured access logging middleware
- Pre-commit hook: syntax, imports, secrets detection, code quality, schema validation

### 7.4 Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_DB_PATH` | `dod_budget.sqlite` | Database file path |
| `APP_PORT` | `8000` | API server port |
| `APP_LOG_FORMAT` | `text` | Logging format (`text` or `json`) |
| `APP_CORS_ORIGINS` | `*` | CORS allowed origins |
| `APP_DB_POOL_SIZE` | `10` | Connection pool size |
| `RATE_LIMIT_SEARCH` | `60` | Search rate limit (req/min/IP) |
| `RATE_LIMIT_DOWNLOAD` | `10` | Download rate limit (req/min/IP) |
| `RATE_LIMIT_DEFAULT` | `120` | Default rate limit (req/min/IP) |
| `TRUSTED_PROXIES` | (empty) | Trusted proxy IPs for X-Forwarded-For |

---

## 8. Data Coverage

| Dimension | Coverage |
|-----------|----------|
| **Services** | Army, Navy/USMC, Air Force, Space Force (FY2021+), Defense-Wide, Joint Staff |
| **Fiscal Years** | FY1998-1999, FY2010-2026 (FY2000-2009 gap: documents not yet acquired) |
| **Exhibit Types** | P-1, P-1R, P-5, R-1, R-2, R-3, R-4, O-1, M-1, C-1, RF-1 + OCO/supplemental variants |
| **Dollar Unit** | Thousands of dollars ($K) as published in source documents |
| **Classification** | Unclassified only |

---

## 9. Known Limitations

1. **FY2000-2009 data gap** — Documents for these fiscal years have not been downloaded or ingested
2. **PDF extraction accuracy** — Varies by document layout; some tables extract poorly from complex PDFs
3. **Appropriation codes** — Not fully parsed for all exhibit types
4. **Classified programs** — Excluded per DoD public release policy; budget totals will not match classified-inclusive figures
5. **Tag over-indexing** — Enrichment pipeline assigns overly broad tags for some categories (e.g., `rdte` on 97% of PEs). Tags covering >60% of programs are too broad for meaningful filtering. See TODO Group E in `docs/TODO_PLAN.md`.
6. **Dollar rounding** — Service/program totals computed from parsed line items may not match official totals exactly due to rounding and coverage gaps
7. **PDF-only PE handling** — D8Z Defense-Wide PEs that exist only in PDFs now have R-1 titles extracted from PDF pages and R-1 funding aggregated from R-2 sub-elements (fixed 2026-04-02). Some edge cases may remain for PEs with unusual PDF layouts.
8. **Description quality varies** — R-1 descriptions may contain page headers or artifacts; `_is_garbage_description()` filters the worst cases but some noise may remain. R-2 descriptions are cleaned via `clean_narrative()` but multi-page artifacts can still slip through.

---

## 10. Security

- **Input sanitization:** FTS5 queries sanitized via `sanitize_fts5_query()`; SQL parameters always bound (never interpolated); ORDER BY columns whitelisted
- **Content Security Policy:** Script sources restricted to `'self'`, `unpkg.com`, `cdn.jsdelivr.net`
- **Docker:** Non-root container user, database mounted as external volume
- **Rate limiting:** Per-IP with configurable limits per endpoint category
- **Headers:** `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`
