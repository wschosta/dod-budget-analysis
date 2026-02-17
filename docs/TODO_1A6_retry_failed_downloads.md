# Step 1.A6 — Retry Failed Downloads

**Status:** Not started
**Type:** Code modification (AI-agent, ordered sub-tasks)
**Depends on:** None (complements 1.A3)

## Overview

Add ability to re-run only previously failed downloads by reading a structured
failure log. Requires: upgrading failure tracking, adding `--retry-failures`
CLI flag, and updating the GUI completion dialog.

---

## Sub-tasks

### 1.A6-a — Implement structured failure log
**Type:** AI-agent (prerequisite for b and c)
**Estimated tokens:** ~1200 output

1. Add `_failed_files: list[dict]` to both `ProgressTracker` and `GuiProgressTracker`
2. Each failure: `{url, dest, filename, error, source, year, use_browser, timestamp}`
3. Add `file_failed(url, dest, filename, error, source, year, use_browser)` method
4. In `download_file()` and `_browser_download_file()`: call on exception with full context
5. At end of `main()`: write `{output_dir}/failed_downloads.json` if failures exist
6. Document JSON schema in a comment

**File:** `dod_budget_downloader.py` — modify trackers, download functions, `main()`

---

### 1.A6-b — Add --retry-failures CLI flag
**Type:** AI-agent
**Estimated tokens:** ~1000 output
**Depends on:** 1.A6-a

1. Add `--retry-failures [PATH]` to argparse (default: `{output_dir}/failed_downloads.json`)
2. When set: read JSON, skip discovery/scanning, build file list from failures
3. Iterate with `download_file()` using stored url, dest, use_browser
4. Write new `failed_downloads.json` with only re-failed entries
5. Works with both `--no-gui` and GUI modes

**File:** `dod_budget_downloader.py` — add early-return path in `main()`

---

### 1.A6-c — Update GUI completion dialog for failures
**Type:** AI-agent
**Estimated tokens:** ~500 output
**Depends on:** 1.A6-a

1. "View Failures" shows: `[FAIL] filename\n       URL: https://...`
2. Add "Copy Retry Command" button
3. Command: `python dod_budget_downloader.py --retry-failures {path}`

**File:** `dod_budget_downloader.py` — modify `show_completion_dialog()`

---

## Annotations

- **Ordered:** 1.A6-a → 1.A6-b → 1.A6-c
- No data processing required — pure code modification
