# Step 1.A5 — Document All Data Sources

**Status:** Not started
**Type:** Documentation (AI-agent completable)
**Depends on:** 1.A1 (audit results feed into this), 1.A2 (fiscal year coverage)

## Task

Create `DATA_SOURCES.md` listing every URL pattern, document type, file format,
and fiscal-year availability for each service and agency. This is the
authoritative reference for the downloader's scope.

## Agent Instructions

1. Read `dod_budget_downloader.py` — extract `SERVICE_PAGE_TEMPLATES`, all
   discoverer functions, URL patterns, and file extension filters
2. Cross-reference with audit results from Step 1.A1
3. Cross-reference with fiscal year coverage from Step 1.A2
4. Create `DATA_SOURCES.md` in the project root with:
   - A table per source: URL template, file formats, FY range, download method
   - A combined coverage matrix (source x fiscal year)
   - Notes on any sources that require special handling (browser, WAF, etc.)
5. Also update `docs/wiki/Data-Sources.md` with the same content
6. Estimated tokens: ~1200 output tokens

## Annotations

- Best completed after 1.A1 and 1.A2, but can be started with current knowledge
- If 1.A1/1.A2 are not yet complete, document what is currently known and mark
  gaps with `<!-- TODO: verify -->` comments
