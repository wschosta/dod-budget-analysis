# Open TODO Plan — DoD Budget Analysis

> **Generated:** 2026-04-02
> **Purpose:** Comprehensive inventory of all remaining work items, organized for parallel sub-agent execution.

---

## Executive Summary

| Priority | Count | Description |
|----------|-------|-------------|
| **HIGH** | 2 | Data correctness — PDF-only PE titles and R-1 funding rows |
| **MEDIUM** | 1 | Feature verification — Explorer PE number search |
| **LOW** | 5 (3 done) | Pipeline fixes and UI polish |
| **DEFERRED** | 6 | Require external resources (hosting, domain, launch) |
| **CLEANUP** | 3 | Inline code TODOs (partially implemented stubs) |
| **Total** | **17** | |

---

## 1. HIGH Priority — Data Quality & Correctness

These directly affect data accuracy on the hypersonics and explorer pages.

### TODO-H1: Fix R-1 title/description for PDF-only PEs

- **Problem:** PEs existing only in PDFs get stub R-1 rows with raw PE number as title (e.g., `0603183D8Z`) instead of the real R-1 title (e.g., "Joint Hypersonic Technology Development").
- **Root cause:** `build_cache_table()` in `api/routes/keyword_search.py` (~line 885) inserts stubs without extracting titles from R-1 PDF pages.
- **Fix:** After stub insertion, scan `pdf_pages` for R-1 pages (via `pdf_pe_numbers`), extract title using `PE\s+(\d{7}PE_SUFFIX_PATTERN)\s*[/:]\s*(.+)` regex, and UPDATE the stub row's `line_item_title`.
- **Files:** `api/routes/keyword_search.py`, `utils/patterns.py`
- **Validation:** `SELECT pe_number, line_item_title FROM hypersonics_cache WHERE pe_number LIKE '%D8Z' AND exhibit_type='r1'` should show real titles.
- **Estimated effort:** Medium (~2h)

### TODO-H2: Fix missing R-1 funding for Defense-Wide D8Z PEs

- **Problem:** D8Z PE stub R-1 rows have NULL funding amounts because they don't exist in `budget_lines`.
- **Fix:** After R-2 PDF mining, aggregate sub-element funding into the R-1 stub: `UPDATE {cache_table} SET fy20XX = (SELECT SUM(fy20XX) FROM {cache_table} WHERE pe_number=? AND exhibit_type='r2') WHERE pe_number=? AND exhibit_type='r1'`.
- **Files:** `api/routes/keyword_search.py` (~line 993, before index creation)
- **Validation:** `SELECT pe_number, fy2024, fy2025, fy2026 FROM hypersonics_cache WHERE pe_number='0603183D8Z' AND exhibit_type='r1'` should show non-NULL totals.
- **Estimated effort:** Medium (~1.5h)
- **Dependency:** Best done after TODO-H1.

---

## 2. MEDIUM Priority — Feature Parity & UX

### TODO-M1: Verify Explorer page PE number search

- **Problem:** Entering a PE number (e.g., `0604030N`) as a keyword on `/explorer` may not return that PE in results.
- **Current state:** `collect_matching_pe_numbers_split()` (~line 143) already has PE detection. May already work.
- **Action:** Verify behavior; if broken, ensure `kw.strip()` before regex match and add `pe_index` fallback for PDF-only PEs.
- **Files:** `api/routes/keyword_search.py` (~line 143-160), `api/routes/explorer.py`
- **Estimated effort:** Low (~1h, mostly verification)

---

## 3. LOW Priority — Pipeline & Infrastructure

### TODO-L1: Pipeline enricher progress reporting

- **Problem:** Inconsistent progress messages across enricher's 5 phases.
- **Fix:** Add uniform progress reporter to each phase's main loop: `Phase X: {completed}/{total} ({pct:.1f}%) | Elapsed: {elapsed} | ETA: {eta}`.
- **Files:** `pipeline/enricher.py` (phases 1-5)
- **Estimated effort:** Low (~1h)

### ~~TODO-L2: Fix RuntimeWarning on `python -m pipeline.enricher`~~ DONE

- **Problem:** `RuntimeWarning: 'pipeline.enricher' found in sys.modules` due to eager import in `pipeline/__init__.py`.
- **Fix:** Replaced eager imports in `pipeline/__init__.py` with lazy `__getattr__`-based imports. `__all__` still exports correctly.
- **Files:** `pipeline/__init__.py`

### ~~TODO-L3: Fix `--with-llm` in Phase 3~~ DONE

- **Problem:** `anthropic package not installed` error partway through LLM tagging despite some batches succeeding.
- **Fix:** Consolidated to single top-of-file `_HAS_ANTHROPIC` flag; check once at `run_phase3()` entry, falls back to rule-based tagging with a warning.
- **Files:** `pipeline/enricher.py`

### ~~TODO-L4: Fix Phase 3 non-LLM tagging (0 rows)~~ DONE

- **Problem:** Rule-based tagger in Phase 3 produces 0 tag rows for 85 PEs.
- **Fix:** `bl_texts` query now concatenates `line_item_title`, `budget_activity_title`, and `account_title` (was only using `line_item_title`). Added diagnostic logging: summary stats after rule-based pass and per-PE `logger.debug()` showing matched tags.
- **Files:** `pipeline/enricher.py`

### TODO-L5: Add Rebuild Cache button to Hypersonics page

- **Problem:** No UI way to trigger cache rebuild; only via API or script.
- **Fix:** Add button + JS `rebuildCache()` calling `POST /api/v1/hypersonics/rebuild`. Endpoint may already exist.
- **Files:** `templates/hypersonics.html`, `api/routes/hypersonics.py`
- **Estimated effort:** Low (~30min)

---

## 4. DEFERRED — Require External Resources

These are blocked on hosting/domain/deployment decisions and cannot be completed by code-only agents.

| ID | Task | Blocker |
|----|------|---------|
| OH-MY-007 | Choose hosting platform (Fly.io/Railway/Render) | Cloud account setup |
| OH-MY-008 | Configure CD deployment workflow | Depends on OH-MY-007 + secrets |
| OH-MY-009 | Register domain + configure TLS | Domain registration |
| OH-MY-010 | Lighthouse accessibility audit | Running UI instance |
| OH-MY-011 | Soft launch + collect feedback | Deployed application |
| OH-MY-012 | Public launch + announcement | Depends on OH-MY-011 |

---

## 5. CLEANUP — Inline Code TODOs (Stubs Already Implemented)

These are partial implementations referenced by inline comments. They represent incremental improvements, not bugs.

| Location | Reference | Status | Action |
|----------|-----------|--------|--------|
| `pipeline/builder.py:877` | TODO 1.B3-d | Implemented — `_EXHIBIT_BUDGET_TYPE` mapping exists | Mark as done |
| `pipeline/builder.py:1244` | TODO 1.B3-b | Implemented — `_detect_currency_year()` call exists | Mark as done |
| `downloader/gui.py:42` | TODO 1.A6-a | Stub exists — `_failed_files` list populated | Tied to ROADMAP 1.A6 (retry-failures CLI flag) |

---

## 6. Stale TODO Blocks to Remove

These files have empty "TODOs for this file" headers with no active items:

| File | Action |
|------|--------|
| `utils/validation.py` (lines 8-12) | Remove empty TODO block |
| `utils/database.py` (lines 8-13) | Remove empty TODO block (only DONE item) |
| `utils/formatting.py` (lines 8-12) | Remove empty TODO block |
| `utils/config.py` (lines 8-12) | Remove empty TODO block |
| `pipeline/db_validator.py` (lines 14-22) | Remove empty TODO block (only DONE items) |
| `pipeline/enricher.py` (lines 17-32) | Remove completed LION TODO block |

---

## Sub-Agent Execution Plan

Recommended parallel agent assignments:

### Agent 1: `fix/hypersonics-pdf-pe-titles` (TODO-H1 + TODO-H2)
- Both items modify `api/routes/keyword_search.py` in the cache-build flow
- H1 must land before H2 (title extraction before funding aggregation)
- Run tests: `pytest tests/ -k "hypersonics or keyword" -v`

### Agent 2: `fix/enricher-pipeline-bugs` (TODO-L2 + TODO-L3 + TODO-L4)
- All three modify `pipeline/enricher.py` or `pipeline/__init__.py`
- L2 is a quick fix; L3 and L4 require investigation
- Run tests: `pytest tests/ -k "enricher or pipeline" -v`

### Agent 3: `feat/enricher-progress-and-ui` (TODO-L1 + TODO-L5)
- Independent from agents 1 and 2
- L1: `pipeline/enricher.py` progress reporting
- L5: `templates/hypersonics.html` + verify API endpoint
- Run tests: `pytest tests/ -k "hypersonics or frontend" -v`

### Agent 4: `verify/explorer-pe-search` (TODO-M1)
- Verification-first task — may require no code changes
- Independent from all other agents
- Run tests: `pytest tests/ -k "explorer" -v`

### Sequential (user-driven): Deferred items (OH-MY-007 through OH-MY-012)
- Require hosting platform decision and credentials
- Cannot be parallelized with code agents

---

## ROADMAP Status Corrections

Items in ROADMAP.md that need status updates:

| Item | Current Status | Correct Status |
|------|---------------|----------------|
| 1.A6 (Retry failed downloads) | "⚠️ Not started" | Partially started — `_failed_files` stub in `downloader/gui.py` |
| 1.B3 (Normalize monetary values) | "🔄 In Progress" | Mostly Complete — currency-year detection implemented (TODO 1.B3-b done), budget_type mapping done (TODO 1.B3-d done) |
| Test suite count | "1,248 tests" | Needs verification (may have grown) |
