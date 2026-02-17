# Step 1.A4 — Automate Download Scheduling

**Status:** Not started
**Type:** Code + Configuration (AI-agent completable)
**Depends on:** 1.A3 (manifest is useful but not blocking)

## Task

Create a repeatable, scriptable download pipeline that can run without GUI
dependency via cron or CI (GitHub Actions).

## Sub-tasks

### 1A4a — CLI-only pipeline script (AI-agent completable)
Create a `scripts/scheduled_download.py` (or shell script) that:
- Calls `dod_budget_downloader.py --years all --sources all --no-gui --output ...`
- Captures stdout/stderr to a log file
- Exits with non-zero status on any failures
- Agent instructions: Write a thin wrapper script. Use `subprocess.run()` or
  just a bash script. Include `--no-gui` flag. Write log to
  `{output_dir}/download_{date}.log`.
  Estimated tokens: ~400

### 1A4b — GitHub Actions workflow (AI-agent completable)
Create `.github/workflows/download.yml` that:
- Runs on a schedule (e.g., weekly or on new fiscal year release)
- Installs dependencies including Playwright Chromium
- Runs the download script
- Commits the manifest to the repo (or uploads as artifact)
- Agent instructions: Write a standard GitHub Actions YAML. Use
  `actions/checkout`, `actions/setup-python`, install deps from
  `requirements.txt`, run `python -m playwright install chromium`,
  run the download script.
  Estimated tokens: ~600

## Annotations

- **USER INTERVENTION:** User should decide the schedule frequency and whether
  downloaded files should be committed to the repo or stored externally
- 1A4a is straightforward; 1A4b needs user input on hosting/artifact strategy
