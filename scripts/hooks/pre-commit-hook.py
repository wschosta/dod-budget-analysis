#!/usr/bin/env python
# TODO [Group: BEAR] BEAR-012: Update pre-commit hook for new file location + CONTRIBUTING.md reference (~1,000 tokens)
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

import ast
import re
import sqlite3
import subprocess
import sys
from pathlib import Path


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


def check_syntax():
    """Verify all Python files have valid syntax."""
    print("\nChecking Python syntax...")
    errors = []
    root = Path(".")

    for py_file in root.glob("*.py"):
        if py_file.name.startswith("test_"):
            continue

        try:
            with open(py_file) as f:
                ast.parse(f.read())
        except SyntaxError as e:
            errors.append(f"{py_file.name}:{e.lineno}: {e.msg}")

    if errors:
        print("[FAILED] Syntax errors found:")
        for error in errors:
            print(f"  {error}")
        return False

    print("[PASSED] All Python files have valid syntax.")
    return True


def check_code_quality():
    """Check for common code quality issues."""
    print("\nChecking code quality...")
    errors = []
    root = Path(".")

    # Check for debug statements
    debug_patterns = [
        (r"\bbreakpoint\(\)", "breakpoint() statement"),
        (r"\bpdb\.set_trace\(\)", "pdb.set_trace() statement"),
    ]

    for py_file in root.glob("*.py"):
        if (py_file.name.startswith("test_")
                or "check" in py_file.name
                or py_file.name.startswith(".pre-commit")):
            continue
        # Skip pre-commit scripts themselves (they contain these patterns in string literals)
        if "precommit" in py_file.name or py_file.name.startswith(".pre-commit"):
            continue

        with open(py_file) as f:
            for i, line in enumerate(f, 1):
                for pattern, desc in debug_patterns:
                    if re.search(pattern, line):
                        errors.append(f"{py_file.name}:{i}: {desc} found")

    if errors:
        print("[FAILED] Code quality issues found:")
        for error in errors:
            print(f"  {error}")
        return False

    print("[PASSED] No debug statements found.")
    return True


def check_security():
    """Check for potential security issues."""
    print("\nChecking for security issues...")
    errors = []
    root = Path(".")

    secret_patterns = [
        (r"password\s*=\s*['\"](?!.*\$|.*\{)[^'\"]+['\"]", "hardcoded password"),
        (r"api[_-]?key\s*=\s*['\"](?!.*\$|.*\{)[^'\"]+['\"]", "hardcoded API key"),
        (r"secret\s*=\s*['\"](?!.*\$|.*\{)[^'\"]+['\"]", "hardcoded secret"),
    ]

    for py_file in root.glob("*.py"):
        if py_file.name.startswith("test_"):
            continue

        with open(py_file) as f:
            for i, line in enumerate(f, 1):
                if line.strip().startswith("#"):
                    continue

                for pattern, desc in secret_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        errors.append(f"{py_file.name}:{i}: {desc}")

    if errors:
        print("[FAILED] Security issues found:")
        for error in errors:
            print(f"  {error}")
        return False

    print("[PASSED] No hardcoded secrets detected.")
    return True


def check_database_schema():
    """Validate database schema if it exists."""
    print("\nValidating database schema...")
    db_path = Path("dod_budget.sqlite")

    if not db_path.exists():
        print("[SKIPPED] Database not created yet.")
        return True

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check for critical tables
        required_tables = ["budget_lines", "pdf_pages"]
        missing_tables = []

        for table in required_tables:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)
            )
            if not cursor.fetchone():
                missing_tables.append(table)

        conn.close()

        if missing_tables:
            print(f"[FAILED] Missing tables: {', '.join(missing_tables)}")
            return False

        print("[PASSED] Database schema is valid.")
        return True

    except sqlite3.DatabaseError as e:
        print(f"[FAILED] Database error: {e}")
        return False


def check_required_files():
    """Verify required configuration files exist."""
    print("\nChecking for required files...")

    required_files = [
        "requirements.txt",
        "README.md",
        ".gitignore",
    ]

    missing = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing.append(file_path)

    if missing:
        print(f"[FAILED] Missing required files: {', '.join(missing)}")
        return False

    print("[PASSED] All required files present.")
    return True


def main():
    print("=" * 70)
    print("PRE-COMMIT HOOK: Comprehensive Checks")
    print("=" * 70)

    # Run all checks
    results = {
        "Optimization Tests": run_optimization_tests(),
        "Module Imports": check_imports(),
        "Syntax Validation": check_syntax(),
        "Code Quality": check_code_quality(),
        "Security": check_security(),
        "Database Schema": check_database_schema(),
        "Required Files": check_required_files(),
    }

    # Summary
    print("\n" + "=" * 70)
    print("PRE-COMMIT CHECK SUMMARY")
    print("=" * 70)

    all_passed = True
    for check_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{check_name:.<50} {status}")
        if not passed:
            all_passed = False

    print("=" * 70)

    if all_passed:
        print("All pre-commit checks passed. Proceeding with commit.")
        print("=" * 70)
        return 0
    else:
        print("Pre-commit checks failed. Please fix errors before committing.")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
