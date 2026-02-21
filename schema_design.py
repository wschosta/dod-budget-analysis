"""Backward-compatible shim -- canonical code lives in pipeline/schema.py."""
from pipeline.schema import *  # noqa: F401,F403

# Re-export private names used by tests and scripts
from pipeline.schema import (  # noqa: F401,E402
    _current_version,
    _DDL_001_CORE,
    _DDL_001_SEEDS,
    _MIGRATIONS,
    _DDL_SCHEMA_VERSION,
    _DDL_001_DOCS,
    _DDL_003_FY2027,
    _DDL_003_FY2027_MAP,
    _DDL_COMPAT_VIEW,
    _apply_fy2027_migration,
)
