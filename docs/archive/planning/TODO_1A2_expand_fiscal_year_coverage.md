# Step 1.A2 — Expand Fiscal-Year Coverage

**Status:** Not started
**Type:** ENVIRONMENT TESTING + Code modification
**Depends on:** 1.A1-a (audit shows which years currently work)

## Overview

Ensure the downloader discovers and retrieves documents for all publicly
available fiscal years (target: FY2017–FY2026+).

---

## Sub-tasks

### 1.A2-a — Test historical FY reach for Comptroller
**Type:** ENVIRONMENT TESTING (requires network)
**Estimated tokens:** ~400 output

1. Run `discover_fiscal_years()` and record all years returned
2. Run `--list --years 2017 2018 2019 2020 --sources comptroller`
3. Record: which years return files, which 404, which redirect
4. Check if pre-FY2020 uses different URL patterns

---

### 1.A2-b — Fix Comptroller historical URL patterns
**Type:** AI-agent (code modification)
**Estimated tokens:** ~600 output
**Depends on:** 1.A2-a (must know which years fail)

If older FYs use different URL patterns:
1. Inspect page HTML for failing years
2. Add URL variants to `discover_comptroller_files()`
3. Use fallback: try primary → alternate → skip with warning

---

### 1.A2-c — Test historical FY reach for service sources
**Type:** ENVIRONMENT TESTING (requires network)
**Estimated tokens:** ~500 output

1. Run `--list --years 2017 2018 2019 2020 --sources army navy airforce`
2. Record which service/year combinations return files
3. For failures: inspect site for correct URL pattern

---

### 1.A2-d — Fix service-specific historical URL patterns
**Type:** AI-agent (code modification)
**Estimated tokens:** ~800 output
**Depends on:** 1.A2-c

For each failing service/year:
1. Add alternate URL patterns to the relevant `discover_*_files()` function
2. Use try/fallback approach: primary URL → alternate → skip with warning

---

### 1.A2-e — Update coverage documentation
**Type:** AI-agent (documentation)
**Estimated tokens:** ~400 output
**Depends on:** 1.A2-a through 1.A2-d

1. Fill in coverage matrix in `docs/wiki/Data-Sources.md`
2. Update this TODO status

---

## Annotations

- All testing sub-tasks require network access to government sites
- URL pattern changes are the most likely cause of historical year failures
- Some historical data may not be published online (pre-FY2017)
