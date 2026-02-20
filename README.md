# DoD Budget Analysis

A comprehensive Python toolkit for downloading, parsing, normalizing, and querying Department of Defense budget justification documents. Includes a bulk document downloader, Excel/PDF parser, SQLite database with full-text search, a FastAPI REST API, and a validation/reconciliation framework.

## Data Sources

| Source | Website | Method |
|---|---|---|
| **Comptroller** | [comptroller.war.gov](https://comptroller.war.gov/Budget-Materials/) | Direct HTTP |
| **Defense Wide** | [comptroller.war.gov](https://comptroller.war.gov/Budget-Materials/) | Direct HTTP |
| **US Army** | [asafm.army.mil](https://www.asafm.army.mil/Budget-Materials/) | Playwright (WAF) |
| **US Navy** | [secnav.navy.mil](https://www.secnav.navy.mil/fmc/fmb/Pages/archive.aspx) | Playwright (SharePoint) |
| **US Air Force** | [saffm.hq.af.mil](https://www.saffm.hq.af.mil) | Playwright (WAF) |

The tool downloads PDFs, Excel spreadsheets (`.xlsx`, `.xls`), ZIP archives, and CSV files.

## Features

- **Multi-source discovery** across five DoD budget data sources
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
- **⚡ Optimized for Speed** - 5-15x faster with 10 performance enhancements (see [docs/wiki/optimizations](docs/wiki/optimizations/))

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
| `--sources` | Sources: `comptroller`, `defense-wide`, `army`, `navy`, `airforce`, or `all` |
| `--output` | Output directory (default: `DoD_Budget_Documents`) |
| `--list` | List available files without downloading |
| `--types` | Filter by file type (e.g., `pdf xlsx`) |
| `--overwrite` | Re-download files even if they already exist |
| `--no-gui` | Disable GUI window, use terminal-only progress |
| `--refresh-cache` | Ignore cache and refresh discovery from source |
| `--delay` | Seconds to wait between requests (default: 0.5) |
| `--extract-zips` | Extract ZIP archives after downloading them |

## Output Structure

```
DoD_Budget_Documents/
  FY2026/
    Comptroller/
      FY2026_Budget_Overview.pdf
      ...
    Defense_Wide/
      ...
    US_Army/
      ...
    US_Navy/
      ...
    US_Air_Force/
      ...
  FY2025/
    ...
```

## Performance

This tool is optimized for speed with 10 performance enhancements:

| Use Case | Speedup | Key Optimizations |
|----------|---------|-------------------|
| **Fresh Discovery** | 1.3x | lxml parser, connection pooling |
| **Cached Discovery** | 10-20x | Metadata caching (24h TTL) |
| **Download Retry** | 2-3x | Partial resume, adaptive chunking |
| **Overall** | **5-15x** | Cumulative effect of all optimizations |

**Example**: First run discovers sources, second run reuses cache for 10-20x speedup.

See [docs/wiki/optimizations/START_HERE.md](docs/wiki/optimizations/START_HERE.md) for detailed optimization information.

## Architecture

- **`requests` + `BeautifulSoup`** for sites with standard HTML (Comptroller, Defense Wide)
- **Playwright (Chromium)** for sites with WAF protection or SharePoint rendering (Army, Navy, Air Force). The browser runs with `headless=False` for WAF bypass but is positioned off-screen to remain invisible.
- **Three-strategy browser download**: API-level fetch with cookies, injected anchor element, and direct navigation as fallback
- **Navy archive caching**: The SharePoint archive page is loaded once and filtered in-memory for each fiscal year
- **Connection pooling** with 20 concurrent connections and automatic retry (3 attempts with exponential backoff)
- **Parallel discovery & download**: ThreadPoolExecutor for concurrent source discovery (4 workers) and direct file downloads (4 workers)
- **Background ZIP extraction**: Queue-based background thread for non-blocking ZIP extraction
- **Smart prefetching**: Batch HEAD requests (8 workers) for remote file sizes before download phase

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
| **Document downloader** | `dod_budget_downloader.py` | 2,442 | ✅ Functional — 5 sources, Playwright automation, parallel downloads |
| **Database builder (CLI)** | `build_budget_db.py` | 1,957 | ✅ Functional — Excel/PDF parsing, incremental updates |
| **Database builder (GUI)** | `build_budget_gui.py` | 497 | ✅ Functional — tkinter interface with progress/ETA |
| **Schema & migrations** | `schema_design.py` | 482 | ✅ Complete — versioned migrations, reference table seeding |
| **Exhibit catalog** | `exhibit_catalog.py` | 429 | ✅ Complete — 9 exhibit types (P-1, P-5, R-1, R-2, O-1, M-1, C-1, P-1R, RF-1) |
| **Validation suite** | `validate_budget_db.py` + `utils/validation.py` | 777 | ✅ Complete — 10+ checks, ValidationRegistry framework |
| **Data reconciliation** | `scripts/reconcile_budget_data.py` | 481 | ✅ Complete — cross-service + cross-exhibit reconciliation |
| **Search interface** | `search_budget.py` | 582 | ✅ Functional — FTS5 full-text search, results display, export |
| **REST API** | `api/` (6 route modules, 11 Pydantic models) | 1,239 | ✅ Complete — FastAPI with search, budget-lines, aggregations, download, reference |
| **Utility libraries** | `utils/` (11 modules) | 2,093 | ✅ Complete — config, database, HTTP, patterns, strings, validation |
| **Test suite** | `tests/` (49 test files) | — | ✅ **1,183 tests** passing |
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

The project includes a full FastAPI REST API for programmatic access to budget data.

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/search` | GET | Full-text search across budget lines and PDF pages |
| `/api/v1/budget-lines` | GET | Filtered, paginated list of budget line items |
| `/api/v1/budget-lines/{id}` | GET | Single budget line item detail |
| `/api/v1/aggregations` | GET | Aggregated totals by service, fiscal year, etc. |
| `/api/v1/download` | GET | Streaming CSV/JSON export with same filters |
| `/api/v1/reference/{type}` | GET | Reference data (services, exhibit types, fiscal years) |
| `/health` | GET | Health check endpoint |

### Running the API

```bash
pip install fastapi uvicorn
uvicorn api.app:app --reload
```

API documentation is auto-generated at `/docs` (Swagger UI) and `/redoc` (ReDoc).

## Database Building

```bash
# Build the SQLite database from downloaded documents
python build_budget_db.py

# Or use the GUI interface
python build_budget_gui.py

# Search the database
python search_budget.py "F-35"

# Validate data quality
python validate_budget_db.py
```

## Testing

```bash
# Run all 1,183 tests
python -m pytest

# Run specific test modules
python -m pytest tests/test_parsing.py
python -m pytest tests/test_api_models.py

# Run with coverage
python -m pytest --cov=. --cov-report=term-missing
```

## License

This tool downloads publicly available U.S. government budget documents. All downloaded content is public domain.
