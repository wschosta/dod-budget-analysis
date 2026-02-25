"""Backward-compatible shim -- canonical code lives in pipeline/backfill.py."""
import sys
from pipeline.backfill import main, backfill  # noqa: F401

if __name__ == "__main__":
    sys.exit(main())
