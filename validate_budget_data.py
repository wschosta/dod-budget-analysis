"""Backward-compatible shim -- canonical code lives in pipeline/validator.py."""
from pipeline.validator import *  # noqa: F401,F403

# Re-export private names used by tests
from pipeline.validator import (  # noqa: F401,E402
    _BASELINE_AMOUNT_COLUMNS,
    _get_amount_columns,
)

if __name__ == "__main__":
    main()
