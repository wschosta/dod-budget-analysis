"""Backward-compatible shim -- canonical code lives in pipeline/search.py."""
from pipeline.search import *  # noqa: F401,F403

# Re-export private names used by tests
from pipeline.search import (  # noqa: F401,E402
    _sanitize_fts5_query,
    _highlight_terms,
    _extract_snippet,
)

if __name__ == "__main__":
    main()
