# Data Dictionary

<!-- TODO [Steps 2.A1, 3.C2]: Expand with full field definitions after the
     production schema is finalized and the UI is built. -->

Definitions for all fields in the DoD Budget database. Values are stored in
the `dod_budget.sqlite` database built by `build_budget_db.py`.

---

## Budget Line Items (`budget_lines` table)

| Field | Type | Description |
|-------|------|-------------|
| `id` | INTEGER | Auto-incrementing primary key |
| `source_file` | TEXT | Filename of the ingested document |
| `exhibit_type` | TEXT | Exhibit code (`p1`, `r1`, `o1`, `m1`, `c1`, `rf1`, `p1r`) |
| `sheet_name` | TEXT | Excel worksheet name (if applicable) |
| `fiscal_year` | TEXT | Fiscal year the document belongs to |
| `account` | TEXT | Appropriation account code |
| `account_title` | TEXT | Appropriation account name |
| `organization` | TEXT | Organization code (A, N, F, S, D, M, J) |
| `organization_name` | TEXT | Organization full name (Army, Navy, etc.) |
| `budget_activity` | TEXT | Budget activity code |
| `budget_activity_title` | TEXT | Budget activity name |
| `sub_activity` | TEXT | Sub-activity group code |
| `sub_activity_title` | TEXT | Sub-activity group name |
| `line_item` | TEXT | Line item number |
| `line_item_title` | TEXT | Line item description |
| `classification` | TEXT | Security classification |
| `amount_fy2024_actual` | REAL | FY2024 actual dollars (thousands) |
| `amount_fy2025_enacted` | REAL | FY2025 enacted dollars (thousands) |
| `amount_fy2025_supplemental` | REAL | FY2025 supplemental dollars (thousands) |
| `amount_fy2025_total` | REAL | FY2025 total dollars (thousands) |
| `amount_fy2026_request` | REAL | FY2026 President's Budget request (thousands) |
| `amount_fy2026_reconciliation` | REAL | FY2026 reconciliation amount (thousands) |
| `amount_fy2026_total` | REAL | FY2026 total dollars (thousands) |
| `quantity_fy2024` | REAL | FY2024 quantity (items/units) |
| `quantity_fy2025` | REAL | FY2025 quantity |
| `quantity_fy2026_request` | REAL | FY2026 requested quantity |
| `quantity_fy2026_total` | REAL | FY2026 total quantity |
| `extra_fields` | TEXT | JSON blob for fields not mapped to named columns |

---

## PDF Pages (`pdf_pages` table)

| Field | Type | Description |
|-------|------|-------------|
| `id` | INTEGER | Auto-incrementing primary key |
| `source_file` | TEXT | Filename of the ingested PDF |
| `source_category` | TEXT | Category of the source document |
| `page_number` | INTEGER | Page number within the PDF |
| `page_text` | TEXT | Extracted text content of the page |
| `has_tables` | INTEGER | 1 if tables were detected, 0 otherwise |
| `table_data` | TEXT | Extracted table data (JSON) |

---

## Reference Fields

### Organization Codes (`ORG_MAP`)

| Code | Organization |
|------|-------------|
| `A` | Army |
| `N` | Navy |
| `F` | Air Force |
| `S` | Space Force |
| `D` | Defense-Wide |
| `M` | Marine Corps |
| `J` | Joint Staff |

### Exhibit Types

See [Exhibit Types](Exhibit-Types.md) for the full catalog.

---

## Units and Conventions

- **Dollar amounts:** Stored in thousands of dollars. Display can be toggled
  to millions in the UI.
- **Fiscal years:** Formatted as four-digit years (e.g., `2026`)
- **NULL values:** NULL in an amount column means the value was not present in
  the source document (distinct from zero)

---

## Ingestion Tracking (`ingested_files` table)

Tracks which source files have been ingested (used for incremental builds).

| Field | Type | Description |
|-------|------|-------------|
| `file_path` | TEXT PK | Path relative to documents directory |
| `file_type` | TEXT | `excel` or `pdf` |
| `file_size` | INTEGER | File size in bytes at ingestion time |
| `file_modified` | REAL | File modification timestamp (Unix time) |
| `ingested_at` | TEXT | ISO timestamp when file was ingested |
| `row_count` | INTEGER | Number of rows inserted (Excel) or pages parsed (PDF) |
| `status` | TEXT | `ok` or error description |
| `source_url` | TEXT | Source URL if known |

---

## Data Source Registry (`data_sources` table)

Tracks download sources and their coverage.

| Field | Type | Description |
|-------|------|-------------|
| `source_id` | TEXT PK | Source identifier (e.g., `comptroller-2026`) |
| `source_name` | TEXT | Human-readable source name |
| `source_url` | TEXT | Source website URL |
| `fiscal_year` | TEXT | Fiscal year (e.g., `2026`) |
| `last_checked` | TEXT | ISO timestamp of last discovery check |
| `last_updated` | TEXT | ISO timestamp of last successful download |
| `file_count` | INTEGER | Number of files from this source |
| `notes` | TEXT | Any notes about the source |

---

## Build Progress (`build_progress` table)

Tracks build sessions for checkpoint/resume support.

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | TEXT UNIQUE | UUID identifying the build session |
| `checkpoint_time` | DATETIME | When this checkpoint was saved |
| `files_processed` | INTEGER | Number of files processed so far |
| `total_files` | INTEGER | Total files to process |
| `pages_processed` | INTEGER | PDF pages processed |
| `rows_inserted` | INTEGER | Budget lines inserted |
| `bytes_processed` | INTEGER | Source file bytes processed |
| `status` | TEXT | `in_progress`, `complete`, or `stopped` |
| `last_file` | TEXT | Most recently processed file path |
| `last_file_status` | TEXT | Status of the last processed file |
| `notes` | TEXT | Build notes or stop reason |

---

## Extraction Issues (`extraction_issues` table)

Logs per-file/per-page extraction problems for later triage.

| Field | Type | Description |
|-------|------|-------------|
| `file_path` | TEXT | Path of the source file |
| `page_number` | INTEGER | Page number (PDF only; NULL for Excel) |
| `issue_type` | TEXT | Category of issue (timeout, decode_error, etc.) |
| `issue_detail` | TEXT | Detailed description of the issue |
| `encountered_at` | DATETIME | When the issue was recorded |

---

## Full-Text Search Indexes

The database has two FTS5 virtual tables that are kept in sync via triggers:

| Table | Source Table | Indexed Columns |
|-------|-------------|-----------------|
| `budget_lines_fts` | `budget_lines` | account_title, budget_activity_title, sub_activity_title, line_item_title, organization_name |
| `pdf_pages_fts` | `pdf_pages` | page_text, source_file, table_data |

Query using the `MATCH` operator:
```sql
SELECT bl.*, bts.rank
FROM budget_lines bl
JOIN budget_lines_fts bts ON bl.id = bts.rowid
WHERE budget_lines_fts MATCH '"missile defense"'
ORDER BY bts.rank;
```

---

## Schema Design Notes

The current schema uses **denormalized fiscal year columns** (FY2024–FY2026 hardcoded)
for simplicity and query performance. When a new fiscal year's budget materials are
published:

1. Add new columns to `budget_lines` (e.g., `amount_fy2027_request`)
2. Update `_map_columns()` in `build_budget_db.py`
3. Update the `ingest_excel_file()` column mapping logic
4. Run `--rebuild` to regenerate the database

See the comment block in `create_database()` for a discussion of normalization
trade-offs and planned evolution.
