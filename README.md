# DoD Budget Analysis

A comprehensive Python toolkit for downloading, parsing, normalizing, and querying Department of Defense budget justification documents. Features a bulk document downloader, Excel/PDF parser, SQLite database with full-text search, a FastAPI REST API, a web frontend with interactive charts, and a data validation framework.

## Features

- **Multi-source document downloader** across five DoD budget data sources with Playwright browser automation for WAF-protected sites
- **Excel/PDF parser** that ingests 11 budget exhibit types (P-1, R-1, O-1, M-1, C-1, and more) into a SQLite database
- **Full-text search** via SQLite FTS5 with BM25 relevance ranking
- **FastAPI REST API** with rate limiting, CORS, ETag caching, and auto-generated OpenAPI docs
- **Web frontend** using Jinja2 templates, HTMX for dynamic updates, and Chart.js for visualizations
- **Data validation framework** with 10+ automated quality checks and cross-service reconciliation
- **Data enrichment pipeline** for program element descriptions, tags, and lineage tracking
- **Performance optimized** — 5-15x faster downloads, 75-90% faster PDF processing

## Quick Start

```bash
# Clone and install
git clone https://github.com/wschosta/dod-budget-analysis.git
cd dod-budget-analysis
pip install -r requirements.txt
python -m playwright install chromium

# Download budget documents
python dod_budget_downloader.py --years 2026 --sources all

# Build the database
python build_budget_db.py

# Start the web UI and API
uvicorn api.app:app --reload --port 8000
# Open http://localhost:8000
```

Or use Docker:

```bash
docker compose up --build
```

## Data Sources

| Source | Website | Method |
|--------|---------|--------|
| **Comptroller** | [comptroller.war.gov](https://comptroller.war.gov/Budget-Materials/) | Direct HTTP |
| **Defense Wide** | [comptroller.war.gov](https://comptroller.war.gov/Budget-Materials/) | Direct HTTP |
| **US Army** | [asafm.army.mil](https://www.asafm.army.mil/Budget-Materials/) | Playwright (WAF) |
| **US Navy** | [secnav.navy.mil](https://www.secnav.navy.mil/fmc/fmb/Pages/archive.aspx) | Playwright (SharePoint) |
| **US Air Force** | [saffm.hq.af.mil](https://www.saffm.hq.af.mil) | Playwright (WAF) |

Downloads PDFs, Excel spreadsheets (`.xlsx`, `.xls`), ZIP archives, and CSV files.

## Data Pipeline

```
DoD websites (Comptroller, Army, Navy, Air Force, Defense-Wide)
        |
        v
dod_budget_downloader.py  ->  DoD_Budget_Documents/  (PDFs, XLSX, CSV, ZIP)
        |
        v
build_budget_db.py        ->  dod_budget.sqlite  (SQLite + FTS5)
        |
        v
validate_budget_data.py   ->  data_quality_report.json
        |
        v
enrich_budget_db.py       ->  pe_index, pe_descriptions, pe_tags, pe_lineage
        |
        v
api/app.py (FastAPI)      ->  Browser (HTMX + Chart.js)
```

## Features

- **Multi-source discovery** across six DoD budget data sources (incl. Navy archive)
- **Automated browser downloads** for WAF-protected and SharePoint sites using Playwright (Chromium)
- **Smart file skipping** - previously downloaded files (>1 KB) are skipped instantly without network requests
- **GUI progress window** (tkinter) with:
  - Discovery phase progress bar while scanning sources
  - Download phase progress bar with per-file speed and ETA
  - Running log of completed files
  - Session vs. total database size metrics
- **Terminal-only mode** (`--no-gui`) with ASCII progress bars
- **Failure logging** - timestamped `.txt` log with URLs for any failed downloads
- **Configurable** - filter by fiscal year, source, and file type
- **Cross-source deduplication** - identical files from multiple sources (e.g. navy and navy-archive) downloaded only once
- **Navy exhibit type mapping** - automatic classification of Navy appropriation book filenames to exhibit types
- **Defense-Wide classification** - pattern-based classification of Defense-Wide agency documents
- **Parquet staging** - optional intermediate Parquet format decouples parsing from DB loading
- **Optimized for Speed** - 5-15x faster with 10 performance enhancements (see [docs/wiki/optimizations](docs/wiki/optimizations/))

## Requirements

- Python 3.10+
- Dependencies:
  ```
  pip install requests beautifulsoup4 playwright
  python -m playwright install chromium
  ```

## Installation

```bash
git clone https://github.com/wschosta/dod-budget-analysis.git
cd dod-budget-analysis
pip install -r requirements.txt
python -m playwright install chromium
```

## Usage

### Interactive Mode

```bash
python dod_budget_downloader.py
```

Prompts you to select fiscal years and data sources from numbered menus.

### Command-Line Mode

```bash
# Download FY2026 Comptroller documents (default source)
python dod_budget_downloader.py --years 2026

# Download FY2026 from all sources
python dod_budget_downloader.py --years 2026 --sources all

# Download FY2025-2026 Army and Navy documents
python dod_budget_downloader.py --years 2026 2025 --sources army navy

# Download everything available
python dod_budget_downloader.py --years all --sources all

# List files without downloading (dry run)
python dod_budget_downloader.py --years 2026 --sources all --list

# Download only PDFs, no GUI
python dod_budget_downloader.py --years 2026 --types pdf --no-gui

# Overwrite existing files
python dod_budget_downloader.py --years 2026 --overwrite
```

### CLI Arguments

| Argument | Description |
|---|---|
| `--years` | Fiscal years to download (e.g., `2026 2025`) or `all` |
| `--sources` | Sources: `comptroller`, `defense-wide`, `army`, `navy`, `navy-archive`, `airforce`, or `all` |
| `--output` | Output directory (default: `DoD_Budget_Documents`) |
| `--list` | List available files without downloading |
| `--types` | Filter by file type (e.g., `pdf xlsx`) |
| `--overwrite` | Re-download files even if they already exist |
| `--no-gui` | Disable GUI window, use terminal-only progress |
| `--refresh-cache` | Ignore cache and refresh discovery from source |
| `--delay` | Per-domain seconds between requests (default: 0.1) |
| `--extract-zips` | Extract ZIP archives after downloading them |
| `--no-dedup` | Disable cross-source file deduplication |
| `--retry-failures` | Re-download only previously failed files |
| `--since YYYY-MM-DD` | Skip files already downloaded on or after this date |
| `--workers N` | Number of concurrent HTTP download threads (default: 4) |

## Output Structure

```
DoD_Budget_Documents/
  FY2026/
    PB/
      Comptroller/
        summary/
          p1_display.xlsx
          r1_display.xlsx
        detail/
          p5_display.xlsx
          r2_display.xlsx
        other/
          ...
      US_Army/
        summary/
        detail/
        other/
      US_Navy/
        ...
  FY2025/
    ...
```

The full pipeline can be run with `python run_pipeline.py`.

## Web UI

The web interface at `http://localhost:8000` provides:

- **Search** — Full-text keyword search with filters for fiscal year, service, exhibit type, appropriation, and amount range
- **Results table** — Sortable, paginated results with column toggling and active filter chips
- **Detail view** — Full line-item detail with funding breakdown and related items across fiscal years
- **Charts** — Year-over-year trends, service comparisons, and top-N budget items
- **Dashboard** — Budget overview with interactive visualizations
- **Programs** — Browse and search by program element
- **Export** — Download filtered results as CSV, JSON (NDJSON), or Excel
- **Dark mode** — Toggle between light and dark themes

## Architecture

- **`requests` + `BeautifulSoup`** for sites with standard HTML (Comptroller, Defense Wide)
- **Playwright (Chromium)** for sites with WAF protection or SharePoint rendering (Army, Navy, Air Force). The browser runs with `headless=False` for WAF bypass but is positioned off-screen to remain invisible.
- **Three-strategy browser download**: API-level fetch with cookies, injected anchor element, and direct navigation as fallback
- **Navy archive caching**: The SharePoint archive page is loaded once and filtered in-memory for each fiscal year
- **Connection pooling** with 20 concurrent connections and automatic retry (3 attempts with exponential backoff)
- **Parallel discovery & download**: ThreadPoolExecutor for concurrent source discovery (4 workers) and direct file downloads (4 workers)
- **Background ZIP extraction**: Queue-based background thread for non-blocking ZIP extraction
- **Smart prefetching**: Batch HEAD requests (8 workers) for remote file sizes before download phase

See [docs/wiki/optimizations/START_HERE.md](docs/wiki/optimizations/START_HERE.md) for detailed optimization information.

## Project Roadmap

> **Objective:** Build a public, web-facing, user-queryable database of Department of Defense budget data that allows users to filter, explore, and download results.

| Phase | Title | Status | Description |
|-------|-------|--------|-------------|
| **0** | Project Description & Documentation | ✅ Complete | Updated readme, wiki skeleton, and project documentation |
| **1** | Data Extraction & Normalization | ✅ ~90% Complete | Download, parse, and normalize DoD budget documents into clean, structured data |
| **2** | Database Design & Population | ✅ Complete | Production schema, data loading, reconciliation, and full REST API |
| **3** | Front-End & Documentation | 📋 Planned | Build a web UI for querying, filtering, and downloading data, plus user-facing docs |
| **4** | Publish, Feedback & Iteration | 📋 Planned | Deploy publicly, collect user feedback, and iterate on improvements |

### Current Project Status

| Component | File(s) | Lines | Status |
|-----------|---------|-------|--------|
| **Document downloader** | `dod_budget_downloader.py` | 2,442 | ✅ Functional — 6 sources (incl. navy-archive), Playwright automation, parallel downloads, cross-source dedup |
| **Database builder (CLI)** | `build_budget_db.py` | 1,957 | ✅ Functional — Excel/PDF parsing, incremental updates |
| **Database builder (GUI)** | `build_budget_gui.py` | 497 | ✅ Functional — tkinter interface with progress/ETA |
| **Schema & migrations** | `schema_design.py` | 482 | ✅ Complete — versioned migrations, reference table seeding |
| **Exhibit catalog** | `exhibit_catalog.py` | 429 | ✅ Complete — 9 exhibit types (P-1, P-5, R-1, R-2, O-1, M-1, C-1, P-1R, RF-1) |
| **Validation suite** | `validate_budget_db.py` + `utils/validation.py` | 777 | ✅ Complete — 10+ checks, ValidationRegistry framework |
| **Data reconciliation** | `scripts/reconcile_budget_data.py` | 481 | ✅ Complete — cross-service + cross-exhibit reconciliation |
| **Search interface** | `search_budget.py` | 582 | ✅ Functional — FTS5 full-text search, results display, export |
| **REST API** | `api/` (6 route modules, 11 Pydantic models) | 1,239 | ✅ Complete — FastAPI with search, budget-lines, aggregations, download, reference |
| **Utility libraries** | `utils/` (16 modules) | 2,093 | ✅ Complete — config, database, HTTP, patterns, strings, validation, formatting, cache, and more |
| **Test suite** | `tests/` (82 test files) | — | ✅ Tests passing |
| **Performance optimizations** | `docs/wiki/optimizations/` | — | ✅ Complete — 5-15x speedup with 13 optimizations |

### Remaining TODOs (20 items)

All remaining items require external resources not available in development:

| Category | Count | Blocker |
|----------|-------|---------|
| Data Source Auditing (1.A) | 6 | Network access to DoD websites |
| Exhibit Inventory (1.B) | 1 | Downloaded document corpus |
| Frontend Accessibility (3.A) | 1 | Frontend implementation (Phase 3) |
| Deployment & Launch (4.x) | 4 | Cloud accounts, domain registration |
| Documentation Verification | 8 | Depends on source coverage audit |
| **Total** | **20** | |

See [REMAINING_TODOS.md](docs/REMAINING_TODOS.md) for detailed descriptions and [ROADMAP.md](docs/ROADMAP.md) for the full task breakdown (57 steps).

## REST API

All data endpoints are under `/api/v1`. Interactive docs at `/docs` (Swagger) and `/redoc`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/search` | GET | Full-text search (FTS5 + BM25 ranking) |
| `/api/v1/budget-lines` | GET | Filtered, paginated budget line items |
| `/api/v1/budget-lines/{id}` | GET | Single budget line item detail |
| `/api/v1/aggregations` | GET | GROUP BY summaries for charts/dashboards |
| `/api/v1/download` | GET | Streaming CSV/NDJSON export |
| `/api/v1/reference/{type}` | GET | Reference data (services, exhibit types, fiscal years) |
| `/api/v1/metadata` | GET | Database and dataset metadata |
| `/api/v1/feedback` | POST | User feedback submission |
| `/health` | GET | Health check (DB connectivity) |
| `/health/detailed` | GET | Detailed metrics (uptime, counters, query stats) |

Amounts are in **thousands of dollars ($K)** unless `amount_unit` says otherwise.

## CLI Tools

```bash
# Download budget documents
python dod_budget_downloader.py --years 2026 --sources all

# Build the SQLite database
python build_budget_db.py

# Search from the command line
python search_budget.py "F-35"
python search_budget.py --org Navy --exhibit r1 --year 2026 "submarine"

# Validate data quality
python validate_budget_db.py --verbose

# Full pipeline (download + build + validate + enrich)
python run_pipeline.py

# Refresh data (download + rebuild + validate)
python refresh_data.py --years 2026

# GUI database builder
python build_budget_gui.py
```

## Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test modules
python -m pytest tests/test_pipeline_group/test_parsing.py
python -m pytest tests/test_web_group/test_api_models.py

# Run with coverage (80% minimum on api/ and utils/)
python -m pytest tests/ --cov=api --cov=utils --cov-report=term-missing --cov-fail-under=80

# Lint and type check
ruff check . --select=E,W,F --ignore=E501 --exclude=DoD_Budget_Documents
mypy api/ utils/ --ignore-missing-imports
```

## Project Status

| Phase | Status | Description |
|-------|--------|-------------|
| **0** Documentation | Complete | Project docs, roadmap, wiki |
| **1** Data Extraction | ~90% Complete | Download, parse, normalize (remaining items need network access) |
| **2** Database & API | Complete | Schema, data loading, REST API, reconciliation |
| **3** Frontend & Docs | Complete | Web UI, charts, dashboard, user documentation |
| **4** Deploy & Launch | ~50% Complete | Docker, CI/CD, monitoring (remaining: hosting, domain, public launch) |

| Component | Status |
|-----------|--------|
| Document downloader | 5 sources, Playwright automation, parallel downloads |
| Database builder | Excel/PDF parsing, incremental updates, dynamic FY columns |
| Schema & migrations | Versioned migrations, reference table seeding |
| Validation suite | 10+ checks, cross-service/exhibit reconciliation |
| REST API | 10 route modules, Pydantic models, rate limiting, connection pooling |
| Web UI | Search, filters, results, detail, charts, dashboard, dark mode |
| Test suite | 75 test files, 80% coverage threshold |
| CI/CD | GitHub Actions: lint, type check, test matrix, Docker build |
| Docker | Production, multi-stage, dev, and staging configurations |

## Documentation

| Document | Description |
|----------|-------------|
| [User Guide](docs/user-guide/) | Getting started, data sources, exhibit types, data dictionary, FAQ |
| [Developer Guide](docs/developer/) | Architecture, API reference, testing, deployment, utilities |
| [Architecture Decisions](docs/decisions/) | ADRs for FastAPI, HTMX+Jinja2, FTS5 |
| [Roadmap](docs/ROADMAP.md) | Full project roadmap with 57 tasks across 4 phases |
| [Contributing](CONTRIBUTING.md) | Development setup, code standards, PR process |

## License

This tool downloads publicly available U.S. government budget documents. All downloaded content is public domain.
