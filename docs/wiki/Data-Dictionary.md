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
