# DoD Budget Analysis UI Wireframes — TODO 3.A2-a

**Format:** ASCII Art & HTML Mockups
**Technology:** HTMX + Jinja2 Templates
**Responsive:** Mobile, Tablet, Desktop

---

## 1. Landing/Search Page — Desktop View

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ DoD Budget Analysis                                    [Home] [About] [GitHub]│
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ╭─────────────────────────────────────────────────────────────────────────╮ │
│  │ Search DoD Budget Data                                                  │ │
│  │                                                                           │ │
│  │ Search Term: [____________________________________]         [Search] │ │
│  │                                                                           │ │
│  ╰─────────────────────────────────────────────────────────────────────────╯ │
│                                                                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────────────────┐  ┌──────────────────────────────────────────┐  │
│  │    FILTER SIDEBAR       │  │                                          │  │
│  ├─────────────────────────┤  │         RESULTS TABLE                    │  │
│  │ Fiscal Year:            │  ├──────────────────────────────────────────┤  │
│  │ ☑ 2025                  │  │ Service │ Program │ Amount | Exhibit     │  │
│  │ ☑ 2024                  │  ├─────────┼─────────┼────────┼─────────────┤  │
│  │ ☐ 2023                  │  │ Army    │ Fighter │  450M  │ P-1         │  │
│  │ ☐ 2022                  │  │         │ Jet XYZ │        │             │  │
│  │                         │  ├─────────┼─────────┼────────┼─────────────┤  │
│  │ Service:                │  │ Navy    │ Carrier │  2.1B  │ P-1         │  │
│  │ ☑ Army                  │  │         │ Upgrade │        │             │  │
│  │ ☑ Navy                  │  ├─────────┼─────────┼────────┼─────────────┤  │
│  │ ☑ Air Force             │  │ USAF    │ B-21    │  1.2B  │ P-1         │  │
│  │ ☑ Space Force           │  │         │ Bomber  │        │             │  │
│  │ ☐ Marine Corps          │  ├─────────┼─────────┼────────┼─────────────┤  │
│  │                         │  │ Navy    │ LCS-    │  125M  │ P-5         │  │
│  │ Exhibit Type:           │  │         │ Module  │        │             │  │
│  │ ☑ P-1 (Procurement)     │  ├─────────┼─────────┼────────┼─────────────┤  │
│  │ ☑ P-5 (Procurement Det) │  │ Army    │ M109A7  │  895M  │ P-1         │  │
│  │ ☑ R-1 (RDT&E)           │  │         │ Howitzer│        │             │  │
│  │ ☑ O-1 (O&M)             │  │ [< Prev]  Page 1 of 127   [Next >]        │  │
│  │ ☑ M-1 (Military Pers.)  │  │                                          │  │
│  │                         │  │                                          │  │
│  │ Amount Range:           │  │ [Download Results as CSV/JSON]          │  │
│  │ Min: [____] thousands   │  │                                          │  │
│  │ Max: [____] thousands   │  └──────────────────────────────────────────┘  │
│  │                         │                                                 │
│  │ [Apply Filters]         │                                                 │
│  │ [Clear All]             │                                                 │
│  └─────────────────────────┘                                                 │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Search Results with Detail Panel — Desktop View

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ DoD Budget Analysis                    Search: "fighter aircraft procurement" │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │ Results for "fighter aircraft procurement"   (1,247 results)            │ │
│  ├─────────────────────────────────────────────────────────────────────────┤ │
│  │ • F-35 Lightning II Procurement (Army/Air Force)                       │ │
│  │   ... requested $18.2B for 156 aircraft in FY2025 budget exhibit ...    │ │
│  │   [View Details]                                                        │ │
│  │                                                                           │ │
│  │ • F-15EX Eagle II Procurement (Air Force)                             │ │
│  │   ... $7.5B allocation for combat support and electronic warfare ...    │ │
│  │   [View Details]                                                        │ │
│  │                                                                           │ │
│  │ • Aircraft Procurement Program Element 0602702E (Navy)                │ │
│  │   ... RDT&E for carrier aircraft development and testing ...           │ │
│  │   [View Details]                                                        │ │
│  │                                                                           │ │
│  │ [< Previous]  Results 1-3 of 1,247  [Next >]                          │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │ DETAIL VIEW (from [View Details] click)                                │ │
│  ├─────────────────────────────────────────────────────────────────────────┤ │
│  │ F-35 Lightning II Procurement                                          │ │
│  │                                                                           │ │
│  │ Fiscal Year:           2025                                            │ │
│  │ Service:               Air Force / Marine Corps / Navy                  │ │
│  │ Program Element:       0604229F                                         │ │
│  │ Account:               2105 - Aircraft Procurement, Air Force          │ │
│  │ Appropriation:         Procurement, Air Force                         │ │
│  │ Exhibit Type:          P-1 (Procurement Summary)                       │ │
│  │                                                                           │ │
│  │ Budget Amounts (thousands of dollars):                                 │ │
│  │   Prior Year (FY2024):  $15,200,000                                   │ │
│  │   Current Year (FY2025): $18,200,000                                  │ │
│  │   % Change:             +19.7%                                         │ │
│  │                                                                           │ │
│  │ Quantity & Cost:                                                        │ │
│  │   Quantity:             156 aircraft                                    │ │
│  │   Unit Cost:            $116,667 thousands ($116.7M per unit)         │ │
│  │                                                                           │ │
│  │ Related Items:                                                          │ │
│  │   ▸ FY2024: $15,200,000                                               │ │
│  │   ▸ FY2026 (projected): $21,500,000                                   │ │
│  │                                                                           │ │
│  │ Source Document:                                                        │ │
│  │   File: Air_Force_P-1_FY2025.xlsx                                      │ │
│  │   URL: [View on DoD Comptroller]                                       │ │
│  │                                                                           │ │
│  │ [Close Detail] [Download This Item] [Show in Table]                   │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Results Table with Sorting & Column Toggle

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Budget Line Items                                    [⚙ Column Settings]    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  Column Settings Modal:                                                      │
│  ╭────────────────────────╮                                                  │
│  │ Visible Columns:       │                                                  │
│  │                        │                                                  │
│  │ ☑ Service             │                                                  │
│  │ ☑ Program Element     │                                                  │
│  │ ☑ Amount              │                                                  │
│  │ ☑ Fiscal Year         │                                                  │
│  │ ☐ Account Code        │                                                  │
│  │ ☐ Budget Activity     │                                                  │
│  │ ☐ Unit Cost           │                                                  │
│  │ ☐ Quantity            │                                                  │
│  │                        │                                                  │
│  │ [Apply] [Cancel]      │                                                  │
│  ╰────────────────────────╯                                                  │
│                                                                               │
│  Results Table:                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │Service      │Program Element│Amount (Thousands) │Fiscal Year │Exhibit│   │
│  │             │(↑ sortable)   │(↑ sortable)       │(↑ sortable)│Type   │   │
│  ├──────────────┼───────────────┼──────────────────┼────────────┼───────┤   │
│  │Army         │0602702E       │450,000           │2025        │P-1    │   │
│  ├──────────────┼───────────────┼──────────────────┼────────────┼───────┤   │
│  │Navy         │0604754N       │125,000           │2025        │P-5    │   │
│  ├──────────────┼───────────────┼──────────────────┼────────────┼───────┤   │
│  │Air Force    │0604229F       │18,200            │2025        │P-1    │   │
│  ├──────────────┼───────────────┼──────────────────┼────────────┼───────┤   │
│  │Space Force  │0604855F       │28,300            │2025        │P-1    │   │
│  ├──────────────┼───────────────┼──────────────────┼────────────┼───────┤   │
│  │Marine Corps │0604754M       │15,800            │2025        │P-1    │   │
│  └──────────────┴───────────────┴──────────────────┴────────────┴───────┘   │
│                                                                               │
│  [< Previous]  Showing 1-5 of 4,527   [Next >]                             │
│  Page size: [20 ▼]  Go to page: [  ] [Go]                                 │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Download Modal

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Download Filtered Results                                              [×]   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  Your current filters match 4,527 budget line items.                        │
│                                                                               │
│  Format Selection:                                                           │
│  ◉ CSV (Excel-compatible, best for spreadsheet analysis)                   │
│    • All columns exported                                                   │
│    • File: budget_export_2025-02-18.csv                                    │
│                                                                               │
│  ◉ JSON (Newline-delimited, best for data pipelines)                       │
│    • All fields exported                                                   │
│    • File: budget_export_2025-02-18.json                                   │
│    • Easy to import into other tools                                       │
│                                                                               │
│  ◉ Excel (.xlsx, best for reports)                                         │
│    • Multiple sheets (one per service)                                     │
│    • Pre-formatted columns                                                 │
│    • File: budget_export_2025-02-18.xlsx                                   │
│                                                                               │
│  Current Filters Applied:                                                   │
│  • Fiscal Year: 2024, 2025                                                 │
│  • Services: Army, Navy, Air Force                                         │
│  • Exhibit Type: P-1, P-5, R-1                                             │
│  • Amount Range: $100M - $2B                                               │
│                                                                               │
│  Estimated File Size: ~2.3 MB                                              │
│  Estimated Time: ~5 seconds                                                │
│                                                                               │
│  [Download as CSV]  [Download as JSON]  [Download as Excel]  [Cancel]    │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Mobile View — Phone (< 640px)

```
┌────────────────────────────┐
│ DoD Budget Analysis    [☰] │
├────────────────────────────┤
│                            │
│ [Search Budget Data...]    │
│                            │
├────────────────────────────┤
│ FILTERS                    │
├────────────────────────────┤
│ Fiscal Year:               │
│ ☑ 2025   ☑ 2024   ☐ 2023 │
│                            │
│ Service:                   │
│ ☑ Army                     │
│ ☑ Navy                     │
│ ☑ Air Force                │
│ ☐ Space Force              │
│                            │
│ Amount Range:              │
│ Min: [______] thousands    │
│ Max: [______] thousands    │
│                            │
│ [Apply] [Clear]            │
├────────────────────────────┤
│ RESULTS (4,527 items)      │
├────────────────────────────┤
│                            │
│ ► F-35 Procurement         │
│   Army, 2025, $450M        │
│   [Details]                │
│                            │
│ ► Carrier Upgrade          │
│   Navy, 2025, $2.1B        │
│   [Details]                │
│                            │
│ ► B-21 Bomber              │
│   USAF, 2025, $1.2B        │
│   [Details]                │
│                            │
│ [Load More]                │
│                            │
│ [Download Results]         │
│                            │
└────────────────────────────┘
```

---

## 6. Tablet View — Landscape (640px - 1024px)

```
┌───────────────────────────────────────────────────┐
│ DoD Budget Analysis                          [☰]  │
├───────────────────────────────────────────────────┤
│ [Search DoD Budget Data...]              [Search] │
├────────────────────────┬───────────────────────────┤
│  FILTER SIDEBAR        │  RESULTS TABLE            │
│  ────────────────────  │  ──────────────────────   │
│ Fiscal Year:           │ Showing 1-10 of 4,527    │
│ ☑ 2025  ☑ 2024         │                           │
│ ☐ 2023  ☐ 2022         │ Service  │ Program │ ... │
│                        │ ──────────┼─────────┼─────│
│ Service:               │ Army     │ 0602... │ ... │
│ ☑ Army  ☑ Navy         │ Navy     │ 0604... │ ... │
│ ☑ USAF  ☑ SpaceF       │ USAF     │ 0604... │ ... │
│                        │ SpaceF   │ 0604... │ ... │
│ Exhibit Type:          │                           │
│ ☑ P-1   ☑ P-5          │ [< Prev] Page 1  [Next>] │
│ ☑ R-1   ☑ O-1          │                           │
│                        │ [Download Results]       │
│ [Apply Filters]        │                           │
│ [Clear All]            │                           │
└────────────────────────┴───────────────────────────┘
```

---

## 7. Detail View — Full Screen

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Budget Line Item Detail                              [← Back to Results]     │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│ ╭─────────────────────────────────────────────────────────────────────────╮  │
│ │ Program Title: F-35 Lightning II Procurement                           │  │
│ │ Program Element: 0604229F                                             │  │
│ │ Service: Air Force / Marine Corps / Navy                              │  │
│ ╰─────────────────────────────────────────────────────────────────────────╯  │
│                                                                               │
│ ┌────────────────────────────────┬────────────────────────────────────────┐  │
│ │ BASIC INFORMATION              │ BUDGET DETAILS                         │  │
│ ├────────────────────────────────┼────────────────────────────────────────┤  │
│ │ Fiscal Year:      2025         │ FY2024 (Enacted):   $15,200,000       │  │
│ │ Service:          Air Force    │ FY2025 (Enacted):   $18,200,000       │  │
│ │ Account Code:     2105         │ FY2025 (Estimate):  $18,200,000       │  │
│ │ Account Title:    Aircraft     │ Change from Prior:  +19.7% ($3.0B)    │  │
│ │                   Procurement  │                                       │  │
│ │ Appropriation:    Procurement  │ QUANTITY & UNIT COST                  │  │
│ │ Budget Activity:  02           │ ├─ Quantity: 156 aircraft              │  │
│ │ Exhibit Type:     P-1          │ ├─ Unit Cost: $116.7M per aircraft    │  │
│ │ Line Item:        001          │ └─ Total: $18,200,000                 │  │
│ │                                │                                       │  │
│ │ NARRATIVE JUSTIFICATION        │ RELATED ITEMS                         │  │
│ │ ────────────────────────────   │ ────────────────────────────────────  │  │
│ │ The F-35 Lightning II is the   │ ► FY2024: $15,200,000                │  │
│ │ Department of Defense's next   │ ► FY2026 (projected): $21,500,000    │  │
│ │ generation fighter aircraft... │ ► FY2027 (projected): $23,100,000    │  │
│ │                                │                                       │  │
│ │ [Read More]                    │ SOURCE DOCUMENT                       │  │
│ └────────────────────────────────┼────────────────────────────────────────┤  │
│ │ File: Air_Force_P-1_FY2025.xlsx                                       │  │
│ │ Sheet: P-1 (Procurement)                                              │  │
│ │ Row: 42                                                               │  │
│ │ URL: https://comptroller.defense.gov/Portals/51/...                 │  │
│ │                                                                       │  │
│ │ [View Original Document] [Download This Row as JSON]                 │  │
│ └────────────────────────────────────────────────────────────────────────┘  │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Visualization Dashboard — Year-over-Year Trend

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Budget Trends                                                                 │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│ Program: Fighter Aircraft (F-35, F-15EX, F-18E/F)                           │
│                                                                               │
│     B   │ FY2024      FY2025      FY2026(est) FY2027(est)                   │
│     i   │  ________   _________   _________  ________                       │
│     l   │ │     │     │      │     │       │  │       │                    │
│     l   │ │ 15.2│─────│ 18.2 │─────│  21.5 │──│  23.1 │                   │
│     i   │ │_____|     │______|     │_______|  │_______|                    │
│     o   │                                                                    │
│     n   │  Year-over-Year Change: +19.7% (FY24→FY25), +18.1% (FY25→FY26)   │
│     s   │                                                                    │
│         │                                                                    │
│         │ Comparison by Service:                                            │
│         │                                                                    │
│         │ Air Force:    ████████████████ 12.5B (68%)                       │
│         │ Navy/USMC:    ███████████ 8.2B (44%)                             │
│         │ Army:        ██████ 4.5B (24%)                                  │
│         │                                                                    │
│         │ Total: $25.2B                                                     │
│         │                                                                    │
│ [View as Chart] [Download Data] [Share] [Print]                            │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Template Implementation Notes

### Template Files to Create

1. **base.html** — Layout with navigation, CSS/JS includes
   - Header with logo, nav links
   - Footer with copyright, links
   - Includes HTMX script from CDN
   - Includes main CSS and JS files
   - `{% block content %} {% endblock %}`

2. **index.html** — Search/filter page (extends base.html)
   - Search bar at top
   - Two-column layout: filters on left, results on right
   - Uses partials: filters.html, results.html

3. **partials/filters.html** — Filter sidebar (reusable)
   - Fiscal year checkboxes
   - Service multi-select
   - Exhibit type checkboxes
   - Amount range sliders
   - [Apply] [Clear] buttons
   - Uses `hx-get="/api/v1/results"` on filter change

4. **partials/results.html** — Results table (swapped by HTMX)
   - Table with sortable columns
   - Pagination controls
   - "Download" button
   - Each row links to detail view

5. **detail.html** — Line item detail (opened as modal/panel)
   - Full item metadata
   - Related items
   - Download link
   - Source document link

6. **partials/pagination.html** — Reusable pagination
   - "< Previous" and "Next >" links
   - Page number indicators
   - Items per page selector

### HTMX Integration Points

```html
<!-- Filter change triggers results fetch -->
<input type="checkbox" name="service" value="Army"
       hx-get="/api/v1/results"
       hx-target="#results-table"
       hx-trigger="change"
       hx-push-url="true" />

<!-- Sort column click -->
<th hx-get="/api/v1/results?sort=amount_thousands"
    hx-target="#results-table"
    hx-push-url="true">Amount ↓</th>

<!-- Detail view -->
<a href="#" hx-get="/detail/bl_12345"
   hx-target="#detail-panel"
   hx-swap="innerHTML">View Details</a>
```

---

## Responsive Design Breakpoints

| Device | Width | Layout |
|--------|-------|--------|
| Mobile | <640px | Stacked (filter, then results) |
| Tablet | 640-1024px | Two-column (filter left, results right) |
| Desktop | >1024px | Two-column (filter left, results right) |

---

## Accessibility Features

- Semantic HTML (`<label>`, `<button>`, `<form>`)
- ARIA labels for filter groups
- Keyboard navigation (Tab, Enter, Escape)
- Color contrast ≥ 4.5:1 for text
- Form labels properly associated with inputs
- Skip-to-content link
