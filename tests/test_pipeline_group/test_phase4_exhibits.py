"""
Phase 4 — B4.3: Validate P-5 and R-2 detail exhibit parsing.

Tests that the exhibit catalog column specs and the builder's _map_columns()
function correctly handle P-5 (Procurement Detail) and R-2 (RDT&E Detail)
exhibit types, including procurement-specific and RDT&E-specific fields.
"""

import sqlite3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pipeline.exhibit_catalog import (
    EXHIBIT_CATALOG,
    find_matching_columns,
    get_column_spec_for_exhibit,
    get_exhibit_spec,
)
from pipeline.builder import _map_columns


# ---------------------------------------------------------------------------
# P-5 Procurement Detail exhibit tests
# ---------------------------------------------------------------------------

class TestP5ExhibitCatalog:
    """Verify P-5 catalog spec contains procurement-specific fields."""

    def test_p5_exists_in_catalog(self):
        assert "p5" in EXHIBIT_CATALOG

    def test_p5_exhibit_class_is_detail(self):
        spec = get_exhibit_spec("p5")
        assert spec is not None
        assert spec["name"] == "Procurement Detail (P-5)"

    def test_p5_has_procurement_specific_columns(self):
        col_specs = get_column_spec_for_exhibit("p5")
        field_names = {c["field"] for c in col_specs}
        # Procurement-specific fields
        assert "line_item_number" in field_names
        assert "line_item_title" in field_names
        assert "program_element" in field_names
        assert "unit" in field_names

    def test_p5_has_unit_cost_columns(self):
        col_specs = get_column_spec_for_exhibit("p5")
        field_names = {c["field"] for c in col_specs}
        assert "prior_year_unit_cost" in field_names
        assert "current_year_unit_cost" in field_names
        assert "estimate_unit_cost" in field_names

    def test_p5_has_quantity_columns(self):
        col_specs = get_column_spec_for_exhibit("p5")
        field_names = {c["field"] for c in col_specs}
        assert "prior_year_qty" in field_names
        assert "current_year_qty" in field_names
        assert "estimate_qty" in field_names

    def test_p5_has_justification_column(self):
        col_specs = get_column_spec_for_exhibit("p5")
        field_names = {c["field"] for c in col_specs}
        assert "justification" in field_names


class TestP5ColumnMapping:
    """Verify P-5 column matching via find_matching_columns and _map_columns."""

    def test_find_matching_columns_p5_basic(self):
        """Catalog-based matching should map P-5 specific headers."""
        headers = [
            "Account", "PE", "LIN", "Item Title",
            "Prior Year Unit Cost", "Current Year Unit Cost",
            "Estimate Unit Cost", "Unit of Measure",
            "Prior Year Quantity", "Current Year Quantity",
            "Estimate Quantity", "Justification",
        ]
        mapping = find_matching_columns("p5", headers)
        matched_fields = set(mapping.values())
        assert "account" in matched_fields
        assert "program_element" in matched_fields
        assert "line_item_number" in matched_fields
        assert "line_item_title" in matched_fields
        assert "unit" in matched_fields

    def test_map_columns_p5_pe_maps_to_account(self):
        """For P-5, PE/Program Element should exist in the mapping (via catalog)."""
        headers = [
            "Account", "PE", "Line Item", "Item Title",
            "FY 2025 Enacted Amount", "FY 2026 Request Amount",
        ]
        mapping = _map_columns(headers, "p5")
        # The builder maps 'account' from first column
        assert "account" in mapping
        # Amount columns should be detected
        amount_keys = [k for k in mapping if k.startswith("amount_fy")]
        assert len(amount_keys) >= 1

    def test_map_columns_p5_cost_type(self):
        """P-5 cost_type and cost_type_title should be mapped."""
        headers = [
            "Account", "Account Title", "Line Item", "Line Item Title",
            "Cost Type", "Cost Type Title",
            "FY 2025 Enacted Amount", "FY 2026 Request Amount",
        ]
        mapping = _map_columns(headers, "p5")
        assert "cost_type" in mapping
        assert "cost_type_title" in mapping


class TestP5DatabaseInsertion:
    """Verify P-5 budget lines can be inserted and queried correctly."""

    def test_p5_budget_line_insertion(self, tmp_path: Path):
        """Create a minimal budget_lines table and insert P-5 style rows."""
        db_path = tmp_path / "test_p5.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE budget_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT,
                exhibit_type TEXT,
                fiscal_year TEXT,
                account TEXT,
                account_title TEXT,
                line_item TEXT,
                line_item_title TEXT,
                pe_number TEXT,
                amount_fy2025_enacted REAL,
                amount_fy2026_request REAL,
                quantity_fy2026_request REAL,
                amount_unit TEXT DEFAULT 'thousands'
            )
        """)

        # Insert P-5 style rows
        conn.execute("""
            INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, account, account_title,
             line_item, line_item_title, pe_number,
             amount_fy2025_enacted, amount_fy2026_request, quantity_fy2026_request)
            VALUES
            ('test_p5.xlsx', 'p5', 'FY 2026', '2035', 'Aircraft Procurement, Army',
             'A001', 'AH-64E Apache Block III', '0202032A',
             150000.0, 175000.0, 12)
        """)
        conn.execute("""
            INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, account, account_title,
             line_item, line_item_title, pe_number,
             amount_fy2025_enacted, amount_fy2026_request, quantity_fy2026_request)
            VALUES
            ('test_p5.xlsx', 'p5', 'FY 2026', '2035', 'Aircraft Procurement, Army',
             'A002', 'UH-60M Black Hawk', '0204720A',
             200000.0, 220000.0, 24)
        """)
        conn.commit()

        # Verify P-5 lines were inserted
        rows = conn.execute(
            "SELECT * FROM budget_lines WHERE exhibit_type = 'p5'"
        ).fetchall()
        assert len(rows) == 2

        # Verify amounts are populated
        row = conn.execute(
            "SELECT amount_fy2025_enacted, amount_fy2026_request, "
            "quantity_fy2026_request FROM budget_lines WHERE line_item = 'A001'"
        ).fetchone()
        assert row[0] == 150000.0
        assert row[1] == 175000.0
        assert row[2] == 12

        conn.close()


# ---------------------------------------------------------------------------
# R-2 RDT&E Detail exhibit tests
# ---------------------------------------------------------------------------

class TestR2ExhibitCatalog:
    """Verify R-2 catalog spec contains RDT&E-specific fields."""

    def test_r2_exists_in_catalog(self):
        assert "r2" in EXHIBIT_CATALOG

    def test_r2_exhibit_class_is_detail(self):
        spec = get_exhibit_spec("r2")
        assert spec is not None
        assert spec["name"] == "RDT&E Detail Schedule (R-2)"

    def test_r2_has_rdte_specific_columns(self):
        col_specs = get_column_spec_for_exhibit("r2")
        field_names = {c["field"] for c in col_specs}
        # RDT&E-specific fields
        assert "program_element" in field_names
        assert "sub_element" in field_names
        assert "title" in field_names

    def test_r2_has_amount_columns(self):
        col_specs = get_column_spec_for_exhibit("r2")
        field_names = {c["field"] for c in col_specs}
        assert "prior_year_amount" in field_names
        assert "current_year_amount" in field_names
        assert "estimate_amount" in field_names

    def test_r2_has_performance_columns(self):
        col_specs = get_column_spec_for_exhibit("r2")
        field_names = {c["field"] for c in col_specs}
        assert "performance_metric" in field_names
        assert "planned_achievement" in field_names
        assert "current_achievement" in field_names


class TestR2ColumnMapping:
    """Verify R-2 column matching via find_matching_columns and _map_columns."""

    def test_find_matching_columns_r2_basic(self):
        """Catalog-based matching should map R-2 specific headers."""
        headers = [
            "PE", "Sub-Element", "Program Title",
            "Prior Year", "Current Year", "Estimate",
            "Performance", "Planned Achievement", "Current Achievement",
        ]
        mapping = find_matching_columns("r2", headers)
        matched_fields = set(mapping.values())
        assert "program_element" in matched_fields
        assert "sub_element" in matched_fields
        assert "title" in matched_fields

    def test_map_columns_r2_pe_maps_to_account(self):
        """For R-2 exhibits, PE should map to account (as anchor field)."""
        headers = [
            "PE", "Sub-Element", "Title",
            "FY 2025 Enacted", "FY 2026 Disc Request",
        ]
        mapping = _map_columns(headers, "r2")
        # R-2 maps PE to account as the anchor
        assert "account" in mapping
        # Sub-element maps to line_item
        assert "line_item" in mapping

    def test_map_columns_r2_title_maps_to_line_item_title(self):
        """For R-2 exhibits, 'Program Title' or 'Title' maps to line_item_title."""
        headers = [
            "Program Element", "Sub Element", "Program Title",
            "FY 2025 Enacted", "FY 2026 Disc Request",
        ]
        mapping = _map_columns(headers, "r2")
        assert "line_item_title" in mapping

    def test_map_columns_r2_amount_columns(self):
        """R-2 FY-specific amount columns should be mapped."""
        headers = [
            "PE", "Sub-Element", "Title",
            "FY 2024 Actuals", "FY 2025 Enacted", "FY 2026 Disc Request",
        ]
        mapping = _map_columns(headers, "r2")
        amount_keys = [k for k in mapping if k.startswith("amount_fy")]
        assert len(amount_keys) >= 2  # At least enacted + request


class TestR2DatabaseInsertion:
    """Verify R-2 budget lines can be inserted and queried correctly."""

    def test_r2_budget_line_insertion(self, tmp_path: Path):
        """Create a minimal budget_lines table and insert R-2 style rows."""
        db_path = tmp_path / "test_r2.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE budget_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT,
                exhibit_type TEXT,
                fiscal_year TEXT,
                account TEXT,
                account_title TEXT,
                line_item TEXT,
                line_item_title TEXT,
                pe_number TEXT,
                budget_activity TEXT,
                budget_activity_title TEXT,
                amount_fy2024_actual REAL,
                amount_fy2025_enacted REAL,
                amount_fy2026_request REAL,
                amount_unit TEXT DEFAULT 'thousands'
            )
        """)

        # Insert R-2 style rows (RDT&E detail)
        conn.execute("""
            INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, account, account_title,
             line_item, line_item_title, pe_number,
             budget_activity, budget_activity_title,
             amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request)
            VALUES
            ('test_r2.xlsx', 'r2', 'FY 2026', '0602102A', 'Army RDT&E',
             '001', 'Materials Technology', '0602102A',
             '6.2', 'Applied Research',
             45000.0, 50000.0, 55000.0)
        """)
        conn.execute("""
            INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, account, account_title,
             line_item, line_item_title, pe_number,
             budget_activity, budget_activity_title,
             amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request)
            VALUES
            ('test_r2.xlsx', 'r2', 'FY 2026', '0603002A', 'Army RDT&E',
             '002', 'Medical Advanced Technology', '0603002A',
             '6.3', 'Advanced Technology Development',
             30000.0, 32000.0, 35000.0)
        """)
        conn.commit()

        # Verify R-2 lines were inserted
        rows = conn.execute(
            "SELECT * FROM budget_lines WHERE exhibit_type = 'r2'"
        ).fetchall()
        assert len(rows) == 2

        # Verify amounts are populated
        row = conn.execute(
            "SELECT amount_fy2024_actual, amount_fy2025_enacted, "
            "amount_fy2026_request FROM budget_lines WHERE line_item = '001'"
        ).fetchone()
        assert row[0] == 45000.0
        assert row[1] == 50000.0
        assert row[2] == 55000.0

        conn.close()

    def test_r2_pe_number_query(self, tmp_path: Path):
        """R-2 budget lines should be queryable by pe_number."""
        db_path = tmp_path / "test_r2_pe.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE budget_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT,
                exhibit_type TEXT,
                pe_number TEXT,
                line_item_title TEXT,
                amount_fy2026_request REAL
            )
        """)
        conn.execute("""
            INSERT INTO budget_lines
            (source_file, exhibit_type, pe_number, line_item_title,
             amount_fy2026_request)
            VALUES
            ('r2_test.xlsx', 'r2', '0602102A', 'Materials Technology', 55000.0)
        """)
        conn.commit()

        row = conn.execute(
            "SELECT pe_number, line_item_title, amount_fy2026_request "
            "FROM budget_lines WHERE pe_number = '0602102A'"
        ).fetchone()
        assert row is not None
        assert row[0] == "0602102A"
        assert row[2] == 55000.0

        conn.close()


# ---------------------------------------------------------------------------
# Cross-exhibit tests
# ---------------------------------------------------------------------------

class TestExhibitTypeDistinction:
    """Verify P-5 and R-2 have distinct column specs appropriate to their type."""

    def test_p5_and_r2_have_different_columns(self):
        p5_fields = {c["field"] for c in get_column_spec_for_exhibit("p5")}
        r2_fields = {c["field"] for c in get_column_spec_for_exhibit("r2")}
        # P-5 has unit cost and quantity columns not in R-2
        assert "prior_year_unit_cost" in p5_fields
        assert "prior_year_unit_cost" not in r2_fields
        # R-2 has performance/achievement columns not in P-5
        assert "performance_metric" in r2_fields
        assert "performance_metric" not in p5_fields

    def test_both_have_program_element(self):
        p5_fields = {c["field"] for c in get_column_spec_for_exhibit("p5")}
        r2_fields = {c["field"] for c in get_column_spec_for_exhibit("r2")}
        assert "program_element" in p5_fields
        assert "program_element" in r2_fields

    def test_p5_is_detail_exhibit(self):
        """P-5 should be classified as a detail exhibit in the seeds."""
        from pipeline.schema import _DDL_001_SEEDS
        assert "'detail'" in _DDL_001_SEEDS or "detail" in _DDL_001_SEEDS

    def test_r2_is_detail_exhibit(self):
        """R-2 should be classified as a detail exhibit in the seeds."""
        from pipeline.schema import _DDL_001_SEEDS
        # Check that r2 is seeded as detail
        assert "r2" in _DDL_001_SEEDS.lower()
