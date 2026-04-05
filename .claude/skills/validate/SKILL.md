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

Run these three checks **sequentially** so failures are easy to read:

### 1. Lint (ruff)

```!
ruff check . --select=E,W,F --ignore=E501 --exclude=DoD_Budget_Documents 2>&1 | tail -20
```

### 2. Type check (mypy)

```!
mypy api/ utils/ --ignore-missing-imports --no-error-summary 2>&1 | tail -20
```

### 3. Tests (pytest)

If the user passed `--quick` as an argument, run a fast subset:

```bash
python -m pytest tests/ --ignore=tests/test_gui_tracker.py --ignore=tests/optimization_validation -q --tb=short -x
```

Otherwise run the full suite with coverage:

```bash
python -m pytest tests/ --ignore=tests/test_gui_tracker.py --ignore=tests/optimization_validation --cov=api --cov=utils --cov-report=term-missing -q --tb=short
```

## Output

After all three steps, produce a summary table:

| Check | Status | Issues |
|-------|--------|--------|
| ruff  | PASS/FAIL | count |
| mypy  | PASS/FAIL | count |
| pytest | PASS/FAIL | passed/failed/skipped |

If any check fails, list the specific errors and suggest fixes. Do NOT auto-fix without asking — just report.
