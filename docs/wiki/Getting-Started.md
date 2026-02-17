# Getting Started

<!-- TODO [Step 3.C1]: Write a full plain-language guide after the web UI is built. -->

A guide to searching, filtering, and downloading DoD budget data.

---

## What This Tool Does

<!-- Brief explanation of the tool's purpose and target audience:
     analysts, researchers, journalists, and anyone interested in DoD budgets. -->

## What Data Is Included

<!-- List of services covered, fiscal year range, exhibit types, and data
     volume (row counts, file counts). Reference the Data Sources page. -->

## Prerequisites

<!-- System requirements: Python 3.10+, dependencies via requirements.txt,
     Playwright for browser-based downloads. -->

## Downloading Budget Documents

```bash
# Download all available documents
python dod_budget_downloader.py

# Download specific sources and fiscal years
python dod_budget_downloader.py --sources army navy --years 2025 2026
```

## Building the Database

```bash
# Parse downloaded documents into SQLite
python build_budget_db.py
```

## Searching the Database

```bash
# Search for a topic
python search_budget.py "apache helicopter"

# Filter by organization and exhibit type
python search_budget.py --org Army --exhibit p1 "aircraft"

# Interactive mode
python search_budget.py --interactive

# Show database summary
python search_budget.py --summary
```

## Validating Data Quality

```bash
python validate_budget_db.py --verbose
```

## Tips and Tricks

<!-- Power-user tips: prefix searches (excel:, pdf:, org:), top-N queries,
     combining filters, exporting results. -->
