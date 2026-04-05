---
name: validate
description: Run the full pre-PR validation suite (ruff lint, mypy type check, pytest tests). Use before committing or when checking code quality.
user-invocable: true
allowed-tools: "Bash Read Grep"
argument-hint: "[--quick]"
---

# Validate — Pre-PR Check Suite

Run the project's full validation pipeline and report results. This matches the CI workflow and the Pre-PR Checklist in CLAUDE.md.

## Steps

If `$ARGUMENTS` contains `--quick`, run a fast subset (stop on first failure, no coverage):

```bash
python -m pytest tests/ --ignore=tests/test_gui_tracker.py --ignore=tests/optimization_validation -q --tb=short -x
```

Otherwise, run the full suite via the existing pre-commit checker, which orchestrates ruff, mypy, and pytest with coverage:

```bash
python run_precommit_checks.py
```

If `run_precommit_checks.py` is unavailable or fails to import, fall back to running the three checks directly:

```bash
ruff check . --select=E,W,F --ignore=E501 --exclude=DoD_Budget_Documents
mypy api/ utils/ --ignore-missing-imports --no-error-summary
python -m pytest tests/ --ignore=tests/test_gui_tracker.py --ignore=tests/optimization_validation --cov=api --cov=utils --cov-report=term-missing -q --tb=short
```

## Output

After all checks complete, produce a summary table:

| Check | Status | Issues |
|-------|--------|--------|
| ruff  | PASS/FAIL | count |
| mypy  | PASS/FAIL | count |
| pytest | PASS/FAIL | passed/failed/skipped |

If any check fails, list the specific errors and suggest fixes. Do NOT auto-fix without asking — just report.
