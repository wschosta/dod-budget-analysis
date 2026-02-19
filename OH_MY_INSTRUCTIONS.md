# OH MY Instructions — Requires User Intervention / External Resources

These tasks **cannot be completed by an autonomous agent**. They require network access to live DoD websites, cloud accounts, domain registration, a downloaded document corpus, or community review.

**This file is for the human project owner.** Each task includes what to do, what decisions are needed, and how to verify completion.

---

## Priority Order

1. **HIGH (Unblocks deployment):** OH-MY-007 → OH-MY-008 → OH-MY-009 → OH-MY-010
2. **MEDIUM (Data quality):** OH-MY-001 → OH-MY-002 → OH-MY-003 → OH-MY-004 → OH-MY-005 → OH-MY-006
3. **LOW (Post-launch):** OH-MY-011 → OH-MY-012

---

## Task List

### OH-MY-001: Audit downloader source coverage
**Roadmap:** 1.A1-a | **File:** `dod_budget_downloader.py` | **Complexity:** LOW | **Tokens:** ~1,500
**Requires:** Network access to DoD websites
**Dependencies:** None

Run the downloader with `--list --no-gui` and compare discovered files against expected sources:
1. `python dod_budget_downloader.py --years 2026 --sources all --list --no-gui`
2. Record: which sources return files, which return 0
3. Check each agency URL is still active: comptroller.defense.gov, Army, Navy, USAF, USMC
4. Update `DATA_SOURCES.md` coverage matrix with actual results

**Verification:** DATA_SOURCES.md shows verified FY ranges per source.

---

### OH-MY-002: Identify missing DoD component sources
**Roadmap:** 1.A1-b | **File:** `dod_budget_downloader.py` | **Complexity:** MEDIUM | **Tokens:** ~2,500
**Requires:** Web browsing of DoD agency sites
**Dependencies:** OH-MY-001

Browse DoD component websites to find additional budget exhibit sources:
1. Check: Defense Logistics Agency (DLA), Missile Defense Agency (MDA), SOCOM, DHA, DISA
2. For each: note base URL, file formats available (Excel, PDF), FY coverage
3. Decide: which sources to add to the downloader
4. File an issue or create a TODO for each new source to implement

**Verification:** List of new sources with URLs documented.

---

### OH-MY-003: Verify defense-wide J-Books discovery
**Roadmap:** 1.A1-c | **File:** `dod_budget_downloader.py` | **Complexity:** LOW | **Tokens:** ~1,000
**Requires:** Network access
**Dependencies:** OH-MY-001

Verify Comptroller defense-wide justification books are fully discovered:
1. Browse comptroller.defense.gov/Budget-Materials/ for the current and prior FYs
2. Compare discovered J-Book files against what appears on the website
3. Note any missing document types or fiscal years

**Verification:** All defense-wide J-Books are discoverable.

---

### OH-MY-004: Test historical fiscal year reach (FY2017+)
**Roadmap:** 1.A2-a | **File:** `dod_budget_downloader.py` | **Complexity:** LOW | **Tokens:** ~1,000
**Requires:** Network access
**Dependencies:** None

Test whether the downloader can discover and retrieve documents back to FY2017:
1. `python dod_budget_downloader.py --years 2017 2018 2019 2020 --sources all --list --no-gui`
2. Record which years and sources return results
3. Note any URL pattern changes for older fiscal years
4. Document findings in DATA_SOURCES.md

**Verification:** FY coverage table updated with actual availability.

---

### OH-MY-005: Handle alternate URL patterns for older FYs
**Roadmap:** 1.A2-b | **File:** `dod_budget_downloader.py` | **Complexity:** MEDIUM | **Tokens:** ~2,000
**Requires:** Network access + development
**Dependencies:** OH-MY-004

Based on findings from OH-MY-004, implement URL pattern fixes:
1. If older FYs use different URL structures, add alternate discovery patterns
2. Add fallback URL generation for pre-FY2021 documents
3. Test with `--list --no-gui` to verify discovery

**Verification:** `--list` shows documents for FY2017-2020 from all available sources.

---

### OH-MY-006: Cross-validate exhibit inventory against real corpus
**Roadmap:** 1.B1-a | **File:** `exhibit_catalog.py` | **Complexity:** LOW | **Tokens:** ~1,500
**Requires:** Downloaded document corpus
**Dependencies:** OH-MY-001 (need downloaded files)

Run the exhibit audit tool against real downloaded files:
1. Download a representative set of budget documents
2. `python exhibit_type_inventory.py --export-json inventory.json --verbose`
3. Compare discovered exhibit types against `exhibit_catalog.py` definitions
4. Add any new exhibit types found to the catalog
5. Update `scripts/exhibit_audit.py` if needed

**Verification:** All exhibit types in downloaded corpus are cataloged.

---

### OH-MY-007: Choose hosting platform (CRITICAL — unblocks deployment)
**Roadmap:** 4.A1 | **File:** `docs/design/deployment_design.py` | **Complexity:** MEDIUM | **Tokens:** ~2,000
**Requires:** Cloud account setup
**Dependencies:** None

Evaluate and select a hosting platform:
1. **Top candidates:** Fly.io, Railway, Render (all support SQLite persistent volumes)
2. **Criteria:** Free tier available, persistent disk for SQLite, auto-deploy from GitHub, custom domain, HTTPS
3. **Recommendation:** Fly.io (persistent volumes, free tier, GitHub auto-deploy)
4. Create account, do test deploy of Docker image
5. Document decision in `docs/HOSTING_DECISION.md`

**Verification:** Test deployment accessible via platform URL; SQLite file persists across restarts.

---

### OH-MY-008: Configure CD deployment workflow
**Roadmap:** 4.A3-a | **File:** `.github/workflows/deploy.yml` | **Complexity:** MEDIUM | **Tokens:** ~2,000
**Requires:** Cloud account + secrets
**Dependencies:** OH-MY-007

Fill in the deploy workflow template (created by BEAR-007):
1. Add platform-specific deploy step (e.g., `flyctl deploy` for Fly.io)
2. Configure GitHub secrets: `FLY_API_TOKEN` (or equivalent)
3. Add environment protection rules for production
4. Run `scripts/smoke_test.py` against deployed URL
5. Test: push to main triggers deploy

**Verification:** Push to main auto-deploys; smoke test passes against live URL.

---

### OH-MY-009: Register domain and configure TLS
**Roadmap:** 4.A4 / 4.C1-a | **Complexity:** LOW | **Tokens:** ~1,000
**Requires:** Domain registration
**Dependencies:** OH-MY-007

Register and configure a custom domain:
1. Register domain (e.g., dodbudget.org, dodbudgetexplorer.com)
2. Configure DNS to point to hosting platform
3. Enable HTTPS (most platforms provide free TLS via Let's Encrypt)
4. Verify: `curl -I https://custom-domain.com` returns 200

**Verification:** Application accessible at `https://custom-domain.com`.

---

### OH-MY-010: Run Lighthouse accessibility audit
**Roadmap:** 3.A7-b | **File:** `docs/design/frontend_design.py` | **Complexity:** LOW | **Tokens:** ~1,000
**Requires:** Running UI + Lighthouse/axe-core
**Dependencies:** OH-MY-007 (or local docker-compose up)

Run accessibility audit on the deployed or locally running UI:
1. Start the app: `docker-compose up` or `uvicorn api.app:create_app --factory`
2. Run Lighthouse audit on: `/`, `/charts`
3. Run axe-core browser extension on both pages
4. Target: Lighthouse accessibility score >= 90
5. File issues for any findings below score target
6. Fix critical issues (missing labels, contrast, keyboard nav)

**Verification:** Lighthouse accessibility score >= 90 on both pages.

---

### OH-MY-011: Soft launch and collect feedback
**Roadmap:** 4.B1 + 4.B2-a | **Complexity:** LOW | **Tokens:** ~1,500
**Requires:** Deployed application + secrets
**Dependencies:** OH-MY-008

Share with initial users and set up feedback collection:
1. Identify 5-10 target users (defense analysts, policy researchers, journalists)
2. Configure feedback form to create GitHub Issues (needs GITHUB_TOKEN secret)
3. Share URL with initial users
4. Monitor feedback for 1-2 weeks
5. Triage issues: bug, feature request, data quality, UX

**Verification:** At least 3 users have provided feedback; issues triaged.

---

### OH-MY-012: Public launch
**Roadmap:** 4.B3 + 4.B4 + 4.C6-a | **Complexity:** LOW | **Tokens:** ~1,500
**Requires:** Deployed application + community channels
**Dependencies:** OH-MY-011

Prepare and execute public launch:
1. Write launch announcement (blog post or README update)
2. Review README for public-facing accuracy
3. Verify LICENSE file is appropriate (MIT recommended)
4. Create GitHub Release with changelog
5. Share on: r/dataisbeautiful, Hacker News, civic tech communities, defense policy forums
6. Monitor for issues in first 48 hours

**Verification:** Repository is public; announcement posted; monitoring active.
