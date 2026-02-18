# Exhibit Types

Catalog of DoD budget exhibit types and their column structures. The internal
code for each type is used in the `exhibit_type` column of the database.

> This page is generated from `exhibit_catalog.py`, which is the single source of truth
> for column layouts and semantics. See that file for the full `EXHIBIT_CATALOG` dict.

---

## Summary of Known Types

| Code | DB Key | Name | Description |
|------|--------|------|-------------|
| P-1 | `p1` | Procurement | Procurement line items by appropriation and budget activity |
| P-1R | `p1r` | Procurement (Reserves) | Reserve component procurement items |
| P-5 | `p5` | Procurement Detail | Per-item quantities and unit costs within procurement accounts |
| R-1 | `r1` | RDT&E | Research, Development, Test & Evaluation program elements |
| R-2 | `r2` | RDT&E Schedule | Program element schedule with milestone and achievement data |
| R-3 | `r3` | RDT&E Project | Project-level schedule showing development approach and cost growth |
| R-4 | `r4` | RDT&E Justification | Detailed budget item justification with technical narrative |
| O-1 | `o1` | Operation & Maintenance | O&M by budget activity |
| M-1 | `m1` | Military Personnel | Military personnel funding by component |
| C-1 | `c1` | Military Construction | Military construction projects |
| RF-1 | `rf1` | Revolving Funds | Defense Working Capital Fund and similar revolving accounts |

---

## P-1 — Procurement

**DB key:** `p1`  
**Description:** Summary procurement budget exhibit — funding requests for procurement
of weapons, vehicles, aircraft, ships, and other equipment.

### Column Layout

| Field | Header Patterns | Data Type | Description |
|-------|----------------|-----------|-------------|
| `account` | Account, ACC | Text | Procurement account code (e.g., 2035 for Aircraft Procurement, Army) |
| `account_title` | Account Title, Title | Text | Full title of the procurement account |
| `program_element` | PE, Program Element | Text | Program Element number (7 digits + 1 letter) |
| `appropriation` | Appropriation | Text | Appropriation category |
| `budget_activity` | BA, Budget Activity | Text | Budget Activity Code |
| `amount_fy2024_actual` | Prior Year, PriorYBud | Currency (thousands) | Prior year enacted amount |
| `amount_fy2025_enacted` | Current Year, CurYBud | Currency (thousands) | Current year enacted amount |
| `amount_fy2026_request` | Budget Estimate, BudEst | Currency (thousands) | President's budget estimate |

### Known Variations

- Navy/USMC versions may use "PE/BLI" header instead of separate Program Element column
- Army versions sometimes include "SLI" (Sub-Line Item) designation
- Column order may vary by service; the parser uses header patterns for robust matching

---

## P-1R — Procurement (Reserves)

**DB key:** `p1r`  
**Description:** Procurement reserves budget — unfunded requirements and contingency funds
for Reserve component.

### Column Layout

| Field | Header Patterns | Data Type | Description |
|-------|----------------|-----------|-------------|
| `reserve_type` | Reserve Type, Type | Text | Type of reserve (unfunded requirement, contingency) |
| `line_item_title` | Description, Title | Text | Description of the reserve |
| `amount_fy2024_actual` | Prior Year | Currency (thousands) | Prior year amount |
| `amount_fy2025_enacted` | Current Year | Currency (thousands) | Current year amount |
| `amount_fy2026_request` | Estimate | Currency (thousands) | Budget estimate |
| `extra_fields.justification` | Justification, Rationale | Text | Justification for the reserve |

---

## P-5 — Procurement Detail

**DB key:** `p5`  
**Description:** Detailed procurement line items — provides per-item quantities and unit
costs within procurement accounts. Supplements the P-1 summary.

### Column Layout

| Field | Header Patterns | Data Type | Description |
|-------|----------------|-----------|-------------|
| `account` | Account | Text | Procurement account code |
| `program_element` | PE, Program Element | Text | Program Element number |
| `line_item` | LIN, Line Item, Item Number | Text | Line Item Number (unique within account) |
| `line_item_title` | Title, Item Title | Text | Description of the procurement item |
| `extra_fields.unit` | Unit, UOM, Unit of Measure | Text | Unit of measure (Each, Lot, Program) |
| `quantity_fy2024` | Prior Year Quantity, PY Qty | Integer | Prior year quantity |
| `extra_fields.prior_year_unit_cost` | Prior Year Unit Cost | Currency (thousands) | Prior year unit cost |
| `quantity_fy2025` | Current Year Quantity, CY Qty | Integer | Current year quantity |
| `extra_fields.current_year_unit_cost` | Current Year Unit Cost | Currency (thousands) | Current year unit cost |
| `quantity_fy2026_request` | Estimate Quantity, Est Qty | Integer | Budget estimate quantity |
| `amount_fy2026_request` | Estimate Unit Cost | Currency (thousands) | Budget estimate unit cost |
| `extra_fields.justification` | Justification | Text | Narrative justification |

### Known Variations

- Quantity and unit cost may be combined into a single "total amount" column for
  items with unit=Program
- Some exhibits show APUC (Average Procurement Unit Cost) instead of unit cost

---

## R-1 — RDT&E

**DB key:** `r1`  
**Description:** Research, Development, Test & Evaluation summary — funding for military
technology development programs organized by Program Element.

### Column Layout

| Field | Header Patterns | Data Type | Description |
|-------|----------------|-----------|-------------|
| `account` | Account, ACC | Text | RDT&E account code |
| `account_title` | Account Title, Title | Text | Full account title |
| `program_element` | PE, Program Element | Text | Program Element number |
| `appropriation` | Appropriation | Text | Appropriation category (RDT&E) |
| `budget_activity` | BA, Budget Activity | Text | Budget Activity code (6.1–6.7) |
| `amount_fy2024_actual` | Prior Year, PriorYBud | Currency (thousands) | Prior year enacted |
| `amount_fy2025_enacted` | Current Year, CurYBud | Currency (thousands) | Current year enacted |
| `amount_fy2026_request` | Budget Estimate, BudEst | Currency (thousands) | President's budget estimate |

### Budget Activity Codes (RDT&E)

| Code | Description |
|------|-------------|
| 6.1 | Basic Research |
| 6.2 | Applied Research |
| 6.3 | Advanced Technology Development |
| 6.4 | Advanced Component Development & Prototypes |
| 6.5 | System Development & Demonstration |
| 6.6 | RDT&E Management Support |
| 6.7 | Operational System Development |

---

## R-2 — RDT&E Schedule

**DB key:** `r2`  
**Description:** RDT&E line-item schedule with milestone and achievement data for research
programs. Provides more detail than R-1.

### Column Layout

| Field | Header Patterns | Data Type | Description |
|-------|----------------|-----------|-------------|
| `program_element` | PE, Program Element | Text | Program Element number |
| `extra_fields.sub_element` | Sub-Element, Sub Element | Text | Sub-element or sub-project designation |
| `line_item_title` | Title, Program Title | Text | Program element title |
| `amount_fy2024_actual` | Prior Year, PriorYAmount | Currency (thousands) | Prior year funding |
| `amount_fy2025_enacted` | Current Year, CurYAmount | Currency (thousands) | Current year funding |
| `amount_fy2026_request` | Estimate, Est Amount | Currency (thousands) | Budget estimate |
| `extra_fields.performance_metric` | Metric, Performance, Key Metric | Text | Key performance metric or milestone |
| `extra_fields.current_achievement` | Current Achievement, Achievement | Text | Current year achievement or status |
| `extra_fields.planned_achievement` | Planned Achievement, Planned | Text | Planned achievement for budget year |

### Known Variations

- R-2 often includes narrative justification sections below tabular data
- Performance metrics vary significantly by research program domain

---

## R-3 — RDT&E Project

**DB key:** `r3`  
**Description:** RDT&E project-level schedule showing development approach, schedule,
and cost estimate growth.

### Column Layout

| Field | Header Patterns | Data Type | Description |
|-------|----------------|-----------|-------------|
| `program_element` | PE | Text | Program Element number |
| `extra_fields.project_number` | Project Number, Project No | Text | Project identification |
| `line_item_title` | Project Title, Title | Text | Project title |
| `amount_fy2024_actual` | Prior Year | Currency (thousands) | Prior year amount |
| `amount_fy2025_enacted` | Current Year | Currency (thousands) | Current year amount |
| `amount_fy2026_request` | Estimate | Currency (thousands) | Budget estimate |
| `extra_fields.development_approach` | Development Approach | Text | Development approach description |
| `extra_fields.schedule_summary` | Schedule | Text | Schedule summary |

---

## R-4 — RDT&E Budget Item Justification

**DB key:** `r4`  
**Description:** Detailed justification for RDT&E budget items with technical narrative.

### Column Layout

| Field | Header Patterns | Data Type | Description |
|-------|----------------|-----------|-------------|
| `program_element` | PE | Text | Program Element number |
| `line_item` | Line Item, Item | Text | Line item identifier |
| `amount_fy2026_request` | Amount, Total | Currency (thousands) | Total amount |
| `extra_fields.narrative` | Narrative, Justification | Text | Technical narrative justification |

---

## O-1 — Operation & Maintenance

**DB key:** `o1`  
**Description:** Operation and Maintenance summary — funding for personnel, operations,
sustainment, and training activities.

### Column Layout

| Field | Header Patterns | Data Type | Description |
|-------|----------------|-----------|-------------|
| `account` | Account, ACC | Text | O&M account code |
| `account_title` | Account Title, Title | Text | O&M account title |
| `program_element` | PE, Program Element | Text | Program Element number |
| `appropriation` | Appropriation | Text | Appropriation category (O&M) |
| `budget_activity` | BA, Budget Activity | Text | Budget Activity code |
| `amount_fy2024_actual` | Prior Year, PriorYBud | Currency (thousands) | Prior year enacted |
| `amount_fy2025_enacted` | Current Year, CurYBud | Currency (thousands) | Current year enacted |
| `amount_fy2026_request` | Budget Estimate, BudEst | Currency (thousands) | President's budget estimate |

### Known Variations

- O-1 often has service-specific column headers for type-of-activity breakdowns

---

## M-1 — Military Personnel

**DB key:** `m1`  
**Description:** Military Personnel summary — funding for active duty, reserves, and
National Guard personnel pay, allowances, and benefits.

### Column Layout

| Field | Header Patterns | Data Type | Description |
|-------|----------------|-----------|-------------|
| `account` | Account, ACC | Text | Military Personnel account code |
| `account_title` | Account Title, Title | Text | Military Personnel account title |
| `appropriation` | Appropriation | Text | Appropriation category (MilPers) |
| `extra_fields.personnel_category` | Category, Personnel Category | Text | Officer, Enlisted, or other breakdown |
| `extra_fields.authorized_strength` | Authorized, Auth Strength | Integer | Authorized personnel headcount |
| `amount_fy2024_actual` | Prior Year, PriorYBud | Currency (thousands) | Prior year enacted |
| `amount_fy2025_enacted` | Current Year, CurYBud | Currency (thousands) | Current year enacted |
| `amount_fy2026_request` | Budget Estimate, BudEst | Currency (thousands) | President's budget estimate |

### Known Variations

- M-1 may include "strength" (headcount) alongside budget amounts
- Some versions separate Officer and Enlisted personnel on different rows

---

## C-1 — Military Construction

**DB key:** `c1`  
**Description:** Military Construction budget — facility projects and real property
acquisitions. Uses authorization/appropriation columns instead of the standard
request/enacted pattern.

### Column Layout

| Field | Header Patterns | Data Type | Description |
|-------|----------------|-----------|-------------|
| `account` | Account | Text | Military Construction account code |
| `extra_fields.project_number` | Project Number, Project No | Text | Project identification number |
| `line_item_title` | Project Title, Title | Text | Project name/description |
| `extra_fields.location` | Location, Installation | Text | Military installation or location |
| `extra_fields.authorization_amount` | Authorization, Auth Amount | Currency (thousands) | Authorization amount (not enacted) |
| `amount_fy2025_enacted` | Appropriation, Approp Amount | Currency (thousands) | Appropriation amount |
| `amount_fy2026_request` | Estimate, Est Amount | Currency (thousands) | Budget estimate |

### Known Variations

- C-1 uses authorization/appropriation instead of prior/current enacted pattern
- May include project duration or completion date fields

---

## RF-1 — Revolving Funds

**DB key:** `rf1`  
**Description:** Revolving Fund budget — working capital funds and enterprise funds.
Shows revenue and expenses rather than budget authority like other exhibits.

### Column Layout

| Field | Header Patterns | Data Type | Description |
|-------|----------------|-----------|-------------|
| `budget_activity` | Activity, Fund Activity | Text | Revolving fund activity code |
| `budget_activity_title` | Title, Activity Title | Text | Activity description |
| `extra_fields.prior_year_revenue` | Prior Year Revenue | Currency (thousands) | Prior year revenue/receipts |
| `extra_fields.prior_year_expenses` | Prior Year Expenses | Currency (thousands) | Prior year expenses/obligations |
| `extra_fields.current_year_revenue` | Current Year Revenue | Currency (thousands) | Current year estimated revenue |
| `extra_fields.current_year_expenses` | Current Year Expenses | Currency (thousands) | Current year estimated expenses |
| `extra_fields.estimate_revenue` | Estimate Revenue | Currency (thousands) | Budget estimate revenue |
| `extra_fields.estimate_expenses` | Estimate Expenses | Currency (thousands) | Budget estimate expenses |

### Known Variations

- RF-1 exhibits revenue and expenses rather than budget authority
- Revolving fund structure varies by fund type (working capital, service/support)

---

## Monetary Convention

- **Canonical unit:** Thousands of dollars (as stored in source documents)
- **Display toggle:** The planned UI will support toggling to millions of dollars
- **Budget cycles:** FY2024 Actual, FY2025 Enacted, FY2025 Supplemental,
  FY2025 Total, FY2026 Request, FY2026 Reconciliation, FY2026 Total

## Extra Fields

Columns not mapped to a named canonical field are stored as JSON in the `extra_fields`
column of `budget_lines`. To query an extra field:

```sql
SELECT json_extract(extra_fields, '$.justification') AS justification
FROM budget_lines
WHERE exhibit_type = 'p5' AND line_item_title LIKE '%Apache%';
```
