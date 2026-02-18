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

TODO 1.B1-a [Complexity: LOW] [Tokens: ~1500] [User: YES — needs downloaded corpus]
    Inventory all exhibit types found in downloaded files.
    Steps:
      1. Write a 40-line script: walk DoD_Budget_Documents/, open every .xlsx
      2. Read sheet names + header rows (first 5 rows)
      3. Emit report of unique (filename_pattern, sheet_name, header_signature)
      4. Output to exhibit_audit_report.txt
    Note: scripts/exhibit_audit.py already exists — run it against real data.
    Success: A complete list of exhibit types and header patterns in corpus.

TODO 1.B1-b [Complexity: MEDIUM] [Tokens: ~3000] [User: NO]
    Document column layouts for summary exhibits (P-1, R-1, O-1, M-1).
    Steps:
      1. For each exhibit, examine EXHIBIT_CATALOG entry above
      2. Cross-reference with actual header rows from TODO 1.B1-a output
      3. Record: header text, position, dtype, FY association, variations
      4. Update column_spec entries in EXHIBIT_CATALOG dict above
    Dependency: Best done after TODO 1.B1-a provides real header data.
    Success: column_spec for P-1/R-1/O-1/M-1 matches real spreadsheets.

TODO 1.B1-c [Complexity: MEDIUM] [Tokens: ~3000] [User: NO]
    Document column layouts for detail exhibits (P-5, R-2, R-3, R-4).
    Steps:
      1. From TODO 1.B1-a output, identify which detail exhibits exist
      2. Open sample files, record header patterns and data types
      3. Update/expand column_spec entries for p5, r2, r3, r4 above
    Dependency: requires TODO 1.B1-a output.
    Success: column_spec for detail exhibits matches real spreadsheets.

TODO 1.B1-d [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Verify column layouts for C-1 (MilCon) and RF-1 (Revolving Fund).
    Steps:
      1. Cross-reference c1 and rf1 entries above with real data
      2. C-1 uses authorization/appropriation instead of request/enacted
      3. RF-1 has revenue/expense columns — verify these match
      4. Update column_spec if discrepancies found
    Success: c1 and rf1 column_spec entries are validated.

TODO 1.B1-e [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Document column layouts for unusual exhibit types found by 1.B1-a.
    Steps:
      1. Check audit output for types not in EXHIBIT_CATALOG (J-Books,
         budget amendments, supplemental request exhibits)
      2. Add new entries to EXHIBIT_CATALOG for each new type
      3. Provide column_spec with header_patterns and dtypes
    Dependency: requires TODO 1.B1-a output.
    Success: All exhibit types found in corpus have catalog entries.

TODO 1.B1-f [Complexity: LOW] [Tokens: ~1000] [User: NO]
    Ensure EXHIBIT_CATALOG is fully integrated with build_budget_db.py.
    Steps:
      1. Verify find_matching_columns() is called from _map_columns()
         (already done — see build_budget_db.py line ~627)
      2. Add unit test that each catalog exhibit type returns non-empty
         column mapping for a realistic header row
      3. Test in test_exhibit_catalog.py
    Success: All catalog entries produce valid column mappings.
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

    # Detail Exhibits (Line-Item Level)
    "p5": {
        "name": "Procurement Detail (P-5)",
        "description": "Detailed procurement line items — provides per-item quantities and unit costs within procurement accounts",
        "column_spec": [
            {"field": "account", "header_patterns": ["Account"], "dtype": "text",
             "description": "Procurement account code"},
            {"field": "program_element", "header_patterns": ["PE", "Program Element"], "dtype": "text",
             "description": "Program Element number"},
            {"field": "line_item_number", "header_patterns": ["LIN", "Line Item", "Item Number"], "dtype": "text",
             "description": "Line Item Number (unique within account)"},
            {"field": "line_item_title", "header_patterns": ["Title", "Item Title"], "dtype": "text",
             "description": "Description of the procurement item"},
            {"field": "prior_year_unit_cost", "header_patterns": ["Prior Year Unit Cost"], "dtype": "currency_thousands",
             "description": "Prior year unit cost in thousands"},
            {"field": "current_year_unit_cost", "header_patterns": ["Current Year Unit Cost"], "dtype": "currency_thousands",
             "description": "Current year unit cost in thousands"},
            {"field": "estimate_unit_cost", "header_patterns": ["Estimate Unit Cost"], "dtype": "currency_thousands",
             "description": "Budget estimate unit cost in thousands"},
            {"field": "unit", "header_patterns": ["Unit of Measure", "UOM", "Unit"], "dtype": "text",
             "description": "Unit of measure (e.g., 'Each', 'Lot', 'Program')"},
            {"field": "prior_year_qty", "header_patterns": ["Prior Year Quantity", "PY Qty"], "dtype": "integer",
             "description": "Prior year quantity"},
            {"field": "current_year_qty", "header_patterns": ["Current Year Quantity", "CY Qty"], "dtype": "integer",
             "description": "Current year quantity"},
            {"field": "estimate_qty", "header_patterns": ["Estimate Quantity", "Est Qty"], "dtype": "integer",
             "description": "Budget estimate quantity"},
            {"field": "justification", "header_patterns": ["Justification", "Justification Text"], "dtype": "text",
             "description": "Narrative justification for the line item"},
        ],
        "known_variations": [
            "Quantity and unit cost may be combined into a single 'total amount' column for items with unit=Program",
            "Some exhibits show APUC (Average Procurement Unit Cost) instead of unit cost",
        ],
    },

    "r2": {
        "name": "RDT&E Detail Schedule (R-2)",
        "description": "RDT&E line-item schedule with milestone and achievement data for research programs",
        "column_spec": [
            {"field": "program_element", "header_patterns": ["PE", "Program Element"], "dtype": "text",
             "description": "Program Element number"},
            {"field": "sub_element", "header_patterns": ["Sub-Element", "Sub Element"], "dtype": "text",
             "description": "Sub-element or sub-project designation"},
            {"field": "title", "header_patterns": ["Title", "Program Title"], "dtype": "text",
             "description": "Program element title or description"},
            {"field": "prior_year_amount", "header_patterns": ["Prior Year", "PriorYAmount"], "dtype": "currency_thousands",
             "description": "Prior year funding in thousands"},
            {"field": "current_year_amount", "header_patterns": ["Current Year", "CurYAmount"], "dtype": "currency_thousands",
             "description": "Current year funding in thousands"},
            {"field": "estimate_amount", "header_patterns": ["Estimate", "Est Amount"], "dtype": "currency_thousands",
             "description": "Budget estimate in thousands"},
            {"field": "performance_metric", "header_patterns": ["Metric", "Performance", "Key Metric"], "dtype": "text",
             "description": "Key performance metric or milestone"},
            {"field": "planned_achievement", "header_patterns": ["Planned Achievement", "Planned"], "dtype": "text",
             "description": "Planned achievement for budget estimate year"},
            {"field": "current_achievement", "header_patterns": ["Current Achievement", "Achievement"], "dtype": "text",
             "description": "Current year achievement or status"},
        ],
        "known_variations": [
            "R-2 often includes narrative justification sections below tabular data",
            "Performance metrics vary significantly by research program domain",
        ],
    },

    "r3": {
        "name": "RDT&E Project Schedule (R-3)",
        "description": "RDT&E project-level schedule showing development approach, schedule, and cost estimate growth",
        "column_spec": [
            {"field": "program_element", "header_patterns": ["PE"], "dtype": "text"},
            {"field": "project_number", "header_patterns": ["Project Number", "Project No"], "dtype": "text"},
            {"field": "project_title", "header_patterns": ["Project Title", "Title"], "dtype": "text"},
            {"field": "prior_year_amount", "header_patterns": ["Prior Year"], "dtype": "currency_thousands"},
            {"field": "current_year_amount", "header_patterns": ["Current Year"], "dtype": "currency_thousands"},
            {"field": "estimate_amount", "header_patterns": ["Estimate"], "dtype": "currency_thousands"},
            {"field": "development_approach", "header_patterns": ["Development Approach"], "dtype": "text"},
            {"field": "schedule_summary", "header_patterns": ["Schedule"], "dtype": "text"},
        ],
        "known_variations": [],
    },

    "r4": {
        "name": "RDT&E Budget Item Justification (R-4)",
        "description": "Detailed justification for RDT&E budget items with technical narrative",
        "column_spec": [
            {"field": "program_element", "header_patterns": ["PE"], "dtype": "text"},
            {"field": "line_item", "header_patterns": ["Line Item", "Item"], "dtype": "text"},
            {"field": "amount", "header_patterns": ["Amount", "Total"], "dtype": "currency_thousands"},
            {"field": "narrative", "header_patterns": ["Narrative", "Justification"], "dtype": "text"},
        ],
        "known_variations": [],
    },

    # Special Exhibits
    "c1": {
        "name": "Military Construction (C-1)",
        "description": "Military Construction budget — facility projects and real property acquisitions",
        "column_spec": [
            {"field": "account", "header_patterns": ["Account"], "dtype": "text",
             "description": "Military Construction account code"},
            {"field": "project_number", "header_patterns": ["Project Number", "Project No"], "dtype": "text",
             "description": "Project identification number"},
            {"field": "project_title", "header_patterns": ["Project Title", "Title"], "dtype": "text",
             "description": "Project name/description"},
            {"field": "location", "header_patterns": ["Location", "Installation"], "dtype": "text",
             "description": "Military installation or location"},
            {"field": "authorization_amount", "header_patterns": ["Authorization", "Auth Amount"], "dtype": "currency_thousands",
             "description": "Authorization amount in thousands (not enacted like other exhibits)"},
            {"field": "appropriation_amount", "header_patterns": ["Appropriation", "Approp Amount"], "dtype": "currency_thousands",
             "description": "Appropriation amount in thousands"},
            {"field": "estimate_amount", "header_patterns": ["Estimate", "Est Amount"], "dtype": "currency_thousands",
             "description": "Budget estimate in thousands"},
        ],
        "known_variations": [
            "C-1 uses authorization/appropriation instead of prior/current enacted pattern",
            "May include project duration or completion date fields",
        ],
    },

    "rf1": {
        "name": "Revolving Funds (RF-1)",
        "description": "Revolving Fund budget — working capital funds and enterprise funds",
        "column_spec": [
            {"field": "activity", "header_patterns": ["Activity", "Fund Activity"], "dtype": "text",
             "description": "Revolving fund activity code"},
            {"field": "activity_title", "header_patterns": ["Title", "Activity Title"], "dtype": "text",
             "description": "Activity description"},
            {"field": "prior_year_revenue", "header_patterns": ["Prior Year Revenue"], "dtype": "currency_thousands",
             "description": "Prior year revenue/receipts in thousands"},
            {"field": "prior_year_expenses", "header_patterns": ["Prior Year Expenses"], "dtype": "currency_thousands",
             "description": "Prior year expenses/obligations in thousands"},
            {"field": "current_year_revenue", "header_patterns": ["Current Year Revenue"], "dtype": "currency_thousands",
             "description": "Current year estimated revenue in thousands"},
            {"field": "current_year_expenses", "header_patterns": ["Current Year Expenses"], "dtype": "currency_thousands",
             "description": "Current year estimated expenses in thousands"},
            {"field": "estimate_revenue", "header_patterns": ["Estimate Revenue"], "dtype": "currency_thousands",
             "description": "Budget estimate revenue in thousands"},
            {"field": "estimate_expenses", "header_patterns": ["Estimate Expenses"], "dtype": "currency_thousands",
             "description": "Budget estimate expenses in thousands"},
        ],
        "known_variations": [
            "RF-1 exhibits revenue and expenses rather than budget authority like other exhibits",
            "Revolving fund structure varies by fund type (working capital, service/support)",
        ],
    },

    "p1r": {
        "name": "Procurement Reserve (P-1R)",
        "description": "Procurement reserves budget — unfunded requirements and contingency funds",
        "column_spec": [
            {"field": "reserve_type", "header_patterns": ["Reserve Type", "Type"], "dtype": "text",
             "description": "Type of reserve (unfunded requirement, contingency, etc.)"},
            {"field": "description", "header_patterns": ["Description", "Title"], "dtype": "text",
             "description": "Description of the reserve"},
            {"field": "prior_year_amount", "header_patterns": ["Prior Year"], "dtype": "currency_thousands",
             "description": "Prior year amount in thousands"},
            {"field": "current_year_amount", "header_patterns": ["Current Year"], "dtype": "currency_thousands",
             "description": "Current year amount in thousands"},
            {"field": "estimate_amount", "header_patterns": ["Estimate"], "dtype": "currency_thousands",
             "description": "Budget estimate in thousands"},
            {"field": "justification", "header_patterns": ["Justification", "Rationale"], "dtype": "text",
             "description": "Justification for the reserve"},
        ],
        "known_variations": [],
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Helper Functions — For use by build_budget_db.py and other parsing modules
# ──────────────────────────────────────────────────────────────────────────────

def get_exhibit_spec(exhibit_type_key: str):
    """
    Retrieve the complete specification for an exhibit type.

    Args:
        exhibit_type_key: Lowercase exhibit type key (e.g., 'p1', 'r1', 'm1')

    Returns:
        Dict with 'name', 'description', 'column_spec', 'known_variations',
        or None if not found.
    """
    return EXHIBIT_CATALOG.get(exhibit_type_key.lower())


def get_column_spec_for_exhibit(exhibit_type_key: str):
    """
    Retrieve just the column specification for an exhibit type.

    Args:
        exhibit_type_key: Lowercase exhibit type key

    Returns:
        List of column specs or empty list if not found.
    """
    spec = get_exhibit_spec(exhibit_type_key)
    return spec.get("column_spec", []) if spec else []


def find_matching_columns(exhibit_type_key: str, header_row: list):
    """
    Match a header row against the known column specifications for an exhibit type.
    Returns a mapping of column index → field name for columns that match.

    Args:
        exhibit_type_key: Lowercase exhibit type key
        header_row: List of header cell values (strings)

    Returns:
        Dict mapping column_index (int) → field_name (str) for matched columns,
        empty dict if no match found.
    """
    col_specs = get_column_spec_for_exhibit(exhibit_type_key)
    if not col_specs:
        return {}

    matched_columns = {}
    header_lower = [str(h).lower() if h else "" for h in header_row]

    for col_idx, header_text in enumerate(header_lower):
        for col_spec in col_specs:
            patterns = col_spec.get("header_patterns", [])
            for pattern in patterns:
                if pattern.lower() in header_text:
                    matched_columns[col_idx] = col_spec["field"]
                    break
            if col_idx in matched_columns:
                break

    return matched_columns


def list_all_exhibit_types():
    """
    Return a list of all known exhibit type keys in the catalog.

    Returns:
        List of exhibit type keys (lowercase strings).
    """
    return sorted(EXHIBIT_CATALOG.keys())


def describe_catalog():
    """
    Return a human-readable summary of all exhibits in the catalog.

    Returns:
        Formatted string with exhibit names, descriptions, and column counts.
    """
    lines = [
        "=" * 80,
        "DoD BUDGET EXHIBIT CATALOG",
        "=" * 80,
        ""
    ]

    for exhibit_type in list_all_exhibit_types():
        spec = get_exhibit_spec(exhibit_type)
        col_count = len(spec.get("column_spec", []))
        lines.append(f"{exhibit_type.upper():6s} | {spec['name']:40s} | {col_count} columns")
        lines.append(f"         {spec['description']}")
        lines.append("")

    return "\n".join(lines)


# TODO 1.B1-a [Complexity: LOW] [Tokens: ~1500] [User: YES — needs downloaded corpus]
#   Run scripts/exhibit_audit.py against DoD_Budget_Documents/ to inventory
#   actual header rows from every .xlsx file. Compare against catalog entries.
#   Save output to exhibit_audit_report.txt and review for catalog gaps.
#   Cannot run without the multi-GB downloaded corpus — user must execute.
