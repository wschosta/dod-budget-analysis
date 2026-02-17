# Step 1.A5 — Document All Data Sources

**Status:** Not started
**Type:** Documentation (AI-agent completable)
**Depends on:** 1.A1 (audit), 1.A2 (FY coverage) — but can start now

## Overview

Create authoritative `DATA_SOURCES.md` documenting every URL pattern,
document type, file format, and fiscal-year availability.

---

## Sub-tasks

### 1.A5-a — Create DATA_SOURCES.md from current code
**Type:** AI-agent
**Estimated tokens:** ~800 output

1. Read `dod_budget_downloader.py`: extract `SERVICE_PAGE_TEMPLATES`,
   discoverer functions, `ALL_SOURCES`, `BROWSER_REQUIRED_SOURCES`
2. Create `DATA_SOURCES.md` in project root with:
   - Section per source: URL template, file formats, download method
   - Notes on WAF/browser requirements
   - Known FY range (mark unverified with `<!-- TODO: verify -->`)
3. Include the failure log JSON schema for reference

---

### 1.A5-b — Sync wiki Data-Sources page
**Type:** AI-agent
**Estimated tokens:** ~400 output
**Depends on:** 1.A5-a

1. Sync content from `DATA_SOURCES.md` to `docs/wiki/Data-Sources.md`
2. Adjust relative links, add cross-references

---

### 1.A5-c — Add coverage matrix after audit
**Type:** AI-agent (documentation)
**Estimated tokens:** ~500 output
**Depends on:** 1.A1-a, 1.A2-a

1. Fill coverage matrix with verified file counts per source × FY
2. Mark gaps with explanatory notes
3. Update both `DATA_SOURCES.md` and wiki page

---

## Annotations

- 1.A5-a can be done immediately from reading source code
- 1.A5-c requires audit results from 1.A1 and 1.A2
- If audit not done, mark gaps with `<!-- TODO: verify after audit -->`
