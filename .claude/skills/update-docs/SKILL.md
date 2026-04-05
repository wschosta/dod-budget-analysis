---
name: update-docs
description: Sync project documentation (PRD, ROADMAP, NOTICED_ISSUES) after code changes. Enforces the update rules from CLAUDE.md. Use after implementing features, fixing bugs, or completing roadmap tasks.
user-invocable: true
allowed-tools: "Read Edit Write Bash Grep Glob"
---

# Update Docs — Post-Change Documentation Sync

After code changes, ensure all canonical docs stay in sync per CLAUDE.md rules.

## Process

### 1. Identify what changed

Review recent changes to understand scope:

```bash
git diff --name-only HEAD~1..HEAD 2>/dev/null || git diff --name-only --cached
git log -3 --oneline
```

### 2. Determine which docs need updates

Apply these rules from CLAUDE.md:

| Change Type | Update Required |
|-------------|----------------|
| Feature added/changed/removed | `docs/PRD.md` |
| Roadmap task completed | `docs/ROADMAP.md` |
| Data quality issue fixed/found | `docs/NOTICED_ISSUES.md` |
| User-facing docs affected | Corresponding wiki page |

### 3. Read only the docs that need updating

Read each doc identified in step 2 — skip docs that don't need changes.

- `docs/PRD.md` — canonical feature descriptions
- `docs/ROADMAP.md` — task statuses with IDs like `1.A1`, `2.B3`, `4.C3`
- `docs/NOTICED_ISSUES.md` — data quality and UI issues with resolution status

### 4. Make targeted updates

For each doc:
- **PRD.md**: Update the relevant section to describe the current state of the feature. Add new sections for new features. Remove sections for removed features.
- **ROADMAP.md**: Change task status to `✅ **Complete**` with a brief note on what was done.
- **NOTICED_ISSUES.md**: Mark issues as `**[RESOLVED]**` with a one-line fix description, or add new `**[OPEN]**` issues discovered during work. Follow the file's existing formatting conventions (strikethrough on resolved issue titles, bold status tags).

If the scope of changes is ambiguous, ask the user before editing.

### 5. Summary

List exactly which files were updated and what changed. If no doc updates were needed, say so explicitly.

## Important

- Do NOT update docs speculatively — only reflect actual changes.
- Do NOT rewrite large sections — make surgical edits.
- Preserve existing formatting and conventions in each file.
