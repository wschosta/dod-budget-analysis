# Frequently Asked Questions

---

## Data Coverage

**Q: What military branches are covered?**

A: Army, Navy, Marine Corps, Air Force, Space Force, Defense-Wide agencies, and Joint Staff.
Each service publishes its own budget justification exhibits; coverage depends on which
sources were downloaded. See [Data Sources](data-sources.md) for details.

**Q: What fiscal years are available?**

A: The downloader currently targets FY2024, FY2025, and FY2026 by default. Historical data
back to approximately FY2017 is available on the source websites. Use `--years all` to
attempt to discover and download all available years.

**Q: Are classified programs included?**

A: No. Only unclassified, publicly available budget documents are downloaded and parsed.
Classified programs appear in separate Special Access Program (SAP) budgets that are not
publicly released.

**Q: What about supplemental appropriations?**

A: FY2025 supplemental amounts are stored in `amount_fy2025_supplemental` and
`amount_fy2025_total` columns when present in source documents. Not all exhibits include
supplemental data.

**Q: Are Reserve and National Guard budgets included?**

A: Yes, where published. P-1R exhibits cover Reserve component procurement. Military
personnel exhibits (M-1) typically include breakdowns for Active, Reserve, and Guard
components.

---

## Units and Terminology

**Q: What unit are dollar amounts in?**

A: **Thousands of dollars ($K)**, as published in the source DoD documents. A value of
`1000` in the database equals $1,000,000 (one million dollars).

So a figure of `$1,200,000` in the database means $1.2 billion (1,200,000 x $1,000),
not $1.2 million. A figure of `$450,000` means $450 million.

This is standard practice across all DoD budget documents and is not an error. When
reading or citing specific amounts, always multiply the displayed figure by 1,000 to
get the actual dollar value.

**Q: What is the difference between request, enacted, actual, and total?**

| Term | Meaning |
|------|---------|
| **Request** | President's Budget submission (what the administration asks for) |
| **Enacted** | Final amount authorized by Congress and signed into law |
| **Actual** | Funds actually obligated or expended in a completed fiscal year |
| **Total** | Sum of enacted + supplemental (or similar combined figure) |
| **Supplemental** | Additional funding provided via a supplemental appropriations act |

**Q: What's the difference between PB, enacted, and CR amounts?**

- **PB (President's Budget):** The formal budget request submitted by the President to
  Congress, usually in February. This is what the executive branch is asking to receive.
  PB figures represent intent and priorities, but Congress is not required to approve them.

- **Enacted:** The amount Congress actually appropriated, as signed into law through
  an appropriations act. Enacted figures may be higher or lower than the PB request,
  and Congress sometimes funds programs the executive did not request, or cuts programs
  the executive prioritized.

- **CR (Continuing Resolution):** When Congress does not pass full-year appropriations
  by October 1, it passes a CR that temporarily funds the government, usually at the
  prior year's rate. CR figures are not the same as PB or enacted figures and do not
  reflect new program requests.

Most documents in this database represent PB submissions. Enacted amounts, where
available, are noted in separate columns and sourced from enacted appropriations exhibits.

**Q: What is a Program Element (PE)?**

A: A Program Element is the fundamental building block of the DoD budget for RDT&E
activities. PEs are 8-character codes (e.g., `0602702E`) where the last character indicates
the component (E=Navy, A=Army, F=Air Force, D=Defense-Wide, etc.). The first two digits
broadly indicate the budget activity (06=RDT&E).

PE numbers are useful for tracking a single program across multiple years or across
different exhibit types (e.g., finding both the R-2 research justification and the P-5
procurement detail for the same program).

| Suffix | Component |
|--------|-----------|
| `A` | Army |
| `N` | Navy / Marine Corps |
| `F` | Air Force / Space Force |
| `D` | Defense-Wide |
| `E` | Defense Agencies (some) |

**Example:** PE `0604229F` is the F-35 Lightning II program element for the Air Force.

**Q: What is a budget activity?**

A: Budget activities subdivide appropriations into functional categories. For RDT&E:

| Code | Name |
|------|------|
| 6.1 | Basic Research |
| 6.2 | Applied Research |
| 6.3 | Advanced Technology Development |
| 6.4 | Advanced Component Development & Prototypes |
| 6.5 | System Development & Demonstration |
| 6.6 | RDT&E Management Support |
| 6.7 | Operational System Development |

**Q: What does each exhibit type represent?**

A: See [Exhibit Types](exhibit-types.md) for the full catalog. In brief:

| Code | Name |
|------|------|
| P-1 | Procurement summary |
| P-1R | Procurement (Reserve component) |
| P-5 | Procurement line-item detail |
| R-1 | RDT&E summary |
| R-2 | RDT&E program element schedule |
| R-3 | RDT&E project detail |
| R-4 | RDT&E budget item justification |
| O-1 | Operation & Maintenance |
| M-1 | Military Personnel |
| C-1 | Military Construction |
| RF-1 | Revolving Funds |

**Q: What is an exhibit type (R-2, P-5, etc.)?**

A: Exhibit types are the standardized form numbers used in DoD budget justification
documents. Each type corresponds to a different appropriation category and level of detail:

| Exhibit | Full Name | What It Contains |
|---------|-----------|------------------|
| **P-1** | Procurement Summary | Summary-level list of all procurement line items |
| **P-5** | Procurement Detail | Cost and quantity breakdowns, unit costs, production quantities |
| **R-1** | RDT&E Summary | Summary list of all research and development programs |
| **R-2** | RDT&E Program Detail | Narrative descriptions, technical goals, and funding profiles for individual R&D programs |
| **O-1** | Operation & Maintenance Summary | O&M budget by activity group |
| **M-1** | Military Personnel | Military pay, allowances, and authorized end-strength |
| **C-1** | Military Construction | Individual construction projects with location and cost |
| **RF-1** | Revolving Fund | Working capital fund activity |

The exhibit type determines what fields are available for a given record. Procurement
exhibits (P-1, P-5) include quantity and unit cost fields. RDT&E exhibits (R-1, R-2)
include technology readiness levels and development phase information where available.

---

## Data Freshness

**Q: How often is the data updated?**

A: The database can be updated by running the download and build pipeline, or via the
automated weekly refresh (`refresh_data.py`). The DoD publishes new budget materials each
February when the President's Budget is submitted to Congress. Supplemental and enacted
figures are published throughout the year.

**Q: When are new fiscal year documents published?**

A: Typically in February when the President's Budget is submitted. For example, FY2026
materials appeared in February 2025. Enacted figures follow after congressional action
(often October--December).

**Q: How do I know if my data is current?**

A: Run `python search_budget.py --summary` to see ingestion counts. The `ingested_files`
table tracks when each file was last processed. In the web UI, the `/health/detailed`
endpoint shows database statistics and the last ingestion timestamp.

---

## Why Don't Service Totals Add Up?

There are several legitimate reasons why totals you compute from this database may not
match figures published by DoD:

1. **Coverage gaps:** Not every line item from every exhibit has been successfully
   parsed and loaded. Missing rows will cause totals to be lower than official figures.
2. **Rounding:** Exhibit documents sometimes round individual line items in ways that
   do not sum exactly to their own reported totals.
3. **Double-counting risk:** Some programs appear in both summary exhibits (e.g., P-1)
   and detail exhibits (e.g., P-5), representing the same funding. Summing across
   exhibit types without filtering can double-count amounts.
4. **Parsing errors:** Automated parsing of PDF and Excel files occasionally misreads
   values, particularly for complex multi-column layouts or merged cells.
5. **Scope differences:** DoD's published topline figures sometimes include items not
   broken out at the line-item level in justification exhibits (e.g., classified programs,
   legislative rescissions, or adjustments).

For authoritative totals, always refer to the official DoD Comptroller published documents.

---

## Why Are Some Years Missing?

Coverage varies for several reasons:

- **Format changes:** DoD periodically changes the format of budget exhibits (switching
  from PDF to Excel, restructuring columns, or renaming fields). When the format changes,
  the parser may not extract data correctly until it is updated.
- **Availability:** Not all historical documents are posted on current service websites.
  Older documents may have been removed or archived in ways that automated collection
  cannot reach.
- **Parsing failures:** Some documents -- particularly older PDFs -- could not be parsed
  reliably enough to include in the database. See the [Methodology](methodology.md) for
  more on parsing accuracy.
- **Coverage scope:** The project began with recent fiscal years and is expanding backward
  over time. Some earlier years may not yet be included.

If a specific fiscal year or service you need is missing, check the
[Methodology](methodology.md) for known gaps, or report it as a data gap.

---

## Known Limitations

**Q: Why are some rows showing zero or NULL amounts?**

A: Several possible reasons:

- The source document omitted that fiscal year column for that exhibit type
- The exhibit uses a different column layout that the parser did not recognize
- The row is a subtotal or header row, not a data row

Run `python validate_budget_db.py --verbose` to see which files and exhibit types have
high rates of zero/null amounts.

**Q: Why is a particular service missing a fiscal year?**

A: Common reasons:

- The source website did not have documents for that year
- A WAF blocked the browser download
- Playwright was not installed for browser-required sources

Check the download log and re-run with `--years <year> --sources <service>`.

**Q: How accurate is the PDF text extraction?**

A: Text extraction via pdfplumber is accurate for text-layer PDFs. Scanned PDFs produce
poor or no text. Table extraction accuracy varies by layout. PDF data is stored as-is in
`pdf_pages` for full-text search; it is not structured into columns like Excel data.

**Q: What happens when column layouts change between fiscal years?**

A: The column mapper uses fuzzy header matching and falls back to positional mapping for
unknown columns. Unknown columns are stored in the `extra_fields` JSON blob.

**Q: Why does the downloader require a browser (Playwright)?**

A: Army, Navy, and Air Force websites use WAFs that block plain HTTP requests from scripts.
Playwright emulates a real browser. Comptroller and Defense-Wide sources work without it.

---

## Querying the Database

**Q: How does full-text search work?**

A: The database uses SQLite FTS5 with BM25 ranking. Search queries are sanitized and
matched against indexed columns in `budget_lines_fts` and `pdf_pages_fts` virtual tables.
Both the CLI (`search_budget.py`) and the web UI use the same search engine.

**Q: Can I query the database directly with SQL?**

A: Yes. The database is a standard SQLite file (`dod_budget.sqlite`). Open it with any
SQLite client (DB Browser for SQLite, DBeaver, `sqlite3` CLI) or Python:

```python
import sqlite3
conn = sqlite3.connect("dod_budget.sqlite")
rows = conn.execute("SELECT * FROM budget_lines LIMIT 10").fetchall()
```

Key tables: `budget_lines`, `pdf_pages`, `ingested_files`, `data_sources`.

**Q: Is there a REST API?**

A: Yes. Start the web server with `uvicorn api.app:app --reload --port 8000` and access
the API at `http://localhost:8000/api/v1/`. Interactive API documentation is available at
`/docs` (Swagger UI) and `/redoc` (ReDoc). See the
[API Reference](../developer/api-reference.md) for full endpoint details.

---

## How Do I Cite This Data?

When citing specific budget figures for reporting or research, we recommend citing both
this database and the underlying source document. Example citation format:

> [Program Name], [Service], FY[Year] President's Budget, [Exhibit Type],
> [Amount] (in thousands). Source document: [source_file field]. Data via
> DoD Budget Explorer, accessed [date].

The `source_file` field on each record identifies the original document filename.
The source documents themselves are public records published by the Department of Defense
and available on the DoD Comptroller website (comptroller.defense.gov) and individual
service budget office websites.

For journalistic use, confirm key figures against the primary source document before
publication.

---

## How Do I Report Errors?

If you find data that appears incorrect -- a wrong amount, a mislabeled service, a
program attributed to the wrong fiscal year, or a line item that is clearly garbled --
please report it.

**To report an error:**

1. Note the record ID (the `id` field shown in the detail view, e.g., `bl_12345`)
2. Note the specific field that appears wrong and what the correct value should be
3. If possible, identify the source document page or row where the correct value appears
4. Submit a report via the project's GitHub issue tracker, or use the feedback form
   in the web UI

Including the source document reference makes it much easier to diagnose whether the
error is a parsing bug, a data entry issue in the original document, or a known
limitation of automated extraction.

See also the [Methodology](methodology.md) document for a description of known parsing
limitations that may explain some apparent errors.

---

See also [Getting Started](getting-started.md) for setup instructions and
[Data Dictionary](data-dictionary.md) for field definitions.
