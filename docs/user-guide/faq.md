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

A: Thousands of dollars (as published in the source DoD documents). A value of `1000` in
the database equals $1,000,000 (one million dollars).

**Q: What is the difference between request, enacted, actual, and total?**

| Term | Meaning |
|------|---------|
| **Request** | President's Budget submission (what the administration asks for) |
| **Enacted** | Final amount authorized by Congress and signed into law |
| **Actual** | Funds actually obligated or expended in a completed fiscal year |
| **Total** | Sum of enacted + supplemental (or similar combined figure) |
| **Supplemental** | Additional funding provided via a supplemental appropriations act |

**Q: What is a Program Element (PE)?**

A: A Program Element is the fundamental building block of the DoD budget for RDT&E
activities. PEs are 8-character codes (e.g., `0602702E`) where the last character indicates
the component (E=Navy, A=Army, F=Air Force, D=Defense-Wide, etc.). The first two digits
broadly indicate the budget activity (06=RDT&E).

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

---

## Data Freshness

**Q: How often is the data updated?**

A: The database is updated manually by running the download and build pipeline. The DoD
publishes new budget materials each February when the President's Budget is submitted to
Congress. Supplemental and enacted figures are published throughout the year.

**Q: When are new fiscal year documents published?**

A: Typically in February when the President's Budget is submitted. For example, FY2026
materials appeared in February 2025. Enacted figures follow after congressional action
(often October--December).

**Q: How do I know if my data is current?**

A: Run `python search_budget.py --summary` to see ingestion counts. The `ingested_files`
table tracks when each file was last processed.

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

A: The database uses SQLite FTS5. Search queries are sanitized and matched against indexed
columns in `budget_lines_fts` and `pdf_pages_fts` virtual tables.

**Q: Can I query the database directly with SQL?**

A: Yes. The database is a standard SQLite file (`dod_budget.sqlite`). Open it with any
SQLite client (DB Browser for SQLite, DBeaver, `sqlite3` CLI) or Python:

```python
import sqlite3
conn = sqlite3.connect("dod_budget.sqlite")
rows = conn.execute("SELECT * FROM budget_lines LIMIT 10").fetchall()
```

Key tables: `budget_lines`, `pdf_pages`, `ingested_files`, `data_sources`.
