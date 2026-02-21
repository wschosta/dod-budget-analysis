"""Backward-compatible shim -- canonical code lives in pipeline/db_validator.py."""
from pipeline.db_validator import *  # noqa: F401,F403

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
