# Methodology & Limitations

How data is collected, parsed, and loaded into the DoD Budget Analysis database.
This document is intended to help users understand the provenance and quality of
the data, and to be transparent about the limitations of automated parsing.

---

## Data Sources

All data in this database originates from publicly available U.S. government budget
justification documents. The source sites are:

| Source | Website | Content |
|--------|---------|---------|
| **DoD Comptroller** | comptroller.defense.gov | Defense-Wide and consolidated budget exhibits |
| **Department of the Army** | asafm.army.mil | Army budget justification books |
| **Department of the Navy** | secnav.navy.mil | Navy and Marine Corps budget documents |
| **Department of the Air Force** | saffm.hq.af.mil | Air Force and Space Force budget documents |

These sites publish budget documents in a mix of formats: Excel spreadsheets (`.xlsx`,
`.xls`), PDF files, and occasionally ZIP archives containing multiple files.

All downloaded documents are public domain U.S. government records. No login, FOIA
request, or fee is required to access the originals.

See [Data Sources](data-sources.md) for the full catalog of source URLs, access methods,
and coverage matrix.

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

### Access Methods by Source

| Source | Method | Reason |
|--------|--------|--------|
| Comptroller | Direct HTTP (`requests`) | Publicly accessible, no WAF |
| Defense-Wide | Direct HTTP (`requests`) | Publicly accessible, no WAF |
| Army (asafm.army.mil) | Playwright browser | WAF blocks plain HTTP |
| Navy (secnav.navy.mil) | Playwright browser | WAF blocks plain HTTP |
| Air Force (saffm.hq.af.mil) | Playwright browser | WAF blocks plain HTTP |

The downloader skips files that have already been downloaded (checking by filename and
file size) to avoid redundant network requests on subsequent runs.

---

## Parsing Approach

The database builder (`build_budget_db.py`) processes two file types differently:

### Excel Files (openpyxl)

Excel budget exhibits are parsed using **openpyxl**, a Python library for reading
`.xlsx` files. The parser reads each sheet, identifies header rows, maps column names
to standardized field names, and extracts individual line items.

The detailed steps are:

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

Excel parsing is generally the most reliable method. Budget justification spreadsheets
follow relatively consistent column layouts within a given exhibit type and fiscal year.
Common issues include:

- **Merged cells:** Exhibit headers sometimes span multiple columns or rows with merged
  cells, which openpyxl handles by propagating the merged cell value.
- **Format changes across years:** Column positions and names have shifted in some years,
  requiring year-specific parsing logic for affected exhibit types.
- **Hidden rows or sheets:** Some spreadsheets include hidden summary rows or sheets
  that are not intended as line-item data. These are filtered during parsing.

### PDF Files (pdfplumber)

PDF budget documents are parsed using **pdfplumber**, a Python library that extracts
text and tables from PDF files. PDF parsing is inherently less reliable than Excel
parsing and is used when a given document is only available in PDF format.

1. **Open** with `pdfplumber`
2. **Per-page extraction** -- for each page, extract raw text via `page.extract_text()`
3. **Table detection** -- attempt `page.extract_tables()` to identify structured tables;
   pages with tables set `has_tables=1` and store extracted table JSON in `table_data`
4. **Timeout protection** -- table extraction runs with a 10-second timeout to prevent
   hanging on complex layouts
5. **Insert** one row per page into `pdf_pages`; FTS5 trigger syncs `pdf_pages_fts`

**Known limitations of PDF parsing:**

- **Table detection accuracy:** pdfplumber uses heuristics to identify table boundaries
  in PDFs. Complex multi-column layouts, nested tables, or tables that span page breaks
  can produce garbled or incomplete output.
- **Column alignment:** PDF text extraction relies on character position coordinates.
  If a PDF is generated from a scanned image (rather than from digital text), character
  positions may be imprecise, causing columns to misalign during extraction.
- **Scanned documents:** Older budget documents (pre-2010 in many cases) were scanned
  from paper rather than digitally generated. The database does not currently perform
  OCR on scanned PDFs. These documents are excluded from the database or flagged as
  low-confidence records.
- **Footnotes and annotations:** Footnotes, asterisks, and margin annotations in PDFs
  are sometimes mixed into tabular data during extraction, producing spurious values.

Users should treat amounts extracted from PDFs with more caution than amounts from
Excel exhibits. The `source_file` field on each record identifies whether data came
from a PDF or spreadsheet source.

---

## SQLite FTS5 Full-Text Search

The database is stored in **SQLite** and uses the **FTS5** (Full-Text Search version 5)
extension for keyword search across budget records and extracted document text.

FTS5 provides ranked full-text search with support for phrase queries, prefix matching,
and relevance ranking using the BM25 algorithm. Two FTS5 virtual tables are maintained:

1. **Budget line items** -- indexed fields include program title, account title,
   organization name, and narrative text extracted from R-2 exhibits.
2. **PDF text excerpts** -- page-level text extracted from PDF documents, allowing
   search to surface relevant passages even when the structured data extraction was
   incomplete.

Search results from both tables are merged and ranked by relevance before being
returned to the user.

FTS5 search is case-insensitive and handles common stemming (e.g., a search for
`aircraft` will match `aircrafts`). It does not perform semantic search or synonym
expansion -- a search for `plane` will not automatically match `aircraft`.

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

### PDF Parsing Accuracy

PDF extraction accuracy varies significantly by document. For well-structured digital
PDFs from recent years, accuracy is generally high. For older, scanned, or
unusually formatted PDFs, extraction errors -- including wrong amounts, truncated text,
or missing rows -- are possible. Every PDF-sourced record should be verified against
the original document for high-stakes use.

### Coverage Gaps

Not every exhibit type is available for every service in every year. Some documents
were not accessible via automated collection (due to site changes, link rot, or format
incompatibility). The database reflects what was successfully downloaded and parsed;
it is not guaranteed to be comprehensive.

### Amount Reconciliation

Amounts parsed from individual line items may not sum to the officially published
topline totals for a service or appropriation account. This can result from parsing
errors, missing line items, rounding differences, or the presence of classified
adjustments in official totals that do not appear in unclassified exhibits.

Do not rely on this database as the authoritative source for DoD topline spending
figures. Use the official DoD Comptroller publications for authoritative totals.

### Classified Programs

Classified or "black" programs appear in published budget documents as aggregate
placeholders without program names or details. These placeholders are present in the
database as parsed but contain limited information by design. The database does not
contain any classified information.

### Exhibit Type Column Variation

Column headers for the same exhibit type (e.g., P-1) vary across services and occasionally
across fiscal years. The column mapper handles common variations but may miss new patterns
when DoD updates document templates. Unknown columns are captured in `extra_fields` for
manual review.

### Historical Fiscal Year URL Changes

DoD service websites occasionally reorganize their URL structures for older fiscal years.
The downloader's URL templates are calibrated for recent fiscal years (FY2023+). Older
years may require URL pattern updates.

### WAF Rate Limiting

Browser-based downloads use Playwright but may still be rate-limited or blocked by WAF
policies if too many requests are made too quickly. The downloader includes a configurable
delay between file downloads.

### Monetary Unit Consistency

Most DoD exhibits denominate amounts in thousands of dollars, but a small number use
whole dollars or millions. The parser assumes thousands by default. If a particular
exhibit uses a different unit, values will be misinterpreted.

### Currency Year

The `currency_year` field distinguishes between then-year (nominal) and constant
(inflation-adjusted) dollars where the source document provides this information.
Most DoD budget exhibits use then-year dollars. Assume then-year if the field is null.

### Timeliness

The database reflects documents collected at a specific point in time. Corrections,
amendments, or supplemental budget requests issued after the initial download may not
be reflected.

---

## How to Report Data Errors

Data quality depends on user feedback. If you find a record with an incorrect amount,
a mislabeled service or program, or other apparent parsing error, please report it:

1. Copy the record's **ID** from the detail view (e.g., `bl_12345` or `pdf_67890_p45`)
2. Note the specific field and what the correct value should be
3. If possible, identify the source document (filename, page number, or row number)
   where the correct value can be verified
4. Open an issue on the project's GitHub repository with the above information

You can also run `python validate_budget_db.py --verbose` to confirm the issue is
detected by the automated validation suite.

Reports that include a reference to the source document are most actionable, because
they allow the maintainers to determine whether the error is a parser bug (fixable by
updating the parsing logic) or an anomaly in the source document itself.

Systematic errors -- where a whole exhibit type or fiscal year appears to be parsed
incorrectly -- are especially valuable to report, as they may indicate a format change
that requires a parser update.

---

See also [Data Sources](data-sources.md) for source URL details,
[Data Dictionary](data-dictionary.md) for field definitions,
and the [FAQ](faq.md) for answers to common questions.
