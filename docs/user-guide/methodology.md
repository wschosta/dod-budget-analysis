# Methodology & Limitations

How data is collected, parsed, and loaded into the DoD Budget Analysis database.

---

## DoD Budget Structure

Understanding the DoD budget document hierarchy is essential for interpreting the data
in this database. The structure below follows the conventions established by the Office
of the Under Secretary of Defense (Comptroller).

### Budget Hierarchy

The DoD budget is organized in a strict hierarchy:

```
Appropriation Account  (e.g., RDT&E, Procurement, O&M)
  └── Budget Activity  (e.g., 6.1 Basic Research, 6.2 Applied Research)
       └── Program Element (PE)  (e.g., 0602702F — Air Force applied research)
            └── Project  (e.g., Project 1234 — Specific sub-effort within a PE)
```

Each level corresponds to a different document exhibit family and level of detail.

### Program Elements (PEs)

A **Program Element** is the fundamental building block of DoD budget justification.
There are **over 3,600 individual PEs** across the department, spanning the five-year
Future Years Defense Program (FYDP) horizon.

**PE number format:** Seven digits plus an alphabetical service suffix:

| Position | Meaning | Example |
|----------|---------|---------|
| Digits 1--2 | Major Force Program (MFP) | `06` = RDT&E |
| Digits 3--5 | Program identifier | `027` = specific program |
| Digits 6--7 | Sub-classification | `02` |
| Letter suffix | Service | A=Army, N=Navy, F=Air Force, M=Marines |

Example: `0602702F` → MFP 06 (R&D), program 027, sub-class 02, Air Force.

Some PEs have multi-character suffixes for defense agencies (e.g., `BR` for DARPA,
`BB` for NSA, `BQ` for Special Operations Command, `LC` for intelligence community).

### Appropriation Categories ("Color of Money")

Each appropriation has a distinct availability period that constrains how and when
funds can be obligated:

| Category | Availability | Typical Exhibits |
|----------|-------------|-----------------|
| RDT&E | 2 years | R-1, R-2, R-3, R-4 |
| Procurement | 3 years | P-1, P-5, P-21, P-40 |
| Operation & Maintenance | 1 year | O-1 |
| Military Personnel | 1 year | M-1 |
| Military Construction | 5 years | C-1 |

The $350K expense/investment threshold drives decisions about which appropriation
category a program falls under, which in turn determines which exhibit documents
contain its budget data.

### Cross-Document Tracking

Approximately one-third of RDT&E funding appears under PEs not identified as R&D
in their coding. As programs mature from research (R-docs) to production (P-docs),
they may appear in different exhibit families. This means a single PE's full budget
picture often requires cross-referencing R-series and P-series documents.

This cross-document nature is why the enrichment pipeline's lineage detection
(Phase 4) scans PDF narratives for PE cross-references — programs frequently cite
related PEs in their justification text.

### FYDP Organization

The Future Years Defense Program structures budget data across three dimensions:

1. **Organizations** — Military departments (Army, Navy, Air Force) and defense agencies
2. **Appropriations** — RDT&E, O&M, Procurement, MilPers, MilCon
3. **Major Force Programs (MFPs)** — 11 categories (strategic forces, general purpose
   forces, mobility forces, R&D, etc.)

This three-dimensional structure enables "crosswalk" analysis between internal DoD
accounting (MFP view) and Congressional appropriations (exhibit view).

---

## Data Collection Process

The download pipeline (`dod_budget_downloader.py`) follows these steps:

1. **Discover fiscal years** -- scrape the DoD Comptroller budget materials index page to
   find all available fiscal year links
2. **Discover files per source** -- for each selected source and fiscal year, crawl the
   relevant page and extract links to downloadable files (`.xlsx`, `.pdf`, `.zip`, `.xls`,
   `.csv`)
3. **Check existing files** -- compare remote file sizes against local files; skip if
   already current (avoids re-downloading unchanged documents)
4. **Download** -- fetch new or changed files; browser-based downloads use Playwright for
   WAF-protected sites
5. **Log and manifest** -- record download status and generate a `manifest.json` for
   provenance tracking

Files are organized under `DoD_Budget_Documents/` by source name and fiscal year:

```
DoD_Budget_Documents/
  comptroller/FY2026/
  defense-wide/FY2026/
  army/FY2026/
  navy/FY2026/
  airforce/FY2026/
```

### Access methods by source

| Source | Method | Reason |
|--------|--------|--------|
| Comptroller | Direct HTTP (`requests`) | Publicly accessible, no WAF |
| Defense-Wide | Direct HTTP (`requests`) | Publicly accessible, no WAF |
| Army (asafm.army.mil) | Playwright headless browser | WAF blocks plain HTTP |
| Navy (secnav.navy.mil) | Playwright headless browser | WAF blocks plain HTTP |
| Air Force (saffm.hq.af.mil) | Playwright headless browser | WAF blocks plain HTTP |

---

## Parsing Approach

The database builder (`build_budget_db.py`) processes two file types differently:

### Excel Files (`.xlsx`)

1. **Open workbook** with `openpyxl` in read-only mode for memory efficiency
2. **Detect exhibit type** from the filename using `_detect_exhibit_type()` -- maps filename
   patterns (e.g., `p1`, `r1_display`, `m1`) to exhibit type codes
3. **Find header row** -- scan the first 15 rows of each sheet; a row containing "Account"
   or similar known column headers is the header row
4. **Map columns** with `_map_columns()` -- fuzzy match header text against ~40 canonical
   column name patterns to produce a `{field_name: column_index}` mapping; unknown columns
   are stored in the `extra_fields` JSON blob
5. **Extract data rows** -- iterate rows below the header; skip blank/subtotal rows; convert
   currency cells with `safe_float()` (handles commas, dollar signs, None)
6. **Detect organization** -- map the `organization` column value (A, N, F, S, D, M, J)
   to a full organization name via `ORG_MAP`
7. **Extract PE numbers** -- extract Program Element numbers from line_item and account
   fields using the regex `\d{7}[A-Z]{1,2}`
8. **Batch insert** into `budget_lines` -- rows are buffered and inserted in batches of
   1000 for performance
9. **Update FTS5 index** -- triggers automatically sync `budget_lines_fts` after each insert

### PDF Files (`.pdf`)

1. **Open** with `pdfplumber`
2. **Per-page extraction** -- for each page, extract raw text via `page.extract_text()`
3. **Table detection** -- attempt `page.extract_tables()` to identify structured tables;
   pages with tables set `has_tables=1` and store extracted table JSON in `table_data`
4. **Timeout protection** -- table extraction runs with a 10-second timeout to prevent
   hanging on complex layouts
5. **Insert** one row per page into `pdf_pages`; FTS5 trigger syncs `pdf_pages_fts`

---

## Incremental Updates

The builder tracks ingested files in the `ingested_files` table, storing:
- File path (relative to docs directory)
- File size and modification time at ingestion time
- Row count and ingestion timestamp
- Status (`ok` or error description)

On subsequent runs, a file is re-ingested only if its size or modification time has changed.
This allows partial updates without a full rebuild.

### Checkpointing

Long builds (especially large PDF corpora) support checkpointing:
- A session ID is created at build start
- Every N files (default: 10), a checkpoint is saved in the `build_sessions` table
- If interrupted (Ctrl+C or explicit stop in the GUI), the checkpoint is preserved
- `--resume` continues from the last checkpoint, skipping already-processed files in the
  interrupted session

---

## Column Mapping Details

The `_map_columns()` function attempts to match worksheet headers to canonical field names.
The matching priority is:

1. **Exact match** (case-insensitive) on known header strings
2. **Partial match** -- the header contains a known keyword
3. **Positional fallback** for well-known exhibit types with stable layouts

Canonical fields and their common header variations:

| Canonical Field | Common Header Variations |
|-----------------|--------------------------|
| `account` | "Account", "ACC", "Acct" |
| `account_title` | "Title", "Account Title", "Description" |
| `organization` | "Org", "Component", "Service" |
| `budget_activity` | "BA", "Bud Act", "Budget Activity" |
| `line_item` | "LI", "Line Item", "Item" |
| `amount_fy2026_request` | "FY 2026", "Budget Estimate", "Request" |
| `amount_fy2025_enacted` | "FY 2025", "Current Year", "Enacted" |
| `amount_fy2024_actual` | "FY 2024", "Prior Year", "Actual" |

---

## Data Validation

The validation suite (`validate_budget_db.py` and `validate_budget_data.py`) runs
7 automated checks after each build:

| Check | Description | Severity |
|-------|-------------|----------|
| Missing fiscal years | Services missing expected FY coverage | Warning |
| Duplicate rows | Identical key tuples (source, exhibit, account, line_item, FY) | Error |
| Zero-amount line items | Rows where all dollar columns are NULL or zero | Warning |
| Column alignment | Rows with account code but no organization | Warning |
| Unknown exhibit types | Exhibit codes not in the known set | Info |
| Ingestion errors | Files that errored during parsing | Error |
| Empty files | Files ingested but producing zero rows | Warning |

---

## Known Limitations

**PDF table extraction accuracy**
PDF layouts vary significantly across services, years, and document types. pdfplumber
extracts text reliably for text-layer PDFs but struggles with complex multi-column layouts,
overlapping elements, and rotated text. Scanned PDFs with no text layer produce no output.

**Exhibit type column variation**
Column headers for the same exhibit type (e.g., P-1) vary across services and occasionally
across fiscal years. The column mapper handles common variations but may miss new patterns
when DoD updates document templates. Unknown columns are captured in `extra_fields` for
manual review.

**Historical fiscal year URL changes**
DoD service websites occasionally reorganize their URL structures for older fiscal years.
The downloader's URL templates are calibrated for recent fiscal years (FY2023+). Older
years may require URL pattern updates.

**WAF rate limiting**
Browser-based downloads use Playwright but may still be rate-limited or blocked by WAF
policies if too many requests are made too quickly. The downloader includes a configurable
delay between file downloads.

**Monetary unit consistency**
Most DoD exhibits denominate amounts in thousands of dollars, but a small number use
whole dollars or millions. The parser assumes thousands by default. If a particular
exhibit uses a different unit, values will be misinterpreted.

**Currency year**
The database does not yet distinguish between then-year dollars and constant dollars.
All amounts are stored as-is from source documents.

**PE index coverage gap**
The `pe_index` enrichment table currently indexes only PEs found in `budget_lines`
(Excel-parsed data), which captures ~1,600 PEs. However, over 3,600 PEs exist across
the DoD, and ~3,400 distinct PEs are mentioned in PDF narratives (`pdf_pe_numbers`).
This means approximately 1,800 PEs that appear in PDF justification text but lack
corresponding Excel line items are not indexed and therefore receive no tags, lineage
detection, or program detail pages. These are typically cross-referenced programs,
defense agency PEs with multi-character suffixes (e.g., `BR` for DARPA, `BB` for NSA),
or programs from exhibit types not yet parsed (P-21, P-40, R-2a).

---

## How to Report Data Errors

1. Run `python validate_budget_db.py --verbose` to confirm the issue is detected
2. Note the source file, exhibit type, and specific row or field affected
3. Open a GitHub Issue with the `[Data Quality]` label
4. Include: source file path, exhibit type, fiscal year, expected vs actual value,
   and the output of `validate_budget_db.py --verbose` for that file if possible
