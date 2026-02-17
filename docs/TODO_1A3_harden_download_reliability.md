# Step 1.A3 — Harden Download Reliability

**Status:** Not started
**Type:** Code modification (AI-agent completable, multi-step)
**Depends on:** None (builds on existing `dod_budget_downloader.py`)

## Task

Improve the downloader's robustness: better retry logic, WAF/CAPTCHA
resilience, file verification, and a download manifest.

## Sub-tasks

### 1A3a — Download manifest (AI-agent completable)
Create a `download_manifest.json` written after each run that records:
- Every file attempted: URL, destination path, status (ok/skip/fail), size, timestamp
- Summary totals
- Agent instructions: Add a `_write_manifest()` function called at end of `main()`.
  Read the tracker's state to build the manifest dict. Write to `{output_dir}/manifest.json`.
  Estimated tokens: ~800

### 1A3b — File size/checksum verification (AI-agent completable)
After each download, verify the file is valid:
- Non-zero size
- For PDFs: check the `%PDF` magic bytes header
- For XLSX: check the PK (ZIP) magic bytes header
- Log verification failures
- Agent instructions: Add a `_verify_download(dest_path)` function called after
  successful write in `download_file()`. Return bool. On failure, mark as "fail"
  and delete the corrupt file.
  Estimated tokens: ~600

### 1A3c — Improved retry with backoff (AI-agent completable)
The existing retry adapter uses `max_retries=3` with `backoff_factor=1`.
Review and improve:
- Increase backoff factor for WAF-heavy sites
- Add per-file retry (current code retries at the HTTP level but not at the
  download-file level — a partial download that fails mid-stream is not retried)
- Agent instructions: Wrap the download logic in `download_file()` with a
  retry loop (max 2 retries with 5s delay). Keep the existing `requests.adapters.Retry`
  for connection-level retries.
  Estimated tokens: ~500

### 1A3d — WAF/CAPTCHA detection (needs environment testing)
Some government sites may present CAPTCHAs or challenge pages instead of files.
- Detect when a response is an HTML challenge page instead of the expected file
- Log the event and skip gracefully rather than saving the HTML as a PDF
- **ENVIRONMENT TESTING:** This requires running downloads against live government
  sites to observe what challenge pages look like. Save sample challenge HTML
  in `tests/fixtures/` for future automated detection.
- Agent instructions for future session: Run a download against each source,
  capture any non-file HTTP responses, and build detection logic based on
  response content-type and body patterns.

## Annotations

- Sub-tasks 1A3a–1A3c are independently completable by an AI agent
- Sub-task 1A3d requires live network testing against government WAFs —
  save for a session with network access and document findings
