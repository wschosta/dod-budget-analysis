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
- [ ] Amount range filter operates on the correct column context (fix current bug where it's hardcoded to FY2026)
- [ ] Row click expands detail panel showing budget justification text, related items

### 1.3 URL-Based State
- [ ] All search parameters, filters, sort order, and pagination encoded in URL query params
- [ ] Browser back/forward navigates through search history
- [ ] Copy URL = share exact view

### 1.4 Export
- [ ] CSV export of current filtered results (with source metadata)
- [ ] Styled Excel export (.xlsx) with headers, column widths, number formatting, totals row, and source attribution
- [ ] PDF export of formatted table
- [ ] Image export of formatted table (for presentations)
- [ ] All exports include data source attribution (exhibit type, fiscal year, budget submission)

### 1.5 Navigation (RESOLVED)
- [ ] Nav order: Home → Search/Results → Charts → Programs → About → API Docs
- [ ] Programs remains a top-level nav item (contingent on program data availability)

### 1.6 Visual Foundations
- [ ] Global amount formatting toggle ($K / $M / $B) -- all values on screen use the same unit simultaneously
- [ ] Colorblind-friendly default chart palette; user-selectable alternative palettes (deuteranopia, protanopia, tritanopia, high-contrast)
- [ ] Dark mode fully polished -- migrate all hardcoded inline colors to CSS custom properties

### 1.7 Data Display Decisions (RESOLVED)
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

### 3.3 Data Dictionary / Glossary
- [ ] In-app reference page explaining exhibit types, amount columns, appropriation codes, PE number formats
- [ ] Contextual help tooltips throughout the interface

---

## Phase 4: Polish & Enhancements (Post-MVP)

### 4.1 News/Context Layer
- [ ] Linked news articles explaining year-over-year changes in specific programs
- [ ] Requires data pipeline for news ingestion and PE-line matching

### 4.2 Accessibility Hardening
- [ ] WCAG 2.1 AA audit and remediation
- [ ] Color contrast fixes
- [ ] Full keyboard navigation for table rows
- [ ] Screen reader testing (NVDA, JAWS, VoiceOver)
- [ ] Reduced motion mode

### 4.3 Performance
- [ ] Lazy-load charts (IntersectionObserver)
- [ ] Self-host CDN dependencies for reliability
- [ ] Mobile-optimized filter drawer

### 4.4 Advanced Features
- [ ] Saved views / named reports (if URL-based sharing proves insufficient)
- [ ] Embed mode for iframes
- [ ] Bulk row selection and comparison
- [ ] Advanced search with field-specific operators

---

## Open Questions Blocking Roadmap Items

These questions (from GUI_DECISIONS_AND_QUESTIONS.md) need resolution before their associated roadmap items can be fully specified:

| Question | Blocks | Section | Status |
|----------|--------|---------|--------|
| ~~2.1 -- Must-have chart types for MVP?~~ | ~~Phase 1.5, Phase 2~~ | ~~Data & Display~~ | **RESOLVED** |
| ~~2.2 -- Data granularity (PE-level vs. project-level)?~~ | ~~Phase 1.2, Phase 1.5~~ | ~~Data & Display~~ | **RESOLVED** |
| ~~2.3 -- Inflation-adjusted dollars?~~ | ~~Phase 1.5, Phase 2.1~~ | ~~Data & Display~~ | **RESOLVED** |
| ~~2.4 -- "Formatted table" export definition?~~ | ~~Phase 1.4~~ | ~~Data & Display~~ | **RESOLVED** |
| ~~4.3 -- Dark mode polished?~~ | ~~Phase 4~~ | ~~Visual Design~~ | **RESOLVED** |
| ~~4.4 -- Colorblind-friendly palette?~~ | ~~Phase 1, Phase 2~~ | ~~Visual Design~~ | **RESOLVED** |
| ~~4.5 -- Amount formatting toggle ($K / $M / $B)?~~ | ~~Phase 1.2~~ | ~~Visual Design~~ | **RESOLVED** |
| 5.1 -- WCAG 2.1 AA target? | Phase 4.2 | Accessibility | OPEN |

---

*Last updated: 2026-02-20.*
