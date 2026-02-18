# Remaining TODOs

Generated: 2026-02-18

This document catalogs all remaining TODO items found across the codebase, organized
by category and priority.

---

## Summary

| Category | Count |
|---|---|
| Data Source Auditing & Coverage (1.A) | 6 |
| Exhibit Parsing & Cataloging (1.B) | 3 |
| Test Fixtures & Specifications (1.C) | 10 |
| Data Reconciliation (2.B) | 2 |
| Frontend (3.A) | 1 |
| Deployment & Launch (4.x) | 4 |
| Documentation Verification | 8 |
| **Total** | **34** |

---

## 1. Data Source Auditing & Coverage

### `dod_budget_downloader.py`

| ID | Line | Complexity | Description |
|---|---|---|---|
| 1.A1-a | 33 | LOW | Audit source coverage by running `--list --years all --sources all`. Produce a coverage matrix (source × FY) and document gaps in `DATA_SOURCES.md`. Requires network + live env. |
| 1.A1-b | 42 | MEDIUM | Identify missing DoD component sources (DLA, MDA, SOCOM, DHA, DISA, National Guard Bureau). Search each agency domain for standalone budget justification documents and add to `SERVICE_PAGE_TEMPLATES` if found. Requires web browsing. |
| 1.A1-c | 57 | LOW | Verify defense-wide discovery captures all J-Books. Run `--list --years 2026 --sources defense-wide` and compare against known defense agency J-Books. Requires network. |
| 1.A2-a | 65 | LOW | Test historical fiscal year reach back to FY2017. Run `--list` for years 2017-2019 and check for non-empty results. Try Wayback Machine if gaps found. Requires network. |
| 1.A2-b | 73 | MEDIUM | Handle alternate URL patterns for older fiscal years. Depends on 1.A2-a identifying which years fail first. Requires network. |
| 1.A2-c | 82 | MEDIUM | Handle service-specific historical URL changes for FY2017-2020. Run `--list` for each service for years 2017-2018 and fix failures. Requires network. |

### Inline implementation markers

| ID | Line | Note |
|---|---|---|
| 1.A3-b | 1583 | Hash verification stub — comment marks where previously-recorded hash verification should be extended. |
| 1.A3-c | 1630 | WAF/bot detection helper — marked as implemented. |

---

## 2. Exhibit Parsing & Cataloging

### `build_budget_db.py`

| ID | Line | Complexity | Description |
|---|---|---|---|
| 1.B5-a | 31 | MEDIUM | Audit PDF extraction quality for common layouts. Write a script querying `pdf_pages` for pages with high non-ASCII char or whitespace-only ratios. Record findings in `docs/pdf_quality_audit.md`. Requires downloaded corpus. |
| 1.B2-c | 636 | MEDIUM | Handle multi-row headers in Excel exhibit sheets. Detect when `rows[header_idx+1]` is a continuation row and merge cells with `" ".join()` before passing to `_map_columns()`. Add test fixture. |

### `exhibit_catalog.py`

| ID | Line | Complexity | Description |
|---|---|---|---|
| 1.B1-a | 19, 425 | LOW | Inventory all exhibit types found in downloaded files. Run `scripts/exhibit_audit.py` against `DoD_Budget_Documents/` and compare against catalog entries. Requires downloaded corpus. |

---

## 3. Test Fixtures & Specifications

### `tests/conftest.py`

| ID | Line | Description |
|---|---|---|
| TEST-001 | 242 | P-5 Procurement Detail fixtures — columns match P-5 header. |
| TEST-001 | 254 | R-2 RDT&E Detail Schedule fixtures. |
| 1.C1-a | 276 | Excel fixtures for summary exhibits. |
| 1.C1-b | 287 | PDF fixtures. |

### `tests/test_parsing.py`

| ID | Line | Description |
|---|---|---|
| 1.C2-a | 39 | Tests for `_detect_exhibit_type`. |
| 1.C2-c | 63 | Tests for `_safe_float`. |
| 1.C2-d | 83 | Tests for `_determine_category`. |
| 1.C2-e | 101 | Tests for `_extract_table_text`. |
| 1.C2-b | 132 | `_map_columns` basic coverage (partial). |
| 1.C2-g | 520 | Clean up legacy TODO comments in related test files. |
| 1.B2-b | 530 | Catalog-driven column detection for detail exhibits. |

### `tests/test_exhibit_catalog.py`

| ID | Line | Description |
|---|---|---|
| 1.B1-f | 184 | All catalog entries return valid mappings. |

### `tests/fixtures/README.md`

| ID | Line | Description |
|---|---|---|
| 1.C1 | 3 | Populate fixtures directory with representative test files. |

---

## 4. Data Reconciliation

### `schema_design.py`

| ID | Line | Complexity | Description |
|---|---|---|---|
| 2.B2-a | 65 | MEDIUM | Cross-service reconciliation check. For each FY, sum service-level P-1 totals and compare against Comptroller summary P-1 total. Output reconciliation report with deltas. Requires real data. |
| 2.B2-b | 73 | MEDIUM | Cross-exhibit reconciliation (P-1 vs P-5, R-1 vs R-2, O-1 vs O-1 detail). Compare summary totals vs sum of details per service+FY. Requires real data. |

---

## 5. Frontend

### `frontend_design.py`

| ID | Line | Complexity | Description |
|---|---|---|---|
| 3.A7-b | 44 | LOW | Accessibility audit. Run Lighthouse or axe-core, fix issues (labels, contrast, ARIA, keyboard nav). Depends on 3.A2-3.A6 being implemented. Target: Lighthouse score >= 90. |

---

## 6. Deployment & Launch

### `deployment_design.py`

| ID | Line | Complexity | Description |
|---|---|---|---|
| 4.A3-a | 25 | MEDIUM | Choose hosting platform. Evaluate Railway, Fly.io, Render, AWS ECS, DigitalOcean. Criteria: cost, SQLite support, auto-deploy, custom domain, HTTPS. Requires cloud account. |
| 4.B2-a | 46 | MEDIUM | Create GitHub Actions deploy workflow (`.github/workflows/deploy.yml`). Trigger on push to main, build Docker image, deploy, run smoke test. Depends on 4.A3-a. Requires secrets. |
| 4.C1-a | 61 | LOW | Configure custom domain + HTTPS. Register domain, configure DNS, enable TLS. Requires domain registration. |
| 4.C6-a | 80 | LOW | Prepare for public launch. Community review needed. |

---

## 7. Documentation Verification

These are inline verification markers in documentation files that need to be resolved
after running the source coverage audit (TODO 1.A1-a).

| File | Line | Description |
|---|---|---|
| `DATA_SOURCES.md` | 44 | Verify actual earliest year after running 1.A1 audit. |
| `DATA_SOURCES.md` | 62 | Verify FY range for source after audit. |
| `DATA_SOURCES.md` | 81 | Verify FY range for source after audit. |
| `DATA_SOURCES.md` | 100 | Verify FY range for source after audit. |
| `DATA_SOURCES.md` | 120 | Verify FY range for source after audit. |
| `DATA_SOURCES.md` | 140 | Verify FY range; Space Force separated FY 2021+. |
| `DATA_SOURCES.md` | 200 | Fill in after running audit (Step 1.A1). |
| `docs/wiki/Data-Sources.md` | 79 | Fill in after running downloader audit (Step 1.A1). |

---

## 8. API Documentation

| File | Line | Description |
|---|---|---|
| `docs/wiki/API-Reference.md` | 3 | Populate after API endpoints are designed and implemented (Steps 2.C2-2.C6). |

---

## Dependency Graph

```
1.A1-a ──► 1.A2-a ──► 1.A2-b
  │                     │
  ▼                     ▼
Documentation      1.A2-c
verification
(DATA_SOURCES.md)

1.B1-a (needs downloaded corpus)
1.B2-c (standalone)
1.B5-a (needs downloaded corpus)

2.B2-a, 2.B2-b (need real data in DB)

3.A2–3.A6 ──► 3.A7-b (accessibility audit)

4.A3-a ──► 4.B2-a ──► 4.C1-a ──► 4.C6-a
```
