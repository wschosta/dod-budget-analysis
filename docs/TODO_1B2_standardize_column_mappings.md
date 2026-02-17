# Step 1.B2 — Standardize Column Mappings

**Status:** Not started
**Type:** Code modification + Tests (AI-agent completable)
**Depends on:** 1.B1 (exhibit type catalog)

## Task

Extend `_map_columns()` in `build_budget_db.py` to handle all known exhibit
formats consistently. Add unit tests for each exhibit type with sample data.

## Current State

`_map_columns()` handles common fields (account, organization, budget_activity)
and several amount column patterns. It is hardcoded to FY2024-2026 column names.

## Known Issues

- Column names are hardcoded to specific fiscal years (FY2024/2025/2026) —
  will break for other years
- Some exhibit types have columns not yet mapped
- No unit tests exist for the mapping logic

## Agent Instructions

1. Read `_map_columns()` in `build_budget_db.py` (lines ~197-308)
2. Refactor the FY-specific column matching to be year-agnostic:
   - Match patterns like `FY\d{4}` instead of literal `fy2024`
   - Use the matched year to determine column semantics (prior year actual,
     current year enacted, budget year request)
3. Using the exhibit catalog from 1.B1, add mapping rules for any unmapped
   column patterns
4. Create `tests/test_column_mapping.py` with test cases:
   - One test per exhibit type using sample header rows
   - Verify the returned mapping dict contains expected fields
5. Estimated tokens: ~2000 output tokens

## Annotations

- **DATA PROCESSING:** Needs sample header rows from real Excel files (from 1.B1)
- The year-agnostic refactor is the highest-value change — it makes the tool
  work for any fiscal year without code changes
- Keep backward compatibility: existing FY2024-2026 files must still parse correctly
