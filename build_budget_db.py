"""Backward-compatible shim -- canonical code lives in pipeline/builder.py."""
from pipeline.builder import *  # noqa: F401,F403

# Re-export private names used by tests and scripts
from pipeline.builder import (  # noqa: F401,E402
    _PE_PATTERN,
    _SCHEMA_VERSION,
    _create_session_id,
    _detect_amount_unit,
    _detect_currency_year,
    _detect_exhibit_type,
    _detect_pdf_exhibit_type,
    _determine_category,
    _ensure_fy_columns,
    _extract_all_pe_numbers,
    _extract_fy_from_path,
    _extract_pdf_data,
    _extract_pe_number,
    _extract_table_text,
    _extract_tables_with_timeout,
    _file_needs_update,
    _get_last_checkpoint,
    _get_processed_files,
    _likely_has_tables,
    _map_columns,
    _mark_file_processed,
    _mark_session_complete,
    _merge_header_rows,
    _normalise_fiscal_year,
    _parse_appropriation,
    _recreate_pdf_fts_triggers,
    _register_data_source,
    _remove_file_data,
    _safe_float,
    _save_checkpoint,
)

if __name__ == "__main__":
    main()
