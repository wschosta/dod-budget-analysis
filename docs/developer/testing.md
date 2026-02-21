# Testing Guide

Comprehensive guide to testing the DoD Budget Analysis project. The test suite
covers utilities, API endpoints, frontend routes, data pipeline operations,
performance, and code quality.

---

## Framework and Configuration

| Setting | Value |
|---------|-------|
| **Framework** | pytest with pytest-cov |
| **Config file** | `pyproject.toml` |
| **Test paths** | `tests/` |
| **Default options** | `-v --tb=short` |
| **Coverage threshold** | 80% minimum on `api/` and `utils/` |
| **Python versions** | 3.11, 3.12 (CI matrix); `requires-python >= 3.10` |
| **Test file count** | 75 test files |

---

## Running Tests

### Full Suite

```bash
python -m pytest tests/ -v
```

### Specific Module

```bash
python -m pytest tests/test_api.py -v
```

### Specific Test Class or Function

```bash
python -m pytest tests/test_rate_limiter.py::TestSearchRateLimit -v
python -m pytest tests/test_api.py::test_health_endpoint -v
```

### With Coverage

```bash
python -m pytest tests/ --cov=api --cov=utils --cov-report=term-missing --cov-fail-under=80
```

### Skip Problematic Tests

```bash
# Skip GUI tracker tests (require Xvfb display) and optimization validation
python -m pytest tests/ --ignore=tests/test_gui_tracker.py --ignore=tests/optimization_validation
```

### Run Tests Matching a Pattern

```bash
python -m pytest tests/ -k "search" -v      # All tests with "search" in the name
python -m pytest tests/ -k "not slow" -v     # Skip tests marked as slow
```

---

## Test Groups

Tests are organized into groups as reflected in the CI pipeline
(`.github/workflows/ci.yml`):

### 1. Unit Tests

Utilities, patterns, config, validation, and query builders.

```bash
python -m pytest tests/test_utils.py tests/test_patterns.py tests/test_config.py tests/test_validation.py -v
```

### 2. API Tests

Endpoints, models, search, download, rate limiting, charts, and PE routes.

```bash
python -m pytest tests/test_api.py tests/test_models.py tests/test_search.py tests/test_download.py tests/test_rate_limiter.py -v
```

### 3. Frontend Tests

Routes, helpers, GUI features, fixes, and accessibility.

```bash
python -m pytest tests/test_frontend_routes.py -v
```

### 4. Data Pipeline Tests

Build, enrichment, schema, pipeline, exhibits, manifests, and PDF processing.

```bash
python -m pytest tests/test_build.py tests/test_enrichment.py tests/test_schema_design.py tests/test_pipeline.py -v
```

### 5. Performance Tests

Load testing, benchmarks, and optimization validation.

```bash
python -m pytest tests/test_performance.py tests/test_benchmarks.py -v
```

### 6. Code Quality

Pre-commit checks and hook tests.

```bash
python -m pytest tests/test_precommit.py -v
```

### 7. Advanced Test Groups

These test suites cover cross-cutting concerns:

- **BEAR** -- Schema, migration, Docker, and refresh workflow tests
- **TIGER** -- Caching, performance, feedback, and validation tests
- **LION** -- Database integrity and consistency tests
- **EAGLE** -- Frontend and PE endpoint tests

### 8. Operational Tests

Refresh workflow and scheduled download tests.

```bash
python -m pytest tests/test_refresh.py tests/test_scheduled_download.py -v
```

### 9. GUI Tracker Tests

tkinter-based GUI tests that require a display server (Xvfb in CI).

```bash
# Requires Xvfb for headless environments
xvfb-run python -m pytest tests/test_gui_tracker.py -v
```

### 10. Docker Build Validation

Separate CI job that verifies the Docker image builds successfully and
all Python imports resolve correctly.

---

## Test Fixtures

Shared fixtures are defined in `tests/conftest.py`. Static fixture data
lives in `tests/fixtures/`.

### Session-Scoped Fixtures

| Fixture | Scope | Description |
|---------|-------|-------------|
| `fixtures_dir` | session | Temp directory with both Excel and PDF fixture files |
| `fixtures_dir_excel_only` | session | Temp directory with only Excel fixtures (no PDFs) |
| `test_db` | session | Pre-built SQLite database from all fixtures (Excel + PDF) |
| `test_db_excel_only` | session | Pre-built SQLite database from Excel-only fixtures |
| `bad_excel` | session | Intentionally malformed Excel file for error-handling tests |

### Function-Scoped Fixtures

| Fixture | Scope | Description |
|---------|-------|-------------|
| `tmp_db` | function | Empty SQLite database in a temporary directory for unit tests |

### Usage Tips

- **Use `test_db_excel_only` instead of `test_db`** when tests only need
  Excel data. This avoids occasional `pdfplumber PanicException` errors
  that can occur when PDF fixtures are processed.
- **Use `tmp_db`** for tests that need a clean, isolated database (e.g.,
  schema creation tests, migration tests).
- Session-scoped fixtures are created once per test session and shared
  across all tests that request them, making the suite significantly faster.

---

## Writing New Tests

### File Naming

Create test files as `tests/test_<module>.py`. The `tests/` directory is
flat (no subdirectories except `fixtures/` and `optimization_validation/`).

### Basic Test Structure

```python
"""Tests for utils/my_module.py."""
import pytest


def test_my_function_basic():
    """Test the basic behavior of my_function."""
    from utils.my_module import my_function
    result = my_function("input")
    assert result == "expected"


def test_my_function_edge_case():
    """Test my_function with edge-case input."""
    from utils.my_module import my_function
    assert my_function("") == ""
    assert my_function(None) is None
```

### API Endpoint Tests

For API tests, create an in-memory or `tmp_path`-backed SQLite database,
build the schema with `executescript()`, and use FastAPI's `TestClient`:

```python
"""Tests for the /api/v1/search endpoint."""
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app


@pytest.fixture
def client(tmp_path):
    """Create a test client with a temporary database."""
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            exhibit_type TEXT,
            fiscal_year TEXT,
            organization_name TEXT,
            line_item_title TEXT
        );
        -- Add FTS5 table, triggers, etc. as needed
    """)
    conn.close()

    app = create_app(db_path=str(db_path))
    return TestClient(app)


def test_search_returns_results(client):
    """Test that search returns matching results."""
    response = client.get("/api/v1/search?q=Apache")
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
```

### Rate Limiter Tests

Rate limiter tests must clear the rate counter state between test cases
to avoid interference. Use an `autouse=True` fixture:

```python
import pytest
import api.app


@pytest.fixture(autouse=True)
def clear_rate_counters():
    """Clear rate limit counters before each test."""
    api.app._rate_counters.clear()
    yield
    api.app._rate_counters.clear()
```

### Module-Scoped Client Fixtures

Some test modules use module-scoped `client` fixtures that share global
database path state. If a test changes the DB path (e.g., to test
error handling with a missing database), **put it in a separate module**
to avoid affecting other tests in the same module.

---

## Coverage Requirements

The project enforces an **80% minimum code coverage** on the `api/` and
`utils/` directories:

```bash
python -m pytest tests/ --cov=api --cov=utils --cov-report=term-missing --cov-fail-under=80
```

This is enforced in CI. When adding new code to `api/` or `utils/`:

1. Write tests that exercise the new code paths
2. Run coverage locally before pushing to verify you meet the threshold
3. Use `--cov-report=term-missing` to identify uncovered lines
4. Focus on testing public API surfaces, error paths, and edge cases

---

## CI Test Organization

The GitHub Actions CI pipeline (`.github/workflows/ci.yml`) runs tests
in parallel groups for faster feedback:

1. **Lint** -- `ruff check` for style violations
2. **Type check** -- `mypy` on `api/` and `utils/`
3. **Unit tests** -- Utility and core logic tests
4. **API tests** -- Endpoint and model tests
5. **Frontend tests** -- Route and template tests
6. **Data pipeline tests** -- Build, enrichment, and schema tests
7. **Performance tests** -- Load and benchmark tests
8. **Code quality** -- Pre-commit hook tests
9. **Advanced tests** -- BEAR, TIGER, LION, EAGLE groups
10. **Operational tests** -- Refresh and download workflow tests
11. **GUI tracker tests** -- Requires Xvfb (run separately)
12. **Docker build** -- Verifies image builds and imports work
13. **Coverage** -- Runs full suite with coverage enforcement

Tests run on both Python 3.11 and Python 3.12 in a matrix configuration.

---

## Common Patterns and Best Practices

### Use Shared Fixtures

Always check `tests/conftest.py` for existing fixtures before creating
your own. The session-scoped database fixtures avoid redundant setup.

### Test Error Paths

Test both success cases and error cases:

```python
def test_budget_line_not_found(client):
    """Test that requesting a non-existent ID returns 404."""
    response = client.get("/api/v1/budget-lines/999999")
    assert response.status_code == 404
```

### Test Input Validation

```python
def test_search_empty_query(client):
    """Test that an empty query returns 422."""
    response = client.get("/api/v1/search?q=")
    assert response.status_code == 422
```

### Parametrize Repetitive Tests

```python
@pytest.mark.parametrize("group_by", ["service", "fiscal_year", "exhibit_type"])
def test_aggregation_group_by(client, group_by):
    """Test that aggregation works for all group_by values."""
    response = client.get(f"/api/v1/aggregations?group_by={group_by}")
    assert response.status_code == 200
```

### Avoid Test Interdependence

Each test should be independent and not rely on state from other tests.
Use function-scoped fixtures for mutable state and session-scoped fixtures
only for read-only shared data.

### Database Test Isolation

For tests that modify the database, always use `tmp_db` (function-scoped)
rather than `test_db` (session-scoped) to avoid polluting the shared
database state.

---

## Troubleshooting

### pdfplumber PanicException

If you see `PanicException` errors from pdfplumber during tests, switch
from `test_db` to `test_db_excel_only`. The PDF processing can occasionally
trigger panics in the underlying C library.

### Rate Limiter Interference

If rate limiter tests fail intermittently, ensure the `autouse` fixture
that clears `_rate_counters` is present in the test module.

### Module-Scoped Fixture Conflicts

If tests pass individually but fail when run together, check for
module-scoped fixtures that share mutable state (especially database
path globals). Move conflicting tests to separate modules.

### GUI Tests Failing in CI

GUI tests require a display server. In CI, they run under `xvfb-run`.
Locally, they require a display (X11 or Wayland). Skip them with
`--ignore=tests/test_gui_tracker.py` if no display is available.

---

## Related Documentation

- [Architecture Overview](architecture.md) -- System components being tested
- [API Reference](api-reference.md) -- Endpoint specifications for API tests
- [Utilities Reference](utilities.md) -- Module documentation for unit tests
- [Performance](performance.md) -- Performance test expectations and benchmarks
