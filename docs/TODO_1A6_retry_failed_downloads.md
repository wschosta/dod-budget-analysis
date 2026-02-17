# Step 1.A6 — Retry Failed Downloads

**Status:** Not started
**Type:** Code modification (AI-agent completable, multi-step)
**Depends on:** None (but complements 1.A3 reliability hardening)

## Task

Add the ability to re-run only previously failed downloads by reading a
structured failure log from the last run. This requires two changes:
upgrading the failure log to include enough detail for replay, and adding
a `--retry-failures` CLI flag.

## Current State

- `_failure_lines` in `GuiProgressTracker` stores `[FAIL] filename` strings
  — display-only, no URL or destination path
- `ProgressTracker` (CLI) has no failure tracking at all
- `file_done()` receives only `(filename, size, status)` — no URL or dest path
- No failure log file is written to disk
- `download_file()` has full context (URL, dest_path, use_browser) but
  doesn't pass it to the tracker on failure

## Sub-tasks

### 1A6a — Structured failure log (prerequisite)

Upgrade failure tracking so each failure records enough info to replay:

1. Add a `_failed_files` list to both `ProgressTracker` and
   `GuiProgressTracker` that stores dicts, not display strings:
   ```python
   {"url": str, "dest": str, "filename": str, "error": str,
    "source": str, "year": str, "use_browser": bool, "timestamp": str}
   ```
2. Change the `file_done()` signature (or add a new `file_failed()` method)
   to accept the full context. Callers in `download_file()` and
   `_browser_download_file()` already have `url`, `dest_path`, and
   `use_browser` available — pass them through.
3. At the end of `main()`, if there were failures, write
   `{output_dir}/failed_downloads.json` containing the list of failure
   dicts. This file is the input for the retry flow.
4. The `show_completion_dialog()` "View Failures" button should be updated
   to also show the URL for each failure (not just filename).

**Agent instructions:**
- Read `download_file()` (~line 1080) and `_browser_download_file()` (~line 780)
  to identify where `file_done(..., "fail")` is called
- Add `url` and `dest_path` params to `file_done()` (optional, default None,
  for backward compatibility) or add a separate `file_failed(url, dest, error)` method
- At the bottom of `main()`, after the summary, serialize `_failed_files` to JSON
- Estimated tokens: ~1200

### 1A6b — `--retry-failures` CLI flag

Add a flag that reads the failure log and re-attempts only those files:

1. Add `--retry-failures [PATH]` argument to the argparse section.
   Default path: `{output_dir}/failed_downloads.json`
2. When `--retry-failures` is used:
   - Read the JSON failure log
   - Skip all discovery/scanning steps
   - Build a file list directly from the failure log entries
   - Set `total_files` to the failure count
   - Iterate through failures calling `download_file()` with the stored
     URL, dest path, and `use_browser` flag
   - Write a new `failed_downloads.json` containing only files that
     failed again (so the user can retry iteratively)
3. Works with both `--no-gui` and GUI modes

**Agent instructions:**
- Add the argparse argument after the existing `--overwrite` flag
- Add a new code path in `main()` (early return) that runs before the
  discovery section: if `args.retry_failures`, load JSON and go straight
  to download loop
- Reuse `download_file()` as-is — it already handles all download strategies
- Estimated tokens: ~1000

### 1A6c — Update GUI completion dialog

Update `show_completion_dialog()` so the "View Failures" window shows the
URL alongside each filename, and add a "Copy retry command" button that
copies a ready-to-paste CLI command to the clipboard:
```
python dod_budget_downloader.py --retry-failures DoD_Budget_Documents/failed_downloads.json
```

**Agent instructions:**
- Read `show_completion_dialog()` (~line 592)
- The `_view_failures()` inner function builds a text widget — update it to
  show `[FAIL] filename\n       URL: https://...` per entry
- Add a `ttk.Button("Copy Retry Command", command=_copy_cmd)` that calls
  `dlg.clipboard_clear(); dlg.clipboard_append(cmd)`
- Estimated tokens: ~500

## Annotations

- Sub-tasks must be done in order: 1A6a first (creates the log), then
  1A6b (consumes it), then 1A6c (optional UX polish)
- **No data processing required** — this is pure code modification
- The failure log JSON format should be documented in a comment at the
  top of the file or in `DATA_SOURCES.md` so future agents know the schema
- Consider: should `--retry-failures` also respect `--sources` and `--years`
  flags to filter which failures to retry? Probably not — the failure log
  is already scoped to a specific run. Keep it simple.
