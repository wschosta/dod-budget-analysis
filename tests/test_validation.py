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
    check_fiscal_year_coverage,
    check_column_types,
    validate_all,
    generate_quality_report,
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


# ── Additional check functions (consolidated from test_config_coverage.py) ───

@pytest.fixture()
def populated_db_path(tmp_path):
    """Create a file-backed database with budget_lines, pdf_pages, ingested_files."""
    db_path = tmp_path / "test_validate.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL, exhibit_type TEXT, sheet_name TEXT,
            fiscal_year TEXT, account TEXT, account_title TEXT,
            organization TEXT, organization_name TEXT,
            budget_activity TEXT, budget_activity_title TEXT,
            sub_activity TEXT, sub_activity_title TEXT,
            line_item TEXT, line_item_title TEXT,
            classification TEXT,
            amount_fy2024_actual REAL, amount_fy2025_enacted REAL,
            amount_fy2025_supplemental REAL, amount_fy2025_total REAL,
            amount_fy2026_request REAL, amount_fy2026_reconciliation REAL,
            amount_fy2026_total REAL
        );
        CREATE TABLE pdf_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL, source_category TEXT,
            page_number INTEGER, page_text TEXT,
            has_tables INTEGER DEFAULT 0, table_data TEXT
        );
        CREATE TABLE ingested_files (
            file_path TEXT PRIMARY KEY, file_type TEXT,
            file_size INTEGER, file_modified REAL, ingested_at TEXT,
            row_count INTEGER, status TEXT DEFAULT 'ok', source_url TEXT
        );
    """)
    conn.execute("""
        INSERT INTO budget_lines
            (source_file, exhibit_type, organization_name, fiscal_year,
             account, line_item, sheet_name,
             amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request)
        VALUES ('army/p1.xlsx', 'p1', 'Army', '2026',
                '2035', 'L001', 'Sheet1', 12345.0, 13456.0, 14000.0)
    """)
    conn.execute("""
        INSERT INTO budget_lines
            (source_file, exhibit_type, organization_name, fiscal_year,
             account, line_item, sheet_name,
             amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request)
        VALUES ('navy/r1.xlsx', 'r1', 'Navy', '2026',
                '1300', 'L002', 'Sheet1', 45000.0, 47000.0, 48500.0)
    """)
    conn.execute("""
        INSERT INTO ingested_files (file_path, file_type, row_count)
        VALUES ('army/p1.xlsx', 'excel', 1)
    """)
    conn.execute("""
        INSERT INTO ingested_files (file_path, file_type, row_count)
        VALUES ('navy/r1.xlsx', 'excel', 1)
    """)
    conn.commit()
    conn.close()
    return db_path


def test_fiscal_year_coverage(populated_db_path):
    conn = sqlite3.connect(str(populated_db_path))
    result = check_fiscal_year_coverage(conn)
    conn.close()
    assert result["name"] == "fiscal_year_coverage"


def test_column_types_valid(populated_db_path):
    conn = sqlite3.connect(str(populated_db_path))
    result = check_column_types(conn)
    conn.close()
    assert result["status"] == "pass"


def test_validate_all_runs_all_checks(populated_db_path):
    summary = validate_all(populated_db_path)
    assert summary["total_checks"] == 8
    assert "checks" in summary
    assert "exit_code" in summary


def test_generate_quality_report(populated_db_path):
    output_path = populated_db_path.parent / "report.json"
    report = generate_quality_report(
        populated_db_path, output_path, print_console=False
    )
    assert "timestamp" in report
    assert "total_budget_lines" in report
    assert report["total_budget_lines"] == 2
    assert output_path.exists()
