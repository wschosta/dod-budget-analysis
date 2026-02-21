# Data Dictionary

Definitions for all fields in the DoD Budget database. Values are stored in
the `dod_budget.sqlite` database built by `build_budget_db.py`.

**Version:** 1.0
**Schema version:** 2 (migration 002_fts5_indexes applied)

---

## Introduction

This data dictionary describes the tables and fields in the DoD Budget Explorer
SQLite database. All data originates from publicly available U.S. Department of
Defense budget justification documents published by the DoD Comptroller
(comptroller.defense.gov) and the service budget offices (Army, Navy, Marine Corps,
Air Force, Space Force, and Defense-Wide agencies).

Documents are downloaded in Excel (`.xlsx`) and PDF formats, parsed by an automated
pipeline (`build_budget_db.py`), and loaded into a normalized SQLite database. The
schema is applied via a migration framework (`schema_design.py`); the current
production schema is at version 2.

**Monetary units:** Unless otherwise noted, all dollar amounts are expressed in
**thousands of U.S. dollars (i.e., $K)**, matching the convention used in the
source budget exhibits. An `amount` value of `1000` means $1,000,000 (one million
dollars).

**Fiscal year convention:** DoD fiscal years run from October 1 through September 30.
"FY2026" means October 1, 2025 through September 30, 2026.

**API field naming:** All fields use `snake_case`. The REST API exposes two response
shapes: `BudgetLineOut` (a summary subset) and `BudgetLineDetailOut` (the full row
including all amount and quantity columns).

---

## Table: `budget_lines`

This is the primary fact table. Each row represents one budget line item extracted
from a source document.

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
| `sub_activity` | TEXT | Sub-activity group code (O-1/M-1 exhibits) |
| `sub_activity_title` | TEXT | Sub-activity group name |
| `line_item` | TEXT | Line item or PE/BLI number |
| `line_item_title` | TEXT | Line item description |
| `classification` | TEXT | Security classification |
| `amount_fy2024_actual` | REAL | FY2024 actual dollars (**thousands**) |
| `amount_fy2025_enacted` | REAL | FY2025 enacted dollars (**thousands**) |
| `amount_fy2025_supplemental` | REAL | FY2025 supplemental dollars (**thousands**) |
| `amount_fy2025_total` | REAL | FY2025 total dollars (**thousands**) |
| `amount_fy2026_request` | REAL | FY2026 President's Budget request (**thousands**) |
| `amount_fy2026_reconciliation` | REAL | FY2026 reconciliation amount (**thousands**) |
| `amount_fy2026_total` | REAL | FY2026 total dollars (**thousands**) |
| `quantity_fy2024` | REAL | FY2024 quantity (items/units) |
| `quantity_fy2025` | REAL | FY2025 quantity |
| `quantity_fy2026_request` | REAL | FY2026 requested quantity |
| `quantity_fy2026_total` | REAL | FY2026 total quantity |
| `extra_fields` | TEXT | JSON blob for fields not mapped to named columns |
| `pe_number` | TEXT | Program Element number extracted from line_item or account (e.g. `0602702E`). Indexed and FTS5-searchable. |
| `currency_year` | TEXT | Dollar type: `"then-year"` (nominal) or `"constant"` dollars |
| `appropriation_code` | TEXT | Leading numeric code from account_title (e.g. `"2035"` for Aircraft Procurement, Army) |
| `appropriation_title` | TEXT | Appropriation name without the leading code |
| `amount_unit` | TEXT | Unit of stored dollar amounts -- always `"thousands"` after normalization; non-thousands values indicate a missed conversion |
| `budget_type` | TEXT | Broad budget category derived from exhibit type: `MilPers`, `O&M`, `Procurement`, `RDT&E`, `Construction`, `Revolving`, or NULL |

---

### Field Details

#### id

- **Type:** integer
- **Description:** Auto-incrementing surrogate primary key. Uniquely identifies
  each row across the database. Used as the stable identifier in API responses and
  as the `content_rowid` for the FTS5 virtual table `budget_line_items_fts`.
- **Source exhibit:** all
- **Caveats:** IDs are not stable across full database rebuilds. Do not store
  external references to row IDs across rebuild events.

#### source_file

- **Type:** text
- **Description:** Relative or absolute filesystem path (or a normalized filename)
  of the source document from which this row was extracted. Indicates whether the
  data came from an Excel spreadsheet or a PDF. Example:
  `DoD_Budget_Documents/FY2026/US_Army/fy2026_p1_army.xlsx`.
- **Source exhibit:** all
- **Caveats:** Path separators are OS-dependent and may differ between environments.
  Use `LIKE '%.pdf'` to identify PDF-sourced rows, which have lower parsing
  confidence than Excel-sourced rows.

#### exhibit_type

- **Type:** text (nullable)
- **Description:** Short code identifying the DoD budget exhibit type from which
  this row was extracted. Common values: `p1`, `r1`, `o1`, `m1`, `c1`, `rf1`,
  `p1r`, `p5`, `r2`, `r3`, `r4`. Summary exhibits (`p1`, `r1`, `o1`, `m1`, `c1`,
  `rf1`) contain service-level roll-ups; detail exhibits (`p5`, `r2`, `r3`, `r4`)
  contain program-level line items.
- **Source exhibit:** all
- **Caveats:** May be null for rows extracted from documents where the exhibit type
  could not be inferred from the filename or sheet header. Values are lowercase
  (e.g., `p5` not `P-5`).

#### fiscal_year

- **Type:** text (nullable)
- **Description:** The DoD fiscal year to which this budget request applies,
  stored as a four-digit string (e.g., `"2026"`). Determined from the source
  document filename or header metadata.
- **Source exhibit:** all
- **Caveats:** May be null when fiscal year cannot be parsed from the source
  document. A single source file typically contains data for a single fiscal year,
  but some documents include multi-year comparison columns; in those cases each
  comparison amount is stored as a separate field (e.g., `amount_fy2024_actual`)
  rather than a separate row.

#### organization_name

- **Type:** text (nullable)
- **Description:** Name of the military department, defense agency, or DoD
  component that submitted this budget request. Examples: `"Department of the Army"`,
  `"Defense Logistics Agency"`, `"Missile Defense Agency"`. Indexed in FTS5.
- **Source exhibit:** all
- **Caveats:** Naming is not perfectly standardized across source documents.
  Defense-Wide submissions may use varying agency names. Use the `services_agencies`
  reference table for canonical names and groupings.

#### pe_number

- **Type:** text (nullable)
- **Description:** Program Element (PE) number -- a seven-digit number followed by
  a one-letter service designator (e.g., `"0603000A"` for Army, `"0601153N"` for
  Navy). Program Elements are the primary budget accounting unit for RDT&E
  appropriations and are cross-referenced in R-1, R-2, and R-3 exhibits. Indexed
  in FTS5.
- **Source exhibit:** R-1, R-2, R-3, R-4, P-1, P-5
- **Caveats:** Null for O&M and Military Personnel rows, which do not use PE
  numbers. PE numbers may be reformatted during parsing (hyphens removed, leading
  zeros added or dropped) -- normalize before joining across tables.

#### amount_fy2026_request

- **Type:** real (nullable)
- **Description:** President's Budget request amount for Fiscal Year 2026, in
  thousands of dollars. This is the primary budget estimate column for most rows
  sourced from FY2026 budget justification documents.
- **Source exhibit:** P-1, R-1, O-1, M-1, C-1, RF-1, P-5, R-2, R-3, R-4
- **Caveats:** Represents the executive branch request; enacted amounts may differ
  after Congressional action. Null for rows sourced from prior-year documents that
  predate the FY2026 submission.

#### amount_fy2025_enacted

- **Type:** real (nullable)
- **Description:** Enacted appropriation amount for Fiscal Year 2025, in
  thousands of dollars. Represents the amount appropriated by Congress, excluding
  any supplemental appropriations (see `amount_fy2025_supplemental`).
- **Source exhibit:** P-1, R-1, O-1, M-1, P-5, R-2
- **Caveats:** May reflect a Continuing Resolution (CR) annualized rate rather
  than a full-year enacted figure if Congress had not yet passed an appropriations
  bill when the document was published.

#### amount_fy2025_supplemental

- **Type:** real (nullable)
- **Description:** Supplemental appropriation amount for Fiscal Year 2025, in
  thousands of dollars. When non-null, adds to `amount_fy2025_enacted` to form
  `amount_fy2025_total`.
- **Source exhibit:** Supplemental exhibits only
- **Caveats:** Null for the vast majority of rows. Non-null only when rows are
  extracted from supplemental budget documents.

#### amount_fy2026_reconciliation

- **Type:** real (nullable)
- **Description:** Reconciliation adjustment amount for Fiscal Year 2026, in
  thousands of dollars. May be positive (additional funding) or negative
  (reduction/offset).
- **Source exhibit:** Select P-1, R-1 exhibits with reconciliation columns
- **Caveats:** Null for the large majority of rows.

#### amount_unit

- **Type:** text (nullable)
- **Description:** Unit in which monetary amounts are reported. Default value is
  `"thousands"` (i.e., all amounts are in thousands of U.S. dollars). A value
  of `1000` in any amount column means one million dollars.
- **Source exhibit:** all
- **Caveats:** Defaults to `"thousands"` during ingest when not explicitly stated
  in the source document.

---

## Table: `pdf_pages`

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

## Reference Tables

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

### `services_agencies`

Catalog of military departments, defense agencies, combatant commands, and OSD
components. Seed data is defined in `schema_design.py`.

| Column | Type | Description |
|--------|------|-------------|
| `id` | integer | Auto-increment primary key |
| `code` | text | Short identifier used in `organization_name` matching (e.g., `"Army"`, `"DISA"`, `"DARPA"`) |
| `full_name` | text | Official full name (e.g., `"Defense Advanced Research Projects Agency"`) |
| `category` | text | Component category: `"military_dept"`, `"defense_agency"`, `"combatant_cmd"`, or `"osd_component"` |

Seeded with 22 organizations including all military departments, major defense
agencies (DLA, MDA, SOCOM, DHA, DISA, DARPA, NSA, DIA, NRO, NGA, DTRA, DCSA),
and OSD components (OSD, NGB, Joint Staff, WHS).

### `exhibit_types`

Catalog of DoD budget exhibit formats. Each exhibit type has a defined column
layout documented in `exhibit_catalog.py`.

| Column | Type | Description |
|--------|------|-------------|
| `id` | integer | Auto-increment primary key |
| `code` | text | Lowercase exhibit key matching `budget_lines.exhibit_type` (e.g., `"p5"`, `"r2"`) |
| `display_name` | text | Human-readable name (e.g., `"Procurement Detail (P-5)"`) |
| `exhibit_class` | text | `"summary"` (service-level roll-up) or `"detail"` (program-level line items) |
| `description` | text | Brief description of the exhibit's purpose |

Seeded with 11 exhibit types: `p1`, `r1`, `o1`, `m1`, `c1`, `rf1`, `p1r`
(summary class) and `p5`, `r2`, `r3`, `r4` (detail class).

See [Exhibit Types](exhibit-types.md) for the full catalog.

### `appropriation_titles`

Maps short appropriation codes to their official titles and budget color-of-money
classification.

| Column | Type | Description |
|--------|------|-------------|
| `id` | integer | Auto-increment primary key |
| `code` | text | Short code matching `budget_lines.appropriation_code` (e.g., `"RDTE"`, `"PROC"`) |
| `title` | text | Full appropriation title (e.g., `"Research, Development, Test & Evaluation"`) |
| `color_of_money` | text | Budget category: `"investment"`, `"operation"`, or `"personnel"` (null for `OTHER`) |

Seeded with 7 codes: `PROC` (investment), `RDTE` (investment), `MILCON`
(investment), `OMA` (operation), `MILPERS` (personnel), `RFUND` (operation),
`OTHER`.

---

## Units and Conventions

- **Dollar amounts:** All `amount_*` columns are stored in **thousands of
  dollars**. Values from millions-denominated source exhibits are multiplied
  by 1,000 during ingestion so that all stored values share the same unit.
  Use `search_budget.py --unit millions` or the `unit millions` interactive
  command to display values divided by 1,000 with a ($M) label.
- **Fiscal years:** Formatted as four-digit years (e.g., `2026`)
- **NULL values:** NULL in an amount column means the value was not present in
  the source document (distinct from zero)
- **PE numbers:** Program Element numbers follow the pattern `DDDDDDDLL`
  (7 digits + 1--2 uppercase letters, e.g. `0602702E`). They are searchable
  via the `pe_number` column index and the FTS5 full-text search index.

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

FTS5 search is case-insensitive and uses `unicode61` tokenization. Indexed fields
include: `account_title`, `budget_activity_title`, `sub_activity_title`,
`line_item_title`, `organization_name`, `pe_number`.

---

## API Field Naming Conventions

- All fields use **`snake_case`** in both the database schema and API responses.
- **Monetary fields** are prefixed with `amount_` and suffixed with the fiscal
  year and budget phase (e.g., `amount_fy2026_request`, `amount_fy2025_enacted`).
  All monetary values are in **thousands of U.S. dollars ($K)** unless
  `amount_unit` explicitly states otherwise.
- **Quantity fields** are prefixed with `quantity_` and follow the same year
  suffix pattern (e.g., `quantity_fy2026_request`).
- **Nullable fields** default to `None` (JSON `null`) in API responses. The
  `BudgetLineOut` summary shape omits the detail-only fields
  (`appropriation_code`, `appropriation_title`, `currency_year`, `amount_unit`,
  `amount_fy2025_supplemental`, `amount_fy2025_total`,
  `amount_fy2026_reconciliation`, and all `quantity_*` fields). Use the
  `/api/v1/budget-lines/{id}` endpoint to retrieve the full `BudgetLineDetailOut`
  shape.

---

## Schema Design Notes

The current schema uses **denormalized fiscal year columns** (FY2024--FY2026 hardcoded)
for simplicity and query performance. When a new fiscal year's budget materials are
published:

1. Add new columns to `budget_lines` (e.g., `amount_fy2027_request`)
2. Update `_map_columns()` in `build_budget_db.py`
3. Update the `ingest_excel_file()` column mapping logic
4. Run `--rebuild` to regenerate the database

See the comment block in `create_database()` for a discussion of normalization
trade-offs and planned evolution.

---

## Known Data Quality Caveats

1. **PDF extraction accuracy is lower than Excel.** Rows sourced from PDF
   documents (identifiable via `source_file` ending in `.pdf`) should be treated
   with reduced confidence. Amount columns may be null, misaligned, or contain
   footnote artifacts from PDF table extraction. Always verify PDF-sourced amounts
   against the original published document.

2. **Amount reconciliation gaps.** Individual line-item amounts do not always sum
   to officially published service or appropriation toplines. Discrepancies arise
   from parsing gaps, rounding, classified line-item placeholders, or late-cycle
   amendments not captured in the downloaded corpus.

3. **Classified program placeholders.** Classified or "black" programs appear in
   unclassified exhibits as aggregate placeholder rows with no program name or
   detail. These rows are ingested as-is with null `line_item_title` and
   `pe_number`. The database contains no classified information.

4. **Column layout shifts across fiscal years.** Some exhibit types have changed
   column positions or header names between FY2024 and FY2026. Year-specific
   parsing logic is applied where identified, but undetected format changes may
   produce null amount columns for affected rows.

5. **`pe_number` normalization.** Program Element numbers are parsed from source
   documents that apply inconsistent formatting (with or without hyphens, with or
   without leading zeros). Normalize to 8-character format (7 digits + 1 letter)
   before joining across tables or fiscal years.

6. **Continuing Resolution periods.** When the source document was published
   during an active Continuing Resolution, `amount_fy2025_enacted` may reflect
   an annualized CR rate rather than a final enacted appropriation. No flag
   currently distinguishes CR-based figures from full-year enacted figures.

7. **Coverage is not comprehensive.** Not all exhibit types are available for all
   services in all fiscal years. The database reflects the corpus that was
   successfully ingested at build time.

8. **`organization_name` is not controlled vocabulary.** Values are drawn directly
   from source documents and may vary in wording for the same organization across
   services or years. Use the `services_agencies` reference table and its `category`
   field for grouping and filtering by component type.

---

See also [Exhibit Types](exhibit-types.md) for exhibit column structures,
[Methodology](methodology.md) for details on how data is parsed, and
the [Database Schema](../developer/database-schema.md) for the full DDL.
