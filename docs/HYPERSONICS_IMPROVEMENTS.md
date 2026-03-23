# Hypersonics Page Improvements

Planned changes discussed 2026-03-22.

## 1. Collapsible PE → Sub-element Hierarchy

- Group rows by PE number: PE is a parent row, sub-elements are indented children
- PE parent row is always visible as context (no auto-totaling of parent)
- Show/Total checkboxes on parent control group visibility (toggling parent "show" off hides entire group)
- Individual sub-elements have their own independent Show/Total checkboxes
- User selectively enables show/total on only the hypersonics-relevant sub-elements

## 2. Column Sorting

- Click any column header to sort ascending/descending
- Applies to all columns (PE number, service, exhibit, line item, FY amounts, etc.)

## 3. Description Text Per Line Item

- Surface pe_descriptions text for each row to help assess hypersonics relevance
- Expandable tooltip or drawer — not a new column of raw text

## 4. Keyword Hit Indicators (Inline)

- Show which search terms matched for each row
- Display as inline tags/badges on the line item name, or tooltip on hover
- No additional columns

## 5. Budget Activity Deduplication

- Normalize budget activity titles (case, punctuation: "&" vs "And", etc.)
- Roll up to BA 1–9 totals instead of showing near-duplicate rows in the totals section

## 6. Materialized Hypersonics Table

- Pre-compute hypersonics PE set (or full pivoted data) in a dedicated SQLite table
- Populate during pipeline/enrichment step (`enrich_budget_db.py`)
- Eliminates the ~20s cold-cache LIKE scan on pe_descriptions at query time
