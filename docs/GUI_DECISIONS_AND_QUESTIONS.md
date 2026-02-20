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
| 2.5 | **Amount Range filter hardcoded to FY2026 column.** Should it dynamically filter on whichever FY column(s) the user has visible? | **High** | **RESOLVED** | Dynamic filtering based on visible columns. See decision below. |
| 2.6 | **Should users be able to filter by multiple amount columns simultaneously?** | **Low** | **RESOLVED -- Not needed** | No use case identified. Dropped from consideration. |
| 2.7 | **How should "related items" in the detail panel be determined?** | **Medium** | **RESOLVED** | Tag-based matching from context analysis. See decision below. |
| 2.8 | **Should the Programs page require PE enrichment data, or work with just `budget_lines`?** | **Medium** | **RESOLVED** | Requires PE enrichment data. See decision below. |
| 2.9 | **Should there be a "compare" feature on the Search page?** | **Medium** | **RESOLVED** | Display multiple PE lines simultaneously. See decision below. |
| 2.10 | **Is the autocomplete keyword search sufficient, or should there be advanced search with field-specific operators?** | **Medium** | **RESOLVED -- MVP** | Advanced search included in MVP (bounded scope). See decision below. |
| 2.11 | **Should there be saved views/dashboards with server-side persistence?** | **Low** | **RESOLVED -- Not MVP** | localStorage + URL sharing is sufficient for MVP. |

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

### 2.5 -- Dynamic Amount Range Filter (RESOLVED)

The Amount Range filter must **dynamically operate on whichever FY column(s) the user currently has visible/selected**, not a hardcoded FY2026 column. If the user is viewing FY2024 Actual data, the amount filter should apply to FY2024 Actual values. This requires refactoring `frontend.py` lines 207-222 to reference the active fiscal year context rather than hardcoding `amount_fy2026_request`.

### 2.6 -- Multi-Column Amount Filter (RESOLVED -- Not Needed)

No use case identified for filtering by multiple amount columns simultaneously (e.g., "FY24 > $10M AND FY26 > $15M"). **Dropped from consideration entirely** -- not even on a future backlog.

### 2.7 -- Related Items: Tag-Based Matching (RESOLVED)

Related items in the detail panel should be determined by **tags derived from context analysis** of the text associated with accomplishments, programs, and PE line descriptions. The current fallback approach (matching on `organization_name + line_item_title`) produces false positives (e.g., two different "Program Management" entries at the same organization). Tag-based matching provides semantic relevance rather than string-matching coincidence.

**Implementation:** Requires a tagging pipeline that analyzes accomplishment text, program descriptions, and PE line context to produce tags, then matches related items by shared tags.

### 2.8 -- Programs Page Requires PE Enrichment Data (RESOLVED)

The Programs page **requires PE enrichment data** and should not attempt to work with just `budget_lines`. The PE enrichment step should be called **after budget docs are compiled** as part of the standard data pipeline. The current behavior of silently showing an empty page when enrichment hasn't been run should be replaced with an informative message explaining the dependency.

### 2.9 -- Compare Feature: Multiple PE Lines Displayed Simultaneously (RESOLVED)

The ability to **display multiple PE lines simultaneously** is the natural comparison mechanism. Users can select and view multiple PE lines side-by-side in the results table. No additional dedicated "compare mode" UI is needed beyond this -- the multi-row display IS the comparison feature.

### 2.10 -- Advanced Search: MVP (Bounded Scope) (RESOLVED)

Advanced search with field-specific operators is included in the **MVP**, bounded to a reasonable first release. Initial operators:

- Field-specific search: `service:Army`, `exhibit:R-2`, `pe:0603285E`
- Amount operators: `amount>50000`, `amount<1000000`
- Boolean operators: `AND`, `OR` for combining field queries
- Free-text remains the default (no field prefix = FTS5 search)

**Deferred to later:** Nested boolean expressions, regex support, saved search templates, proximity operators.

### 2.11 -- Saved Views: localStorage + URL Sharing (RESOLVED -- Not MVP)

Server-side persistence for saved views is **not required for the MVP**. The combination of `localStorage` for personal bookmarks and URL query parameters for shareable views is sufficient. Server-side persistence can be revisited if user feedback indicates the need.

---

## 3. Navigation & Information Architecture

| # | Question / Decision | Priority | Status | Context |
|---|---------------------|----------|--------|---------|
| 3.1 | **Nav order: Home, Search/Results, Charts, Programs, About, API Docs** | **Medium** | **RESOLVED** | Confirmed. Home is the hybrid landing page. Search is the primary workflow entry point. |
| 3.2 | **Programs as a top-level nav item** | **Medium** | **RESOLVED** | Confirmed as top-level, contingent on identifying program information from the data. |
| 3.3 | **Should the API Docs link open in a new tab (current behavior) or be an in-app page?** | **Low** | **RESOLVED** | New tab (current behavior confirmed). |
| 3.4 | **Is the footer adequate?** Should it include version info, last data refresh date, or data coverage statistics? | **Low** | **RESOLVED** | Yes, add version, last refresh date, and data coverage stats. See decision below. |

### 3.1 -- Nav Order (RESOLVED)

**Confirmed:** Home (hybrid landing) → Search/Results → Charts → Programs → About → API Docs

### 3.2 -- Programs as Top-Level Nav (RESOLVED)

Programs stays as a **top-level nav item**, provided the app can identify and surface program information from the budget data. If program-level data is available, a dedicated page is warranted rather than burying it as a tab within Search.

### 3.3 -- API Docs Link: New Tab (RESOLVED)

**Confirmed:** API Docs opens in a new tab (`target="_blank"`). This is standard for developer documentation and keeps the main app context intact.

### 3.4 -- Footer Content: Version, Refresh Date, Coverage Stats (RESOLVED)

The footer should be enhanced to include:
- **Application version** (e.g., "v1.0.0")
- **Last data refresh date** (when the database was last rebuilt/updated)
- **Data coverage statistics** (e.g., "Covering FY2020-FY2026 | 12,345 budget line items | 6 services")

These provide transparency about what the user is looking at and when it was last updated.

---

## 4. Visual Design & Style Preferences

| # | Question / Decision | Priority | Status | Context |
|---|---------------------|----------|--------|---------|
| 4.1 | **Color palette: Should the current navy/blue/gray theme reference official DoD branding?** | **Medium** | **RESOLVED** | Project-specific WCAG 2.1 AA palette. See decision below. |
| 4.2 | **Typography: Should the app use a specific typeface instead of `system-ui`?** | **Medium** | **RESOLVED** | Hadrian.co-inspired typeface. See decision below. |
| 4.3 | **Dark mode: fully polished** | **Medium** | **RESOLVED** | See decision below. |
| 4.4 | **Chart colors: colorblind-friendly default with user-selectable palettes** | **Medium** | **RESOLVED** | See decision below. |
| 4.5 | **Amount formatting: global toggle ($K / $M / $B)** | **Medium** | **RESOLVED** | See decision below. |
| 4.6 | **Should there be data density options (compact / comfortable / spacious) for table rows?** | **Low** | **RESOLVED** | Yes, three options. Default: comfortable. See decision below. |
| 4.7 | **Print styles: Is the current print format the desired one?** | **Low** | **RESOLVED -- Post-MVP** | Yes, enhance with totals/page count/source URL. Deferred to post-MVP. |

### 4.3 -- Dark Mode: Fully Polished (RESOLVED)

Dark mode should be **fully polished**, not just a toggle that half-works. This means:
- Migrate all hardcoded inline colors (`#555`, `#888`, `#dbeafe`, `#ddd`, etc.) to CSS custom properties that adapt to dark mode
- Ensure all chart elements, borders, and backgrounds respond to the theme
- Test both modes thoroughly before shipping

### 4.4 -- Chart Color Palette: Colorblind-Friendly Default (RESOLVED)

- The **default palette** should be colorblind-friendly (avoid problematic red/green pairs)
- Users should be able to **choose their own color scheme** from a set of options (e.g., default, high-contrast, warm, cool)
- Different colorblind-friendly palettes (deuteranopia, protanopia, tritanopia) should be available as selectable options
- This is an accessibility feature, not just a cosmetic preference

### 4.5 -- Amount Formatting: Global Toggle (RESOLVED)

- A **global toggle** lets the user switch between $K, $M, and $B display
- **All numbers on the screen use the same unit at the same time** -- no mixing of $K, $M, and $B values side by side
- This prevents misreading: if everything shows $M, there's no risk of confusing 1K with 1M with 1B
- The toggle applies to tables, charts, exports, and any displayed amounts
- Default unit can be auto-selected based on the data range, but user override takes precedence

### 4.1 -- Project-Specific Color Palette: WCAG 2.1 AA (RESOLVED)

Create a **project-specific color palette** that meets WCAG 2.1 AA contrast requirements as the default for the site. The palette should:
- Be defined as **CSS custom properties** (variables) for easy site-wide updates
- Meet **4.5:1 contrast ratio** for all text/background combinations in both light and dark mode
- Replace the current generic navy/blue/gray values with intentionally designed, tested colors
- Be documented with their contrast ratios against expected backgrounds
- Variables should be named semantically (e.g., `--clr-primary`, `--clr-accent`) so they can be updated later without renaming references throughout the codebase

### 4.2 -- Typography: Hadrian.co-Inspired (RESOLVED)

Typography inspired by [hadrian.co](https://www.hadrian.co/) -- a clean, geometric, modern sans-serif aesthetic with generous letter-spacing for headings and excellent data readability for body text.

**Font stack (all available via Google Fonts):**
- **Headings:** `Space Grotesk` -- geometric, wide, technical feel. Uppercase with letter-spacing for major headings (matching the Hadrian hero style)
- **Body text:** `Inter` -- excellent readability at small sizes, clean proportions for data-heavy tables
- **Monospace (PE numbers, amounts, code):** `Space Mono` -- pairs with Space Grotesk, technical character

**CSS variables:**
```css
--font-heading: 'Space Grotesk', system-ui, sans-serif;
--font-body: 'Inter', system-ui, sans-serif;
--font-mono: 'Space Mono', 'Courier New', monospace;
```

**Loading strategy:** Google Fonts via `<link>` with `font-display: swap` for progressive loading. Consistent with the CDN approach (decision 6.5).

### 4.6 -- Data Density Options (RESOLVED)

Three density options for table rows, controlled by a toggle in the UI:
- **Compact** -- minimal padding, smaller font size. For analysts scanning many rows.
- **Comfortable** (default) -- balanced padding and readability
- **Spacious** -- generous padding, larger touch targets. For casual browsing.

Implemented via a CSS class on the table container (`density-compact`, `density-comfortable`, `density-spacious`) with the preference stored in `localStorage`.

### 4.7 -- Print Styles: Enhanced (RESOLVED -- Post-MVP)

Print output should include:
- Summary totals for visible columns
- Page count (e.g., "Page 1 of 3")
- Source URL in the footer (so printed pages can be traced back to the app)
- Data source attribution and date of export

**Deferred to post-MVP** -- current print styles are functional. Enhancement is not blocking.

---

## 5. Accessibility

| # | Question / Decision | Priority | Status | Context |
|---|---------------------|----------|--------|---------|
| 5.1 | **WCAG 2.1 AA is the target compliance level** | **High** | **RESOLVED** | MVP requirement. See decision below. |
| 5.2 | **Color contrast must meet 4.5:1 ratio** | **High** | **RESOLVED** | MVP requirement. See decision below. |
| 5.3 | **Screen reader experience: Is the HTMX partial swap approach providing adequate announcements?** | **Medium** | **RESOLVED -- Post-MVP** | Deferred. Ideally write compliance tests to assess/score/correct throughout build. Formal screen reader testing not required for MVP. |
| 5.4 | **Should there be a "reduce motion" mode that suppresses skeleton loading animations and chart transitions?** | **Low** | **RESOLVED** | Yes, respect `prefers-reduced-motion`. See decision below. |
| 5.5 | **Table rows are clickable but lack explicit `role="button"` or `tabindex="0"`.** Should table row selection be fully keyboard-accessible via arrow keys? | **Medium** | **RESOLVED -- MVP** | Arrow keys + Enter. See decision below. |

### 5.1 -- WCAG 2.1 AA: MVP Requirement (RESOLVED)

**WCAG 2.1 AA is the target compliance level for the MVP.** This is not deferred -- it ships with the first release. The codebase already has many AA foundations in place (skip-link, aria-live regions, keyboard shortcuts, focus-visible outlines, sr-only text). Remaining work is to formally audit and close the gaps.

### 5.2 -- Color Contrast Fixes: MVP Requirement (RESOLVED)

All text/background combinations must meet the **4.5:1 contrast ratio** required by WCAG 2.1 AA. Known failures to fix:
- `color:#888` on white (3.5:1) -- **fails AA**, must be darkened
- `color:#555` on white (4.6:1) -- barely passes for normal text but **fails at smaller font sizes** (`.78rem`, `.75rem`)
- All hardcoded colors must also be verified against dark mode backgrounds
- This work is a prerequisite for the dark mode polish (decision 4.3)

### 5.3 -- Screen Reader Testing (RESOLVED -- Post-MVP)

Formal screen reader testing (NVDA, JAWS, VoiceOver) for HTMX partial swap announcements is **deferred to post-MVP**. However, the ideal approach is to:
- Write **automated accessibility compliance tests** that can assess and score the application throughout the build process
- Use these tests to catch regressions and guide corrections incrementally
- Formal manual screen reader testing is not required for MVP, but automated checks provide a safety net

### 5.4 -- Reduce Motion Mode (RESOLVED)

The application should respect the **`prefers-reduced-motion: reduce`** media query. When the user's OS-level setting requests reduced motion, the app should:
- Suppress skeleton loading animations
- Disable chart transitions and animated data updates
- Remove any CSS transitions/animations that aren't essential to understanding the interface
- This is a CSS-only implementation using `@media (prefers-reduced-motion: reduce)` to override animation properties

**Context:** `prefers-reduced-motion` is an OS-level accessibility setting (macOS: System Preferences → Accessibility → Display → Reduce motion; Windows: Settings → Ease of Access → Display → Show animations). When enabled, the browser reports `prefers-reduced-motion: reduce`, allowing CSS to respond.

### 5.5 -- Keyboard Navigation for Table Rows: MVP (RESOLVED)

Table rows must be fully keyboard-accessible in the MVP:
- **Arrow keys (Up/Down):** Move selection between rows
- **Enter:** Expand the detail panel for the selected row
- **Tab:** Moves focus to the next interactive element (standard browser behavior)
- Implementation: Add `tabindex="0"` to table rows, appropriate ARIA roles, and JavaScript key event handlers for arrow key navigation
- Visual focus indicator must be visible (already covered by existing `focus-visible` styles)

---

## 6. Performance & Responsiveness

| # | Question / Decision | Priority | Status | Context |
|---|---------------------|----------|--------|---------|
| 6.1 | **Filter sidebar becomes a collapsible drawer on small screens** | **Medium** | **RESOLVED** | See decision below. |
| 6.2 | **Tablet experience: There is no breakpoint between 480px and 768px.** Should one be added? | **Low** | **RESOLVED** | Yes, add ~600px tablet breakpoint. |
| 6.3 | **Should charts be lazy-loaded (only render when scrolled into view)?** | **Low** | **RESOLVED** | Yes, use IntersectionObserver. No strong preference on timing. |
| 6.4 | **Should search results support infinite scroll instead of pagination?** | **Low** | **RESOLVED** | Pagination with configurable page size. See decision below. |
| 6.5 | **CDN dependencies: Keep external for now, revisit post-release** | **Medium** | **RESOLVED** | See decision below. |

### 6.1 -- Collapsible Filter Drawer on Small Screens (RESOLVED)

The filter sidebar should become a **collapsible drawer** (slide-in or accordion) on small screens instead of stacking above results. This:
- Prevents users from scrolling past all filters before seeing any data
- Establishes a familiar UX pattern for an eventual mobile rollout
- **Note: Full mobile-optimized layout is NOT part of MVP scope.** The collapsible drawer is a responsive improvement for the desktop app on narrow viewports.

### 6.2 -- Tablet Breakpoint at ~600px (RESOLVED)

Add a **tablet breakpoint at ~600px** between the existing 480px (mobile) and 768px (desktop) breakpoints. This ensures tablets in portrait mode get a layout optimized for their viewport rather than falling into the mobile layout.

### 6.3 -- Lazy-Load Charts (RESOLVED)

Charts should be **lazy-loaded using IntersectionObserver** -- only rendered when scrolled into view. This prevents the charts page from loading all charts simultaneously, improving initial page load performance. Standard IntersectionObserver pattern with a reasonable root margin (e.g., `200px`) to start loading slightly before the chart enters the viewport.

### 6.4 -- Pagination with Configurable Page Size (RESOLVED)

**Pagination** (not infinite scroll) with user-configurable page size:
- **Default:** 25 results per page
- **Options:** 25, 50, 100, 200
- Page size preference stored in `localStorage`
- Current page encoded in URL query parameters (supports shareability -- decision 1.5)

Infinite scroll was rejected because:
- The dataset is large enough that unbounded scroll would be problematic
- Pagination preserves URL-based state and "share this view" workflows
- Standard preset page sizes keep the implementation simple

### 6.5 -- CDN Dependencies: Keep for Now (RESOLVED)

External CDN loading of HTMX, Chart.js, and treemap plugin is **acceptable for initial release**. Self-hosting should be revisited post-release as a reliability improvement. Current approach is pragmatic for MVP velocity.

---

## 7. Feature Gaps & Enhancements to Consider

| # | Feature Idea | Priority | Status | Notes |
|---|--------------|----------|--------|-------|
| 7.1 | **Toast notifications** for user actions (download started, feedback submitted, URL copied, search saved). | **Medium** | **RESOLVED -- MVP** | See decision below. |
| 7.2 | **Keyboard navigation through table rows** using arrow keys (Up/Down to move selection, Enter to expand detail). | **Medium** | **RESOLVED -- MVP** | Covered by accessibility decision 5.5. Arrow keys + Enter confirmed. |
| 7.3 | **Bulk actions**: Select multiple rows via checkboxes, then export selected or compare selected. | **Low** | **RESOLVED** | Multi-PE-line display covers comparison (2.9). Bulk export covered by filtered CSV/Excel export (2.4). No separate "bulk actions" UI needed. |
| 7.4 | **Data dictionary / glossary page** explaining exhibit types, amount columns, appropriation codes, and PE number formats. | **Medium** | **RESOLVED -- MVP** | See decision below. |
| 7.5 | **URL shortener or permalink service** for shared filtered views. | **Low** | **OPEN** | Post-release consideration. |
| 7.6 | **Embed mode** for iframes. | **Low** | **OPEN** | Post-release consideration. |
| 7.7 | **"Back to top" button** for long result sets. | **Low** | **OPEN** | Post-release consideration. |

### 7.1 -- Toast Notifications: MVP (RESOLVED)

Toast notifications should be included in the MVP. Users currently receive no visible feedback for:
- URL copied to clipboard (Share button)
- Download started / completed
- Feedback submitted
- Search saved

A lightweight toast component (non-blocking, auto-dismiss) should provide confirmation for all user-initiated actions.

### 7.4 -- Data Dictionary / Glossary Page: MVP (RESOLVED)

A data dictionary / glossary page should be included in the MVP. This supports the **source transparency** design principle. The existing `docs/data_dictionary.md` can serve as the content source. The page should:
- Explain exhibit types, amount columns, appropriation codes, and PE number formats
- Be linked from the main navigation (under About or as a sub-page)
- Complement the existing tooltip-based contextual help

---

## 8. Technical Debt & Architecture Questions

| # | Question / Decision | Priority | Status | Context |
|---|---------------------|----------|--------|---------|
| 8.1 | **Migrate from `unsafe-inline` CSP to nonce-based CSP** | **Medium** | **RESOLVED -- MVP** | See decision below. |
| 8.2 | **Extract inline chart JS (620+ lines) to separate file** | **Medium** | **RESOLVED -- MVP** | See decision below. Prerequisite for 8.1. |
| 8.3 | **Rate limiting defaults: Are 60 search/min and 10 download/min appropriate?** | **Low** | **OPEN** | 60/min could be restrictive for rapid HTMX filter toggling. |
| 8.4 | **Caching strategy: 5-minute TTL configurable at runtime?** | **Low** | **OPEN** | Currently hardcoded in `frontend.py`. |
| 8.5 | **Replace silent error catching with user-visible error feedback** | **Medium** | **RESOLVED -- MVP** | See decision below. |
| 8.6 | **Inline styles migration to CSS classes** | **Low** | **OPEN** | Partially addressed by dark mode polish (4.3) which requires moving hardcoded colors to CSS vars. |
| 8.7 | **Dashboard SSR vs. client-side rendering** | **Low** | **OPEN** | Inconsistency with Search page approach. |

### 8.1/8.2 -- Extract Inline JS and Migrate to Nonce-Based CSP: MVP (RESOLVED)

The 620+ lines of inline JavaScript in `charts.html` should be **extracted to a separate `.js` file** for the MVP. This:
- Enables browser caching of the JS separately from the HTML
- Makes the JavaScript testable in isolation
- **Removes the need for `'unsafe-inline'` in the CSP**, allowing migration to nonce-based CSP
- Improves the overall security posture of the application

The dark mode initialization script in `base.html` should also be extracted. Once all inline scripts are externalized, the CSP can be tightened to use nonces instead of `'unsafe-inline'`.

### 8.5 -- Error Handling: User-Visible Feedback: MVP (RESOLVED)

Silent error catching (empty `catch(e) {}` blocks, silently returning empty results) should be **replaced with user-visible error feedback** for the MVP. This includes:
- Replacing empty catch blocks in chart loading with error messages shown in the chart container
- Showing meaningful error states on the Programs page when exceptions occur (instead of silently returning empty)
- Integrating with the toast notification system (7.1) for transient errors
- Showing inline error states (e.g., "Failed to load chart -- try refreshing") for persistent failures

---

## Summary

### Resolved Decisions (All Sections)

**Section 1 -- Use Cases & Workflows:**
- **1.1** -- Three user personas defined: Analyst (expert), Industry/Journalist (moderate), General Public (low knowledge)
- **1.2** -- Three use case tiers ranked: (1) Targeted reporting, (2) Trend analysis ("across" and "down"), (3) Browsing/discovery
- **1.3** -- Query model is search-then-filter (not pivot table)
- **1.4** -- Hybrid landing page: search bar over clickable summary visuals
- **1.5** -- URL-based state for shareable/bookmarkable views
- **1.6** -- News/context layer deferred to post-MVP

**Section 2 -- Data & Functionality:**
- **2.1** -- MVP charts: bar, stacked bar, tables, Spruill. Sankey/river deferred to Phase 3
- **2.2** -- Project-level detail with tagging at project level. Accomplishment text viewable year-over-year
- **2.3** -- Source fidelity: display exactly what budget docs report, never adjust numbers. Toggle if both nominal and constant-year exist in source
- **2.4** -- Formatted table = styled Excel (.xlsx), with PDF and image export options
- **2.5** -- Amount range filter dynamically operates on visible FY columns (not hardcoded to FY2026)
- **2.6** -- Multi-column amount filter: not needed, dropped entirely
- **2.7** -- Related items determined by tag-based matching from context analysis of accomplishments/programs/PE text
- **2.8** -- Programs page requires PE enrichment data; enrichment runs after budget doc compilation
- **2.9** -- Compare = displaying multiple PE lines simultaneously (no separate compare mode needed)
- **2.10** -- Advanced search with field-specific operators included in MVP (bounded scope: field prefixes, amount operators, AND/OR)
- **2.11** -- Saved views: localStorage + URL sharing sufficient for MVP; no server-side persistence needed

**Section 3 -- Navigation:**
- **3.1** -- Nav order: Home → Search/Results → Charts → Programs → About → API Docs
- **3.2** -- Programs is a top-level nav item (contingent on program data availability)
- **3.3** -- API Docs opens in new tab (current behavior confirmed)
- **3.4** -- Footer enhanced with version, last data refresh date, and data coverage stats

**Section 4 -- Visual Design:**
- **4.1** -- Project-specific WCAG 2.1 AA color palette stored as CSS custom properties
- **4.2** -- Typography: Space Grotesk (headings) + Inter (body) + Space Mono (monospace) -- inspired by hadrian.co
- **4.3** -- Dark mode fully polished (migrate hardcoded colors to CSS custom properties)
- **4.4** -- Colorblind-friendly default palette; user-selectable alternative palettes
- **4.5** -- Global amount toggle ($K / $M / $B) -- all values on screen use the same unit simultaneously
- **4.6** -- Data density options: compact / comfortable (default) / spacious
- **4.7** -- Print styles: enhance with totals, page count, source URL (post-MVP)

**Section 5 -- Accessibility:**
- **5.1** -- WCAG 2.1 AA is the target -- MVP requirement, not deferred
- **5.2** -- Color contrast fixes are MVP requirement (4.5:1 ratio for all text/background combinations)
- **5.3** -- Screen reader testing: post-MVP (write automated compliance tests for ongoing assessment)
- **5.4** -- Reduce motion: respect `prefers-reduced-motion` media query
- **5.5** -- Keyboard navigation for table rows: arrow keys + Enter (MVP)

**Section 6 -- Performance & Responsiveness:**
- **6.1** -- Collapsible filter drawer on small screens (full mobile rollout is NOT MVP)
- **6.2** -- Add tablet breakpoint at ~600px
- **6.3** -- Lazy-load charts via IntersectionObserver
- **6.4** -- Pagination with configurable page size: 25 (default), 50, 100, 200
- **6.5** -- CDN dependencies acceptable for initial release; revisit self-hosting post-release

**Section 7 -- Feature Gaps:**
- **7.1** -- Toast notifications for user actions -- MVP
- **7.2** -- Keyboard navigation -- MVP (covered by 5.5)
- **7.3** -- Bulk actions: covered by multi-PE-line display (2.9) and filtered export (2.4)
- **7.4** -- Data dictionary / glossary page -- MVP (surface existing `docs/data_dictionary.md`)

**Section 8 -- Technical Debt:**
- **8.1/8.2** -- Extract inline JS to separate files, migrate to nonce-based CSP -- MVP
- **8.5** -- Replace silent error catching with user-visible error feedback -- MVP

### Remaining Open Items (Lower Priority, Not Blocking MVP)
- **Section 7** -- (7.5-7.7): permalink service, embed mode, back-to-top button
- **Section 8** -- (8.3-8.4, 8.6-8.7): rate limiting defaults, caching TTL, inline styles migration, dashboard SSR consistency

---

*Document generated from codebase analysis. Last updated: 2026-02-20.*
