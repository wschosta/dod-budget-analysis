"""Tests for utils/validation.py — check_summary_detail_consistency and
check_yoy_outliers.

These are the untested validation checks (VAL-001 and VAL-002) that operate
on budget_lines data.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.validation import (
    check_summary_detail_consistency,
    check_yoy_outliers,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def db():
    """In-memory SQLite with budget_lines table matching expected schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            exhibit_type TEXT,
            organization_name TEXT,
            fiscal_year TEXT,
            pe_number TEXT,
            line_item_title TEXT,
            amount_fy2024_actual REAL,
            amount_fy2025_enacted REAL,
            amount_fy2026_request REAL
        )
    """)
    conn.commit()
    yield conn
    conn.close()


def _insert(conn, **kwargs):
    """Insert a budget_lines row with defaults for missing fields."""
    defaults = {
        "source_file": "test.xlsx",
        "exhibit_type": "p1",
        "organization_name": "Army",
        "fiscal_year": "FY 2026",
        "pe_number": "0602120A",
        "line_item_title": "Test Program",
        "amount_fy2024_actual": None,
        "amount_fy2025_enacted": None,
        "amount_fy2026_request": None,
    }
    defaults.update(kwargs)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join("?" for _ in defaults)
    conn.execute(
        f"INSERT INTO budget_lines ({cols}) VALUES ({placeholders})",
        tuple(defaults.values()),
    )
    conn.commit()


# ── check_summary_detail_consistency ─────────────────────────────────────────


class TestCheckSummaryDetailConsistency:
    def test_no_data_returns_empty(self, db):
        """Empty table produces no issues."""
        issues = check_summary_detail_consistency(db)
        assert issues == []

    def test_matching_totals_no_issues(self, db):
        """When P-1 and P-5 totals match, no issues reported."""
        _insert(db, exhibit_type="p1", organization_name="Army",
                fiscal_year="FY 2026", amount_fy2026_request=1000.0)
        _insert(db, exhibit_type="p5", organization_name="Army",
                fiscal_year="FY 2026", amount_fy2026_request=1000.0)
        issues = check_summary_detail_consistency(db)
        assert len(issues) == 0

    def test_small_difference_within_tolerance(self, db):
        """Differences within 5% tolerance should not be flagged."""
        _insert(db, exhibit_type="p1", organization_name="Army",
                fiscal_year="FY 2026", amount_fy2026_request=1000.0)
        _insert(db, exhibit_type="p5", organization_name="Army",
                fiscal_year="FY 2026", amount_fy2026_request=1040.0)
        issues = check_summary_detail_consistency(db)
        assert len(issues) == 0  # 4% diff < 5% tolerance

    def test_large_difference_flagged(self, db):
        """Differences exceeding tolerance should produce a warning."""
        _insert(db, exhibit_type="p1", organization_name="Army",
                fiscal_year="FY 2026", amount_fy2026_request=1000.0)
        _insert(db, exhibit_type="p5", organization_name="Army",
                fiscal_year="FY 2026", amount_fy2026_request=500.0)
        issues = check_summary_detail_consistency(db)
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert "P-1 vs P-5" in issues[0].detail

    def test_r1_r2_pair(self, db):
        """R-1 vs R-2 pair is also checked."""
        _insert(db, exhibit_type="r1", organization_name="Navy",
                fiscal_year="FY 2026", amount_fy2026_request=2000.0)
        _insert(db, exhibit_type="r2", organization_name="Navy",
                fiscal_year="FY 2026", amount_fy2026_request=800.0)
        issues = check_summary_detail_consistency(db)
        assert any("R-1 vs R-2" in i.detail for i in issues)

    def test_zero_summary_total_skipped(self, db):
        """Zero summary total shouldn't cause division by zero."""
        _insert(db, exhibit_type="p1", organization_name="Army",
                fiscal_year="FY 2026", amount_fy2026_request=0.0)
        _insert(db, exhibit_type="p5", organization_name="Army",
                fiscal_year="FY 2026", amount_fy2026_request=100.0)
        issues = check_summary_detail_consistency(db)
        # Zero summary is skipped — should not flag
        assert len(issues) == 0

    def test_missing_detail_no_issue(self, db):
        """If only summary exists (no matching detail), no issue reported."""
        _insert(db, exhibit_type="p1", organization_name="Army",
                fiscal_year="FY 2026", amount_fy2026_request=1000.0)
        issues = check_summary_detail_consistency(db)
        assert len(issues) == 0

    def test_custom_tolerance(self, db):
        """Custom tolerance parameter is respected."""
        _insert(db, exhibit_type="p1", organization_name="Army",
                fiscal_year="FY 2026", amount_fy2026_request=1000.0)
        _insert(db, exhibit_type="p5", organization_name="Army",
                fiscal_year="FY 2026", amount_fy2026_request=900.0)
        # 10% diff should pass at 15% tolerance
        issues_loose = check_summary_detail_consistency(db, tolerance=0.15)
        assert len(issues_loose) == 0
        # 10% diff should fail at 5% tolerance
        issues_tight = check_summary_detail_consistency(db, tolerance=0.05)
        assert len(issues_tight) == 1

    def test_exception_handling(self):
        """If table doesn't exist, returns an issue instead of crashing."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        issues = check_summary_detail_consistency(conn)
        # Should get warning about not being able to run the check
        assert len(issues) >= 1
        assert any("Could not run" in i.detail for i in issues)
        conn.close()


# ── check_yoy_outliers ──────────────────────────────────────────────────────


class TestCheckYoyOutliers:
    def test_no_data_returns_empty(self, db):
        issues = check_yoy_outliers(db)
        assert issues == []

    def test_small_change_no_outlier(self, db):
        """20% change should not be flagged at 50% threshold."""
        _insert(db, amount_fy2025_enacted=100.0, amount_fy2026_request=120.0)
        issues = check_yoy_outliers(db)
        assert issues == []

    def test_large_change_flagged(self, db):
        """200% change should be flagged."""
        _insert(db, amount_fy2025_enacted=100.0, amount_fy2026_request=300.0)
        issues = check_yoy_outliers(db)
        assert len(issues) == 1
        assert issues[0].severity == "warning"
        assert "yoy_outliers" == issues[0].check_name

    def test_decrease_flagged(self, db):
        """Large decreases should also be flagged."""
        _insert(db, amount_fy2025_enacted=1000.0, amount_fy2026_request=100.0)
        issues = check_yoy_outliers(db)
        assert len(issues) == 1

    def test_null_enacted_skipped(self, db):
        """NULL FY2025 enacted should be excluded from check."""
        _insert(db, amount_fy2025_enacted=None, amount_fy2026_request=100.0)
        issues = check_yoy_outliers(db)
        assert issues == []

    def test_zero_enacted_skipped(self, db):
        """Zero FY2025 enacted should not cause division by zero."""
        _insert(db, amount_fy2025_enacted=0.0, amount_fy2026_request=100.0)
        issues = check_yoy_outliers(db)
        assert issues == []

    def test_null_request_skipped(self, db):
        """NULL FY2026 request should be excluded from check."""
        _insert(db, amount_fy2025_enacted=100.0, amount_fy2026_request=None)
        issues = check_yoy_outliers(db)
        assert issues == []

    def test_custom_threshold(self, db):
        """Custom threshold parameter is respected."""
        _insert(db, amount_fy2025_enacted=100.0, amount_fy2026_request=130.0)
        # 30% change should be flagged at 20% threshold
        issues_tight = check_yoy_outliers(db, threshold=0.2)
        assert len(issues_tight) == 1
        # 30% change should not be flagged at 50% threshold
        issues_loose = check_yoy_outliers(db, threshold=0.5)
        assert len(issues_loose) == 0

    def test_issue_count_matches_rows(self, db):
        """Issue count field should reflect the number of outlier rows."""
        for i in range(5):
            _insert(
                db, pe_number=f"PE{i:04d}X",
                amount_fy2025_enacted=100.0,
                amount_fy2026_request=500.0,
            )
        issues = check_yoy_outliers(db)
        assert len(issues) == 1  # Single issue with count=5
        assert issues[0].count == 5

    def test_issue_includes_sample(self, db):
        """Issue sample should include first outlier row details."""
        _insert(
            db, pe_number="0602120A", line_item_title="Cyber Research",
            amount_fy2025_enacted=100.0, amount_fy2026_request=500.0,
        )
        issues = check_yoy_outliers(db)
        assert issues[0].sample is not None
        assert issues[0].sample["pe_number"] == "0602120A"

    def test_exception_handling(self):
        """If table doesn't exist, returns warning instead of crashing."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        issues = check_yoy_outliers(conn)
        assert len(issues) == 1
        assert "Could not run" in issues[0].detail
        conn.close()
