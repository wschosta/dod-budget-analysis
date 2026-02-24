# Parallel Implementation Plan — GUI + Database Build

## Overview

This plan organizes work into **two parallel streams** that can be executed simultaneously by separate agents:

- **Stream A (GUI Agent)**: Frontend templates, JavaScript, CSS, and frontend route changes
- **Stream B (Database/Pipeline Agent)**: Database schema, enrichment pipeline, API route logic, and data quality

Each stream is divided into phases. Within each phase, tasks are independent and can be executed in any order. Cross-stream dependencies are explicitly marked with `SYNC` points — both agents should reach the sync point before proceeding past it.

The plan is derived from:
- The **Tool Assessment** (docs/TOOL_ASSESSMENT.md) with 27 stakeholder-answered questions
- The **Database Browser Fix Plan** (14 diagnosed bugs)
- The **API vs. GUI parity gap** (10+ API endpoints not surfaced in GUI)
- The **stakeholder priority stack** (Spruill charts, full drill-down, source traceability, description search)

---

## Phase 1: Fix Existing Bugs (Both Streams)

### Stream A — GUI Bug Fixes

| ID | Task | Files | Notes |
|----|------|-------|-------|
| A1.1 | **Fix CSS overflow clipping dropdowns** | `static/css/main.css:441` | Change `.results-panel { overflow: hidden }` to `overflow: visible` |
| A1.2 | **Fix `restoreFiltersFromURL()` for checkbox-select** | `static/js/app.js:202-221` | Detect checkbox-select wrappers and use their API instead of native `.options` |
| A1.3 | **Add `setSelectedValues()` API to checkbox-select** | `static/js/checkbox-select.js` | Public method to programmatically set checked items and sync the hidden `<select>` |
| A1.4 | **Suppress filter debounce while dropdown is open** | `static/js/app.js:851-862`, `static/js/checkbox-select.js` | Add `data-dropdown-open` flag; fire `filter-debounced` on dropdown close instead of during interaction |
| A1.5 | **Reinitialize checkbox-select after HTMX swaps** | `static/js/app.js:542-560` | In `htmx:afterSwap`, find and initialize any new checkbox-select elements in swapped content |
| A1.6 | **Remove dead `/glossary` nav check** | `templates/base.html:54` | Remove `request.url.path == "/glossary"` condition |

### Stream B — Database/API Bug Fixes

| ID | Task | Files | Notes |
|----|------|-------|-------|
| B1.1 | **Add DISTINCT to reference services query** | `api/routes/reference.py:31` | `SELECT DISTINCT code, full_name, category FROM services_agencies` |
| B1.2 | **Add INSERT OR IGNORE for reference table backfill** | `pipeline/backfill.py`, `backfill_reference_tables.py` | Prevent duplicate reference rows on re-run |
| B1.3 | **Add budget_lines deduplication constraint** | `pipeline/builder.py` | Add composite UNIQUE constraint or use INSERT OR IGNORE on `(source_file, sheet_name, fiscal_year, pe_number, line_item_title, organization_name, amount_type)` |
| B1.4 | **Add duplicate detection validation check** | `validate_budget_data.py` | New validation rule reporting duplicate budget lines |

> **SYNC-1**: Both agents complete Phase 1 before Phase 2. The GUI agent's dropdown and filter fixes depend on correct data from Stream B. Test: `python -m pytest tests/ -v` passes.

---

## Phase 2: Wire Existing API Endpoints to GUI (Highest Impact)

These are the **lowest-effort, highest-value** changes: API endpoints already exist but are not surfaced in the GUI.

### Stream A — New GUI Components

| ID | Task | Files | Notes |
|----|------|-------|-------|
| A2.1 | **Add search autocomplete/typeahead** | `static/js/app.js`, `templates/index.html` | Wire `GET /api/v1/search/suggest` to the search input with a dropdown suggestion list. Debounce 200ms, show max 5 results. |
| A2.2 | **Add "Funding Changes" tab to PE detail** | `templates/program-detail.html`, new partial `templates/partials/program-changes.html` | HTMX lazy-loaded section showing line-item-level changes (new/terminated/increase/decrease). Calls `GET /api/v1/pe/{pe}/changes`. |
| A2.3 | **Add "PDF Pages" tab to PE detail** | `templates/program-detail.html`, new partial `templates/partials/program-pdf-pages.html` | Inline extracted text viewer. Calls `GET /api/v1/pe/{pe}/pdf-pages`. Show page text with section headers and source file link. |
| A2.4 | **Add "View Source" traceability to detail panel** | `templates/partials/detail.html` | Show source_file, sheet_name, row_number. Add "View Source" button linking to source file in `DoD_Budget_Documents/`. |
| A2.5 | **Add sort options to Programs page** | `templates/programs.html`, `static/js/app.js` | Add sort dropdown: PE Number, Funding (desc), YoY Change (desc), Name. Passes `sort_by` and `sort_dir` to `/partials/program-list`. |
| A2.6 | **Surface "Top Changes" on Programs page** | `templates/programs.html` | Add "Biggest Movers" section/card at top of Programs page showing top 5 increases and decreases. Calls `GET /api/v1/pe/top-changes?limit=5`. |

### Stream B — API Route Enhancements

| ID | Task | Files | Notes |
|----|------|-------|-------|
| B2.1 | **Add frontend route for program changes partial** | `api/routes/frontend.py` | New `GET /partials/program-changes/{pe_number}` route that calls `get_pe_changes()` and returns HTML partial |
| B2.2 | **Add frontend route for program PDF pages partial** | `api/routes/frontend.py` | New `GET /partials/program-pdf-pages/{pe_number}` route that calls `get_pe_pdf_pages()` and returns HTML partial |
| B2.3 | **Add sort_by/sort_dir parameters to program_list_partial** | `api/routes/frontend.py` | Parse `sort_by` and `sort_dir` from query params and pass them to `list_pes()` |
| B2.4 | **Add top-changes frontend endpoint** | `api/routes/frontend.py` or `api/routes/dashboard.py` | New endpoint returning top changes as HTML partial for the Programs page hero section |
| B2.5 | **Ensure `/api/v1/pe/{pe}/changes` handles edge cases** | `api/routes/pe.py` | Verify behavior when PE has no FY2025 data, when all lines are new, when PE exists only in PDFs |

> **SYNC-2**: GUI agent and DB agent coordinate on the partial template names and query parameter contracts. The GUI templates reference `/partials/program-changes/{pe}` and `/partials/program-pdf-pages/{pe}` — both must agree on the endpoint URLs and the context variable names.

---

## Phase 3: New Analyst Features (Medium Effort)

### Stream A — New GUI Pages and Components

| ID | Task | Files | Notes |
|----|------|-------|-------|
| A3.1 | **Build Spruill chart table component** | New `templates/partials/spruill-table.html`, `static/js/spruill.js` | Multi-PE table: rows = PE numbers (or sub-elements), columns = fiscal years. Interactive — click a cell to see line items. Stakeholder priority #1 visualization. |
| A3.2 | **Add multi-PE selection to Programs page** | `templates/programs.html`, `templates/partials/program-list.html`, `static/js/app.js` | Add checkboxes to PE cards. "Compare Selected" button navigates to Spruill view with selected PEs. |
| A3.3 | **Add program description full-text search** | `templates/index.html` or new search mode toggle | Add search type toggle: "Budget Lines" / "Program Descriptions" / "Both". When "Program Descriptions" is selected, search uses `pe_descriptions_fts`. |
| A3.4 | **Improve related PEs display** | `templates/partials/program-related.html` | Raise default confidence to 60%. Group by relationship type (explicit_pe_ref vs. name_match). Show type labels with distinct styling. |
| A3.5 | **Add full chart drill-down** | `static/js/charts.js`, `static/js/dashboard.js` | All charts become clickable: top-10 chart → PE detail page, treemap cell → filtered search, appropriation doughnut → filtered search. |
| A3.6 | **Add quantity data display** | `templates/program-detail.html`, `templates/partials/results.html` | Add togglable quantity columns (Qty FY24, Qty FY25, Qty FY26) to funding tables and search results. Only visible when data exists. |

### Stream B — Database/Pipeline Enhancements

| ID | Task | Files | Notes |
|----|------|-------|-------|
| B3.1 | **Add Spruill data API endpoint** | `api/routes/pe.py` | New `GET /api/v1/pe/spruill?pe=X&pe=Y` that returns data formatted for Spruill table: rows of PEs/sub-elements, columns of FY amounts. Built on `compare_pes()` but with sub-element breakdown. |
| B3.2 | **Add program description search to search endpoint** | `api/routes/search.py` | Extend search to optionally include `pe_descriptions_fts` results. Add `source` parameter: `budget_lines`, `descriptions`, `both`. |
| B3.3 | **Add `pe_descriptions_fts` FTS5 table if missing** | `schema_design.py`, `pipeline/enricher.py` | Create FTS5 virtual table on `pe_descriptions(description_text)` with sync triggers. This is needed for Phase 3 description search. |
| B3.4 | **Add PE sub-element funding breakdown for Spruill** | `api/routes/pe.py` | Enhance `compare_pes()` to return sub-element rows (budget_activity, line_item) for each PE when `detail=true` parameter is set. |
| B3.5 | **Add enrichment coverage metadata endpoint** | `api/routes/metadata.py` | Return counts of enriched PEs, tags, descriptions, lineage links, and last enrichment timestamp. Surfaced in the Programs page header. |

> **SYNC-3**: The Spruill table (A3.1) depends on the Spruill data endpoint (B3.1). Both agents must agree on the data contract before building. The GUI agent can build a mockup with sample data while waiting.

---

## Phase 4: Data Quality and Completeness

### Stream A — UX Polish and Error Handling

| ID | Task | Files | Notes |
|----|------|-------|-------|
| A4.1 | **Add data freshness indicator** | `templates/base.html` or `templates/partials/` | Banner or footer badge: "Data last updated: {date}". Fetches from `/api/v1/metadata`. |
| A4.2 | **Add "no data for this filter" messaging** | `templates/partials/results.html`, `templates/programs.html` | When fiscal year filter returns 0 results, show message: "No data found for the selected fiscal years. Available data covers FY2024-FY2026." |
| A4.3 | **Add PNG/SVG chart export** | `static/js/charts.js`, `static/js/dashboard.js`, `static/js/program-detail.js` | Add "Export as PNG" button to each chart card. Use `Chart.toBase64Image()` → download link. |
| A4.4 | **Add tag cloud/browse view** | `templates/programs.html` or new `templates/tags.html` | Visual tag cloud using data from `GET /api/v1/pe/tags/all`. Tag size proportional to PE count. Click tag to filter Programs page. |

### Stream B — Pipeline Robustness

| ID | Task | Files | Notes |
|----|------|-------|-------|
| B4.1 | **Add data update changelog table** | `schema_design.py` | New `data_changelog` table: `id, action (insert/update/delete), table_name, record_count, source_file, timestamp, notes`. Populated by `refresh_data.py`. |
| B4.2 | **Add metadata last-updated timestamp** | `api/routes/metadata.py` | Return `last_build_time`, `last_enrichment_time`, `total_budget_lines`, `total_pe_count`, `total_pdf_pages`. |
| B4.3 | **Validate P-5 and R-2 detail exhibit parsing** | `pipeline/builder.py`, `tests/` | Add test fixtures for P-5 (procurement detail) and R-2 (RDT&E detail) exhibits. Verify column mapping matches real data format. |
| B4.4 | **Add FY normalization to ingestion** | `pipeline/builder.py` | Normalize all fiscal_year values to consistent 4-digit format during ingestion (e.g., "FY 2026" → "2026", "FY2026" → "2026"). |

---

## Dependency Graph

```
Phase 1 (Bug Fixes)
  Stream A: A1.1─A1.6  (independent, parallel)
  Stream B: B1.1─B1.4  (independent, parallel)
        │
    SYNC-1 ─── pytest passes
        │
Phase 2 (Wire API to GUI)
  Stream A: A2.1─A2.6  (independent, parallel)
  Stream B: B2.1─B2.5  (independent, parallel)
        │
    SYNC-2 ─── partial URLs + context vars agreed
        │
Phase 3 (New Features)
  Stream A: A3.1─A3.6  (A3.1 depends on B3.1 data contract)
  Stream B: B3.1─B3.5  (B3.3 needed before B3.2)
        │
    SYNC-3 ─── Spruill data contract finalized
        │
Phase 4 (Quality + Polish)
  Stream A: A4.1─A4.4  (independent)
  Stream B: B4.1─B4.4  (independent)
```

---

## File Ownership Map

To avoid merge conflicts, each file is owned by one stream:

### Stream A (GUI Agent) — owns:
- `static/css/main.css`
- `static/js/*.js` (all JavaScript files)
- `templates/*.html` (all templates)
- `templates/partials/*.html` (all partials)

### Stream B (Database/Pipeline Agent) — owns:
- `api/routes/*.py` (all API route files)
- `api/models.py`
- `api/app.py`
- `pipeline/*.py`
- `schema_design.py`
- `utils/*.py`
- `validate_budget_data.py`
- `backfill_reference_tables.py`

### Shared (coordinate changes):
- `tests/` — both agents add tests, but in separate test files
  - Stream A: `tests/test_web_group/test_gui_*.py`, `tests/test_web_group/test_frontend_*.py`
  - Stream B: `tests/test_pipeline_group/test_*.py`, `tests/test_web_group/test_api_*.py`

---

## Testing Strategy

### After Each Phase

Both agents run:
```bash
python -m pytest tests/ -v --ignore=tests/test_gui_tracker.py --ignore=tests/optimization_validation
```

### Per-Stream Testing

**Stream A** validates:
- HTMX partials render without errors (TestClient with test DB)
- JavaScript changes don't break existing tests
- New templates reference correct HTMX endpoints and context variables
- CSS changes don't break responsive layout

**Stream B** validates:
- API endpoints return correct data structures
- New database tables/indexes created correctly
- Enrichment pipeline produces expected output
- FTS5 search works with new tables
- Rate limiting and caching still work

### Integration Testing (at SYNC points)

At each SYNC point, run the full test suite plus manual verification:
1. Start server: `uvicorn api.app:app --reload --port 8000`
2. Navigate to each modified page and verify functionality
3. Test HTMX partial loading in browser DevTools Network tab
4. Verify chart interactions and drill-down links
5. Test search autocomplete with real database

---

## Summary: Priority by Impact

| Rank | Items | Effort | Impact | Phase |
|------|-------|--------|--------|-------|
| 1 | Fix dropdown/filter bugs (A1.1-A1.5, B1.1-B1.3) | Low | Critical — users can't use filters | 1 |
| 2 | Search autocomplete (A2.1) | Low | High — reduces friction for all users | 2 |
| 3 | Programs page sort + top changes (A2.5, A2.6) | Low | High — enables discovery workflow | 2 |
| 4 | PE funding changes tab (A2.2, B2.1) | Low | High — core analyst need | 2 |
| 5 | PE PDF pages tab (A2.3, B2.2) | Low | High — source traceability | 2 |
| 6 | View Source button (A2.4) | Low | High — trust and verification | 2 |
| 7 | Spruill chart table (A3.1, B3.1) | Medium | High — #1 stakeholder visualization | 3 |
| 8 | Multi-PE comparison (A3.2) | Medium | High — analyst workflow | 3 |
| 9 | Description search (A3.3, B3.2, B3.3) | Medium | High — cross-cutting analysis | 3 |
| 10 | Full chart drill-down (A3.5) | Medium | Medium — discovery workflow | 3 |
| 11 | Chart export PNG/SVG (A4.3) | Low | Medium — briefing support | 4 |
| 12 | Tag cloud (A4.4) | Low | Medium — discovery | 4 |
| 13 | Data freshness indicator (A4.1, B4.2) | Low | Low-Medium — trust | 4 |
| 14 | P-5/R-2 validation (B4.3) | Medium | Medium — data completeness | 4 |
