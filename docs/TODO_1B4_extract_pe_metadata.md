# Step 1.B4 — Extract and Normalize PE / Line-Item Metadata

**Status:** Complete
**Type:** Code modification (AI-agent completable)
**Depends on:** 1.B1 (exhibit catalog), 1.B2 (column mappings)

## Overview

Parse Program Element numbers, line-item numbers, budget activity codes, and
appropriation titles into dedicated, queryable fields.

---

## Sub-tasks

### 1.B4-a — Add program_element column and PE extraction
**Type:** AI-agent
**Estimated tokens:** ~600 output

1. Add `program_element TEXT` column to `budget_lines` schema
2. Parse PE numbers using regex `r'\d{7}[A-Z]'` from `line_item` or dedicated column
3. In R-1/R-2 exhibits: PE is typically a dedicated column
4. In other exhibits: extract from `line_item` or `account` fields
5. Add `program_element` to FTS5 index for searchability
6. Requires `--rebuild`

**File:** `build_budget_db.py` — modify schema, `ingest_excel_file()`, FTS triggers

---

### 1.B4-b — Normalize budget activity codes
**Type:** AI-agent
**Estimated tokens:** ~400 output

1. Standardize format to 2-digit string (e.g., "01", "02")
2. Strip inconsistent padding/formatting from source data
3. Add validation: warn on codes outside expected range per exhibit type

**File:** `build_budget_db.py` — modify `ingest_excel_file()`

---

### 1.B4-c — Split appropriation title from account_title
**Type:** AI-agent
**Estimated tokens:** ~500 output

The `account_title` field often contains both code and title
(e.g., "2035 Aircraft Procurement, Army"):
1. Add `appropriation_code TEXT` and `appropriation_title TEXT` columns
2. Parse: extract leading numeric code, remaining text is title
3. Handle edge cases: multi-part codes, parenthetical service names

**File:** `build_budget_db.py` — modify schema and `ingest_excel_file()`

---

### 1.B4-d — Add Space Force and Marine Corps path handling
**Type:** AI-agent
**Estimated tokens:** ~300 output

1. Update `_determine_category()` to handle "space_force" and "marine_corps" paths
2. Add these to `ORG_MAP` if not already present
3. Ensure correct organization_name assignment

**File:** `build_budget_db.py` — modify `_determine_category()` (~line 535)

---

### 1.B4-e — Update wiki Data-Dictionary with new fields
**Type:** AI-agent (documentation)
**Estimated tokens:** ~300 output
**Depends on:** 1.B4-a through 1.B4-c

Update `docs/wiki/Data-Dictionary.md` with:
- `program_element` field definition
- `appropriation_code` and `appropriation_title` field definitions
- `budget_type` field from 1.B3-d

---

## Annotations

- Schema changes require `--rebuild`
- PE numbers are critical for cross-referencing across exhibits and FYs
- DATA PROCESSING: Inspect R-1 Excel files to verify PE number format
