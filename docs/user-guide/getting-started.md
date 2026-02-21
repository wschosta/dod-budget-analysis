# Getting Started

A guide to downloading, building, browsing, searching, and exporting DoD budget data.

---

## What This Tool Does

The DoD Budget Analysis tool downloads, parses, and indexes Department of Defense budget
justification documents into a searchable SQLite database. It lets analysts, researchers,
journalists, and policy-watchers query structured budget data — dollar amounts, program
elements, organizations, and exhibit types — alongside full-text search of the underlying
PDF documents.

**Key capabilities:**
- Download budget spreadsheets and PDFs from official DoD sources (Comptroller, Army, Navy,
  Air Force, Space Force)
- Parse Excel exhibits (P-1, R-1, O-1, M-1, C-1, RF-1, P-1R, P-5, R-2, R-3, R-4) into a
  structured SQLite database with FTS5 full-text search
- Extract text and table data from budget-justification PDFs
- Browse and search via a web interface with charts and dashboards
- Search by keyword, organization, fiscal year, exhibit type, or a combination
- Export search results to CSV or JSON
- Validate data quality after ingestion

---

## What Data Is Included

| Dimension | Details |
|-----------|---------|
| **Services** | Army, Navy, Marine Corps, Air Force, Space Force, Defense-Wide, Joint Staff |
| **Fiscal Years** | FY2024--FY2026 (downloaded); historical years available on source sites |
| **Exhibit Types** | P-1, P-1R, P-5, R-1, R-2, R-3, R-4, O-1, M-1, C-1, RF-1 |
| **Formats** | Excel (.xlsx) -> `budget_lines` table; PDF -> `pdf_pages` table |
| **Dollar Unit** | Thousands of dollars (as published in source documents) |
| **Classification** | Unclassified only -- classified programs are excluded from public documents |

> See [Exhibit Types](exhibit-types.md) and [Data Sources](data-sources.md) for complete details.

---

## Prerequisites

- **Python 3.10+** (Python 3.11 or 3.12 recommended)
- Install Python dependencies:
  ```bash
  pip install -r requirements.txt
  ```
- For browser-based downloads (Army, Navy, Air Force sites use WAF protection):
  ```bash
  playwright install chromium
  ```
- Disk space: ~2--5 GB for a full download of multiple fiscal years

### Optional: Development dependencies

For running tests and pre-commit checks:
```bash
pip install -r requirements-dev.txt
```

---

## Downloading Budget Documents

```bash
# Download the Comptroller summary documents for the latest fiscal year
python dod_budget_downloader.py

# Download a specific fiscal year, all sources
python dod_budget_downloader.py --years 2026 --sources all

# Download specific services for multiple years
python dod_budget_downloader.py --years 2025 2026 --sources army navy airforce

# Dry-run: list what would be downloaded without downloading
python dod_budget_downloader.py --years 2026 --sources all --list

# Run without the GUI progress window
python dod_budget_downloader.py --years 2026 --no-gui
```

Files are saved to `DoD_Budget_Documents/` organized by source and fiscal year.

### Available Sources

| Source Key | Description | Access Method |
|------------|-------------|---------------|
| `comptroller` | DoD Comptroller summary documents | Direct HTTP |
| `defense-wide` | Defense-Wide justification books | Direct HTTP |
| `army` | US Army budget materials | Browser (WAF-protected) |
| `navy` | US Navy / Marine Corps | Browser (WAF-protected) |
| `navy-archive` | Navy archive alternate source | Browser (WAF-protected) |
| `airforce` | Air Force / Space Force | Browser (WAF-protected) |

---

## Building the Database

```bash
# Build (or incrementally update) the database from downloaded documents
python build_budget_db.py

# Force a full rebuild (delete and recreate the database)
python build_budget_db.py --rebuild

# Resume an interrupted build from the last checkpoint
python build_budget_db.py --resume

# Use a custom database path
python build_budget_db.py --db /path/to/budget.sqlite

# Use the GUI progress window
python build_budget_gui.py
```

The builder:
1. Scans `DoD_Budget_Documents/` for `.xlsx` and `.pdf` files
2. Skips files already recorded in `ingested_files` (incremental mode)
3. Parses Excel exhibits into the `budget_lines` table
4. Extracts PDF text and table data into `pdf_pages`
5. Creates FTS5 full-text search indexes

---

## Web UI

The project includes a full web interface for browsing, searching, and visualizing budget data.

### Starting the server

```bash
# Start the API server in development mode
uvicorn api.app:app --reload --port 8000
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.

Alternatively, use Docker:

```bash
docker compose up --build
```

### Features

- **Full-text search** -- search budget line items and PDF documents by keyword with BM25 ranking
- **Filters** -- narrow results by service/organization, exhibit type, fiscal year, and budget activity
- **Results table** -- sortable, paginated table of matching budget line items
- **Detail view** -- click any row to see the full record with all fields and amounts
- **Charts** -- interactive Chart.js visualizations at `/charts`
- **Dashboard** -- summary dashboard with aggregations at `/dashboard`
- **Programs** -- browse all program elements at `/programs`, with per-program detail pages at `/programs/{pe_number}`
- **Dark mode** -- toggle between light and dark themes (preference is persisted)
- **CSV/JSON export** -- download filtered results as CSV or NDJSON via the `/api/v1/download` endpoint

For API documentation, visit `/docs` (OpenAPI/Swagger UI) or `/redoc` (ReDoc) while the server is running. See the [API Reference](../developer/api-reference.md) for full endpoint details.

---

## Searching the Database

```bash
# Basic keyword search
python search_budget.py "apache helicopter"

# Filter by organization
python search_budget.py --org Army "aircraft"

# Filter by exhibit type
python search_budget.py --exhibit p1 "aircraft"

# Combined filters
python search_budget.py --org Navy --exhibit r1 --year 2026 "submarine"

# Show top N results (default: 20)
python search_budget.py --top 50 "cyber"

# Search only Excel data or only PDF data
python search_budget.py --type excel "missile"
python search_budget.py --type pdf "budget justification"

# Interactive (REPL) mode
python search_budget.py --interactive

# Database summary (row counts, exhibit breakdown, top organizations)
python search_budget.py --summary
```

### Export Results

```bash
# Export to CSV
python search_budget.py "missile defense" --export csv

# Export to JSON
python search_budget.py "cyber" --export json --type excel

# Custom output file
python search_budget.py "space" --export csv --output space_results.csv
```

---

## Validating Data Quality

```bash
# Run all validation checks
python validate_budget_db.py

# Show details for each issue found
python validate_budget_db.py --verbose

# Exit non-zero on warnings (useful in CI)
python validate_budget_data.py --strict

# Output validation results as JSON
python validate_budget_data.py --json
```

The validator runs 7 automated checks:
1. **Missing fiscal years** -- services missing expected coverage years
2. **Duplicate rows** -- identical key tuples (possible parsing bug)
3. **Zero-amount line items** -- rows where all dollar columns are NULL/zero
4. **Column alignment** -- rows with account code but no organization
5. **Unknown exhibit types** -- exhibit codes not in the known set
6. **Ingestion errors** -- files that errored during parsing
7. **Empty files** -- files successfully ingested but producing zero rows

---

## Complete Data Refresh

```bash
# Download + build + validate in one step for FY2026
python refresh_data.py --years 2026

# Multiple years, specific sources
python refresh_data.py --years 2025 2026 --sources army navy

# Preview without executing
python refresh_data.py --dry-run --years 2026
```

---

## Tips and Tricks

### Search filters

- **Organization:** `--org Army` / `--org Navy` / `--org "Air Force"` (matches `organization_name` field).
- **Exhibit type:** `--exhibit p1`, `--exhibit r1`, `--exhibit o1` etc. (lowercase, without hyphen).
- **Fiscal year:** `--year 2026` narrows results to a specific fiscal year.
- **Source type:** `--type excel` searches budget lines only; `--type pdf` searches document text only.
- **Top N:** `--top 50` returns more results (default is 20).

### Combining filters

```bash
# All Navy R-1 (RDT&E) items mentioning cyber, FY2026
python search_budget.py --org Navy --exhibit r1 --year 2026 "cyber"

# Top 100 Army P-1 (procurement) results for aircraft
python search_budget.py --org Army --exhibit p1 --top 100 "aircraft"
```

### Finding program elements

Program element numbers follow the pattern `NNNNNNNX` (7 digits + 1 letter, e.g., `0602702E`).
Search by PE number to find all exhibits referencing a specific research program:

```bash
python search_budget.py "0602702E"
```

### Understanding dollar amounts

- All dollar amounts are stored in **thousands of dollars** as published in source documents.
- A value of `1000` means $1,000,000 (one million dollars).
- NULL in an amount column means the value was absent from the source document (not zero).

### Scheduled / automated downloads

For unattended cron/Task Scheduler runs:
```bash
python scripts/scheduled_download.py --output DoD_Budget_Documents --log downloads.log
```
