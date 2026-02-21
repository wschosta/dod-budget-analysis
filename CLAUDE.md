# CLAUDE.md

Guide for AI assistants working on this codebase.

## Project Overview

DoD Budget Analysis is a Python toolkit for downloading, parsing, normalizing, and querying Department of Defense budget justification documents. It includes:

- **Bulk document downloader** with Playwright browser automation for WAF-protected sites
- **Excel/PDF parser** that ingests budget exhibits into a SQLite database
- **Full-text search** via SQLite FTS5 with BM25 ranking
- **FastAPI REST API** with rate limiting, CORS, ETag caching, and OpenAPI docs
- **Web frontend** using Jinja2 templates, HTMX, Chart.js, and custom JavaScript
- **Validation/reconciliation framework** with 10+ data quality checks
- **Data enrichment pipeline** for PE index, descriptions, tags, lineage, and project-level decomposition

## Quick Reference

```bash
# Install dependencies
pip install -r requirements-dev.txt
python -m playwright install chromium

# Run tests (82 test files)
python -m pytest tests/ -v

# Run with coverage (80% minimum on api/ and utils/)
python -m pytest tests/ --cov=api --cov=utils --cov-report=term-missing --cov-fail-under=80

# Start the API server (dev mode)
uvicorn api.app:app --reload --port 8000

# Lint
ruff check . --select=E,W,F --ignore=E501 --exclude=DoD_Budget_Documents

# Type check
mypy api/ utils/ --ignore-missing-imports

# Format
black .

# Docker
docker compose up --build
```

## Repository Structure

```
dod-budget-analysis/
├── api/                          # FastAPI application
│   ├── app.py                    # App factory, middleware, rate limiting, health endpoints
│   ├── database.py               # DB path resolution, connection pool, get_db() dependency
│   ├── models.py                 # Pydantic request/response models
│   └── routes/                   # Route modules (one file per router group)
│       ├── aggregations.py       # GET /api/v1/aggregations
│       ├── budget_lines.py       # GET /api/v1/budget-lines, /budget-lines/{id}
│       ├── dashboard.py          # Dashboard data endpoints
│       ├── download.py           # GET /api/v1/download (streaming CSV/NDJSON)
│       ├── feedback.py           # POST /api/v1/feedback
│       ├── frontend.py           # GET /, /charts, /partials/* (HTML routes)
│       ├── metadata.py           # GET /api/v1/metadata
│       ├── pe.py                 # PE-centric views, funding, sub-elements
│       ├── reference.py          # GET /api/v1/reference/{type}
│       └── search.py             # GET /api/v1/search (FTS5 full-text search)
├── utils/                        # Shared utility library (16 modules)
│   ├── cache.py                  # TTLCache implementation
│   ├── common.py                 # format_bytes, elapsed, sanitize_filename
│   ├── config.py                 # AppConfig, DatabaseConfig, DownloadConfig, KnownValues
│   ├── database.py               # batch_insert/upsert, FTS5 helpers, QueryBuilder
│   ├── formatting.py             # format_amount, extract_snippet, highlight_terms
│   ├── http.py                   # RetryStrategy, SessionManager, TimeoutManager
│   ├── manifest.py               # File manifest tracking with hashes
│   ├── metadata.py               # Metadata extraction and management
│   ├── patterns.py               # Regex: PE_NUMBER, FISCAL_YEAR, ACCOUNT_CODE_TITLE
│   ├── pdf_sections.py           # Narrative section parsing from PDFs
│   ├── progress.py               # ProgressTracker variants (Terminal, Silent, File)
│   ├── query.py                  # build_where_clause, build_order_clause
│   ├── search_parser.py          # Search query parsing and tokenization
│   ├── strings.py                # safe_float, normalize_whitespace, sanitize_fts5_query
│   └── validation.py             # ValidationIssue, ValidationResult, ValidationRegistry
├── tests/                        # pytest test suite (82 test files)
│   ├── conftest.py               # Session-scoped fixtures: test DBs, Excel/PDF fixtures
│   ├── fixtures/                 # Static test fixture data (Excel files, expected outputs)
│   └── optimization_validation/  # Advanced optimization tests
├── scripts/                      # Operational scripts
│   ├── backup_db.py              # SQLite online backup
│   ├── cleanup_and_restart.py    # Environment cleanup and restart
│   ├── exhibit_audit.py          # Exhibit data auditing
│   ├── generate_data_dictionary.py  # Data dictionary generation
│   ├── generate_expected_output.py  # Expected test output generation
│   ├── hooks/pre-commit-hook.py  # Pre-commit hook (syntax, imports, secrets, quality)
│   ├── monitor_build.py          # Build monitoring
│   ├── pdf_quality_audit.py      # PDF extraction quality audit
│   ├── profile_queries.py        # Query performance profiling
│   ├── reconcile_budget_data.py  # Cross-service/exhibit reconciliation
│   ├── run_optimization_tests.py # Optimization test runner
│   ├── run_precommit_checks.py   # Pre-commit check runner
│   ├── scheduled_download.py     # Automated download scheduling
│   ├── smoke_test.py             # Post-deploy smoke tests
│   ├── verify_optimization.py    # Optimization verification
│   └── test_edge_cases.py        # Edge case test script
├── pipeline/                     # Data pipeline modules
│   ├── backfill.py               # Reference table backfill logic
│   ├── builder.py                # Database build orchestration
│   ├── db_validator.py           # Database-level validation
│   ├── enricher.py               # PE enrichment logic
│   ├── exhibit_catalog.py        # Exhibit type catalog
│   ├── exhibit_inventory.py      # Exhibit type discovery
│   ├── gui.py                    # tkinter GUI for pipeline
│   ├── refresh.py                # Data refresh with rollback
│   ├── schema.py                 # Schema management
│   ├── search.py                 # CLI search interface
│   ├── staging.py                # Parquet staging layer (decouple parsing from DB loading)
│   └── validator.py              # Data quality validation
├── downloader/                   # Document downloader modules
│   ├── core.py                   # Core download logic
│   ├── gui.py                    # tkinter GUI for downloader
│   ├── manifest.py               # File manifest tracking
│   ├── metadata.py               # Download-time metadata detection (exhibit type, cycle, service)
│   └── sources.py                # Source discovery and configuration
├── templates/                    # Jinja2 HTML templates
│   ├── base.html                 # Base layout template
│   ├── index.html                # Search page
│   ├── charts.html               # Visualizations page
│   ├── dashboard.html            # Dashboard page
│   ├── about.html                # About page
│   ├── programs.html             # Programs listing page
│   ├── program-detail.html       # Individual program detail page
│   ├── errors/                   # Custom error pages (404, 500)
│   └── partials/                 # HTMX partial responses
│       ├── advanced-search.html  # Advanced search form partial
│       ├── detail.html           # Detail view partial
│       ├── feedback.html         # Feedback form partial
│       ├── glossary.html         # Glossary terms partial
│       ├── program-descriptions.html  # Program descriptions partial
│       ├── program-list.html     # Program list partial
│       ├── results.html          # Search results partial
│       └── toast.html            # Toast notification partial
├── static/                       # Static frontend assets
│   ├── css/main.css              # Main stylesheet (supports dark mode via CSS variables)
│   └── js/                       # JavaScript modules
│       ├── app.js                # Main application JS (search, HTMX integration)
│       ├── charts.js             # Charts page Chart.js visualizations
│       ├── checkbox-select.js    # Custom checkbox-select dropdown component
│       ├── dark-mode.js          # Dark mode toggle and persistence
│       ├── dashboard.js          # Dashboard Chart.js visualizations
│       ├── program-detail.js     # Program detail page interactions
│       └── search.js             # Search-specific JS functionality
├── docs/                         # Documentation
│   ├── instructions/             # Agent instruction files (LION, TIGER, BEAR, OH MY)
│   ├── wiki/                     # Extended wiki documentation
│   ├── design/                   # Design documents (api_design.py, frontend_design.py, deployment_design.py)
│   ├── *.md                      # Various planning and specification docs
│   └── AGENT_PROMPTS.md          # Agent prompt documentation
├── docker/                       # Staging Docker configs
│   ├── Dockerfile.multistage     # Multi-stage production Dockerfile
│   └── docker-compose.staging.yml  # Staging compose configuration
├── .github/
│   ├── ISSUE_TEMPLATE/           # GitHub issue templates
│   │   ├── bug_report.md         # Bug report template
│   │   └── feature_request.md    # Feature request template
│   └── workflows/                # CI/CD workflows
│       ├── ci.yml                # Main CI: lint, type check, test groups, coverage, Docker build
│       ├── deploy.yml            # Docker build/push to GHCR + deploy template
│       ├── download.yml          # Automated document download
│       └── refresh-data.yml      # Scheduled data refresh
│
│ # Root-level pipeline scripts
├── build_budget_db.py            # Main data ingestion (Excel + PDF parsing)
├── build_budget_gui.py           # tkinter GUI for build_budget_db
├── dod_budget_downloader.py      # Multi-source document downloader
├── enrich_budget_db.py           # PE enrichment (index, descriptions, tags, lineage, project decomposition)
├── exhibit_catalog.py            # 9 exhibit types: P-1, P-5, R-1, R-2, O-1, etc.
├── exhibit_type_inventory.py     # Exhibit type discovery and inventory
├── refresh_data.py               # Scheduled data refresh with rollback
├── run_pipeline.py               # Full pipeline: build -> validate -> enrich
├── stage_budget_data.py          # Parquet staging CLI (parse -> Parquet -> SQLite)
├── schema_design.py              # DB schema, migrations, reference table seeding
├── search_budget.py              # CLI full-text search interface
├── validate_budget_data.py       # Data quality validation checks
├── validate_budget_db.py         # Database-level validation suite
└── backfill_reference_tables.py  # Populate reference tables from flat data
```

## Data Flow

```
DoD websites (Comptroller, Army, Navy, Air Force, Defense-Wide)
        |
        v
dod_budget_downloader.py  ->  DoD_Budget_Documents/  (PDFs, XLSX, CSV, ZIP)
        |
        v  (optional: --use-staging)
stage_budget_data.py      ->  staging/  (Parquet files + metadata)
        |
        v
build_budget_db.py        ->  dod_budget.sqlite  (SQLite + FTS5)
        |
        v
validate_budget_data.py   ->  data_quality_report.json
        |
        v
enrich_budget_db.py       ->  pe_index, pe_descriptions, pe_tags, pe_lineage, project_descriptions
        |
        v
api/app.py (FastAPI)      ->  Browser (HTMX + Chart.js)
        |
        v
refresh_data.py           ->  Weekly scheduled refresh with automatic rollback
```

The full pipeline can be run with `python run_pipeline.py`.

## Architecture Decisions

- **Database:** SQLite with FTS5 full-text search, WAL mode, raw SQL (no ORM)
- **API framework:** FastAPI with Pydantic v2 models, auto-generated OpenAPI docs
- **Frontend:** Server-side rendered Jinja2 templates with HTMX for dynamic updates, Chart.js for visualizations, and vanilla JS modules
- **Browser automation:** Playwright (Chromium) for WAF-protected / SharePoint sites
- **HTTP scraping:** requests + BeautifulSoup for standard HTML sites
- **Connection pooling:** Custom `_ConnectionPool` class in `api/database.py` (queue-based, thread-safe)
- **File paths:** Use `Path` objects, not raw strings
- **Dark mode:** CSS variables for theming (no hardcoded colors)

## Testing

### Framework and Configuration

- **Framework:** pytest with pytest-cov
- **Config:** `pyproject.toml` — testpaths=`["tests"]`, addopts=`"-v --tb=short"`
- **Coverage:** 80% minimum threshold on `api/` and `utils/` directories
- **Python versions:** 3.11, 3.12 (CI matrix); `requires-python >= 3.10`

### Running Tests

```bash
# Full suite
python -m pytest tests/ -v

# Specific module
python -m pytest tests/test_api.py -v

# Specific test
python -m pytest tests/test_rate_limiter.py::TestSearchRateLimit -v

# With coverage
python -m pytest tests/ --cov=api --cov=utils --cov-report=term-missing --cov-fail-under=80

# Skip GUI tracker and optimization validation (as CI does)
python -m pytest tests/ --ignore=tests/test_gui_tracker.py --ignore=tests/optimization_validation
```

### Test Groups (as organized in CI)

1. **Unit tests:** utilities, patterns, config, validation, query builders
2. **API tests:** endpoints, models, search, download, rate limiting, charts, PE
3. **Frontend tests:** routes, helpers, GUI features, fixes, accessibility
4. **Data pipeline tests:** build, enrichment, schema, pipeline, exhibits, manifests, PDF
5. **Performance tests:** load, benchmarks, optimization
6. **Code quality:** pre-commit checks and hook tests
7. **Advanced:** BEAR (schema/migration/Docker/refresh), TIGER (caching/performance/feedback/validation), LION (DB integrity), and EAGLE (frontend/PE) groups
8. **Operational tests:** refresh workflow, scheduled download
9. **GUI tracker tests:** tkinter tests (requires Xvfb for headless display)
10. **Docker build validation:** separate CI job verifying Docker image builds and imports

### Test Fixtures

| Fixture | Scope | Description |
|---------|-------|-------------|
| `fixtures_dir` | session | Temp directory with Excel + PDF fixture files |
| `fixtures_dir_excel_only` | session | Temp directory with only Excel fixtures (no PDF) |
| `test_db` | session | Pre-built SQLite DB from all fixtures |
| `test_db_excel_only` | session | Pre-built SQLite DB from Excel-only fixtures |
| `bad_excel` | session | Intentionally malformed Excel file |
| `tmp_db` | function | Empty SQLite DB for unit tests |

Static fixture files live in `tests/fixtures/` (Excel samples, expected outputs).

### Writing New Tests

1. Create `tests/test_<module>.py`
2. Use shared fixtures from `tests/conftest.py` where possible
3. For API tests: create an in-memory or `tmp_path`-backed SQLite DB, build the schema with `executescript()`, and use `TestClient(create_app(db_path=...))`
4. Rate-limiter tests must clear `api.app._rate_counters` between cases (use `autouse=True` fixture)
5. Module-scoped `client` fixtures share global DB-path state — if a test changes the DB path, put it in a separate module
6. Use `test_db_excel_only` instead of `test_db` when tests only need Excel data (avoids pdfplumber PanicException)

## Code Standards

### Formatting and Linting

- **Formatter:** black (line length 100)
- **Linter:** ruff (`--select=E,W,F --ignore=E501`)
- **Type checker:** mypy on `api/` and `utils/` (`--ignore-missing-imports`)

### Conventions

- PEP 8 naming conventions
- Type annotations required on new functions and methods
- `Path` objects over raw strings for file paths
- `sqlite3` directly — no ORM; raw SQL is intentional
- `logging` module instead of `print()` in library code
- Small, focused functions (single responsibility)
- CSS variables for colors/theming (no hardcoded color values)
- Do not add external dependencies without discussion

### Commit Messages

```
<TYPE>: <short imperative summary (<=72 chars)>

<optional body explaining the "why", wrapped at 100 chars>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`

### Branch Naming

```
claude/<ticket-id>-<short-description>   # agent branches
feat/<short-description>                 # new features
fix/<short-description>                  # bug fixes
docs/<short-description>                 # documentation only
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_DB_PATH` | `dod_budget.sqlite` | Path to SQLite database |
| `APP_PORT` | `8000` | API server port |
| `APP_LOG_FORMAT` | `text` | Logging format: `text` or `json` |
| `APP_CORS_ORIGINS` | `*` | Comma-separated CORS origins |
| `APP_DB_POOL_SIZE` | `10` | Max DB connections in pool |
| `RATE_LIMIT_SEARCH` | `60` | Search requests per minute per IP |
| `RATE_LIMIT_DOWNLOAD` | `10` | Download requests per minute per IP |
| `RATE_LIMIT_DEFAULT` | `120` | Default requests per minute per IP |
| `TRUSTED_PROXIES` | (empty) | Comma-separated trusted proxy IPs |

## API Endpoints

All API routes are prefixed with `/api/v1`. OpenAPI docs at `/docs`, ReDoc at `/redoc`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/search` | GET | Full-text search (FTS5 + BM25 ranking) |
| `/api/v1/budget-lines` | GET | Filtered, paginated budget line items |
| `/api/v1/budget-lines/{id}` | GET | Single budget line item detail |
| `/api/v1/aggregations` | GET | GROUP BY summaries for charts/dashboards |
| `/api/v1/download` | GET | Streaming CSV/NDJSON export |
| `/api/v1/reference/{type}` | GET | Reference data (services, exhibit types, FYs) |
| `/api/v1/metadata` | GET | Database and dataset metadata |
| `/api/v1/feedback` | POST | User feedback submission |
| `/health` | GET | Health check (DB connectivity) |
| `/health/detailed` | GET | Detailed metrics (uptime, counters, query stats) |

Frontend HTML routes: `/` (search), `/charts`, `/dashboard`, `/about`, `/programs`, `/programs/{pe_number}`, `/partials/*` (HTMX partials).

Amounts are in **thousands of dollars ($K)** unless `amount_unit` says otherwise.

## Key Technical Details

### Database Schema

The primary tables in `dod_budget.sqlite`:

- `budget_lines` — Flat fact table with all parsed budget line items
- `pdf_pages` — Extracted PDF page text and table data
- `ingested_files` — File manifest (path, type, size, modified time, status, exhibit_type, budget_cycle, download_timestamp, service_org)
- `pdf_pe_numbers` — PE-to-PDF page junction table for direct joins
- `budget_lines_fts` / `pdf_pages_fts` — FTS5 virtual tables for full-text search
- Reference tables: `services_agencies`, `exhibit_types`, `appropriation_titles`, `budget_cycles`
- Enrichment tables: `pe_index`, `pe_descriptions`, `pe_tags`, `pe_lineage`, `project_descriptions`
  - `pe_tags` confidence levels: 1.0 (structured field match), 0.9 (budget_lines keyword match), 0.85 (project-level keyword), 0.8 (PDF narrative keyword), 0.7 (LLM-generated); includes `source_files` JSON column for provenance tracking

Schema is versioned via `schema_version` table with a `migrate()` function in `schema_design.py`.

### Pre-commit Hook

Install with:
```bash
cp scripts/hooks/pre-commit-hook.py .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

Checks: optimization tests, module imports, syntax, code quality (no debug statements), security (no hardcoded secrets), database schema, required files.

### Docker

- Base image: `python:3.12-slim`
- Non-root user (`appuser`) for security
- Database mounted as volume at `/app/dod_budget.sqlite`
- Health check via `/health` endpoint
- Development: `docker compose up --build` (hot-reload enabled)
- Staging: `docker/docker-compose.staging.yml`
- Production multi-stage: `docker/Dockerfile.multistage`

## Common Tasks

### Adding a New API Endpoint

1. Create or edit a route file in `api/routes/`
2. Define Pydantic models in `api/models.py` if needed
3. Register the router in `api/app.py` via `app.include_router()`
4. Use `Depends(get_db)` for database access
5. Add tests in `tests/test_<endpoint>.py` using `TestClient(create_app(db_path=...))`
6. Ensure rate limiting behavior is tested if the endpoint has custom limits

### Adding a New Frontend Page

1. Create a template in `templates/` (extend `base.html`)
2. For HTMX partials, add to `templates/partials/`
3. Add a route in `api/routes/frontend.py`
4. Add JavaScript in `static/js/` if needed
5. Use CSS variables from `static/css/main.css` for theming (dark mode compatibility)
6. Add tests in `tests/test_frontend_routes.py`

### Adding a New Utility Module

1. Create `utils/<module>.py`
2. Export public symbols from `utils/__init__.py`
3. Add tests in `tests/test_<module>.py`
4. Ensure coverage stays above 80%

### Modifying the Database Schema

1. Update DDL in `schema_design.py`
2. Add a new migration to the `migrate()` function with incremented version
3. Test with `tests/test_schema_design.py`
4. Update `build_budget_db.py` if the ingestion pipeline is affected

### Pre-PR Checklist

- `python -m pytest tests/ -v` passes
- `ruff check . --select=E,W,F --ignore=E501 --exclude=DoD_Budget_Documents` reports no errors
- `mypy api/ utils/ --ignore-missing-imports` passes
- New public functions have type annotations
- New endpoints have corresponding tests
- No hardcoded colors (use CSS variables)
- No secrets, credentials, or large binary files committed
