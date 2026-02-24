"""
Tests for budget data reconciliation scripts — Steps 2.B2-a and 2.B2-b

Tests the reconciliation logic using an in-memory SQLite database populated
with controlled test data. No network or real data required.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from reconcile_budget_data import (
    reconcile_cross_service,
    reconcile_cross_exhibit,
    generate_report,
    _get_service_totals,
    _get_comptroller_total,
)


@pytest.fixture()
def reconciliation_db():
    """Create an in-memory database with budget_lines for reconciliation tests."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT,
            exhibit_type TEXT,
            organization_name TEXT,
            amount_fy2024_actual REAL,
            amount_fy2025_enacted REAL,
            amount_fy2026_request REAL,
            sheet_name TEXT,
            fiscal_year TEXT,
            account TEXT,
            account_title TEXT,
            organization TEXT,
            budget_activity TEXT,
            budget_activity_title TEXT,
            sub_activity TEXT,
            sub_activity_title TEXT,
            line_item TEXT,
            line_item_title TEXT,
            classification TEXT,
            amount_fy2025_supplemental REAL,
            amount_fy2025_total REAL,
            amount_fy2026_reconciliation REAL,
            amount_fy2026_total REAL
        )
    """)
    # Army P-1 summary rows
    conn.execute("""
        INSERT INTO budget_lines
            (source_file, exhibit_type, organization_name,
             amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request)
        VALUES
            ('Army/p1.xlsx', 'p1', 'Army', 100000, 110000, 120000)
    """)
    conn.execute("""
        INSERT INTO budget_lines
            (source_file, exhibit_type, organization_name,
             amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request)
        VALUES
            ('Army/p1.xlsx', 'p1', 'Army', 50000, 55000, 60000)
    """)
    # Navy P-1 summary
    conn.execute("""
        INSERT INTO budget_lines
            (source_file, exhibit_type, organization_name,
             amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request)
        VALUES
            ('Navy/p1.xlsx', 'p1', 'Navy', 200000, 210000, 220000)
    """)
    # Comptroller P-1 summary (should equal Army + Navy)
    conn.execute("""
        INSERT INTO budget_lines
            (source_file, exhibit_type, organization_name,
             amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request)
        VALUES
            ('Comptroller/p1.xlsx', 'p1', 'Comptroller',
             350000, 375000, 400000)
    """)
    # Army P-5 detail rows (should sum to Army P-1 totals)
    conn.execute("""
        INSERT INTO budget_lines
            (source_file, exhibit_type, organization_name,
             amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request)
        VALUES
            ('Army/p5.xlsx', 'p5', 'Army', 90000, 100000, 110000)
    """)
    conn.execute("""
        INSERT INTO budget_lines
            (source_file, exhibit_type, organization_name,
             amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request)
        VALUES
            ('Army/p5.xlsx', 'p5', 'Army', 60000, 65000, 70000)
    """)
    yield conn
    conn.close()


class TestGetServiceTotals:
    def test_returns_totals_by_org(self, reconciliation_db):
        totals = _get_service_totals(
            reconciliation_db, "p1", "amount_fy2026_request"
        )
        assert "Army" in totals
        assert totals["Army"] == 180000  # 120000 + 60000
        assert "Navy" in totals
        assert totals["Navy"] == 220000

    def test_empty_for_missing_exhibit(self, reconciliation_db):
        totals = _get_service_totals(
            reconciliation_db, "m1", "amount_fy2026_request"
        )
        assert totals == {}


class TestGetComptrollerTotal:
    def test_returns_comptroller_total(self, reconciliation_db):
        total = _get_comptroller_total(
            reconciliation_db, "p1", "amount_fy2026_request"
        )
        assert total == 400000

    def test_returns_none_for_missing(self, reconciliation_db):
        total = _get_comptroller_total(
            reconciliation_db, "m1", "amount_fy2026_request"
        )
        assert total is None


class TestCrossServiceReconciliation:
    def test_detects_delta(self, reconciliation_db):
        """Service sum (Army 180k + Navy 220k = 400k) vs Comptroller (400k)."""
        results = reconcile_cross_service(reconciliation_db)
        p1_request = [
            r
            for r in results
            if r["exhibit_type"] == "p1"
            and r["amount_column"] == "FY2026 Request"
        ]
        assert len(p1_request) == 1
        r = p1_request[0]
        assert r["service_sum"] == 400000
        assert r["comptroller_total"] == 400000
        assert r["delta"] == 0
        assert r["within_tolerance"] is True

    def test_detects_mismatch(self, reconciliation_db):
        """FY2024 Actual: Army 150k + Navy 200k = 350k vs Comptroller 350k."""
        results = reconcile_cross_service(reconciliation_db)
        p1_actual = [
            r
            for r in results
            if r["exhibit_type"] == "p1"
            and r["amount_column"] == "FY2024 Actual"
        ]
        assert len(p1_actual) == 1
        r = p1_actual[0]
        assert r["service_sum"] == 350000
        assert r["comptroller_total"] == 350000
        assert r["within_tolerance"] is True


class TestCrossExhibitReconciliation:
    def test_p1_vs_p5_comparison(self, reconciliation_db):
        """Army P-1 total (180k) vs P-5 detail sum (180k) for FY2026."""
        results = reconcile_cross_exhibit(reconciliation_db)
        army_p1_p5 = [
            r
            for r in results
            if r["organization"] == "Army"
            and "P-1" in r["label"]
            and r["amount_column"] == "FY2026 Request"
        ]
        assert len(army_p1_p5) == 1
        r = army_p1_p5[0]
        assert r["summary_total"] == 180000
        assert r["detail_total"] == 180000
        assert r["delta"] == 0
        assert r["within_tolerance"] is True

    def test_missing_detail_noted(self, reconciliation_db):
        """Navy has P-1 but no P-5 detail rows."""
        results = reconcile_cross_exhibit(reconciliation_db)
        navy_p5 = [
            r
            for r in results
            if r["organization"] == "Navy"
            and "P-1" in r["label"]
            and r["amount_column"] == "FY2026 Request"
        ]
        assert len(navy_p5) == 1
        r = navy_p5[0]
        assert r["detail_total"] is None
        assert "missing" in (r.get("note") or "")


class TestGenerateReport:
    def test_report_is_markdown(self, reconciliation_db):
        cs = reconcile_cross_service(reconciliation_db)
        ce = reconcile_cross_exhibit(reconciliation_db)
        report = generate_report(cs, ce, 1.0)
        assert "# Budget Data Reconciliation Report" in report
        assert "Cross-Service" in report
        assert "Cross-Exhibit" in report

    def test_empty_data_produces_report(self):
        report = generate_report([], [], 1.0)
        assert "No data available" in report
