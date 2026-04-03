# Noticed Issues — 2026-02-25

Issues observed during review of the DoD Budget Explorer UI (localhost:8000).
Split into two rounds: the first (2026-02-24) catalogued data and rendering bugs;
the second (2026-02-25) focused on hardcoded values, UX problems, and things that
would worsen the user experience as data grows.

**Legend:** ~~Strikethrough~~ = resolved. Items marked **[RESOLVED]** have been fixed
and should not be re-attempted. Items marked **[OPEN]** still need attention.

---

## Round 1 — Data & Rendering Bugs (2026-02-24)

### Search Page (/)

1. **[RESOLVED — verified via test suite]** **Fiscal Year dropdown — empty** (0 options, won't open)
   _Fix: FY dropdown queries `budget_lines` directly with validation. Tests: `test_frontend_helpers.py::TestGetFiscalYears` (4 cases)._
2. **[RESOLVED — verified via test suite]** **Appropriation dropdown — empty** (0 options, won't open)
   _Fix: Endpoint queries distinct appropriation_code from budget_lines. Tests: `test_reference_aggregation.py::TestListAppropriations` (2 cases)._
3. **[RESOLVED — verified via test suite]** **Service/Agency — duplicates** (AF/Air Force, ARMY/Army, NAVY/Navy — 57 total entries)
   _Fix: 94-variant normalization mapping in `utils/normalization.py`. Tests: `test_frontend_helpers.py::TestGetServices` (2 cases)._
4. **[RESOLVED — verified via test suite]** **Exhibit Type — bad labels** (showing `c1 — c1` instead of readable names like "C-1")
   _Fix: `_clean_display()` fallback in `api/routes/frontend.py`. Tests: `test_frontend_helpers.py::TestGetExhibitTypes::test_bad_display_name_replaced_by_static_map`._
5. **[RESOLVED in Round 5]** **"By Appropriation Type" donut chart — all "Unknown"** (single $6B slice)
6. **[RESOLVED in Round 5]** **"Budget by Service" bar chart — large "Unknown" bucket** ($665M)
7. **[RESOLVED in Round 5]** **Duplicate/repetitive search results** — programs appear multiple times instead of consolidated
8. **[STRUCTURAL — documented in PRD §9]** **Missing PE numbers** — those same programs should have PE#s but show "—"
   _Note: 33,854 of 51,053 rows (66.3%) lack PE numbers. However, this is **three distinct populations**, not one problem:_
   - _**R-1 (RDT&E):** 98.3% PE coverage (280 remaining are classified programs, footnotes, or non-standard suffixes like BTA/OTE). Essentially solved._
   - _**P-1/P-1R (Procurement):** 2.1% PE coverage (18,260 rows). These use **Budget Line Items (BLIs)**, a fundamentally different identifier system from Program Elements. Only ~120 rows can be mapped via title+org matching against pe_index. The rest (ammunition, equipment, modifications) have no PE equivalent in DoD's budget structure. **Future work:** build a parallel BLI-based enrichment/tagging system analogous to the PE pipeline._
   - _**O-1/M-1/C-1/RF-1 (O&M, MilPers, MilCon, Revolving):** 0% PE coverage (13,559 rows, 26.6%). These exhibit types structurally do not use PE numbers._
   - _**Amendment/OGSI:** 31%/24% coverage (2,549 rows). Partially recoverable via cross-reference._

### Detail View (from search results)

9. **[RESOLVED — verified via test suite]** **Detail tab is very slow** to load when clicking a search result
   _Fix: Composite indexes + dedup (644K→47K rows). Tests: `test_schema_design.py::TestCreateMigration::test_creates_indexes`._
10. **[RESOLVED — 2026-04-02]** **Detail tab data errors (CPS example):**
    - ~~Shows FY 1998 — incorrect, program didn't exist then~~ ← **fixed: `source_fiscal_year` column distinguishes data FY from source document FY**
    - ~~Appropriation shows "- -" (meaningless)~~ ← **fixed by appropriation backfill (Round 5)**
    - ~~Source file path says "FY1998\PB\Defense_wide..." — wrong~~ ← **fixed: detail view now shows "Budget Submission" FY separately when it differs from data FY**
    - ~~Related Fiscal Years shows "FYFY 1998" — duplicated prefix typo~~ ← **fixed by `format_fy` filter**
    _Fix: Added `source_fiscal_year` column to `budget_lines` (extracted from directory path). Detail template shows "Data Fiscal Year" and "Budget Submission" FY when they differ. 3,296 of 51,053 rows (6.5%) have a mismatch._

### Dashboard (/dashboard)

11. **[RESOLVED — verified via test suite]** **Dashboard page — extremely slow to load**
    _Fix: Indexes, cache warmup, 47K-row table. Tests: `test_gui_features.py::TestDashboardAPI` (11 cases) + `test_reference_aggregation.py::TestWarmCaches` (3 cases)._
12. **[RESOLVED — verified via test suite]** **Summary cards show "— —"** for FY2026 Total Request, FY2025 Enacted, and YOY Change
    _Fix: Dynamic FY column detection. Tests: `test_dynamic_fy_columns.py` (32 cases)._
13. **[RESOLVED — verified via test suite]** **"By Appropriation" — "No appropriation data available"**
    _Fix: Appropriation backfill + BUDGET_TYPE_CASE_EXPR. Tests: `test_data_quality_fixes.py::TestStep2AppropriationCodeBackfill`._
14. **[RESOLVED in Round 5]** **"Budget by Service" chart** — bars near zero ($0-$1M range), "Unknown" is top entry
15. **[RESOLVED — verified via test suite]** **"Top 10 Programs by FY2026 Request" — completely empty**
    _Fix: Cascading fix from dedup + indexes. Tests: `test_gui_features.py::TestDashboardAPI::test_summary_has_top_programs`._

### Charts (/charts)

16. **[STRUCTURAL — documented in PRD §9]** **YOY chart data gap** — FY 2000-2009 show no bars (documents not publicly available). FY 2010-2026 now populated.
    _Note: Original description said "bars only at FY 1998 and FY 2025-2026" — this was accurate before FY2012+ display-file fix (bd2e4b5). Current gap is FY 2000-2009 only._
17. **[RESOLVED — 2026-04-02]** **Top 10 has duplicates** — "Classified Programs" x4, "Private Sector Care" x2, "Ship Depot Maintenance" x2
    _Fix: Client-side deduplication by line_item_title in `static/js/charts.js` loadTopNChart(), fetches 30 rows and deduplicates to top 10._
18. **[RESOLVED — verified via test suite]** **Defaults to FY 1998** — should probably default to most recent year
    _Fix: `api/routes/frontend.py:540` reverses FY list. Tests: `test_frontend_helpers.py::TestGetFiscalYears`._
~~19. Selecting FY 2012 shows blank~~ **[RESOLVED — 2026-04-02]**
    _Fix: Commit bd2e4b5 changed display-file exclusion logic to retain `_display.xlsx` files when no base file exists. FY2012 now has 2,997 rows. See #56._
20. **[RESOLVED — verified 2026-04-02]** **Service dropdown has same duplicates** (ARMY/Army, AF/Air Force, NAVY/Navy)
    _Fix: Same as #3. Verified: `repair_database.py` run on production DB; org normalization confirmed 0 rows needing fix (already normalized)._
21. **[RESOLVED — verified 2026-04-02]** **Appropriation Breakdown donut is 100% "Unknown"**
    _Fix: Same as #5. Verified: `repair_database.py` run on production DB; reference tables populated (225 appropriation titles, 54 services, 17 exhibit types)._

### Programs (/programs)

22. **[RESOLVED in Round 5]** **Duplicate FY entries** — e.g., FY 2012 appears 8 times for B-52 Squadrons
~~23. Missing FY columns~~ **[RESOLVED in Round 2]**
    _Fix: `get_amount_columns(conn)` dynamically discovers all `amount_fy*` columns from DB schema. See #29 (Round 2). Column display is no longer hardcoded._
24. **[STRUCTURAL — documented in PRD §9]** **FY 2000-2009 have zero entries** (documents not publicly available). FY 2010-2011 have minimal data (2-5 rows). FY 2012+ fully populated after display-file fix (bd2e4b5).
    _Note: Original description said "FY 2000-2011 have zero entries" — overstated. FY2010 has 2 rows, FY2011 has 5, FY2012 has 2,997._
25. **[RESOLVED — 2026-04-02]** **FY24 Actual data incorrectly attributed** to FY 1998 source
    _Fix: Same as #10 — `source_fiscal_year` column now separates data FY from source document FY._
26. **[RESOLVED — CSS fix verified]** **Tags dropdown is mispositioned** — overlaps onto the program cards
    _Fix: CSS z-index + stacking context in `static/css/main.css:1354-1358`._
27. **[RESOLVED — 2026-04-02]** **Tag counts look inflated** — rdte: 1539/1579, communications: 1502, aviation: 1438 (nearly every program tagged with nearly everything)
    _Fix: API endpoint `GET /api/v1/pe/tags/all` now filters by `min_confidence` (default 0.85) and `max_coverage` (default 0.5). Pipeline-level over-tagging still exists in the raw data but is filtered at query time._

### Footer (all pages)

28. **[STRUCTURAL — documented in PRD §9]** **Data sources FY gap** — FY 2000-2009 missing (documents not publicly available). FY 1998-1999 and FY 2010-2026 are populated.
    _Note: FY2010 has 2 rows, FY2011 has 5, FY2012+ fully populated._

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
| #16, ~~#19~~, #28 (FY data gap 2000-2009) | **Data never ingested** | FY 2000-2009 was never downloaded or parsed. FY 1998-1999 and FY 2010-2026 exist. #19 resolved — FY2012 now populated (bd2e4b5). |
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

### ~~29. Search Results — Hardcoded FY Columns~~ **[RESOLVED]**

Backend now calls `get_amount_columns(conn)` to discover all `amount_fy*` columns
from the DB schema. Template column toggles, headers, and cells are generated via
`{% for col in amount_columns %}` loops. Sort validation accepts any `amount_fy*`
column via regex pattern. Users can now see data from all available fiscal years.

**Files changed:** `api/routes/frontend.py`, `templates/partials/results.html`, `utils/query.py`
**Test coverage:** `tests/test_shared_group/test_dynamic_fy_columns.py` (32 cases)

---

### ~~30. Detail Panel — Hardcoded FY Funding Fields~~ **[RESOLVED]**

Template now iterates `{% for key, value in item.items() %}` filtering for
`key.startswith('amount_fy')` and non-null values. All FY amount columns present
in the row are displayed automatically.

**Files changed:** `templates/partials/detail.html`

---

### ~~31. Dashboard — Hardcoded to FY2025/FY2026 Labels~~ **[RESOLVED]**

Stat card labels changed from "FY2026 Total Request" / "FY2025 Enacted" to
"Latest Request Total" / "Prior Year Enacted". Top programs heading changed to
"Top 10 Programs by Request". Chart legend and table headers genericized.
"Last Updated" stat card added showing data freshness from API.

**Files changed:** `templates/dashboard.html`, `static/js/dashboard.js`
**Note:** The dashboard still uses `_detect_fy_columns()` internally — it just doesn't
expose year-specific labels to the UI. A FY selector is a possible future enhancement.

---

### ~~32. Program Detail — Hardcoded FY Columns in Funding Table & Chart~~ **[RESOLVED]**

Template now discovers `amount_fy*` columns from `pe_data.funding[0].keys()` and
renders headers and cells dynamically. Delta calculation uses the last two sorted
amount columns. Chart in `program-detail.js` detects all `fy*` keys from the API
response and builds datasets dynamically.

**Files changed:** `templates/program-detail.html`, `static/js/program-detail.js`

---

### ~~33. Program Funding Changes — Hardcoded FY25→FY26~~ **[RESOLVED]**

Section header changed to "Funding Changes (Year-over-Year)". Summary labels changed
to "Prior Year Total" / "Current Request". Table headers changed to "Prior Year ($K)"
/ "Request ($K)".

**Files changed:** `templates/program-detail.html`, `templates/partials/program-changes.html`

---

### ~~34. Charts Page — Top-N Query Hardcoded to `amount_fy2026_request`~~ **[RESOLVED]**

`loadTopNChart(fy)` now constructs the sort column dynamically:
`'amount_fy' + fy.replace(/\D/g, '') + '_request'`. Fallback also uses the
selected FY instead of hardcoded 2026.

**Files changed:** `static/js/charts.js`

---

### ~~35. Filter Chips Display Hardcoded "FY26" Label~~ **[RESOLVED]**

Added Jinja loop to derive `amt_label` from `fiscal_year_columns` by matching
`amount_column`. Chips now show e.g. "FY2024 Actual Min $K" instead of "FY26 Min $K".

**Files changed:** `templates/partials/results.html`

---

### ~~36. Empty State Text Hardcoded to "FY2024–FY2026"~~ **[RESOLVED]**

Replaced with generic "Try broadening your search or removing some filters." in both
results.html and program-list.html.

**Files changed:** `templates/partials/results.html`, `templates/partials/program-list.html`

---

### ~~37. Search Source Toggle Duplicated~~ **[RESOLVED]**

Removed the hero version (`name="hero_source"`) radio buttons. The sidebar version
(`name="source"`) is the only functional one and remains.

**Files changed:** `templates/index.html`

---

### ~~38. Service/Agency Dropdown — Potentially Dozens of Entries~~ **[RESOLVED — verified 2026-04-02]**

**Root cause:** Database-level issue. Organization names need normalization.

**Fix applied:** Same fix as #3 — org normalization in `utils/normalization.py`.
**Verified:** `repair_database.py` run on production DB 2026-04-02; all org names canonical (54 distinct services, no duplicates).

---

### ~~39. Tags Dropdown — Up to 30 Options, Potentially Meaningless~~ **[RESOLVED — 2026-04-02]**

**Root cause:** Enrichment pipeline over-tags (issue #27).

**Fix applied:** Added `min_confidence` (default 0.85) and `max_coverage` (default 0.5) query parameters to `list_tags()` in `api/routes/pe.py`. Tags with low confidence or covering >50% of PEs are now filtered out by default. Parameters are adjustable per request.

---

### ~~40. Programs Page — No Pagination, Only Shows 25 Items~~ **[RESOLVED]**

Both `/programs` and `/partials/program-list` routes now parse `limit` (10-100) and
`offset` from query params. The "Refine your filters" nag was replaced with a
"Showing X of Y programs." message.

**Files changed:** `api/routes/frontend.py`, `templates/partials/program-list.html`

---

### ~~41. Program Cards — No Funding Preview~~ **[RESOLVED]**

Cards now show `FY26: $X,XXXK` when `item.total_fy2026_request` is available.

**Files changed:** `templates/partials/program-list.html`

---

### ~~42. Charts Page — Service Multi-Select Has Hardcoded Height~~ **[RESOLVED]**

Replaced `height:80px` with `min-height:2.5rem;max-height:150px` for auto-sizing.

**Files changed:** `templates/charts.html`

---

### ~~43. Compare Link Points to Wrong URL~~ **[RESOLVED]**

Changed `href="/spruill"` to `href="/compare"`.

**Files changed:** `templates/partials/program-list.html`

---

### ~~44. Treemap Labels — Hardcoded White Text Color~~ **[RESOLVED]**

Now reads `--text-on-primary` CSS variable with `#fff` fallback.

**Files changed:** `static/js/charts.js`

---

### ~~45. Dashboard — Data Freshness Not Displayed~~ **[RESOLVED]**

Added "Last Updated" stat card that reads `data.freshness.last_build` from API.

**Files changed:** `templates/dashboard.html`, `static/js/dashboard.js`

---

### ~~46. Download Modal — Hardcoded 50,000 Row Limit Text~~ **[RESOLVED]**

Now shows "Your filters match X rows. Downloads include all matching rows (up to
50,000)." using the `total` template variable.

**Files changed:** `templates/index.html`

---

### ~~47. Glossary — Hardcoded FY Example~~ **[RESOLVED]**

Changed to timeless "e.g., FY20XX runs Oct 20XX-1 through Sep 20XX".

**Files changed:** `templates/partials/glossary.html`

---

### ~~48. Amount Range Filter — No FY Column Selector~~ **[RESOLVED]**

Added `<select name="amount_column">` dropdown that iterates
`fiscal_year_columns` (now dynamically built from `get_amount_columns()`).
`validate_amount_column()` now uses regex pattern instead of static whitelist.

**Files changed:** `templates/index.html`, `utils/query.py`, `api/routes/frontend.py`
**Test coverage:** `tests/test_shared_group/test_dynamic_fy_columns.py`

---

### 49. Excessive Inline Styles Throughout Templates **[RESOLVED — 2026-04-02]**

Added 60+ utility CSS classes to `static/css/main.css` and converted inline styles
across all 21 template files. Inline style count reduced from **301 to 87** (71% reduction across three passes: 301->169->125->87).
Remaining 87 are JS-toggled display states (24), Jinja conditionals (7), and
component-specific combos that resist extraction (absolute positioning, conditional
colors, non-standard margin combos).

---

### ~~50. FY Tooltip Hardcoded to "FY2026"~~ **[RESOLVED]**

Changed to "FY20XX = Oct 20XX-1 – Sep 20XX" — generic, timeless.

**Files changed:** `templates/index.html`

---

## Round 3 — Data Quality Audit & Future Directions (2026-02-26)

Findings from database investigation and consolidated view development. These are
not UI bugs — they are data pipeline gaps and architecture issues to address in
future sprints.

### Data Quality Issues

#### ~~51. Project-Level Tags Are Empty (0 tags)~~ **[RESOLVED — Pipeline]**

Root cause identified and fixed: `detect_project_boundaries()` in
`utils/pdf_sections.py` only handled explicit `"Project: 1234"` / `"Project Number:
1234"` markers, but actual DoD R-2A exhibits use numeric project codes like:

- `671810 / B-52 AEHF INTEGRATION` — modern R-2A format (project number / TITLE)
- `675144: GLOBAL HAWK` — older R-2A format (project number: TITLE)
- `PE 0101113F / B-52 Squadrons  671810 / B-52 AEHF INTEGRATION` — page-header
  artifact containing the project number

Three new patterns were added to `_PROJECT_BOUNDARY_PATTERNS`:
1. `r"^(\d{4,7})\s*/\s*([A-Z][A-Z0-9 \-&,()/.]{3,})$"` — R-2A slash format
2. `r"PE\s+\w+\s*/\s*[^\n]+?\s+(\d{4,7})\s*/\s*([^\n]+?)"` — page-header artifact
3. `r"^(\d{4,7})\s*:\s*([A-Z][A-Z0-9 \-&,()/.]{3,})$"` — older colon format

The uppercase-title constraint on patterns 1 and 3 prevents false positives on
numeric ratios like "2024 / 2025" or monetary amounts.

With these patterns in place, Phase 5 will now correctly populate
`project_descriptions.project_number` for R-2A exhibit text, and Phase 3 will
produce project-level `pe_tags` rows on the next pipeline run.

**Files changed:** `utils/pdf_sections.py`
**Test coverage:** `tests/test_pipeline_group/test_project_decomposition.py::TestDetectProjectBoundariesR2A` (6 cases)

---

#### ~~52. Detail Rows Have NULL budget_type Despite Valid appropriation_code~~ **[RESOLVED — Round 4 + 2026-04-02]**

_Resolved in Round 4 via `scripts/fix_budget_types.py` migration. Additionally fixed
at ingestion time (2026-04-02): `pipeline/builder.py` now derives budget_type from
`_APPROP_TO_BUDGET_TYPE` when exhibit type mapping is missing. See Round 4 entry below._

---

#### 53. 66.3% of budget_lines Have No PE Number **[STRUCTURAL — documented in PRD §9]**

33,854 of 51,053 rows (66.3%) have NULL `pe_number`. Two backfill passes recovered 2,700 rows
(was 36,554 post-dedup, 83,497 of 124,670 pre-dedup).

**Detailed breakdown by exhibit type (2026-04-02):**

| Exhibit | Total | Has PE | % | Status |
|---------|-------|--------|---|--------|
| R-1 (RDT&E) | 16,286 | 16,006 | 98.3% | Solved. 280 remaining: classified (9999999999), footnotes, non-standard suffixes (BTA, OTE). |
| P-1 (Procurement) | 14,720 | 348 | 2.4% | **Uses BLIs, not PEs.** Only ~120 recoverable via title+org match against pe_index. See below. |
| C-1 (MilCon) | 8,659 | 18 | 0.2% | Structural — no PE in source documents. |
| O-1 (O&M) | 4,447 | 3 | 0.1% | Structural — no PE in source documents. |
| P-1R (Reserve Proc) | 3,939 | 51 | 1.3% | Same as P-1 — uses BLIs. |
| Amendment | 2,082 | 662 | 31.8% | Partial — cross-reference recovers some. |
| OGSI | 467 | 111 | 23.8% | Partial — cross-reference recovers some. |
| RF-1 (Revolving) | 383 | 0 | 0.0% | Structural — no PE in source documents. |
| M-1 (MilPers) | 70 | 0 | 0.0% | Structural — no PE in source documents. |

**Why P-1 procurement rows lack PEs — the BLI/PE identifier mismatch:**

Procurement exhibits (P-1, P-1R) use **Budget Line Items (BLIs)** — a separate identifier
system from the **Program Elements (PEs)** used in RDT&E. BLIs identify specific
procurement items (e.g., "CTG, 5.56mm, All Types", "AN/TPS-80 G/ATOR") while PEs
identify research programs. The DoD maps BLIs to PEs in P-5 detail exhibits, but:
- 720 P-5 PDF files exist in the corpus but contain no structured Excel data
- Only 10 distinct PEs were extracted from P-5 PDF text
- 1,702 distinct P-1 titles have no PE match (ammunition, equipment, modifications)

**Future work:** Build a BLI-based enrichment/tagging pipeline parallel to the PE
system. This would allow procurement items to be tagged and explored without requiring
a PE number. The P-5 PDF text could also be parsed more aggressively to extract
BLI→PE mappings from the structured header text that appears on each page.

---

#### ~~54. Keyword Taxonomy May Be Too Restrictive (41 terms)~~ **[RESOLVED — Pipeline]**

Added `_TAXONOMY_TIER2` in `pipeline/enricher.py` with 14 new domain tags at
lower confidence (0.7 budget_lines / 0.65 PDF narrative):

`jadc2`, `sigint` (SIGINT/ELINT/COMINT/MASINT), `geoint`, `pnt` (GPS/GNSS),
`iads`, `information-warfare`, `strategic-mobility` (airlift/tanker/refueling),
`amphibious`, `force-protection`, `readiness`, `emp`, `cbrn` (CBRNE),
`counter-intelligence`, `kill-chain`.

Tier-1 taxonomy confidence unchanged (0.9/0.8). Tier-2 tags use 0.7/0.65 to
reflect broader, lower-signal patterns. `run_phase3()` loops over both tiers;
project-level tagging also uses both.

**Files changed:** `pipeline/enricher.py`
**Test coverage:** `tests/test_pipeline_group/test_enrich_budget_db.py::TestHelpers` (15 new cases including confidence-level assertion)

---

#### ~~55. 12 PEs Without Mission Descriptions~~ **[RESOLVED — 2026-04-02]**

Added fallback in `pipeline/enricher.py` Phase 2: PEs with no PDF-derived descriptions
now get descriptions synthesized from their budget_lines data (line_item_title,
budget_activity_title, appropriation_title). Stored with `section_header='Budget Line Title'`
and `source_file='budget_lines'` to distinguish from PDF-sourced descriptions.

---

#### ~~56. Fiscal Year Gaps in PE Funding Matrices~~ **[RESOLVED — 2026-04-02]**

**Root cause:** The builder excluded all `*_display.xlsx` files, but FY2026 (and FY2012)
only published display variants on the Comptroller site — no base Excel files exist.
Only `c1.xlsx` was ingested for FY2026, yielding 581 rows vs ~3,000+ for other years.

**Fix:** Modified display-file exclusion logic in `pipeline/builder.py` to only exclude
`_display` files when a corresponding base file exists in the same directory. Display
files without a base file are now kept and ingested.

**Result:** FY2026 rows: 581 → 3,094. `amount_fy2026_request` non-zero: 98 → 2,097.
FY2012 also gained D8Z PE data from its display files. Total DB: 47,531 → 51,053 rows.

**Files changed:** `pipeline/builder.py` (display-file exclusion logic, ~line 2451)

---

#### ~~57. appropriation_code NULL Rows~~ **[RESOLVED — Round 5 Partial]**

_Resolved in Round 5 via `repair_database.py` enhanced keyword matching. NULL
appropriation_code reduced from 21,831 (17.5%) to 3,531 (7.4%). Remaining NULLs
lack sufficient context to infer. See Round 5 entry below._

---

### Performance Issues

#### ~~58. Missing Composite Database Indexes~~ **[RESOLVED — Round 4]**

_Resolved in Round 4: 4 composite indexes added. See Round 4 entry below._

---

#### ~~59. TTL Cache Too Short for Production (300s)~~ **[RESOLVED — Round 4]**

_Resolved in Round 4: Dashboard cache 300→900s, aggregation 300→600s. See Round 4 entry below._

---

#### ~~60. FTS Queries With Large Result Sets~~ **[RESOLVED]**

Added `_FTS_SCAN_LIMIT = 10_000` constant and bounded FTS subqueries in
`api/routes/search.py` (`_budget_select`, `_pdf_select`, `_description_select`).

- Unfiltered relevance queries use `ORDER BY rank LIMIT offset+limit`, enabling
  FTS5's early-termination optimiser path so only the needed rows are scored.
- Filtered or amount-sorted queries use `LIMIT _FTS_SCAN_LIMIT` to cap
  materialisation while still covering typical paginated access patterns.

**Files changed:** `api/routes/search.py`
**Test coverage:** `tests/test_web_group/test_search_endpoint.py::TestFtsScanLimit` (7 cases)

---

#### ~~61. Full Table Scans for Aggregation Queries~~ **[RESOLVED — Perf]**

Two improvements applied:

1. **Hierarchy endpoint — hardcoded FY columns removed.** `api/routes/aggregations.py`
   `/hierarchy` previously hardcoded `fy2026_request` / `fy2025_enacted` as its
   primary and prior columns. It now uses `amount_cols[-1]` (latest column from schema
   introspection) and `amount_cols[-2]` as the prior column — consistent with the main
   aggregation endpoint. This means the treemap stays correct when FY2027+ data is
   added without any code change.

2. **Startup cache warmup (OPT-AGG-002).** A `warm_caches(db_path)` function was
   added to `api/routes/aggregations.py`. It pre-populates the TTL caches for the four
   most common no-filter group keys (`service`, `fiscal_year`, `budget_type`,
   `exhibit_type`) plus the hierarchy endpoint by running queries at startup time in
   a background daemon thread (via `api/app.py` lifespan). This eliminates cold-cache
   full-table scans on the first real request after startup.

Note: TTL caches for aggregations (600s) and dashboard (900s) were already in place
from prior work; composite indexes were added in #58. After Round 5 deduplication
the table is 47,531 rows (down from 124K), so all queries are fast.

**Files changed:** `api/routes/aggregations.py`, `api/app.py`
**Test coverage:** `tests/test_web_group/test_reference_aggregation.py::TestHierarchyDynamicColumns` (8 cases),
`::TestWarmCaches` (3 cases)

---

### Future Directions (No Code Changes Yet)

#### Programs Tab Evolution: Weapon System Grouping

The Programs page should evolve to group PEs by weapon system or major program
(e.g., "B-52" would show its RDT&E PE, Procurement PE, O&M PE, and MilPers PE
together). This is the path toward a "Spruill chart" showing total cost of
ownership across all appropriation types.

**Data requirements:**
- New `program_groups` + `pe_group_membership` tables
- Initial mapping: manual curation for top 20-50 weapon systems
- Future: LLM-assisted classification, fuzzy title matching

---

#### Search Results: Funding Timeline View

Add a "Timeline View" toggle to search results on `/` that replaces the tabular
amount columns with horizontal funding bars per row. The amount data already
exists in `data-raw` attributes — a client-side sparkline renderer can build
mini bar charts without API changes.

---

#### Sub-PE Programs in Tag-Search View

When `/programs?tag=X` matches project-level tags (once they exist), expand PE
cards to show which sub-projects matched with badges linking to
`/consolidated/{pe}#project-{projNum}`.

---

## Round 4 — Tag Coverage Assessment & Fixes (2026-02-26)

### ~~52. budget_type NULL Rows~~ **[RESOLVED]**

Created `scripts/fix_budget_types.py` migration that backfills budget_type from
appropriation_code. 2,161 rows fixed. Also added post-ingestion step in
`pipeline/builder.py`. 388 rows remain NULL (no appropriation_code to derive from).

---

### ~~58. Missing Composite Indexes~~ **[RESOLVED]**

Added 4 composite indexes via migration script and pipeline:
`idx_bl_org_fy`, `idx_bl_bt_fy`, `idx_bl_et_fy`, `idx_bl_pe_fy`.
Also runs ANALYZE for query planner optimization.

---

### ~~59. TTL Cache Too Short~~ **[RESOLVED]**

Dashboard cache: 300 -> 900 seconds. Aggregation cache: 300 -> 600 seconds.

---

### 62. Tag Coverage Assessment **[DOCUMENTED]**

Assessment of PE-level tagging quality (2026-02-26):

| Metric | Value |
|--------|-------|
| Total PEs in pe_index | 3,442 |
| PEs with at least 1 tag | 3,357 (97.5%) |
| Keyword tags | 39,059 (across 3,340 PEs, 34 unique tags) |
| Structured tags | 4,140 (across 1,498 PEs, 12 unique tags) |
| Classification tags (rdte, procurement, etc.) | 1,477 (3.4% of total) |
| Discovery tags (keyword/domain) | 41,722 (96.6%) |
| Project-level tags | **25,149** (fixed 2026-04-02 via Phase 6) |
| Average tags per PE | ~12.6 |

**Tag quality assessment:**
- Classification tags (rdte, procurement, om, milpers) are 3.4% of total — this is
  acceptable; they serve as budget category markers, not the main discovery mechanism.
- Top discovery tags: communications (2,679), aviation (2,521), training (2,499),
  space (2,275), logistics (2,242), missile (2,169). These cover 60-78% of PEs each.
- The high-coverage tags (communications at 78%) are still meaningful for defense
  budget context — most programs involve some communications component.
- Lower-coverage tags are more selective: autonomy (987, 29%), directed-energy (814,
  24%), special-operations (761, 22%), hypersonics (506, 15%).
- **Project-level tags: 25,149** — fixed via enricher Phase 6 (2026-04-02). Phase 3 ran before Phase 5 could populate `project_descriptions`, so project-level tagging never executed. Phase 6 now runs after Phase 5 and applies taxonomy to project-level text (including 23,877 tags on numeric R-2A project numbers).

**Related programs (PE lineage):**
- Total links: 783,845
- explicit_pe_ref: 773,974 (confidence 0.95)
- name_match: 9,871 (confidence 0.60)
- With confidence >= 0.8: 773,974 (only explicit refs survive)
- The 773K explicit links is high — suggests many cross-references in budget docs.
  The 0.8 threshold effectively filters to explicit PE references only.

**Recommendation:** No immediate changes needed for PE-level tags. The pipeline
produces reasonable coverage with meaningful domain-specific tags. The main gap
is project-level tags (#51) which requires pipeline debugging.

---

## Round 5 — Database Data Quality Fixes (2026-02-27)

9-step migration (`scripts/fix_data_quality.py`) plus pipeline hardening to address
duplicate rows, NULL fields, and reference table noise.

### ~~5. "By Appropriation Type" donut — all "Unknown"~~ **[RESOLVED]**

Budget type backfill expanded: added DHP to O&M and AMMO to Procurement mappings in
`scripts/fix_budget_types.py`; exact title mapping added in `repair_database.py`.
NULL budget_type reduced from 388 to 116.

---

### ~~6/14. "Budget by Service" — large "Unknown" bucket~~ **[RESOLVED]**

Empty `organization_name` rows (311) filled via source-file path inference in
migration step 5. Empty organization count: 311 to 0.

---

### ~~7/17/22. Duplicate/repetitive results~~ **[RESOLVED]**

Cross-file deduplication added to `pipeline/builder.py` (excludes `*a.xlsx` amendment
files when base file exists) plus migration step 1 dedup by
`(pe_number, line_item, fiscal_year, organization, exhibit_type, source_file)`.
Total rows: 124,670 to 47,531 (62% reduction). Cross-file duplicates: 28,276+ to 0.

---

### ~~57. appropriation_code NULL rows~~ **[RESOLVED — Partial]**

Enhanced keyword matching in `repair_database.py` with broader appropriation patterns.
NULL appropriation_code reduced from 21,831 (17.5%) to 3,531 (7.4%). Remaining NULLs
are rows without enough context to infer an appropriation code.

---

### 63. Footnote entries in appropriation_titles reference table **[RESOLVED]**

`pipeline/backfill.py` modified to filter footnote-like entries from the
`appropriation_titles` query. Cleaned 31 footnote rows; title count: 256 to 225.

---

### Round 5 Files Changed

| File | Change |
|------|--------|
| `scripts/fix_data_quality.py` | New — 9-step migration (steps 0-8) |
| `pipeline/builder.py` | `*a.xlsx` exclusion + cross-file dedup logic |
| `repair_database.py` | Enhanced appropriation keyword matching + exact title mapping |
| `scripts/fix_budget_types.py` | Added DHP to O&M, AMMO to Procurement |
| `pipeline/backfill.py` | Footnote filtering in appropriation_titles query |
| `tests/test_pipeline_group/test_data_quality_fixes.py` | New — 34 tests |

### Round 5 Results Summary

| Metric | Before | After |
|--------|--------|-------|
| Total rows | 124,670 | 47,531 (62% reduction) |
| Cross-file duplicates | 28,276+ | 0 |
| NULL appropriation_code | 21,831 (17.5%) | 3,531 (7.4%) |
| NULL budget_type | 388 | 116 |
| Empty organization_name | 311 | 0 |
| Footnote entries in ref table | 31 | 0 |
| Appropriation titles | 256 | 225 (clean) |

---

## Summary

| Status | Count | Issues |
|--------|-------|--------|
| **RESOLVED** | 57 | #1-4, #5, #6/14, #7/17/22, #9-13, #15, #18-21, #23, #25-27, #29-48, #50-52, #54-61, #63 |
| **STRUCTURAL — documented in PRD §9** | 5 | #8, #16, #24, #28, #53 (data coverage limitations) |
| **DOCUMENTED** | 1 | #62 (tag coverage assessment) |
| **RESOLVED (partial)** | 1 | #49 (inline styles — 301→87, 71% reduction; remainder is JS-toggled/Jinja/structural) |

### Infrastructure Added to Prevent Regression

- `validate_amount_column()` uses regex `^amount_fy\d{4}_[a-z]+$` — prevents SQL injection while accepting any valid FY column
- `get_amount_columns(conn)` discovers columns from DB schema at runtime — no manual update needed when new FY data is added
- `make_fiscal_year_column_labels()` builds human-readable labels from column names
- `BUDGET_TYPE_CASE_EXPR` in `utils/database.py` — shared CASE expression for deriving budget_type from appropriation_code, used by dashboard and aggregations
- `tests/test_shared_group/test_dynamic_fy_columns.py` — 32-case test suite covering regex validation, label generation, and WHERE clause building with dynamic columns
- All template FY rendering uses `{% for %}` loops over dynamic data — no hardcoded FY references remain in Round 2 scope
