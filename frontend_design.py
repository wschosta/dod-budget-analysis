"""
Front-End & Documentation Design — Steps 3.A, 3.B, 3.C

Plans and TODOs for the web UI, data visualizations, and user documentation.

──────────────────────────────────────────────────────────────────────────────
TODOs — Step 3.A (UI Design & Core Features)
──────────────────────────────────────────────────────────────────────────────

TODO 3.A1-a [Complexity: LOW] [Tokens: ~1000] [User: NO]
    DONE — FRONTEND_TECHNOLOGY.md already documents HTMX+Jinja2 decision.
    Steps:
      1. Verify FRONTEND_TECHNOLOGY.md is complete
      2. Add jinja2 + python-multipart to requirements.txt if not present
    Success: Decision documented; deps in requirements.txt.

TODO 3.A0-a [Complexity: MEDIUM] [Tokens: ~2500] [User: NO]
    Create Flask app that serves HTMX templates alongside the FastAPI API.
    This is a prerequisite for all 3.A2-* through 3.A7-* TODOs.
    Steps:
      1. Create templates/ and static/ directories
      2. Add Flask or Starlette template serving to the FastAPI app
         (FastAPI supports Jinja2Templates natively)
      3. Create templates/base.html with: nav, CSS reset, HTMX CDN include
      4. Create GET / route that renders templates/index.html
      5. Add `jinja2` to requirements.txt
    Success: GET / returns HTML page; HTMX loaded and functional.

TODO 3.A2-a [Complexity: MEDIUM] [Tokens: ~3000] [User: NO]
    Create wireframe templates as Jinja2 HTML (4 files).
    Dependency: TODO 3.A0-a (Flask/template structure) must exist.
    Steps:
      1. templates/index.html — landing page with search bar + filter sidebar
      2. templates/partials/results.html — table partial for HTMX swap
      3. templates/partials/detail.html — line item detail panel
      4. templates/partials/filters.html — filter sidebar partial
      5. Each ~50 lines of HTML/Jinja2
    Success: Pages render with placeholder data and correct layout.

TODO 3.A3-a [Complexity: MEDIUM] [Tokens: ~2500] [User: NO]
    Build the search/filter form with HTMX.
    Steps:
      1. In templates/partials/filters.html, create form with:
         fiscal year multi-select, service multi-select, appropriation
         multi-select, PE text input, exhibit type multi-select, free text
      2. Populate each dropdown from /api/v1/reference/* endpoints
      3. Add hx-get on filter change to reload results partial
    Success: Changing any filter updates the results table live.

TODO 3.A3-b [Complexity: LOW] [Tokens: ~1000] [User: NO]
    Wire filter state to URL query parameters.
    Steps:
      1. Add hx-push-url="true" to results container
      2. On page load, parse window.location.search in <script> block
      3. Pre-populate form fields from URL params (~20 lines JS)
    Success: Users can bookmark and share filtered views via URL.

TODO 3.A4-a [Complexity: MEDIUM] [Tokens: ~3000] [User: NO]
    Build the results table with server-rendered sorting + pagination.
    Steps:
      1. In templates/partials/results.html, render <table> with columns:
         Service, FY, Appropriation, Program, Amount, Exhibit Type
      2. Sortable column headers: hx-get with sort param swaps <tbody>
      3. Pagination: previous/next + page number display
      4. ~80 lines HTML/Jinja2
    Success: Click column header → sorted results; click next → page 2.

TODO 3.A4-b [Complexity: LOW] [Tokens: ~1000] [User: NO]
    Add column toggling (show/hide columns).
    Steps:
      1. Add toggle checkboxes above table
      2. JS function toggles CSS classes on <th>/<td> (~25 lines)
      3. Store preference in localStorage
    Success: Hidden columns persist across page reloads.

TODO 3.A5-a [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Build the download button/modal.
    Steps:
      1. "Download" button opens modal showing: current filters summary,
         estimated row count, format selector (CSV/JSON)
      2. Download link points to /api/v1/download with current filters
      3. ~40 lines HTML + 10 lines JS
    Success: User can download filtered data as CSV or JSON.

TODO 3.A6-a [Complexity: MEDIUM] [Tokens: ~2500] [User: NO]
    Build the detail/drill-down view.
    Steps:
      1. Click row in results table → hx-get="/detail/{id}"
      2. Detail panel shows: all fields, source PDF link, related items
         (same program across fiscal years)
      3. ~60 lines HTML/Jinja2
    Success: Clicking any row shows full detail below table.

TODO 3.A7-a [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Responsive design pass.
    Steps:
      1. CSS media queries: stack filters above results on mobile
      2. Table: horizontal scroll on small screens
      3. Touch targets >= 44px
      4. ~30 lines of CSS additions
    Success: UI usable on mobile (320px+ viewport).

TODO 3.A7-b [Complexity: LOW] [Tokens: ~1000] [User: YES — needs running UI]
    Accessibility audit.
    Steps:
      1. Run Lighthouse or axe-core on the running UI
      2. Fix: missing labels, contrast, ARIA attrs, keyboard nav
      3. Create follow-up TODOs for each finding
    Dependency: All 3.A2-3.A6 must be implemented first.
    Success: Lighthouse accessibility score >= 90.


──────────────────────────────────────────────────────────────────────────────
TODOs — Step 3.B (Data Visualization — Stretch Goals)
──────────────────────────────────────────────────────────────────────────────

TODO 3.B1-a [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Year-over-year trend chart (Chart.js via CDN).
    Steps:
      1. Fetch /api/v1/aggregations?group_by=fiscal_year&pe=<pe>
      2. Render line/bar chart in <canvas> element
      3. ~30 lines total (5 lines Chart.js config + HTML)
    Success: Selecting a PE shows a multi-year budget trend line.

TODO 3.B2-a [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Service comparison bar chart.
    Steps:
      1. Fetch /api/v1/aggregations?group_by=service&fiscal_year=<fy>
      2. Render horizontal bar chart comparing service budgets
      3. Same Chart.js library as 3.B1-a
    Success: Bar chart shows relative budget sizes per service.

TODO 3.B3-a [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Top-N dashboard panel (top 10 budget lines).
    Steps:
      1. Fetch /api/v1/budget-lines?sort=-amount&limit=10
      2. Render horizontal bar chart
    Success: Dashboard shows largest budget items for current filters.


──────────────────────────────────────────────────────────────────────────────
TODOs — Step 3.C (User Documentation)
──────────────────────────────────────────────────────────────────────────────

TODO 3.C1-a [Complexity: LOW] [Tokens: ~3000] [User: NO]
    Write Getting Started guide (docs/getting_started.md).
    Steps:
      1. Sections: What is this?, Data included, How to search/filter/download
      2. Plain language for: Congressional staffers, journalists, researchers
      3. ~150 lines of markdown
    Success: Non-technical users can use the tool after reading this.

TODO 3.C2-a [Complexity: MEDIUM] [Tokens: ~4000] [User: NO]
    Write data dictionary (docs/data_dictionary.md).
    Steps:
      1. Generate skeleton from schema DDL (one entry per field)
      2. For each: field name, type, description, source exhibit, caveats
      3. ~200 lines of markdown
    Success: Every field in UI/API is documented with provenance.

TODO 3.C3-a [Complexity: LOW] [Tokens: ~2000] [User: NO]
    Write FAQ (docs/faq.md).
    Steps:
      1. Answer: data currency, missing years, "thousands" meaning,
         PB vs enacted, service total discrepancies, citation guidance
      2. ~100 lines of markdown
    Success: Common user questions answered.

TODO 3.C4-a [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Customize OpenAPI documentation.
    Steps:
      1. Add rich descriptions to each FastAPI endpoint docstring
      2. Add example requests/responses to Pydantic Field() definitions
      3. Add top-level API description in create_app()
    Dependency: Requires API endpoints to exist (Phase 2).
    Success: /docs page has complete, useful API documentation.

TODO 3.C5-a [Complexity: LOW] [Tokens: ~1000] [User: NO]
    Add contextual help tooltips to the UI.
    Steps:
      1. Add data-tooltip attributes to filter labels + table headers
      2. CSS-only tooltip using ::after pseudo-element (~20 lines)
      3. Derive tooltip text from data dictionary
    Success: Hovering any filter/column shows explanatory tooltip.

TODO 3.C6-a [Complexity: LOW] [Tokens: ~2500] [User: NO]
    Write methodology & limitations page (docs/methodology.md).
    Steps:
      1. Explain: data sources, collection process, parsing approach
      2. Document: known limitations (PDF accuracy, coverage gaps)
      3. Include: how to report errors
      4. ~120 lines of markdown
    Success: Transparency about data quality and collection methods.
"""

# Placeholder — front-end structure will be created when implementation begins.
# Suggested structure if HTMX + Jinja2:
#   templates/
#     base.html         — layout with nav, CSS, JS includes
#     index.html        — search/filter page
#     partials/
#       results.html    — results table (swapped by HTMX)
#       detail.html     — line item detail panel
#       filters.html    — filter sidebar
#   static/
#     css/style.css     — custom styles
#     js/app.js         — minimal JS (column toggle, chart init)
