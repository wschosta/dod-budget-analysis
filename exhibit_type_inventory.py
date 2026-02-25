"""Backward-compatible shim -- canonical code lives in pipeline/exhibit_inventory.py."""
from pipeline.exhibit_inventory import main  # noqa: F401

# Re-export public names used by tests
from pipeline.exhibit_inventory import ExhibitInventory  # noqa: F401,E402

if __name__ == "__main__":
    main()
