# Step 1.B2 — Standardize Column Mappings

**Status:** In Progress (1.B2-a, 1.B2-c done; 1.B2-b depends on 1.B1; 1.B2-d, 1.B2-e, 1.B2-f remain)
**Type:** Code modification + Tests
**Depends on:** 1.B1 (exhibit catalog for column specs)

## Overview

Refactor `_map_columns()` to be year-agnostic and data-driven (using
`EXHIBIT_CATALOG`), then add comprehensive tests.

---

## Sub-tasks

### 1.B2-a — Make _map_columns() year-agnostic
**Type:** AI-agent (code modification)
**Estimated tokens:** ~1000 output

1. Read `_map_columns()` in `build_budget_db.py` (~lines 284-400)
2. Replace hardcoded FY2024/2025/2026 patterns with regex: `FY\s*\d{4}`
3. Detect which fiscal year each column represents by matching patterns:
   - "Prior Year" / "PY" / "Actual" → prior year actual
   - "Current Year" / "CY" / "Enacted" → current year enacted
   - "Budget Year" / "BY" / "Request" → budget year request
4. Generate column names dynamically: `amount_fy{year}_{type}`
5. **Critical:** Maintain backward compatibility with FY2024-2026 files

**File:** `build_budget_db.py` — refactor `_map_columns()`

---

### 1.B2-b — Integrate EXHIBIT_CATALOG into _map_columns()
**Type:** AI-agent (code modification)
**Estimated tokens:** ~600 output
**Depends on:** 1.B1-f (catalog must be populated), 1.B2-a

1. Import `EXHIBIT_CATALOG` from `exhibit_catalog.py`
2. If exhibit_type is in catalog: use `column_spec` to drive mapping
3. Fall back to heuristic matching for unknown exhibit types
4. Log when falling back (helps identify gaps in catalog)

**File:** `build_budget_db.py`

---

### 1.B2-c — Handle multi-row headers
**Type:** AI-agent (code modification)
**Estimated tokens:** ~500 output

Some exhibits split headers across 2-3 rows (e.g., "FY 2026" on row 1,
"Request" on row 2):
1. After finding header row, peek at `rows[header_idx+1]`
2. If it contains header-like text (not data), merge cells vertically
3. Joined headers become the input to `_map_columns()`

**File:** `build_budget_db.py` — modify header detection in `ingest_excel_file()`

---

### 1.B2-d — Update schema for dynamic FY columns
**Type:** AI-agent (code modification)
**Estimated tokens:** ~800 output
**Depends on:** 1.B2-a

The current schema has hardcoded `amount_fy2024_actual`, etc. To support
arbitrary years:
1. Option A: Keep adding columns dynamically (ALTER TABLE)
2. Option B: Normalize — one row per (line_item, fiscal_year, amount_type)
3. Write both schemas as SQL, document pros/cons, pick one
4. If Option A: update `create_database()` to accept a year range parameter
5. Update `validate_budget_db.py` AMOUNT_COLUMNS accordingly

**File:** `build_budget_db.py`, `validate_budget_db.py`, `validate_budget_data.py`

---

### 1.B2-e — Add unit tests for _map_columns()
**Type:** AI-agent
**Estimated tokens:** ~800 output

1. Add test cases to `tests/test_parsing.py` (or new `tests/test_column_mapping.py`)
2. One test per exhibit type using sample header rows from 1.B1
3. Verify returned mapping contains expected field names
4. Test edge cases: incomplete headers, unknown columns, mixed case

**File:** `tests/test_parsing.py` or `tests/test_column_mapping.py`

---

### 1.B2-f — Refactor _map_columns() for readability
**Type:** AI-agent (refactoring)
**Estimated tokens:** ~500 output

Current function is ~110 lines with three large loops. Split into:
1. `_map_metadata_columns(headers)` → account, org, budget_activity, etc.
2. `_map_amount_columns(headers, exhibit_type)` → dollar amount columns
3. `_map_quantity_columns(headers)` → quantity columns

**File:** `build_budget_db.py`

---

## Annotations

- 1.B2-a is the highest-value change (year-agnostic = works for any FY)
- 1.B2-d is an architectural decision — recommend documenting trade-offs
- Keep backward compatibility: existing FY2024-2026 files must still parse
- The inline `get_val`/`get_str` closures (redefined per row) should be
  moved to module scope for efficiency (see build_budget_db.py line ~447)
