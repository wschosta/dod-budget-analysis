"""
Budget Data Validation Suite — Step 1.B6

Automated checks that run against a populated dod_budget.sqlite database and
flag anomalies.  Designed to run after every build_budget_db.py invocation
(or as a standalone QA step).

Usage (planned):
    python validate_budget_data.py                      # Validate default DB
    python validate_budget_data.py --db path/to/db      # Custom DB path
    python validate_budget_data.py --strict              # Non-zero exit on warnings

──────────────────────────────────────────────────────────────────────────────
TODOs — each is an independent validation check unless noted otherwise
──────────────────────────────────────────────────────────────────────────────

TODO 1.B6-a: Check for missing fiscal-year coverage per service.
    Query budget_lines grouped by (organization_name, fiscal_year).  Flag any
    service that has data for FY X but not FY X-1 or X+1 within the expected
    range.  Output: list of (service, missing_fy) pairs.
    Standalone function, ~20 lines.

TODO 1.B6-b: Detect duplicate rows.
    Query for rows that share the same (source_file, exhibit_type, account,
    organization, budget_activity, line_item, fiscal_year).  These likely
    indicate a parsing bug (e.g., ingesting the same sheet twice).
    Standalone function, ~15 lines.

TODO 1.B6-c: Flag zero-sum or null-heavy line items.
    Identify budget_lines where ALL amount columns are NULL or zero.  These
    are either header/separator rows that leaked through or genuine zero-budget
    items.  Report count per exhibit type so we can decide whether to filter
    them during ingestion.

TODO 1.B6-d: Detect column misalignment.
    Heuristic: if a text column (e.g., account_title) contains only numeric
    values, or a numeric column (e.g., amount_fy2026_request) contains text,
    the column mapping is likely wrong for that file.  Query a sample from each
    source_file and check types.

TODO 1.B6-e: Flag unexpected exhibit types.
    Compare the set of exhibit_type values in budget_lines against the known
    set in exhibit_catalog.EXHIBIT_CATALOG.  Anything labeled "unknown" or
    not in the catalog needs investigation.

TODO 1.B6-f: Validate monetary value ranges.
    Flag budget_lines where any amount column has an absolute value > 1 trillion
    (in thousands) or is negative when it shouldn't be.  Large outliers often
    indicate unit-of-measure mismatches (whole dollars ingested as thousands).

TODO 1.B6-g: Cross-check row counts against ingested_files.
    For each entry in ingested_files, verify that the row_count matches the
    actual count in budget_lines/pdf_pages for that source_file.  Mismatches
    indicate a partial or failed ingestion that didn't get properly recorded.

TODO 1.B6-h: Wire validation into build_budget_db.py.
    After the build pipeline finishes, call the validation checks and log
    results.  In --strict mode, exit non-zero if any warnings are found.
    This is integration work — do after the individual checks above are done.

TODO 1.B6-i: Generate a validation summary report (text or JSON).
    Aggregate all check results into a structured report with pass/warn/fail
    counts and details.  Write to validation_report.json so CI can consume it.
"""

import sqlite3
from pathlib import Path


DEFAULT_DB_PATH = Path("dod_budget.sqlite")


def validate_all(db_path: Path = DEFAULT_DB_PATH, strict: bool = False) -> dict:
    """Run all validation checks and return a summary dict.

    Returns:
        {
            "checks": [
                {"name": "missing_fy_coverage", "status": "pass"|"warn"|"fail",
                 "details": [...]},
                ...
            ],
            "total_warnings": int,
            "total_failures": int,
        }
    """
    # TODO: implement — call each check function, collect results
    raise NotImplementedError("Validation checks not yet implemented — see TODOs above")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Validate budget database")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    validate_all(args.db, strict=args.strict)
