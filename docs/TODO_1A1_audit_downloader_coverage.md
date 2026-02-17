# Step 1.A1 — Audit Existing Downloader Coverage

**Status:** Not started
**Type:** Research + Documentation (AI-agent completable)
**Depends on:** None

## Task

Catalog every source `dod_budget_downloader.py` currently supports and identify
gaps in agency/service coverage.

## Current Coverage (known)

- Comptroller (comptroller.war.gov) — summary budget documents
- Defense-Wide (comptroller.war.gov) — justification books
- Army (asafm.army.mil) — budget materials
- Navy (secnav.navy.mil) — budget materials (browser-based)
- Air Force / Space Force (saffm.hq.af.mil) — budget materials (browser-based)

## Gaps to Investigate

- Defense Logistics Agency (DLA)
- Missile Defense Agency (MDA) standalone exhibits
- SOCOM (Special Operations Command)
- Defense Health Agency (DHA)
- Any other agencies with separate budget justification pages

## Agent Instructions

1. Read `dod_budget_downloader.py` — catalog `SERVICE_PAGE_TEMPLATES`,
   `SOURCE_DISCOVERERS`, and `ALL_SOURCES`
2. Web-search for each known gap agency to find their budget justification pages
3. For each discovered source, document: URL pattern, whether it requires a
   browser, file formats available, and fiscal years covered
4. Output a coverage matrix as a markdown table
5. Update `docs/wiki/Data-Sources.md` with findings
6. Estimated tokens: ~2000 output (research-heavy, multiple web fetches)

## Annotations

- **DATA PROCESSING:** Requires web searches to discover agency budget pages
- **USER INTERVENTION:** User should review and approve which new sources to
  add to the downloader, as each requires a new discoverer function
