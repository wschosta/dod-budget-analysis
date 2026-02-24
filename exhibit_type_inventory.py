"""Backward-compatible shim -- canonical code lives in pipeline/exhibit_inventory.py."""
from pipeline.exhibit_inventory import *  # noqa: F401,F403

if __name__ == "__main__":
    main()
