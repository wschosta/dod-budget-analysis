# DoD Budget Document Downloader

A Python tool that bulk-downloads public budget justification documents from the Department of Defense Comptroller website and individual military service budget pages. Supports interactive and fully automated operation with a real-time GUI progress window.

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

| Phase | Title | Description |
|-------|-------|-------------|
| **0** | Project Description & Documentation | Updated readme, wiki skeleton, and project documentation |
| **1** | Data Extraction & Normalization | Download, parse, and normalize DoD budget documents into clean, structured data |
| **2** | Database Design & Population | Design the production schema, load all data, and expose it through an API |
| **3** | Front-End & Documentation | Build a web UI for querying, filtering, and downloading data, plus user-facing docs |
| **4** | Publish, Feedback & Iteration | Deploy publicly, collect user feedback, and iterate on improvements |

### Current Project Status

| Component | File | Covers |
|-----------|------|--------|
| Document downloader | `dod_budget_downloader.py` | Steps 1.A1-1.A4 (partial) |
| Database builder (CLI) | `build_budget_db.py` | Steps 1.B1-1.B5 (partial), 2.B1 (partial) |
| Database builder (GUI) | `build_budget_gui.py` | GUI wrapper for the above |
| Search interface | `search_budget.py` | Prototype for 2.C query logic |

See [ROADMAP.md](ROADMAP.md) for the full task breakdown (57 steps), and [docs/TASK_INDEX.md](docs/TASK_INDEX.md) for Phase 0-1 implementation details.

## License

This tool downloads publicly available U.S. government budget documents. All downloaded content is public domain.
