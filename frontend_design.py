"""
Front-End & Documentation Design — Steps 3.A, 3.B, 3.C

Plans and TODOs for the web UI, data visualizations, and user documentation.

──────────────────────────────────────────────────────────────────────────────
TODOs — Step 3.A (UI Design & Core Features)
──────────────────────────────────────────────────────────────────────────────

TODO 3.A1-a: Choose front-end technology and document the decision.
    Evaluate options for a budget data explorer:
    1. React + Vite — most ecosystem support, many table/chart libraries
    2. Svelte/SvelteKit — smaller bundle, simpler reactivity model
    3. HTMX + Jinja2 templates — no JS build step, server-rendered, simplest
       deployment (single Python process serves everything)
    4. Vue 3 — middle ground between React and Svelte

    Decision factors: this is a data-heavy CRUD/search app, not a complex SPA.
    HTMX + Jinja2 is likely sufficient and drastically simplifies deployment
    (no separate frontend build/serve).  Write a decision record with rationale.
    Token-efficient tip: ~30 lines of prose.  If choosing HTMX, add
    jinja2 + python-multipart to requirements.txt.

TODO 3.A2-a: Design wireframes as ASCII art or simple HTML.
    Pages needed:
    1. Landing/search page — search bar, filter sidebar, results area
    2. Results table — sortable columns, pagination controls
    3. Detail view — full line item info, source document link, related items
    4. Download modal — format selection (CSV/JSON), filter summary
    Token-efficient tip: if using HTMX, the wireframes ARE the templates —
    write them as Jinja2 HTML directly.  ~4 files, ~50 lines each.

TODO 3.A3-a: Build the search/filter form.
    Filters: fiscal year (multi-select), service/agency (multi-select),
    appropriation (multi-select), program element (text input),
    exhibit type (multi-select), free-text search (text input).
    Each filter populates from the /reference API endpoints.
    If HTMX: use hx-get to fetch updated results on filter change.
    ~60 lines of HTML/Jinja2.

TODO 3.A3-b: Wire filter state to URL query parameters.
    Ensure that the current filter state is reflected in the URL so users
    can bookmark and share filtered views.  On page load, read filters from
    URL params and pre-populate the form.
    Token-efficient tip: if HTMX, use hx-push-url="true" on the results
    container; on load, parse window.location.search in a <script> block.
    ~20 lines of JS.

TODO 3.A4-a: Build the results table component.
    Sortable columns: Service, FY, Appropriation, Program, Amount, Exhibit Type.
    Pagination: previous/next + page number display.
    If HTMX: server renders the <tbody> partial; sorting and pagination are
    hx-get requests that swap the table body.
    ~80 lines of HTML/Jinja2.

TODO 3.A4-b: Add column toggling.
    Let users show/hide columns.  Store preference in localStorage.
    Token-efficient tip: a small JS function that toggles CSS classes on
    <th>/<td> elements.  ~25 lines of JS.

TODO 3.A5-a: Build the download button/modal.
    "Download" button triggers a modal showing: current filters summary,
    estimated row count, format selector (CSV/JSON), and a download link
    pointing to /api/v1/download with the current filters.
    ~40 lines of HTML + 10 lines of JS.

TODO 3.A6-a: Build the detail/drill-down view.
    When a user clicks a row in the results table, show a detail page/panel:
    all fields for that line item, link to the source PDF on the DoD
    Comptroller site, and a "related items" section showing the same program
    across fiscal years.
    If HTMX: hx-get="/detail/{id}" swaps a detail panel below the table.
    ~60 lines of HTML/Jinja2.

TODO 3.A7-a: Responsive design pass.
    After the core UI is built, add responsive CSS: stack filters above results
    on mobile, make the table horizontally scrollable, ensure touch targets
    are ≥44px.
    Token-efficient tip: use CSS media queries.  ~30 lines of CSS.

TODO 3.A7-b: Accessibility audit.
    Run axe-core or Lighthouse accessibility audit.  Fix: missing labels,
    insufficient contrast, missing ARIA attributes, keyboard navigation gaps.
    Token-efficient tip: this is investigative — run the tool first, then
    create follow-up TODOs for each finding.  Save for a future session after
    the UI exists.


──────────────────────────────────────────────────────────────────────────────
TODOs — Step 3.B (Data Visualization — Stretch)
──────────────────────────────────────────────────────────────────────────────

TODO 3.B1-a: Year-over-year trend chart.
    Given a PE number or appropriation, fetch /api/v1/aggregations?group_by=
    fiscal_year&pe=<pe> and render a line/bar chart.
    Library options: Chart.js (simple, no build step), Observable Plot (modern,
    lightweight), D3 (most flexible, most complex).
    Token-efficient tip: Chart.js via CDN is ~5 lines of config.  Use a
    <canvas> element and a small <script> block.  ~30 lines total.

TODO 3.B2-a: Service comparison chart.
    Bar chart comparing budget amounts across services for a selected FY.
    Fetch /api/v1/aggregations?group_by=service&fiscal_year=<fy>.
    Same library as TODO 3.B1-a for consistency.  ~25 lines.

TODO 3.B3-a: Top-N dashboard panel.
    Show top 10 budget line items by amount for the current filter set.
    Horizontal bar chart.  Fetch from /api/v1/budget-lines?sort=-amount&limit=10.
    ~25 lines.


──────────────────────────────────────────────────────────────────────────────
TODOs — Step 3.C (User Documentation)
──────────────────────────────────────────────────────────────────────────────

TODO 3.C1-a: Write Getting Started guide (docs/getting_started.md).
    Sections: What is this tool?, What data is included?, How to search,
    How to filter, How to download.  Plain language, no jargon.
    Target audience: Congressional staffers, journalists, policy researchers.
    ~150 lines of markdown.

TODO 3.C2-a: Write data dictionary (docs/data_dictionary.md).
    For every field visible in the UI and API: field name, type, description,
    source (which exhibit/column it comes from), caveats.
    Token-efficient tip: generate a skeleton from the schema DDL, then add
    prose descriptions.  ~200 lines.

TODO 3.C3-a: Write FAQ (docs/faq.md).
    Questions to answer:
    - How current is the data?
    - Why are some years missing?
    - What does "thousands of dollars" mean?
    - What's the difference between PB and enacted?
    - Why don't service totals match the DoD total exactly?
    - Can I cite this tool in a report?
    ~100 lines.

TODO 3.C4-a: Generate OpenAPI documentation.
    If using FastAPI, this is automatic at /docs.  Customize: add descriptions
    to each endpoint, add example requests/responses to Pydantic models,
    add a top-level API description with usage guide.
    Token-efficient tip: this is all done via docstrings and Pydantic Field()
    descriptions — no separate doc to write.  ~30 lines of additions to the
    existing route/model code.

TODO 3.C5-a: Add contextual help to the UI.
    For each filter and table column, add a tooltip (title attribute or a
    small info icon with a popover) explaining what it means.  Derive text
    from the data dictionary.
    Token-efficient tip: a CSS-only tooltip using ::after pseudo-element and
    data-tooltip attributes.  ~20 lines of CSS + HTML attributes.

TODO 3.C6-a: Write methodology & limitations page (docs/methodology.md).
    Explain: data sources (URLs), collection process, parsing approach,
    known limitations (PDF extraction accuracy, coverage gaps per FY/service),
    how to report errors.
    ~120 lines.
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
