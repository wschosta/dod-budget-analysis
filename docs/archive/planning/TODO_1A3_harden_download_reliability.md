# Step 1.A3 — Harden Download Reliability

**Status:** Complete (1.A3-e skipped — requires live WAF environment)
**Type:** Code modification (multi-step, mostly AI-agent)
**Depends on:** None

## Overview

Improve retry logic, add file verification, implement a download manifest,
and handle WAF/CAPTCHA challenges gracefully.

---

## Sub-tasks

### 1.A3-a — Add download manifest generation
**Type:** AI-agent
**Estimated tokens:** ~800 output

1. Add `_write_manifest(all_files, output_dir, tracker)` function
2. Before download loop: write `manifest.json` with status "pending" per file
3. After each download: update entry with status, size, duration
4. At end of `main()`: write final manifest with summary
5. Schema: `{"files": [{url, dest, source, year, status, size, sha256, duration_s}], "summary": {total, ok, skip, fail}}`

**File:** `dod_budget_downloader.py` — add near line ~1250

---

### 1.A3-b — Add file magic-byte verification
**Type:** AI-agent
**Estimated tokens:** ~500 output

1. Add `_verify_download(dest_path: Path) -> bool`
2. Check: `%PDF` for .pdf, `PK` (ZIP) for .xlsx/.zip, non-zero size
3. Call after every successful write in `download_file()` and `_browser_download_file()`
4. On failure: log warning, delete corrupt file, mark "fail" in manifest

**File:** `dod_budget_downloader.py` — add near `_clean_file_entry()`

---

### 1.A3-c — Add SHA-256 checksums to manifest
**Type:** AI-agent
**Estimated tokens:** ~400 output
**Depends on:** 1.A3-a

1. Compute `hashlib.sha256` after each download, store in manifest
2. On subsequent runs: compare hashes, redownload on mismatch

**File:** `dod_budget_downloader.py` — modify `download_file()`

---

### 1.A3-d — Add application-level retry with backoff
**Type:** AI-agent
**Estimated tokens:** ~500 output

1. Wrap `download_file()` try/except in retry loop (max 3, delays 2s/4s/8s)
2. Add `--retries` CLI flag (default: 2)
3. Log each retry attempt
4. Apply same pattern to `_browser_download_file()`

**File:** `dod_budget_downloader.py`

---

### 1.A3-e — Add WAF/CAPTCHA detection
**Type:** AI-agent + ENVIRONMENT TESTING
**Estimated tokens:** ~500 output

1. Add `_detect_waf_block(response_or_page) -> str | None`
2. Check for: HTTP 403 + "Access Denied", CAPTCHA text, HTML when expecting
   binary, Cloudflare challenge markers
3. When detected: log specific warning, mark "waf_blocked" in manifest

**ENVIRONMENT TESTING:** Must test against live WAF-protected sites.

---

### 1.A3-f — Handle ZIP extraction
**Type:** AI-agent
**Estimated tokens:** ~500 output

1. Add `--extract-zips` CLI flag (default: False)
2. After downloading a `.zip`: extract with `zipfile.extractall()`
3. Log extracted files, add to manifest

---

### 1.A3-g — Consolidate User-Agent string
**Type:** AI-agent (quick refactoring)
**Estimated tokens:** ~200 output

1. Extract User-Agent to `USER_AGENT` constant
2. Use in both `HEADERS` dict and `_get_browser_context()`
3. Remove duplication (lines ~203 and ~700)

---

### 1.A3-h — Extract shared ProgressTracker helpers
**Type:** AI-agent (refactoring)
**Estimated tokens:** ~400 output

1. Create `_ProgressBase` class or module-level functions for `_format_bytes()`, `_elapsed()`
2. Have both `ProgressTracker` and `GuiProgressTracker` use shared implementations
3. Eliminate duplicated code

---

## Annotations

- Sub-tasks 1.A3-a through 1.A3-d and 1.A3-f through 1.A3-h are pure code
- Sub-task 1.A3-e needs live WAF testing for pattern verification
- Manifest (1.A3-a) is prerequisite for retry (1.A6) and checksums (1.A3-c)
- These improvements make the downloader CI-ready for 1.A4
