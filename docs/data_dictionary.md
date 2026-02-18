# DoD Budget Analysis — Data Dictionary

**Version:** 1.0  
**Last updated:** 2026-02-18  
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
from a source document. The flat representation (used by the API layer and existing
queries) denormalizes some reference columns for query convenience.

The normalized counterpart is `budget_line_items` (see `schema_design.py`), which
uses foreign keys to `services_agencies`, `exhibit_types`, `appropriation_titles`,
and `budget_cycles`. The column-level documentation below applies to both forms.

---

### id

- **Type:** integer
- **Description:** Auto-incrementing surrogate primary key. Uniquely identifies
  each row across the database. Used as the stable identifier in API responses and
  as the `content_rowid` for the FTS5 virtual table `budget_line_items_fts`.
- **Source exhibit:** all
- **Caveats:** IDs are not stable across full database rebuilds. Do not store
  external references to row IDs across rebuild events.

---

### source_file

- **Type:** text
- **Description:** Relative or absolute filesystem path (or a normalized filename)
  of the source document from which this row was extracted. Indicates whether the
  data came from an Excel spreadsheet or a PDF. Example:
  `DoD_Budget_Documents/FY2026/US_Army/fy2026_p1_army.xlsx`.
- **Source exhibit:** all
- **Caveats:** Path separators are OS-dependent and may differ between environments.
  Use `LIKE '%.pdf'` to identify PDF-sourced rows, which have lower parsing
  confidence than Excel-sourced rows.

---

### exhibit_type

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

---

### sheet_name

- **Type:** text (nullable)
- **Description:** Name of the Excel worksheet from which this row was extracted.
  Not applicable for PDF-sourced rows. Useful for debugging parse issues or
  identifying sub-exhibits within a multi-sheet workbook. Example: `"P-1"`,
  `"BA01"`, `"Summary"`.
- **Source exhibit:** all (Excel sources only)
- **Caveats:** Null for all PDF-sourced rows. Sheet names are not standardized
  across services or fiscal years.

---

### fiscal_year

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

---

### account

- **Type:** text (nullable)
- **Description:** Numeric appropriation account code assigned by the Office of
  Management and Budget (OMB). Identifies the Treasury account to which the
  appropriation is charged. Examples: `"2035"` (Aircraft Procurement, Army),
  `"0400"` (Research, Development, Test & Evaluation, Army). Aligns with the
  President's Budget Appendix account structure.
- **Source exhibit:** P-1, R-1, O-1, M-1, C-1
- **Caveats:** Format and length vary by service. May be null for detail exhibit
  rows where the account is implied by context (a parent summary row).

---

### account_title

- **Type:** text (nullable)
- **Description:** Human-readable title for the appropriation account identified
  by `account`. Example: `"Aircraft Procurement, Army"`,
  `"Research, Development, Test & Evaluation, Navy"`. Indexed in the FTS5
  virtual table for full-text search.
- **Source exhibit:** P-1, R-1, O-1, M-1, C-1
- **Caveats:** Titles are drawn from source documents and may vary slightly in
  wording across services or fiscal years for the same account.

---

### organization_name

- **Type:** text (nullable)
- **Description:** Name of the military department, defense agency, or DoD
  component that submitted this budget request. Examples: `"Department of the Army"`,
  `"Defense Logistics Agency"`, `"Missile Defense Agency"`. Indexed in FTS5.
  Corresponds to the `code` field of the `services_agencies` reference table.
- **Source exhibit:** all
- **Caveats:** Naming is not perfectly standardized across source documents.
  Defense-Wide submissions may use varying agency names. Use the `services_agencies`
  reference table for canonical names and groupings.

---

### budget_activity_title

- **Type:** text (nullable)
- **Description:** Title of the Budget Activity (BA) grouping within an
  appropriation account. Budget Activities subdivide appropriations into functional
  categories. For RDT&E, Budget Activities correspond to research categories:
  BA-1 Basic Research, BA-2 Applied Research, BA-3 Advanced Technology Development,
  BA-4 Advanced Component Development, BA-5 System Development, BA-6 Management
  Support, BA-7 Operational Systems Development. Indexed in FTS5.
- **Source exhibit:** P-1, R-1, O-1, P-5, R-2
- **Caveats:** May be null for rows from exhibits that do not break out Budget
  Activity hierarchies. The numeric Budget Activity code (e.g., `"BA-3"`) is not
  stored separately in the flat schema.

---

### sub_activity_title

- **Type:** text (nullable)
- **Description:** Title of the sub-activity or sub-program grouping below the
  Budget Activity level. Not all exhibit types use sub-activities. Indexed in FTS5.
- **Source exhibit:** O-1, M-1
- **Caveats:** Typically null for procurement and RDT&E exhibits. May be null even
  for O&M rows if the source document does not use sub-activity breakdowns.

---

### line_item

- **Type:** text (nullable)
- **Description:** Alphanumeric line item identifier (Line Item Number, LIN, BLI,
  or sub-program code) within a procurement or RDT&E account. Examples: `"001"`,
  `"AA"`, `"P00013"`. Combined with `account` and `pe_number`, this forms the
  lowest-level identifier for a specific weapon system, research project, or
  program element.
- **Source exhibit:** P-5, R-2, R-3, R-4
- **Caveats:** Null for summary-level exhibit rows. Format varies significantly
  by service and exhibit type. Not guaranteed to be unique within a single file.

---

### line_item_title

- **Type:** text (nullable)
- **Description:** Descriptive title for the line item identified by `line_item`.
  Examples: `"UH-60 Black Hawk Helicopter"`, `"Hypersonic Attack Cruise Missile"`,
  `"Network Modernization"`. This is the primary human-readable name for a
  specific program or procurement item. Indexed in FTS5.
- **Source exhibit:** P-5, R-2, R-3, R-4
- **Caveats:** May be null for rows extracted from PDFs where table structure was
  ambiguous. Titles are not controlled vocabulary; similar programs may appear
  under slightly different names across fiscal years or services.

---

### pe_number

- **Type:** text (nullable)
- **Description:** Program Element (PE) number — a seven-digit number followed by
  a one-letter service designator (e.g., `"0603000A"` for Army, `"0601153N"` for
  Navy). Program Elements are the primary budget accounting unit for RDT&E
  appropriations and are cross-referenced in R-1, R-2, and R-3 exhibits. Indexed
  in FTS5.
- **Source exhibit:** R-1, R-2, R-3, R-4, P-1, P-5
- **Caveats:** Null for O&M and Military Personnel rows, which do not use PE
  numbers. PE numbers may be reformatted during parsing (hyphens removed, leading
  zeros added or dropped) — normalize before joining across tables.

---

### amount_type

- **Type:** text (nullable)
- **Description:** Classifies the type of budget authority this row's amounts
  represent. Values: `"budget_authority"` (the standard President's Budget
  request), `"authorization"` (used in C-1 Military Construction exhibits),
  `"outlay"`, `"appropriation"`. Defaults to `"budget_authority"` for most rows.
- **Source exhibit:** all
- **Caveats:** Populated as `"budget_authority"` by default for Excel-parsed rows
  when the source exhibit does not explicitly label the amount type. May be null
  for PDF-extracted rows.

---

### appropriation_code

- **Type:** text (nullable)
- **Description:** Short code identifying the appropriation category for this row.
  Values match the `code` column of the `appropriation_titles` reference table:
  `"PROC"` (Procurement), `"RDTE"` (Research, Development, Test & Evaluation),
  `"MILCON"` (Military Construction), `"OMA"` (Operation & Maintenance),
  `"MILPERS"` (Military Personnel), `"RFUND"` (Revolving & Management Funds),
  `"OTHER"`.
- **Source exhibit:** all
- **Caveats:** May be null when the parser could not resolve the appropriation
  category from the source file context. Populated from `appropriation_titles`
  reference table via a lookup during ingest.

---

### appropriation_title

- **Type:** text (nullable)
- **Description:** Full human-readable name of the appropriation, e.g.,
  `"Procurement"`, `"Research, Development, Test & Evaluation"`,
  `"Military Construction"`. Denormalized from the `appropriation_titles`
  reference table for query convenience.
- **Source exhibit:** all
- **Caveats:** Populated from reference table; may be null if `appropriation_code`
  is null or unmatched.

---

### currency_year

- **Type:** text (nullable)
- **Description:** Specifies whether dollar amounts in this row are expressed in
  then-year (nominal) or constant (inflation-adjusted) dollars. Values:
  `"then-year"` or `"constant"`. Most DoD budget exhibits use then-year dollars.
  Constant-dollar exhibits are used in some long-range procurement analyses.
- **Source exhibit:** P-5, R-2, C-1
- **Caveats:** Often null because the large majority of exhibits use then-year
  dollars without explicitly labeling the field. Assume then-year if null.

---

### amount_unit

- **Type:** text (nullable)
- **Description:** Unit in which monetary amounts are reported. Default value is
  `"thousands"` (i.e., all amounts are in thousands of U.S. dollars). A value
  of `1000` in any amount column means one million dollars. Some specialized
  exhibits may use `"millions"` or `"dollars"` — treat this field as authoritative
  when present.
- **Source exhibit:** all
- **Caveats:** Defaults to `"thousands"` during ingest when not explicitly stated
  in the source document. Verify with source exhibit if using for precise dollar
  calculations.

---

### amount_fy2024_actual

- **Type:** real (nullable)
- **Description:** Enacted/actual funding amount for Fiscal Year 2024, in
  thousands of dollars. Drawn from the "Prior Year" or "FY2024 Actual" column
  in source exhibits. Represents funding actually appropriated and obligated (or
  the best estimate thereof at time of publication).
- **Source exhibit:** P-1, R-1, O-1, M-1, P-5, R-2
- **Caveats:** May be null for rows from documents published before FY2024
  comparison columns were included, or for PDF-extracted rows where the column
  alignment was ambiguous. Some exhibits report preliminary actuals rather than
  final audited figures.

---

### amount_fy2025_enacted

- **Type:** real (nullable)
- **Description:** Enacted appropriation amount for Fiscal Year 2025, in
  thousands of dollars. Drawn from the "Current Year" or "FY2025 Enacted" column
  in source exhibits. Represents the amount appropriated by Congress, excluding
  any supplemental appropriations (see `amount_fy2025_supplemental`).
- **Source exhibit:** P-1, R-1, O-1, M-1, P-5, R-2
- **Caveats:** May reflect a Continuing Resolution (CR) annualized rate rather
  than a full-year enacted figure if Congress had not yet passed an appropriations
  bill when the document was published. Check `amount_type` and `source_file`
  for context.

---

### amount_fy2025_supplemental

- **Type:** real (nullable)
- **Description:** Supplemental appropriation amount for Fiscal Year 2025, in
  thousands of dollars. Represents additional funding provided through a
  supplemental appropriations act separate from the base enacted amount. When
  non-null, adds to `amount_fy2025_enacted` to form `amount_fy2025_total`.
- **Source exhibit:** Supplemental exhibits only
- **Caveats:** Null for the vast majority of rows, which come from the base
  President's Budget request documents. Non-null only when rows are extracted from
  supplemental budget documents. Not all supplemental documents follow the same
  column layout.

---

### amount_fy2025_total

- **Type:** real (nullable)
- **Description:** Total FY2025 funding, in thousands of dollars. Equals
  `amount_fy2025_enacted + amount_fy2025_supplemental` when both are present.
  May be provided directly by the source exhibit as a computed total rather than
  derived by the parser.
- **Source exhibit:** Supplemental exhibits; some P-1 and R-1 exhibits
- **Caveats:** May be null when only the enacted figure is available. Do not
  assume this equals `amount_fy2025_enacted` — always check whether a supplemental
  component exists.

---

### amount_fy2026_request

- **Type:** real (nullable)
- **Description:** President's Budget request amount for Fiscal Year 2026, in
  thousands of dollars. This is the primary budget estimate column for most rows
  sourced from FY2026 budget justification documents. Drawn from the "Budget
  Estimate" or "FY2026 Request" column.
- **Source exhibit:** P-1, R-1, O-1, M-1, C-1, RF-1, P-5, R-2, R-3, R-4
- **Caveats:** Represents the executive branch request; enacted amounts may differ
  after Congressional action. Null for rows sourced from prior-year documents that
  predate the FY2026 submission.

---

### amount_fy2026_reconciliation

- **Type:** real (nullable)
- **Description:** Reconciliation adjustment amount for Fiscal Year 2026, in
  thousands of dollars. Represents programmatic adjustments, transfers, or
  offsets applied to the base FY2026 request to arrive at the total. May be
  positive (additional funding) or negative (reduction/offset).
- **Source exhibit:** Select P-1, R-1 exhibits with reconciliation columns
- **Caveats:** Null for the large majority of rows. Present only in exhibits that
  explicitly break out reconciliation amounts from the base request. Verify
  against source document before using.

---

### amount_fy2026_total

- **Type:** real (nullable)
- **Description:** Total FY2026 funding, in thousands of dollars. Equals
  `amount_fy2026_request + amount_fy2026_reconciliation` when both are present,
  or may equal `amount_fy2026_request` when no reconciliation column exists.
  This is the field used by API aggregation endpoints when computing FY2026 totals.
- **Source exhibit:** P-1, R-1, O-1, M-1
- **Caveats:** May be null for detail exhibit rows where only the request amount
  is provided without an explicit total column.

---

### quantity_fy2024

- **Type:** real (nullable)
- **Description:** Procurement quantity for Fiscal Year 2024 (prior year). Units
  depend on the line item (aircraft, vehicles, missiles, etc.). Used exclusively
  in procurement exhibits where unit quantities are meaningful alongside unit costs.
- **Source exhibit:** P-5, P-1R
- **Caveats:** Null for non-procurement exhibits (RDT&E, O&M, Military Personnel,
  Military Construction). May be null for procurement items where the quantity is
  classified, not applicable (e.g., "Lot" purchases), or not separately reported
  in the source exhibit.

---

### quantity_fy2025

- **Type:** real (nullable)
- **Description:** Procurement quantity for Fiscal Year 2025 (current year).
  See `quantity_fy2024` for general notes on quantity fields.
- **Source exhibit:** P-5, P-1R
- **Caveats:** Null for non-procurement rows. May reflect a planned quantity that
  differs from the ultimately contracted quantity.

---

### quantity_fy2026_request

- **Type:** real (nullable)
- **Description:** Requested procurement quantity for Fiscal Year 2026, as
  submitted in the President's Budget. See `quantity_fy2024` for general notes.
- **Source exhibit:** P-5, P-1R
- **Caveats:** Null for non-procurement rows. Quantities may be stored as real
  numbers (not integers) to accommodate fractional units or partial-year buys
  in some exhibits.

---

### quantity_fy2026_total

- **Type:** real (nullable)
- **Description:** Total procurement quantity for Fiscal Year 2026, after
  applying any adjustments or reconciliations to the base request quantity.
  See `quantity_fy2024` for general notes.
- **Source exhibit:** P-5, P-1R
- **Caveats:** Null for non-procurement rows and for procurement rows where the
  source exhibit does not provide a separate total quantity column.

---

## Reference Tables

The following lookup tables provide controlled vocabulary and metadata used to
normalize and categorize rows in `budget_lines`.

---

### `services_agencies`

Catalog of military departments, defense agencies, combatant commands, and OSD
components. Seed data is defined in `schema_design.py` (_DDL_001_SEEDS).

| Column | Type | Description |
|--------|------|-------------|
| `id` | integer | Auto-increment primary key |
| `code` | text | Short identifier used in `organization_name` matching (e.g., `"Army"`, `"DISA"`, `"DARPA"`) |
| `full_name` | text | Official full name (e.g., `"Defense Advanced Research Projects Agency"`) |
| `category` | text | Component category: `"military_dept"`, `"defense_agency"`, `"combatant_cmd"`, or `"osd_component"` |

Seeded with 22 organizations including all military departments, major defense
agencies (DLA, MDA, SOCOM, DHA, DISA, DARPA, NSA, DIA, NRO, NGA, DTRA, DCSA),
and OSD components (OSD, NGB, Joint Staff, WHS).

---

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

---

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
- **FTS5 search** indexes: `account_title`, `budget_activity_title`,
  `sub_activity_title`, `line_item_title`, `organization_name`, `pe_number`.
  Search queries are case-insensitive and use `unicode61` tokenization.

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
   services in all fiscal years. Link rot, site changes, and format incompatibilities
   may have prevented certain documents from being downloaded or successfully parsed.
   The database reflects the corpus that was successfully ingested at build time.

8. **`organization_name` is not controlled vocabulary.** Values are drawn directly
   from source documents and may vary in wording for the same organization across
   services or years. Use the `services_agencies` reference table and its `category`
   field for grouping and filtering by component type.
