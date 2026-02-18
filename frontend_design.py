"""
Front-End & Documentation Design — Steps 3.A, 3.B, 3.C

Plans and TODOs for the web UI, data visualizations, and user documentation.

──────────────────────────────────────────────────────────────────────────────
TODOs — Step 3.A (UI Design & Core Features)
──────────────────────────────────────────────────────────────────────────────

DONE 3.A1-a  jinja2>=3.1 + python-multipart>=0.0.6 added to requirements.txt;
    FRONTEND_TECHNOLOGY.md documents HTMX+Jinja2 decision.

DONE 3.A0-a  templates/ and static/ directories created; Jinja2Templates mounted
    in api/app.py at create_app(); StaticFiles mounted at /static;
    api/routes/frontend.py created with GET /, /charts, /partials/results,
    /partials/detail/{id}; fmt_amount Jinja2 filter registered.

DONE 3.A2-a  Templates created: templates/base.html, templates/index.html,
    templates/partials/results.html, templates/partials/detail.html,
    templates/charts.html; all render correctly.

DONE 3.A3-a  Filter sidebar in templates/index.html with keyword input + multi-select
    dropdowns (fiscal_year, service, exhibit_type) populated from reference API;
    hx-get="/partials/results" on form change + hx-push-url="true".

DONE 3.A3-b  URL query params: hx-push-url="true" on all HTMX requests; restoreFiltersFromURL()
    in static/js/app.js pre-populates form fields on page load from window.location.search.

DONE 3.A4-a  Results table in partials/results.html: sortable column headers (hx-vals for
    sort_by/sort_dir), pagination (prev/next + numbered), row count display.

DONE 3.A4-b  Column toggle buttons in results header; toggleCol() in app.js toggles
    CSS classes + persists to localStorage under key "dod_hidden_cols".

DONE 3.A5-a  Download modal in index.html; buildDownloadURL() in app.js constructs
    /api/v1/download URLs from current form state; CSV + JSON links.

DONE 3.A6-a  Detail panel: clicking a row fires hx-get="/partials/detail/{id}" into
    #detail-container; partials/detail.html shows all fields + provenance.

DONE 3.A7-a  Responsive CSS in static/css/main.css: media queries at 768px + 480px,
    horizontal table scroll, touch-friendly targets >= 44px.

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

DONE 3.B1-a  Year-over-year grouped bar chart in templates/charts.html using Chart.js 4.4.2
    via CDN; fetches /api/v1/aggregations?group_by=fiscal_year and renders bar chart.

DONE 3.B2-a  Service comparison bar chart on charts page; fetches
    /api/v1/aggregations?group_by=service and renders horizontal bar chart.

DONE 3.B3-a  Top-N horizontal bar chart on charts page; fetches
    /api/v1/budget-lines?sort_by=amount_fy2026_request&sort_dir=desc&limit=10.


──────────────────────────────────────────────────────────────────────────────
TODOs — Step 3.C (User Documentation)
──────────────────────────────────────────────────────────────────────────────

DONE 3.C1-a  docs/getting_started.md (~204 lines): What is DoD Budget Explorer?,
    data included, how to search/filter/download, how to read amounts ($K).
    Written for Congressional staffers, journalists, researchers.

DONE 3.C2-a  docs/data_dictionary.md (~572 lines): all 25 budget_lines fields
    with type, description, source exhibit, caveats; reference tables;
    API naming conventions; 8 data quality caveats.

DONE 3.C3-a  docs/faq.md (~180 lines): data currency, missing years, $K meaning,
    PB vs enacted vs CR, why totals don't reconcile, how to cite, PE numbers,
    exhibit types, error reporting.

DONE 3.C4-a  OpenAPI documentation enhanced:
    - api/app.py: rich description, rate-limit notes, tag descriptions,
      contact, license_info fields in create_app()
    - api/models.py: Field() descriptions + examples on all fields.

DONE 3.C5-a  CSS tooltips added:
    - static/css/main.css: [data-tooltip] ::after/::before rules (~50 lines)
    - templates/index.html: data-tooltip on q, fiscal_year, service,
      exhibit_type filter labels
    - templates/partials/results.html: data-tooltip on FY, Exhibit,
      Account, PE #, FY25 Enacted column headers.

DONE 3.C6-a  docs/methodology.md (~206 lines): data sources, collection process
    (Playwright/Chromium), Excel parsing (openpyxl), PDF parsing (pdfplumber),
    FTS5 architecture, known limitations, error reporting.
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
