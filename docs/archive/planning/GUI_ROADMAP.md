# DoD Budget Explorer: GUI Roadmap

This document tracks the phased implementation plan for the DoD Budget Explorer GUI rebuild. It is informed by the resolved decisions in [GUI_DECISIONS_AND_QUESTIONS.md](./GUI_DECISIONS_AND_QUESTIONS.md).

---

## Design Principles (derived from stakeholder Q&A)

1. **Search-then-filter paradigm** -- Users start from a PE line, tag, or free-text search. Results show all available fiscal years. Users filter down from there.
2. **Progressive disclosure** -- Simple by default, powerful on demand. Serve both analyst precision workflows and public exploration workflows.
3. **Clickable visuals** -- Every summary chart element acts as an implicit search. Clicking drills into the underlying data.
4. **Reproducible views** -- URL query parameters encode the full view state. Any view can be bookmarked, shared, or recreated.
5. **Source transparency** -- Users must always be able to see where data came from (exhibit type, fiscal year, budget submission).
6. **Source fidelity** -- Never display budget data that does not come from a source document. The only exception is summations (totals computed from source data). Never adjust, inflate, or deflate numbers.

---

## Phase 1: MVP (Core Search & Report Workflow)

The minimum viable product focuses on **Use Case 1 (Targeted Reporting)** and the **Analyst** persona, since these drive the most specific requirements. Industry/journalist and public personas benefit from the same core infrastructure.

### 1.1 Hybrid Landing Page
- [ ] Prominent search bar (PE line, tag, or free-text)
- [ ] Summary visuals below search bar (top-level budget breakdowns by service, appropriation type)
- [ ] All summary visuals are clickable -- clicking navigates to search results for that item
- [ ] URL state synced on page load

### 1.2 Search & Results
- [ ] Search by PE line number, tag, or free-text across budget documentation
- [ ] Results table showing all available fiscal years for matching items
- [ ] Sortable, filterable columns
- [ ] Filter sidebar: service, appropriation type, exhibit type, fiscal year, amount range
- [ ] Amount range filter dynamically operates on whichever FY column(s) the user has visible (not hardcoded to any single FY)
- [ ] Row click expands detail panel showing budget justification text, related items
- [ ] Related items determined by tag-based matching (context analysis of accomplishments, programs, PE text)
- [ ] Display multiple PE lines simultaneously for natural comparison
- [ ] Pagination: 25 results/page (default), with options for 50, 100, 200. Page size stored in localStorage.

### 1.3 Advanced Search (bounded MVP scope)
- [ ] Field-specific search: `service:Army`, `exhibit:R-2`, `pe:0603285E`
- [ ] Amount operators: `amount>50000`, `amount<1000000`
- [ ] Boolean operators: `AND`, `OR` for combining field queries
- [ ] Free-text remains the default (no field prefix = FTS5 search)
- **Deferred:** Nested boolean expressions, regex support, saved search templates, proximity operators

### 1.4 URL-Based State
- [ ] All search parameters, filters, sort order, page number, and page size encoded in URL query params
- [ ] Browser back/forward navigates through search history
- [ ] Copy URL = share exact view
- [ ] Saved views use localStorage + URL sharing (no server-side persistence needed for MVP)

### 1.5 Export
- [ ] CSV export of current filtered results (with source metadata)
- [ ] Styled Excel export (.xlsx) with headers, column widths, number formatting, totals row, and source attribution
- [ ] PDF export of formatted table
- [ ] Image export of formatted table (for presentations)
- [ ] All exports include data source attribution (exhibit type, fiscal year, budget submission)

### 1.6 Navigation
- [ ] Nav order: Home → Search/Results → Charts → Programs → About → API Docs
- [ ] Programs remains a top-level nav item (contingent on program data availability)
- [ ] API Docs opens in new tab (`target="_blank"`)
- [ ] Footer: version info, last data refresh date, data coverage statistics (e.g., "Covering FY2020-FY2026 | 12,345 budget line items | 6 services")

### 1.7 Visual Foundations
- [ ] **Color palette:** Project-specific WCAG 2.1 AA palette defined as CSS custom properties with documented contrast ratios
- [ ] **Typography:** Space Grotesk (headings), Inter (body), Space Mono (monospace) via Google Fonts with `font-display: swap`
- [ ] Global amount formatting toggle ($K / $M / $B) -- all values on screen use the same unit simultaneously
- [ ] Colorblind-friendly default chart palette; user-selectable alternative palettes (deuteranopia, protanopia, tritanopia, high-contrast)
- [ ] Dark mode fully polished -- migrate all hardcoded inline colors to CSS custom properties
- [ ] Data density options: compact / comfortable (default) / spacious -- stored in localStorage

### 1.8 Accessibility (MVP Requirement)
- [ ] WCAG 2.1 AA compliance audit and remediation
- [ ] Fix all color contrast failures (4.5:1 ratio minimum for all text/background combinations)
- [ ] Darken `#888` text (currently 3.5:1 -- fails AA)
- [ ] Verify `#555` text at small font sizes (`.78rem`, `.75rem`)
- [ ] Verify all colors against dark mode backgrounds
- [ ] Full keyboard navigation for table rows (`tabindex`, arrow keys Up/Down to move, Enter to expand detail)
- [ ] Respect `prefers-reduced-motion: reduce` (suppress skeleton animations, chart transitions)

### 1.9 Responsive Layout
- [ ] Collapsible filter drawer on small screens (replaces stacking above results)
- [ ] Add tablet breakpoint at ~600px (between existing 480px mobile and 768px desktop)
- [ ] Note: Full mobile-optimized layout is NOT MVP scope

### 1.10 UX Polish
- [ ] Toast notifications for user actions (URL copied, download started, feedback submitted, search saved)
- [ ] Data dictionary / glossary page (surface existing `docs/data_dictionary.md` in the UI)

### 1.11 Programs Page
- [ ] Requires PE enrichment data (not just `budget_lines`)
- [ ] PE enrichment step called after budget docs are compiled in the data pipeline
- [ ] Show informative message when enrichment data is unavailable (replace silent empty page)

### 1.12 Technical Foundations
- [ ] Extract inline chart JS (620+ lines in `charts.html`) to separate `.js` file
- [ ] Extract dark mode initialization script from `base.html` to external file
- [ ] Migrate CSP from `'unsafe-inline'` to nonce-based
- [ ] Replace silent error catching with user-visible error states (inline messages + toast notifications)
- [ ] Lazy-load charts via IntersectionObserver (render when scrolled into view)

### 1.13 Data Display Decisions (RESOLVED)
- **Chart types (MVP):** Bar charts, stacked bar/area charts, sortable tables, Spruill charts
- **Chart types (deferred):** Sankey/river charts → Phase 3
- **Data granularity:** Project-level detail (not just PE-level). Tags applied at project level where available. Accomplishment text viewable year-over-year.
- **Dollar representation:** Display exactly what source documents report. If both nominal and constant-year figures exist, show both with a toggle. Never adjust numbers. Only exception: computed summations.
- **Display hierarchy:** PE Line → Project(s) → Accomplishment text (by fiscal year)

---

## Phase 2: Trend Analysis & Visualization

Focuses on **Use Case 2 (Trend Analysis)** and serving the **Industry/Journalist** persona.

### 2.1 "Across" Analysis (one PE line over time)
- [ ] Line/bar chart showing funding history for a selected PE line across all available fiscal years
- [ ] Ability to overlay multiple PE lines on the same chart for comparison
- [ ] If source documents provide both nominal and constant-year figures, toggle between views

### 2.2 "Down" Analysis (multiple PE lines in one fiscal year)
- [ ] Stacked bar or grouped bar chart comparing selected PE lines within a fiscal year
- [ ] Sortable by amount, service, or appropriation type

### 2.3 Spruill Charts
- [ ] Classic Spruill chart output for analyst workflows
- [ ] Configurable axes and groupings

### 2.4 Budget Document Viewer
- [ ] Ability to view underlying budget justification documents (R-2 exhibits, etc.)
- [ ] Linked from detail panel and chart tooltips
- [ ] Provides the "nuance" layer analysts and journalists need

---

## Phase 3: Browsing & Discovery

Focuses on **Use Case 3 (Browsing)** and the **General Public** persona.

### 3.1 River / Sankey Charts
- [ ] Visual showing how budget pieces build up to total defense budget
- [ ] Interactive -- clicking a segment drills into that portion
- [ ] Multiple levels of granularity (total → service → appropriation → PE line)

### 3.2 Program Background Pages
- [ ] Enriched program pages with descriptions, history, and context
- [ ] Linked from search results and charts

### 3.3 Data Dictionary / Glossary (expanded)
- [ ] In-app reference page explaining exhibit types, amount columns, appropriation codes, PE number formats
- [ ] Contextual help tooltips throughout the interface

---

## Phase 4: Polish & Enhancements (Post-MVP)

### 4.1 News/Context Layer
- [ ] Linked news articles explaining year-over-year changes in specific programs
- [ ] Requires data pipeline for news ingestion and PE-line matching

### 4.2 Accessibility Hardening (continued from Phase 1)
- [ ] Screen reader testing (NVDA, JAWS, VoiceOver) -- verify HTMX partial swaps announce correctly
- [ ] Automated accessibility compliance test suite for ongoing assessment

### 4.3 Performance & Infrastructure
- [ ] Self-host CDN dependencies for reliability (revisit post-initial release)
- [ ] Full mobile-optimized layout (beyond the Phase 1 collapsible drawer)

### 4.4 Print & Export Enhancements
- [ ] Print styles: summary totals, page count, source URL footer
- [ ] Enhanced print layout optimized for data tables

### 4.5 Advanced Features (if needed)
- [ ] Saved views / named reports with server-side persistence (if localStorage + URL proves insufficient)
- [ ] Embed mode for iframes
- [ ] Advanced search extensions: nested boolean, regex, saved search templates, proximity operators
- [ ] URL shortener / permalink service for shared views

---

## Open Questions (Not Blocking Any Phase)

These items are low-priority and do not block any roadmap phase:

| Question | Section | Notes |
|----------|---------|-------|
| 7.5 -- URL shortener / permalink service | Feature Gaps | Post-release consideration |
| 7.6 -- Embed mode for iframes | Feature Gaps | Post-release consideration |
| 7.7 -- "Back to top" button | Feature Gaps | Post-release consideration |
| 8.3 -- Rate limiting defaults (60 search/min, 10 download/min) | Tech Debt | May need adjustment for rapid HTMX filter toggling |
| 8.4 -- Caching strategy (5-min TTL configurable at runtime?) | Tech Debt | Currently hardcoded |
| 8.6 -- Inline styles migration to CSS classes | Tech Debt | Partially addressed by dark mode polish (4.3) |
| 8.7 -- Dashboard SSR vs. client-side rendering consistency | Tech Debt | Low priority |

---

*Last updated: 2026-02-20.*
