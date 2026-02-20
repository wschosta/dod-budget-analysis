# GUI Implementation Plan: HAWK / EAGLE / FALCON

Three parallel agents implement the GUI MVP defined in [GUI_ROADMAP.md](./GUI_ROADMAP.md) and [GUI_DECISIONS_AND_QUESTIONS.md](./GUI_DECISIONS_AND_QUESTIONS.md). Each agent works on a **fully separate branch** with **zero file overlap**, enabling independent development and clean merges.

---

## Architecture Overview

```
HAWK  (Data Layer)     ──┐
                         ├──► Merge in order: HAWK → EAGLE → FALCON
EAGLE (API/Route Layer)──┤
                         │
FALCON (UI Layer)      ──┘
```

**HAWK** builds the data foundations: project-level decomposition, enrichment pipeline integration, advanced search parsing, and metadata API.

**EAGLE** refactors the API layer to consume HAWK's new data: dynamic amount filtering, tag-based related items, expanded pagination, and project-level detail in routes.

**FALCON** builds the visual interface: templates, CSS, JavaScript, and all user-facing interactions defined in the GUI decisions.

---

## Merge Order and Strategy

1. **HAWK merges first** -- no dependencies on other agents
2. **EAGLE merges second** -- depends on HAWK's new tables and API endpoints
3. **FALCON merges last** -- depends on EAGLE's template context variables and HAWK's metadata API

After each merge, run the full test suite (`pytest tests/ -x -q`) before proceeding to the next merge. Resolve any conflicts conservatively -- prefer keeping both changes where possible.

---

## Branch Naming

Each agent operates on its own branch. The naming convention follows the existing pattern:

- HAWK: `hawk/gui-data-layer`
- EAGLE: `eagle/gui-api-layer`
- FALCON: `falcon/gui-ui-layer`

All branches fork from `main` (or whatever branch has the latest LION/TIGER/BEAR work merged).

---

## File Ownership Map

**ZERO OVERLAP RULE:** No file may be modified by more than one agent. If a task requires changes to a file owned by another agent, the task is assigned to the file owner and the dependency is documented as an integration contract.

### HAWK -- Data Pipeline, Enrichment, Search, Metadata

**Modified files (exclusive ownership):**
| File | Purpose |
|------|---------|
| `enrich_budget_db.py` | Add project-level decomposition (Phase 5), tag `project_number` column |
| `utils/pdf_sections.py` | Add project boundary detection within PE narratives |
| `refresh_data.py` | Integrate enrichment as Stage 5 of the pipeline |
| `api/routes/search.py` | Add advanced search parsing (field prefixes, amount operators, AND/OR) |
| `api/routes/budget_lines.py` | Expand page_size cap from 100 → 200 |

**New files (created by HAWK):**
| File | Purpose |
|------|---------|
| `utils/search_parser.py` | Advanced search query parser (field:value, amount operators, boolean) |
| `utils/metadata.py` | Database metadata helper (version, refresh date, coverage stats) |
| `api/routes/metadata.py` | `GET /api/v1/metadata` endpoint |
| `tests/test_search_parser.py` | Tests for advanced search parser |
| `tests/test_metadata.py` | Tests for metadata endpoint and helpers |
| `tests/test_project_decomposition.py` | Tests for project-level enrichment |

### EAGLE -- Frontend Python Logic (API Routes)

**Modified files (exclusive ownership):**
| File | Purpose |
|------|---------|
| `api/routes/frontend.py` | Dynamic amount filter, tag-based related items, project-level detail, expanded page size options |
| `api/routes/pe.py` | Project-level descriptions in PE detail, dynamic FY references |
| `api/routes/download.py` | Export with source attribution, page size options for export |
| `utils/query.py` | WHERE clause builder updates for dynamic FY filtering and tag-based queries |

**New files (created by EAGLE):**
| File | Purpose |
|------|---------|
| `tests/test_eagle_frontend.py` | Tests for refactored frontend routes |
| `tests/test_eagle_pe.py` | Tests for project-level PE detail |

### FALCON -- UI, Templates, CSS, JavaScript

**Modified files (exclusive ownership):**
| File | Purpose |
|------|---------|
| `templates/base.html` | Footer with metadata, nav order, nonce-based CSP |
| `templates/index.html` | Hybrid landing page with search + clickable summary visuals |
| `templates/charts.html` | Lazy-load charts, extract inline JS |
| `templates/programs.html` | Programs page with enrichment dependency messaging |
| `templates/about.html` | Data dictionary / glossary link |
| `templates/partials/results.html` | Keyboard-navigable rows, density classes, multi-PE display |
| `templates/partials/detail.html` | Tag-based related items display, project-level text |
| `templates/partials/program-list.html` | Enhanced program listing |
| `templates/partials/program-descriptions.html` | Project-level descriptions display |
| `templates/program-detail.html` | Program detail with enrichment data |
| `templates/dashboard.html` | Clickable summary visuals |
| `static/css/main.css` | All CSS: density, dark mode polish, responsive, print |
| `static/js/app.js` | URL state, keyboard nav, density toggle, toast, amount format |
| `static/js/dashboard.js` | Chart interactions, lazy loading |
| `static/js/program-detail.js` | Program page interactions |

**New files (created by FALCON):**
| File | Purpose |
|------|---------|
| `static/js/charts.js` | Extracted chart JS from `charts.html` (620+ lines) |
| `static/js/dark-mode.js` | Extracted dark mode init from `base.html` |
| `static/js/search.js` | Advanced search UI, field-prefix helpers |
| `templates/partials/toast.html` | Toast notification component |
| `templates/partials/advanced-search.html` | Advanced search form partial |
| `templates/partials/glossary.html` | Data dictionary content |
| `templates/errors/404.html` | Already exists -- may update styling |
| `templates/errors/500.html` | Already exists -- may update styling |

---

## HAWK Task List

HAWK focuses on **data correctness and completeness** -- making sure the database has everything the GUI needs, in the right shape.

### HAWK-1: Project-Level Narrative Decomposition (MVP CRITICAL)

**Priority:** P0 -- blocks EAGLE and FALCON

**Problem:** `enrich_budget_db.py` links descriptions at the PE level only. R-2 exhibits contain project-level breakdowns within a PE, but these are stored as a single text blob. The GUI needs project-level descriptions (decision 2.2).

**Implementation:**
1. In `utils/pdf_sections.py`, add `detect_project_boundaries(page_text)` that identifies project number/title lines within R-2 narrative text. R-2 exhibits typically include lines like:
   ```
   Project: 1234 — Advanced Targeting System
   ```
   or section headers with project numbers embedded.
2. In `enrich_budget_db.py`, create a new `project_descriptions` table:
   ```sql
   CREATE TABLE IF NOT EXISTS project_descriptions (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       pe_number TEXT NOT NULL,
       project_number TEXT,          -- NULL if PE-level only
       project_title TEXT,           -- NULL if PE-level only
       fiscal_year TEXT,
       section_header TEXT NOT NULL,  -- e.g. "Accomplishments/Planned Program"
       description_text TEXT NOT NULL,
       source_file TEXT,
       page_start INTEGER,
       page_end INTEGER,
       created_at TEXT DEFAULT (datetime('now'))
   );
   CREATE INDEX idx_proj_desc_pe ON project_descriptions(pe_number);
   CREATE INDEX idx_proj_desc_proj ON project_descriptions(project_number);
   CREATE INDEX idx_proj_desc_fy ON project_descriptions(fiscal_year);
   ```
3. Add Phase 5 to `enrich_budget_db.py` that iterates `pe_descriptions`, parses narrative text using `detect_project_boundaries()` and `parse_narrative_sections()`, and populates `project_descriptions` with decomposed sections.
4. If project boundaries cannot be detected (some PE narratives don't have sub-projects), store the text with `project_number=NULL` -- this is the PE-level fallback.

**Acceptance criteria:**
- `project_descriptions` table is populated after enrichment
- Each row has a PE number, optional project number/title, section header, and description text
- PE-level fallback works when project boundaries aren't detected
- Tests verify both project-level and PE-level cases

### HAWK-2: Project-Level Tag Column

**Priority:** P0

**Problem:** `pe_tags` only has `pe_number`. Tags should also reference a project number where applicable (decision 2.7).

**Implementation:**
1. Add `project_number TEXT` column to `pe_tags` (nullable, indexed)
2. Update Phase 3 (keyword tagging) and Phase 4 (LLM tagging) to tag at the project level when project text is available from `project_descriptions`
3. Maintain PE-level tags as the fallback

**Acceptance criteria:**
- `pe_tags.project_number` column exists
- Tags are applied at project level when project text is available
- PE-level-only tags still work for PEs without project decomposition

### HAWK-3: Integrate Enrichment into Refresh Pipeline

**Priority:** P0

**Problem:** `refresh_data.py` has 4 stages (download → build → validate → report) but never calls `enrich_budget_db.py`. The Programs page depends on enrichment data (decision 2.8).

**Implementation:**
1. Import `enrich_budget_db` functions into `refresh_data.py`
2. Add Stage 5 after validation:
   ```python
   def _stage_5_enrich(self):
       """Run PE enrichment pipeline (pe_index, descriptions, tags, lineage)."""
   ```
3. Update progress file to include Stage 5
4. Enrichment failure should warn but not roll back the entire refresh (enrichment can be re-run independently)

**Acceptance criteria:**
- `python refresh_data.py --years 2026` runs enrichment after validation
- `--phases` flag can skip enrichment: `--phases 1,2,3,4` (original behavior)
- Progress file shows Stage 5 status
- Enrichment failure logs a warning but doesn't trigger rollback

### HAWK-4: Advanced Search Query Parser

**Priority:** P1

**Problem:** The current search is free-text only. The GUI needs field-specific operators (decision 2.10): `service:Army`, `pe:0603285E`, `amount>50000`, `AND`/`OR`.

**Implementation:**
1. Create `utils/search_parser.py` with:
   ```python
   @dataclass
   class ParsedQuery:
       fts_terms: str           # Free-text for FTS5
       field_filters: list[FieldFilter]  # service:Army → FieldFilter("service", "=", "Army")
       amount_filters: list[AmountFilter]  # amount>50000 → AmountFilter(">", 50000)

   def parse_search_query(raw_query: str) -> ParsedQuery:
       """Parse a mixed free-text + structured query string."""
   ```
2. Recognized field prefixes: `service:`, `exhibit:`, `pe:`, `org:`, `tag:`
3. Amount operators: `amount>N`, `amount<N`, `amount>=N`, `amount<=N`
4. Boolean: `AND`, `OR` between field clauses (implicit AND by default)
5. Anything without a prefix goes into `fts_terms` for FTS5 search

**Integration contract with EAGLE:**
- EAGLE imports `parse_search_query()` from `utils.search_parser`
- Returns a `ParsedQuery` that EAGLE converts into SQL WHERE clauses via `utils/query.py`

**Acceptance criteria:**
- `parse_search_query("hypersonic service:Army amount>50000")` produces correct ParsedQuery
- Free-text, field filters, and amount filters are all independently testable
- Malformed queries degrade gracefully (treat as free-text)

### HAWK-5: Metadata API Endpoint

**Priority:** P1

**Problem:** The footer needs version, refresh date, and coverage stats (decision 3.4). No endpoint currently provides this.

**Implementation:**
1. Create `utils/metadata.py`:
   ```python
   def get_database_metadata(db_path: str) -> dict:
       """Return metadata about the budget database."""
       return {
           "version": "1.0.0",            # from a VERSION file or config
           "last_refresh": "2026-02-20",   # from refresh_progress.json or DB mtime
           "budget_lines": 12345,          # SELECT COUNT(*) FROM budget_lines
           "services": ["Army", ...],      # SELECT DISTINCT organization_name
           "fiscal_years": ["FY2024", ...], # from column names or distinct values
           "pe_count": 456,                # SELECT COUNT(DISTINCT pe_number)
           "enrichment_available": True,   # pe_index table exists and has rows
       }
   ```
2. Create `api/routes/metadata.py`:
   ```python
   @router.get("/metadata", summary="Database metadata for UI footer")
   def get_metadata(db=Depends(get_db)):
       return get_database_metadata(db)
   ```
3. Register the route in `api/app.py` (HAWK touches only the import + `include_router` line)

**Integration contract with FALCON:**
```json
GET /api/v1/metadata → {
    "version": "1.0.0",
    "last_refresh": "2026-02-20T04:15:00Z",
    "budget_lines": 12345,
    "services": ["Army", "Navy", "Air Force", "Marine Corps", "Space Force", "Defense-Wide"],
    "fiscal_years": ["FY2024", "FY2025", "FY2026"],
    "pe_count": 456,
    "enrichment_available": true
}
```

**Acceptance criteria:**
- `GET /api/v1/metadata` returns the above shape
- Values are derived from actual database state, not hardcoded
- Endpoint is fast (cached with TTLCache)

### HAWK-6: Expand Page Size Cap

**Priority:** P2

**Problem:** `api/routes/budget_lines.py` caps `page_size` at `min(100, max(10, ...))`. The GUI needs 200 as an option (decision 6.4).

**Implementation:**
- Change line in `budget_lines.py`: `min(200, max(10, page_size))`

**Acceptance criteria:**
- `page_size=200` works without truncation
- Default remains 25

---

## EAGLE Task List

EAGLE focuses on **API correctness** -- making the Python route layer serve data in the shapes FALCON needs.

### EAGLE-1: Dynamic Amount Filter

**Priority:** P0

**Problem:** `frontend.py` lines 207-222 hardcode `amount_fy2026_request` as the amount filter column. The GUI needs the amount filter to operate on whichever FY column the user has visible (decision 2.5).

**Implementation:**
1. Accept an `amount_column` query parameter (e.g., `?amount_column=amount_fy2025_enacted`)
2. Validate the column name against a whitelist of known FY columns (use `utils/query.py` to introspect available columns, or maintain an allow-list)
3. Use the validated column name in the WHERE clause instead of hardcoded `amount_fy2026_request`
4. If no `amount_column` is specified, default to the latest available FY request column
5. Pass the active `amount_column` name to the template context so FALCON can highlight it

**Integration contract with FALCON:**
- Template context includes `amount_column` (string) indicating which FY column is active for filtering
- Template context includes `fiscal_year_columns` (list of dicts):
  ```python
  [
      {"column": "amount_fy2024_actual", "label": "FY2024 Actual"},
      {"column": "amount_fy2025_enacted", "label": "FY2025 Enacted"},
      {"column": "amount_fy2026_request", "label": "FY2026 Request"},
  ]
  ```

**Acceptance criteria:**
- `?amount_min=50000&amount_column=amount_fy2025_enacted` filters on FY2025 Enacted
- Invalid column names are rejected with a 400 error
- Default behavior works when no `amount_column` is specified

### EAGLE-2: Tag-Based Related Items

**Priority:** P1

**Problem:** Related items in the detail panel use `pe_number` or `org + title` matching (frontend.py ~lines 377-404), which produces false positives. The GUI needs tag-based matching (decision 2.7).

**Implementation:**
1. When rendering the detail panel, look up the item's tags from `pe_tags` (using both PE-level and project-level tags from HAWK-2)
2. Find other budget lines that share tags with the current item
3. Rank by number of shared tags (more shared tags = more related)
4. Fallback to the existing `pe_number` match when no tags are available
5. Return top 10 related items

**Dependency:** Requires HAWK-2 (project-level tags). EAGLE can implement the logic with a fallback — if `pe_tags` table doesn't exist or is empty, use the current approach.

**Integration contract with FALCON:**
- Detail panel context includes `related_items` (list of dicts):
  ```python
  [
      {"id": 123, "pe_number": "0603285E", "title": "...", "shared_tags": ["hypersonic", "missile"], "amount": 45000},
      ...
  ]
  ```

**Acceptance criteria:**
- Related items are ranked by tag relevance when tags exist
- Graceful fallback when tags are unavailable
- Performance: < 100ms for related items query

### EAGLE-3: Project-Level Detail in PE Routes

**Priority:** P0

**Problem:** `pe.py` returns PE-level summaries only. The GUI needs project-level descriptions and funding breakdowns (decision 2.2).

**Implementation:**
1. In the PE detail endpoint, join on `project_descriptions` (from HAWK-1) to include project-level narrative text
2. Group descriptions by project number and fiscal year
3. Include in the response:
   ```python
   "projects": [
       {
           "project_number": "1234",
           "project_title": "Advanced Targeting System",
           "descriptions": [
               {"fiscal_year": "FY2025", "header": "Accomplishments", "text": "..."},
               {"fiscal_year": "FY2026", "header": "Plans", "text": "..."},
           ]
       },
       ...
   ]
   ```
4. For PE detail HTML route, pass `projects` list to template context

**Dependency:** Requires HAWK-1 (`project_descriptions` table). EAGLE should check if the table exists and return an empty `projects` list if not.

**Integration contract with FALCON:**
- Template context includes `projects` (list of project dicts with nested descriptions)
- Template context includes `has_project_data` (boolean)

**Acceptance criteria:**
- PE detail shows project-level breakdown when available
- PE-level fallback when no project data exists
- Year-over-year text is accessible per project

### EAGLE-4: Expanded Pagination Options

**Priority:** P2

**Problem:** Frontend route caps page_size at 100. GUI needs 25/50/100/200 options (decision 6.4).

**Implementation:**
1. In `frontend.py`, change the page_size clamp to `min(200, max(10, page_size))`
2. Pass `page_size_options = [25, 50, 100, 200]` to template context
3. Pass current `page_size` to template context

**Integration contract with FALCON:**
- Template context includes `page_size_options` (list of ints) and `page_size` (int)

**Acceptance criteria:**
- Page sizes 25, 50, 100, 200 all work
- Default is 25
- Current selection persists via URL params

### EAGLE-5: Advanced Search Integration

**Priority:** P1

**Problem:** Frontend search only supports free-text FTS5. The GUI needs field-specific and amount operators (decision 2.10).

**Implementation:**
1. Import `parse_search_query` from `utils.search_parser` (HAWK-4)
2. In the search handler, parse the raw query through `parse_search_query()`
3. Convert `ParsedQuery.field_filters` into additional WHERE clauses via `utils/query.py`
4. Convert `ParsedQuery.amount_filters` into amount WHERE clauses (using the active `amount_column` from EAGLE-1)
5. Pass `ParsedQuery.fts_terms` to the existing FTS5 search
6. Pass the parsed query structure to template context so FALCON can show active filters

**Dependency:** Requires HAWK-4 (`utils/search_parser.py`). EAGLE should gracefully handle the import not existing yet by falling back to raw free-text.

**Integration contract with FALCON:**
- Template context includes `parsed_query` with structure:
  ```python
  {
      "raw": "hypersonic service:Army amount>50000",
      "fts_terms": "hypersonic",
      "field_filters": [{"field": "service", "op": "=", "value": "Army"}],
      "amount_filters": [{"op": ">", "value": 50000}],
  }
  ```

**Acceptance criteria:**
- `?q=hypersonic+service:Army+amount>50000` works
- Field filters combine with FTS search
- Malformed queries degrade to free-text

### EAGLE-6: Export Source Attribution

**Priority:** P2

**Problem:** Exports lack data source attribution. The GUI requires all exports to include source metadata (decision 2.4, 1.5).

**Implementation:**
1. In `download.py`, add source attribution columns to CSV export: `exhibit_type`, `fiscal_year`, `budget_submission`
2. For Excel export (if implemented by TIGER/LION DL-001), include a metadata header row with database version, export date, and query parameters
3. Include the URL that generated the export in a header row

**Acceptance criteria:**
- CSV exports include source attribution columns
- Excel exports include metadata header
- Attribution is human-readable

---

## FALCON Task List

FALCON focuses on **user experience** -- building everything the user sees and interacts with.

### FALCON-1: Hybrid Landing Page

**Priority:** P0

**Roadmap ref:** 1.1

**Implementation:**
1. Redesign `index.html` with a prominent search bar (full-width, centered, large)
2. Below the search bar, add clickable summary visuals:
   - Top-level budget breakdown by service (bar chart)
   - Breakdown by appropriation type (stacked bar)
3. Clicking a chart element navigates to search results filtered by that item (e.g., clicking "Army" bar → `?service=Army`)
4. Summary data comes from existing `/api/v1/aggregations` or a new HTMX partial
5. URL state synced on page load

**Acceptance criteria:**
- Search bar is the dominant visual element
- Summary visuals load and are clickable
- Chart clicks navigate to filtered search results

### FALCON-2: Search Results with Keyboard Navigation

**Priority:** P0

**Roadmap ref:** 1.2, 5.5

**Implementation:**
1. Update `partials/results.html` to include `tabindex="0"` on table rows
2. Add `role="row"` and `aria-selected` attributes for accessibility
3. In `app.js`, add keyboard event handlers:
   - Arrow Up/Down: move selection between rows
   - Enter: expand detail panel for selected row
   - Escape: collapse detail panel
4. Visual focus indicator via `:focus-visible` styles (already in CSS)
5. Support displaying multiple PE lines simultaneously (multi-select for comparison)
6. Implement data density classes on the results table container

**Acceptance criteria:**
- Arrow keys navigate between rows
- Enter opens detail panel
- Focus indicator is visible
- Density toggle works (compact/comfortable/spacious)

### FALCON-3: Filter Sidebar Enhancements

**Priority:** P0

**Roadmap ref:** 1.2, 6.1

**Implementation:**
1. Add amount range filter UI that dynamically operates on the selected FY column
2. Add FY column selector dropdown (populated from `fiscal_year_columns` context variable from EAGLE-1)
3. Make filter sidebar collapsible on small screens (drawer pattern)
4. At tablet breakpoint (~600px), collapse sidebar by default with a toggle button
5. Active filters shown as removable chips above results

**Acceptance criteria:**
- Amount filter applies to selected FY column
- FY column selector is populated dynamically
- Sidebar collapses on narrow viewports
- Filter chips show active filters

### FALCON-4: Advanced Search UI

**Priority:** P1

**Roadmap ref:** 1.3

**Implementation:**
1. Create `templates/partials/advanced-search.html` with:
   - Field prefix helpers (dropdowns or autocomplete for `service:`, `exhibit:`, `pe:`, `org:`, `tag:`)
   - Amount operator builder (operator dropdown + amount input)
   - Boolean operator toggles (AND/OR)
2. In `static/js/search.js`:
   - Build the query string from the advanced search form
   - Parse the search input in real-time to show recognized fields as colored chips
   - Provide autocomplete suggestions for field values (services, exhibit types)
3. Toggle between simple and advanced search modes

**Acceptance criteria:**
- Advanced search form builds valid query strings
- Recognized field prefixes are highlighted in the search input
- Users can toggle between simple and advanced modes

### FALCON-5: URL-Based State Management

**Priority:** P0

**Roadmap ref:** 1.4

**Implementation:**
1. In `app.js`, implement URL state sync:
   - Read URL params on page load to restore search/filter/sort/page state
   - Update URL params on every user interaction (search, filter, sort, page change)
   - Use `history.pushState` for filter changes (not full page reload)
2. Parameters: `q`, `service`, `exhibit`, `fy`, `amount_min`, `amount_max`, `amount_column`, `sort`, `sort_dir`, `page`, `page_size`
3. Browser back/forward navigates through search history

**Acceptance criteria:**
- Copy-paste URL reproduces exact view
- Browser back/forward works
- All filter/sort/page state is in the URL

### FALCON-6: Export UI

**Priority:** P1

**Roadmap ref:** 1.5

**Implementation:**
1. Export button group in results header: CSV, Excel, PDF, Image
2. Each export includes the current filter state in the request
3. Show toast notification on export start/completion
4. PDF and image exports use client-side rendering of the visible table

**Acceptance criteria:**
- All four export formats work
- Exports reflect current filter/sort state
- Toast notification confirms export

### FALCON-7: Navigation and Footer

**Priority:** P1

**Roadmap ref:** 1.6, 3.1-3.4

**Implementation:**
1. Update `base.html` nav order: Home → Search/Results → Charts → Programs → About → API Docs
2. API Docs link: `target="_blank"`
3. Footer content populated via `GET /api/v1/metadata` (HAWK-5):
   - Version, last refresh date, data coverage stats
   - Fetch on page load via HTMX or inline from template context
4. Add data dictionary / glossary link under About or as sub-nav item

**Acceptance criteria:**
- Nav order matches spec
- Footer shows live metadata
- API Docs opens in new tab

### FALCON-8: Dark Mode Polish

**Priority:** P1

**Roadmap ref:** 4.3

**Implementation:**
1. Audit all hardcoded inline colors and migrate to CSS custom properties
2. Verify all chart elements respond to `[data-theme="dark"]`
3. Test all form elements, borders, and backgrounds in dark mode
4. Ensure toast notifications, error states, and overlays work in dark mode

**Acceptance criteria:**
- No hardcoded colors remain in templates
- All elements respond correctly to theme toggle
- AA contrast ratios maintained in dark mode

### FALCON-9: Amount Formatting Toggle

**Priority:** P1

**Roadmap ref:** 4.5

**Implementation:**
1. Add global toggle UI (button group or dropdown) for $K / $M / $B
2. In `app.js`, implement client-side number formatting:
   - Apply selected unit to all displayed amounts on the page
   - Store preference in localStorage
   - Trigger re-format on toggle change
3. All values use the same unit simultaneously (no mixing)
4. Default unit auto-selected based on data range, but user override takes precedence

**Acceptance criteria:**
- Toggle switches all amounts on screen simultaneously
- Preference persists across sessions
- Charts and tables both respond to the toggle

### FALCON-10: Toast Notification Component

**Priority:** P1

**Roadmap ref:** 7.1

**Implementation:**
1. Create `templates/partials/toast.html` -- lightweight, auto-dismiss notification
2. In `app.js`, implement `showToast(message, type)` function
3. Toast types: success, info, warning, error
4. Auto-dismiss after 4 seconds (configurable)
5. Respects `prefers-reduced-motion` (no slide animation)
6. Wire up to: URL copy, export start/complete, feedback submit, search save

**Acceptance criteria:**
- Toasts appear for all specified user actions
- Auto-dismiss works
- Accessible (role="alert", aria-live="polite")

### FALCON-11: Extract Inline JavaScript

**Priority:** P1

**Roadmap ref:** 8.1, 8.2

**Implementation:**
1. Extract 620+ lines of chart JS from `charts.html` into `static/js/charts.js`
2. Extract dark mode init script from `base.html` into `static/js/dark-mode.js`
3. Update script references in templates
4. This enables migrating CSP from `'unsafe-inline'` to nonce-based

**Acceptance criteria:**
- No inline `<script>` blocks remain in templates (except nonce-based)
- Charts still function correctly
- Dark mode still initializes on page load

### FALCON-12: Programs Page Enhancement

**Priority:** P1

**Roadmap ref:** 1.11

**Implementation:**
1. Update `programs.html` to show an informative message when enrichment data is unavailable:
   ```html
   <div class="info-banner">
     Program data requires enrichment. Run <code>python enrich_budget_db.py</code> to populate.
   </div>
   ```
2. When enrichment data IS available, display:
   - Program list with PE numbers, tags, and descriptions
   - Project-level breakdown within each program (from EAGLE-3's `projects` context)
   - Year-over-year accomplishment text
3. Link program entries back to search results

**Acceptance criteria:**
- Missing enrichment data shows a clear, helpful message
- Available enrichment data displays project-level detail
- Programs link to search results

### FALCON-13: Accessibility Audit and Fixes

**Priority:** P0

**Roadmap ref:** 1.8, 5.1, 5.2, 5.4

**Implementation:**
1. Audit all color contrast in both light and dark mode (already partially done in CSS)
2. Add `aria-live` regions for HTMX partial swaps
3. Implement `@media (prefers-reduced-motion: reduce)` overrides (already started in CSS)
4. Ensure all interactive elements have visible focus indicators
5. Add skip-to-content link styling
6. Verify form labels, error messages, and required field indicators

**Acceptance criteria:**
- All text/background combinations meet 4.5:1 contrast ratio
- HTMX partial swaps announce to screen readers
- Reduced motion mode suppresses animations
- All interactive elements are keyboard-accessible

### FALCON-14: Responsive Layout

**Priority:** P2

**Roadmap ref:** 1.9, 6.2

**Implementation:**
1. Tablet breakpoint at 600px (already partially in CSS)
2. Filter drawer behavior at narrow viewports
3. Results table horizontal scroll on small screens
4. Chart container responsive sizing

**Acceptance criteria:**
- Tablet portrait gets optimized layout
- Filter sidebar collapses below 600px
- Tables scroll horizontally without breaking layout

---

## Integration Contracts (Summary)

These are the agreed interfaces between agents. Each agent can develop against these contracts independently.

### HAWK → EAGLE: Database Schema

**`project_descriptions` table:**
```sql
(id, pe_number, project_number, project_title, fiscal_year,
 section_header, description_text, source_file, page_start, page_end, created_at)
```

**`pe_tags` table update:**
```sql
ALTER TABLE pe_tags ADD COLUMN project_number TEXT;
```

**`utils/search_parser.py` API:**
```python
from utils.search_parser import parse_search_query, ParsedQuery
result: ParsedQuery = parse_search_query("hypersonic service:Army amount>50000")
# result.fts_terms = "hypersonic"
# result.field_filters = [FieldFilter(field="service", op="=", value="Army")]
# result.amount_filters = [AmountFilter(op=">", value=50000)]
```

### HAWK → FALCON: Metadata API

```
GET /api/v1/metadata → {
    "version": str,
    "last_refresh": str (ISO 8601),
    "budget_lines": int,
    "services": list[str],
    "fiscal_years": list[str],
    "pe_count": int,
    "enrichment_available": bool
}
```

### EAGLE → FALCON: Template Context Variables

**Search results page (`/` and `/partials/results`):**
```python
{
    "amount_column": "amount_fy2026_request",       # active FY column
    "fiscal_year_columns": [                         # all available FY columns
        {"column": "amount_fy2024_actual", "label": "FY2024 Actual"},
        {"column": "amount_fy2025_enacted", "label": "FY2025 Enacted"},
        {"column": "amount_fy2026_request", "label": "FY2026 Request"},
    ],
    "page_size": 25,
    "page_size_options": [25, 50, 100, 200],
    "parsed_query": {                                # from advanced search
        "raw": "...", "fts_terms": "...",
        "field_filters": [...], "amount_filters": [...]
    },
}
```

**PE detail page (`/partials/detail/{id}` and `/pe/{pe_number}`):**
```python
{
    "projects": [                                    # project-level data
        {
            "project_number": "1234",
            "project_title": "Advanced Targeting System",
            "descriptions": [
                {"fiscal_year": "FY2025", "header": "Accomplishments", "text": "..."},
            ]
        }
    ],
    "has_project_data": True,
    "related_items": [                               # tag-based related items
        {"id": 123, "pe_number": "0603285E", "title": "...",
         "shared_tags": ["hypersonic", "missile"], "amount": 45000},
    ],
}
```

---

## Commit Convention

Each agent prefixes commit messages with its name:

```
HAWK: Implement HAWK-1 — project-level narrative decomposition
EAGLE: Implement EAGLE-1 — dynamic amount filter on visible FY columns
FALCON: Implement FALCON-1 — hybrid landing page with clickable visuals
```

Each agent should commit after completing each task (not batch). Use `/compact` between tasks to manage context window.

---

## Answering: "Is there anything else?"

Beyond the HAWK/EAGLE/FALCON tasks above, the following are **not assigned to any agent** but should be tracked:

1. **Colorblind-friendly chart palettes** (decision 4.4) -- FALCON can include the default palette, but the user-selectable palette UI is Phase 2 scope.

2. **Lazy-load charts via IntersectionObserver** (decision 6.3) -- assigned to FALCON-11 implicitly as part of the JS extraction. Can be a follow-up if the extraction is already complex enough.

3. **Nonce-based CSP migration** (decision 8.1) -- enabled by FALCON-11 (JS extraction). The actual CSP header change is a one-liner in `api/app.py` middleware but requires all inline scripts to be extracted first. Could be a small follow-up task.

4. **Automated accessibility compliance tests** (decision 5.3) -- not assigned. Could be a fourth agent (OSPREY?) or post-merge work. These are test files that verify WCAG compliance programmatically.

5. **Error state UI** (decision 8.5) -- partially covered by FALCON-10 (toast) and FALCON-12 (programs page). Remaining: chart loading errors, search failures, API timeouts. Can be woven into FALCON's tasks.

6. **Data dictionary page content** (decision 7.4) -- FALCON-7 links to it; the content comes from existing `docs/data_dictionary.md`. A `templates/partials/glossary.html` template renders it. Assigned to FALCON.

None of these are blocking. They can be addressed during implementation or in a cleanup pass after the three-agent merge.

---

*Last updated: 2026-02-20. Derived from [GUI_DECISIONS_AND_QUESTIONS.md](./GUI_DECISIONS_AND_QUESTIONS.md) and [GUI_ROADMAP.md](./GUI_ROADMAP.md).*
