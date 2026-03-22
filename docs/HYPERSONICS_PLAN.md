# Hypersonics PE Lines View — Implementation Plan

## Goal
Add a `/hypersonics` page to the existing tool that shows a single, flat table of
every budget line and sub-program related to hypersonics, covering FY2015 onwards.
No charts. Just the table plus a CSV download.

---

## What We're Building

### 1. New API route file: `api/routes/hypersonics.py`
Two endpoints:
- `GET /api/v1/hypersonics` — JSON, returns paginated rows matching hypersonics keywords
- `GET /api/v1/hypersonics/download` — streaming CSV of all matching rows

### 2. New frontend HTML route (added to `api/routes/frontend.py`)
- `GET /hypersonics` — server-rendered HTML page, queries DB directly, renders template

### 3. New template: `templates/hypersonics.html`
Extends `base.html`. Contains:
- A filter bar (fiscal year from/to, service/org, exhibit type)
- Row count + "Download CSV" button
- A flat, sortable HTML table (no JS charts)
- All matching rows including sub-elements, sorted by pe_number → fiscal_year → exhibit_type

### 4. Register the new API router in `api/app.py`

### 5. Add "Hypersonics" nav link in `templates/base.html`

### 6. Update `docs/PRD.md`

---

## Keyword Search Strategy

The query filters budget_lines on:
```sql
WHERE (
    line_item_title LIKE '%hypersonic%'
    OR account_title LIKE '%hypersonic%'
    OR budget_activity_title LIKE '%hypersonic%'
    OR line_item_title LIKE '%ARRW%'
    OR line_item_title LIKE '%LRHW%'
    OR line_item_title LIKE '%C-HGB%'
    OR line_item_title LIKE '%CHGB%'
    OR line_item_title LIKE '%glide body%'
    OR line_item_title LIKE '%scramjet%'
    OR line_item_title LIKE '%HACM%'
    OR line_item_title LIKE '%HCSW%'
    OR line_item_title LIKE '%AGM-183%'
)
AND fiscal_year >= 'FY 2015'
```
- `fiscal_year` in the DB is stored as "FY YYYY" (e.g., "FY 2025") — `>= 'FY 2015'` works
  lexicographically since all values share the "FY " prefix.
- The search is case-insensitive via SQLite LIKE.

---

## Table Columns

| Column | Source |
|--------|--------|
| PE Number | `pe_number` |
| Service/Org | `organization_name` |
| FY (Doc Year) | `fiscal_year` |
| Exhibit Type | `exhibit_type` |
| Line Item Title | `line_item_title` |
| Budget Activity | `budget_activity_title` |
| FY2024 Actual ($K) | `amount_fy2024_actual` |
| FY2025 Enacted ($K) | `amount_fy2025_enacted` |
| FY2025 Total ($K) | `amount_fy2025_total` |
| FY2026 Request ($K) | `amount_fy2026_request` |

The display table uses these fixed columns (all present in the schema).
The CSV download includes all amount_fy* columns discovered dynamically via `get_amount_columns()`.

---

## Sorting & Filtering

- Default sort: `pe_number ASC`, then `fiscal_year ASC`, then `exhibit_type ASC`
- Filters (optional URL params, applied via GET form):
  - `fy_from` / `fy_to` — restrict fiscal year range (e.g., `fy_from=2020`)
  - `service` — substring match on `organization_name`
  - `exhibit` — exact match on `exhibit_type`
- Results are NOT paginated on the HTML page — show all rows (typically <500 for hypersonics)
  but the API endpoint supports `limit`/`offset` for programmatic use.

---

## File Changes Summary

| File | Action |
|------|--------|
| `api/routes/hypersonics.py` | **CREATE** — API JSON + CSV endpoints |
| `api/routes/frontend.py` | **MODIFY** — add `GET /hypersonics` HTML route |
| `templates/hypersonics.html` | **CREATE** — table page template |
| `api/app.py` | **MODIFY** — register `hypersonics.router` |
| `templates/base.html` | **MODIFY** — add nav link |
| `docs/PRD.md` | **MODIFY** — document new page and endpoints |
