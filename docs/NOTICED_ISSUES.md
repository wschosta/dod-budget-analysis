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

## Round 3 — Data Quality Audit & Future Directions (2026-02-26)

Findings from database investigation and consolidated view development. These are
not UI bugs — they are data pipeline gaps and architecture issues to address in
future sprints.

### Data Quality Issues

#### 51. Project-Level Tags Are Empty (0 tags) **[OPEN — Pipeline]**

Despite 412,071 `project_descriptions` records, the `pe_tags` table has **zero**
rows where `project_number IS NOT NULL`. The enricher's project-level keyword
matching (`enricher.py:985-993`) either isn't running or the taxonomy patterns
find no hits in project description text.

**Impact:** Consolidated view sub-project panels show no tags. Users see tags at
PE level but not at sub-project level.

```sql
SELECT COUNT(*) FROM pe_tags WHERE project_number IS NOT NULL;
-- Result: 0
SELECT COUNT(*) FROM project_descriptions;
-- Result: 412,071
```

**Suggested fix:** Debug the enricher Phase 3 project-level tagging loop. The
keyword regex patterns may not match the shorter, more technical project titles.
Consider adding a broader second-tier taxonomy or running LLM tagging on project
descriptions.

---

#### 52. Detail Rows Have NULL budget_type Despite Valid appropriation_code **[OPEN — DB]**

2,161 rows in `budget_lines` have `appropriation_code` populated but `budget_type`
is NULL. These are detail exhibit rows (r2, p5, amendment, ogsi). Summary rows
(p1, r1) have `budget_type` populated.

**Workaround applied:** Dashboard and aggregation endpoints now use a shared
`BUDGET_TYPE_CASE_EXPR` (`utils/database.py`) to derive budget type from
appropriation code at query time.

**Permanent fix:** Populate `budget_type` during ingestion for all rows, not just
summary exhibits.

```sql
SELECT appropriation_code, COUNT(*) FROM budget_lines
WHERE budget_type IS NULL AND appropriation_code IS NOT NULL
GROUP BY appropriation_code ORDER BY COUNT(*) DESC;
```

---

#### 53. 67% of budget_lines Have No PE Number **[OPEN — DB]**

83,497 of 124,670 rows (67%) have NULL `pe_number`. These rows cannot be enriched,
tagged, or linked to PE-centric views (Programs, Consolidated).

**Root cause:** PE numbers only appear in certain exhibit types (R-2, P-5). Summary
exhibits (R-1, P-1, O-1) and many O&M/MilPers exhibits don't include PE numbers
at the line level.

```sql
SELECT exhibit_type, COUNT(*) as cnt,
       SUM(CASE WHEN pe_number IS NULL THEN 1 ELSE 0 END) as null_pe
FROM budget_lines GROUP BY exhibit_type ORDER BY cnt DESC;
```

---

#### 54. Keyword Taxonomy May Be Too Restrictive (41 terms) **[OPEN — Pipeline]**

The domain taxonomy in `enricher.py:64-127` has 41 keyword patterns. Current tag
distribution: 39,059 keyword tags + 4,140 structured tags across 3,357 PEs (~12.9
tags/PE average).

**Potential expansion terms:** JADC2, kill-chain, integrated-air-defense, SIGINT,
ELINT, COMINT, GEOINT, PNT, GPS, EMP, CBRNE, force-protection, readiness,
mobility, airlift, tanker, refueling, amphibious, counter-intelligence,
information-warfare, cyber-operations, unmanned-systems.

**Suggested fix:** Add a second tier of tags with confidence 0.6-0.7. Consider
running LLM-based tagging (Phase 3 optional) for broader coverage.

---

#### 55. 12 PEs Without Mission Descriptions **[OPEN — Pipeline]**

```sql
SELECT pe_number FROM pe_index
WHERE pe_number NOT IN (SELECT DISTINCT pe_number FROM pe_descriptions);
-- Returns 12 PEs
```

These PEs get no keyword tags from narrative text. They rely solely on structured
tags from budget_lines fields.

---

#### 56. Fiscal Year Gaps in PE Funding Matrices **[OPEN — DB]**

Some PEs show funding for FY2025-2026 but nothing earlier, even when historical
data should exist. Requires cross-referencing `line_item_amounts` coverage per PE.

```sql
SELECT li.pe_number, MIN(a.target_fy) as fy_min, MAX(a.target_fy) as fy_max,
       COUNT(DISTINCT a.target_fy) as fy_count
FROM line_items li JOIN line_item_amounts a ON a.line_item_id = li.id
GROUP BY li.pe_number HAVING fy_count < 3 ORDER BY fy_count;
```

---

#### 57. appropriation_code NULL Rows **[OPEN — DB]**

Rows where `appropriation_code` is NULL fall through the CASE mapping and appear
as "Unknown" in budget type breakdowns.

```sql
SELECT COUNT(*) FROM budget_lines WHERE appropriation_code IS NULL;
```

---

### Performance Issues

#### 58. Missing Composite Database Indexes **[OPEN — Perf]**

No composite index on commonly co-filtered columns:
- `(pe_number, fiscal_year)` — used by PE detail, funding matrix, aggregations
- `(organization_name, fiscal_year)` — used by service-filtered queries

```sql
CREATE INDEX IF NOT EXISTS idx_bl_pe_fy ON budget_lines(pe_number, fiscal_year);
CREATE INDEX IF NOT EXISTS idx_bl_org_fy ON budget_lines(organization_name, fiscal_year);
```

---

#### 59. TTL Cache Too Short for Production (300s) **[OPEN — Perf]**

Dashboard and aggregation caches use 300-second TTL. Data rarely changes between
database rebuilds. Consider increasing to 3600s for production or invalidating on
rebuild via webhook/signal.

---

#### 60. FTS Queries With Large Result Sets **[OPEN — Perf]**

FTS5 `MATCH` returns all matches before pagination is applied. Consider using
`LIMIT` inside the FTS subquery for early termination when only the first page
is needed.

---

#### 61. Full Table Scans for Aggregation Queries **[OPEN — Perf]**

Most aggregation queries scan 124K+ rows in `budget_lines`. Consider materialized
summary tables or pre-computed aggregations for common groupings (by service, by
fiscal year, by budget type).

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
| Project-level tags | **0** (unchanged from #51) |
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
- **Project-level tags remain at 0** — this is the main gap. See #51 for details.

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
| **Round 5 RESOLVED** | 5 | #5, #6/14, #7/17/22, #57, #63 |
| **Round 4 RESOLVED** | 3 | #52, #58, #59 |
| **Round 4 DOCUMENTED** | 1 | #62 (tag assessment) |
| **Round 3 OPEN (Data)** | 5 | #51, 53-56 (pipeline/DB data quality) |
| **Round 3 OPEN (Perf)** | 2 | #60-61 (performance optimization) |
| **Round 2 RESOLVED** | 20 | #29-37, #40-48, #50 |
| **Round 2 OPEN** | 2 | #38 (service normalization — DB), #39 (tag quality — pipeline) |
| **Round 2 GRADUAL** | 1 | #49 (inline styles — ongoing) |
| **Round 1 OPEN** | 28 | #1-28 (mostly DB/pipeline root causes) |

### Infrastructure Added to Prevent Regression

- `validate_amount_column()` uses regex `^amount_fy\d{4}_[a-z]+$` — prevents SQL injection while accepting any valid FY column
- `get_amount_columns(conn)` discovers columns from DB schema at runtime — no manual update needed when new FY data is added
- `make_fiscal_year_column_labels()` builds human-readable labels from column names
- `BUDGET_TYPE_CASE_EXPR` in `utils/database.py` — shared CASE expression for deriving budget_type from appropriation_code, used by dashboard and aggregations
- `tests/test_shared_group/test_dynamic_fy_columns.py` — 32-case test suite covering regex validation, label generation, and WHERE clause building with dynamic columns
- All template FY rendering uses `{% for %}` loops over dynamic data — no hardcoded FY references remain in Round 2 scope
