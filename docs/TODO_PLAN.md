# Open TODO Plan — DoD Budget Analysis

> **Generated:** 2026-04-02 (updated after comprehensive audit)
> **Purpose:** Complete inventory of all remaining work items, organized for parallel sub-agent execution.

---

## Executive Summary

| Priority | Count | Description |
|----------|-------|-------------|
| **HIGH — Data Quality (DB)** | 10 | Round 1 open issues requiring pipeline/DB fixes |
| **HIGH — Code TODOs** | 2 (DONE) | PDF-only PE titles and R-1 funding rows |
| **MEDIUM — Data Quality** | 5 | Pipeline gaps: PE numbers, descriptions, FY coverage |
| **MEDIUM — Code TODOs** | 1 (DONE) | Explorer PE number search fallback |
| **LOW — Code TODOs** | 5 (3 DONE) | Pipeline fixes and UI polish |
| **LOW — UX/Frontend** | 3 | Service normalization, tag quality, inline styles |
| **DEFERRED** | 6 | Require external resources (hosting, domain, launch) |
| **Total** | **32** | 6 code TODOs done, 20 open, 6 deferred |

---

## 1. NOTICED ISSUES — Open Database & Pipeline Issues

These are from `docs/NOTICED_ISSUES.md` — issues observed against the live database
that require pipeline re-runs, migrations, or data fixes. **Many share root causes.**

### 1a. Round 1 — Open (Root Cause: DB/Pipeline)

Most of these were catalogued against the pre-Round-5 database (124K rows). Round 5
dedup reduced to 47K rows and fixed several. The issues below are **still marked [OPEN]**
in NOTICED_ISSUES.md and need verification against the current database.

| Issue # | Problem | Root Cause | Needs DB? |
|---------|---------|------------|-----------|
| **#1** | Fiscal Year dropdown — empty | Reference tables missing or not populated | Yes — run `backfill_reference_tables.py` or verify `budget_cycles` table |
| **#2** | Appropriation dropdown — empty | Reference tables missing | Yes — verify `appropriation_titles` table populated |
| **#3, #20** | Service/Agency duplicates (ARMY/A, NAVY/N, AF/F) | Inconsistent `organization_name` | Yes — **#38 same issue**. Run org normalization in `repair_database.py` |
| **#4** | Exhibit Type showing "c1 — c1" | Fallback when `exhibit_types` reference table missing | Yes — verify `exhibit_types` table has display_name values |
| **#5, #21** | Appropriation donut 100% "Unknown" | `appropriation_code` empty/null | Partially fixed in Round 5 (17.5%→7.4% NULL). Remaining 7.4% need investigation |
| **#6, #14** | Budget by Service large "Unknown" | Blank organization rows | Fixed in Round 5 (311→0 empty). **Verify resolved.** |
| **#7, #17, #22** | Duplicate/repetitive results | Cross-file duplicates | Fixed in Round 5 (124K→47K). **Verify resolved.** |
| **#8** | 73% of rows missing PE numbers | PE numbers only in certain exhibit types | **#53 same issue.** Structural — PE numbers only in R-2/P-5 exhibits. Document as known limitation. |
| **#9, #11** | Slow detail/dashboard | No indexes on filter columns | Fixed in Round 4 (#58 composites). **Verify resolved.** |
| **#10, #25** | Wrong FY attribution (FY1998) | FY derived from source file path | Needs pipeline fix — derive FY from document content, not filepath |
| **#12, #15** | Dashboard empty/broken | Cascading from missing data | **Verify after fixing #1-#6.** |
| **#16, #19** | FY data gap 2000-2009 | Data never downloaded | Known limitation — documents not available. Already in PRD §9. |
| **#18** | Charts defaults to FY 1998 | Sort order bug | Fixed (PR #18). **Verify resolved.** |
| **#23-#24** | Missing FY columns, FY 2000-2011 zero entries | Same root cause as #16 | Known limitation |
| **#26** | Tags dropdown mispositioned | CSS z-index | Fixed (PR #26). **Verify resolved.** |
| **#27** | Tag counts inflated (rdte on 1539/1579) | Over-tagging in enrichment | **#39 same issue.** Pipeline tuning needed. |
| **#28** | Footer FY gap | Data gap display | Known limitation (cosmetic) |

### 1b. Round 3 — Open Data Quality Issues

| Issue # | Problem | Root Cause | Needs DB? |
|---------|---------|------------|-----------|
| **#52** | 2,161 rows NULL `budget_type` despite valid `appropriation_code` | Detail exhibits not backfilled | Fixed in Round 4 (→116 NULL). **Verify resolved.** |
| **#53** | 67% of `budget_lines` have no PE number | Structural — O-1/M-1/P-1 exhibits don't carry PE at line level | Document as known limitation |
| **#55** | 12 PEs without mission descriptions | Pipeline gap — PDFs not parsed for these PEs | Yes — re-run Phase 2 enrichment or investigate missing PDFs |
| **#56** | FY gaps in PE funding matrices | Historical data not linked | Yes — investigate `budget_lines` coverage per PE |
| **#57** | `appropriation_code` NULL rows → "Unknown" | Incomplete parsing | Partially fixed in Round 5 (→7.4%). Further improvement possible |

### 1c. Round 2 — Open UX Issues

| Issue # | Problem | Root Cause | Needs DB? |
|---------|---------|------------|-----------|
| **#38** | Service dropdown — dozens of duplicate entries | `organization_name` not normalized | Yes — same as #3/#20 |
| **#39** | Tags dropdown — 30 options, many meaningless | Enrichment over-tagging | Pipeline Phase 3 tuning |
| **#49** | Excessive inline styles in templates | Ongoing gradual refactor | No — CSS cleanup as files are touched |

---

## 2. Code TODOs — Status

### ~~TODO-H1: Fix R-1 title/description for PDF-only PEs~~ DONE

- **Fix:** `_extract_r1_titles_for_stubs()` added to `api/routes/keyword_search.py`

### ~~TODO-H2: Fix missing R-1 funding for Defense-Wide D8Z PEs~~ DONE

- **Fix:** `_aggregate_r2_funding_into_r1_stubs()` added to `api/routes/keyword_search.py`

### ~~TODO-M1: Explorer PE number search~~ DONE

- **Fix:** Added `pe_index` fallback for PDF-only PEs + 8 tests

### ~~TODO-L1: Pipeline enricher progress reporting~~ DONE

- **Fix:** `_log_progress()` helper integrated into all 5 phases

### ~~TODO-L2: Fix RuntimeWarning~~ DONE

- **Fix:** Lazy `__getattr__` imports in `pipeline/__init__.py`

### ~~TODO-L3: Fix `--with-llm` in Phase 3~~ DONE

- **Fix:** Single `_HAS_ANTHROPIC` flag, checked once at phase entry

### ~~TODO-L4: Fix Phase 3 non-LLM tagging~~ DONE

- **Fix:** Expanded text sources + diagnostic logging

### ~~TODO-L5: Rebuild Cache button~~ DONE

- **Fix:** Button + JS in `templates/hypersonics.html`

### TODO-1.A6: Retry failed downloads (partial)

- **Status:** `_failed_files` list stub in `downloader/gui.py`; CLI `--retry-failures` flag not implemented
- **Files:** `downloader/gui.py`, `dod_budget_downloader.py`

---

## 3. Infrastructure TODOs

### `.github/workflows/deploy.yml` — 4 placeholder TODOs

All marked `[OH MY]` — require cloud platform credentials:
- Line 9: Fill in deployment secrets
- Line 71: Set GHCR_TOKEN or PAT
- Line 151: Update `needs` for chosen deploy job
- Line 160: Replace with actual deployment URL

---

## 4. DEFERRED — Require External Resources

| ID | Task | Blocker |
|----|------|---------|
| OH-MY-007 | Choose hosting platform (Fly.io/Railway/Render) | Cloud account setup |
| OH-MY-008 | Configure CD deployment workflow | Depends on OH-MY-007 + secrets |
| OH-MY-009 | Register domain + configure TLS | Domain registration |
| OH-MY-010 | Lighthouse accessibility audit | Running UI instance |
| OH-MY-011 | Soft launch + collect feedback | Deployed application |
| OH-MY-012 | Public launch + announcement | Depends on OH-MY-011 |

---

## 5. Sub-Agent Execution Plan (Phase 2)

Now that the code TODOs are resolved, the next wave of work is **database verification
and data quality fixes**. These require a live database to test against.

### Agent A: `fix/verify-round5-fixes` (Verification)
Verify that Round 4/5 fixes actually resolved the issues they claimed to:
- **Issues to verify:** #6/14 (org Unknown), #7/17/22 (duplicates), #9/11 (slow queries),
  #18 (FY default), #26 (z-index), #52 (budget_type NULLs)
- **Method:** Run SQL queries from NOTICED_ISSUES.md against the current DB
- **Action:** Mark verified issues as [RESOLVED] in NOTICED_ISSUES.md, or re-open with updated details

### Agent B: `fix/reference-tables-and-dropdowns` (Issues #1, #2, #4)
- Verify `budget_cycles`, `appropriation_titles`, `services_agencies`, `exhibit_types` tables exist and are populated
- If empty, run `backfill_reference_tables.py` or add migration
- Verify frontend dropdowns populate correctly
- **Files:** `backfill_reference_tables.py`, `schema_design.py`, `api/routes/frontend.py`

### Agent C: `fix/organization-normalization` (Issues #3, #20, #38)
- Normalize `organization_name` in `budget_lines`: collapse ARMY/A→Army, NAVY/N→Navy, AF/F→Air Force
- Add normalization to `repair_database.py` or `pipeline/builder.py` ingestion
- Update `services_agencies` reference table
- **Files:** `repair_database.py`, `pipeline/builder.py`

### Agent D: `fix/fy-attribution` (Issues #10, #25)
- Fix FY derived from source file path instead of document content
- Investigate `fiscal_year` column population in `pipeline/builder.py`
- **Files:** `pipeline/builder.py`

### Agent E: `fix/enrichment-quality` (Issues #27, #39, #55)
- Tune tag confidence thresholds to reduce over-tagging
- Investigate 12 PEs without mission descriptions
- **Files:** `pipeline/enricher.py`

### Agent F: `fix/retry-failures-cli` (TODO 1.A6)
- Implement `--retry-failures` CLI flag for `dod_budget_downloader.py`
- Write `failed_downloads.json` structured log
- **Files:** `dod_budget_downloader.py`, `downloader/gui.py`

### Prerequisite: Database availability
Agents A-E need a populated SQLite database. Either:
1. Use the test fixtures (`test_db`, `test_db_excel_only` from `conftest.py`) for structural checks
2. Or have access to a real `dod_budget.sqlite` for data quality verification

---

## Future Directions (from NOTICED_ISSUES.md)

These are documented enhancement ideas, not bugs:
- **Weapon system grouping** — `program_groups` + `pe_group_membership` tables for Spruill charts
- **Timeline view** — Sparkline funding bars in search results
- **Sub-PE tag browsing** — Expand PE cards to show matched sub-projects
