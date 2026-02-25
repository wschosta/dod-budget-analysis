"""Backward-compatible shim -- canonical code lives in pipeline/search.py."""
from pipeline.search import main  # noqa: F401

# Re-export public API used by tests and other modules
from pipeline.search import (  # noqa: F401,E402
    search_budget_lines,
    display_budget_results,
    display_pdf_results,
    export_results,
)

# Re-export private names used by tests
from pipeline.search import (  # noqa: F401,E402
    _sanitize_fts5_query,
    _highlight_terms,
    _extract_snippet,
)

if __name__ == "__main__":
    main()
