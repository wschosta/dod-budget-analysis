"""Backward-compatible shim -- canonical code lives in pipeline/gui.py."""
from pipeline.gui import main  # noqa: F401

# Re-export private names used by tests
from pipeline.gui import _fmt_eta  # noqa: F401,E402

if __name__ == "__main__":
    main()
