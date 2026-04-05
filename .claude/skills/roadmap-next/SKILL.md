---
name: roadmap-next
description: Find the next open task from docs/ROADMAP.md and present an implementation plan. Use when looking for what to work on next.
user-invocable: true
allowed-tools: "Read Grep Glob Bash"
argument-hint: "[phase-or-task-id]"
---

# Roadmap Next — Pick Up the Next Task

Scan `docs/ROADMAP.md` for incomplete tasks and present a prioritized implementation plan.

## Process

### 1. Parse the roadmap

Read `docs/ROADMAP.md` and identify all tasks NOT marked `✅ **Complete**`. Incomplete statuses include `⚠️ Not started`, `Partially Complete`, `Mostly Complete`, or any status without the word "Complete" standing alone.

### 2. Filter by argument (optional)

If `$ARGUMENTS` contains a phase number (e.g., `4`) or task ID (e.g., `4.A1`), filter to just that scope. Otherwise, show all open tasks.

### 3. Prioritize

Rank open tasks by:
1. **Dependencies satisfied** — can it be done now without external blockers (e.g., "requires deployed application" = blocked)?
2. **Phase order** — earlier phases before later
3. **Impact** — tasks that unblock other tasks first

### 4. Present the plan

For the top 1-3 actionable tasks, present:

| Field | Content |
|-------|---------|
| **Task ID** | e.g., `3.A7` |
| **Title** | From roadmap |
| **Current status** | What's done, what remains |
| **Files to modify** | List specific files |
| **Implementation steps** | Numbered steps |
| **Tests needed** | What test files to create/update |
| **Estimated scope** | Small / Medium / Large |

### 5. Ask before starting

Present the plan and **ask the user which task to proceed with** before writing any code. Do not start implementation automatically.

After implementation, suggest running `/update-docs` to keep PRD and ROADMAP in sync.

## Important

- If a candidate task overlaps with known data quality issues, check `docs/NOTICED_ISSUES.md` for context.
- Distinguish between tasks blocked on external factors (hosting, domain, user feedback) vs tasks that can be done now.
- Read `docs/PRD.md` only when needed to understand the feature area of a specific task.
