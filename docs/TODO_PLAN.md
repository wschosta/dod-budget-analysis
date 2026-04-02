# Open TODO Plan — DoD Budget Analysis

> **Last Updated:** 2026-04-02
> **Purpose:** Canonical list of remaining work. Single source of truth for task execution.
> **Reference:** See `docs/NOTICED_ISSUES.md` for issue details and root cause analysis.

---

## Quick Reference

| Group | Focus | Code Status | What Remains |
|-------|-------|-------------|-------------|
| **A** | Verify prior fixes | ✅ Code complete | DB verification only |
| **B** | Reference tables & dropdowns | ✅ Code complete | DB verification only |
| **C** | Org name normalization | ✅ Code complete | DB verification only |
| **D** | FY attribution | ⚠️ Partial | Mismatch logs but no auto-correction |
| **E** | Enrichment quality | ✅ Code complete | Tag filtering + description fallback done; #27 pipeline-level deferred |
| **F** | Download retry CLI | ✅ Complete | Done (2026-04-02) |
| **G** | Deploy & launch | ❌ Blocked | Needs user infrastructure decisions |

---

## Completed Groups

### Group F: Download Retry CLI ✅
Fully implemented. `--retry-failures` CLI flag, `failed_downloads.json` log, GUI retry command copy button.
Tests: `tests/test_downloader_group/test_retry_failures.py` (16 tests).

---

## Code-Complete Groups (DB Verification Only)

These groups have all fixes implemented in code. They only need someone to run the
verification queries against `dod_budget.sqlite` and update `docs/NOTICED_ISSUES.md`.

### Group A: Verify Prior Fixes
**NOTICED_ISSUES refs:** ~~#6~~, ~~#7~~, #9, #18, #26, ~~#52~~

All fixes are in the codebase. Issues #6, #7, #52 were resolved in Rounds 4-5 and
confirmed with ingestion-time fixes (2026-04-02). Remaining items (#9, #18, #26) are
code-verified but need DB confirmation.

- Org normalization: `utils/normalization.py` (94 mappings), `repair_database.py:step_3`
- Deduplication: `pipeline/builder.py` (PARTITION BY 7 cols + unique index)
- Composite indexes: `pipeline/builder.py`, `repair_database.py:step_5`
- Charts FY sort: `api/routes/frontend.py:540` (reversed list)
- Z-index fix: `static/css/main.css` (Issue #26 stacking context)
- budget_type backfill: `pipeline/builder.py` (ingestion-time) + `scripts/fix_budget_types.py` (migration)

**Verification queries** (run against dod_budget.sqlite):
```sql
-- #9: Indexes exist
SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_bl_%';

-- #18: FY sort (code check only — verified in api/routes/frontend.py:540)

-- #26: Z-index (CSS check only — verified in static/css/main.css)

-- budget_type NULLs (should be even fewer after ingestion fix)
SELECT COUNT(*) FROM budget_lines WHERE budget_type IS NULL;
-- expect ≤116
```

**After verification:** Update `docs/NOTICED_ISSUES.md` — change `[CODE COMPLETE]` to `[RESOLVED — verified YYYY-MM-DD]`.

---

### Group B: Reference Tables & Dropdowns
**NOTICED_ISSUES refs:** #1, #2, #4, ~~#5~~, #21, ~~#57~~

All fixes implemented:
- Reference table DDL + seed data: `pipeline/schema.py` (22 services, 7 appropriations, 11 exhibits, 5 budget cycles)
- Display name fallback (#4): `api/routes/frontend.py:147-179` (`_clean_display()`)
- FY dropdown (#1): `api/routes/frontend.py:182-213` (queries budget_lines directly)
- Appropriation backfill: `repair_database.py:153-216` (3-strategy matching)
- Repair automation: `repair_database.py` (7-step process)

**Verification queries:**
```sql
SELECT COUNT(*) FROM budget_cycles;              -- expect 5
SELECT COUNT(*) FROM appropriation_titles;       -- expect ~225
SELECT COUNT(*) FROM services_agencies;          -- expect 22+
SELECT COUNT(*) FROM exhibit_types;              -- expect 11+
SELECT COUNT(*) FROM budget_lines WHERE appropriation_code IS NULL; -- expect ~3,531
```

**After verification:** Update `docs/NOTICED_ISSUES.md`.

---

### Group C: Organization Name Normalization
**NOTICED_ISSUES refs:** #3, #20, #38

All fixes implemented:
- Central mapping: `utils/normalization.py` — 94 org variants -> canonical forms
- Pipeline integration: `pipeline/builder.py` uses `ORG_MAP` at ingestion
- Repair script: `repair_database.py:step_3` — batch CASE WHEN updates
- Reference table: `pipeline/schema.py` — 22 canonical services/agencies

**Verification query:**
```sql
SELECT organization_name, COUNT(*) FROM budget_lines
GROUP BY organization_name ORDER BY 2 DESC;
-- expect canonical names only (Army, Navy, Air Force, etc.)
```

**After verification:** Update `docs/NOTICED_ISSUES.md`.

---

### Group E: Enrichment Quality ✅
**NOTICED_ISSUES refs:** ~~#27~~ (mitigated), ~~#39~~, ~~#55~~

**All code fixes applied (2026-04-02):**
- ~~Tag filtering in API~~ ✅ `min_confidence` (0.85) and `max_coverage` (0.5) params in `api/routes/pe.py`
- ~~Description gap-fill~~ ✅ Phase 2 fallback in `pipeline/enricher.py` synthesizes descriptions from budget_lines
- **#27 (pipeline over-tagging):** Mitigated at API level by confidence/coverage filtering. Further pipeline-level taxonomy tightening deferred — low priority since API filtering is effective

**Verification queries** (run against dod_budget.sqlite):
```sql
-- Confirm tag filtering works (should exclude broad tags)
SELECT tag, COUNT(*) c FROM pe_tags WHERE confidence >= 0.85
GROUP BY tag ORDER BY c DESC LIMIT 20;

-- Confirm no PEs without descriptions
SELECT COUNT(*) FROM pe_index
WHERE pe_number NOT IN (SELECT DISTINCT pe_number FROM pe_descriptions);
-- expect 0
```

---

## Partially Implemented Groups

### Group D: Fiscal Year Attribution
**NOTICED_ISSUES refs:** #10, #25, #56

**What exists:**
- FY extraction from file path: `pipeline/builder.py:1663-1673`
- FY mismatch detection: `pipeline/builder.py:1213-1222` (logs warning, prefers sheet value)
- FY validation at download: `downloader/metadata.py:273-285` (`validate_fy_match`)

**What's missing:**
- Auto-correction when file-path FY disagrees with content FY (currently only logs)
- Investigation of PE FY gaps (#56)

**Files to modify:**
- `pipeline/builder.py` (add correction logic)
- `docs/NOTICED_ISSUES.md` (update #10, #25, #56)

**Needs DB:** Yes — to verify FY attribution and investigate gaps

**Verification queries:**
```sql
-- Check for FY mismatches
SELECT pe_number, fiscal_year, COUNT(*) FROM budget_lines
WHERE pe_number IN (SELECT pe_number FROM pe_index WHERE fiscal_years LIKE '%2025%')
GROUP BY 1, 2 ORDER BY 1, 2;
```

**Tests:**
```bash
python -m pytest tests/ -k "fiscal_year or builder" -v
```

---

## Blocked Groups

### Group G: Deploy & Launch
**Blocked on:** User infrastructure decisions (hosting platform, domain, credentials)

Scaffolding exists:
- Docker: `Dockerfile` (production), `Dockerfile.multistage` (embedded DB)
- CI/CD template: `.github/workflows/deploy.yml` (4 TODO placeholders)
- Health checks, monitoring, backup scripts all in place

Sub-tasks (sequential):
1. **G1** Choose hosting platform -> create `docs/HOSTING_DECISION.md`
2. **G2** Configure CD workflow -> fill deploy.yml TODOs + GitHub secrets
3. **G3** Register domain + TLS
4. **G4** Accessibility audit (Lighthouse score >= 90)
5. **G5** Soft launch to 5-10 users
6. **G6** Public launch + announcement

---

## Known Limitations (not actionable)

Documented in `docs/PRD.md` §9 and `docs/NOTICED_ISSUES.md`:
- #8, #53: 67% of rows lack PE numbers (O-1/M-1/P-1 exhibits don't carry PE)
- #16, #19, #28: FY2000-2009 data gap (documents not publicly available)
- #49: Inline styles (ongoing gradual refactor)

---

## Completed Work Reference

| ID | Task | Resolution |
|----|------|------------|
| TODO-H1 | R-1 titles for PDF-only PEs | `_extract_r1_titles_for_stubs()` in `keyword_search.py` |
| TODO-H2 | R-1 funding for D8Z PEs | `_aggregate_r2_funding_into_r1_stubs()` in `keyword_search.py` |
| TODO-M1 | Explorer PE number search | `pe_index` fallback + 8 tests |
| TODO-L1 | Enricher progress reporting | `_log_progress()` in all 5 phases |
| TODO-L2 | RuntimeWarning fix | Lazy `__getattr__` imports in `pipeline/__init__.py` |
| TODO-L3 | Anthropic import consolidation | Single `_HAS_ANTHROPIC` flag |
| TODO-L4 | Rule-based tagger fix | Expanded text sources + diagnostics |
| TODO-L5 | Rebuild Cache button | Button + JS in `templates/hypersonics.html` |

---

## Notes for Agents

- **Database path:** `dod_budget.sqlite` (or `APP_DB_PATH` env var)
- **Run tests:** `python -m pytest tests/ --ignore=tests/test_gui_tracker.py --ignore=tests/optimization_validation -q`
- **Lint:** `ruff check . --select=E,W,F --ignore=E501 --exclude=DoD_Budget_Documents`
- **Type check:** `mypy api/ utils/ --ignore-missing-imports`
- **After fixing issues:** Update `docs/NOTICED_ISSUES.md` status markers
- **`PE_SUFFIX_PATTERN`** is in `utils/patterns.py`
- **Commit format:** `fix(<scope>): <summary>`
