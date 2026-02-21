"""Backward-compatible shim -- canonical code lives in pipeline/enricher.py."""
from pipeline.enricher import *  # noqa: F401,F403

# Re-export private names used by tests
from pipeline.enricher import (  # noqa: F401,E402
    _context_window,
    _drop_enrichment_tables,
    _extract_fy_from_path,
    _tags_from_keywords,
)

if __name__ == "__main__":
    main()
