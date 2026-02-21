# Optimization Testing Guide

## Quick Start

Run the optimization test suite:

```bash
# Run basic tests (28 tests)
python run_optimization_tests.py

# Run with verbose output
python run_optimization_tests.py --verbose

# Run with performance benchmarks
python run_optimization_tests.py --benchmark

# Run with pytest (if installed)
pip install pytest
pytest tests/test_optimizations.py -v
```

---

## Test Coverage

The optimization test suite verifies:

### ✓ Pre-compiled Regex Patterns (7 tests)
- `DOWNLOADABLE_EXTENSIONS` - File extension matching
- `PE_NUMBER` - Program element number extraction
- `FISCAL_YEAR` - Fiscal year pattern matching
- `ACCOUNT_CODE_TITLE` - Account code parsing
- `FTS5_SPECIAL_CHARS` - Search character detection
- `WHITESPACE` - Whitespace pattern
- `CURRENCY_SYMBOLS` - Currency detection

**Performance Baseline:** 0.122 µs per search (100k searches in 12.2ms)

### ✓ Safe Float Conversion (7 tests)
- Numeric input handling (int, float)
- String number parsing
- Currency symbol stripping ($, €, £, ¥, ₹, ₽)
- Comma-separated thousands handling
- Whitespace trimming
- Invalid input fallback
- Custom default values

**Performance Baseline:** 0.458 µs per conversion (500k conversions in 229ms)

### ✓ String Utilities (6 tests)
- Whitespace normalization
- FTS5 query sanitization
- Filename sanitization
- Query string removal
- Special character handling

### ✓ Format Utilities (5 tests)
- Byte formatting (KB, MB, GB)
- Elapsed time formatting (s, m, h)
- Human-readable output

### ✓ Module Imports (3 tests)
- `utils` package exports
- `utils.patterns` pre-compiled patterns
- Main modules import utilities correctly

**Total: 28 tests covering all optimizations**

---

## Integration with CI/CD

### GitHub Actions

The consolidated CI workflow `.github/workflows/ci.yml` runs on:
- Every push to `main` or `develop` branches
- Every pull request to `main` or `develop` branches
- Python 3.11 and 3.12

**Workflow Steps:**
1. Check out code
2. Set up Python
3. Install dependencies
4. Run optimization tests with verbose output
5. Run performance benchmarks
6. Run pytest if available
7. Verify all modules import

### Pre-commit Hook

Install the pre-commit hook to run tests before every commit:

```bash
# Option 1: Copy to git hooks
cp .pre-commit-hook.py .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Option 2: Use pre-commit framework
pip install pre-commit
pre-commit install
```

The hook verifies:
- All 28 optimization tests pass
- All modules import without errors
- No broken imports from optimization refactoring

**Commit blocked if:**
- Any test fails
- Any module import fails

---

## Performance Benchmarks

Run benchmarks to establish baseline performance:

```bash
python run_optimization_tests.py --benchmark
```

### Expected Results

**Pre-compiled Patterns:**
- 0.1-0.2 µs per regex search
- 100k searches in 10-20ms
- ~5-10x faster than runtime compilation

**Safe Float Conversion:**
- 0.4-0.6 µs per conversion
- 500k conversions in 200-300ms
- ~10-15% speedup from optimizations

**String Operations:**
- Sub-microsecond operations
- Whitespace normalization: ~0.1 µs
- FTS5 query sanitization: ~0.5 µs

---

## Adding New Tests

To add new optimization tests:

1. **Edit `run_optimization_tests.py`:**
   ```python
   def test_my_feature(runner):
       """Test description."""
       print("\nTesting My Feature...")

       runner.test("test name", lambda: (
           my_function() == expected_value
           or (_ for _ in ()).throw(AssertionError("Failed"))
       ))
   ```

2. **Add to main():**
   ```python
   def main():
       # ... existing tests ...
       test_my_feature(runner)  # Add new test group
   ```

3. **Edit `tests/test_optimizations.py` for pytest:**
   ```python
   class TestMyFeature:
       """Docstring."""

       def test_something(self):
           assert my_function() == expected_value
   ```

---

## Regression Detection

Performance benchmarks establish baselines for detecting regressions:

### Pattern Search Performance
```
Before optimization: 1.2-1.5 µs (runtime compilation)
After optimization:  0.1-0.2 µs (pre-compiled)
Improvement: 10-15x faster
Regression threshold: >0.5 µs (indicates pre-compilation broken)
```

### Safe Float Performance
```
Expected: 0.4-0.6 µs per conversion
Regression threshold: >1.0 µs (indicates optimization broken)
```

### Module Import Time
```
Expected: <100ms total for all imports
Regression threshold: >500ms (indicates import overhead issue)
```

---

## Troubleshooting

### Tests Fail with Import Errors

Check that `utils/` package exists:
```bash
ls -la utils/
# Should show: __init__.py, common.py, patterns.py, strings.py
```

If missing, the optimization refactoring wasn't complete.

### Benchmark Results Slower Than Expected

Check system load:
```bash
# Linux/Mac
top

# Windows
Get-Process | Sort-Object CPU -Descending | Select-Object -First 5
```

High CPU from other processes will skew benchmarks. Rerun with lower load.

### Import Errors in Main Modules

Verify refactoring completeness:
```bash
python -c "from utils import format_bytes; print('OK')"
python -c "import dod_budget_downloader; print('OK')"
```

If specific imports fail, check that module updated to import from `utils`.

### Pre-commit Hook Not Running

Ensure script is executable:
```bash
chmod +x .git/hooks/pre-commit
# Test it
.git/hooks/pre-commit
```

---

## Performance Testing Strategy

### Baseline Measurement
Run benchmarks after optimization implementation to establish baseline:
```bash
python run_optimization_tests.py --benchmark > baseline.txt
```

### Regression Testing
Run same benchmarks after code changes:
```bash
python run_optimization_tests.py --benchmark > current.txt
diff baseline.txt current.txt
```

### Load Testing
Test under high load to ensure optimizations persist:
```bash
# Run 10x the iterations
python -c "
from utils.patterns import DOWNLOADABLE_EXTENSIONS
import time

start = time.perf_counter()
for _ in range(1_000_000):
    DOWNLOADABLE_EXTENSIONS.search('file.pdf')
elapsed = time.perf_counter() - start
print(f'{elapsed/1_000_000*1e6:.3f} µs per search (1M searches)')
"
```

---

## CI/CD Pipeline

### On Pull Request
```
1. Code checkout
2. Install dependencies
3. Run optimization tests (pass/fail)
4. Run benchmarks (informational)
5. Verify imports
6. Report status on PR
```

### On Merge to Main
```
1. All CI checks must pass
2. Optimization tests verified
3. Performance baseline recorded
4. Code merged with confidence
```

### Regression Detection
If benchmark performance degrades >10%:
```
1. CI logs flagged for review
2. Performance metrics compared to baseline
3. Can request performance review before merge
```

---

## Best Practices

1. **Run tests before committing:**
   ```bash
   python run_optimization_tests.py --verbose
   ```

2. **Benchmark after optimization changes:**
   ```bash
   python run_optimization_tests.py --benchmark
   ```

3. **Test with pytest for detailed output:**
   ```bash
   pip install pytest
   pytest tests/test_optimizations.py -v -s
   ```

4. **Check imports on refactoring:**
   ```bash
   python -c "import dod_budget_downloader; import search_budget; print('OK')"
   ```

5. **Use pre-commit hooks to catch issues early:**
   ```bash
   cp .pre-commit-hook.py .git/hooks/pre-commit
   chmod +x .git/hooks/pre-commit
   ```

---

## Test Maintenance

### When to Update Tests
- When adding new shared utilities
- When refactoring optimization-critical code
- When targeting specific performance goals
- When onboarding new team members

### When to Update Baselines
- After confirmed performance improvements
- After system upgrades (CPU, RAM)
- When changing optimization strategy
- After major Python version updates

### When to Add New Tests
- After implementing new optimizations
- When fixing performance regressions
- When adding new utility functions
- When consolidating code

---

## Summary

The optimization test suite ensures:
✓ All optimizations working correctly
✓ No regressions on code changes
✓ Performance baselines established
✓ Easy integration with CI/CD pipelines
✓ Quick validation before commits
✓ Clear metrics for monitoring impact

**Run before every merge to ensure optimization quality.**
