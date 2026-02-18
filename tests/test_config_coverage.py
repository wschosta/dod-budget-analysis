"""
Additional config tests — coverage gap fill

Tests for DatabaseConfig and DownloadConfig classes, plus
validate_budget_data's check functions against a controlled database.
"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.config import DatabaseConfig, DownloadConfig, Config


# ── DatabaseConfig tests ─────────────────────────────────────────────────────

class TestDatabaseConfig:
    def test_defaults(self):
        cfg = DatabaseConfig()
        assert cfg.db_path == Path("dod_budget.sqlite")
        assert cfg.wal_mode is True
        assert cfg.synchronous == "NORMAL"
        assert cfg.temp_store == "MEMORY"
        assert cfg.cache_size == -64000
        assert cfg.batch_size == 1000
        assert cfg.max_connections == 5

    def test_to_dict(self):
        cfg = DatabaseConfig()
        d = cfg.to_dict()
        assert "db_path" in d
        assert "wal_mode" in d
        assert "batch_size" in d

    def test_roundtrip_json(self, tmp_path):
        cfg = DatabaseConfig()
        cfg.batch_size = 500
        path = tmp_path / "db_config.json"
        cfg.save_json(path)

        loaded = Config.load_json(path)
        assert loaded.batch_size == 500


# ── DownloadConfig tests ─────────────────────────────────────────────────────

class TestDownloadConfig:
    def test_defaults(self):
        cfg = DownloadConfig()
        assert cfg.documents_dir == Path("DoD_Budget_Documents")
        assert cfg.cache_dir == Path(".discovery_cache")
        assert cfg.cache_ttl_hours == 24
        assert cfg.max_retries == 3
        assert cfg.backoff_factor == 2.0
        assert cfg.timeout_seconds == 30
        assert cfg.pool_connections == 10
        assert cfg.pool_maxsize == 20

    def test_to_dict(self):
        cfg = DownloadConfig()
        d = cfg.to_dict()
        assert "documents_dir" in d
        assert "max_retries" in d
        assert "timeout_seconds" in d

    def test_roundtrip_json(self, tmp_path):
        cfg = DownloadConfig()
        cfg.max_retries = 5
        cfg.timeout_seconds = 60
        path = tmp_path / "dl_config.json"
        cfg.save_json(path)

        loaded = Config.load_json(path)
        assert loaded.max_retries == 5
        assert loaded.timeout_seconds == 60


# ── validate_budget_data check functions ─────────────────────────────────────

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


@pytest.fixture()
def validation_db(tmp_path):
    """Create a database with budget_lines, pdf_pages, and ingested_files."""
    db_path = tmp_path / "test_validate.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            exhibit_type TEXT,
            sheet_name TEXT,
            fiscal_year TEXT,
            account TEXT,
            account_title TEXT,
            organization TEXT,
            organization_name TEXT,
            budget_activity TEXT,
            budget_activity_title TEXT,
            sub_activity TEXT,
            sub_activity_title TEXT,
            line_item TEXT,
            line_item_title TEXT,
            classification TEXT,
            amount_fy2024_actual REAL,
            amount_fy2025_enacted REAL,
            amount_fy2025_supplemental REAL,
            amount_fy2025_total REAL,
            amount_fy2026_request REAL,
            amount_fy2026_reconciliation REAL,
            amount_fy2026_total REAL
        );
        CREATE TABLE pdf_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT NOT NULL,
            source_category TEXT,
            page_number INTEGER,
            page_text TEXT,
            has_tables INTEGER DEFAULT 0,
            table_data TEXT
        );
        CREATE TABLE ingested_files (
            file_path TEXT PRIMARY KEY,
            file_type TEXT,
            file_size INTEGER,
            file_modified REAL,
            ingested_at TEXT,
            row_count INTEGER,
            status TEXT DEFAULT 'ok',
            source_url TEXT
        );
    """)
    # Insert test data
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


class TestCheckDatabaseStats:
    def test_non_empty_db(self, validation_db):
        conn = sqlite3.connect(str(validation_db))
        result = check_database_stats(conn)
        conn.close()
        assert result["status"] == "pass"
        assert result["details"]["budget_lines"] == 2

    def test_empty_db(self, tmp_path):
        db = tmp_path / "empty.sqlite"
        conn = sqlite3.connect(str(db))
        conn.executescript("""
            CREATE TABLE budget_lines (id INTEGER PRIMARY KEY);
            CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY);
            CREATE TABLE ingested_files (file_path TEXT PRIMARY KEY);
        """)
        result = check_database_stats(conn)
        conn.close()
        assert result["status"] == "fail"


class TestCheckDuplicateRows:
    def test_no_duplicates(self, validation_db):
        conn = sqlite3.connect(str(validation_db))
        result = check_duplicate_rows(conn)
        conn.close()
        assert result["status"] == "pass"


class TestCheckNullHeavyRows:
    def test_with_valid_data(self, validation_db):
        conn = sqlite3.connect(str(validation_db))
        result = check_null_heavy_rows(conn)
        conn.close()
        assert result["status"] == "pass"


class TestCheckUnknownExhibitTypes:
    def test_known_types(self, validation_db):
        conn = sqlite3.connect(str(validation_db))
        result = check_unknown_exhibit_types(conn)
        conn.close()
        assert result["status"] == "pass"


class TestCheckValueRanges:
    def test_normal_values(self, validation_db):
        conn = sqlite3.connect(str(validation_db))
        result = check_value_ranges(conn)
        conn.close()
        assert result["status"] == "pass"


class TestCheckRowCountConsistency:
    def test_consistent_counts(self, validation_db):
        conn = sqlite3.connect(str(validation_db))
        result = check_row_count_consistency(conn)
        conn.close()
        assert result["name"] == "row_count_consistency"


class TestCheckFiscalYearCoverage:
    def test_with_data(self, validation_db):
        conn = sqlite3.connect(str(validation_db))
        result = check_fiscal_year_coverage(conn)
        conn.close()
        assert result["name"] == "fiscal_year_coverage"


class TestCheckColumnTypes:
    def test_numeric_columns(self, validation_db):
        conn = sqlite3.connect(str(validation_db))
        result = check_column_types(conn)
        conn.close()
        assert result["status"] == "pass"


class TestValidateAll:
    def test_runs_all_checks(self, validation_db):
        summary = validate_all(validation_db)
        assert summary["total_checks"] == 8
        assert "checks" in summary
        assert "exit_code" in summary


class TestGenerateQualityReport:
    def test_generates_report(self, validation_db):
        output_path = validation_db.parent / "report.json"
        report = generate_quality_report(
            validation_db, output_path, print_console=False
        )
        assert "timestamp" in report
        assert "total_budget_lines" in report
        assert report["total_budget_lines"] == 2
        assert output_path.exists()

        # Verify JSON is valid
        data = json.loads(output_path.read_text())
        assert data["total_budget_lines"] == 2
