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

## Likely Root Causes to Investigate

- **Database: fiscal_year column** — possibly not populated, or stored in wrong format
- **Database: appropriation column** — likely not populated (explains empty dropdown + "Unknown" charts)
- **Database: service column** — inconsistent values (abbreviations vs full names)
- **Database: duplicate rows** — same program appearing multiple times per FY
- **Database: PE numbers** — not being linked to budget lines
- **Frontend: exhibit type labels** — showing raw codes instead of display names
- **Frontend: tags dropdown CSS** — positioning/z-index issue
- **Frontend: "FYFY" prefix** — string concatenation bug
- **Data pipeline: FY 2000-2009** — possibly never ingested, or ingested incorrectly
