# Pre-Commit Tests Guide

## Overview

Extended pre-commit test suite to catch common issues before code is committed. Tests are organized by category and run automatically with the git pre-commit hook.

## Running Pre-Commit Tests

### Standalone Test Runner

```bash
# Run all tests
python run_precommit_checks.py

# With verbose output
python run_precommit_checks.py --verbose
```

### Automated (Via Git Hook)

```bash
# Install pre-commit hook
cp .pre-commit-hook.py .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Tests now run automatically before commits
git commit -m "Your message"
```

### With pytest (If Installed)

```bash
pip install pytest
pytest tests/test_precommit_checks.py -v
```

---

## Test Categories

### 1. Syntax Validation (1 test)

**Purpose:** Ensure all Python files parse without syntax errors

**What it checks:**
- All `.py` files parse successfully with Python AST
- No syntax errors that would break imports
- Valid Python 3.11+ syntax

**Fails if:**
- Any file has syntax errors
- Import statements are malformed
- Python grammar violations

**Example:**
```python
# FAIL: Missing colon
if condition
    pass

# PASS: Valid syntax
if condition:
    pass
```

---

### 2. Import Validation (1 test)

**Purpose:** Verify all modules can be imported without errors

**What it checks:**
- No circular import dependencies
- All required dependencies are available
- Module import chain is valid
- Relative imports work correctly

**Fails if:**
- Any module raises ImportError
- Circular dependencies detected
- Missing dependencies

**Example:**
```python
# FAIL: Circular import
# module_a.py imports module_b
# module_b.py imports module_a

# PASS: Proper dependency order
# utils imports nothing
# build_budget_db imports utils
# main imports build_budget_db
```

---

### 3. Code Quality Checks (2 tests)

#### 3a. No Debug Statements

**Purpose:** Prevent accidental commits of debugging code

**What it checks:**
- No `breakpoint()` calls
- No `pdb.set_trace()` calls
- No debug print statements left in code
- No `import pdb` in production code

**Fails if:**
- Any debug statement found in production files
- Breakpoint/pdb statements present (outside test files)

**Example:**
```python
# FAIL: Debug statement left in
def process_data(data):
    breakpoint()  # Forgot to remove!
    return data

# PASS: Debug statement removed
def process_data(data):
    return data
```

#### 3b. No Hardcoded Secrets

**Purpose:** Prevent accidental exposure of credentials

**What it checks:**
- No hardcoded passwords
- No API keys in strings
- No tokens or secrets
- No connection strings with credentials

**Fails if:**
- Patterns like `password = "..."`
- Patterns like `api_key = "..."`
- Patterns like `secret = "..."`
- Patterns like `token = "..."`

**Example:**
```python
# FAIL: Hardcoded password
PASSWORD = "SuperSecret123"

# PASS: Use environment variables
import os
PASSWORD = os.getenv("DB_PASSWORD")
```

---

### 4. Naming & Shadowing Detection (1 test)

**Purpose:** Catch variable name collisions with imported functions

**What it checks:**
- No shadowing of imported functions
- Variable names don't conflict with builtins
- Imported names used correctly
- No accidental name overwrites

**Fails if:**
- Local variable shadows imported function
- Builtin names are overwritten
- Import conflicts detected

**Example:**
```python
# FAIL: Shadowing imported function
from utils import elapsed
elapsed = time.time() - start  # Shadows function!
print(elapsed(start_time))  # Error!

# PASS: Use different variable name
from utils import elapsed
elapsed_time = time.time() - start
print(elapsed(start_time))  # Works!
```

---

### 5. Code Consistency (1 test)

**Purpose:** Maintain consistent code style

**What it checks:**
- Line length within limits (max 100 chars)
- Proper import organization (stdlib, third-party, local)
- Consistent indentation
- Module-level docstrings present

**Fails if:**
- Many lines exceed 100 characters
- Imports not properly grouped
- Missing module docstrings

**Notes:**
- SQL statements and URLs allowed to be longer
- Design files exempt from line length checks

**Example:**
```python
# FAIL: Line too long
result = some_very_long_function_name(parameter1, parameter2, parameter3, parameter4, parameter5)

# PASS: Wrapped or abbreviated
result = some_very_long_function_name(
    parameter1, parameter2, parameter3, parameter4, parameter5
)
```

---

### 6. Documentation Checks (1 test)

**Purpose:** Ensure code is documented

**What it checks:**
- All modules have docstrings
- Critical functions have docstrings
- Type hints present for complex functions
- Documentation is up-to-date

**Fails if:**
- Module missing docstring
- Critical functions lack documentation
- Docstrings are empty/placeholder

**Example:**
```python
# FAIL: Missing module docstring
import os

def process_file(path):
    """Process a file."""
    ...

# PASS: Complete documentation
"""
File processing module.

Handles reading and parsing budget files.
"""
import os

def process_file(path: str) -> str:
    """Process a file and return results.

    Args:
        path: Path to file to process

    Returns:
        Processed file contents
    """
    ...
```

---

### 7. Configuration Files (1 test)

**Purpose:** Verify all required configuration is present

**What it checks:**
- GitHub Actions workflow exists
- Pre-commit hook script exists
- Utils package complete
- CI/CD configuration valid

**Fails if:**
- `.github/workflows/ci.yml` missing
- `.pre-commit-hook.py` missing
- Any utils file missing

---

### 8. Database Consistency (1 test)

**Purpose:** Verify database integrity (if present)

**What it checks:**
- Database file is valid SQLite
- Schema tables present
- No corruption detected
- Migrations up-to-date

**Skipped if:**
- Database hasn't been created yet

**Fails if:**
- Database file corrupted
- Required tables missing
- Schema integrity issues

---

### 9. Optimization Tests (1 test)

**Purpose:** Ensure optimization improvements still work

**What it checks:**
- All 28 optimization tests pass
- Utils package functions work
- Performance baselines maintained
- Pre-compiled patterns functional

**Fails if:**
- Any optimization test fails
- Performance regression detected
- Utils imports broken

---

## Test Results Summary

```
======================================================================
PRE-COMMIT CHECKS: 10 passed, 0 failed (10 total)
======================================================================

Results:
[PASS] Syntax validation
[PASS] Import validation
[PASS] No debug statements
[PASS] No hardcoded secrets
[PASS] Naming & shadowing
[PASS] Code consistency
[PASS] Documentation
[PASS] Configuration files
[PASS] Database consistency
[PASS] Optimization tests
```

---

## Common Issues & Fixes

### "Syntax errors found"

**Cause:** File has Python syntax errors

**Fix:**
```bash
# Check specific file
python -m py_compile your_file.py

# Fix and try again
git add your_file.py
git commit -m "Fix syntax error"
```

### "Module import failed"

**Cause:** Missing dependency or circular import

**Fix:**
```bash
# Test import
python -c "import module_name"

# Check dependencies
pip list

# Install missing dependencies
pip install -r requirements.txt
```

### "Shadowing of imported function"

**Cause:** Variable name conflicts with imported name

**Fix:**
```python
# Before (FAIL)
from utils import elapsed
elapsed = time.time() - start

# After (PASS)
from utils import elapsed
elapsed_time = time.time() - start
```

### "Debug statement found"

**Cause:** Breakpoint or pdb left in code

**Fix:**
```bash
# Find and remove all breakpoints
grep -r "breakpoint()" .
grep -r "pdb.set_trace()" .

# Remove the lines and commit again
```

### "Hardcoded secret detected"

**Cause:** Password/API key/token in code

**Fix:**
```bash
# Move to environment variable
export DB_PASSWORD="your_password"

# Use in code
import os
password = os.getenv("DB_PASSWORD")
```

---

## Continuous Integration

### GitHub Actions

Pre-commit tests run automatically on:
- Every push to `main` or `develop`
- Every pull request
- Python 3.11 and 3.12

**Check PR status** for test results before merging.

### Local Testing

Always run before committing:

```bash
# Quick check
python run_precommit_checks.py

# Verbose check
python run_precommit_checks.py --verbose

# Full suite with pytest
pytest tests/test_precommit_checks.py -v
```

---

## Best Practices

1. **Run tests before committing**
   ```bash
   python run_precommit_checks.py --verbose
   ```

2. **Install pre-commit hook**
   ```bash
   cp .pre-commit-hook.py .git/hooks/pre-commit
   chmod +x .git/hooks/pre-commit
   ```

3. **Fix issues immediately**
   - Don't commit with failing tests
   - Address warnings before pushing

4. **Review test output**
   - Check verbose output for details
   - Fix root cause, not just symptoms

5. **Keep tests up-to-date**
   - Update when adding new checks
   - Document new requirements

---

## Test Files

- **Standalone runner:** `run_precommit_checks.py`
- **pytest suite:** `tests/test_precommit_checks.py`
- **Git hook:** `.pre-commit-hook.py`
- **Optimization tests:** `run_optimization_tests.py`

---

## Summary

**10 comprehensive pre-commit checks** ensure code quality, consistency, and maintainability:

✓ Syntax validation
✓ Import validation
✓ No debug statements
✓ No hardcoded secrets
✓ Naming & shadowing detection
✓ Code consistency
✓ Documentation completeness
✓ Configuration files present
✓ Database consistency
✓ Optimization tests pass

**Run before every commit:** `python run_precommit_checks.py`
