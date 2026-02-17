# Contributing

<!-- TODO [Step 4.C6]: Populate when the project is ready for external contributors. -->

Guide for contributing to the DoD Budget Analysis project.

---

## Development Setup

<!-- Prerequisites:
     - Python 3.10+
     - pip install -r requirements.txt
     - playwright install chromium
     - Download sample data: python dod_budget_downloader.py --sources comptroller --years 2026
     - Build database: python build_budget_db.py -->

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

<!-- Style guide:
     - Python: follow existing code style (type hints, docstrings)
     - Markdown: ATX headings, reference-style links where practical
     - Commit messages: conventional commits with Step references
     - Tests: pytest with parametrize for multiple cases -->

## Pull Request Process

<!-- PR guidelines:
     - Reference the Step ID in the PR title (e.g., "[Step 1.B2] ...")
     - Include a description of what changed and why
     - Ensure validate_budget_db.py passes if data-related
     - Run pytest if test-related
     - Update relevant TODO file status -->

## Reporting Issues

<!-- Issue templates:
     - Bug report: steps to reproduce, expected vs actual
     - Data quality: source file, exhibit type, details
     - Feature request: use case, proposed approach -->
