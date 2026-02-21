# Architecture Overview

This document describes the overall architecture of the DoD Budget Analysis
project, including the data pipeline, API server, frontend, and key
technology decisions.

---

## System Overview

The DoD Budget Analysis project is a complete pipeline for downloading,
parsing, normalizing, querying, and visualizing Department of Defense budget
justification documents. It transforms thousands of Excel spreadsheets and
PDF documents from DoD websites into a searchable, queryable database served
through a REST API and web frontend.

```
DoD websites (Comptroller, Army, Navy, Air Force, Defense-Wide)
        |
        v
dod_budget_downloader.py  -->  DoD_Budget_Documents/  (PDFs, XLSX, CSV, ZIP)
        |
        v
build_budget_db.py        -->  dod_budget.sqlite  (SQLite + FTS5)
        |
        v
validate_budget_data.py   -->  data_quality_report.json
        |
        v
enrich_budget_db.py       -->  pe_index, pe_descriptions, pe_tags, pe_lineage
        |
        v
api/app.py (FastAPI)      -->  Browser (HTMX + Chart.js)
        |
        v
refresh_data.py           -->  Weekly scheduled refresh with automatic rollback
```

The full pipeline can be run with `python run_pipeline.py`.

---

## Key Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Database** | SQLite with FTS5 | Single-file deployment, zero configuration, full-text search built in, excellent read performance |
| **API framework** | FastAPI | Auto-generated OpenAPI docs, async support, Pydantic validation, high performance |
| **Frontend** | Jinja2 + HTMX + Chart.js | Server-side rendering with progressive enhancement, no build step, minimal JavaScript |
| **Browser automation** | Playwright (Chromium) | Required for WAF-protected and SharePoint-hosted DoD sites |
| **HTTP scraping** | requests + BeautifulSoup | Standard HTML sites that do not require browser automation |

For detailed decision rationale, see the Architecture Decision Records:

- [ADR 001: API Framework](../decisions/001-api-framework.md)
- [ADR 002: Frontend Technology](../decisions/002-frontend-technology.md)
- [ADR 003: FTS5 Search](../decisions/003-fts5-search.md)

---

## Component Overview

### Data Pipeline Components

| Component | Script | Description |
|-----------|--------|-------------|
| **Downloader** | `dod_budget_downloader.py` | Multi-source document downloader with parallel discovery, parallel downloads, and Playwright browser automation |
| **Builder** | `build_budget_db.py` | Parses Excel exhibits and PDF documents into a normalized SQLite database with FTS5 indexes |
| **Validator** | `validate_budget_data.py` | Runs 10+ data quality checks and produces a validation report |
| **Enricher** | `enrich_budget_db.py` | Adds PE index, descriptions, tags, and lineage data |
| **Pipeline Runner** | `run_pipeline.py` | Orchestrates the full pipeline: build, validate, enrich |
| **Data Refresher** | `refresh_data.py` | Scheduled refresh with automatic rollback on failure |

### Application Components

| Component | Location | Description |
|-----------|----------|-------------|
| **API Server** | `api/` | FastAPI application with REST endpoints, rate limiting, and CORS |
| **Frontend** | `templates/`, `static/` | Jinja2 templates with HTMX for dynamic updates and Chart.js for visualizations |
| **Utilities** | `utils/` | 16 shared modules for database access, HTTP, validation, formatting, etc. |
| **Scripts** | `scripts/` | Operational scripts for backup, monitoring, profiling, and maintenance |

---

## Database Architecture

### SQLite with WAL Mode

The project uses SQLite as its sole database, chosen for its zero-configuration
deployment model and excellent read performance. A single
`dod_budget.sqlite` file contains all application state.

**WAL (Write-Ahead Logging) mode** is enabled for concurrent read access.
Multiple API request handlers can read the database simultaneously without
blocking each other, while the data pipeline can write without blocking
readers.

### Schema Structure

The database contains four categories of tables:

1. **Core tables**: `budget_lines` (structured Excel data) and `pdf_pages`
   (extracted PDF text)
2. **FTS5 virtual tables**: `budget_lines_fts` and `pdf_pages_fts` for
   full-text search with BM25 ranking
3. **Reference tables**: `services_agencies`, `exhibit_types`,
   `appropriation_titles`, `budget_cycles`
4. **Enrichment tables**: `pe_index`, `pe_descriptions`, `pe_tags`,
   `pe_lineage`

Schema is versioned via the `schema_version` table with an incremental
`migrate()` function in `schema_design.py`.

See [Database Schema](database-schema.md) for complete table definitions.

### Connection Pooling

The API server uses a custom queue-based connection pool (`_ConnectionPool`
in `api/database.py`). Key characteristics:

- Thread-safe via `queue.Queue`
- Configurable pool size (default: 10, via `APP_DB_POOL_SIZE`)
- Each connection has `row_factory = sqlite3.Row` and optimized PRAGMAs
- Connections are reused across requests for efficiency
- Pool is exposed via FastAPI's `Depends(get_db)` dependency injection

### Full-Text Search

SQLite FTS5 provides full-text search with BM25 relevance ranking. Two
FTS5 virtual tables are maintained:

- `budget_lines_fts` -- indexes line item titles and organization names
- `pdf_pages_fts` -- indexes PDF page text and table data

Both tables use content-sync triggers to stay up to date with their source
tables. During bulk ingestion, triggers are temporarily disabled and the
FTS5 indexes are rebuilt in batch for a ~30% performance improvement.

---

## API Architecture

### Application Factory

The API uses an application factory pattern (`create_app()` in `api/app.py`)
that accepts a configurable database path. This enables:

- Different database paths for testing vs. production
- Clean dependency injection via FastAPI's `Depends()`
- Testability with `TestClient(create_app(db_path=...))`

### Route Modules

Each API route group is implemented as a separate module under `api/routes/`:

```
api/routes/
  aggregations.py   # GET /api/v1/aggregations
  budget_lines.py   # GET /api/v1/budget-lines, /budget-lines/{id}
  dashboard.py      # Dashboard data endpoints
  download.py       # GET /api/v1/download (streaming CSV/NDJSON)
  feedback.py       # POST /api/v1/feedback
  frontend.py       # HTML routes (/, /charts, /dashboard, /about, /programs, /partials/*)
  metadata.py       # GET /api/v1/metadata
  pe.py             # PE-centric views, funding, sub-elements
  reference.py      # GET /api/v1/reference/{type}
  search.py         # GET /api/v1/search (FTS5 full-text search)
```

Routers are registered in `api/app.py` via `app.include_router()`.

### Pydantic Models

Request validation and response serialization use Pydantic v2 models
defined in `api/models.py`. This provides:

- Automatic request parameter validation with clear error messages
- Response schema documentation in OpenAPI docs
- Type-safe data handling throughout the API layer

### Middleware

The application includes several middleware layers:

1. **CORS middleware** -- Configurable cross-origin resource sharing
2. **Security headers** -- CSP, X-Content-Type-Options, X-Frame-Options
3. **Rate limiting** -- Per-IP request rate limiting with configurable limits
4. **ETag caching** -- Conditional responses for bandwidth reduction
5. **Request timing** -- Tracks response times for the health endpoint

### Rate Limiting

Rate limiting is implemented as middleware in `api/app.py` using an in-memory
counter per IP address with a fixed 60-second sliding window. Different
endpoints have different limits:

- Search: 60/min (configurable via `RATE_LIMIT_SEARCH`)
- Download: 10/min (configurable via `RATE_LIMIT_DOWNLOAD`)
- Default: 120/min (configurable via `RATE_LIMIT_DEFAULT`)

The `TRUSTED_PROXIES` environment variable configures trusted proxy IPs
for correct client IP extraction from `X-Forwarded-For` headers.

---

## Frontend Architecture

### Server-Side Rendering

The frontend uses **Jinja2 templates** rendered server-side by FastAPI route
handlers in `api/routes/frontend.py`. All pages extend `templates/base.html`
which provides the common layout, navigation, and asset loading.

### HTMX for Dynamic Updates

**HTMX** provides dynamic page updates without a JavaScript framework:

- Search results load via AJAX into partial templates
- Filter changes trigger server requests that return HTML fragments
- Detail views open inline without full page navigation
- Partial templates live in `templates/partials/`

This approach keeps the frontend simple (no build step, no framework) while
providing a responsive user experience.

### Chart.js Visualizations

**Chart.js** powers the data visualizations on the `/charts` and `/dashboard`
pages. Chart configurations are defined in:

- `static/js/charts.js` -- Charts page visualizations
- `static/js/dashboard.js` -- Dashboard visualizations

Charts fetch data from the API aggregation endpoints and render client-side.

### JavaScript Modules

Frontend JavaScript is organized as vanilla ES modules:

| Module | Purpose |
|--------|---------|
| `static/js/app.js` | Main application (search, HTMX integration) |
| `static/js/charts.js` | Charts page Chart.js visualizations |
| `static/js/checkbox-select.js` | Custom checkbox-select dropdown component |
| `static/js/dark-mode.js` | Dark mode toggle and persistence |
| `static/js/dashboard.js` | Dashboard Chart.js visualizations |
| `static/js/program-detail.js` | Program detail page interactions |
| `static/js/search.js` | Search-specific functionality |

### Dark Mode

Dark mode is implemented using **CSS custom properties** (variables) in
`static/css/main.css`. The `dark-mode.js` module toggles a class on the
document root, which switches the CSS variable values. This approach:

- Avoids hardcoded color values throughout the CSS
- Persists the user's preference in `localStorage`
- Respects the system `prefers-color-scheme` media query as the default

---

## Data Pipeline Detail

### Stage 1: Download

`dod_budget_downloader.py` discovers and downloads budget documents from
five DoD source websites:

1. **Comptroller** (comptroller.defense.gov) -- Standard HTTP
2. **Army** -- Playwright browser automation (WAF-protected)
3. **Navy** -- Playwright browser automation (SharePoint-hosted)
4. **Air Force** -- Standard HTTP / Playwright
5. **Defense-Wide** -- Standard HTTP

Discovery and download are parallelized for performance. Downloaded files
are stored in `DoD_Budget_Documents/` organized by source and fiscal year.
A file manifest tracks download status, file hashes, and sizes.

### Stage 2: Parse and Load

`build_budget_db.py` processes downloaded files:

1. **Excel parsing** -- Reads budget exhibit spreadsheets, maps columns to
   canonical field names using `utils/config.py:ColumnMapping`, and inserts
   rows into the `budget_lines` table
2. **PDF parsing** -- Extracts text and tables from PDF documents using
   `pdfplumber`, stores page-level content in the `pdf_pages` table
3. **FTS5 indexing** -- Builds full-text search indexes after data loading
4. **File tracking** -- Records processed files in `ingested_files` for
   incremental update support

### Stage 3: Validate

`validate_budget_data.py` runs 10+ data quality checks:

- Missing or null values in required fields
- Amount validation (non-negative, reasonable ranges)
- Fiscal year format and range validation
- Organization name validation against known values
- Exhibit type validation
- Duplicate detection
- Cross-service reconciliation

Results are written to `data_quality_report.json`.

### Stage 4: Enrich

`enrich_budget_db.py` adds contextual data:

- **PE index** -- Master index of all program elements
- **PE descriptions** -- Narrative descriptions from R-2 exhibits and PDFs
- **PE tags** -- Keyword categorizations for enhanced search
- **PE lineage** -- Historical tracking of PE changes over time

### Stage 5: Serve

The FastAPI application serves the enriched database through:

- REST API endpoints for programmatic access
- Server-rendered HTML pages for browser-based exploration
- Full-text search with relevance ranking
- Aggregations and visualizations for analysis

---

## Security Considerations

### Content Security Policy

All responses include a `Content-Security-Policy` header that restricts
script sources to `'self'`, `unpkg.com`, and `cdn.jsdelivr.net` (for HTMX
and Chart.js CDN resources). Inline scripts are allowed via `'unsafe-inline'`
for HTMX attribute handlers.

### Rate Limiting

Per-IP rate limiting protects against abuse and ensures fair resource
allocation. The download endpoint has a stricter limit (10/min) since it
produces larger responses.

### Input Sanitization

- FTS5 search queries are sanitized via `utils/strings.py:sanitize_fts5_query()`
  to prevent FTS5 injection
- SQL query parameters are always passed as bound parameters (never string
  interpolation)
- Column names in ORDER BY clauses are validated against a whitelist
- Pydantic models validate all request parameters

### Docker Security

- Container runs as non-root user (`appuser`)
- Database mounted as a volume (not baked into the image)
- Health check endpoint available for orchestrator monitoring
- No secrets required in the current configuration

### Additional Headers

| Header | Value | Purpose |
|--------|-------|---------|
| `X-Content-Type-Options` | `nosniff` | Prevent MIME type sniffing |
| `X-Frame-Options` | `DENY` | Prevent clickjacking |

---

## Directory Structure

```
dod-budget-analysis/
  api/                    # FastAPI application
    app.py                # App factory, middleware, rate limiting
    database.py           # Connection pool, get_db() dependency
    models.py             # Pydantic request/response models
    routes/               # One file per router group
  utils/                  # 16 shared utility modules
  templates/              # Jinja2 HTML templates
    partials/             # HTMX partial response templates
    errors/               # Custom error pages
  static/                 # Frontend assets
    css/main.css          # Stylesheet with CSS variables
    js/                   # JavaScript modules
  tests/                  # 75 test files
    conftest.py           # Shared fixtures
    fixtures/             # Static test data
  scripts/                # Operational scripts
  docs/                   # Documentation
    developer/            # Developer documentation (this directory)
    decisions/            # Architecture Decision Records
    user-guide/           # End-user documentation
  .github/workflows/      # CI/CD pipelines
  docker/                 # Staging Docker configs
```

---

## Related Documentation

- [API Reference](api-reference.md) -- Complete endpoint documentation
- [Database Schema](database-schema.md) -- Table definitions and relationships
- [Utilities Reference](utilities.md) -- Shared utility module documentation
- [Testing](testing.md) -- Test framework, fixtures, and patterns
- [Deployment](deployment.md) -- Environment configuration and operations
- [Performance](performance.md) -- Optimization details and benchmarks
- [ADR 001: API Framework](../decisions/001-api-framework.md)
- [ADR 002: Frontend Technology](../decisions/002-frontend-technology.md)
- [ADR 003: FTS5 Search](../decisions/003-fts5-search.md)
