# Step 1.A2 — Expand Fiscal-Year Coverage

**Status:** Not started
**Type:** Research + Code modification (AI-agent completable)
**Depends on:** None

## Task

Verify the downloader can discover and retrieve documents for all publicly
available fiscal years, back to at least FY2017. Identify any years that
fail and fix the discovery logic.

## Current State

- `discover_fiscal_years()` dynamically scrapes comptroller.war.gov for
  available years — works for recent years
- Service-specific pages use URL templates with `{fy}` or `{fy2}` placeholders
- Unknown how far back each service source goes

## Agent Instructions

1. Read `discover_fiscal_years()` in `dod_budget_downloader.py`
2. Run the function (or simulate by fetching the comptroller page) to list
   all years it discovers
3. For each service source, test URL templates for years 2017–2026 to see
   which return valid pages vs. 404s
4. Document the coverage matrix: which years are available from which sources
5. If any years fail due to URL pattern changes (older pages may use different
   URL structures), propose fixes to the discovery functions
6. Estimated tokens: ~1500 output tokens + web fetches

## Annotations

- **DATA PROCESSING:** Requires fetching multiple URLs to test year availability
- **ENVIRONMENT TESTING:** Run `discover_fiscal_years()` to verify dynamic
  discovery. If environment lacks network access, document the test plan for
  a future session with network
