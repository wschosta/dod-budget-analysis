# Test Fixtures

<!-- TODO [Step 1.C1]: Populate this directory with representative test files. -->

This directory holds sample Excel and PDF files used by the automated test suite.

## Expected Contents

Once populated (Step 1.C1), this directory should contain:

- One representative `.xlsx` file per (exhibit_type x service) combination
- A few representative `.pdf` files from different sources
- An `expected/` subdirectory with JSON files documenting expected parse output

## Naming Convention

```
{service}_{exhibit_type}_fy{year}.xlsx
{service}_{description}_fy{year}.pdf
```

Examples:
- `army_p1_fy2026.xlsx`
- `navy_r1_fy2026.xlsx`
- `comptroller_summary_fy2026.pdf`

## How to Populate

1. Run the downloader to fetch budget documents
2. Select one file per category from `DoD_Budget_Documents/`
3. Copy to this directory with the naming convention above
4. Run `python scripts/generate_expected_output.py` (to be created) to
   produce the expected JSON files

## Size Target

Keep this directory under 50 MB so tests remain fast.
