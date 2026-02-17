# Step 1.A4 — Automate Download Scheduling

**Status:** Not started
**Type:** Code + Configuration (AI-agent completable)
**Depends on:** 1.A3 (manifest is useful but not blocking)

## User Decisions (RESOLVED)

- **Schedule:** Manual trigger only (`workflow_dispatch`) — no automatic schedule
- **Storage:** Downloaded files are NOT committed to the repo. The workflow
  uploads the download manifest as a GitHub Actions artifact for tracking.

## Task

Create a repeatable, scriptable download pipeline that can run without GUI
dependency, triggered manually via GitHub Actions or local CLI.

## Sub-tasks

### 1A4a — CLI-only pipeline script (AI-agent completable)
Create a `scripts/scheduled_download.py` (or shell script) that:
- Calls `dod_budget_downloader.py --years all --sources all --no-gui --output ...`
- Captures stdout/stderr to a timestamped log file
- Exits with non-zero status on any failures
- Agent instructions: Write a thin wrapper script. Use `subprocess.run()` or
  just a bash script. Include `--no-gui` flag. Write log to
  `{output_dir}/download_{date}.log`.
  Estimated tokens: ~400

### 1A4b — GitHub Actions workflow (AI-agent completable)
Create `.github/workflows/download.yml` that:
- Triggered by `workflow_dispatch` only (manual trigger, no cron schedule)
- Accepts inputs: fiscal years (default: "all"), sources (default: "all")
- Installs dependencies including Playwright Chromium
- Runs the download script from 1A4a
- Uploads the manifest (`manifest.json`) as a GitHub Actions artifact
- Does NOT commit downloaded files to the repo
- Agent instructions: Write a standard GitHub Actions YAML. Use
  `actions/checkout`, `actions/setup-python`, install deps from
  `requirements.txt`, run `python -m playwright install chromium`,
  run the download script, use `actions/upload-artifact` for manifest.
  Estimated tokens: ~600

## Annotations

- ~~**USER INTERVENTION:** User should decide the schedule frequency and whether
  downloaded files should be committed to the repo or stored externally~~
  **RESOLVED:** Manual trigger only, files stored externally, manifest as artifact.
- Both sub-tasks are independently completable by an AI agent
