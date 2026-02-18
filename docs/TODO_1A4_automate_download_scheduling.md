# Step 1.A4 — Automate Download Scheduling

**Status:** Complete
**Type:** Code + Configuration (AI-agent completable)
**Depends on:** 1.A3-a (manifest useful but not blocking)

## User Decisions (RESOLVED)

- **Schedule:** Manual trigger only (`workflow_dispatch`) — no automatic schedule
- **Storage:** Downloaded files NOT committed to repo. Manifest uploaded as artifact.

---

## Sub-tasks

### 1.A4-a — Refactor main() into callable download_all() function
**Type:** AI-agent (refactoring)
**Estimated tokens:** ~500 output

1. Extract download pipeline from `main()` (~lines 1286–1406) into a
   `download_all(years, sources, output_dir, **opts) -> dict` function
2. Function returns summary dict (total, ok, skip, fail)
3. `main()` calls `download_all()` after parsing args
4. Decouples pipeline from CLI/GUI for programmatic use

**File:** `dod_budget_downloader.py`

---

### 1.A4-b — Create CLI-only pipeline wrapper script
**Type:** AI-agent
**Estimated tokens:** ~400 output

1. Implement `scripts/scheduled_download.py` (currently a skeleton)
2. Import and call `download_all()` from the refactored downloader
3. Capture stdout/stderr to timestamped log
4. Exit with non-zero on any failures

**File:** `scripts/scheduled_download.py`

---

### 1.A4-c — Create GitHub Actions workflow
**Type:** AI-agent
**Estimated tokens:** ~600 output

1. Create `.github/workflows/download.yml`
2. Trigger: `workflow_dispatch` only (inputs: years, sources)
3. Steps: checkout, setup-python, install deps + playwright, run script,
   upload manifest as artifact
4. Do NOT commit downloaded files

**File:** `.github/workflows/download.yml`

---

### 1.A4-d — Verify --no-gui flag works without tkinter
**Type:** AI-agent
**Estimated tokens:** ~300 output

1. Verify `--no-gui` flag exists in argparse
2. Ensure `GuiProgressTracker` is not imported/initialized when set
3. Ensure CLI-only mode works in headless environments (CI)

**File:** `dod_budget_downloader.py`

---

## Annotations

- All sub-tasks are AI-agent completable
- 1.A4-a is highest-value (enables programmatic use)
- 1.A4-c depends on 1.A4-b (workflow runs the script)
