# DoD Budget Explorer: GUI Decisions & Open Questions

This document catalogs unresolved design decisions and open questions for the DoD Budget Explorer web interface. Each item is grounded in observations from the current codebase and is intended to guide stakeholder discussions, prioritize the backlog, and ensure the interface meets the needs of its target audience. Items are organized by domain and tagged with a priority level (**High**, **Medium**, or **Low**) reflecting their likely impact on usability, correctness, or adoption.

---

## 1. Use Cases & User Workflows

Understanding who uses this tool and how they use it determines nearly every downstream design choice.

| # | Question / Decision | Priority | Context |
|---|---------------------|----------|---------|
| 1.1 | **Who are the primary user personas?** Defense budget analysts, investigative journalists, academic researchers, congressional staff, or general public? Each group implies different defaults for complexity, export formats, and terminology. | **High** | The current UI exposes raw column names like `amount_fy2026_request` and exhibit type codes (`R-2`, `P-5`, `O-1`) without inline definitions beyond tooltips. Analysts may be comfortable with this; journalists may not. |
| 1.2 | **What are the top 5 tasks users want to accomplish?** Candidates include: (a) find a specific program's funding history, (b) compare service budgets year-over-year, (c) export a filtered dataset for offline analysis, (d) browse the largest budget items, (e) share a filtered view with a colleague. Are these correct, and what is their rank order? | **High** | Current navigation order (Dashboard, Search, Charts, Programs, About) implies browsing-first, but the root URL (`/`) serves the Search page, suggesting search is actually the primary entry point. |
| 1.3 | **Should the tool support side-by-side comparison of budget items across years?** | **Medium** | The Charts page has a "Budget Comparison" widget (`VIZ-005`) that compares two services across fiscal years, but there is no way to select two arbitrary budget line items from the search results and compare them side by side. |
| 1.4 | **Should the Search page or the Dashboard be the landing page?** | **High** | Currently `/` renders `index.html` (Search) while `/dashboard` is a separate nav link. The dashboard loads summary stats and charts via client-side API calls. If most users arrive wanting an overview, the dashboard may be a better default. |
| 1.5 | **How important is export (CSV/JSON/XLSX) vs. in-app analysis?** | **Medium** | The download modal supports CSV, NDJSON, and Excel with up to 50,000 rows. If users primarily export and work in Excel/Python, investment should shift toward richer export options (e.g., pivot-ready formats). If users stay in the browser, investment should go toward in-app filtering and charting. |

---

## 2. Data & Functionality

| # | Question / Decision | Priority | Context |
|---|---------------------|----------|---------|
| 2.1 | **The Amount Range filter is hardcoded to the `amount_fy2026_request` column.** Should it dynamically filter on whichever FY column(s) the user has visible via the column toggles? | **High** | In `frontend.py` lines 207-222, the WHERE clause explicitly references `amount_fy2026_request >= ?` and `amount_fy2026_request <= ?`. If a user hides FY26 columns and only shows FY24 Actual, the amount filter still operates on FY26, which is confusing. |
| 2.2 | **Should users be able to filter by multiple amount columns simultaneously?** For example, "show lines where FY24 Actual > $10M AND FY26 Request > $15M." | **Low** | No current UI or backend support. Would require a more advanced filter builder. |
| 2.3 | **How should "related items" in the detail panel be determined?** | **Medium** | `frontend.py` lines 362-386 first match on `pe_number`, then fall back to matching `organization_name + line_item_title`. The fallback may surface false positives (e.g., two different programs with the same generic title like "Program Management" at the same organization). Should the fallback be tightened or removed? |
| 2.4 | **Should the Programs page require PE enrichment data, or should it work with just `budget_lines`?** | **Medium** | `frontend.py` line 412 checks `_table_exists(conn, "pe_index")` and silently returns an empty list if the table is absent. Users see an empty Programs page with no explanation. The `/programs/{pe_number}` route raises a 404 with a message to "Run enrich_budget_db.py." Should there be a more prominent UI notice, or should Programs derive cards from `budget_lines` directly? |
| 2.5 | **Should there be a "compare" feature on the Search page?** Users would select 2+ rows via checkboxes and view a side-by-side comparison panel. | **Medium** | The `checkbox-select.js` script is already loaded in `base.html` (line 85), but no multi-row selection checkboxes appear in the results table. The infrastructure may be partially in place. |
| 2.6 | **Is the autocomplete keyword search sufficient, or should there be advanced search with field-specific operators?** (e.g., `service:Army AND exhibit:R-2 AND amount>50000`) | **Low** | The current search uses FTS5 (`sanitize_fts5_query`) across all indexed text. Power users (analysts, researchers) may want structured queries. |
| 2.7 | **Should there be saved views/dashboards with server-side persistence?** | **Low** | Saved searches currently use `localStorage` only (client-side). The "Save" button in `index.html` line 108 calls `saveCurrentSearch(name)` which stores to the browser. Sharing saved searches across devices or teams is not possible. |

---

## 3. Navigation & Information Architecture

| # | Question / Decision | Priority | Context |
|---|---------------------|----------|---------|
| 3.1 | **Is the current nav order correct?** Dashboard, Search, Charts, Programs, About, API Docs. | **Medium** | In `base.html` lines 52-57, Dashboard appears first but Search is the `/` route. Users clicking the site title "DoD Budget Explorer" go to Search, not Dashboard, creating a potential disconnect. |
| 3.2 | **Should "Programs" be a top-level nav item or a sub-section of Search?** | **Medium** | Programs is conceptually a filtered, enriched view of the same budget data. It could be a tab within Search rather than a separate page, reducing navigation fragmentation. |
| 3.3 | **Should the API Docs link open in a new tab (current behavior) or be an in-app page?** | **Low** | `base.html` line 57 uses `target="_blank"`. The Swagger UI (`/docs`) and ReDoc (`/redoc`) are both available. Opening in a new tab is standard for developer docs but may surprise non-technical users. |
| 3.4 | **Is the footer adequate?** Should it include version info, last data refresh date, or data coverage statistics? | **Low** | The footer (`base.html` lines 71-79) currently shows only the data source link, a disclaimer, an API link, and a Feedback button. The app version (`1.0.0` from `app.py`) and data freshness ("refreshed weekly via GitHub Actions") are not surfaced to end users. |

---

## 4. Visual Design & Style Preferences

| # | Question / Decision | Priority | Context |
|---|---------------------|----------|---------|
| 4.1 | **Color palette: Should the current navy/blue/gray theme reference official DoD branding?** | **Low** | CSS custom properties in `main.css` lines 7-17 define `--clr-navy: #1a3a5c`, `--clr-blue: #2563eb`, etc. These are functional but generic. Official DoD visual identity guidelines exist and could lend credibility. |
| 4.2 | **Typography: Should the app use a specific typeface instead of `system-ui`?** | **Low** | `main.css` line 83: `font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`. System fonts load instantly but vary across platforms. A defined typeface (e.g., Inter, Source Sans Pro) would ensure visual consistency. |
| 4.3 | **Dark mode: Several hardcoded colors bypass CSS custom properties and do not adapt to dark mode.** Should dark mode be fully polished? | **Medium** | Specific instances found in template inline styles: `color:#555` appears in `index.html` line 174 and `results.html` line 132; `color:#888` in `results.html` line 51. The selected-row highlight `#dbeafe` in `main.css` line 331 is a hardcoded light-blue that does not invert in dark mode. The `border:1px solid #ddd` in `charts.html` lines 11, 22, 72, 78 also remains unchanged. |
| 4.4 | **Chart colors: Should the 10-color palette be colorblind-friendly?** Should there be a colorblind mode toggle? | **Medium** | `charts.html` line 123 defines `COLORS = ['#2563eb','#16a34a','#d97706','#dc2626','#7c3aed','#0891b2','#c2410c','#065f46','#92400e','#1e1b4b']`. The green (`#16a34a`) and red (`#dc2626`) pair is problematic for red-green colorblind users, which affects approximately 8% of males. |
| 4.5 | **Should amount formatting include a toggle between $K (current), $M, and $B?** | **Medium** | All amounts display in $K in the results table (via the `fmt_amount` Jinja filter) and in $M in the charts (divided by 1000 in JavaScript). There is no user control. For large programs (billions), $K values like `8,234,567.0` are harder to scan than `$8.2B`. |
| 4.6 | **Should there be data density options (compact / comfortable / spacious) for table rows?** | **Low** | The results table uses fixed padding. Analysts viewing many rows may prefer compact density; casual users may prefer spacious. |
| 4.7 | **Print styles: Is the current print format the desired one?** | **Low** | `main.css` lines 735-814 hide the sidebar, header, footer, buttons, and pagination for print. The page size is set to landscape. The print header (`.print-header` in `index.html` lines 131-140) shows active filters and print date. Should the print output include summary totals, a page count, or a footer with the source URL? |

---

## 5. Accessibility

| # | Question / Decision | Priority | Context |
|---|---------------------|----------|---------|
| 5.1 | **Should WCAG 2.1 AA be the target compliance level?** | **High** | Several accessibility features are already in place: skip-link (`base.html` line 40), `aria-live` regions (`index.html` lines 148-156), keyboard shortcuts (`/`, `Ctrl+K`, `Escape` in `app.js` lines 336-377), `focus-visible` outlines (`main.css` lines 604-613), and screen-reader-only text (`.sr-only` class). These suggest AA was intended but has not been formally verified. |
| 5.2 | **Color contrast: Do all text/background combinations meet the 4.5:1 ratio?** | **High** | Inline styles using `color:#555` on white backgrounds yield a contrast ratio of approximately 4.6:1, which barely passes AA for normal text but fails for the smaller font sizes (`.78rem`, `.75rem`) where those colors are used. `color:#888` on white yields only 3.5:1, which fails AA. In dark mode, these hardcoded colors would appear against dark backgrounds with even worse contrast. |
| 5.3 | **Screen reader experience: Is the HTMX partial swap approach providing adequate announcements?** | **Medium** | The `#results-container` div has `aria-live="polite"` and `aria-atomic="false"` (`index.html` lines 153-156). When HTMX swaps in new content, assistive technology should announce changes, but partial swaps of large HTML tables may produce noisy or incomplete announcements. Has this been tested with NVDA, JAWS, or VoiceOver? |
| 5.4 | **Should there be a "reduce motion" mode that suppresses skeleton loading animations and chart transitions?** | **Low** | Skeleton rows (`.skeleton-loading` in `results.html`) use CSS animation. Chart.js uses default animation on render. Users with vestibular disorders may prefer reduced motion. A `@media (prefers-reduced-motion: reduce)` rule could disable these. |
| 5.5 | **Table rows are clickable but lack explicit `role="button"` or `tabindex="0"`.** Should table row selection be fully keyboard-accessible via arrow keys? | **Medium** | In `results.html` line 123, `<tr>` elements have `hx-get` and `onclick="selectRow(this)"` but no `tabindex` or ARIA role to indicate they are interactive. Keyboard-only users cannot tab to individual rows or use arrow keys to navigate. |

---

## 6. Performance & Responsiveness

| # | Question / Decision | Priority | Context |
|---|---------------------|----------|---------|
| 6.1 | **Mobile experience: Should the filter sidebar be a collapsible drawer instead of stacking above results?** | **Medium** | At `max-width: 768px` (`main.css` line 570), the `.search-layout` grid collapses to a single column, placing the entire filter panel above the results. On mobile, users must scroll past all filters before seeing any data. A slide-in drawer or collapsible accordion would improve the experience. |
| 6.2 | **Tablet experience: There is no breakpoint between 480px and 768px.** Should one be added? | **Low** | `main.css` has breakpoints at 768px (line 570) and 480px (line 599). Tablets in portrait mode (around 600px) fall into the mobile layout, which may waste horizontal space. |
| 6.3 | **Should charts be lazy-loaded (only render when scrolled into view)?** | **Low** | The Charts page loads all 7 charts simultaneously via `Promise.all` in `charts.html` line 196. On slow connections or devices, this makes 6+ API calls at once. `IntersectionObserver` could defer rendering off-screen charts. |
| 6.4 | **Should search results support infinite scroll instead of (or in addition to) pagination?** | **Low** | Current pagination (`results.html` lines 157-194) uses HTMX page buttons. Infinite scroll would provide a more fluid browse experience but complicates URL state and "share this view" workflows. |
| 6.5 | **CDN dependencies: Should HTMX, Chart.js, and the treemap plugin be self-hosted for reliability?** | **Medium** | `base.html` lines 28-32 load three scripts from `unpkg.com` and `cdn.jsdelivr.net`. If either CDN experiences an outage, the entire application breaks. Self-hosting (or using a fallback loader) would improve reliability. Note: SRI integrity hashes were previously added but removed due to version mismatches (`FIX-001`). |

---

## 7. Feature Gaps & Enhancements to Consider

| # | Feature Idea | Priority | Notes |
|---|--------------|----------|-------|
| 7.1 | **Toast notifications** for user actions (download started, feedback submitted, URL copied, search saved). | **Medium** | The Share button (`index.html` line 104) copies a URL to clipboard via `copyShareURL()` but provides no visible confirmation to the user. The feedback form submission similarly provides no toast on success or failure. |
| 7.2 | **Keyboard navigation through table rows** using arrow keys (Up/Down to move selection, Enter to expand detail). | **Medium** | Currently only click and HTMX-get trigger row detail. No `tabindex` on rows, no arrow-key handler. |
| 7.3 | **Bulk actions**: Select multiple rows via checkboxes, then export selected or compare selected. | **Low** | `checkbox-select.js` is loaded globally (`base.html` line 85) but not visibly integrated into the results table. |
| 7.4 | **Data dictionary / glossary page** explaining exhibit types, amount columns, appropriation codes, and PE number formats. | **Medium** | Tooltips on filter labels and column headers (`data-tooltip` attributes in `index.html` and `results.html`) provide some context, but a dedicated reference page would help new users. A `docs/data_dictionary.md` file exists in the repo but is not linked from the UI. |
| 7.5 | **URL shortener or permalink service** for shared filtered views. | **Low** | The Share button copies the full URL with all query parameters, which can be very long. A server-side short URL would be cleaner for sharing. |
| 7.6 | **Embed mode** for iframes: a `?embed=true` query parameter that hides the header and footer so the search or charts can be embedded in external sites. | **Low** | The `X-Frame-Options: DENY` header in `app.py` line 438 currently prevents any iframe embedding. Embed mode would require relaxing this for specific paths. |
| 7.7 | **"Back to top" button** for the search results page after scrolling through long result sets. | **Low** | No current implementation. Long tables on mobile can leave users far from the filter sidebar. |

---

## 8. Technical Debt & Architecture Questions

| # | Question / Decision | Priority | Context |
|---|---------------------|----------|---------|
| 8.1 | **CSP uses `'unsafe-inline'` for both scripts and styles.** Should the app migrate to nonce-based CSP? | **Medium** | `app.py` line 429: `script-src 'self' unpkg.com cdn.jsdelivr.net 'unsafe-inline'`. The inline `<script>` block in `base.html` lines 9-16 (dark mode initialization) and the large inline `<script>` in `charts.html` lines 119-741 require `unsafe-inline`. Moving these to external `.js` files and using nonce-based CSP would improve security posture. |
| 8.2 | **Should the inline chart JavaScript in `charts.html` (620+ lines) be extracted to a separate file?** | **Medium** | `charts.html` contains approximately 620 lines of inline JavaScript (lines 119-741) defining all chart loading functions. This prevents browser caching of the JS separately from the HTML, makes testing harder, and is the primary reason `'unsafe-inline'` is needed in the CSP. |
| 8.3 | **Rate limiting defaults: Are 60 search/min and 10 download/min appropriate?** | **Low** | Defined in `app.py` lines 92-96 via `AppConfig`. The search limit (60/min) allows about 1 request per second, which could be restrictive for rapid filter toggling via HTMX (each filter change triggers a search request). The download limit (10/min) seems reasonable. |
| 8.4 | **Caching strategy: The 5-minute TTL for reference data -- should this be configurable at runtime?** | **Low** | `frontend.py` lines 55-57 create `TTLCache` instances with `ttl_seconds=300`. This is hardcoded. If reference data rarely changes, a longer TTL would reduce database queries. If data is refreshed during a running session, a shorter TTL or cache-bust mechanism would help. |
| 8.5 | **Error handling: Many chart and API failures are silently caught.** Should there be a global error toast? | **Medium** | In `charts.html` line 731, the `populateServiceDropdowns` function has an empty `catch(e) {}` block. In `frontend.py` lines 413-424 and 477-492, the Programs page catches all exceptions and silently returns empty results. Users see blank sections with no indication of what went wrong. |
| 8.6 | **Inline styles are used extensively in templates.** Should these be migrated to CSS classes? | **Low** | Templates like `index.html`, `charts.html`, `results.html`, and `detail.html` contain numerous `style="..."` attributes for layout (flex, gap, margins, font sizes, colors). This makes the styles harder to maintain, overrides the cascade, and prevents dark-mode adaptation for hardcoded color values. |
| 8.7 | **The dashboard page loads all data client-side via fetch calls.** Should it use server-side rendering like the Search page? | **Low** | `dashboard.html` renders an empty shell with placeholder stat cards (`--`) and hidden chart containers, then loads everything via `dashboard.js`. The Search page, by contrast, renders server-side via `_query_results()` in `frontend.py`. The inconsistency means the dashboard shows a loading spinner on every page visit while Search renders instantly. |

---

## Summary of High-Priority Items

The following decisions should be resolved first, as they have the broadest impact on usability and correctness:

1. **1.1** -- Define primary user personas to anchor all subsequent design decisions.
2. **1.2** -- Identify and rank the top 5 user tasks.
3. **1.4** -- Decide whether Search or Dashboard should be the landing page.
4. **2.1** -- Fix the Amount Range filter to operate on the correct column context.
5. **5.1** -- Confirm WCAG 2.1 AA as the target accessibility standard.
6. **5.2** -- Audit and fix color contrast failures (particularly `#555` and `#888` on light/dark backgrounds).

---

*Document generated from codebase analysis. Last updated: 2026-02-20.*
