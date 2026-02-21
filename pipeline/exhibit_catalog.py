"""
Exhibit Type Catalog

Comprehensive catalog of every DoD budget exhibit type, documenting the column
layout and semantics for each.  This module serves as the single source of truth
for how each exhibit's spreadsheet is structured, what columns to expect, and
how to map them to our canonical data model.
"""

EXHIBIT_CATALOG = {
    # --------------------------------------------------------------------------
    # Summary Exhibits
    # --------------------------------------------------------------------------
    #
    # IMPORTANT -- Real-data header patterns (verified against FY2026 comptroller files)
    #
    # The comptroller Excel files use a consistent multi-sheet layout:
    #   - First sheet is the "Exhibit <type>" summary (all FYs side-by-side)
    #   - Subsequent sheets are per-FY breakdowns: "FY 2024 Actuals", "FY 2025 Enacted", etc.
    #   - Header row is always Row 2 (Row 1 is blank or a title)
    #
    # Dollar-amount columns use FY-specific headers (not generic "Prior Year"):
    #   "FY 2024 Actuals", "FY 2025 Enacted", "FY 2025 Supplemental", "FY 2025 Total",
    #   "FY 2026 Disc Request", "FY 2026 Reconciliation Request", "FY 2026 Total"
    #
    # Common structural columns across most exhibits:
    #   Account, Account Title, Organization, Budget Activity, Budget Activity Title,
    #   BSA (or AG/BSA), Budget SubActivity (BSA) Title (or AG/Budget SubActivity...),
    #   Line Number, Add/Non-Add, Include In TOA, Classification
    #
    # The dollar-amount header_patterns below use substring matching, so "Actuals"
    # will match "FY 2024 Actuals" and "FY 2025 Actuals" across different FYs.
    # --------------------------------------------------------------------------

    "p1": {
        "name": "Procurement (P-1)",
        "description": "Summary procurement budget exhibit -- funding requests for procurement of weapons, vehicles, equipment",
        "column_spec": [
            {"field": "account", "header_patterns": ["Account"], "dtype": "text",
             "description": "Procurement account code (e.g., 2035 for Aircraft Procurement, Army)"},
            {"field": "account_title", "header_patterns": ["Account Title"], "dtype": "text",
             "description": "Full title of the procurement account"},
            {"field": "organization", "header_patterns": ["Organization"], "dtype": "text",
             "description": "Military service or organization"},
            {"field": "budget_activity", "header_patterns": ["Budget Activity"], "dtype": "text",
             "description": "Budget Activity code"},
            {"field": "budget_activity_title", "header_patterns": ["Budget Activity Title"], "dtype": "text",
             "description": "Budget Activity description"},
            {"field": "line_number", "header_patterns": ["Line Number"], "dtype": "text",
             "description": "Line item number within the account"},
            {"field": "bsa", "header_patterns": ["BSA"], "dtype": "text",
             "description": "Budget Sub-Activity code"},
            {"field": "bsa_title", "header_patterns": ["Budget SubActivity (BSA) Title"], "dtype": "text",
             "description": "Budget Sub-Activity description"},
            {"field": "budget_line_item", "header_patterns": ["Budget Line Item"], "dtype": "text",
             "description": "Budget Line Item (BLI) code"},
            {"field": "bli_title", "header_patterns": ["Budget Line Item (BLI) Title"], "dtype": "text",
             "description": "Budget Line Item description"},
            {"field": "cost_type", "header_patterns": ["Cost Type"], "dtype": "text",
             "description": "Cost type code (e.g., recurring, non-recurring)"},
            {"field": "cost_type_title", "header_patterns": ["Cost Type Title"], "dtype": "text",
             "description": "Cost type description"},
            {"field": "add_non_add", "header_patterns": ["Add/Non-Add"], "dtype": "text",
             "description": "Indicates additive or non-additive row"},
            {"field": "actuals_quantity", "header_patterns": ["Actuals Quantity"], "dtype": "integer",
             "description": "Prior year actual quantity"},
            {"field": "actuals_amount", "header_patterns": ["Actuals Amount"], "dtype": "currency_thousands",
             "description": "Prior year actual amount in thousands"},
            {"field": "enacted_quantity", "header_patterns": ["Enacted Quantity"], "dtype": "integer",
             "description": "Current year enacted quantity"},
            {"field": "enacted_amount", "header_patterns": ["Enacted Amount"], "dtype": "currency_thousands",
             "description": "Current year enacted amount in thousands"},
            {"field": "request_quantity", "header_patterns": ["Request Quantity", "Disc Request Quantity"], "dtype": "integer",
             "description": "Budget request quantity"},
            {"field": "request_amount", "header_patterns": ["Request Amount", "Disc Request Amount"], "dtype": "currency_thousands",
             "description": "Budget request amount in thousands"},
            {"field": "classification", "header_patterns": ["Classification"], "dtype": "text",
             "description": "Security classification level"},
        ],
        "known_variations": [
            "Dollar/quantity columns use FY-prefixed headers: 'FY 2024 Actuals Amount', 'FY 2025 Enacted Quantity', etc.",
            "Reconciliation columns may appear: 'FY 2026 Reconciliation Request Quantity/Amount'",
            "Total columns may appear: 'FY 2026 Total Quantity/Amount'",
            "Navy/USMC versions may use 'PE/BLI' header instead of separate columns",
            "Army versions sometimes include 'SLI' (Sub-Line Item) designation",
        ],
    },

    "r1": {
        "name": "RDT&E (R-1)",
        "description": "Research, Development, Test & Evaluation summary -- funding for military technology development",
        "column_spec": [
            {"field": "account", "header_patterns": ["Account"], "dtype": "text",
             "description": "RDT&E account code"},
            {"field": "account_title", "header_patterns": ["Account Title"], "dtype": "text",
             "description": "Full account title"},
            {"field": "organization", "header_patterns": ["Organization"], "dtype": "text",
             "description": "Military service or organization"},
            {"field": "budget_activity", "header_patterns": ["Budget Activity"], "dtype": "text",
             "description": "Budget Activity code (6.1, 6.2, 6.3, etc.)"},
            {"field": "budget_activity_title", "header_patterns": ["Budget Activity Title"], "dtype": "text",
             "description": "Budget Activity description"},
            {"field": "line_number", "header_patterns": ["Line Number"], "dtype": "text",
             "description": "Line item number"},
            {"field": "pe_bli", "header_patterns": ["PE/BLI"], "dtype": "text",
             "description": "Program Element / Budget Line Item code"},
            {"field": "pe_bli_title", "header_patterns": ["Program Element/Budget Line Item (BLI) Title"], "dtype": "text",
             "description": "PE/BLI description"},
            {"field": "include_in_toa", "header_patterns": ["Include In TOA"], "dtype": "text",
             "description": "Whether line is included in Total Obligation Authority"},
            {"field": "actuals", "header_patterns": ["Actuals"], "dtype": "currency_thousands",
             "description": "Prior year actual amount in thousands"},
            {"field": "enacted", "header_patterns": ["Enacted"], "dtype": "currency_thousands",
             "description": "Current year enacted amount in thousands"},
            {"field": "request", "header_patterns": ["Disc Request"], "dtype": "currency_thousands",
             "description": "Budget request amount in thousands"},
            {"field": "classification", "header_patterns": ["Classification"], "dtype": "text",
             "description": "Security classification level"},
        ],
        "known_variations": [
            "Dollar columns use FY-prefixed headers: 'FY 2024 Actuals', 'FY 2025 Enacted', 'FY 2026 Disc Request'",
            "Supplemental and Reconciliation columns may appear for current FY",
            "Total columns may appear: 'FY 2025 Total', 'FY 2026 Total'",
        ],
    },

    "o1": {
        "name": "Operation & Maintenance (O-1)",
        "description": "Operation & Maintenance summary -- funding for personnel, operations, sustainment, and training",
        "column_spec": [
            {"field": "account", "header_patterns": ["Account"], "dtype": "text",
             "description": "O&M account code"},
            {"field": "account_title", "header_patterns": ["Account Title"], "dtype": "text",
             "description": "O&M account title"},
            {"field": "organization", "header_patterns": ["Organization"], "dtype": "text",
             "description": "Military service or organization"},
            {"field": "budget_activity", "header_patterns": ["Budget Activity"], "dtype": "text",
             "description": "Budget Activity code"},
            {"field": "budget_activity_title", "header_patterns": ["Budget Activity Title"], "dtype": "text",
             "description": "Budget Activity description"},
            {"field": "ag_bsa", "header_patterns": ["AG/BSA"], "dtype": "text",
             "description": "Activity Group / Budget Sub-Activity code"},
            {"field": "ag_bsa_title", "header_patterns": ["AG/Budget SubActivity (BSA) Title"], "dtype": "text",
             "description": "Activity Group / BSA description"},
            {"field": "line_number", "header_patterns": ["Line Number"], "dtype": "text",
             "description": "Line item number"},
            {"field": "sag_bli", "header_patterns": ["SAG/BLI"], "dtype": "text",
             "description": "Sub-Activity Group / Budget Line Item code"},
            {"field": "sag_bli_title", "header_patterns": ["SAG/Budget Line Item (BLI) Title"], "dtype": "text",
             "description": "SAG/BLI description"},
            {"field": "include_in_toa", "header_patterns": ["Include In TOA"], "dtype": "text",
             "description": "Whether line is included in Total Obligation Authority"},
            {"field": "actuals", "header_patterns": ["Actuals"], "dtype": "currency_thousands",
             "description": "Prior year actual amount in thousands"},
            {"field": "enacted", "header_patterns": ["Enacted"], "dtype": "currency_thousands",
             "description": "Current year enacted amount in thousands"},
            {"field": "request", "header_patterns": ["Disc Request"], "dtype": "currency_thousands",
             "description": "Budget request amount in thousands"},
            {"field": "classification", "header_patterns": ["Classification"], "dtype": "text",
             "description": "Security classification level"},
        ],
        "known_variations": [
            "Dollar columns use FY-prefixed headers: 'FY 2024 Actuals', 'FY 2025 Enacted', 'FY 2026 Disc Request'",
            "Supplemental and Reconciliation columns may appear",
            "Sheets: 'OM Title plus Indefinite' (combined), 'OM Title', 'Indefinite Accounts' + FY sheets",
        ],
    },

    "m1": {
        "name": "Military Personnel (M-1)",
        "description": "Military Personnel summary -- funding for active duty, reserves, national guard personnel",
        "column_spec": [
            {"field": "account", "header_patterns": ["Account"], "dtype": "text",
             "description": "Military Personnel account code"},
            {"field": "account_title", "header_patterns": ["Account Title"], "dtype": "text",
             "description": "Military Personnel account title"},
            {"field": "organization", "header_patterns": ["Organization"], "dtype": "text",
             "description": "Military service or organization"},
            {"field": "budget_activity", "header_patterns": ["Budget Activity"], "dtype": "text",
             "description": "Budget Activity code"},
            {"field": "budget_activity_title", "header_patterns": ["Budget Activity Title"], "dtype": "text",
             "description": "Budget Activity description"},
            {"field": "bsa", "header_patterns": ["BSA"], "dtype": "text",
             "description": "Budget Sub-Activity code"},
            {"field": "bsa_title", "header_patterns": ["Budget SubActivity (BSA) Title"], "dtype": "text",
             "description": "Budget Sub-Activity description"},
            {"field": "add_non_add", "header_patterns": ["Add/Non-Add"], "dtype": "text",
             "description": "Indicates additive or non-additive row"},
            {"field": "include_in_toa", "header_patterns": ["Include In TOA"], "dtype": "text",
             "description": "Whether line is included in Total Obligation Authority"},
            {"field": "actuals", "header_patterns": ["Actuals"], "dtype": "currency_thousands",
             "description": "Prior year actual amount in thousands"},
            {"field": "enacted", "header_patterns": ["Enacted"], "dtype": "currency_thousands",
             "description": "Current year enacted amount in thousands"},
            {"field": "request", "header_patterns": ["Disc Request"], "dtype": "currency_thousands",
             "description": "Budget request amount in thousands"},
            {"field": "classification", "header_patterns": ["Classification"], "dtype": "text",
             "description": "Security classification level"},
        ],
        "known_variations": [
            "Dollar columns use FY-prefixed headers: 'FY 2024 Actuals', 'FY 2025 Enacted', 'FY 2026 Disc Request'",
            "Supplemental columns may appear: 'FY 2025 Supplemental', 'FY 2025 Total'",
            "Reconciliation columns may appear: 'FY 2026 Reconciliation Request', 'FY 2026 Total'",
        ],
    },

    # Detail Exhibits (Line-Item Level)
    # NOTE: P-5, R-2, R-3, R-4 are found in J-Book PDFs, not in comptroller Excel files.
    # Their column specs are based on DoD format documentation and have NOT been verified
    # against real corpus data yet. They will need updating when J-Book Excel data is available.
    "p5": {
        "name": "Procurement Detail (P-5)",
        "description": "Detailed procurement line items -- provides per-item quantities and unit costs within procurement accounts",
        "column_spec": [
            {"field": "account", "header_patterns": ["Account"], "dtype": "text",
             "description": "Procurement account code"},
            {"field": "program_element", "header_patterns": ["PE", "Program Element"], "dtype": "text",
             "description": "Program Element number"},
            {"field": "line_item_number", "header_patterns": ["LIN", "Line Item", "Item Number"], "dtype": "text",
             "description": "Line Item Number (unique within account)"},
            {"field": "line_item_title", "header_patterns": ["Item Title"], "dtype": "text",
             "description": "Description of the procurement item"},
            {"field": "prior_year_unit_cost", "header_patterns": ["Prior Year Unit Cost"], "dtype": "currency_thousands",
             "description": "Prior year unit cost in thousands"},
            {"field": "current_year_unit_cost", "header_patterns": ["Current Year Unit Cost"], "dtype": "currency_thousands",
             "description": "Current year unit cost in thousands"},
            {"field": "estimate_unit_cost", "header_patterns": ["Estimate Unit Cost"], "dtype": "currency_thousands",
             "description": "Budget estimate unit cost in thousands"},
            {"field": "unit", "header_patterns": ["Unit of Measure", "Unit", "UOM"], "dtype": "text",
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
            "NOT YET VERIFIED against real corpus -- spec based on DoD format documentation",
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
            {"field": "title", "header_patterns": ["Program Title", "Title"], "dtype": "text",
             "description": "Program element title or description"},
            {"field": "prior_year_amount", "header_patterns": ["Prior Year"], "dtype": "currency_thousands",
             "description": "Prior year funding in thousands"},
            {"field": "current_year_amount", "header_patterns": ["Current Year"], "dtype": "currency_thousands",
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
            "NOT YET VERIFIED against real corpus -- spec based on DoD format documentation",
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
            {"field": "project_title", "header_patterns": ["Project Title"], "dtype": "text"},
            {"field": "prior_year_amount", "header_patterns": ["Prior Year"], "dtype": "currency_thousands"},
            {"field": "current_year_amount", "header_patterns": ["Current Year"], "dtype": "currency_thousands"},
            {"field": "estimate_amount", "header_patterns": ["Estimate"], "dtype": "currency_thousands"},
            {"field": "development_approach", "header_patterns": ["Development Approach"], "dtype": "text"},
            {"field": "schedule_summary", "header_patterns": ["Schedule"], "dtype": "text"},
        ],
        "known_variations": [
            "NOT YET VERIFIED against real corpus -- spec based on DoD format documentation",
        ],
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
        "known_variations": [
            "NOT YET VERIFIED against real corpus -- spec based on DoD format documentation",
        ],
    },

    # Special Exhibits
    "c1": {
        "name": "Military Construction (C-1)",
        "description": "Military Construction budget -- facility projects and real property acquisitions",
        "column_spec": [
            {"field": "account", "header_patterns": ["Account"], "dtype": "text",
             "description": "Military Construction account code"},
            {"field": "account_title", "header_patterns": ["Account Title"], "dtype": "text",
             "description": "Account title"},
            {"field": "budget_activity", "header_patterns": ["Budget Activity"], "dtype": "text",
             "description": "Budget Activity code"},
            {"field": "budget_activity_title", "header_patterns": ["Budget Activity Title"], "dtype": "text",
             "description": "Budget Activity description"},
            {"field": "organization", "header_patterns": ["Organization"], "dtype": "text",
             "description": "Military service or organization"},
            {"field": "state_country", "header_patterns": ["State\nCountry", "State Country"], "dtype": "text",
             "description": "State or country code"},
            {"field": "state_country_title", "header_patterns": ["State Country Title"], "dtype": "text",
             "description": "State or country name"},
            {"field": "fiscal_year", "header_patterns": ["Fiscal Year"], "dtype": "text",
             "description": "Fiscal year of the construction project"},
            {"field": "facility_category_title", "header_patterns": ["Facility Category Title"], "dtype": "text",
             "description": "Type of facility being constructed"},
            {"field": "location_title", "header_patterns": ["Location Title"], "dtype": "text",
             "description": "Military installation or location name"},
            {"field": "construction_project", "header_patterns": ["Construction\nProject", "Construction Project"], "dtype": "text",
             "description": "Construction project code"},
            {"field": "construction_project_title", "header_patterns": ["Construction Project Title"], "dtype": "text",
             "description": "Construction project description"},
            {"field": "classification", "header_patterns": ["Classification"], "dtype": "text",
             "description": "Security classification level"},
            {"field": "authorization_amount", "header_patterns": ["Authorization Amount"], "dtype": "currency_thousands",
             "description": "Authorization amount in thousands"},
            {"field": "authorization_of_approp", "header_patterns": ["Authorization of Approp"], "dtype": "currency_thousands",
             "description": "Authorization of Appropriation amount in thousands"},
            {"field": "appropriation_amount", "header_patterns": ["Appropriation Amount"], "dtype": "currency_thousands",
             "description": "Appropriation amount in thousands"},
            {"field": "total_obligation_authority", "header_patterns": ["Total Obligation Authority"], "dtype": "currency_thousands",
             "description": "Total Obligation Authority in thousands"},
        ],
        "known_variations": [
            "Dollar columns are FY-prefixed: 'FY2024 Authorization Amount', 'FY2024 Appropriation Amount', etc.",
            "C-1 uses authorization/appropriation instead of enacted/request pattern used by other exhibits",
            "Sheets are per-FY: 'FY 2024', 'FY 2025', 'FY 2026', 'FY 2026 Mandatory Recon'",
            "State/Country and Construction Project headers may contain embedded newlines",
        ],
    },

    "rf1": {
        "name": "Revolving Funds (RF-1)",
        "description": "Revolving Fund budget -- working capital funds and enterprise funds",
        "column_spec": [
            {"field": "account", "header_patterns": ["Account"], "dtype": "text",
             "description": "Revolving fund account code"},
            {"field": "account_title", "header_patterns": ["Account Title"], "dtype": "text",
             "description": "Account title"},
            {"field": "organization", "header_patterns": ["Organization"], "dtype": "text",
             "description": "Military service or organization"},
            {"field": "budget_activity", "header_patterns": ["Budget Activity"], "dtype": "text",
             "description": "Budget Activity code"},
            {"field": "budget_activity_title", "header_patterns": ["Budget Activity Title"], "dtype": "text",
             "description": "Budget Activity description"},
            {"field": "ag_bsa", "header_patterns": ["AG/BSA"], "dtype": "text",
             "description": "Activity Group / Budget Sub-Activity code"},
            {"field": "ag_bsa_title", "header_patterns": ["AG/Budget SubActivity (BSA) Title"], "dtype": "text",
             "description": "Activity Group / BSA description"},
            {"field": "line_number", "header_patterns": ["Line Number"], "dtype": "text",
             "description": "Line item number"},
            {"field": "sag_bli", "header_patterns": ["SAG/BLI"], "dtype": "text",
             "description": "Sub-Activity Group / Budget Line Item code"},
            {"field": "sag_bli_title", "header_patterns": ["SAG/Budget Line Item (BLI) Title"], "dtype": "text",
             "description": "SAG/BLI description"},
            {"field": "include_in_toa", "header_patterns": ["Include In TOA"], "dtype": "text",
             "description": "Whether line is included in Total Obligation Authority"},
            {"field": "actuals", "header_patterns": ["Actuals"], "dtype": "currency_thousands",
             "description": "Prior year actual amount in thousands"},
            {"field": "enacted", "header_patterns": ["Enacted"], "dtype": "currency_thousands",
             "description": "Current year enacted amount in thousands"},
            {"field": "request", "header_patterns": ["Disc Request"], "dtype": "currency_thousands",
             "description": "Budget request amount in thousands"},
            {"field": "classification", "header_patterns": ["Classification"], "dtype": "text",
             "description": "Security classification level"},
        ],
        "known_variations": [
            "RF-1 uses the same O&M-style structure (AG/BSA, SAG/BLI hierarchy) not revenue/expense pairs",
            "Dollar columns use FY-prefixed headers: 'FY 2024 Actuals', 'FY 2025 Enacted', 'FY 2026 Disc Request'",
            "Supplemental and Reconciliation columns may appear",
            "Note: 'FY 2024 Acuals' [sic] typo observed in actual FY2026 data (missing 't')",
        ],
    },

    "p1r": {
        "name": "Procurement Reconciliation (P-1R)",
        "description": "Procurement reconciliation exhibit -- same structure as P-1 with quantity/amount pairs per fiscal year",
        "column_spec": [
            {"field": "account", "header_patterns": ["Account"], "dtype": "text",
             "description": "Procurement account code"},
            {"field": "account_title", "header_patterns": ["Account Title"], "dtype": "text",
             "description": "Account title"},
            {"field": "organization", "header_patterns": ["Organization"], "dtype": "text",
             "description": "Military service or organization"},
            {"field": "budget_activity", "header_patterns": ["Budget Activity"], "dtype": "text",
             "description": "Budget Activity code"},
            {"field": "budget_activity_title", "header_patterns": ["Budget Activity Title"], "dtype": "text",
             "description": "Budget Activity description"},
            {"field": "bsa", "header_patterns": ["BSA"], "dtype": "text",
             "description": "Budget Sub-Activity code"},
            {"field": "bsa_title", "header_patterns": ["Budget SubActivity (BSA) Title"], "dtype": "text",
             "description": "Budget Sub-Activity description"},
            {"field": "budget_line_item", "header_patterns": ["Budget Line Item"], "dtype": "text",
             "description": "Budget Line Item code"},
            {"field": "pe_bli_title", "header_patterns": ["Program Element/Budget Line Item (BLI) Title"], "dtype": "text",
             "description": "PE/BLI description"},
            {"field": "cost_type", "header_patterns": ["Cost Type"], "dtype": "text",
             "description": "Cost type code"},
            {"field": "cost_type_title", "header_patterns": ["Cost Type Title"], "dtype": "text",
             "description": "Cost type description"},
            {"field": "add_non_add", "header_patterns": ["Add/Non-Add"], "dtype": "text",
             "description": "Indicates additive or non-additive row"},
            {"field": "actuals_quantity", "header_patterns": ["Actuals Quantity"], "dtype": "integer",
             "description": "Prior year actual quantity"},
            {"field": "actuals_amount", "header_patterns": ["Actuals Amount"], "dtype": "currency_thousands",
             "description": "Prior year actual amount in thousands"},
            {"field": "enacted_quantity", "header_patterns": ["Enacted Quantity"], "dtype": "integer",
             "description": "Current year enacted quantity"},
            {"field": "enacted_amount", "header_patterns": ["Enacted Amount"], "dtype": "currency_thousands",
             "description": "Current year enacted amount in thousands"},
            {"field": "request_quantity", "header_patterns": ["Request Quantity"], "dtype": "integer",
             "description": "Budget request quantity"},
            {"field": "request_amount", "header_patterns": ["Request Amount"], "dtype": "currency_thousands",
             "description": "Budget request amount in thousands"},
            {"field": "classification", "header_patterns": ["Classification"], "dtype": "text",
             "description": "Security classification level"},
        ],
        "known_variations": [
            "Dollar/quantity columns use FY-prefixed headers: 'FY 2024 Actuals Amount', 'FY 2026 Request Quantity', etc.",
            "Reconciliation columns may appear: 'FY 2026 Reconciliation Quantity/Amount'",
            "Sheets: 'Exhibit P-1R' + per-FY sheets like 'FY 2024 Actuals', 'FY 2025 Enacted', etc.",
        ],
    },
}


# --------------------------------------------------------------------------
# Helper Functions -- For use by build_budget_db.py and other parsing modules
# --------------------------------------------------------------------------

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
    Returns a mapping of column index -> field name for columns that match.

    Uses longest-match-first strategy: for each header cell, all matching patterns
    are collected and the longest pattern wins. This ensures "Account Title" matches
    the account_title field rather than being consumed by "Account" -> account.

    Args:
        exhibit_type_key: Lowercase exhibit type key
        header_row: List of header cell values (strings)

    Returns:
        Dict mapping column_index (int) -> field_name (str) for matched columns,
        empty dict if no match found.
    """
    col_specs = get_column_spec_for_exhibit(exhibit_type_key)
    if not col_specs:
        return {}

    matched_columns = {}
    used_fields = set()
    header_lower = [str(h).lower().replace("\n", " ") if h else "" for h in header_row]

    # Build all candidate matches: (col_idx, field, pattern_length)
    candidates = []
    for col_idx, header_text in enumerate(header_lower):
        if not header_text:
            continue
        for col_spec in col_specs:
            patterns = col_spec.get("header_patterns", [])
            for pattern in patterns:
                if pattern.lower() in header_text:
                    candidates.append((col_idx, col_spec["field"], len(pattern)))

    # Sort by pattern length descending -- longest (most specific) match wins
    candidates.sort(key=lambda x: -x[2])

    for col_idx, field, _plen in candidates:
        if col_idx in matched_columns or field in used_fields:
            continue
        matched_columns[col_idx] = field
        used_fields.add(field)

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
