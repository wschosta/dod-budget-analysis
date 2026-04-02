# Feature Recommendations Review

> **Reviewer:** Claude (claude/review-feature-recommendations-2RFf8)
> **Source:** Merged PR #86 (claude/review-todos-docs-mThIH)
> **Date:** 2026-04-02

---

## Context

PR #86 performed a comprehensive codebase simplify, TODO audit, and documentation
consolidation. It resolved all 8 code TODOs (H1, H2, M1, L1-L5), completed Group F
(download retry CLI), and organized remaining work into Groups A-G in
`docs/TODO_PLAN.md`. This review assesses the outstanding feature recommendations
and their priority.

---

## 1. Documentation Discrepancy Found

**ROADMAP section 4.B2 (Feedback mechanism)** is marked "Not started" but the feature
is **fully implemented and tested:**

- `api/routes/feedback.py` — POST `/api/v1/feedback` with Pydantic validation (bug/feature/data-issue types)
- `templates/partials/feedback.html` — Accessible modal form integrated into base template
- `tests/test_web_group/test_tiger_feedback.py` — 16 tests covering validation, persistence, UUID tracking
- Stores to local `feedback.json` (no external secrets required)

**Action:** Update ROADMAP 4.B2 to "Complete" (GitHub Issues integration is optional future work).

---

## 2. Remaining Work Assessment

### Groups A-C: DB Verification (LOW EFFORT, HIGH VALUE)

All code is complete. These only need someone to run verification SQL queries against
`dod_budget.sqlite` and update `docs/NOTICED_ISSUES.md` status markers. This is
**purely operational** — no new code needed.

**Recommendation:** Do this as a single batch whenever the production database is
available. Not a feature decision — just housekeeping.

### Group D: Fiscal Year Attribution (MEDIUM EFFORT, MEDIUM VALUE)

**Current state:**
- FY extraction from file paths and sheet names works correctly
- Mismatch detection logs warnings but takes no corrective action
- When sheet FY and directory FY disagree, code prefers the sheet value

**What's proposed:** Auto-correction logic when FY sources disagree.

**Review opinion:** **Defer this.** The current behavior (prefer sheet value, log warning)
is the safer default. Auto-correction risks silently misattributing data. The mismatch
warnings serve as an audit trail. If this becomes a real user-facing problem (wrong FY
shown in results), fix it then with specific cases to test against. Speculative
auto-correction for edge cases is premature.

The FY gap investigation (#56) similarly requires the production database to analyze.
Not actionable without it.

### Group E: Enrichment Quality (LOW EFFORT, HIGH VALUE)

**Current state (after fix):**
- Confidence scoring system works (6 levels: 1.0 to 0.65)
- ~~`api/routes/pe.py` `list_tags()` returns all tags without filtering~~ **Fixed:** `min_confidence` (default 0.85) and `max_coverage` (default 0.5) parameters now filter out low-quality and over-applied tags

**What was proposed and resolved:**
1. ~~Add confidence threshold (`WHERE confidence >= 0.85`) to tag API~~ **Done**
2. ~~Add coverage cap (`HAVING pe_count < total_pes * 0.5`) to exclude over-applied tags~~ **Done**
3. Gap-fill 12 PEs missing descriptions — **Deferred** (needs production DB)

**Review opinion:** Items 1 and 2 were implemented in this review. This is a ~5-line code
change in `api/routes/pe.py` that immediately improves tag quality. The coverage cap
(item 2) is also worth adding. Item 3 (gap-fill descriptions) requires the production
database and can wait.

### Group G: Deploy & Launch (HIGH EFFORT, BLOCKED)

**Current state — stronger than documented:**
- Docker: Production-ready with multi-stage build, health checks, non-root user
- Staging compose: Production-like with backup sidecar (6-hour cycle, 28 backups)
- CI: Complete (matrix testing, lint, type check, coverage, Docker build)
- Health monitoring: 3 endpoints with detailed metrics, slow query tracking
- Backup: Online SQLite backup API with configurable retention
- Smoke tests: 8 critical path checks
- Feedback mechanism: Already working (see discrepancy above)
- **Deploy workflow: 4 TODO placeholders** — no platform chosen, no secrets configured

**Review opinion:** This is **blocked on infrastructure decisions** that only the project
owner can make. The codebase is deployment-ready. The decision needed is:
1. Which hosting platform? (Fly.io, Railway, Render — all stubbed in deploy.yml)
2. Domain name?
3. Budget for hosting?

No further code work should happen here until those decisions are made.

---

## 3. Recommended New Features (Priority Order)

Based on the codebase maturity and remaining gaps, here are prioritized recommendations:

### P0 — Fix Now (< 1 hour each)

| Feature | Rationale | Files |
|---------|-----------|-------|
| **Tag confidence filtering** | 5-line fix, immediately improves PE tag quality | `api/routes/pe.py` |
| **ROADMAP 4.B2 correction** | Documentation accuracy | `docs/ROADMAP.md` |

### P1 — Do Before Launch

| Feature | Rationale | Files |
|---------|-----------|-------|
| **Accessibility audit** | WCAG 2.1 AA compliance listed as "mostly complete" — needs Lighthouse/axe-core run | Templates, CSS |
| **Data source doc update** (1.A5) | Only remaining Phase 1 item; users need to know coverage | `docs/user-guide/data-sources.md` |
| **DB verification (Groups A-C)** | Confirm data quality fixes are applied | SQL queries + NOTICED_ISSUES.md |

### P2 — Nice to Have Post-Launch

| Feature | Rationale | Files |
|---------|-----------|-------|
| **FY auto-correction** (Group D) | Only if user reports show FY attribution errors | `pipeline/builder.py` |
| **PE description gap-fill** (Group E, item 3) | 12 PEs missing descriptions — minor completeness issue | `pipeline/enricher.py` |
| **Additional DoD sources** (DLA, MDA, SOCOM) | Expand coverage beyond 6 current sources | `downloader/` |
| **FY2000-2009 historical data** | Documents not publicly available in structured format — may not be feasible | Research task |

### P3 — Not Recommended

| Feature | Rationale |
|---------|-----------|
| **PostgreSQL migration** | SQLite FTS5 is working well; migration adds complexity without clear benefit at current scale |
| **External search engine** (Meilisearch) | Same reasoning — premature optimization |
| **Kubernetes manifests** | Overkill for a single-container SQLite app; Docker Compose is sufficient |
| **Additional exhibit type parsing** | Current 15+ exhibit types cover the primary budget documents |

---

## 4. Summary

The `claude/review-todos-docs-mThIH` branch did excellent work consolidating the
project state. The codebase is **mature and feature-complete** for its stated goals.
The two immediate actions are:

1. **Fix the tag confidence filtering** in `api/routes/pe.py` (5 minutes of code)
2. **Correct the ROADMAP** to reflect the feedback feature is complete

Everything else is either blocked on infrastructure decisions (Group G) or requires
the production database (Groups A-D verification). No major new feature development
is recommended before deployment.
