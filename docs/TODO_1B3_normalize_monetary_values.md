# Step 1.B3 — Normalize Monetary Values

**Status:** Not started
**Type:** Code modification (AI-agent completable)
**Depends on:** 1.B1 (to know what units each exhibit uses)

## Task

Ensure all dollar amounts use a consistent unit (thousands of dollars) and
that the distinction between Budget Authority (BA), Appropriations, and
Outlays is preserved.

## Current State

- `_safe_float()` converts values to float but does no unit normalization
- Column names like `amount_fy2026_request` don't indicate the unit
- Some exhibits may use different units (millions vs. thousands)

## Agent Instructions

1. Read `_safe_float()` and the amount columns in `build_budget_db.py`
2. Research: check a few sample Excel files to determine what unit each
   exhibit type uses (most DoD exhibits are in thousands of dollars, but
   verify)
3. Add a `unit` or `amount_unit` column to the `budget_lines` table schema
   (default: "thousands")
4. In `ingest_excel_file()`, detect the unit from the header row (look for
   "in thousands", "in millions", etc.) and normalize to thousands
5. Add the BA/Appropriation/Outlay distinction as a `budget_type` column
   if the exhibit provides that classification
6. Estimated tokens: ~1200 output tokens

## Annotations

- **DATA PROCESSING:** Requires inspecting sample Excel file headers to
  determine units. If files are not available locally, document the detection
  logic and defer testing.
- **USER INTERVENTION:** Confirm the canonical unit (thousands of dollars is
  standard for DoD budget exhibits, but user should verify)
- This is a schema change — will require `--rebuild` to take effect on
  existing databases
