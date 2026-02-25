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

1. **[OPEN]** **Fiscal Year dropdown — empty** (0 options, won't open)
2. **[OPEN]** **Appropriation dropdown — empty** (0 options, won't open)
3. **[OPEN]** **Service/Agency — duplicates** (AF/Air Force, ARMY/Army, NAVY/Navy — 57 total entries)
4. **[OPEN]** **Exhibit Type — bad labels** (showing `c1 — c1` instead of readable names like "C-1")
5. **[OPEN]** **"By Appropriation Type" donut chart — all "Unknown"** (single $6B slice)
6. **[OPEN]** **"Budget by Service" bar chart — large "Unknown" bucket** ($665M)
7. **[OPEN]** **Duplicate/repetitive search results** — programs appear multiple times instead of consolidated
8. **[OPEN]** **Missing PE numbers** — those same programs should have PE#s but show "—"

### Detail View (from search results)

9. **[OPEN]** **Detail tab is very slow** to load when clicking a search result
10. **[OPEN]** **Detail tab data errors (CPS example):**
    - Shows FY 1998 — incorrect, program didn't exist then
    - Appropriation shows "- -" (meaningless)
    - Source file path says "FY1998\PB\Defense_wide..." — wrong
    - Related Fiscal Years shows "FYFY 1998" — duplicated prefix typo

### Dashboard (/dashboard)

11. **[OPEN]** **Dashboard page — extremely slow to load**
12. **[OPEN]** **Summary cards show "— —"** for FY2026 Total Request, FY2025 Enacted, and YOY Change
13. **[OPEN]** **"By Appropriation" — "No appropriation data available"**
14. **[OPEN]** **"Budget by Service" chart** — bars near zero ($0-$1M range), "Unknown" is top entry
15. **[OPEN]** **"Top 10 Programs by FY2026 Request" — completely empty**

### Charts (/charts)

16. **[OPEN]** **YOY chart confirms data gap** — bars only at FY 1998 and FY 2025-2026, nothing for FY 2000-2024
17. **[OPEN]** **Top 10 has duplicates** — "Classified Programs" x4, "Private Sector Care" x2, "Ship Depot Maintenance" x2
18. **[OPEN]** **Defaults to FY 1998** — should probably default to most recent year
19. **[OPEN]** **Selecting FY 2012 shows blank** (no data for that year)
20. **[OPEN]** **Service dropdown has same duplicates** (ARMY/Army, AF/Air Force, NAVY/Navy)
21. **[OPEN]** **Appropriation Breakdown donut is 100% "Unknown"**

### Programs (/programs)

22. **[OPEN]** **Duplicate FY entries** — e.g., FY 2012 appears 8 times for B-52 Squadrons
23. **[OPEN]** **Missing FY columns** — no columns for FY 1998-2023
24. **[OPEN]** **FY 2000-2011 have zero entries** despite data supposedly existing
25. **[OPEN]** **FY24 Actual data incorrectly attributed** to FY 1998 source
26. **[OPEN]** **Tags dropdown is mispositioned** — overlaps onto the program cards
27. **[OPEN]** **Tag counts look inflated** — rdte: 1539/1579, communications: 1502, aviation: 1438 (nearly every program tagged with nearly everything)

### Footer (all pages)

28. **[OPEN]** **Data sources FY gap** — shows FY 1998, 1999, then jumps to 2010-2026 (missing FY 2000-2009)

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

### 38. Service/Agency Dropdown — Potentially Dozens of Entries **[OPEN]**

**Root cause:** Database-level issue. Organization names need normalization
(collapse ARMY/A → Army, etc.). This requires pipeline/DB changes, not just frontend fixes.

**Suggested fix:** Add a normalization step in the pipeline or a mapping table.

---

### 39. Tags Dropdown — Up to 30 Options, Potentially Meaningless **[OPEN]**

**Root cause:** Enrichment pipeline over-tags (issue #27). Fixing the tag quality
requires pipeline changes, not frontend changes.

**Suggested fix:** Fix enrichment selectivity, then consider filtering tags by
coverage threshold (< 50%) in the dropdown.

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

### 49. Excessive Inline Styles Throughout Templates **[OPEN — GRADUAL]**

This is an ongoing refactor to be addressed as files are touched. Not a discrete fix.

---

### ~~50. FY Tooltip Hardcoded to "FY2026"~~ **[RESOLVED]**

Changed to "FY20XX = Oct 20XX-1 – Sep 20XX" — generic, timeless.

**Files changed:** `templates/index.html`

---

## Summary

| Status | Count | Issues |
|--------|-------|--------|
| **Round 2 RESOLVED** | 20 | #29-37, #40-48, #50 |
| **Round 2 OPEN** | 2 | #38 (service normalization — DB), #39 (tag quality — pipeline) |
| **Round 2 GRADUAL** | 1 | #49 (inline styles — ongoing) |
| **Round 1 OPEN** | 28 | #1-28 (mostly DB/pipeline root causes) |

### Infrastructure Added to Prevent Regression

- `validate_amount_column()` uses regex `^amount_fy\d{4}_[a-z]+$` — prevents SQL injection while accepting any valid FY column
- `get_amount_columns(conn)` discovers columns from DB schema at runtime — no manual update needed when new FY data is added
- `make_fiscal_year_column_labels()` builds human-readable labels from column names
- `tests/test_shared_group/test_dynamic_fy_columns.py` — 32-case test suite covering regex validation, label generation, and WHERE clause building with dynamic columns
- All template FY rendering uses `{% for %}` loops over dynamic data — no hardcoded FY references remain in Round 2 scope
