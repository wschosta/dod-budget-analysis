# Noticed Issues — 2026-02-25

Issues observed during review of the DoD Budget Explorer UI (localhost:8000).
Split into two rounds: the first (2026-02-24) catalogued data and rendering bugs;
the second (2026-02-25) focused on hardcoded values, UX problems, and things that
would worsen the user experience as data grows.

---

## Round 1 — Data & Rendering Bugs (2026-02-24)

### Search Page (/)

1. **Fiscal Year dropdown — empty** (0 options, won't open)
2. **Appropriation dropdown — empty** (0 options, won't open)
3. **Service/Agency — duplicates** (AF/Air Force, ARMY/Army, NAVY/Navy — 57 total entries)
4. **Exhibit Type — bad labels** (showing `c1 — c1` instead of readable names like "C-1")
5. **"By Appropriation Type" donut chart — all "Unknown"** (single $6B slice)
6. **"Budget by Service" bar chart — large "Unknown" bucket** ($665M)
7. **Duplicate/repetitive search results** — programs like "Conventional Munitions Demilitarization" and "Conventional Prompt Strike Test Facility" each appear multiple times instead of as single consolidated entries
8. **Missing PE numbers** — those same programs should have PE#s but show "—"

### Detail View (from search results)

9. **Detail tab is very slow** to load when clicking a search result
10. **Detail tab data errors (CPS example):**
    - Shows FY 1998 — incorrect, program didn't exist then
    - Appropriation shows "- -" (meaningless)
    - Source file path says "FY1998\PB\Defense_wide..." — wrong
    - Related Fiscal Years shows "FYFY 1998" — duplicated prefix typo

### Dashboard (/dashboard)

11. **Dashboard page — extremely slow to load**
12. **Summary cards show "— —"** for FY2026 Total Request, FY2025 Enacted, and YOY Change
13. **"By Appropriation" — "No appropriation data available"**
14. **"Budget by Service" chart** — bars near zero ($0-$1M range), "Unknown" is top entry
15. **"Top 10 Programs by FY2026 Request" — completely empty**

### Charts (/charts)

16. **YOY chart confirms data gap** — bars only at FY 1998 and FY 2025-2026, nothing for FY 2000-2024
17. **Top 10 has duplicates** — "Classified Programs" x4, "Private Sector Care" x2, "Ship Depot Maintenance" x2
18. **Defaults to FY 1998** — should probably default to most recent year
19. **Selecting FY 2012 shows blank** (no data for that year)
20. **Service dropdown has same duplicates** (ARMY/Army, AF/Air Force, NAVY/Navy)
21. **Appropriation Breakdown donut is 100% "Unknown"**

### Programs (/programs)

22. **Duplicate FY entries** — e.g., FY 2012 appears 8 times for B-52 Squadrons
23. **Missing FY columns** — no columns for FY 1998-2023
24. **FY 2000-2011 have zero entries** despite data supposedly existing
25. **FY24 Actual data incorrectly attributed** to FY 1998 source
26. **Tags dropdown is mispositioned** — overlaps onto the program cards
27. **Tag counts look inflated** — rdte: 1539/1579, communications: 1502, aviation: 1438 (nearly every program tagged with nearly everything)

### Footer (all pages)

28. **Data sources FY gap** — shows FY 1998, 1999, then jumps to 2010-2026 (missing FY 2000-2009)

### Round 1 Root Cause Analysis

#### Database Issues (root cause for ~80% of Round 1 problems)

| Issues | Root Cause | Details |
|--------|-----------|---------|
| #1, #2 (empty FY & Appropriation dropdowns) | **Reference tables missing** | `budget_cycles`, `appropriation_titles`, `services_agencies`, `exhibit_types` tables do not exist in the DB. Frontend code tries to query them, gets nothing, falls back poorly. |
| #3, #20 (service duplicates) | **Inconsistent `organization` column** | Same service stored as `ARMY` (155K rows) / `A` (36K rows), `NAVY` (160K) / `N` (42K), `AF` (116K) / `F` (36K). Plus 5,955 blank rows. |
| #5, #13, #21 (appropriation "Unknown") | **`appropriation_code` column empty/null** | Appropriation codes are not being parsed from source documents during ingestion. |
| #6, #14 (service "Unknown") | **Blank organization rows** | 5,955 rows with empty organization + inconsistent naming inflates "Unknown". |
| #7, #17, #22 (duplicate results) | **644K rows, many duplicated per program/FY** | Same programs parsed from multiple exhibits or sources without deduplication. |
| #8 (missing PE numbers) | **73% of rows (472K of 644K) have no PE number** | PE numbers only populated for ~27% of budget lines. |
| #16, #19, #28 (FY data gap 2000-2009) | **Data never ingested** | Only FY 1998-1999 and FY 2010-2026 exist. FY 2000-2009 was never downloaded or parsed. |
| #10, #25 (wrong FY attribution) | **FY derived from source file path** | Data associated with whichever FY folder the source file was in, not the actual program fiscal year. |
| #12, #15 (dashboard empty/broken) | **Cascading effect** | Missing appropriation data + slow queries on 644K unindexed rows. |
| #27 (inflated tag counts) | **Enrichment over-tagging** | Pipeline assigns too many tags — rdte on 1539/1579 programs means tags are nearly meaningless. |

#### Frontend Issues (Round 1)

| Issues | Root Cause | Details |
|--------|-----------|---------|
| #4 (exhibit "c1 — c1") | **Fallback code in `frontend.py:136-140`** | When `exhibit_types` reference table is missing, fallback sets `display_name = code`, producing "c1 — c1". |
| #10 ("FYFY 1998") | **Template prepends "FY"** | `results.html:22` and `detail.html` prepend "FY" to values that already contain "FY" prefix in the database. |
| #9, #11 (slow detail/dashboard) | **No indexes on filter columns** | 644K rows without proper indexes on fiscal_year, organization, etc. (DB issue amplified by frontend). |
| #26 (tags dropdown mispositioned) | **CSS overflow/z-index** | Filter panel clipping the absolutely-positioned dropdown. |
| #18 (defaults to FY 1998) | **Sort order** | Charts page defaults to first FY in sorted list instead of most recent. |

---

## Round 2 — Hardcoded Values & UX Problems (2026-02-25)

### 29. Search Results — Hardcoded FY Columns (Critical UX Issue)

**Location:** `templates/partials/results.html:80-92` (column toggles), `:97-154` (table headers), `:183-189` (table cells); `api/routes/frontend.py:427-431` (SQL SELECT)

The search results table only ever shows five amount columns:
- FY24 Actual, FY25 Enacted, FY25 Total, FY26 Request, FY26 Total

The column toggle buttons, table headers, sort links, and the backend SQL query are all hardcoded to these specific `amount_fy2024_actual`, `amount_fy2025_enacted`, `amount_fy2025_total`, `amount_fy2026_request`, `amount_fy2026_total` columns. There is no UI mechanism for users to view amount data from any other fiscal year — even though the database contains `amount_fy*` columns spanning FY1998 through FY2026.

**Impact:** Users researching historical trends or earlier fiscal years cannot see any dollar amounts in the search results table. This is a fundamental gap since the database covers FY1998-1999 and FY2010-2026.

**Suggested fix:** Dynamically discover available `amount_fy*` columns from the DB schema (the aggregations endpoint already does this via `utils.database.get_amount_columns()`). Let the user select which FY columns to display — either through a FY column picker dropdown or by auto-showing columns relevant to the selected fiscal year filter. The column toggles should be generated dynamically rather than hardcoded in the template.

---

### 30. Detail Panel — Hardcoded FY Funding Fields

**Location:** `templates/partials/detail.html:64-88`

The budget line detail panel displays exactly six hardcoded funding fields: FY2024 Actual, FY2025 Enacted, FY2025 Supplemental, FY2026 Request, FY2026 Reconciliation, FY2026 Total. It queries `SELECT * FROM budget_lines` (line 549 of `frontend.py`) so all columns are fetched, but the template only renders these six.

**Impact:** When a user clicks on a budget line from FY2012, they see zeros or dashes for all funding fields because no FY2012 amount columns are displayed — even though the row may have data in `amount_fy2012_request`, etc.

**Suggested fix:** Template should iterate over all `amount_fy*` columns present in the row dict, filtering out null/zero values, and display them dynamically. Group by fiscal year (Actual, Enacted, Request, etc.) for readability.

---

### 31. Dashboard — Hardcoded to FY2025/FY2026, No Year Selector

**Location:** `templates/dashboard.html:11-16,50`; `static/js/dashboard.js:51-61,76,168-169`; `api/routes/dashboard.py:20-24`

The entire dashboard is locked to FY2025 Enacted vs FY2026 Request:
- Stat cards: "FY2026 Total Request" and "FY2025 Enacted" are hardcoded labels
- Top programs: "Top 10 Programs by FY2026 Request" — hardcoded heading
- Service chart: "FY2026 Request ($M)" — hardcoded label
- Top programs table: "FY26 Request ($K)" / "FY25 Enacted ($K)" — hardcoded headers
- Backend: `_detect_fy_columns()` picks `fy2026_request` and `fy2025_enacted`

There is no fiscal year selector on the dashboard page at all (unlike `/charts` which has one).

**Impact:** When FY2027 data is added, the dashboard will continue showing FY2026 unless someone manually updates multiple files. Users cannot explore budget summaries for any historical year.

**Suggested fix:** Add a FY selector (like the charts page has). Auto-detect the latest available FY pair. Make stat card labels, chart legends, and table headers dynamic based on the selected year. The dashboard API endpoint already accepts a `fiscal_year` filter parameter — just need the UI to expose it.

---

### 32. Program Detail — Hardcoded FY Columns in Funding Table & Chart

**Location:** `templates/program-detail.html:52-59,84-86`; `static/js/program-detail.js:36-55`

The funding history table on the program detail page has hardcoded columns: FY24 Actual, FY25 Enacted, FY26 Request, Delta, plus quantity columns for those same three years. The JS chart also only extracts `fy2024_actual`, `fy2025_enacted`, `fy2026_request`.

**Impact:** If a program has data across multiple fiscal years (e.g., FY2010-FY2026), the funding table only shows the three latest year-type pairs. Historical funding is invisible.

**Suggested fix:** Funding table columns should be generated dynamically from available data. The PE endpoint returns data per fiscal year — the template should iterate over all FY columns present rather than referencing three hardcoded ones. The chart should similarly plot all available years.

---

### 33. Program Funding Changes — Hardcoded FY25→FY26 Comparison

**Location:** `templates/program-detail.html:97`; `templates/partials/program-changes.html:6-11,36-38`

The "Funding Changes" section is locked to "FY25 → FY26":
- Section header: `Funding Changes (FY25 → FY26)` — hardcoded
- Summary: "Total FY25" / "Total FY26 Request" — hardcoded labels
- Table: "FY25 Total ($K)" / "FY26 Request ($K)" — hardcoded headers

**Impact:** Cannot view changes for any other year pair. When FY2027 data arrives, this section becomes stale.

**Suggested fix:** Make the comparison pair dynamic based on the two most recent FY data points available for the PE, or let the user select which year-pair to compare.

---

### 34. Charts Page — Top-N Query Hardcoded to `amount_fy2026_request`

**Location:** `static/js/charts.js:206,220`

The Top 10 chart fetches data sorted by `amount_fy2026_request` regardless of which FY is selected in the dropdown. Line 206: `sort_by=amount_fy2026_request&sort_dir=desc`. Line 220 falls back to `amount_fy2026_request`.

**Impact:** When a user selects FY2020 in the charts page FY dropdown, the Top-10 bar chart still ranks items by their FY2026 request amount — not by the selected year's data. The chart title says "Top 10 Budget Line Items — FY Request ($M)" which is misleading.

**Suggested fix:** Use the selected FY to dynamically pick the sort column. Map the selected FY value to the appropriate `amount_fy{year}_request` (or `_enacted`/`_actual` as appropriate) column name.

---

### 35. Filter Chips Display Hardcoded "FY26" Label for Amount Range

**Location:** `templates/partials/results.html:26-27`

Active filter chips for amount range display "FY26 Min $K" / "FY26 Max $K" regardless of which amount column is actually being filtered. Even though the EAGLE-1 work added dynamic `amount_column` support in the backend, the chip labels are static.

**Suggested fix:** Use the `amount_column` value from the filter context to generate the correct chip label (e.g., "FY24 Actual Min $K" or "FY25 Enacted Min $K").

---

### 36. Empty State Text Hardcoded to "FY2024–FY2026"

**Location:** `templates/partials/results.html:245`; `templates/partials/program-list.html:58`

When filters return zero results, the helpful message says "Available data covers FY2024–FY2026" — a hardcoded string that doesn't reflect actual data coverage (which includes FY1998-1999 and FY2010-2026).

**Suggested fix:** Query actual FY range from the database (min/max fiscal_year from `budget_lines`) and display dynamically.

---

### 37. Search Source Toggle Duplicated Between Hero and Sidebar

**Location:** `templates/index.html:26-30` (hero) and `templates/index.html:88-92` (sidebar)

The "Budget Lines / Program Descriptions / Both" radio buttons appear twice on the search page — once in the hero area and again in the filter sidebar. They use different `name` attributes (`hero_source` vs `source`) and don't sync state between them. Only the sidebar version is actually included in the HTMX filter form.

**Impact:** Users may change the toggle in one location and not realize the other one exists (or expect them to be linked). The hero version's selection is lost when the sidebar form submits.

**Suggested fix:** Remove the duplicate from the hero area (or keep only one and sync state via JS). The sidebar version is the functional one.

---

### 38. Service/Agency Dropdown — Potentially Dozens of Entries

**Location:** `templates/index.html:112-119`; `api/routes/frontend.py:103-134`

Even after the FIX-002 deduplication work, the Service/Agency dropdown pulls all distinct `organization_name` values from `budget_lines`. With inconsistent naming (e.g., ARMY/A/Army as separate entries), this could have 50+ options. The PRD mentions 6 primary services but the DB may contain many more org names (sub-agencies, joint organizations, etc.).

**Impact:** A dropdown with dozens of entries is hard to scan quickly. The checkbox-select component helps but still creates a long scrollable list.

**Suggested fix:** Group or normalize service names at the DB level (collapse ARMY/A → Army, etc.). Consider a two-tier approach: top-level services + "More" for sub-agencies. Or implement type-ahead search within the dropdown.

---

### 39. Tags Dropdown — Up to 30 Options, Potentially Meaningless

**Location:** `templates/programs.html:72-79`; `api/routes/frontend.py:653`

The Tags multi-select dropdown on the Programs page loads up to 30 tags. Combined with issue #27 (inflated tag counts where `rdte` appears on 1539/1579 programs), many tags are near-universal and selecting one barely filters anything. The page also has a tag cloud section that provides a separate browsing experience for the same data.

**Impact:** A 30-option multi-select with meaningless over-applied tags gives the user a false sense of filtering power while achieving little.

**Suggested fix:** Fix the enrichment pipeline to produce more selective tags (issue #27). Until then, consider showing only tags with < 50% coverage (so they actually filter meaningfully). The tag cloud and dropdown serve overlapping purposes — consider consolidating.

---

### 40. Programs Page — No Pagination, Only Shows 25 Items

**Location:** `api/routes/frontend.py:656`; `templates/partials/program-list.html:44-50`

The Programs page loads only 25 PE cards with no pagination controls. When more than 25 programs match, the page displays "Showing 25 of N programs. Refine your filters to narrow results." — asking users to filter instead of browse.

**Impact:** Users exploring the full program inventory cannot page through it. With 1,579 programs and only 25 visible, 98% of data is hidden behind mandatory filtering.

**Suggested fix:** Add HTMX-powered "Load more" or full pagination (page numbers + prev/next) to the program list partial. The `list_pes()` function already accepts `limit` and `offset` parameters.

---

### 41. Program Cards — No Funding Preview

**Location:** `templates/partials/program-list.html:7-33`

PE cards on `/programs` show PE number, organization, title, budget type, and up to 5 tags — but zero dollar amounts. Users must click into each program to see any funding data.

**Impact:** When browsing programs to find the largest ones, users have to click into every card individually. Sorting by "Funding (FY26, desc)" puts big programs first, but the cards don't confirm this with visible amounts.

**Suggested fix:** Add a small funding summary to each card (e.g., "FY26 Request: $1.2B" or a sparkline). The `list_pes()` already returns funding data — just need to display it.

---

### 42. Charts Page — Service Multi-Select Has Hardcoded Height

**Location:** `templates/charts.html:22`

The service filter on the charts page uses `style="height:80px"` for the multi-select, creating a tiny scrollable box. With potentially 50+ service entries (per issue #38), this becomes unusable.

**Suggested fix:** Use the same `checkbox-select` component used on the search page, or remove the fixed height and let it auto-size.

---

### 43. Compare Link Points to Wrong URL

**Location:** `templates/partials/program-list.html:40`

The "Compare Selected" button links to `href="/spruill"`, but the actual route is registered at `/compare` in `frontend.py:718`. This would result in a 404 for users trying to compare programs.

**Suggested fix:** Change the href to `/compare` (or add a `/spruill` redirect in `frontend.py`).

---

### 44. Treemap Labels — Hardcoded White Text Color

**Location:** `static/js/charts.js:408`

The treemap chart uses `color: '#fff'` (white) for all labels. This doesn't respect dark/light mode CSS variables and will be invisible on any light-colored treemap segments.

**Suggested fix:** Use `getComputedStyle(document.documentElement).getPropertyValue('--text-on-primary')` or a contrast-aware color selection. Other charts in `charts.js` already read CSS variables for theming.

---

### 45. Dashboard — Data Freshness Not Displayed

**Location:** `static/js/dashboard.js` (missing); `api/routes/dashboard.py:269-288`

The dashboard API returns a `freshness` field with `last_build`, `last_build_status`, and `data_sources_updated` timestamps. However, `dashboard.js` never reads or displays this information. Users have no way to know how current the displayed data is.

**Suggested fix:** Add a small "Last updated: ..." indicator to the dashboard page, reading from `data.freshness` in the API response.

---

### 46. Download Modal — Hardcoded 50,000 Row Limit Text

**Location:** `templates/index.html:260`

The download modal states "Downloads apply the current filters (up to 50,000 rows)." This limit appears to be informational text only — unclear if the backend enforces it or if the true limit is different.

**Suggested fix:** Verify the actual backend limit and display it dynamically. If possible, inform the user how many rows match the current filters vs the cap (e.g., "Your filters match 12,340 rows. Downloading all.").

---

### 47. Glossary — Hardcoded FY Example

**Location:** `templates/partials/glossary.html:9`

The glossary entry for "Fiscal Year" uses the example "FY2026 = Oct 2025 - Sep 2026". This will become stale as time passes.

**Suggested fix:** Use a timeless formulation like "FY20XX runs October 1, 20XX-1 through September 30, 20XX" or dynamically insert the current/latest year.

---

### 48. Amount Range Filter — No FY Column Selector Exposed in UI

**Location:** `templates/index.html:150-173`

The "Amount Range ($K)" filter lets users enter min/max amounts, but doesn't tell them which FY column is being filtered. The backend (EAGLE-1) supports a dynamic `amount_column` parameter, and `frontend.py` passes `fiscal_year_columns` to the template context — but the template never renders a column picker. The filter silently applies to `amount_fy2026_request` by default.

**Impact:** A user filtering for "programs with more than $1M actual spending" has no way to specify which year's actual column to check. They're always filtering on FY2026 request whether they know it or not.

**Suggested fix:** Add a small dropdown next to the amount range inputs (or use the `fiscal_year_columns` context variable) to let users pick which FY column the min/max filter applies to. The backend plumbing already exists.

---

### 49. Excessive Inline Styles Throughout Templates

**Location:** Nearly every template file

Templates make heavy use of inline `style="..."` attributes instead of CSS classes. Examples:
- `dashboard.html:29`: `style="text-align:center;padding:2rem"`
- `program-detail.html:41-42`: `style="display:flex;align-items:center;justify-content:space-between;..."`
- `results.html:155-163`: Multiple inline styles per row element
- `index.html:184-193`: Save search area entirely inline-styled

**Impact:** Theming is inconsistent — some spacing/colors use CSS variables while adjacent elements use hardcoded values. Responsive design is harder to maintain. Print styles can't override inline styles.

**Suggested fix:** Extract repeated inline style patterns into named CSS classes in `main.css`. This is a gradual refactor — not urgent, but should be addressed as files are touched.

---

### 50. FY Tooltip Hardcoded to "FY2026"

**Location:** `templates/index.html:99`

The fiscal year filter tooltip says `"FY2026 = Oct 2025 – Sep 2026"` — a hardcoded example that will become outdated.

**Suggested fix:** Use a generic phrasing or dynamically insert the latest available FY.

---

## Priority Assessment

### Critical (fundamental data access gap)

| # | Issue | Effort | Fix Approach |
|---|-------|--------|--------------|
| 29 | Search results hardcoded FY columns | Medium | Dynamic column discovery + template loop |
| 30 | Detail panel hardcoded FY fields | Medium | Iterate available `amount_fy*` columns |
| 31 | Dashboard locked to FY25/26 | Medium | Add FY selector, dynamic labels |
| 32 | Program detail hardcoded FY columns | Medium | Dynamic columns from PE API response |
| 34 | Charts Top-N hardcoded to FY2026 | Low | Map selected FY → sort column in JS |

### High (significant UX degradation)

| # | Issue | Effort | Fix Approach |
|---|-------|--------|--------------|
| 33 | Funding changes locked to FY25→26 | Low-Med | Dynamic year-pair from latest data |
| 40 | Programs page no pagination | Low | Add "Load more" or page nav to partial |
| 43 | Compare link wrong URL | Trivial | Fix href to `/compare` |
| 38 | Service dropdown dozens of entries | Medium | Normalize at DB level + type-ahead |
| 48 | Amount filter no FY column picker | Low | Render the already-passed `fiscal_year_columns` |

### Medium (misleading or confusing)

| # | Issue | Effort | Fix Approach |
|---|-------|--------|--------------|
| 35 | Filter chips say "FY26" always | Trivial | Use `amount_column` from context |
| 36 | Empty state says "FY2024-FY2026" | Trivial | Query actual FY range |
| 37 | Duplicate search source toggles | Trivial | Remove hero version |
| 39 | Tags dropdown 30 options, low signal | Med (data) | Fix enrichment pipeline selectivity |
| 41 | Program cards show no funding | Low | Add amount from existing data |
| 44 | Treemap white text ignores theme | Trivial | Use CSS variable for color |
| 45 | Dashboard no data freshness | Low | Display `data.freshness` from API |
| 46 | Download modal hardcoded limit text | Trivial | Dynamic count display |

### Low (cosmetic / future-proofing)

| # | Issue | Effort | Fix Approach |
|---|-------|--------|--------------|
| 42 | Charts service select fixed height | Trivial | Use checkbox-select or remove height |
| 47 | Glossary FY example hardcoded | Trivial | Generic phrasing |
| 49 | Excessive inline styles | Ongoing | Gradual CSS class extraction |
| 50 | FY tooltip hardcoded "FY2026" | Trivial | Generic or dynamic |
