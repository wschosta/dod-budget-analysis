"""
Pipeline package -- DoD Budget Analysis data pipeline.

Re-exports key entry points so callers can do::

    from pipeline import build_database, validate_all, enrich
"""

import sys as _sys

__all__ = [
    "build_database",
    "validate_all",
    "enrich",
]

# Lazy imports to avoid RuntimeWarning when running submodules as __main__
# (e.g. `python -m pipeline.enricher`).  Eager import would cause Python to
# load enricher.py twice — once as __main__ and again as pipeline.enricher.

_LAZY_IMPORTS = {
    "build_database": ("pipeline.builder", "build_database"),
    "validate_all": ("pipeline.validator", "validate_all"),
    "enrich": ("pipeline.enricher", "enrich"),
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        if module_path in _sys.modules:
            mod = _sys.modules[module_path]
        else:
            import importlib
            mod = importlib.import_module(module_path)
        val = getattr(mod, attr)
        # Cache on the module so __getattr__ is not called again
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
