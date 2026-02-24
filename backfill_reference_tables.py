"""Backward-compatible shim -- canonical code lives in pipeline/backfill.py."""
import sys
from pipeline.backfill import *  # noqa: F401,F403

if __name__ == "__main__":
    sys.exit(main())
