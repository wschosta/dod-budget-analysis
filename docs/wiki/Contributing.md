# Contributing

Guide for contributing to the DoD Budget Analysis project.

> **Status:** Phase 1 active development. See [TASK_INDEX.md](../TASK_INDEX.md) for open tasks.

---

## Development Setup

### Prerequisites

- Python 3.10+ (3.11 or 3.12 recommended)
- `pip install -r requirements.txt`
- `pip install -r requirements-dev.txt` (for tests and linting)
- `playwright install chromium` (for browser-based downloads)

### Getting data

```bash
# Download a small slice for development
python dod_budget_downloader.py --sources comptroller --years 2026

# Build the database
python build_budget_db.py

# Verify
python validate_budget_db.py --verbose
```

---

## Project Structure

```
dod-budget-analysis/
  # Core pipeline scripts
  dod_budget_downloader.py   # Document downloader (HTTP + Playwright)
  build_budget_db.py         # Excel/PDF -> SQLite parser (incremental, checkpointed)
  build_budget_gui.py        # Tkinter GUI wrapper for database builder
  search_budget.py           # Full-text search CLI (FTS5)
  validate_budget_db.py      # Data quality validation (7 automated checks)
  validate_budget_data.py    # Extended validation suite
  refresh_data.py            # Orchestrator: download -> build -> validate -> report
  exhibit_catalog.py         # Exhibit type definitions and column specs
  exhibit_type_inventory.py  # Script to scan and inventory exhibit types
  schema_design.py           # Phase 2 schema design planning document
  api_design.py              # Phase 2 API design planning document
  frontend_design.py         # Phase 3 frontend design planning document

  # Utilities (shared across all modules)
  utils/
    __init__.py              # Re-exports for convenient importing
    common.py                # format_bytes, elapsed, sanitize_filename, get_connection
    config.py                # Config, DatabaseConfig, DownloadConfig, KnownValues,
                             # ColumnMapping, FilePatterns
    database.py              # SQLite helpers: init_pragmas, batch_insert, create_fts5_index
    formatting.py            # TableFormatter, ReportFormatter, format_amount
    http.py                  # RetryStrategy, SessionManager, TimeoutManager, CacheManager
    manifest.py              # ManifestManager for download tracking
    patterns.py              # Pre-compiled regex patterns (PE_NUMBER, FISCAL_YEAR, etc.)
    progress.py              # ProgressBar, Spinner, ProgressTracker
    strings.py               # safe_float, normalize_whitespace, sanitize_fts5_query
    validation.py            # validate_db_path, validate_year, validate_source

  # Tests
  tests/
    conftest.py              # Pytest fixtures and shared test utilities
    test_parsing.py          # Unit tests for Excel/PDF parsing logic
    test_e2e_pipeline.py     # End-to-end integration tests
    test_pipeline.py         # Pipeline integration tests
    test_search.py           # Search functionality tests
    test_validation.py       # Validation suite tests
    test_optimizations.py    # Performance optimization tests
    test_optimization.py     # Additional optimization tests
    test_checkpoint.py       # Checkpoint/resume functionality tests
    test_build_integration.py # Build integration tests
    test_precommit_checks.py # Pre-commit hook tests
    fixtures/                # Test data files (Excel/PDF samples)

  # Automation
  scripts/
    scheduled_download.py    # Wrapper for unattended/cron download runs

  # Documentation
  docs/
    TASK_INDEX.md            # Master task index (Phase 0-1)
    TODO_*.md                # Individual task specifications
    wiki/                    # Project wiki pages (this directory)
    API_ENDPOINT_SPECIFICATION.md
    API_FRAMEWORK_DECISION.md
    FRONTEND_TECHNOLOGY_DECISION.md
    UI_WIREFRAMES.md

  # CI/CD
  .github/workflows/
    optimization-tests.yml   # Automated optimization test suite

  # Data (not committed)
  DoD_Budget_Documents/      # Downloaded source files
  dod_budget.sqlite          # Built database
```

---

## Coding Standards

- **Python:** Follow existing code style — type hints for all public function signatures,
  docstrings for all public functions and classes (including `__init__`)
- **Shared utilities:** Use `utils/` modules instead of duplicating logic. Import from
  `utils` rather than rewriting `safe_float`, `format_bytes`, HTTP retry logic, etc.
- **Markdown:** Use ATX headings (`#`, `##`) and pipe tables; wrap at 100 chars where practical
- **Commit messages:** Reference the Step ID when applicable
  (e.g., `[Step 1.B2] Fix column mapping for P-1 exhibits`)
- **Tests:** Use pytest; use `@pytest.mark.parametrize` for multiple test cases

---

## Pull Request Process

1. **Reference the Step ID** in the PR title (e.g., `[Step 1.B2] Fix column mapping`)
2. **Describe the change**: what was changed, why, and how to test it
3. **Run the validation suite** before opening the PR:
   ```bash
   python validate_budget_db.py --verbose
   pytest tests/
   ```
4. **Update the relevant TODO file** in `docs/` with completion status
5. **Update wiki** if the change affects user-visible behavior or data structure

---

## Running Tests

```bash
# Run all tests
pytest tests/

# Run a specific test file
pytest tests/test_parsing.py -v

# Run with coverage
pytest tests/ --cov=. --cov-report=term-missing

# Run optimization tests
python run_optimization_tests.py

# Run pre-commit checks
python run_precommit_checks.py
```

---

## Pre-commit Hook

A pre-commit hook (`.pre-commit-hook.py`) runs a subset of checks before each commit:
- Import checks
- Basic syntax validation
- Lint-style checks

To run manually:
```bash
python run_precommit_checks.py
```

---

## Reporting Issues

When reporting issues, include:

- **Bug reports:** Steps to reproduce, expected behavior, actual behavior, Python/OS version,
  and the relevant log output
- **Data quality issues:** Source file path, exhibit type, specific field(s), expected vs
  actual values, and `python validate_budget_db.py --verbose` output
- **Feature requests:** Use case, proposed approach, alternatives considered

Label issues appropriately: `[Bug]`, `[Data Quality]`, `[Feature]`, `[Documentation]`.
