# Step 1.B1 — Catalog All Exhibit Types

**Status:** Not started
**Type:** Research + Documentation (DATA PROCESSING required)
**Depends on:** Downloaded budget documents in `DoD_Budget_Documents/`

## Overview

Enumerate every exhibit type in downloaded Excel/PDF files and document
column layouts and semantics for each. Populate `exhibit_catalog.py`.

---

## Sub-tasks

### 1.B1-a — Inventory all exhibit types from downloaded files
**Type:** ENVIRONMENT TESTING + script creation
**Estimated tokens:** ~600 output

1. Write `scripts/exhibit_audit.py` (~50 lines) that:
   - Walks `DoD_Budget_Documents/` for all `.xlsx` files
   - Opens each with `openpyxl` (read_only), reads sheet names + first 5 rows
   - Groups by detected exhibit type (via `_detect_exhibit_type()`)
   - Emits report: unique (exhibit_type, sheet_pattern, header_signature) tuples
2. Save output to `docs/exhibit_audit_report.md`

**Token-efficient tip:** Only read header rows, not full files.

---

### 1.B1-b — Document summary exhibit layouts (P-1, R-1, O-1, M-1)
**Type:** AI-agent + DATA PROCESSING
**Estimated tokens:** ~800 output
**Depends on:** 1.B1-a

For each summary exhibit:
1. Record column headers, positions, data types (text/currency/quantity)
2. Note FY associations and cross-service variations
3. Store as structured dict in `exhibit_catalog.py` → `EXHIBIT_CATALOG`
4. Update `docs/wiki/Exhibit-Types.md` with findings

---

### 1.B1-c — Document detail exhibit layouts (P-5, R-2, R-3, R-4)
**Type:** AI-agent + DATA PROCESSING
**Estimated tokens:** ~800 output
**Depends on:** 1.B1-a

Same structure as 1.B1-b for detail exhibits (deeper line-item breakdowns,
narrative justification columns).

---

### 1.B1-d — Document C-1 and RF-1 layouts
**Type:** AI-agent + DATA PROCESSING
**Estimated tokens:** ~500 output

C-1 has authorization/appropriation columns (not standard request/enacted).
RF-1 has unique revenue/expense columns. Document separately.

---

### 1.B1-e — Document unusual/remaining exhibit types
**Type:** AI-agent + DATA PROCESSING
**Estimated tokens:** ~400 output
**Depends on:** 1.B1-a

For any types found by the audit not covered in b/c/d (J-Books, amendments,
supplementals): document column layouts.

---

### 1.B1-f — Build EXHIBIT_CATALOG dict
**Type:** AI-agent
**Estimated tokens:** ~600 output
**Depends on:** 1.B1-b through 1.B1-e

Populate `exhibit_catalog.py` with:
```python
EXHIBIT_CATALOG = {
    "p1": {"name": ..., "description": ..., "column_spec": [...], "known_variations": [...]},
    ...
}
```
Export so `build_budget_db.py` can import for `_map_columns()`.

---

### 1.B1-g — Update wiki Exhibit-Types page
**Type:** AI-agent (documentation)
**Estimated tokens:** ~400 output
**Depends on:** 1.B1-f

Update `docs/wiki/Exhibit-Types.md` with full catalog from `EXHIBIT_CATALOG`.

---

## Annotations

- All sub-tasks except 1.B1-f and 1.B1-g require downloaded Excel files
- 1.B1-a is the discovery step — everything else depends on its output
- TOKEN EFFICIENCY: Only read first 5 rows per sheet with openpyxl read_only
