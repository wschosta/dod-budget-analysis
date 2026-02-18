# Exhibit Types

Catalog of DoD budget exhibit types and their column structures. The internal
code for each type is used in the `exhibit_type` column of the database.

> **Source of truth:** [`exhibit_catalog.py`](../../exhibit_catalog.py) — full column specs
> and helper functions. Run `scripts/exhibit_audit.py` against downloaded files to verify.

---

## Summary of Known Types

| Code | Name | Category | Columns |
|------|------|----------|---------|
| `p1` | P-1 — Procurement | Summary | account, org, budget_activity, line_item, amounts |
| `p1r` | P-1R — Procurement (Reserves) | Summary | same as P-1 |
| `r1` | R-1 — RDT&E | Summary | account, org, budget_activity, PE/BLI, amounts |
| `o1` | O-1 — Operation & Maintenance | Summary | account, org, budget_activity, BSA, amounts |
| `m1` | M-1 — Military Personnel | Summary | account, org, budget_activity, BSA, amounts |
| `c1` | C-1 — Military Construction | Summary | account, construction project, auth/approp amounts |
| `rf1` | RF-1 — Revolving Funds | Summary | account, org, budget_activity, line_item, amounts |
| `p5` | P-5 — Procurement Detail | Detail | program element, line item, qty, unit cost |
| `r2` | R-2 — RDT&E PE Detail | Detail | PE, sub-element, amounts, metrics |
| `r3` | R-3 — RDT&E Project Schedule | Detail | PE, project, amounts, schedule |
| `r4` | R-4 — RDT&E Justification | Detail | PE, line item, amount, narrative |

---

## Summary Exhibits

### P-1 — Procurement

**Description:** Summary procurement exhibit — funding requests for procurement of
weapons systems, vehicles, and equipment.

**Canonical column names** (from `_map_columns()`):

| Field | Source Header | Type |
|-------|--------------|------|
| `account` | `Account` | text |
| `account_title` | `Account Title` | text |
| `organization` | `Organization` | text |
| `budget_activity` | `Budget Activity` | text |
| `budget_activity_title` | `Budget Activity Title` | text |
| `line_item` | `Budget Line Item` | text |
| `line_item_title` | `Budget Line Item (BLI) Title` | text |
| `pe_number` | extracted from line_item | text |
| `amount_fyYYYY_actual` | `FY{YYYY} Actual Amount` | real (thousands) |
| `amount_fyYYYY_enacted` | `FY{YYYY} Enacted Amount` | real (thousands) |
| `amount_fyYYYY_request` | `FY{YYYY} Request Amount` | real (thousands) |
| `amount_fyYYYY_total` | `FY{YYYY} Total Amount` | real (thousands) |

**Known variations:**
- Navy/USMC may use `PE/BLI` instead of `Budget Line Item`
- Army sometimes includes `SLI` (Sub-Line Item) designation

---

### P-1R — Procurement (Reserves)

**Description:** Reserve component procurement — same structure as P-1.

Column mapping is identical to P-1 (shared `_map_columns()` heuristics).

---

### R-1 — RDT&E

**Description:** Research, Development, Test & Evaluation — funding for military
technology development programs.

**Canonical column names:**

| Field | Source Header | Type |
|-------|--------------|------|
| `account` | `Account` | text |
| `account_title` | `Account Title` | text |
| `organization` | `Organization` | text |
| `budget_activity` | `Budget Activity` | text |
| `budget_activity_title` | `Budget Activity Title` | text |
| `line_item` | `PE/BLI` | text |
| `line_item_title` | `Program Element/Budget Line Item (BLI) Title` | text |
| `pe_number` | extracted from line_item | text |
| `amount_fyYYYY_*` | `FY{YYYY} {Type} Amount` | real (thousands) |

**Known variations:**
- Budget activity codes follow DoD RDT&E taxonomy (6.1=Basic Research, 6.2=Applied, etc.)

---

### O-1 — Operation & Maintenance

**Description:** Operation and maintenance funding — personnel operations, sustainment, training.

**Canonical column names:**

| Field | Source Header | Type |
|-------|--------------|------|
| `account` | `Account` | text |
| `account_title` | `Account Title` | text |
| `organization` | `Organization` | text |
| `budget_activity` | `Budget Activity` | text |
| `budget_activity_title` | `Budget Activity Title` | text |
| `sub_activity` | `BSA` or `AG/BSA` | text |
| `sub_activity_title` | `Budget SubActivity Title` | text |
| `amount_fyYYYY_*` | `FY{YYYY} {Type} Amount` | real (thousands) |

---

### M-1 — Military Personnel

**Description:** Military personnel funding — active duty, reserves, National Guard pay.

Same column layout as O-1 (uses BSA/sub-activity structure).

---

### C-1 — Military Construction

**Description:** Military construction projects — facility construction and real property.

**Canonical column names:**

| Field | Source Header | Type |
|-------|--------------|------|
| `account` | `Account` | text |
| `account_title` | `Account Title` | text |
| `line_item` | `Construction Project` | text |
| `line_item_title` | `Construction Project Title` | text |
| `sub_activity` | `Location Title` | text |
| `sub_activity_title` | `Facility Category Title` | text |
| `amount_fyYYYY_request` | `Authorization Amount` | real (thousands) |
| `amount_fyYYYY_enacted` | `Appropriation Amount` | real (thousands) |
| `amount_fyYYYY_total` | `Total Obligation Authority` | real (thousands) |

**Note:** C-1 uses authorization/appropriation semantics, not enacted/request.

---

### RF-1 — Revolving Funds

**Description:** Defense Working Capital Fund and similar revolving accounts.

Same column structure as P-1 (Budget Line Item layout).

---

## Detail Exhibits

Detail exhibits are line-item breakdowns nested within summary exhibits.
They are typically attached to specific program elements and include
narrative justification columns not present in summary exhibits.

### P-5 — Procurement Detail

Per-item quantity and unit cost breakdowns for procurement line items.

Key columns: `program_element`, `line_item_number`, `line_item_title`,
`unit`, `prior_year_qty`, `prior_year_unit_cost`, `estimate_qty`,
`estimate_unit_cost`, `justification`

### R-2 — RDT&E PE Detail Schedule

Research program milestones and performance metrics.

Key columns: `program_element`, `sub_element`, `title`, year amounts,
`performance_metric`, `current_achievement`, `planned_achievement`

### R-3 — RDT&E Project Schedule

Development schedules with cost estimates.

Key columns: `program_element`, `project_number`, `project_title`, year amounts,
`development_approach`, `schedule_summary`

### R-4 — RDT&E Budget Item Justification

Detailed technical narrative justification.

Key columns: `program_element`, `line_item`, `amount`, `narrative`

---

## Monetary Convention

- **Canonical storage unit:** Thousands of dollars
- **Auto-detection:** `_detect_amount_unit()` scans title rows for "in millions" or "in thousands" keywords before parsing
- **Unit multiplier:** Millions-denominated files are multiplied by 1000 during ingestion
- **Display toggle:** `--unit millions` flag in `search_budget.py` divides by 1000 for display
- **Fiscal year columns:** Dynamically detected via regex `FY\s*(\d{4})` — works for any year
- **Column naming:** `amount_fyYYYY_actual`, `amount_fyYYYY_enacted`, `amount_fyYYYY_request`, etc.

---

## Audit Tool

Run `scripts/exhibit_audit.py` against downloaded files to verify that the catalog
matches actual header rows:

```bash
python scripts/exhibit_audit.py
# Output: docs/exhibit_audit_report.md
```

See [DATA_SOURCES.md](../../DATA_SOURCES.md) for how to download budget files.
