# DoD Budget Explorer: GUI Decisions & Open Questions

This document catalogs design decisions (resolved and open) for the DoD Budget Explorer web interface. Each item is grounded in observations from the current codebase and is intended to guide development, prioritize the backlog, and ensure the interface meets the needs of its target audience. Items are organized by domain and tagged with a priority level (**High**, **Medium**, or **Low**) and a status (**RESOLVED** or **OPEN**).

---

## 1. Use Cases & User Workflows

Understanding who uses this tool and how they use it determines nearly every downstream design choice.

| # | Question / Decision | Priority | Status | Context |
|---|---------------------|----------|--------|---------|
| 1.1 | **Who are the primary user personas?** | **High** | **RESOLVED** | See decision below. |
| 1.2 | **What are the top use cases (ranked)?** | **High** | **RESOLVED** | See decision below. |
| 1.3 | **How should "across" and "down" analysis work?** | **Medium** | **RESOLVED** | See decision below. |
| 1.4 | **Should the Search page or the Dashboard be the landing page?** | **High** | **RESOLVED** | See decision below. |
| 1.5 | **How should views be shared?** | **Medium** | **RESOLVED** | See decision below. |
| 1.6 | **Should a news/context layer be part of MVP?** | **Medium** | **RESOLVED** | Deferred to post-MVP. |

### 1.1 -- User Personas (RESOLVED)

Three persona tiers, each implying different UI defaults:

| Persona | Knowledge Level | Primary Goal | Implications |
|---|---|---|---|
| **Analyst** | Expert -- knows PE lines, wants Spruill charts, knows specific outputs needed | Targeted report generation on specific PE lines or topic areas | Needs raw data access, PE-level search, Spruill chart output, export to formatted tables |
| **Industry / Journalist** | Moderate -- knows program names, not budget structure nuance | Trend analysis in a given area, understanding budget trajectories | Needs search by program name or topic, trend charts, ability to see budget docs for nuance |
| **General Public** | Low -- topic-driven, curiosity-driven | Browse and understand where tax dollars go, general research | Needs intuitive visuals (river/Sankey charts), clickable summary views, program background info |

**Design implication:** The GUI must serve both **precision workflows** (analyst building a specific query) and **exploration workflows** (journalist or citizen browsing). This tension must be resolved through progressive disclosure -- simple by default, powerful on demand.

### 1.2 -- Top Use Cases (RESOLVED, ranked)

1. **Targeted reporting** -- Search by tags, PE lines, or free-text to identify a topic area (e.g., "hypersonics" defined by a tag or a list of PE lines). Produce an expenditure report showing the department's total spend in that area. Export both raw data and formatted tables. User must be able to see the data sources and recreate/share the view.

2. **Trend analysis** -- Two dimensions:
   - **"Across"**: All available fiscal years for a given PE line (how has this program's funding changed over time?)
   - **"Down"**: Comparing multiple PE lines within the same fiscal year (how do programs compare in a given year?)
   - Includes RDT&E vs. procurement breakdowns, biggest program outlays. Users need the ability to pull up underlying budget documents to understand nuances.

3. **Browsing / discovery** -- User has a topic interest (e.g., "hypersonics") but no specific product in mind. Involves:
   - Graphical presentation of budget data (river/Sankey charts showing how pieces build up to the total defense budget)
   - Program background information
   - *Future (post-MVP):* Linked news articles explaining year-over-year changes in specific programs

### 1.3 -- Query Model: Search-Then-Filter (RESOLVED)

The interaction model is **search-then-filter**, not a pivot table:
- User starts by picking a PE line, tag, or free-text search
- Results display all available fiscal years for matching items
- User then filters down (by year, service, appropriation type, etc.)

This replaces the original question about "side-by-side comparison across years." The comparison is implicit in showing all fiscal years for a result set.

### 1.4 -- Landing Page (RESOLVED)

**Hybrid landing page:** A prominent search bar over summary visuals (charts, top-level budget breakdowns). The summary visuals must be **clickable** -- clicking a visual element (e.g., a service's bar in a summary chart) navigates the user to the search results as if they had searched for that item. This serves all three personas: analysts can search immediately, browsers can click into visuals.

### 1.5 -- Shareability: URL-Based State (RESOLVED)

Views will be shareable via **URL query parameters** (e.g., `?pe=0603285E,0604856E&fy=2024,2025&view=table`). This makes views bookmarkable, shareable via copy-paste, and reproducible. React Router (or equivalent) will sync UI state to the URL. This is straightforward to implement and avoids the need for server-side saved report infrastructure in MVP.

### 1.6 -- News/Context Layer (RESOLVED -- Deferred)

Linking external news articles and program context descriptions to budget line items is a **post-MVP feature**. It requires a data pipeline (news ingestion, matching to PE lines) that is out of scope for the initial release.

---

## 2. Data & Functionality

| # | Question / Decision | Priority | Status | Context |
|---|---------------------|----------|--------|---------|
| 2.1 | **Must-have chart types for MVP?** | **High** | **RESOLVED** | See decision below. |
| 2.2 | **Data granularity -- PE-level vs. project-level?** | **High** | **RESOLVED** | See decision below. |
| 2.3 | **Dollar normalization -- inflation-adjusted vs. nominal?** | **High** | **RESOLVED** | See decision below. |
| 2.4 | **What does "formatted table" export mean?** | **Medium** | **RESOLVED** | See decision below. |
| 2.5 | **Amount Range filter hardcoded to FY2026 column.** Should it dynamically filter on whichever FY column(s) the user has visible? | **High** | **OPEN** | In `frontend.py` lines 207-222, the WHERE clause explicitly references `amount_fy2026_request`. If a user hides FY26 columns and only shows FY24 Actual, the amount filter still operates on FY26. |
| 2.6 | **Should users be able to filter by multiple amount columns simultaneously?** | **Low** | **OPEN** | No current UI or backend support. Would require a more advanced filter builder. |
| 2.7 | **How should "related items" in the detail panel be determined?** | **Medium** | **OPEN** | `frontend.py` lines 362-386 first match on `pe_number`, then fall back to matching `organization_name + line_item_title`. The fallback may surface false positives. |
| 2.8 | **Should the Programs page require PE enrichment data, or work with just `budget_lines`?** | **Medium** | **OPEN** | `frontend.py` line 412 checks `_table_exists(conn, "pe_index")` and silently returns an empty list if absent. |
| 2.9 | **Should there be a "compare" feature on the Search page?** | **Medium** | **OPEN** | `checkbox-select.js` is loaded but no multi-row selection checkboxes appear in the results table. |
| 2.10 | **Is the autocomplete keyword search sufficient, or should there be advanced search with field-specific operators?** | **Low** | **OPEN** | Current search uses FTS5 across all indexed text. Power users may want structured queries. |
| 2.11 | **Should there be saved views/dashboards with server-side persistence?** | **Low** | **OPEN** | Saved searches currently use `localStorage` only. |

### 2.1 -- Chart Types for MVP (RESOLVED)

**MVP charts (Phase 1-2):**
- Bar charts (year-over-year comparison for a PE line or group)
- Stacked bar / area charts (showing how sub-items build up to a total)
- Sortable, filterable tables
- Spruill charts (classic analyst deliverable)

**Deferred to Phase 3+ (nice-to-have):**
- Sankey / river charts (budget rollup visualization showing how pieces build to total defense budget)

### 2.2 -- Data Granularity: Project-Level Detail (RESOLVED)

The GUI should drill down to **project-level detail**, not just PE-level summaries. This is critical because:
- Some PE lines cover multiple programs, so PE-level aggregation can obscure important distinctions
- Where available, **tagging should happen at the project level**, not the PE level
- Accomplishment/plans text should be viewable year-over-year at the project level

**Display hierarchy:** PE Line → Project(s) → Accomplishment text (by fiscal year)

### 2.3 -- Dollar Representation: Source Fidelity (RESOLVED)

**Core principle: Never display budget data that does not come from a source document. The only exception is summations (totals computed from source data).**

- Do NOT attempt to adjust, inflate, or deflate any numbers
- Display exactly what the budget documents report
- If the budget documents contain both inflation-adjusted (constant-year) and nominal (then-year) figures, identify which is which and display both
- A toggle may be offered to switch between the two views, but only when both are present in the source data
- All displayed values must be traceable to their source document

### 2.4 -- Formatted Table Export (RESOLVED)

"Formatted table" means a **styled Excel workbook** with:
- Proper column headers and formatting
- Column widths, number formatting, totals row
- Data source attribution

Export formats supported:
- **Excel (.xlsx)** -- primary format
- **PDF** -- for sharing/printing
- **Image** -- for embedding in presentations or reports

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

## Summary

### Resolved Decisions
- **1.1** -- Three user personas defined: Analyst (expert), Industry/Journalist (moderate), General Public (low knowledge)
- **1.2** -- Three use case tiers ranked: (1) Targeted reporting, (2) Trend analysis ("across" and "down"), (3) Browsing/discovery
- **1.3** -- Query model is search-then-filter (not pivot table)
- **1.4** -- Hybrid landing page: search bar over clickable summary visuals
- **1.5** -- URL-based state for shareable/bookmarkable views
- **1.6** -- News/context layer deferred to post-MVP
- **2.1** -- MVP charts: bar, stacked bar, tables, Spruill. Sankey/river deferred to Phase 3
- **2.2** -- Project-level detail with tagging at project level. Accomplishment text viewable year-over-year
- **2.3** -- Source fidelity: display exactly what budget docs report, never adjust numbers. Toggle if both nominal and constant-year exist in source
- **2.4** -- Formatted table = styled Excel (.xlsx), with PDF and image export options

### Remaining High-Priority Open Items
1. **2.5** -- Fix the Amount Range filter to operate on the correct column context.
2. **5.1** -- Confirm WCAG 2.1 AA as the target accessibility standard.
3. **5.2** -- Audit and fix color contrast failures (particularly `#555` and `#888` on light/dark backgrounds).

### Open Questions Still Under Discussion
- **Section 2** -- Remaining items (2.5-2.11): amount filter behavior, related items logic, programs page, compare feature, advanced search, saved views
- **Section 3** -- Navigation & Information Architecture
- **Section 4** -- Visual Design & Style Preferences
- **Section 5** -- Accessibility
- **Section 6** -- Performance & Responsiveness
- **Section 7** -- Feature Gaps & Enhancements
- **Section 8** -- Technical Debt & Architecture

---

*Document generated from codebase analysis. Last updated: 2026-02-20.*
