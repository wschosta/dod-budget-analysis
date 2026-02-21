"""Ensure the project root is on sys.path for test modules in this sub-directory."""
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


# ── pyarrow / pandas 3.0 compatibility shim ──────────────────────────────────
# pyarrow ≥23 lazily initialises a pandas compatibility layer that expects
# pandas.__version__ and pandas.DataFrame to exist at module scope.  pandas 3.0
# moved __version__ to pandas.version.version and can trigger AttributeError
# when pyarrow's C-level shim probes for it.  Patching early prevents flaky
# test-order-dependent failures in the full test suite.
try:
    import pandas as _pd
    if not hasattr(_pd, "__version__"):
        import importlib.metadata as _meta
        _pd.__version__ = _meta.version("pandas")  # type: ignore[attr-defined]
except ImportError:
    pass
