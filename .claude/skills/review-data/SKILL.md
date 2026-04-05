---
name: review-data
description: Audit database quality by running validators and cross-referencing NOTICED_ISSUES.md. Use to check data integrity or find new issues.
user-invocable: true
allowed-tools: "Read Bash Grep Glob"
argument-hint: "[db-path]"
---

# Review Data — Database Quality Audit

Run data quality checks against the SQLite database and cross-reference findings with known issues.

## Process

### 1. Locate the database

Use the path from `$ARGUMENTS` if provided, otherwise default to `dod_budget.sqlite` (the `APP_DB_PATH` default).

If the database doesn't exist, report that and stop.

### 2. Run automated validators

Execute the built-in validation CLI (see `pipeline/db_validator.py`):

```bash
python pipeline/db_validator.py --db dod_budget.sqlite --verbose
```

Replace `dod_budget.sqlite` with the actual path from step 1.

If that fails (e.g., missing module or DB), fall back to direct SQL checks:

```bash
sqlite3 dod_budget.sqlite "
SELECT 'Total rows', COUNT(*) FROM budget_lines;
SELECT 'Distinct services', COUNT(DISTINCT service_agency) FROM budget_lines;
SELECT 'Distinct FYs', COUNT(DISTINCT fiscal_year) FROM budget_lines;
SELECT 'Null PE numbers', COUNT(*) FROM budget_lines WHERE pe_number IS NULL;
SELECT 'Null amounts', COUNT(*) FROM budget_lines WHERE amount IS NULL;
SELECT 'FTS index rows', COUNT(*) FROM budget_lines_fts;
"
```

### 3. Cross-reference with NOTICED_ISSUES.md

Use Grep to find open and resolved issues efficiently:

```
Grep pattern="\[OPEN\]|\[RESOLVED\]" path="docs/NOTICED_ISSUES.md"
```

Then check:
- Are any `**[RESOLVED]**` issues showing regression in the current data?
- Are any `**[OPEN]**` issues now fixed based on the validator results?
- Are there new issues the validators found that aren't documented?

Only read the full file if you need more context around a specific issue.

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

If any issues changed status, recommend specific edits to `docs/NOTICED_ISSUES.md` — but do NOT make the edits automatically. Suggest running `/update-docs` afterward.
