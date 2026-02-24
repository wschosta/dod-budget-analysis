# Noticed Issues — 2026-02-24

Issues observed during manual review of the DoD Budget Explorer UI (localhost:8000).
Not yet triaged as bugs vs data issues — this is the investigation list.

## Search Page (/)

1. **Fiscal Year dropdown — empty** (0 options, won't open)
2. **Appropriation dropdown — empty** (0 options, won't open)
3. **Service/Agency — duplicates** (AF/Air Force, ARMY/Army, NAVY/Navy — 57 total entries)
4. **Exhibit Type — bad labels** (showing `c1 — c1` instead of readable names like "C-1")
5. **"By Appropriation Type" donut chart — all "Unknown"** (single $6B slice)
6. **"Budget by Service" bar chart — large "Unknown" bucket** ($665M)
7. **Duplicate/repetitive search results** — programs like "Conventional Munitions Demilitarization" and "Conventional Prompt Strike Test Facility" each appear multiple times instead of as single consolidated entries
8. **Missing PE numbers** — those same programs should have PE#s but show "—"

## Detail View (from search results)

9. **Detail tab is very slow** to load when clicking a search result
10. **Detail tab data errors (CPS example):**
    - Shows FY 1998 — incorrect, program didn't exist then
    - Appropriation shows "- -" (meaningless)
    - Source file path says "FY1998\PB\Defense_wide..." — wrong
    - Related Fiscal Years shows "FYFY 1998" — duplicated prefix typo

## Dashboard (/dashboard)

11. **Dashboard page — extremely slow to load**
12. **Summary cards show "— —"** for FY2026 Total Request, FY2025 Enacted, and YOY Change
13. **"By Appropriation" — "No appropriation data available"**
14. **"Budget by Service" chart** — bars near zero ($0-$1M range), "Unknown" is top entry
15. **"Top 10 Programs by FY2026 Request" — completely empty**

## Charts (/charts)

16. **YOY chart confirms data gap** — bars only at FY 1998 and FY 2025-2026, nothing for FY 2000-2024
17. **Top 10 has duplicates** — "Classified Programs" x4, "Private Sector Care" x2, "Ship Depot Maintenance" x2
18. **Defaults to FY 1998** — should probably default to most recent year
19. **Selecting FY 2012 shows blank** (no data for that year)
20. **Service dropdown has same duplicates** (ARMY/Army, AF/Air Force, NAVY/Navy)
21. **Appropriation Breakdown donut is 100% "Unknown"**

## Programs (/programs)

22. **Duplicate FY entries** — e.g., FY 2012 appears 8 times for B-52 Squadrons
23. **Missing FY columns** — no columns for FY 1998-2023
24. **FY 2000-2011 have zero entries** despite data supposedly existing
25. **FY24 Actual data incorrectly attributed** to FY 1998 source
26. **Tags dropdown is mispositioned** — overlaps onto the program cards
27. **Tag counts look inflated** — rdte: 1539/1579, communications: 1502, aviation: 1438 (nearly every program tagged with nearly everything)

## Footer (all pages)

28. **Data sources FY gap** — shows FY 1998, 1999, then jumps to 2010-2026 (missing FY 2000-2009)

## Root Cause Analysis (investigated 2026-02-24)

### Database Issues (root cause for ~80% of problems)

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

### Frontend Issues

| Issues | Root Cause | Details |
|--------|-----------|---------|
| #4 (exhibit "c1 — c1") | **Fallback code in `frontend.py:136-140`** | When `exhibit_types` reference table is missing, fallback sets `display_name = code`, producing "c1 — c1". |
| #10 ("FYFY 1998") | **Template prepends "FY"** | `results.html:22` and `detail.html` prepend "FY" to values that already contain "FY" prefix in the database. |
| #9, #11 (slow detail/dashboard) | **No indexes on filter columns** | 644K rows without proper indexes on fiscal_year, organization, etc. (DB issue amplified by frontend). |
| #26 (tags dropdown mispositioned) | **CSS overflow/z-index** | Filter panel clipping the absolutely-positioned dropdown. |
| #18 (defaults to FY 1998) | **Sort order** | Charts page defaults to first FY in sorted list instead of most recent. |

### Priority Assessment

**High priority (blocking usability):**
- Missing reference tables (#1, #2, #4) — easy frontend/DB fix
- Service name normalization (#3) — needs DB migration or view
- Appropriation codes not parsed (#5, #13, #21) — ingestion pipeline fix

**Medium priority (data quality):**
- Duplicate rows (#7, #17, #22) — needs dedup strategy
- Missing PE numbers (#8) — 73% gap is significant
- FY data gap 2000-2009 (#16) — need to acquire and ingest
- Over-tagging (#27) — enrichment pipeline tuning

**Low priority (cosmetic/UX):**
- "FYFY" prefix (#10) — simple template fix
- Tags dropdown CSS (#26) — CSS fix
- Default to latest FY (#18) — JS fix
