# Step 1.B6 — Build Validation Suite

**Status:** Complete
**Type:** Code creation (AI-agent completable)
**Depends on:** 1.B2 (column mappings), 1.B3 (normalized values)

## Task

Create automated checks that flag anomalies in ingested data: missing fiscal
years, duplicate rows, zero-sum line items, column misalignment, and
unexpected exhibit formats.

## Agent Instructions

1. Create `validate_budget_db.py` in the project root with:
   - `check_missing_years(conn)` — for each service, verify all expected FYs present
   - `check_duplicates(conn)` — find rows with identical (source_file, exhibit_type,
     account, line_item, fiscal_year) tuples
   - `check_zero_amounts(conn)` — find line items where all amount columns are 0 or NULL
   - `check_column_alignment(conn)` — find rows where account is populated but
     organization is NULL (suggests misaligned columns)
   - `check_unknown_exhibits(conn)` — find exhibit_type values not in EXHIBIT_TYPES
   - `generate_report(conn)` — run all checks, print a summary report
2. Make it runnable as CLI: `python validate_budget_db.py [--db path]`
3. Each check should return a list of issues with enough detail to investigate
4. Estimated tokens: ~1500 output tokens

## Annotations

- This is a new file, not a modification of existing code
- Can be implemented with only knowledge of the database schema (from
  `build_budget_db.py`'s `create_database()` function)
- Does not require downloaded files — operates on the SQLite database
- If the database doesn't exist yet, the script should exit with a helpful message
