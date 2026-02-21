# Getting Started

A guide to setting up, searching, filtering, and downloading DoD budget data using
the command-line tools and web interface.

---

## What This Tool Does

DoD Budget Explorer is a searchable, publicly accessible database of Department of Defense
budget justification documents. It aggregates budget line items submitted by the military
services and defense agencies to Congress and makes them queryable through both a
command-line interface and a full web-based UI.

Every year, the President submits a budget request to Congress. The Department of Defense
publishes detailed supporting documents -- called budget justification exhibits -- that
explain exactly what they are asking to fund and why. These documents are public, but
they are spread across multiple military service websites, published in dozens of PDFs
and Excel spreadsheets, and use specialized terminology that can be difficult to navigate.

DoD Budget Explorer collects all of those documents, parses them into structured data,
and presents them in searchable interfaces with plain-language labels.

**Key capabilities:**
- Download budget spreadsheets and PDFs from official DoD sources (Comptroller, Army, Navy,
  Air Force, Space Force)
- Parse Excel exhibits (P-1, R-1, O-1, M-1, C-1, RF-1, P-1R, P-5, R-2, R-3, R-4) into a
  structured SQLite database with FTS5 full-text search
- Extract text and table data from budget-justification PDFs
- Browse and search via a web interface with interactive charts and dashboards
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

See [Exhibit Types](exhibit-types.md) and [Data Sources](data-sources.md) for complete details.

### Military Services and Agencies

The database includes budget data from the following components:

- **Department of the Army** -- includes Army-specific procurement, R&D, operations, and personnel budgets
- **Department of the Navy** -- covers both the Navy and Marine Corps budgets
- **Department of the Air Force** -- includes Air Force and, separately, Space Force budgets
- **Marine Corps** -- sometimes reported as a subset of Navy, sometimes standalone
- **Space Force** -- stood up as a separate service in December 2019; data available from FY2021 onward
- **Defense-Wide** -- covers defense agencies, joint programs, and activities that serve all services (e.g., DARPA, DIA, MDA)

### Exhibit Types

DoD budget justification documents are organized into standardized "exhibit" types.
Each exhibit type covers a different appropriation category:

| Exhibit | Appropriation Category | What It Covers |
|---------|------------------------|----------------|
| **P-1** | Procurement (summary) | Top-level procurement line items by account |
| **P-5** | Procurement (detail) | Cost and quantity breakdowns for procurement programs |
| **R-1** | RDT&E (summary) | Research, Development, Test & Evaluation summary |
| **R-2** | RDT&E (detail) | Program-level descriptions and justifications for R&D |
| **O-1** | Operation & Maintenance | Operating costs, readiness, training |
| **M-1** | Military Personnel | Pay, allowances, and end-strength |
| **C-1** | Construction | Military construction projects |
| **RF-1** | Revolving Fund | Working capital and revolving fund accounts |

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

## Using the Web UI

The project includes a full web interface for browsing, searching, and visualizing
budget data.

### Starting the Server

```bash
# Start the API server in development mode
uvicorn api.app:app --reload --port 8000
```

Then open [http://localhost:8000](http://localhost:8000) in your browser.

Alternatively, use Docker:

```bash
docker compose up --build
```

### Search Page (/)

The main search page provides full-text search across all budget line items and parsed
document text. You can search for:

- **Program names** -- for example, `F-35`, `Stryker`, `HIMARS`, `Littoral Combat Ship`
- **Topics** -- for example, `cybersecurity`, `artificial intelligence`, `hypersonics`
- **Appropriation accounts** -- for example, `Aircraft Procurement`, `Missile Procurement`
- **Program Element numbers** -- for example, `0604229F` (see the [FAQ](faq.md) for an
  explanation of PE numbers)
- **Contractor names or technologies** -- if mentioned in the document text

Search results are ranked by relevance. Each result shows the program name, service,
fiscal year, appropriation account, and the dollar amount requested.

**Tips for better searches:**

- Use specific terms rather than broad ones -- `M109 howitzer` will return more targeted
  results than just `artillery`
- If your search returns no results, try removing qualifiers or checking for alternate
  spellings (e.g., `F-15EX` vs. `F15EX`)
- PE numbers are exact -- search the full number including the trailing letter if known

### Filter Sidebar

After running a search (or viewing all results), the filter sidebar lets you narrow
results without re-typing a query. Available filters include:

- **Fiscal Year** -- Check one or more fiscal years to limit results to those budget cycles.
  Useful for comparing the same program across multiple years.
- **Service** -- Check one or more services to see only their budget requests. For example,
  checking only "Air Force" and "Space Force" will hide Army, Navy, and Defense-Wide entries.
- **Exhibit Type** -- Filter to a specific exhibit type. For example, selecting only `R-2`
  will show program-level research and development justifications and hide procurement line items.
- **Amount Range** -- Enter a minimum and/or maximum dollar amount (in thousands of dollars --
  see the section below on reading amounts). For example, entering `1000000` as a minimum will
  show only programs requesting $1 billion or more.

After setting filters, click **Apply Filters**. To reset, click **Clear All**.

### Charts Page (/charts)

Interactive Chart.js visualizations of budget data. View spending breakdowns by service,
appropriation type, exhibit category, and fiscal year trends.

### Dashboard (/dashboard)

Overview dashboard with summary statistics, top programs, and key budget metrics displayed
through interactive charts and tables.

### Programs Page (/programs)

Browse and search program elements. Click any program to view its detail page with
funding history, related exhibits, and narrative descriptions.

### Dark Mode

Toggle between light and dark themes using the theme switch in the navigation bar.
Your preference is persisted in local storage.

### Downloading from the Web UI

You can download the results of any search or filter in two formats:

- **CSV** -- compatible with Excel, Google Sheets, and any data analysis tool
- **JSON** -- structured data suitable for pipelines, scripts, or further processing

To download:

1. Run a search or apply filters to the results you want.
2. Click the **Download Results** button below the results table.
3. Select your preferred format (CSV or JSON).
4. The file will download immediately with your current filters applied.

The downloaded file includes all fields visible in the table plus additional metadata
fields (such as source file name and appropriation code) that are not shown by default
in the interface.

There is no row limit on downloads, but very large result sets (tens of thousands of
rows) may take a moment to generate.

### API Documentation

For programmatic access, visit `/docs` (OpenAPI/Swagger UI) or `/redoc` (ReDoc) while
the server is running. See the [API Reference](../developer/api-reference.md) for full
endpoint details.

---

## Searching via the CLI

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

### Export Results (CLI)

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

## How to Read the Data

### Dollar Amounts Are in Thousands

**All dollar amounts in this database are in thousands of dollars ($K).** This is the
standard used in DoD budget documents themselves and is preserved here to match source
data exactly.

To convert to familiar dollar figures:

| What you see | Actual amount |
|---|---|
| `1,000` | $1 million |
| `10,000` | $10 million |
| `100,000` | $100 million |
| `1,000,000` | $1 billion |
| `10,000,000` | $10 billion |

**Example:** A line item showing `amount_thousands: 450,000` means a request for
$450 million -- not $450 thousand.

### PB = President's Budget

**PB** stands for President's Budget. This is the formal budget request that the
President submits to Congress, typically in early February each year. The figures
labeled as PB or "budget estimate" reflect what the executive branch asked for.

Congress then reviews the request, holds hearings, and passes its own funding levels,
which may differ significantly from the request.

### Enacted vs. Request Amounts

Many line items include multiple dollar columns:

- **Request (or Budget Estimate):** The amount the President asked Congress to appropriate.
  This is what you see in the PB documents.
- **Enacted (or Appropriated):** The amount Congress actually approved, as signed into law.
  This may be higher or lower than the request, or may reflect a continuing resolution.
- **Prior Year Enacted:** The enacted amount from the previous fiscal year, shown for
  comparison purposes.

When the database shows only one amount column, it is generally the President's Budget
request figure from the source exhibit.

### Continuing Resolutions (CR)

If Congress does not pass a full appropriations bill before the start of the fiscal year
(October 1), the government operates under a **Continuing Resolution (CR)**. CR funding
is typically set at the prior year's enacted level (sometimes with a slight reduction)
and does not reflect the new year's President's Budget request. Some line items in the
database may note CR amounts separately.

### A Note on Totals

Service and program totals in this database are computed from the parsed line items
and may not match officially published totals exactly. Rounding, coverage gaps, and
parsing limitations can cause small discrepancies. See the [Methodology](methodology.md)
and [FAQ](faq.md) for more detail.

---

## Tips and Tricks

### Search filters (CLI)

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

---

## Getting Help

If you encounter data that looks wrong, a program that appears to be missing, or an
amount that does not match a source document, please report it. See the
[FAQ](faq.md) for instructions on how to report errors.

For technical details on the REST API, see the [API Reference](../developer/api-reference.md).
For database schema details, see the [Database Schema](../developer/database-schema.md).
To contribute to the project, see [Contributing](../../CONTRIBUTING.md).
