# Step 1.C1 — Create Representative Test Fixtures

**Status:** Not started
**Type:** Data preparation (needs environment + user intervention)
**Depends on:** Downloaded budget documents must exist locally

## Task

Assemble a small set of real Excel and PDF files covering each exhibit type
and each service to use in automated tests.

## Agent Instructions

1. From the `DoD_Budget_Documents/` directory, select one representative file
   per (exhibit_type x service) combination
2. Copy each to `tests/fixtures/` with a descriptive name:
   - `tests/fixtures/army_p1_fy2026.xlsx`
   - `tests/fixtures/navy_r1_fy2026.xlsx`
   - `tests/fixtures/comptroller_summary_fy2026.pdf`
   - etc.
3. For each fixture, create a `tests/fixtures/expected/` directory with:
   - A JSON file documenting expected parse results (row count, key field values)
   - This serves as the "golden" output for regression tests
4. Keep the fixture set small (10-15 files, <50 MB total) so tests run fast
5. Estimated tokens: ~1000 output tokens (mostly file operations)

## Annotations

- **DATA PROCESSING:** Requires `DoD_Budget_Documents/` to be populated
- **USER INTERVENTION:** User should review selected fixtures to ensure they
  are representative and do not contain sensitive data (all DoD budget docs
  are public domain, but verify)
- **TOKEN EFFICIENCY:** Don't read file contents into context. Use file
  operations (copy, stat) and short Python scripts to extract expected values.
- If documents are not yet downloaded, create the directory structure and a
  `README.md` in `tests/fixtures/` explaining what goes there
