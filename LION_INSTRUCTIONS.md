# LION Agent Instructions — Frontend, Documentation & User Experience

You are a Claude agent assigned to the **LION** group for the DoD Budget Analysis project. Your focus is **frontend polish, user documentation, and data visualization improvements**. You work autonomously — do not request user input.

---

## Project Context

This is a FastAPI + HTMX/Jinja2 web application that lets users search, filter, and download Department of Defense budget data. The frontend is in `templates/` and `static/`, the API in `api/`, and user documentation in `docs/`.

**Your files:** `templates/`, `static/css/main.css`, `static/js/app.js`, `docs/getting_started.md`, `docs/data_dictionary.md`, `docs/faq.md`, `docs/methodology.md`, `docs/wiki/API-Reference.md`, `api/routes/frontend.py`

---

## Constraints

- **DO NOT** change the code architecture (FastAPI + HTMX + Jinja2 + SQLite).
- **DO NOT** reduce data quality or remove validation checks.
- **DO NOT** add new Python dependencies without documenting why in requirements.txt.
- **DO NOT** modify files owned by TIGER (`api/routes/search.py`, `api/routes/aggregations.py`, `api/routes/download.py`, `utils/`, `schema_design.py`) or BEAR (`tests/`, `.github/`, `Dockerfile*`, `build_budget_db.py`).
- Mark each TODO as DONE in-line when you complete it.
- Run `pytest tests/test_frontend_routes.py tests/test_accessibility.py tests/test_frontend_helpers.py -v` after changes to verify nothing breaks.

---

## Task List (execute in order)

### LION-001: Add error page templates
**Roadmap:** 3.A3-g | **Files:** `templates/errors/404.html`, `templates/errors/500.html`, `api/routes/frontend.py` | **Complexity:** LOW | **Tokens:** ~1,500 | **Time:** ~10 min
**Dependencies:** None

Create user-friendly error pages:
1. Create `templates/errors/404.html` extending `base.html` with "Page not found" message, search link, and consistent styling
2. Create `templates/errors/500.html` extending `base.html` with "Something went wrong" message and retry suggestion
3. Register custom exception handlers in `api/routes/frontend.py` for 404 and 500
4. Verify both pages render correctly

**Acceptance:** GET /nonexistent returns styled 404 page, not raw JSON.

---

### LION-002: Add feedback form UI stub
**Roadmap:** 4.B2-b | **Files:** `templates/partials/feedback.html`, `templates/base.html`, `static/js/app.js` | **Complexity:** MEDIUM | **Tokens:** ~2,500 | **Time:** ~15 min
**Dependencies:** None

Build the UI for user feedback (backend integration requires secrets — OH MY):
1. Create `templates/partials/feedback.html` with fields: type (bug/feature/data-issue), description (textarea), email (optional), page URL (auto-filled)
2. Add "Feedback" button in `templates/base.html` footer that opens the form as a modal
3. Add `openFeedbackModal()` / `closeFeedbackModal()` in `static/js/app.js`
4. Form submission should POST to `/api/v1/feedback` (will return 501 until TIGER implements the endpoint)
5. Add aria-label and keyboard dismiss (Escape key) to modal

**Acceptance:** Feedback button visible in footer; modal opens/closes; form fields present.

---

### LION-003: Add loading skeleton for HTMX requests
**Roadmap:** 3.A3-h | **Files:** `templates/partials/results.html`, `static/css/main.css` | **Complexity:** LOW | **Tokens:** ~1,000 | **Time:** ~10 min
**Dependencies:** None

Show loading indicators during HTMX requests:
1. Add `hx-indicator` class to results container
2. Create `.htmx-indicator` CSS with pulsing skeleton rows (use CSS animation, no JS)
3. Add `htmx:beforeRequest` / `htmx:afterRequest` class toggling if needed
4. Ensure screen readers announce "Loading results..." via aria-live

**Acceptance:** Filter changes show skeleton loading state before results appear.

---

### LION-004: Add "No results" empty state
**Roadmap:** 3.A3-i | **Files:** `templates/partials/results.html`, `static/css/main.css` | **Complexity:** LOW | **Tokens:** ~800 | **Time:** ~5 min
**Dependencies:** None

When search returns 0 results:
1. In `templates/partials/results.html`, add empty-state block when `results` list is empty
2. Show friendly message: "No budget items match your filters. Try broadening your search or clearing some filters."
3. Add "Clear all filters" button that resets the form
4. Style with centered text, muted color, and an icon (CSS-only, no images)

**Acceptance:** Empty search returns styled empty state with clear-filters action.

---

### LION-005: Auto-generate data dictionary from schema
**Roadmap:** 3.C2-b | **Files:** new `scripts/generate_data_dictionary.py`, `docs/data_dictionary.md` | **Complexity:** MEDIUM | **Tokens:** ~3,000 | **Time:** ~20 min
**Dependencies:** None

Automate keeping docs/data_dictionary.md in sync with the actual database schema:
1. Create `scripts/generate_data_dictionary.py` that:
   - Connects to dod_budget.sqlite (or uses schema_design.py DDL if no DB)
   - Reads PRAGMA table_info for budget_lines, pdf_pages, all reference tables
   - Reads column descriptions from a FIELD_DESCRIPTIONS dict (define in script)
   - Generates markdown with field name, type, nullable, description, source exhibit
2. Include a `--check` flag that compares generated output to existing file and exits non-zero if different (for CI)
3. Include human-written caveats section (append from template, don't auto-generate)
4. Run: `python scripts/generate_data_dictionary.py > docs/data_dictionary.md`

**Acceptance:** Script generates valid markdown matching current schema; `--check` returns 0.

---

### LION-006: Add chart export (PNG download)
**Roadmap:** 3.B1-d | **Files:** `templates/charts.html`, `static/js/app.js` | **Complexity:** LOW | **Tokens:** ~1,500 | **Time:** ~10 min
**Dependencies:** None

Allow users to download charts as PNG images:
1. Add "Download as PNG" button below each Chart.js canvas
2. Implement `downloadChartAsPNG(canvasId, filename)` in app.js using `canvas.toDataURL('image/png')`
3. Create temporary `<a>` element with download attribute to trigger browser download
4. Button should be hidden when chart has no data

**Acceptance:** Each chart has a download button; clicking it saves a PNG file.

---

### LION-007: Add URL sharing for filtered views
**Roadmap:** 3.A3-j | **Files:** `templates/index.html`, `static/js/app.js` | **Complexity:** LOW | **Tokens:** ~1,200 | **Time:** ~10 min
**Dependencies:** None

Allow users to copy a shareable URL with current filters:
1. Add "Share" button (link icon) next to the filter form
2. Implement `copyShareURL()` in app.js that copies `window.location.href` (already includes params via hx-push-url)
3. Show brief "Copied!" tooltip on click (CSS-only fade animation)
4. Ensure URL includes all active filters (keyword, fiscal_year, service, exhibit_type, appropriation, amount_min, amount_max)

**Acceptance:** Clicking Share copies current URL to clipboard with confirmation.

---

### LION-008: Add print-friendly results view
**Roadmap:** 3.A4-e | **Files:** `templates/partials/results.html`, `static/css/main.css` | **Complexity:** LOW | **Tokens:** ~1,000 | **Time:** ~10 min
**Dependencies:** None

Improve the print experience:
1. Add "Print Results" button to results header
2. Ensure `@media print` styles already in main.css hide: nav, filter sidebar, pagination, download button
3. Add print-only header showing: "DoD Budget Explorer — [active filters] — Printed [date]"
4. Ensure table fits on page (font-size reduction, landscape hint via `@page`)

**Acceptance:** Ctrl+P produces clean, readable budget table with filter context.

---

### LION-009: Enhance chart interactivity — click-to-filter
**Roadmap:** 3.B4-b | **Files:** `templates/charts.html`, `static/js/app.js` | **Complexity:** MEDIUM | **Tokens:** ~2,000 | **Time:** ~15 min
**Dependencies:** None

Make charts actionable — clicking a bar navigates to filtered results:
1. Add `onClick` handler to each Chart.js chart
2. When user clicks a bar (e.g., "Army" in service comparison), navigate to `/?service=Army`
3. For year-over-year chart, clicking FY2026 bar navigates to `/?fiscal_year=FY2026`
4. For Top-N chart, clicking a program element navigates to `/?q=[pe_number]`
5. Add pointer cursor on hover (`onHover` option in Chart.js)

**Acceptance:** Clicking any chart bar navigates to the search page with corresponding filter applied.

---

### LION-010: Add dark mode toggle
**Roadmap:** 3.A7-k | **Files:** `templates/base.html`, `static/css/main.css`, `static/js/app.js` | **Complexity:** MEDIUM | **Tokens:** ~2,500 | **Time:** ~15 min
**Dependencies:** LION-001 (base.html changes)

Add a light/dark mode toggle:
1. Add CSS custom properties (variables) for all colors in `:root` and `[data-theme="dark"]`
2. Add toggle button in header (sun/moon icon via CSS, no images)
3. Implement `toggleTheme()` in app.js that sets `data-theme` attribute on `<html>` and persists to localStorage
4. Respect `prefers-color-scheme` media query as default
5. Ensure all charts use theme-aware colors (Chart.js `defaults.color`)
6. Ensure sufficient contrast in dark mode (WCAG AA)

**Acceptance:** Toggle switches between light/dark; preference persists across sessions; charts adapt.

---

## After completing all tasks

1. Run the full frontend test suite: `pytest tests/test_frontend_routes.py tests/test_accessibility.py tests/test_frontend_helpers.py -v`
2. Mark all TODO items as DONE in the source files where you added `[Group: LION]` annotations
3. Update `REMAINING_TODOS.md` to reflect completed items
