# Tool Suitability Assessment & GUI Development Questions

**Date:** 2026-02-24
**Assessor:** Claude (autonomous review)
**Scope:** Full codebase review — documentation, reference materials, GUI implementations, API surface, data model, and roadmap
**Purpose:** Evaluate whether the tool as built provides the necessary information to end users, and develop clarifying questions to guide continued GUI development

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Assessment Methodology](#2-assessment-methodology)
3. [What the Tool Does Well](#3-what-the-tool-does-well)
4. [Gap Analysis](#4-gap-analysis)
5. [Reference Document Currency](#5-reference-document-currency)
6. [Clarification Questions for GUI Development](#6-clarification-questions-for-gui-development)
7. [Prioritized Recommendations](#7-prioritized-recommendations)

---

## 1. Executive Summary

The DoD Budget Analysis tool has matured rapidly through February 2026, completing Phases 0-3 of its roadmap and reaching approximately 50% completion on Phase 4 (deployment). The tool provides a **comprehensive, well-architected system** for ingesting, searching, and exploring DoD budget data. The web frontend, API layer, and data pipeline are all functional and well-tested (1,183+ tests, 80%+ coverage).

However, several questions remain about whether the current GUI optimally serves its intended users. The tool excels at **search-then-filter workflows** (Use Case 1 from GUI_DECISIONS) but has less-developed support for **trend analysis** (Use Case 2) and **browsing/discovery** (Use Case 3). The gap between the tool's data capabilities (rich API with 47+ endpoints, PE enrichment, PDF narrative extraction) and what the GUI surfaces to end users represents the primary opportunity for continued development.

The assessment identifies **27 clarification questions** across 7 categories that, once answered, will provide clear direction for the next phase of GUI development.

---

## 2. Assessment Methodology

This assessment was conducted by reviewing:

- **20+ documentation files** in `docs/user-guide/`, `docs/developer/`, and `docs/decisions/`
- **27+ archived planning documents** in `docs/archive/planning/`
- **All GUI code**: 2 tkinter desktop GUIs, 12 Jinja2 templates, 8 HTMX partials, 7 JavaScript modules, 1,792 lines of CSS
- **All API routes**: 47+ endpoints across 10 route modules with 11 Pydantic models
- **Reference materials**: exhibit catalog (11 types), data sources (6), column specifications, validation suite
- **Recent git history**: ~50 commits in February 2026 tracking the most recent development trajectory
- **Instruction files**: LION (10 tasks), TIGER (11 tasks), BEAR (12 tasks), OH MY (12 tasks)

---

## 3. What the Tool Does Well

### 3.1 Data Ingestion & Coverage
- **6 data sources** covering all major DoD components (Comptroller, Defense-Wide, Army, Navy, Air Force)
- **11 exhibit types** cataloged (7 summary exhibits verified against FY2026 real data)
- **FY2017-2026 fiscal year range** with dynamic column support for future years
- **Playwright browser automation** for WAF-protected government sites
- **File integrity verification** with magic-byte checks and manifest tracking

### 3.2 Search & Filtering
- **FTS5 full-text search** with BM25 relevance ranking across budget lines and PDF pages
- **Multi-dimensional filtering**: fiscal year, service, exhibit type, appropriation, amount range
- **Boolean operators**: quotes for exact phrases, minus for exclusion
- **Advanced search builder**: field-specific conditions with add/remove rows
- **URL-based state**: all filters encoded in query string, shareable and bookmarkable

### 3.3 API Design
- **47+ REST endpoints** with comprehensive OpenAPI documentation
- **PE-centric endpoints**: funding history, YoY changes, sub-elements, descriptions, related PEs, comparison, top changes
- **Streaming export**: CSV, NDJSON, Excel with source attribution metadata
- **Rate limiting**, ETag caching, CORS, CSP headers
- **Dashboard summary** endpoint with service/appropriation/program breakdowns

### 3.4 Data Enrichment
- **PE index** with display titles, organizations, budget types
- **Tag system** with confidence levels (1.0 structured → 0.7 LLM-generated) and source provenance
- **PE lineage**: cross-PE relationships with confidence scores and mention counts
- **Project-level decomposition** from R-2 exhibits
- **PDF narrative extraction** with section-level parsing (Accomplishments, Plans, etc.)

### 3.5 Frontend Quality
- **Responsive design** with mobile breakpoints at 768px and 600px
- **Dark mode** with CSS variables, localStorage persistence, and system preference detection
- **Accessibility**: WCAG 2.1 AA color contrast, keyboard navigation (arrow keys, Enter, Escape), skip-to-content, ARIA live regions, focus-visible outlines
- **Print styles** with filter context header
- **Progressive enhancement** via HTMX (no full-page reloads)

### 3.6 Documentation
- **20+ active documentation files** covering users, developers, and operators
- **Architecture Decision Records** for key technology choices
- **Detailed roadmap** with 57 tasks and reference IDs
- **Comprehensive CLAUDE.md** for AI assistant onboarding

---

## 4. Gap Analysis

### 4.1 Data Gaps

| Gap | Impact | Status | Reference |
|-----|--------|--------|-----------|
| **P-5, R-2, R-3, R-4 detail exhibits unverified** against real corpus | HIGH — R-2 is the primary RDT&E exhibit; P-5 is primary procurement detail | Spec-based only | OH-MY-006 notes |
| **Currency year distinction** (then-year vs. constant dollars) not implemented | MEDIUM — affects multi-year trend accuracy | Partially addressed (unit detection added in 1.B3) | 1.B3 |
| **Missing agency sources** (MDA, NGB, DLA standalone) | LOW-MEDIUM — creates gaps for certain PE lookups | Evaluated but not added | data-sources.md |
| **Amount range filter hardcoded to FY2026 request** | MEDIUM — should match visible/active FY column | Known bug | GUI_MVP_IMPROVEMENT_PLAN 1.2 |

### 4.2 GUI Workflow Gaps

| Gap | Impact | Use Case Affected |
|-----|--------|-------------------|
| **No trend analysis view** (one PE over multiple years) | HIGH | UC2: "Across" analysis |
| **No comparison view** (multiple PEs in one FY, side-by-side) | HIGH | UC2: "Down" analysis |
| **No Spruill chart** capability | MEDIUM | UC2: Trend analysis |
| **No budget document viewer** (view source PDF pages inline) | MEDIUM | UC1 & UC3: Provenance verification |
| **No waterfall/Sankey charts** for budget flow visualization | MEDIUM | UC3: Browsing/discovery |
| **Chart drill-through limited** (only service bar chart links to search) | MEDIUM | UC3: Browsing/discovery |
| **No PE family/hierarchy visualization** | LOW-MEDIUM | UC3: Discovery |
| **No data freshness indicator** visible in the GUI | LOW | All use cases |

### 4.3 GUI Usability Gaps

| Gap | Impact | Notes |
|-----|--------|-------|
| **Saved searches are localStorage-only** | MEDIUM | Lost on device change or browser clear |
| **No search history or suggestions** | LOW-MEDIUM | Analyst workflow friction |
| **Programs page has no sorting** (by funding, by org) | LOW-MEDIUM | Discovery friction |
| **No multi-PE comparison** in Programs section | MEDIUM | Analyst need |
| **No "biggest movers" dashboard** (largest YoY changes) | MEDIUM | API exists (`/pe/top-changes`) but not surfaced |
| **No data confidence indicators per field** | LOW | Quality-conscious users |
| **No bulk export from Programs** (e.g., "all PEs tagged 'hypersonics'") | MEDIUM | Analyst workflow |
| **Dashboard lacks drill-down** from cards to details | LOW-MEDIUM | Navigation friction |

### 4.4 API vs. GUI Parity

The API offers several capabilities not yet surfaced in the GUI:

| API Capability | Endpoint | GUI Status |
|---------------|----------|------------|
| PE comparison (side-by-side) | `GET /api/v1/pe/compare` | **Not surfaced** |
| Top funding changes | `GET /api/v1/pe/top-changes` | **Not surfaced** |
| PE funding changes by line item | `GET /api/v1/pe/{pe}/changes` | **Not surfaced** |
| PE sub-elements | `GET /api/v1/pe/{pe}/subelements` | **Not surfaced** |
| PDF pages for a PE | `GET /api/v1/pe/{pe}/pdf-pages` | **Not surfaced** |
| PE export (Spruill table CSV) | `GET /api/v1/pe/{pe}/export/table` | **Not surfaced** |
| PE pages export (ZIP) | `GET /api/v1/pe/export/pages` | **Not surfaced** |
| All tags with PE counts | `GET /api/v1/pe/tags/all` | **Partially surfaced** (tag filter exists but no tag cloud/browse) |
| Search suggestions/autocomplete | `GET /api/v1/search/suggest` | **Not surfaced** |
| Treemap hierarchy data | `GET /api/v1/aggregations/hierarchy` | **Surfaced** (charts page) |
| Enrichment coverage metadata | `GET /api/v1/metadata` | **Partially surfaced** (programs page only) |

This table represents the single largest opportunity: the API already supports many analyst workflows that the GUI doesn't expose.

---

## 5. Reference Document Currency

All reference documents were updated in **February 2026** as part of a documentation restructuring effort. Key findings:

| Document | Last Updated | Currency Assessment |
|----------|-------------|---------------------|
| `docs/user-guide/data-sources.md` | Feb 2026 | **Current** — FY2026 verified, coverage matrix updated |
| `docs/user-guide/exhibit-types.md` | Feb 2026 | **Current** — 11 types cataloged; P-5/R-2/R-3/R-4 flagged as unverified |
| `docs/user-guide/data-dictionary.md` | Feb 2026 | **Current** — All 29 budget_lines columns documented |
| `docs/user-guide/methodology.md` | Feb 2026 | **Current** — Honest about limitations |
| `pipeline/exhibit_catalog.py` | Feb 2026 | **Current** — 7 summary exhibits verified against real FY2026 data |
| `utils/config.py` (KnownValues) | Feb 2026 | **Current** — Services, exhibit types, patterns |
| `OH_MY_INSTRUCTIONS.md` | Feb 2026 | **Current** — OH-MY-001 through 006 marked COMPLETE |

**Key observation**: The latest reference document updates (OH-MY-001 through 006, completed 2026-02-19) confirmed that the 7 summary exhibit column specifications have been cross-validated against real FY2026 data. Detail exhibits (P-5, R-2, R-3, R-4) remain spec-based. This is the most significant gap in reference document completeness.

---

## 6. Clarification Questions for GUI Development

The following questions are organized by category. Answers to these will directly inform the next sprint of GUI development work.

### Category A: User Identity & Primary Workflow

> **A1. Who is the primary user right now?**
> The GUI_DECISIONS document defines three personas — Analyst (expert), Industry/Journalist (moderate domain knowledge), and General Public (low domain knowledge). The current GUI appears optimized for the Analyst persona. **Which persona should the next development sprint prioritize?** If the tool is primarily for professional budget analysts, the GUI should emphasize power-user features (keyboard shortcuts, comparison tables, batch exports). If it's for journalists or the public, it should emphasize guided discovery and contextual explanations.

> **A2. What is the primary workflow you want to optimize?**
> Three use cases were ranked in GUI_DECISIONS:
> 1. Targeted reporting (search → filter → export) — **well-supported today**
> 2. Trend analysis ("across" years and "down" services) — **not yet implemented in GUI**
> 3. Browsing/discovery (clickable visuals leading to insights) — **partially implemented**
>
> **Should the next sprint focus on building out Use Case 2 (trend analysis), or should it continue polishing Use Case 1?** The API endpoints for trend analysis already exist (`/pe/compare`, `/pe/changes`, `/pe/top-changes`) but are not wired to the GUI.

> **A3. Is the tool intended for single-analyst use or multi-user concurrent access?**
> This affects whether server-side saved views, user accounts, and collaboration features (shared search URLs vs. shared saved analyses) should be prioritized. The current architecture (SQLite, no auth) supports single-user well but has limitations for multi-user scenarios.

> **A4. What does a successful analysis session look like?**
> Describe a concrete example: an analyst sits down with a question — what is it? What sequence of screens/interactions do they follow? What do they produce at the end (a report, an exported spreadsheet, a chart for a briefing)? Understanding the end-to-end workflow will reveal which GUI transitions need improvement.

### Category B: Data Presentation & Amounts

> **B1. How should multi-year funding be presented?**
> The current tool shows FY2024 Actual, FY2025 Enacted, and FY2026 Request as separate columns. For trend analysis, should the GUI provide:
> - (a) A time-series chart showing all available FYs for a single PE?
> - (b) A comparison table (Spruill-chart style) with rows=PEs, columns=FYs?
> - (c) A delta/waterfall view showing changes year-over-year?
> - (d) All of the above with the user choosing their view?
>
> The API already supports all of these; the question is which to prioritize for the GUI.

> **B2. Is the $K default display unit appropriate for your users?**
> The tool stores and displays amounts in thousands of dollars ($K) by default, with a toggle for $M and $B. Most DoD budget documents use $K natively. However, for journalists or the general public, $M or $B might be more intuitive. **Should the default display unit change based on the magnitude of the numbers shown?** (e.g., totals in $B, line items in $M)

> **B3. How important is currency year / constant-dollar distinction?**
> The methodology document notes that currency year distinction is not yet implemented. For multi-year trend analysis, comparing FY2020 and FY2026 dollars without inflation adjustment can be misleading. **Is this a critical need, or is nominal-dollar comparison acceptable for your use cases?** If critical, this would require a deflator/inflator dataset and additional columns.

> **B4. Should the tool surface quantity data (unit counts) alongside dollar amounts?**
> P-5 (Procurement Detail) exhibits include quantity fields (units procured per FY). The API exposes these (`quantity_fy2024`, `quantity_fy2025`, etc.) but the GUI hides them. **Are unit costs and quantities important for your analysis?** If so, they could be added as togglable columns in the search results and as a dedicated view in the PE detail page.

### Category C: Visualization & Analysis Features

> **C1. What are the 3 most important charts you need?**
> The tool currently provides 7 chart types (service comparison, YoY trend, top-10, service comparison, treemap, appropriation doughnut, YoY change by service). The GUI roadmap mentions additional chart types for Phase 2:
> - Spruill charts (PE funding over time, the standard DoD budget briefing format)
> - Waterfall charts (showing what changed between two FYs)
> - Sankey/flow diagrams (budget flowing from appropriation → service → program)
>
> **Which of these would be most valuable?** This determines whether to invest in new charting libraries or maximize the existing Chart.js setup.

> **C2. Should chart elements be more interactive?**
> Currently, only the service bar chart is click-to-filter (clicking "Army" navigates to search results filtered by Army). The GUI roadmap planned full click-to-filter for all charts (LION-009, completed). **Do you want deeper chart drill-down** — e.g., clicking a bar in the top-10 chart opens that PE's detail page, clicking a treemap cell shows all budget lines in that cell?

> **C3. Do you need a "biggest movers" view?**
> The API has `GET /api/v1/pe/top-changes` which ranks PEs by largest absolute funding change (FY2025→FY2026). This is a high-value analyst feature that is **not surfaced in the GUI**. **Should this become a dashboard widget, a dedicated page, or a sort option on the Programs page?**

> **C4. Do you need PE-to-PE comparison?**
> The API supports `GET /api/v1/pe/compare?pe=0602702E&pe=0603461E` for side-by-side funding comparison. **Is this a priority feature?** If so, it could be implemented as:
> - (a) A "Compare" button on the Programs page (select 2-10 PEs, then view side-by-side)
> - (b) A comparison panel within the PE detail page ("Compare with...")
> - (c) A dedicated comparison page accessed via URL

### Category D: Source Document Access & Provenance

> **D1. How important is viewing the source PDF pages?**
> The tool extracts PDF text into `pdf_pages` and the API exposes it via `GET /api/v1/pe/{pe}/pdf-pages`. However, the GUI does not provide an inline PDF viewer or even a link to view extracted page text. The GUI roadmap lists a "Budget document viewer" for Phase 2. **Is this a high priority?** Options:
> - (a) Inline extracted text view (show the parsed text, no PDF rendering)
> - (b) PDF viewer with page navigation (requires embedding a PDF renderer)
> - (c) Link to source PDF on DoD website (already partially implemented in detail panel)
> - (d) ZIP download of relevant PDF pages (API exists: `GET /api/v1/pe/export/pages`)

> **D2. Is source traceability important for your users?**
> The tool tracks source file, sheet name, and row number for every budget line. The detail panel shows this information. **Do your users need to trace a specific number back to the exact cell in the source Excel file?** If so, we could add a "View Source" button that highlights the exact row/cell reference, or provide a download of the original source file.

> **D3. Should the tool link budget data to external context?**
> The GUI roadmap mentions a "News/context layer" for Phase 4. This could mean:
> - Linking PE numbers to Congressional Research Service reports
> - Linking to GAO reports on program performance
> - Linking to Selected Acquisition Reports (SARs)
> - Showing relevant committee markup/conference report language
>
> **Is external context integration a priority, or should the tool focus solely on the budget data itself?**

### Category E: Programs & PE Explorer

> **E1. Is the current Program Explorer sufficient?**
> The Programs page lets users browse all PEs with tag/service filtering. The PE detail page shows funding history, related PEs, descriptions, and projects. **What's missing?** Specifically:
> - Do you need to see all budget lines for a PE across all exhibits (P-1 summary + R-2 detail + PDF narratives) in a unified timeline?
> - Do you need PE "family trees" showing parent/child/sibling relationships?
> - Do you need portfolio-level views (e.g., "show me all Hypersonics-tagged PEs across all services")?

> **E2. How should related PEs be presented?**
> The current related-PEs view shows cards with confidence scores and mention counts. The confidence filter defaults to showing all relationships (0%+). **Is this too noisy?** Should the default filter be higher (e.g., 60%+)? Should related PEs be grouped by relationship type (explicit reference vs. name match)?

> **E3. Should program descriptions be searchable independently?**
> PDF-extracted narrative descriptions (Accomplishments, Plans, etc.) are currently only accessible via the PE detail page. **Would it be valuable to search across all program descriptions?** For example, "find all programs that mention 'artificial intelligence' in their Accomplishments section." The FTS5 infrastructure to support this already exists (`pe_descriptions_fts`).

### Category F: Export & Reporting

> **F1. What export formats do your users actually need?**
> The tool supports CSV, NDJSON, and Excel (.xlsx). The GUI roadmap also mentions PDF and PNG image export. **Which formats are essential?**
> - CSV (for data analysts, spreadsheet import)
> - Excel with formatting (for reports, briefings)
> - PDF (for printing, archival)
> - PNG/SVG (for embedding charts in presentations)
> - PowerPoint-ready format
>
> If PDF or PowerPoint-ready exports are needed, this would require significant new development.

> **F2. Do users need pre-built reports or just raw data export?**
> The current export gives raw filtered data. **Would it be valuable to offer structured reports?** For example:
> - "PE Dossier" — a formatted report for a single PE with all funding, descriptions, related PEs, and source pages
> - "Service Overview" — a summary report for one service across all appropriations
> - "Comparison Report" — side-by-side analysis of 2-5 PEs with charts
>
> These would be templates that auto-populate with the user's current selection.

> **F3. Is there a need for scheduled or recurring exports?**
> Some analysts may want to receive a weekly digest of changes or a monthly budget summary. **Should the tool support email notifications or scheduled report generation?** This would require authentication and a notification service.

### Category G: Infrastructure & Access

> **G1. Is the single-page application / server-rendered approach working?**
> The HTMX + Jinja2 approach provides fast initial loads and good SEO but has limitations for complex client-side interactions (e.g., drag-and-drop PE comparison, interactive pivot tables). **Are there specific interactions that feel clunky or limited?** If so, targeted React/Vue components could be added for specific features without replacing the overall architecture.

> **G2. What is the deployment target?**
> Phase 4 deployment work is partially deferred. **What is the intended deployment model?**
> - (a) Public internet site (requires hosting, domain, TLS, monitoring)
> - (b) Internal network / intranet deployment (simpler security model)
> - (c) Desktop application (Electron wrapper around the web app)
> - (d) Docker container that users run locally
>
> This affects authentication, data update frequency, and infrastructure investment.

> **G3. Is authentication needed?**
> The tool currently has no authentication. Adding authentication would enable:
> - Server-side saved searches and views
> - User-specific feedback tracking
> - Access logging for compliance
> - Rate limiting by user (not just IP)
>
> **Is anonymous access sufficient, or do you need user accounts?**

> **G4. How should data updates be communicated to users?**
> When new fiscal year data is published (typically February for the President's Budget), the refresh pipeline runs and ingests new documents. **Should the GUI notify users of data updates?** Options:
> - (a) A banner: "Data updated on [date] — includes FY2027 President's Budget"
> - (b) A changelog page showing what data was added/changed
> - (c) No notification (users assume data is current)
>
> The API already tracks data freshness via the `/api/v1/metadata` and dashboard endpoints.

---

## 7. Prioritized Recommendations

Based on the gap analysis, the following recommendations are ordered by estimated impact:

### High Priority (Surface existing API capabilities in GUI)

1. **Wire the "top changes" API to a dashboard widget or dedicated page.** The `GET /api/v1/pe/top-changes` endpoint already exists and provides exactly the "biggest movers" analysis that budget analysts need. This is a low-effort, high-value addition.

2. **Add search autocomplete.** The `GET /api/v1/search/suggest` endpoint exists but is not connected to the GUI search input. Adding typeahead suggestions would significantly improve the search experience for all user personas.

3. **Surface PE comparison in the Programs section.** Add checkboxes to PE cards and a "Compare Selected" button that calls `GET /api/v1/pe/compare`. This is a core analyst need.

4. **Add a "Funding Changes" tab to the PE detail page.** Wire `GET /api/v1/pe/{pe}/changes` to show which line items increased/decreased/were new/terminated. This line-item-level change view is critical for budget analysis.

5. **Add PDF page text viewing.** Wire `GET /api/v1/pe/{pe}/pdf-pages` to a new tab or expandable section in the PE detail page. This gives analysts direct access to source document narratives without leaving the tool.

### Medium Priority (New GUI capabilities)

6. **Build a trend analysis view.** This is Use Case 2 from the GUI decisions and represents the largest functional gap. A dedicated page or modal that shows a single PE's funding across all available fiscal years, with a line/bar chart, would address the core "across" analysis need.

7. **Add sorting to the Programs page.** Allow sorting by funding amount, YoY change, organization, and enrichment score. This is a small change that significantly improves discovery.

8. **Fix the amount range filter.** It's currently hardcoded to `amount_fy2026_request`. Make it dynamic based on the visible/selected fiscal year column (GUI_MVP_IMPROVEMENT_PLAN 1.2).

9. **Add a tag cloud or tag browse view.** The `GET /api/v1/pe/tags/all` endpoint provides tag counts. A visual tag cloud or faceted tag browser would enable discovery-oriented exploration (Use Case 3).

### Lower Priority (Future consideration)

10. **Validate P-5, R-2, R-3, R-4 detail exhibits** against real J-Book corpus data to confirm column specifications.

11. **Implement currency year handling** for constant-dollar trend analysis.

12. **Add structured report templates** (PE dossier, service overview) for formatted export.

13. **Consider a budget document viewer** for inline PDF page rendering.

---

## 8. Stakeholder Responses

**Date:** 2026-02-24
**Respondent:** Project owner

### Category A: User Identity & Primary Workflow

> **A1. Primary user persona?**
> **Analyst (power user).** Emphasize power-user features: keyboard shortcuts, comparison tables, batch exports, dense data views.

> **A2. Primary workflow to optimize?**
> **All three use cases.** UC1 (search-filter-export), UC2 (trend analysis), and UC3 (browsing/discovery) are all needed.

> **A3. Single-analyst or multi-user?**
> **Start single, scale up.** Single user now, but design so it can scale to multi-user later.

> **A4. What does a successful analysis session produce?**
> **All output types.** Different sessions have different goals — exported spreadsheets, charts for briefings, and quick in-tool answers are all needed.

### Category B: Data Presentation & Amounts

> **B1. Multi-year funding presentation?**
> **Priority order: Spruill chart table first, then time-series chart, then delta/waterfall.** Will eventually need all three views.

> **B2. Default display unit?**
> **$K is fine.** Analysts expect it and it matches source documents.

> **B3. Currency year / constant-dollar distinction?**
> **Not needed.** Core tenet: this is a data analysis/visualization tool, not a data creation tool. Every number comes from a source document or is the result of math off a source document value (e.g., a sum or percentage). No inflation adjustment.

> **B4. Surface quantity data?**
> **Yes, show them.** Add quantity columns as togglable fields in search results and as a dedicated section in PE detail.

### Category C: Visualization & Analysis Features

> **C1. Most important chart types to add?**
> **Spruill charts first.** The standard DoD budget briefing format — PE funding over time in a structured table/chart.

> **C2. More interactive charts?**
> **Yes, full drill-down.** All charts should be clickable with drill-through to relevant detail pages or filtered views.

> **C3. "Biggest movers" view?**
> **Sort option on Programs page.** Add a "Sort by YoY change" option to the existing Programs page.

> **C4. PE-to-PE comparison?**
> **Yes — multi-PE selection for Spruill-style report.** The ability to select multiple PEs to build a report is needed. When selected, it should create a table with rows of PEs or sub-PE elements and columns of FYs.

### Category D: Source Document Access & Provenance

> **D1. Viewing source PDF pages?**
> **Inline extracted text with a link to the source PDF** (the actual file, not the general Comptroller website) that the user can click to download. Eventually may want an embedded PDF viewer or ZIP download of pages, but those can be saved for later.

> **D2. Source traceability?**
> **Yes, critical.** Add a "View Source" button that shows exact file/sheet/row reference and allows downloading the original source file.

> **D3. Link to external context?**
> **Future consideration.** Not a priority now, but plan the architecture to support it later.

### Category E: Programs & PE Explorer

> **E1. What's missing from Program Explorer?**
> **All three capabilities needed:**
> - Unified PE timeline (all exhibits for one PE in chronological view)
> - PE family trees (parent/child/sibling relationships as visual hierarchy)
> - Portfolio views (cross-cutting views like "all Hypersonics-tagged PEs across all services")

> **E2. How should related PEs be presented?**
> **Both changes:** Raise the default confidence threshold to 60%+ AND group by relationship type (explicit reference vs. name match vs. tag overlap).

> **E3. Program descriptions searchable independently?**
> **Yes, high priority.** Searching across narrative descriptions reveals cross-cutting themes and connections. This is a core analyst need.

### Category F: Export & Reporting

> **F1. Export formats needed?**
> **Add PNG/SVG chart export.** Current CSV + Excel is sufficient for data. Add ability to export charts as images for embedding in presentations and briefings.

> **F2. Pre-built report templates?**
> **Future consideration.** Structured reports would be nice eventually, but not a priority now.

> **F3. Scheduled or recurring exports?**
> **Not needed.** Users will run exports manually when they need them.

### Category G: Infrastructure & Access

> **G1. HTMX + Jinja2 approach working?**
> **Not sure yet.** Need to see more features built before deciding if the architecture needs changes.

> **G2. Deployment model?**
> **Initial capability: local Docker container. Target: public internet site.** Start with Docker for single-user, plan for public deployment later.

> **G3. Authentication needed?**
> **Plan for it later.** Not needed now, but architect the system so auth can be added when moving to public deployment.

> **G4. Data update notifications?**
> **Both banner + changelog.** Banner for quick awareness plus a changelog page for details on what data was added or changed.

---

## 9. Key Decisions Summary

Based on the stakeholder responses, the following decisions inform the next development sprint:

| Decision | Answer | Impact |
|----------|--------|--------|
| **Primary persona** | Analyst (power user) | Dense data views, keyboard shortcuts, batch operations |
| **All three use cases** | UC1 + UC2 + UC3 equally | Broad scope — prioritize by effort/impact ratio |
| **Core tenet** | Data analysis/visualization only | No inflation adjustment, no synthetic data — only source document values and derived math |
| **Spruill charts first** | Priority visualization | Standard DoD format, multi-PE table with FY columns |
| **Full chart drill-down** | All charts clickable | Significant Chart.js interaction work |
| **Source traceability critical** | View Source with file download | Inline text + source PDF link + exact row reference |
| **All PE Explorer features** | Unified timeline + family trees + portfolios | Large scope — likely multi-sprint |
| **Description search high priority** | FTS across narratives | Infrastructure exists (FTS5), needs GUI wiring |
| **Related PEs: raise threshold + group** | 60%+ default, grouped by type | Moderate UI work on PE detail page |
| **PNG/SVG chart export** | New capability | Requires Chart.js-to-image export implementation |
| **Local Docker → public site** | Two-phase deployment | Plan auth hooks now, implement later |
| **Banner + changelog for data updates** | User notification | New GUI components needed |

### Development Priority Stack (derived from answers)

**Highest impact, lowest effort (wire existing API to GUI):**
1. Programs page: add "Sort by YoY change" (uses existing `/pe/top-changes` data)
2. Search autocomplete (wire existing `/search/suggest` endpoint)
3. PE detail: add "Funding Changes" tab (wire `/pe/{pe}/changes`)
4. PE detail: add PDF page text tab (wire `/pe/{pe}/pdf-pages`)
5. PE detail: add source traceability ("View Source" button)

**High impact, moderate effort (new GUI features):**
6. Spruill chart table (multi-PE, FY columns) — core analyst need
7. Multi-PE selection on Programs page for Spruill report building
8. Program description full-text search (wire FTS5 to search UI)
9. Related PEs: 60%+ default threshold, group by relationship type
10. Full chart drill-down on all chart types

**High impact, higher effort (new capabilities):**
11. Unified PE timeline (all exhibits chronologically)
12. PE family tree visualization
13. Portfolio views (tag-based cross-service views)
14. PNG/SVG chart export
15. Quantity data display (togglable columns)
16. Data update banner + changelog page

**Future / deferred:**
17. Pre-built report templates (PE dossier, service overview)
18. External context integration (CRS/GAO links)
19. Authentication system
20. Waterfall charts, Sankey diagrams
21. Embedded PDF viewer
22. Public internet deployment

---

## Next Steps

1. ~~Answer the 27 questions above~~ — **DONE** (all 27 answered 2026-02-24)
2. **Begin "wire existing API to GUI" sprint** — items 1-5 from the priority stack are low-effort, high-value
3. **Design Spruill chart component** — this is the single most important new visualization
4. **Add program description search** — FTS5 infrastructure exists, needs GUI integration
5. **Plan auth-ready architecture** — ensure session/user hooks exist even without auth implementation

---

*This assessment was generated by reviewing the complete codebase, all documentation, all planning documents, recent git history, and the current state of all agent instruction files (LION, TIGER, BEAR, OH MY). It represents a snapshot of the project as of 2026-02-24. Stakeholder responses were collected on 2026-02-24.*
