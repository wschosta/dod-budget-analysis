# Data Methodology

This document describes how DoD budget data is collected, processed, and loaded into
the DoD Budget Explorer database. It is intended to help users understand the
provenance and quality of the data, and to be transparent about the limitations of
automated parsing.

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
request, or fee is required to access the originals. The DoD Budget Explorer database
is derived entirely from these publicly posted files.

---

## Collection Process

### Automated Downloading

Documents are collected using a Python-based automated downloader (`dod_budget_downloader.py`).
The downloader discovers available documents by crawling budget pages for each source
site and downloads files that match the configured fiscal years and exhibit types.

Different sites require different collection strategies:

- **DoD Comptroller and Defense-Wide:** Standard HTTP requests using the `requests`
  library with `BeautifulSoup` for HTML parsing. These sites serve documents through
  ordinary web pages without bot protection.

- **Army and Air Force:** These sites use Web Application Firewalls (WAF) that block
  standard HTTP scrapers. The downloader uses **Playwright** (a browser automation
  library driving a headless Chromium browser) to navigate these sites as a real browser
  would. This allows the downloader to receive session cookies and render JavaScript
  before making download requests.

- **Navy:** The Navy's budget archive is hosted on a SharePoint site, which requires
  browser rendering to load document links. Playwright is also used here, with the
  archive page loaded once per session and filtered in-memory for each fiscal year.

The downloader skips files that have already been downloaded (checking by filename and
file size) to avoid redundant network requests on subsequent runs.

### File Organization

Downloaded documents are stored in a local directory tree organized by fiscal year
and source:

```
DoD_Budget_Documents/
  FY2026/
    Comptroller/
    Defense_Wide/
    US_Army/
    US_Navy/
    US_Air_Force/
  FY2025/
    ...
```

---

## Parsing Approach

### Excel Files (openpyxl)

Excel budget exhibits are parsed using **openpyxl**, a Python library for reading
`.xlsx` files. The parser reads each sheet, identifies header rows, maps column names
to standardized field names, and extracts individual line items.

Excel parsing is generally the most reliable method. Budget justification spreadsheets
follow relatively consistent column layouts within a given exhibit type and fiscal year,
making it possible to define column mappings that work across many files. Common issues
include:

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

1. **Budget line items** — indexed fields include program title, account title,
   appropriation title, and narrative text extracted from R-2 exhibits.
2. **PDF text excerpts** — page-level text extracted from PDF documents, allowing
   search to surface relevant passages even when the structured data extraction was
   incomplete.

Search results from both tables are merged and ranked by relevance before being
returned to the user.

FTS5 search is case-insensitive and handles common stemming (e.g., a search for
`aircraft` will match `aircrafts`). It does not perform semantic search or synonym
expansion — a search for `plane` will not automatically match `aircraft`.

---

## Known Limitations

### PDF Parsing Accuracy

PDF extraction accuracy varies significantly by document. For well-structured digital
PDFs from recent years, accuracy is generally high. For older, scanned, or
unusually formatted PDFs, extraction errors — including wrong amounts, truncated text,
or missing rows — are possible. Every PDF-sourced record should be verified against
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

### Timeliness

The database reflects documents collected at a specific point in time. Corrections,
amendments, or supplemental budget requests issued after the initial download may not
be reflected.

---

## How to Report Errors

Data quality depends on user feedback. If you find a record with an incorrect amount,
a mislabeled service or program, or other apparent parsing error, please report it:

1. Copy the record's **ID** from the detail view (e.g., `bl_12345` or `pdf_67890_p45`)
2. Note the specific field and what the correct value should be
3. If possible, identify the source document (filename, page number, or row number)
   where the correct value can be verified
4. Open an issue on the project's GitHub repository with the above information

Reports that include a reference to the source document are most actionable, because
they allow the maintainers to determine whether the error is a parser bug (fixable by
updating the parsing logic) or an anomaly in the source document itself.

Systematic errors — where a whole exhibit type or fiscal year appears to be parsed
incorrectly — are especially valuable to report, as they may indicate a format change
that requires a parser update.
