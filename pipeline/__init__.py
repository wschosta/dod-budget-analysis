"""
Pipeline package -- DoD Budget Analysis data pipeline.

Re-exports key entry points so callers can do::

    from pipeline import build_database, validate_all, enrich
"""

from pipeline.builder import build_database
from pipeline.validator import validate_all
from pipeline.enricher import enrich

__all__ = [
    "build_database",
    "validate_all",
    "enrich",
]
