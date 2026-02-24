"""Backward-compatible shim -- canonical code lives in pipeline/enricher.py."""
from pipeline.enricher import *  # noqa: F401,F403

# Re-export private names used by tests
from pipeline.enricher import (  # noqa: F401,E402
    _context_window,
    _drop_enrichment_tables,
    _ensure_checkpoint_table,
    _extract_fy_from_path,
    _get_checkpoint,
    _MAX_NAME_MATCHES_PER_ROW,
    _MAX_PE_REFS_FOR_NAME_MATCH,
    _MIN_TEXT_FOR_NAME_MATCH,
    _MIN_TITLE_WORDS,
    _save_checkpoint,
    _tags_from_keywords,
)

if __name__ == "__main__":
    main()
