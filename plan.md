# Database Browser Full Scrub — Diagnosis & Fix Plan

## Executive Summary

Investigation of the four reported symptoms (broken links, non-functional dropdowns, duplicate data, broken fiscal year filtering) reveals **14 distinct bugs** spanning the CSS, JavaScript, API route, query-building, and data ingestion layers. The most impactful root causes are:

1. **CSS `overflow: hidden`** on `.results-panel` clipping absolutely-positioned dropdown menus
2. **A `GLOB` pattern** in `frontend.py` that silently excludes fiscal year values not matching exact 4-digit patterns
3. **Missing deduplication** in reference data queries and the ingestion pipeline
4. **`restoreFiltersFromURL()`** in `app.js` unable to interact with the custom `checkbox-select` component, making chart click-through links and URL-based filter restoration non-functional

---

## Issue 1: Broken Links

### Findings

| # | Finding | Severity |
|---|---------|----------|
| 1A | Footer `/about#glossary` anchor — **works correctly** | N/A |
| 1B | PE CSV export link `/api/v1/pe/{pe}/export/table` — **works correctly** | N/A |
| 1C | Chart click-through links (`/?service=Army`) — **silently fail** because `restoreFiltersFromURL()` (app.js:202) tries `form.elements["service"].options` which doesn't work with the custom `checkbox-select` component | **High** |
| 1D | HTMX detail links `hx-get="/partials/detail/{id}"` — **work correctly** | N/A |
| 1E | Programs page links `/programs/{pe_number}` — **work correctly** | N/A |
| 1F | Nav bar checks `request.url.path == "/glossary"` (base.html:54) but no `/glossary` route exists — harmless dead condition but misleading | Low |

### Root Cause

Chart click-through links **appear broken** because `restoreFiltersFromURL()` at `static/js/app.js:202-221` assumes native `<select>` elements with `.options`, but the filter form uses `checkbox-select` custom components. When a user clicks a service bar and lands on `/?service=Army`, the filter is never applied — the page loads but shows unfiltered results.

### Fixes

| Priority | File | Change |
|----------|------|--------|
| High | `static/js/app.js:202-221` | Update `restoreFiltersFromURL()` to detect checkbox-select wrappers and use their API to set selected values, then dispatch a `change` event |
| High | `static/js/checkbox-select.js` | Add a public `setSelectedValues(values)` method that programmatically checks items and syncs the hidden `<select>` |
| Low | `templates/base.html:54` | Remove dead `request.url.path == "/glossary"` condition |

---

## Issue 2: Dropdowns Not Dropping Down

### Findings

| # | Finding | Severity |
|---|---------|----------|
| 2A | `.results-panel` has `overflow: hidden` (main.css:441) — clips any absolutely-positioned dropdown rendered inside the results area | **High** |
| 2B | `.checkbox-select-dropdown` also has `overflow: hidden` (main.css ~line 919) with `z-index: 1000` — the z-index is sufficient but the parent container clips it | **High** |
| 2C | Filter panel (`.filter-panel`) has **no** `overflow: hidden` — sidebar dropdowns should work on desktop | OK |
| 2D | On mobile (<768px), filter panel starts as `display: none` — users must click "Filters & Search Options" toggle first; dropdowns are hidden until drawer opens | Medium |
| 2E | HTMX result swaps may close open dropdowns — the debounce handler (app.js:851-862) fires `filter-debounced` after 300ms of a `change` event, which triggers an HTMX swap while the user is still clicking checkbox options | **High** |
| 2F | After HTMX swaps, new checkbox-select elements in swapped HTML are **not reinitialized** — the `htmx:afterSwap` handler (app.js:542-560) does not call checkbox-select init | Medium |

### Root Causes

1. **`overflow: hidden` on `.results-panel`** (main.css:441) clips any dropdown or popover inside the results area
2. **HTMX swaps during dropdown interaction** — the debounce triggers a content refresh while the user is mid-click, causing the dropdown to vanish
3. **Checkbox-select components not reinitialized** after HTMX swaps content

### Fixes

| Priority | File | Change |
|----------|------|--------|
| **High** | `static/css/main.css:441` | Change `.results-panel { overflow: hidden }` to `overflow: visible` (or remove the property; if needed for border-radius, use a nested wrapper) |
| **High** | `static/js/app.js` + `checkbox-select.js` | Suppress `filter-debounced` while any dropdown is open; fire on dropdown close instead. Add `data-dropdown-open` flag. |
| Medium | `static/js/app.js:542-560` | In `htmx:afterSwap`, reinitialize any checkbox-select components in the swapped content |
| Medium | `static/css/main.css` | Verify `.checkbox-select-dropdown` z-index (1000) clears sticky table header (z-index: 1) and nav (z-index: 100) — currently OK |

---

## Issue 3: Duplicate Data

### Findings

| # | Finding | Severity |
|---|---------|----------|
| 3A | `services_agencies` primary query (reference.py:31) lacks `DISTINCT` — if backfill inserted duplicates, they propagate to every dropdown | **High** |
| 3B | Fiscal year reference query uses `GROUP BY` — **no duplicate risk** | OK |
| 3C | Aggregation endpoint uses `GROUP BY` — **no duplicate risk** | OK |
| 3D | Search results JOIN on `b.id = fts.rowid` — **no duplicate risk from the JOIN itself**, but duplicate *rows in `budget_lines`* (from re-running the build pipeline) would appear as separate results | **High** |
| 3E | `budget_lines` table has **no unique constraint** — `CREATE TABLE IF NOT EXISTS budget_lines` with auto-increment `id` allows identical rows on repeated ingestion | **Critical** |
| 3F | `ingested_files` manifest tracks processed files, but if the DB is rebuilt without clearing, or manifest check is bypassed, duplicates accumulate | High |
| 3G | Programs page service dropdown (`programs.html:50-56`) inherits any duplicates from the service data source | Medium |

### Root Causes

1. **No unique constraint on `budget_lines`** — re-running `build_budget_db.py` without clearing the DB inserts duplicate rows
2. **`services_agencies` backfill may insert duplicates** — `backfill_reference_tables.py` may use plain `INSERT` without `ON CONFLICT` handling
3. **Services query lacks `DISTINCT`** — `reference.py:31` returns raw rows from `services_agencies`

### Fixes

| Priority | File | Change |
|----------|------|--------|
| **Critical** | `pipeline/builder.py` | Add composite `UNIQUE` constraint on `budget_lines` (e.g., `source_file, sheet_name, fiscal_year, pe_number, line_item, organization_name, amount_type`) or use `INSERT OR IGNORE` |
| **High** | `api/routes/reference.py:31` | Add `DISTINCT` to primary services query: `SELECT DISTINCT code, full_name, category FROM services_agencies` |
| **High** | `backfill_reference_tables.py` + `pipeline/backfill.py` | Use `INSERT OR IGNORE` or `INSERT OR REPLACE` when populating reference tables |
| Medium | `validate_budget_data.py` | Add a validation check that detects and reports duplicate budget lines |

---

## Issue 4: Fiscal Year Filtering Broken (Critical)

### Findings

| # | Finding | Severity |
|---|---------|----------|
| 4A | `fiscal_year` column is `TEXT` (builder.py:348) — values could be `"2024"`, `"FY2024"`, `"FY24"`, `"2024.0"`, etc. | Context |
| 4B | **Frontend route uses restrictive GLOB** (frontend.py:158-159): `GLOB '[0-9][0-9][0-9][0-9]'` OR `GLOB 'FY[0-9][0-9][0-9][0-9]'` — this **silently excludes** any FY stored as `"FY24"`, `"2024.0"`, or other non-standard formats | **Critical** |
| 4C | **Dashboard route has the same GLOB** (dashboard.py:62-63) | **Critical** |
| 4D | `build_where_clause` (query.py:98-100) does exact `IN()` matching on `fiscal_year` — if dropdown sends `"2024"` but DB stores `"FY2024"`, zero results | **High** |
| 4E | Fiscal year reference endpoint returns raw DB values — the dropdown shows whatever is stored, which is correct, but if GLOB excludes some values from the dropdown, those years become invisible | **High** |
| 4F | **`VALID_AMOUNT_COLUMNS` only covers FY2024-FY2026** (query.py:17-25) — even if older FY rows existed, they'd have NULL amount columns | Context |
| 4G | "No results for 2000-2024" — the DB likely only contains data for the current budget cycle (FY2024/2025/2026). This is **expected behavior**, not a bug, if only current-cycle documents were ingested | Context |
| 4H | "Not showing FY before 2024" in dropdowns — the fiscal year dropdown is populated from the DB. If only FY2024+ data was ingested, only those years appear. This is **data limitation, not a code bug** | Context |

### Root Causes

1. **The `GLOB` filter** in `frontend.py:158-159` and `dashboard.py:62-63` silently excludes fiscal year values that don't match the exact `[0-9]{4}` or `FY[0-9]{4}` patterns. Any rows with fiscal years like `"FY24"` or `"2024.0"` become invisible.
2. **Type/format mismatch** between what the dropdown sends and what's stored — exact string comparison in `IN()` means `"2024"` ≠ `"FY2024"`.
3. **Limited fiscal year range is a data limitation** — the DB only contains data for ingested budget cycles. Current DoD budget submissions cover FY2024 actual, FY2025 enacted, FY2026 request.
4. **Hardcoded amount columns only cover FY2024-2026** — even if older rows existed, they'd have no dollar values.

### Fixes

| Priority | File | Change |
|----------|------|--------|
| **Critical** | `api/routes/frontend.py:158-159` | Remove or loosen the `GLOB` restriction. Replace with: `AND fiscal_year IS NOT NULL AND fiscal_year != ''` |
| **Critical** | `api/routes/dashboard.py:62-63` | Same fix as frontend.py |
| **High** | `pipeline/builder.py` | Normalize all fiscal year values to a consistent format (e.g., 4-digit `"2026"`) during ingestion via `_normalise_fiscal_year()` |
| **High** | `api/routes/reference.py:76-83` | Add normalization-aware ordering: `ORDER BY CAST(REPLACE(REPLACE(fiscal_year, 'FY', ''), 'CY', '') AS INTEGER)` |
| Medium | `utils/query.py:98-100` | Consider normalizing fiscal_year values before the `IN()` comparison |
| Low | Frontend | Add UI messaging: "Only fiscal years present in ingested data are available. Amount columns cover FY2024-FY2026." |

---

## Additional Findings

| # | Finding | File | Severity |
|---|---------|------|----------|
| 5 | `remove_filter_param` Jinja2 filter used in `partials/results.html:31` — must be registered in the app; if missing, filter chip "remove" links break | `api/app.py` or `api/routes/frontend.py` | Verify |
| 6 | `hx-include="#filter-form"` in pagination buttons depends on filter state surviving HTMX swaps — if checkbox-select loses state after swap, pagination with filters breaks | `partials/results.html:214-215` | Medium |
| 7 | Checkbox-select auto-initializes on DOMContentLoaded, but HTMX-swapped content with new checkbox-select elements won't auto-init | `static/js/checkbox-select.js` | Medium |

---

## Diagnosis Steps (Data Layer)

Before implementing fixes, run these queries against the actual `dod_budget.sqlite` to confirm data-level issues:

```sql
-- 1. What fiscal year formats exist?
SELECT fiscal_year, COUNT(*) FROM budget_lines
GROUP BY fiscal_year ORDER BY fiscal_year;

-- 2. Are there duplicate budget lines?
SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT source_file || '|' || fiscal_year || '|' || pe_number || '|' || line_item_title)
       AS distinct_rows
FROM budget_lines;

-- 3. Are there duplicate services in the reference table?
SELECT code, COUNT(*) FROM services_agencies GROUP BY code HAVING COUNT(*) > 1;

-- 4. What fiscal years are excluded by the GLOB pattern?
SELECT fiscal_year, COUNT(*) FROM budget_lines
WHERE fiscal_year IS NOT NULL
  AND fiscal_year NOT GLOB '[0-9][0-9][0-9][0-9]'
  AND fiscal_year NOT GLOB 'FY[0-9][0-9][0-9][0-9]'
GROUP BY fiscal_year;

-- 5. Are amount columns populated for any FY before 2024?
SELECT fiscal_year,
       SUM(CASE WHEN amount_fy2024_actual IS NOT NULL THEN 1 ELSE 0 END) AS has_2024,
       COUNT(*) AS total
FROM budget_lines
WHERE CAST(REPLACE(REPLACE(fiscal_year, 'FY', ''), 'CY', '') AS INTEGER) < 2024
GROUP BY fiscal_year;

-- 6. Duplicate organization names (near-duplicates)?
SELECT DISTINCT organization_name FROM budget_lines ORDER BY organization_name;
```

---

## Implementation Priority

### Phase 1: Critical — Fiscal Year Filtering
1. Remove/loosen `GLOB` restrictions in `frontend.py` and `dashboard.py`
2. Normalize fiscal year values in the ingestion pipeline (`builder.py`)
3. Verify consistency between reference endpoint values and `IN()` filter values
4. Run diagnostic SQL queries above to confirm data state

### Phase 2: High — Dropdowns and Duplicates
5. Fix `overflow: hidden` on `.results-panel` in `main.css`
6. Add HTMX `afterSwap` handler to reinitialize checkbox-select components
7. Suppress filter debounce while dropdowns are open
8. Add `DISTINCT` to reference table queries
9. Add `INSERT OR IGNORE` / unique constraints for `budget_lines`
10. Add deduplication to reference table backfill

### Phase 3: Medium — Links and UX
11. Fix `restoreFiltersFromURL()` to work with checkbox-select components
12. Add `setSelectedValues()` API to checkbox-select component
13. Improve mobile filter drawer discoverability
14. Add "no data for this range" messaging for fiscal year filters

---

## Files to Modify (Summary)

| File | Change | Priority |
|------|--------|----------|
| `api/routes/frontend.py:158-159` | Remove/loosen GLOB fiscal year filter | Critical |
| `api/routes/dashboard.py:62-63` | Remove/loosen GLOB fiscal year filter | Critical |
| `pipeline/builder.py` | Normalize fiscal_year on ingestion; add unique constraint | Critical |
| `static/css/main.css:441` | Change `.results-panel` overflow to visible | High |
| `api/routes/reference.py:31` | Add DISTINCT to services query | High |
| `static/js/app.js:202-221` | Fix `restoreFiltersFromURL()` for checkbox-select | High |
| `static/js/app.js:542-560` | Reinitialize checkbox-select after HTMX swap | High |
| `static/js/checkbox-select.js` | Add `setSelectedValues()` API; handle HTMX lifecycle | High |
| `static/js/app.js:851-862` | Suppress debounce while dropdown is open | High |
| `pipeline/backfill.py` | Use INSERT OR IGNORE for reference tables | Medium |
| `backfill_reference_tables.py` | Use INSERT OR IGNORE for reference tables | Medium |
| `utils/query.py:98-100` | Consider normalizing fiscal_year in `IN()` filter | Medium |
| `validate_budget_data.py` | Add duplicate detection validation check | Medium |
| `templates/base.html:54` | Remove dead `/glossary` path condition | Low |

---

## Testing Strategy

### Unit Tests
- Verify `build_where_clause` handles mixed fiscal year formats (`"2024"`, `"FY2024"`, `"FY24"`, `"2024.0"`)
- Verify reference services endpoint returns no duplicates
- Verify fiscal year reference endpoint returns correctly ordered years

### Integration Tests
- Populate test DB with multiple fiscal year formats → call `/api/v1/reference/fiscal-years` → use returned values to filter `/api/v1/budget-lines` → assert results returned
- Verify `/partials/results` returns results when `fiscal_year` param matches stored values
- Verify no duplicate rows in search results for a known query

### Frontend Tests
- Verify GLOB patterns do not exclude valid fiscal year values
- Verify checkbox-select components survive HTMX swaps
- Verify `restoreFiltersFromURL()` correctly sets checkbox-select state from URL params

### Data Quality Tests
- Add validation check reporting: distinct fiscal year formats found, duplicate budget lines, duplicate reference table entries
