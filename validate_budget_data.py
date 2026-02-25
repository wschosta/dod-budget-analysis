"""Backward-compatible shim -- canonical code lives in pipeline/validator.py."""
from pipeline.validator import main  # noqa: F401

# Re-export public API used by tests
from pipeline.validator import (  # noqa: F401,E402
    check_database_stats,
    check_duplicate_rows,
    check_null_heavy_rows,
    check_unknown_exhibit_types,
    check_value_ranges,
    check_row_count_consistency,
    check_fiscal_year_coverage,
    check_column_types,
    validate_all,
    generate_quality_report,
)

# Re-export private names used by tests
from pipeline.validator import (  # noqa: F401,E402
    _BASELINE_AMOUNT_COLUMNS,
    _get_amount_columns,
)

if __name__ == "__main__":
    main()
