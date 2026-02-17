# Step 1.B4 — Extract and Normalize PE / Line-Item Metadata

**Status:** Not started
**Type:** Code modification (AI-agent completable)
**Depends on:** 1.B1 (exhibit catalog), 1.B2 (column mappings)

## Task

Parse Program Element (PE) numbers, line-item numbers, budget activity codes,
appropriation titles, and sub-activity groups into dedicated, queryable fields.

## Current State

- `build_budget_db.py` already extracts `line_item`, `budget_activity`,
  `sub_activity` as raw strings
- PE numbers are not explicitly parsed (they may appear in line_item or
  account fields depending on exhibit type)
- No normalization of PE format (e.g., "0602702E" vs "062702E")

## Agent Instructions

1. Read the current extraction logic in `ingest_excel_file()` and `_map_columns()`
2. Add a `program_element` column to the `budget_lines` schema
3. Parse PE numbers from the appropriate column(s) — typically the `line_item`
   or a dedicated PE column in R-1/R-2 exhibits
4. Normalize PE format: strip leading zeros, standardize to 7-character format
   where applicable
5. Add `program_element` to the FTS5 index for searchability
6. Estimated tokens: ~1000 output tokens

## Annotations

- **DATA PROCESSING:** Requires understanding PE number format from real data.
  Inspect a few R-1 Excel files to see how PEs appear.
- Schema change — requires `--rebuild`
- PE numbers are the primary key for cross-referencing budget data across
  exhibits and fiscal years, so getting this right is critical for Phase 2
