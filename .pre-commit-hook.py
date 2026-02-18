#!/usr/bin/env python
"""
Pre-commit hook for optimization tests

Ensures that optimization tests pass before committing.
Install with:
    cp .pre-commit-hook.py .git/hooks/pre-commit
    chmod +x .git/hooks/pre-commit

Or use with pre-commit framework:
    pip install pre-commit
    pre-commit install
"""

import subprocess
import sys


def run_optimization_tests():
    """Run optimization tests before commit."""
    print("Running optimization tests...")
    result = subprocess.run(
        [sys.executable, "run_optimization_tests.py", "--verbose"],
        cwd=".",
    )

    if result.returncode != 0:
        print("\n[FAILED] Optimization tests failed.")
        print("Please fix the issues before committing.")
        return False

    print("\n[PASSED] All optimization tests passed.")
    return True


def check_imports():
    """Verify all modules import without errors."""
    print("\nVerifying module imports...")
    try:
        import dod_budget_downloader
        import search_budget
        import validate_budget_db
        import build_budget_db

        print("[PASSED] All modules import successfully.")
        return True
    except Exception as e:
        print(f"\n[FAILED] Import error: {e}")
        return False


def main():
    print("=" * 70)
    print("PRE-COMMIT HOOK: Optimization Tests")
    print("=" * 70)

    # Run checks
    tests_pass = run_optimization_tests()
    imports_pass = check_imports()

    if tests_pass and imports_pass:
        print("\n" + "=" * 70)
        print("All pre-commit checks passed. Proceeding with commit.")
        print("=" * 70)
        return 0
    else:
        print("\n" + "=" * 70)
        print("Pre-commit checks failed. Please fix errors before committing.")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
