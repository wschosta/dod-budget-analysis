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
