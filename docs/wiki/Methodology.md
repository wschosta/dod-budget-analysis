# Methodology & Limitations

How data is collected, parsed, and loaded into the DoD Budget Analysis database.

> **Current Status:** Phase 3.C, Step 3.C6 — Partial. Core methodology is implemented and documented in code;
> expanded documentation and limitations to be finalized after Phase 1 hardening is complete.

---

## Data Collection Process

<!-- Describe the download pipeline:
     1. Discover links on service budget pages (HTTP or Playwright browser)
     2. Download Excel (.xlsx) and PDF (.pdf) files
     3. Organize by source and fiscal year in DoD_Budget_Documents/
     4. Log failures for retry -->

## Parsing Approach

<!-- Describe the parsing pipeline:
     - Excel files: openpyxl → column detection → exhibit type identification
       → row-by-row extraction into budget_lines table
     - PDF files: pdfplumber → page text extraction → table detection
       → pdf_pages table
     - Column mapping: _map_columns() matches header text to canonical fields
     - Organization detection: ORG_MAP lookup from account codes -->

## Data Validation

The `validate_budget_db.py` suite runs 7 automated checks:

1. **Missing fiscal years** — flags services missing expected FYs
2. **Duplicate rows** — finds identical key tuples
3. **Zero-amount line items** — finds rows where all dollar columns are NULL/zero
4. **Column alignment** — finds rows with account but no organization
5. **Unknown exhibit types** — finds types not in the known set
6. **Ingestion errors** — finds files that errored during parsing
7. **Empty files** — finds ingested files that produced zero rows

## Known Limitations

<!-- Document known issues:
     - PDF table extraction accuracy varies by layout
     - Some exhibit types have inconsistent column layouts across fiscal years
     - WAF protections on government sites may block downloads
     - Historical fiscal years may have different column structures
     - Classified programs are excluded from public budget documents -->

## How to Report Errors

<!-- Instructions for reporting data quality issues:
     - Run validate_budget_db.py first
     - Open a GitHub Issue with the [Data Quality] label
     - Include the source file, exhibit type, and expected vs actual values -->
