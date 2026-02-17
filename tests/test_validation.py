"""
Tests for validate_budget_data.py validation checks.

Uses an in-memory SQLite database with the same schema as build_budget_db.py.
"""
import sqlite3
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Stub pdfplumber to avoid cryptography import issues
if "pdfplumber" not in sys.modules:
    sys.modules.setdefault("pdfplumber", types.ModuleType("pdfplumber"))

from build_budget_db import create_database
from validate_budget_data import (
    check_database_stats,
    check_duplicate_rows,
    check_null_heavy_rows,
    check_unknown_exhibit_types,
    check_value_ranges,
    check_row_count_consistency,
)


@pytest.fixture
def db():
    """Create an in-memory database with the production schema."""
    conn = create_database(Path(":memory:"))
    yield conn
    conn.close()


def _insert_budget_line(conn, **overrides):
    """Insert a budget_lines row with sensible defaults."""
    defaults = {
        "source_file": "test/p1.xlsx",
        "exhibit_type": "p1",
        "sheet_name": "Sheet1",
        "fiscal_year": "FY 2026",
        "account": "2035",
        "account_title": "Aircraft Procurement",
        "organization": "A",
        "organization_name": "Army",
        "budget_activity": "01",
        "budget_activity_title": "Combat Aircraft",
        "line_item": "001",
        "line_item_title": "AH-64 Apache",
        "amount_fy2026_request": 1500.0,
    }
    defaults.update(overrides)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join("?" for _ in defaults)
    conn.execute(f"INSERT INTO budget_lines ({cols}) VALUES ({placeholders})",
                 list(defaults.values()))
    conn.commit()


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_database_stats_empty(db):
    result = check_database_stats(db)
    assert result["status"] == "fail"
    assert result["details"]["budget_lines"] == 0


def test_database_stats_with_data(db):
    _insert_budget_line(db)
    result = check_database_stats(db)
    assert result["status"] == "pass"
    assert result["details"]["budget_lines"] == 1


def test_duplicate_rows_none(db):
    _insert_budget_line(db, line_item="001")
    _insert_budget_line(db, line_item="002")
    result = check_duplicate_rows(db)
    assert result["status"] == "pass"


def test_duplicate_rows_found(db):
    _insert_budget_line(db, line_item="001")
    _insert_budget_line(db, line_item="001")  # exact duplicate key
    result = check_duplicate_rows(db)
    assert result["status"] == "warn"
    assert len(result["details"]) == 1
    assert result["details"][0]["cnt"] == 2


def test_null_heavy_rows_clean(db):
    _insert_budget_line(db, amount_fy2026_request=1500.0)
    result = check_null_heavy_rows(db)
    assert result["status"] == "pass"


def test_null_heavy_rows_flagged(db):
    # Insert 10 rows with zero amounts + 1 with a real amount
    for i in range(10):
        _insert_budget_line(db, line_item=f"zero_{i}", amount_fy2026_request=None)
    _insert_budget_line(db, line_item="real", amount_fy2026_request=500.0)
    result = check_null_heavy_rows(db)
    # 10/11 = 90.9% > 10% threshold
    assert result["status"] == "warn"


def test_unknown_exhibit_types_clean(db):
    _insert_budget_line(db, exhibit_type="p1")
    result = check_unknown_exhibit_types(db)
    assert result["status"] == "pass"


def test_unknown_exhibit_types_found(db):
    _insert_budget_line(db, exhibit_type="unknown")
    result = check_unknown_exhibit_types(db)
    assert result["status"] == "warn"
    assert result["details"][0]["exhibit_type"] == "unknown"


def test_value_ranges_clean(db):
    _insert_budget_line(db, amount_fy2026_request=500000.0)  # $500M in thousands
    result = check_value_ranges(db)
    assert result["status"] == "pass"


def test_value_ranges_extreme(db):
    _insert_budget_line(db, amount_fy2026_request=2_000_000_000.0)  # $2T
    result = check_value_ranges(db)
    assert result["status"] == "warn"
    assert len(result["details"]) >= 1


def test_row_count_consistency_clean(db):
    _insert_budget_line(db)
    db.execute("""
        INSERT INTO ingested_files (file_path, file_type, row_count)
        VALUES ('test/p1.xlsx', 'excel', 1)
    """)
    db.commit()
    result = check_row_count_consistency(db)
    assert result["status"] == "pass"


def test_row_count_consistency_mismatch(db):
    _insert_budget_line(db)
    db.execute("""
        INSERT INTO ingested_files (file_path, file_type, row_count)
        VALUES ('test/p1.xlsx', 'excel', 99)
    """)
    db.commit()
    result = check_row_count_consistency(db)
    assert result["status"] == "warn"
    assert result["details"][0]["expected"] == 99
    assert result["details"][0]["actual"] == 1
