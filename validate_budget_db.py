"""Backward-compatible shim -- canonical code lives in pipeline/db_validator.py."""
from pipeline.db_validator import main  # noqa: F401

# Re-export public API (check functions) used by tests
from pipeline.db_validator import (  # noqa: F401,E402
    check_appropriation_title_consistency,
    check_budget_activity_consistency,
    check_budget_type_values,
    check_column_alignment,
    check_duplicate_budget_lines,
    check_duplicates,
    check_empty_files,
    check_enrichment_orphans,
    check_enrichment_staleness,
    check_expected_fy_columns,
    check_expected_indexes,
    check_extreme_outliers,
    check_fy_column_null_rates,
    check_ingestion_errors,
    check_integrity,
    check_line_item_rollups,
    check_missing_years,
    check_negative_amounts,
    check_pdf_extraction_quality,
    check_pdf_pages_fiscal_year,
    check_pdf_pe_numbers_populated,
    check_pe_number_format,
    check_pe_org_consistency,
    check_pe_tags_source_files,
    check_referential_integrity,
    check_source_file_tracking,
    check_unit_consistency,
    check_unknown_exhibits,
    check_yoy_budget_anomalies,
    check_zero_amounts,
    generate_html_report,
    generate_json_report,
    generate_report,
)

# Re-export private names used by tests
from pipeline.db_validator import (  # noqa: F401,E402
    _HTML_TEMPLATE,
    _KNOWN_BUDGET_TYPES,
    _PE_PATTERN,
    _SEVERITY_COLORS,
    _SEVERITY_LEVELS,
    _exceeds_threshold,
    _get_amount_columns,
    _table_exists,
)

if __name__ == "__main__":
    main()
