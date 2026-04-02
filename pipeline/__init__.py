"""
Pipeline package -- DoD Budget Analysis data pipeline.

Re-exports key entry points so callers can do::

    from pipeline import build_database, validate_all, enrich
"""

# TODO [TODO-L2]: Eager imports cause RuntimeWarning when running
# `python -m pipeline.enricher`. Guard with sys.modules check or use lazy imports.
from pipeline.builder import build_database
from pipeline.validator import validate_all
from pipeline.enricher import enrich

__all__ = [
    "build_database",
    "validate_all",
    "enrich",
]
