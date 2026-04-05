---
name: review-data
description: Audit database quality by running validators and cross-referencing NOTICED_ISSUES.md. Use to check data integrity or find new issues.
user-invocable: true
allowed-tools: "Read Bash Grep Glob Agent"
argument-hint: "[db-path]"
---

# Review Data — Database Quality Audit

Run data quality checks against the SQLite database and cross-reference findings with known issues.

## Process

### 1. Locate the database

Use the path from `$ARGUMENTS` if provided, otherwise default to `dod_budget.sqlite` (the `APP_DB_PATH` default).

If the database doesn't exist, report that and stop.

### 2. Run automated validators

Execute the built-in validation suite:

```bash
python -c "
from pipeline.db_validator import DataValidator
from pathlib import Path
v = DataValidator(Path('${DB_PATH:-dod_budget.sqlite}'))
results = v.run_all()
for r in results:
    print(f'{r.status}: {r.check_name} — {r.message}')
"
```

If that fails (e.g., missing module or DB), fall back to direct SQL checks:

```bash
sqlite3 "${DB_PATH:-dod_budget.sqlite}" "
SELECT 'Total rows', COUNT(*) FROM budget_lines;
SELECT 'Distinct services', COUNT(DISTINCT service_agency) FROM budget_lines;
SELECT 'Distinct FYs', COUNT(DISTINCT fiscal_year) FROM budget_lines;
SELECT 'Null PE numbers', COUNT(*) FROM budget_lines WHERE pe_number IS NULL;
SELECT 'Null amounts', COUNT(*) FROM budget_lines WHERE amount IS NULL;
SELECT 'FTS index rows', COUNT(*) FROM budget_lines_fts;
"
```

### 3. Cross-reference with NOTICED_ISSUES.md

Read `docs/NOTICED_ISSUES.md` and check:
- Are any `**[RESOLVED]**` issues showing regression in the current data?
- Are any `**[OPEN]**` issues now fixed based on the validator results?
- Are there new issues the validators found that aren't documented?

### 4. Report

Produce a summary:

| Category | Count |
|----------|-------|
| Validator checks passed | N |
| Validator checks failed | N |
| Known issues still open | N |
| Known issues now fixed (update docs!) | N |
| New issues found | N |

For any new or regressed issues, provide:
- Description of the problem
- SQL query to reproduce
- Suggested root cause
- Recommended fix approach

### 5. Suggest doc updates

If any issues changed status, recommend specific edits to `docs/NOTICED_ISSUES.md` — but do NOT make the edits automatically. Let the user decide.
