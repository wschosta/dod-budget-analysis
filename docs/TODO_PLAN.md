# Open TODO Plan — DoD Budget Analysis

> **Last Updated:** 2026-04-02
> **Purpose:** Canonical list of all remaining work, organized into agent-executable groups A–G.
> **Usage:** Tell an agent _"Execute TODO groups A–G from `docs/TODO_PLAN.md`"_ or target a single group: _"Execute TODO group C"_.

---

## Quick Reference

| Group | Branch Name | Focus | Issues | Needs DB? |
|-------|------------|-------|--------|-----------|
| **A** | `fix/verify-round5-fixes` | Verify prior fixes landed | #6, #7, #9, #12, #15, #18, #26, #52 | Yes |
| **B** | `fix/reference-tables` | Populate reference tables & dropdowns | #1, #2, #4, #5, #21, #57 | Yes |
| **C** | `fix/org-normalization` | Normalize organization names | #3, #20, #38 | Yes |
| **D** | `fix/fy-attribution` | Fix fiscal year attribution | #10, #25, #56 | Yes |
| **E** | `fix/enrichment-quality` | Tune tags, fill missing descriptions | #27, #39, #55 | Yes |
| **F** | `fix/retry-failures-cli` | ✅ Complete (2026-04-02) — Download retry CLI | ROADMAP 1.A6 | No |
| **G** | `infra/deploy-and-launch` | Hosting, domain, CD, accessibility, launch | OH-MY-007–012 | No (needs credentials) |

**Parallelism:** A runs first (verification). B–F can run in parallel after A confirms the current DB state. F is independent (no DB). G requires user infrastructure decisions before an agent can execute.

---

## Completed Work (for reference)

All 8 code TODOs from the 2026-04-01 sprint are resolved:

| ID | Task | Resolution |
|----|------|------------|
| ~~TODO-H1~~ | R-1 titles for PDF-only PEs | `_extract_r1_titles_for_stubs()` in `keyword_search.py` |
| ~~TODO-H2~~ | R-1 funding for D8Z PEs | `_aggregate_r2_funding_into_r1_stubs()` in `keyword_search.py` |
| ~~TODO-M1~~ | Explorer PE number search | `pe_index` fallback + 8 tests |
| ~~TODO-L1~~ | Enricher progress reporting | `_log_progress()` in all 5 phases |
| ~~TODO-L2~~ | RuntimeWarning fix | Lazy `__getattr__` imports in `pipeline/__init__.py` |
| ~~TODO-L3~~ | Anthropic import consolidation | Single `_HAS_ANTHROPIC` flag |
| ~~TODO-L4~~ | Rule-based tagger fix | Expanded text sources + diagnostics |
| ~~TODO-L5~~ | Rebuild Cache button | Button + JS in `templates/hypersonics.html` |

---

## Group A: Verify Prior Fixes

**Branch:** `fix/verify-round5-fixes`
**Goal:** Confirm that Round 4/5 database fixes actually resolved the issues they claimed to. Update `docs/NOTICED_ISSUES.md` with results.

### Issues to verify

| Issue | Claim | Verification query |
|-------|-------|-------------------|
| **#6, #14** | Org "Unknown" eliminated (311→0 empty rows) | `SELECT COUNT(*) FROM budget_lines WHERE organization_name IS NULL OR organization_name = ''` — expect 0 |
| **#7, #17, #22** | Duplicates eliminated (124K→47K) | `SELECT COUNT(*) FROM budget_lines` — expect ~47K. `SELECT pe_number, line_item, fiscal_year, COUNT(*) c FROM budget_lines GROUP BY 1,2,3 HAVING c > 1` — expect 0 rows |
| **#9, #11** | Composite indexes exist | `.indexes budget_lines` — expect `idx_bl_pe_fy`, `idx_bl_org_fy`, `idx_bl_bt_fy`, `idx_bl_et_fy` |
| **#18** | Charts default to most recent FY | Check `static/js/charts.js` or `api/routes/frontend.py` for sort order |
| **#26** | Tags dropdown z-index fixed | Check CSS in `templates/programs.html` or `static/css/` for z-index fix |
| **#52** | budget_type NULLs reduced | `SELECT COUNT(*) FROM budget_lines WHERE budget_type IS NULL` — expect ≤116 |

### Actions
1. Run each verification query against `dod_budget.sqlite`
2. For each issue:
   - If confirmed fixed → change status in `docs/NOTICED_ISSUES.md` from `[OPEN]` to `[RESOLVED — verified 2026-04-XX]`
   - If NOT fixed → update the issue with current numbers and leave `[OPEN]`
3. Commit changes to `docs/NOTICED_ISSUES.md`

### Files
- `docs/NOTICED_ISSUES.md` (update statuses)

---

## Group B: Reference Tables & Dropdowns

**Branch:** `fix/reference-tables`
**Goal:** Ensure all 4 reference tables are populated so frontend dropdowns work. Also reduce remaining appropriation_code NULLs.

### Issues addressed
- **#1** — Fiscal Year dropdown empty (`budget_cycles` table missing/empty)
- **#2** — Appropriation dropdown empty (`appropriation_titles` table missing/empty)
- **#4** — Exhibit Type shows "c1 — c1" (`exhibit_types` table missing display_name)
- **#5, #21** — Appropriation donut 100% "Unknown" (7.4% NULL `appropriation_code`)
- **#57** — `appropriation_code` NULL rows fall through to "Unknown"

### Steps
1. Check if reference tables exist and are populated:
   ```sql
   SELECT name FROM sqlite_master WHERE type='table' AND name IN ('budget_cycles','appropriation_titles','services_agencies','exhibit_types');
   SELECT COUNT(*) FROM budget_cycles;
   SELECT COUNT(*) FROM appropriation_titles;
   SELECT COUNT(*) FROM services_agencies;
   SELECT COUNT(*) FROM exhibit_types;
   ```
2. If empty, run `python backfill_reference_tables.py` or call `repair_database.py` which includes reference table population
3. Verify `exhibit_types` has meaningful `display_name` values (not just the raw code repeated)
4. For remaining `appropriation_code` NULLs (7.4%):
   - Query: `SELECT exhibit_type, COUNT(*) FROM budget_lines WHERE appropriation_code IS NULL GROUP BY exhibit_type ORDER BY 2 DESC`
   - Extend the keyword matching in `repair_database.py` if patterns emerge
5. Verify frontend dropdowns populate by checking the API responses:
   - `GET /api/v1/reference/fiscal_years`
   - `GET /api/v1/reference/appropriations`
   - `GET /api/v1/reference/exhibit_types`
   - `GET /api/v1/reference/services`

### Files
- `backfill_reference_tables.py`
- `repair_database.py` (appropriation keyword matching)
- `schema_design.py` (if migrations needed)
- `api/routes/frontend.py` (verify dropdown population)
- `docs/NOTICED_ISSUES.md` (update statuses)

### Tests
```bash
python -m pytest tests/ -k "reference or aggregation" -v
```

---

## Group C: Organization Name Normalization

**Branch:** `fix/org-normalization`
**Goal:** Collapse duplicate organization names so dropdowns and charts show clean entries.

### Issues addressed
- **#3, #20** — Service/Agency duplicates in dropdowns (ARMY/A, NAVY/N, AF/F — 57 entries)
- **#38** — Same root cause; dozens of dropdown entries

### Current state
Round 5 fixed empty `organization_name` (311→0) but did NOT normalize variant spellings.
Common duplicates: `ARMY`/`A`, `NAVY`/`N`, `AF`/`F`, `Air Force`/`AF`, plus case variants.

### Steps
1. Audit current values:
   ```sql
   SELECT organization_name, COUNT(*) FROM budget_lines GROUP BY organization_name ORDER BY 2 DESC;
   ```
2. Define normalization mapping. Check if `repair_database.py` already has an org normalization step (search for `organization` or `normalize`). If so, extend it. If not, add one:
   ```python
   ORG_NORMALIZATION = {
       'A': 'Army', 'ARMY': 'Army',
       'N': 'Navy', 'NAVY': 'Navy',
       'F': 'Air Force', 'AF': 'Air Force',
       # ... add all variants found in step 1
   }
   ```
3. Apply via UPDATE statements:
   ```sql
   UPDATE budget_lines SET organization_name = ? WHERE organization_name = ?
   ```
4. Update `services_agencies` reference table to match normalized names
5. **Also add normalization to the ingestion pipeline** (`pipeline/builder.py`) so future builds produce clean names. Search for where `organization_name` is set during parsing and add a normalization step.

### Files
- `repair_database.py` (add/extend org normalization)
- `pipeline/builder.py` (add normalization at ingestion time)
- `docs/NOTICED_ISSUES.md` (update #3, #20, #38 statuses)

### Tests
```bash
python -m pytest tests/ -k "repair or organization" -v
```

---

## Group D: Fiscal Year Attribution

**Branch:** `fix/fy-attribution`
**Goal:** Fix rows where `fiscal_year` is derived from the source file path instead of document content.

### Issues addressed
- **#10, #25** — Data showing FY1998 when it shouldn't; FY derived from file path
- **#56** — FY gaps in PE funding matrices

### Root cause
`pipeline/builder.py` extracts `fiscal_year` from the source file's directory path (e.g., `FY1998\PB\Defense_wide\...`). If a file is stored in the wrong FY folder, all its rows get the wrong FY.

### Steps
1. Investigate how `fiscal_year` is populated:
   ```bash
   grep -n "fiscal_year" pipeline/builder.py | head -30
   ```
2. Check for FY extraction from document content (sheet names, column headers, or cell values). Many exhibits contain the FY in their column headers (e.g., "FY 2025 Request").
3. Add a validation/correction step:
   - If the file path says FY1998 but the column headers contain FY2024/2025/2026, trust the content
   - Log mismatches for review
4. For #56 (FY gaps): investigate whether PEs with gaps have data in `budget_lines` that's attributed to the wrong FY:
   ```sql
   SELECT pe_number, fiscal_year, COUNT(*) FROM budget_lines
   WHERE pe_number IN (SELECT pe_number FROM pe_index WHERE fiscal_years LIKE '%2025%')
   GROUP BY 1, 2 ORDER BY 1, 2;
   ```

### Files
- `pipeline/builder.py` (FY extraction logic)
- `docs/NOTICED_ISSUES.md` (update #10, #25, #56 statuses)

### Tests
```bash
python -m pytest tests/ -k "fiscal_year or builder" -v
```

---

## Group E: Enrichment Quality

**Branch:** `fix/enrichment-quality`
**Goal:** Reduce tag over-indexing and fill gaps in PE descriptions.

### Issues addressed
- **#27** — Tag counts inflated (rdte on 1539/1579 programs)
- **#39** — Tags dropdown has 30 options, many nearly meaningless
- **#55** — 12 PEs without mission descriptions

### Steps for over-tagging (#27, #39)
1. Assess current state:
   ```sql
   SELECT tag, COUNT(*) c FROM pe_tags GROUP BY tag ORDER BY c DESC LIMIT 20;
   SELECT COUNT(DISTINCT pe_number) FROM pe_index;
   ```
2. Tags covering >60% of all PEs are too broad to be useful for filtering. Options:
   - **Raise confidence threshold** — only show tags with confidence ≥ 0.85 in the dropdown (currently shows all)
   - **Narrow keyword rules** — in `pipeline/enricher.py`, tighten the keyword patterns for high-coverage tags
   - **Add a coverage cap** — in the frontend query, filter: `HAVING COUNT(*) < (SELECT COUNT(*) * 0.5 FROM pe_index)`
3. Apply the simplest fix first (confidence threshold in the frontend query), then tune rules if needed.

### Steps for missing descriptions (#55)
1. Find the 12 PEs:
   ```sql
   SELECT pe_number, display_title FROM pe_index
   WHERE pe_number NOT IN (SELECT DISTINCT pe_number FROM pe_descriptions);
   ```
2. Check if these PEs have entries in `pdf_pe_numbers` (they might have PDFs but descriptions weren't extracted):
   ```sql
   SELECT pn.pe_number, COUNT(*) FROM pdf_pe_numbers pn
   WHERE pn.pe_number IN (/* 12 PEs */) GROUP BY 1;
   ```
3. If PDFs exist, re-run Phase 2: `python -m pipeline.enricher --phases 2 --rebuild`
4. If no PDFs exist, these PEs are documentation-only gaps — note in NOTICED_ISSUES.md

### Files
- `pipeline/enricher.py` (tag rules)
- `api/routes/frontend.py` (tag dropdown query — add confidence/coverage filter)
- `docs/NOTICED_ISSUES.md` (update #27, #39, #55 statuses)

### Tests
```bash
python -m pytest tests/ -k "enricher or tag" -v
```

---

## Group F: Download Retry CLI

**Branch:** `fix/retry-failures-cli`
**Goal:** Implement `--retry-failures` flag for the downloader. **Does not require database access.**

### Issue addressed
- **ROADMAP 1.A6** — Retry failed downloads

### Current state
`downloader/gui.py:42` has a `_failed_files: list[dict]` stub that collects failure records during downloads. The CLI flag and JSON log file don't exist yet.

### Steps
1. Read `dod_budget_downloader.py` to understand the CLI argument parsing and download flow
2. Read `downloader/gui.py` to see how `_failed_files` is populated
3. At the end of a download run, write `_failed_files` to `failed_downloads.json`:
   ```json
   [{"url": "...", "dest": "...", "error": "...", "browser": true, "timestamp": "..."}]
   ```
4. Add `--retry-failures` CLI flag to `dod_budget_downloader.py`:
   - Reads `failed_downloads.json`
   - Re-attempts only those files
   - Respects the `browser` flag (use Playwright for browser-required files)
5. Update the GUI completion dialog to show failure count and a "Copy retry command" button

### Files
- `dod_budget_downloader.py` (CLI flag + retry logic)
- `downloader/gui.py` (JSON write + completion dialog update)
- `docs/NOTICED_ISSUES.md` or `docs/ROADMAP.md` (update 1.A6 status)

### Tests
```bash
python -m pytest tests/ -k "download" -v
```

### Resolution
**Status: ✅ Complete (2026-04-02)** — Upon review, all Group F functionality was already implemented:
- `--retry-failures` CLI flag in `downloader/core.py`
- Structured `failed_downloads.json` log with URL, dest, error, browser flag, and timestamp
- GUI completion dialog shows failure count and "Copy retry command" button (`downloader/gui.py`)
- ROADMAP 1.A6 updated to reflect completion.

---

## Known Limitations (not actionable — document only)

These are structural constraints, not bugs. Already documented in `docs/PRD.md` §9.

| Issues | Limitation |
|--------|-----------|
| #8, #53 | 67% of `budget_lines` rows lack PE numbers — O-1/M-1/P-1 exhibits don't carry PE at line level |
| #16, #19, #23, #24, #28 | FY2000-2009 data gap — documents not publicly available in structured format |
| #49 | Excessive inline styles — ongoing gradual refactor, not a discrete fix |

---

## Group G: Deploy & Launch

**Branch:** `infra/deploy-and-launch`
**Goal:** Take the application from localhost to production. **Requires user decisions on hosting, domain, and credentials before an agent can execute.**

### Prerequisites (user must provide)
- Cloud platform account (Fly.io, Railway, Render, or similar)
- Domain name (registered or chosen)
- GitHub secrets configured for CD workflow

### Sub-tasks (sequential — each unblocks the next)

#### G1: Choose hosting platform (OH-MY-007)
1. Evaluate: Fly.io, Railway, Render, AWS ECS, DigitalOcean App Platform
2. Criteria: cost (free tier?), SQLite support (persistent disk), auto-deploy from GitHub, custom domain, HTTPS
3. Recommendation: Fly.io or Railway (both support persistent volumes for SQLite)
4. Write decision record to `docs/HOSTING_DECISION.md`
5. Create account and do a test deploy of the Docker image
- **Files:** `docs/HOSTING_DECISION.md` (new)

#### G2: Configure CD deployment workflow (OH-MY-008)
1. Fill in `.github/workflows/deploy.yml` placeholder TODOs (lines 9, 71, 151, 160)
2. Configure GitHub secrets: `GHCR_TOKEN` (or PAT), platform-specific deploy token
3. Add environment protection rules for production
4. Test: merge to main → auto-deploy within minutes
- **Files:** `.github/workflows/deploy.yml`
- **Depends on:** G1

#### G3: Register domain + configure TLS (OH-MY-009)
1. Register domain (e.g., `dodbudget.org` or similar)
2. Configure DNS to point to hosting platform
3. Enable HTTPS (most platforms provide free TLS via Let's Encrypt)
4. Verify: `curl -I https://custom-domain.com` returns 200
- **Depends on:** G1

#### G4: Lighthouse accessibility audit (OH-MY-010)
1. Run Lighthouse or axe-core against the deployed (or local) UI at `/` and `/hypersonics`
2. Target accessibility score ≥ 90
3. File issues for findings below target; fix critical items inline
4. Update `docs/NOTICED_ISSUES.md` with audit results
- **Files:** templates, CSS
- **Depends on:** G1 (or can run against `localhost:8000`)

#### G5: Soft launch + collect feedback (OH-MY-011)
1. Identify 5-10 target users (analysts, researchers, journalists)
2. Configure feedback form to create GitHub Issues (the `POST /api/v1/feedback` endpoint already exists)
3. Share the URL; monitor for 1-2 weeks; triage issues
- **Depends on:** G2, G3

#### G6: Public launch (OH-MY-012)
1. Review README for public-facing accuracy
2. Verify LICENSE file exists (recommend MIT or public domain for gov data)
3. Create GitHub Release with changelog
4. Write announcement; share on r/dataisbeautiful, Hacker News, civic tech communities
- **Depends on:** G5

---

## Notes for Agents

- **Database path:** `dod_budget.sqlite` (or `APP_DB_PATH` env var)
- **Run tests:** `python -m pytest tests/ --ignore=tests/test_gui_tracker.py --ignore=tests/optimization_validation -q`
- **Lint:** `ruff check . --select=E,W,F --ignore=E501 --exclude=DoD_Budget_Documents`
- **Type check:** `mypy api/ utils/ --ignore-missing-imports`
- **After fixing issues:** Update `docs/NOTICED_ISSUES.md` status markers (`[OPEN]` → `[RESOLVED — ...]`)
- **After completing a group:** Update this file's Quick Reference table with completion date
- **`PE_SUFFIX_PATTERN`** is in `utils/patterns.py` — use for all PE regex
- **Commit format:** `fix(<scope>): <summary> (Group X, issues #N, #M)`
