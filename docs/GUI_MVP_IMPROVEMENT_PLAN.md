# GUI MVP Improvement Plan

**Date:** 2026-02-21
**Focus:** Making initial MVP functionality work as well as possible
**Scope:** Web GUI (FastAPI + Jinja2 + HTMX + Chart.js)

---

## Summary

After a thorough review of the entire GUI codebase — all 6 HTML templates, 4 JS
files, 1 CSS file, and the frontend route handler — all tracked LION/TIGER/BEAR
TODOs are complete. The application is feature-rich and well-structured. This plan
focuses on **fixing functional bugs, eliminating dead code paths, and polishing
the core user experience** for a solid MVP release.

---

## Phase 1: Fix Functional Bugs (High Priority)

### 1.1 Fix debounced multi-select filter firing (app.js)

**Problem:** The debounce handler at `app.js:456-463` sets a timeout with an
empty callback body. HTMX's `hx-trigger="change"` on the form fires immediately
for every checkbox click in the multi-select dropdowns, causing rapid duplicate
API requests when users click multiple options quickly.

**Fix:** Either (a) prevent HTMX's native change trigger on selects and manually
trigger after the debounce elapses, or (b) use `hx-trigger="change delay:300ms"`
on the form element directly (HTMX supports debounce natively). Option (b) is
simpler and more reliable.

**Files:** `templates/index.html`, `static/js/app.js`

---

### 1.2 Fix Amount Range filter column hardcoding (frontend.py)

**Problem:** The amount range filter at `frontend.py:207-222` always queries
`amount_fy2026_request` regardless of which fiscal year columns are visible.
A user filtering by FY2024 Actual amounts would get wrong results.

**Fix:** Default to filtering on the most recent request column
(`amount_fy2026_request`) but label the filter clearly to indicate which column
it operates on. Update the tooltip and label from "Amount Range ($K)" to
"FY2026 Request Range ($K)" so users know what they're filtering.

**Files:** `templates/index.html`, `api/routes/frontend.py`

---

### 1.3 Fix Source Document link in detail panel (detail.html)

**Problem:** The "Source Document" button at `detail.html:134` always links to the
generic comptroller.defense.gov landing page, not the actual source document. This
is misleading — users expect it to open the specific file.

**Fix:** Since we can't construct a direct URL to the specific budget document
from the filename alone, rename the button to "Browse DoD Budget Materials" and
style it as a secondary reference link rather than an action that implies
direct access.

**Files:** `templates/partials/detail.html`

---

### 1.4 Add empty-state notice for Programs page (frontend.py, programs.html)

**Problem:** When `pe_index` doesn't exist (user hasn't run `enrich_budget_db.py`),
the Programs page shows an empty grid with no explanation. The detail route
shows a 404 with a message, but the listing page silently shows nothing.

**Fix:** Add an informational banner when `pe_index` is missing, explaining that
program enrichment data needs to be generated. Include instructions or a link
to documentation.

**Files:** `templates/programs.html`, `api/routes/frontend.py`

---

## Phase 2: UX Polish (Medium Priority)

### 2.1 Add toast notification system

**Problem:** Several user actions (Share URL copied, feedback submitted, search
saved, download started) provide no visual confirmation. The Share button has
a CSS "Copied!" tooltip but other actions are silent.

**Fix:** Add a lightweight toast notification component — a small `<div>` stack
in the bottom-right corner that auto-dismisses after 3 seconds. Wire it up to
Share, Save, Feedback submit, and Download click events.

**Files:** `static/css/main.css`, `static/js/app.js`, `templates/base.html`

---

### 2.2 Replace prompt() for saved search names

**Problem:** The Save button uses `prompt('Name this search:')` which creates
a jarring, unstyled browser dialog that interrupts the dark-themed UI flow.

**Fix:** Replace with an inline input field that appears when the Save button
is clicked. The input appears in the sidebar with a small text box and
Save/Cancel buttons, reusing existing `.btn-sm` styling.

**Files:** `templates/index.html`, `static/js/app.js`

---

### 2.3 Fix hardcoded inline colors for dark mode compatibility

**Problem:** Several templates use hardcoded colors in inline styles that don't
adapt to dark mode:
- `color:#555` in `index.html:174` (print header — low impact since print-only)
- `color:#999` in `app.js:472` (keyboard shortcut hint)
- Various `color:var(--clr-gray-700)` in inline styles (these are OK — using vars)

**Fix:** Replace the remaining hardcoded color values with CSS custom properties:
- `app.js:472`: Use `var(--text-secondary)` instead of `#999`

**Files:** `static/js/app.js`

---

### 2.4 Add mobile filter drawer toggle

**Problem:** On mobile (< 768px), the filter sidebar stacks above results,
requiring users to scroll past all filters to see data. With 6 filter groups,
this pushes results off-screen.

**Fix:** Add a "Show/Hide Filters" toggle button that appears only on mobile.
The filter panel starts collapsed, and clicking the toggle reveals it. The
toggle button shows the count of active filters as a badge.

**Files:** `static/css/main.css`, `static/js/app.js`, `templates/index.html`

---

### 2.5 Add "back to top" button for long result sets

**Problem:** After scrolling through results on mobile, users have no quick way
to return to the top (where filters and search are).

**Fix:** Add a fixed-position "back to top" button that appears after scrolling
past 400px. Uses `window.scrollTo({ top: 0, behavior: 'smooth' })`.

**Files:** `static/css/main.css`, `static/js/app.js`, `templates/base.html`

---

## Phase 3: Code Quality (Lower Priority, Strengthens MVP)

### 3.1 Extract inline chart JavaScript from charts.html

**Problem:** `charts.html` contains ~620 lines of inline `<script>` which:
- Prevents browser caching of JS separately from HTML
- Requires `'unsafe-inline'` in the Content Security Policy
- Makes testing and debugging harder

**Fix:** Extract the chart initialization code into `static/js/charts.js`.
Update `charts.html` to load it via `{% block extra_scripts %}`. Remove
`'unsafe-inline'` from script-src CSP once all inline scripts are externalized.

**Files:** `templates/charts.html`, new `static/js/charts.js`, `api/app.py`

---

### 3.2 Clean up dead/dormant code

**Problem:** `checkbox-select.js` is loaded on every page but only initializes
on `<select multiple>` elements in filter panels. The infrastructure suggests
it was intended for results table row selection, but that integration was never
built. This is fine — the script is lightweight and correctly no-ops when no
multi-selects exist.

**Action:** No change needed — the code is correctly scoped.

---

### 3.3 Dashboard: Add fallback for missing database

**Problem:** If the database is empty or the dashboard API endpoint fails, users
see "Failed to load dashboard: HTTP 500" with no recovery guidance.

**Fix:** Show a user-friendly message suggesting they run the data pipeline first,
with links to documentation.

**Files:** `static/js/dashboard.js`

---

## Implementation Order

The recommended order maximizes impact while minimizing risk:

1. **Phase 1.1** — Fix debounce (quick, high-value UX fix)
2. **Phase 1.2** — Fix amount filter labeling (prevents confusion)
3. **Phase 1.3** — Fix source document link (prevents frustration)
4. **Phase 1.4** — Programs empty state (prevents confusion)
5. **Phase 2.1** — Toast notifications (broad UX improvement)
6. **Phase 2.2** — Save search UX (minor polish)
7. **Phase 2.3** — Dark mode color fix (minor)
8. **Phase 2.4** — Mobile filter drawer (mobile UX)
9. **Phase 2.5** — Back to top button (mobile UX)
10. **Phase 3.1** — Extract chart JS (code quality + security)
11. **Phase 3.3** — Dashboard fallback (edge case)

---

## Out of Scope (OH MY tasks)

These items require external resources and cannot be addressed autonomously:
- OH-MY-001 through OH-MY-012 (network access, cloud accounts, domain, etc.)
- Lighthouse accessibility audit (OH-MY-010) — needs running UI + browser
- Full WCAG 2.1 AA compliance audit — needs manual testing with screen readers

---

*Plan generated from codebase review of the DoD Budget Explorer web GUI.*
