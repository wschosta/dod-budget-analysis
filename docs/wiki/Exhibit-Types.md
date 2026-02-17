# Exhibit Types

<!-- TODO [Step 1.B1]: Expand each section with full column layouts, sample data,
     and semantic descriptions. Requires inspecting downloaded Excel files. -->

Catalog of DoD budget exhibit types and their column structures. The internal
code for each type is used in the `exhibit_type` column of the database.

---

## Summary of Known Types

| Code | Name | Description |
|------|------|-------------|
| `p1` | P-1 — Procurement | Procurement line items by appropriation and budget activity |
| `p1r` | P-1R — Procurement (Reserves) | Reserve component procurement items |
| `r1` | R-1 — RDT&E | Research, Development, Test & Evaluation program elements |
| `o1` | O-1 — Operation & Maintenance | Operation and maintenance by budget activity |
| `m1` | M-1 — Military Personnel | Military personnel funding by component |
| `c1` | C-1 — Military Construction | Military construction projects |
| `rf1` | RF-1 — Revolving Funds | Defense Working Capital Fund and similar revolving accounts |

---

## P-1 — Procurement

<!-- Column layout, typical fields, and sample rows -->

## P-1R — Procurement (Reserves)

<!-- Column layout for reserve component procurement -->

## R-1 — RDT&E

<!-- Column layout, program element structure -->

## O-1 — Operation & Maintenance

<!-- Column layout, budget activity groupings -->

## M-1 — Military Personnel

<!-- Column layout, end-strength and pay data -->

## C-1 — Military Construction

<!-- Column layout, project-level data -->

## RF-1 — Revolving Funds

<!-- Column layout, working capital fund structure -->

---

## Other Exhibit Types

<!-- TODO [Step 1.B1]: Document additional exhibit types as discovered:
     P-5 (Special Interest Items), R-2 (PE detail), R-3 (Project detail),
     R-4 (Schedule/Milestone), etc. -->

| Code | Name | Description |
|------|------|-------------|
| P-5 | Special Interest Items | _To be documented_ |
| R-2 | RDT&E PE Detail | _To be documented_ |
| R-3 | RDT&E Project Detail | _To be documented_ |
| R-4 | RDT&E Schedule/Milestone | _To be documented_ |

---

## Monetary Convention

- **Canonical unit:** Thousands of dollars (as stored in source documents)
- **Display toggle:** User can switch to millions of dollars in the UI
- **Budget cycles:** FY2024 Actual, FY2025 Enacted, FY2025 Supplemental,
  FY2025 Total, FY2026 Request, FY2026 Reconciliation, FY2026 Total
