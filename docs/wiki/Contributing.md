# Contributing

> **Status:** Development phase (Phase 1 in progress).
> Full contribution guidelines will be documented in **Step 4.C6** after API and UI completion.
> For now, see [TASK_INDEX.md](../TASK_INDEX.md) for active development tasks.

Guide for contributing to the DoD Budget Analysis project.

---

## Development Setup

### Prerequisites

- Python 3.10+
- `pip install -r requirements.txt`
- `playwright install chromium` (for browser-based downloads)
- Sample data: `python dod_budget_downloader.py --sources comptroller --years 2026`
- Build database: `python build_budget_db.py`

## Project Structure

```
dod-budget-analysis/
  dod_budget_downloader.py   # Document downloader (CLI + GUI)
  build_budget_db.py         # Excel/PDF → SQLite parser
  build_budget_gui.py        # GUI wrapper for database builder
  search_budget.py           # Full-text search CLI
  validate_budget_db.py      # Data quality validation suite
  docs/
    TASK_INDEX.md            # Master task index (Phase 0–1)
    TODO_*.md                # Individual task specifications
    wiki/                    # Project wiki pages
  tests/
    conftest.py              # Pytest fixtures
    test_parsing.py          # Unit tests for parsing logic
    test_e2e_pipeline.py     # End-to-end integration tests
    fixtures/                # Test data files
  scripts/
    scheduled_download.py    # Automated download script (skeleton)
  DoD_Budget_Documents/      # Downloaded files (not committed)
```

## Coding Standards

- **Python:** Follow existing code style (type hints for public APIs, docstrings for functions)
- **Markdown:** Use ATX headings (`#`, `##`, etc.) and reference-style links where practical
- **Commit messages:** Conventional commits with Step ID references (e.g., `[Step 1.B2] Fix parsing logic`)
- **Tests:** Use pytest with `@pytest.mark.parametrize` for multiple test cases

## Pull Request Process

- **PR title:** Reference the Step ID (e.g., `[Step 1.B2] Fix column mapping for P-1 exhibits`)
- **Description:** Explain what changed and why; reference the relevant TODO file
- **Data changes:** Run `python validate_budget_db.py` and ensure no regressions
- **Test changes:** Run `pytest` and verify coverage
- **Status updates:** Update relevant `TODO_*.md` file with completion status

## Reporting Issues

When reporting issues, include:

- **Bug reports:** Steps to reproduce, expected behavior, actual behavior, Python/OS version
- **Data quality issues:** Source file, exhibit type, specific field(s), description of anomaly
- **Feature requests:** Use case, proposed approach, alternatives considered
