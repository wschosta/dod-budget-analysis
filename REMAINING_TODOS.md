# Remaining TODOs

Updated: 2026-02-18 (continued session)

This document catalogs all remaining TODO items found across the codebase, organized
by category and priority.

---

## Summary

| Category | Count |
|---|---|
| Data Source Auditing & Coverage (1.A) | 6 |
| Exhibit Parsing & Cataloging (1.B) | 1 |
| Frontend (3.A) | 1 |
| Deployment & Launch (4.x) | 4 |
| Documentation Verification | 8 |
| **Total** | **20** |

---

## Recently Completed (this session)

| ID | Description | Implementation |
|---|---|---|
| 1.C2-g | Clean up legacy TODO comments in test files | Replaced TODO markers with DONE in test_parsing.py, test_exhibit_catalog.py, conftest.py |
| 1.B5-a | PDF extraction quality audit script | `scripts/pdf_quality_audit.py` + tests in `tests/test_pdf_quality_audit.py` |
| 2.B2-a | Cross-service reconciliation check | `scripts/reconcile_budget_data.py::reconcile_cross_service()` + tests |
| 2.B2-b | Cross-exhibit reconciliation (P-1 vs P-5, R-1 vs R-2) | `scripts/reconcile_budget_data.py::reconcile_cross_exhibit()` + tests |
| 1.B2-c | Handle multi-row headers in Excel exhibit sheets | Already implemented via `_merge_header_rows()` + `ingest_excel_file()` integration; TODO comment updated to DONE |
| TEST-001 | P-5 and R-2 test fixtures | Already implemented in conftest.py; TODO comment updated to DONE |
| 1.C1-a | Excel fixtures for summary exhibits | Already implemented in conftest.py; TODO comment updated to DONE |
| 1.C1-b | PDF fixtures | Already implemented in conftest.py; TODO comment updated to DONE |
| 1.C2-a | Tests for `_detect_exhibit_type` | Already implemented; TODO comment updated to DONE |
| 1.C2-b | `_map_columns` basic + extended coverage | Already implemented; TODO comment updated to DONE |
| 1.C2-c | Tests for `_safe_float` | Already implemented; TODO comment updated to DONE |
| 1.C2-d | Tests for `_determine_category` | Already implemented; TODO comment updated to DONE |
| 1.C2-e | Tests for `_extract_table_text` | Already implemented; TODO comment updated to DONE |
| 1.B2-b | Catalog-driven column detection for detail exhibits | Already implemented with tests; TODO comment updated to DONE |
| 1.B1-f | All catalog entries return valid mappings | Already implemented with tests; TODO comment updated to DONE |
| 1.C1 | Populate test fixtures directory | `scripts/generate_expected_output.py` creates synthetic .xlsx fixtures + expected JSON; 14 integration tests in `tests/test_fixture_integration.py` |

### Test Coverage Improvements (continued session)

| Test File | Tests | Modules Covered |
|---|---|---|
| `tests/test_backfill.py` | 11 | `backfill_reference_tables.py` — backfill(), service classification, deduplication, dry-run, CLI |
| `tests/test_refresh_workflow.py` | 22 | `refresh_data.py` — RefreshWorkflow init, logging, run_command, dry-run stages, webhook notification |
| `tests/test_database_utils.py` | 19 | `utils/database.py` — init_pragmas, batch_insert, table introspection, FTS5 index/triggers, vacuum |
| `tests/test_pdf_sections.py` | 24 | `utils/pdf_sections.py` — R-2/R-3 section pattern matching, narrative parsing, is_narrative_exhibit |
| `tests/test_common_utils.py` | 12 | `utils/common.py` — format_bytes, elapsed, sanitize_filename, get_connection |
| `tests/test_exhibit_inventory.py` | 19 | `exhibit_type_inventory.py` — ExhibitInventory scan, report, JSON/CSV export |
| `tests/test_search_extended.py` | 9 | `search_budget.py` — display_budget_results, display_pdf_results, export_results |
| `tests/test_build_where.py` | 11 | `api/routes/budget_lines.py` — _build_where() SQL WHERE clause builder |
| `tests/test_gui_eta.py` | 10 | `build_budget_gui.py` — _fmt_eta() ETA formatting |
| `tests/test_api_database.py` | 5 | `api/database.py` — get_db() FastAPI dependency, connection lifecycle |
| **Total** | **142** | Test count: 561 → 844 (+283 new tests across both sessions) |

---

## 1. Data Source Auditing & Coverage

### `dod_budget_downloader.py`

| ID | Line | Complexity | Description |
|---|---|---|---|
| 1.A1-a | 33 | LOW | Audit source coverage by running `--list --years all --sources all`. Produce a coverage matrix (source x FY) and document gaps in `DATA_SOURCES.md`. Requires network + live env. |
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

### `exhibit_catalog.py`

| ID | Line | Complexity | Description |
|---|---|---|---|
| 1.B1-a | 19, 425 | LOW | Inventory all exhibit types found in downloaded files. Run `scripts/exhibit_audit.py` against `DoD_Budget_Documents/` and compare against catalog entries. Requires downloaded corpus. |

---

## 3. Frontend

### `frontend_design.py`

| ID | Line | Complexity | Description |
|---|---|---|---|
| 3.A7-b | 44 | LOW | Accessibility audit. Run Lighthouse or axe-core, fix issues (labels, contrast, ARIA, keyboard nav). Depends on 3.A2-3.A6 being implemented. Target: Lighthouse score >= 90. |

---

## 4. Deployment & Launch

### `deployment_design.py`

| ID | Line | Complexity | Description |
|---|---|---|---|
| 4.A3-a | 25 | MEDIUM | Choose hosting platform. Evaluate Railway, Fly.io, Render, AWS ECS, DigitalOcean. Criteria: cost, SQLite support, auto-deploy, custom domain, HTTPS. Requires cloud account. |
| 4.B2-a | 46 | MEDIUM | Create GitHub Actions deploy workflow (`.github/workflows/deploy.yml`). Trigger on push to main, build Docker image, deploy, run smoke test. Depends on 4.A3-a. Requires secrets. |
| 4.C1-a | 61 | LOW | Configure custom domain + HTTPS. Register domain, configure DNS, enable TLS. Requires domain registration. |
| 4.C6-a | 80 | LOW | Prepare for public launch. Community review needed. |

---

## 5. Documentation Verification

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

## 6. API Documentation

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

3.A2–3.A6 ──► 3.A7-b (accessibility audit)

4.A3-a ──► 4.B2-a ──► 4.C1-a ──► 4.C6-a
```
