"""Backward-compatible shim -- canonical code lives in pipeline/refresh.py."""
from pipeline.refresh import *  # noqa: F401,F403

# Re-export private names used by tests
from pipeline.refresh import (  # noqa: F401,E402
    _SCHEDULE_INTERVALS,
    _next_run_time,
    _PROGRESS_FILE,
)

if __name__ == "__main__":
    main()
