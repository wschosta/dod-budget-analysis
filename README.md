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
