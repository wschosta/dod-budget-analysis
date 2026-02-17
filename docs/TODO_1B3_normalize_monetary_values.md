# Step 1.B3 — Normalize Monetary Values

**Status:** Not started
**Type:** Code modification (AI-agent completable)
**Depends on:** 1.B1 (to know what units each exhibit uses)

## User Decisions (RESOLVED)

- **Canonical storage unit:** Thousands of dollars (confirmed by user)
- **Display toggle:** The search/UI layer must support a toggle to display
  values in millions of dollars (divide by 1,000). This is a display concern,
  not a storage concern — the database always stores in thousands.

## Task

Ensure all dollar amounts are stored in a consistent unit (thousands of
dollars) in the database. Add display-layer support for toggling between
thousands and millions.

## Current State

- `_safe_float()` converts values to float but does no unit normalization
- Column names like `amount_fy2026_request` don't indicate the unit
- Some exhibits may use different units (millions vs. thousands)
- No display-format toggle exists in `search_budget.py`

## Agent Instructions

### 1B3a — Storage normalization (schema + ingestion)

1. Read `_safe_float()` and the amount columns in `build_budget_db.py`
2. Add an `amount_unit` column to the `budget_lines` table schema
   (TEXT, default: "thousands") to record what unit the source used
3. In `ingest_excel_file()`, detect the source unit from the header row:
   - Look for patterns: "in thousands", "in millions", "($ thousands)",
     "($ millions)", "Thousands of Dollars", etc.
   - If "millions" detected, multiply all amount values by 1,000 before
     storing (converting to thousands)
   - Set `amount_unit` to the detected source unit for provenance
4. Preserve the BA/Appropriation/Outlay distinction: add a `budget_type`
   column (TEXT) if the exhibit provides that classification
5. Schema change — requires `--rebuild` to take effect
6. Estimated tokens: ~1000 output tokens

### 1B3b — Display toggle in search tool

1. In `search_budget.py`, add a `--unit` CLI argument:
   `--unit thousands` (default) or `--unit millions`
2. Update `_fmt_amount()` to accept a unit parameter:
   - If "millions": divide value by 1,000, format as `$X.XXM`
   - If "thousands": format as `$X,XXX` (current behavior)
3. In interactive mode, add a `unit millions` / `unit thousands` command
   to toggle display unit mid-session
4. Estimated tokens: ~600 output tokens

### 1B3c — Display toggle in GUI (future, Phase 3)

- The web UI (Phase 3) should include a toggle switch (thousands/millions)
- This is a UI concern — document the requirement but don't implement now
- Add a note in `docs/wiki/Data-Dictionary.md` about the unit convention

## Annotations

- **DATA PROCESSING:** Requires inspecting sample Excel file headers to
  verify unit detection patterns. If files are not available locally,
  implement the detection logic with the known patterns and test later.
- ~~**USER INTERVENTION:** Confirm canonical unit~~ **RESOLVED:** Thousands
  of dollars, with display toggle to millions.
- Sub-tasks 1B3a and 1B3b are independently completable
