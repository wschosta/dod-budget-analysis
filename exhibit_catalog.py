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

EXHIBIT_CATALOG = {
    "p1": {
        "name": "Procurement (P-1)",
        "description": "Summary procurement budget exhibit — funding requests for procurement of weapons, vehicles, equipment",
        "column_spec": [
            {"field": "account", "header_patterns": ["Account", "ACC"], "dtype": "text",
             "description": "Procurement account code (e.g., 2035 for Aircraft Procurement, Army)"},
            {"field": "account_title", "header_patterns": ["Account Title", "Title"], "dtype": "text",
             "description": "Full title of the procurement account"},
            {"field": "program_element", "header_patterns": ["PE", "Program Element"], "dtype": "text",
             "description": "Program Element number (7 digits + 1 letter)"},
            {"field": "appropriation", "header_patterns": ["Appropriation"], "dtype": "text",
             "description": "Appropriation category"},
            {"field": "budget_activity", "header_patterns": ["BA", "Budget Activity"], "dtype": "text",
             "description": "Budget Activity Code"},
            {"field": "prior_year_bud", "header_patterns": ["Prior Year", "PriorYBud"], "dtype": "currency_thousands",
             "description": "Prior year enacted amount in thousands of dollars"},
            {"field": "current_year_bud", "header_patterns": ["Current Year", "CurYBud"], "dtype": "currency_thousands",
             "description": "Current year enacted amount in thousands of dollars"},
            {"field": "budget_estimate", "header_patterns": ["Budget Estimate", "BudEst"], "dtype": "currency_thousands",
             "description": "President's budget estimate (request) in thousands of dollars"},
        ],
        "known_variations": [
            "Navy/USMC versions may use 'PE/BLI' header instead of separate Program Element column",
            "Army versions sometimes include 'SLI' (Sub-Line Item) designation",
            "Column order may vary by service; use header patterns for robust matching",
        ],
    },

    "r1": {
        "name": "RDT&E (R-1)",
        "description": "Research, Development, Test & Evaluation summary — funding for military technology development",
        "column_spec": [
            {"field": "account", "header_patterns": ["Account", "ACC"], "dtype": "text",
             "description": "RDT&E account code"},
            {"field": "account_title", "header_patterns": ["Account Title", "Title"], "dtype": "text",
             "description": "Full account title"},
            {"field": "program_element", "header_patterns": ["PE", "Program Element"], "dtype": "text",
             "description": "Program Element number"},
            {"field": "appropriation", "header_patterns": ["Appropriation"], "dtype": "text",
             "description": "Appropriation category (RDT&E)"},
            {"field": "budget_activity", "header_patterns": ["BA", "Budget Activity"], "dtype": "text",
             "description": "Budget Activity code (6.1, 6.2, 6.3, etc.)"},
            {"field": "prior_year_bud", "header_patterns": ["Prior Year", "PriorYBud"], "dtype": "currency_thousands",
             "description": "Prior year enacted in thousands"},
            {"field": "current_year_bud", "header_patterns": ["Current Year", "CurYBud"], "dtype": "currency_thousands",
             "description": "Current year enacted in thousands"},
            {"field": "budget_estimate", "header_patterns": ["Budget Estimate", "BudEst"], "dtype": "currency_thousands",
             "description": "President's budget estimate in thousands"},
        ],
        "known_variations": [
            "Budget activity codes follow the DoD pattern (6.1=Basic Research, 6.2=Applied Research, etc.)",
        ],
    },

    "o1": {
        "name": "Operation & Maintenance (O-1)",
        "description": "Operation & Maintenance summary — funding for personnel, operations, sustainment, and training",
        "column_spec": [
            {"field": "account", "header_patterns": ["Account", "ACC"], "dtype": "text",
             "description": "O&M account code"},
            {"field": "account_title", "header_patterns": ["Account Title", "Title"], "dtype": "text",
             "description": "O&M account title"},
            {"field": "program_element", "header_patterns": ["PE", "Program Element"], "dtype": "text",
             "description": "Program Element number"},
            {"field": "appropriation", "header_patterns": ["Appropriation"], "dtype": "text",
             "description": "Appropriation category (O&M)"},
            {"field": "budget_activity", "header_patterns": ["BA", "Budget Activity"], "dtype": "text",
             "description": "Budget Activity code"},
            {"field": "prior_year_bud", "header_patterns": ["Prior Year", "PriorYBud"], "dtype": "currency_thousands",
             "description": "Prior year enacted in thousands"},
            {"field": "current_year_bud", "header_patterns": ["Current Year", "CurYBud"], "dtype": "currency_thousands",
             "description": "Current year enacted in thousands"},
            {"field": "budget_estimate", "header_patterns": ["Budget Estimate", "BudEst"], "dtype": "currency_thousands",
             "description": "President's budget estimate in thousands"},
        ],
        "known_variations": [
            "O-1 often has service-specific column headers for type-of-activity breakdowns",
        ],
    },

    "m1": {
        "name": "Military Personnel (M-1)",
        "description": "Military Personnel summary — funding for active duty, reserves, national guard personnel",
        "column_spec": [
            {"field": "account", "header_patterns": ["Account", "ACC"], "dtype": "text",
             "description": "Military Personnel account code"},
            {"field": "account_title", "header_patterns": ["Account Title", "Title"], "dtype": "text",
             "description": "Military Personnel account title"},
            {"field": "appropriation", "header_patterns": ["Appropriation"], "dtype": "text",
             "description": "Appropriation category (Military Personnel)"},
            {"field": "personnel_category", "header_patterns": ["Category", "Personnel Category"], "dtype": "text",
             "description": "Officer, Enlisted, or other breakdown"},
            {"field": "authorized_strength", "header_patterns": ["Authorized", "Auth Strength"], "dtype": "integer",
             "description": "Authorized personnel strength (headcount)"},
            {"field": "prior_year_bud", "header_patterns": ["Prior Year", "PriorYBud"], "dtype": "currency_thousands",
             "description": "Prior year enacted in thousands"},
            {"field": "current_year_bud", "header_patterns": ["Current Year", "CurYBud"], "dtype": "currency_thousands",
             "description": "Current year enacted in thousands"},
            {"field": "budget_estimate", "header_patterns": ["Budget Estimate", "BudEst"], "dtype": "currency_thousands",
             "description": "President's budget estimate in thousands"},
        ],
        "known_variations": [
            "M-1 may include 'strength' (headcount) alongside budget amounts",
            "Some versions separate Officer and Enlisted personnel on different rows",
        ],
    },
}
