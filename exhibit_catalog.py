"""
Exhibit Type Catalog — Step 1.B1

Comprehensive catalog of every DoD budget exhibit type, documenting the column
layout and semantics for each.  This module serves as the single source of truth
for how each exhibit's spreadsheet is structured, what columns to expect, and
how to map them to our canonical data model.

Current state:
    build_budget_db.py has EXHIBIT_TYPES with 7 entries (M-1, O-1, P-1, P-1R,
    R-1, RF-1, C-1) and a _map_columns() function that handles common patterns.
    This is incomplete — many sub-exhibit types (P-5, R-2, R-3, R-4, J-Books,
    etc.) are not explicitly cataloged.

──────────────────────────────────────────────────────────────────────────────
TODOs — each is an independent task unless noted otherwise
──────────────────────────────────────────────────────────────────────────────

TODO 1.B1-a: Inventory all exhibit types found in downloaded files.
    Approach: Write a script that walks DoD_Budget_Documents/, opens every .xlsx
    file, reads sheet names and header rows, and emits a report of unique
    (filename_pattern, sheet_name, header_signature) tuples.  Output to
    exhibit_audit_report.txt.  This tells us exactly what we have to parse.
    Token-efficient tip: A standalone 40-line script; no external state needed.

TODO 1.B1-b: Document column layouts for summary exhibits (P-1, R-1, O-1, M-1).
    For each, record: column header text, column position, data type (text,
    currency, quantity), fiscal-year association, and notes on known variations
    across services.  Store as a dict-of-dicts in this file so other modules
    can import it.

TODO 1.B1-c: Document column layouts for detail exhibits (P-5, R-2, R-3, R-4).
    Same structure as TODO 1.B1-b.  These exhibits have deeper line-item
    breakdowns and narrative justification columns.
    Dependency: requires TODO 1.B1-a output to know which detail exhibits exist
    in the downloaded corpus.

TODO 1.B1-d: Document column layouts for C-1 (MilCon) and RF-1 (Revolving Fund).
    C-1 has authorization/appropriation amount columns instead of the standard
    request/enacted pattern.  RF-1 has unique revenue/expense columns.

TODO 1.B1-e: Document column layouts for any remaining/unusual exhibit types
    found by the audit in TODO 1.B1-a (e.g., J-Books, budget amendments,
    supplemental request exhibits).

TODO 1.B1-f: Build EXHIBIT_CATALOG dict mapping exhibit_type_key →
    { "name", "description", "column_spec": [...], "known_variations": [...] }.
    Export it so build_budget_db.py can import and use it in _map_columns().
"""

# Placeholder — will be populated by TODO 1.B1-b through 1.B1-e

EXHIBIT_CATALOG = {
    # Example structure (to be filled in):
    #
    # "p1": {
    #     "name": "Procurement (P-1)",
    #     "description": "Summary procurement budget exhibit",
    #     "column_spec": [
    #         {"field": "account", "header_patterns": ["Account"], "dtype": "text"},
    #         {"field": "amount_fy2026_request", "header_patterns": ["FY 2026 Request"],
    #          "dtype": "currency_thousands"},
    #         ...
    #     ],
    #     "known_variations": [
    #         "Navy P-1 uses 'PE/BLI' instead of 'Budget Line Item'",
    #     ],
    # },
}
