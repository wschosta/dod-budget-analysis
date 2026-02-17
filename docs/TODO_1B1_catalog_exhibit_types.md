# Step 1.B1 — Catalog All Exhibit Types

**Status:** Not started
**Type:** Research + Documentation (partially AI-agent completable)
**Depends on:** Downloaded budget documents must exist locally

## Task

Enumerate every exhibit type encountered in the downloaded Excel and PDF files.
Document the column layout and semantics for each.

## Current State

`build_budget_db.py` defines `EXHIBIT_TYPES` with 7 types:
- m1 (Military Personnel), o1 (O&M), p1 (Procurement), p1r (Procurement Reserves),
  r1 (RDT&E), rf1 (Revolving Funds), c1 (Military Construction)

Additional types known to exist but not yet cataloged:
- P-5, R-2, R-3, R-4 (detailed program-level exhibits)
- Possibly others in service-specific documents

## Agent Instructions

1. Glob for all `.xlsx` files under `DoD_Budget_Documents/`
2. For each unique filename pattern, open with `openpyxl` (read_only) and
   record: sheet names, header row content (first 5 rows), and column count
3. Group files by exhibit type (detected from filename)
4. For each exhibit type, document:
   - Column headers (standardized names)
   - Which columns contain dollar amounts vs. metadata vs. quantities
   - Any columns unique to that exhibit type
5. Update `docs/wiki/Exhibit-Types.md` with the catalog
6. Estimated tokens: ~2500 output tokens

## Annotations

- **DATA PROCESSING:** Requires reading Excel file headers from the downloaded
  documents directory. If `DoD_Budget_Documents/` is not populated, this task
  must wait until downloads are complete.
- **TOKEN EFFICIENCY:** Rather than reading full files, only read the first 5
  rows of each sheet to capture headers. Use `openpyxl` read_only mode.
- For a future session: `python -c "import openpyxl; ..."` one-liner to extract
  headers from a sample file, then generalize.
