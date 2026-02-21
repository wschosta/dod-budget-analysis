"""
Tests for backfill_reference_tables.py — Step 2.B1-b

Verifies the backfill logic populates reference tables from budget_lines
data with correct classification and deduplication.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backfill_reference_tables import backfill, main


def _create_test_db(conn: sqlite3.Connection) -> None:
    """Create tables needed for backfill testing."""
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT,
            exhibit_type TEXT,
            organization_name TEXT,
            account TEXT,
            account_title TEXT
        );

        CREATE TABLE services_agencies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            full_name TEXT NOT NULL,
            category TEXT NOT NULL
        );

        CREATE TABLE exhibit_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            exhibit_class TEXT NOT NULL,
            description TEXT
        );

        CREATE TABLE appropriation_titles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            color_of_money TEXT
        );
    """)


@pytest.fixture()
def backfill_db():
    """In-memory database with test data for backfill."""
    conn = sqlite3.connect(":memory:")
    _create_test_db(conn)
    # Insert test budget_lines data
    conn.executemany(
        """INSERT INTO budget_lines
           (source_file, exhibit_type, organization_name, account, account_title)
           VALUES (?, ?, ?, ?, ?)""",
        [
            ("army/p1.xlsx", "p1", "Army", "2035", "Aircraft Procurement, Army"),
            ("army/p1.xlsx", "p1", "Army", "2035", "Aircraft Procurement, Army"),
            ("navy/r1.xlsx", "r1", "Navy", "1319", "RDT&E, Navy"),
            ("dw/o1.xlsx", "o1", "Defense-Wide", "0400", "Operation and Maintenance, DW"),
            ("af/m1.xlsx", "m1", "Air Force", "3400", "Military Personnel, AF"),
            ("mc/c1.xlsx", "c1", "Marine Corps", "1235", "MilCon, Marine Corps"),
        ],
    )
    conn.commit()
    yield conn
    conn.close()


class TestBackfill:
    def test_services_agencies_populated(self, backfill_db):
        summary = backfill(backfill_db)
        assert summary["services_agencies"] == 5  # Army, Navy, DW, AF, MC

        rows = backfill_db.execute(
            "SELECT code, category FROM services_agencies ORDER BY code"
        ).fetchall()
        codes = {r[0] for r in rows}
        assert "Army" in codes
        assert "Navy" in codes
        assert "Air Force" in codes
        assert "Marine Corps" in codes
        assert "Defense-Wide" in codes

    def test_military_dept_classification(self, backfill_db):
        backfill(backfill_db)
        row = backfill_db.execute(
            "SELECT category FROM services_agencies WHERE code = 'Army'"
        ).fetchone()
        assert row[0] == "Military Department"

    def test_defense_agency_classification(self, backfill_db):
        backfill(backfill_db)
        row = backfill_db.execute(
            "SELECT category FROM services_agencies WHERE code = 'Defense-Wide'"
        ).fetchone()
        assert row[0] == "Defense Agency"

    def test_exhibit_types_populated(self, backfill_db):
        summary = backfill(backfill_db)
        assert summary["exhibit_types"] == 5  # p1, r1, o1, m1, c1

        rows = backfill_db.execute(
            "SELECT code, display_name FROM exhibit_types ORDER BY code"
        ).fetchall()
        codes = {r[0] for r in rows}
        assert "p1" in codes
        assert "r1" in codes
        assert "c1" in codes

    def test_appropriation_titles_populated(self, backfill_db):
        summary = backfill(backfill_db)
        # 2035, 1319, 0400, 3400, 1235 = 5 unique accounts
        assert summary["appropriation_titles"] == 5

    def test_deduplication(self, backfill_db):
        """Duplicate org names in budget_lines produce one row in services_agencies."""
        backfill(backfill_db)
        count = backfill_db.execute(
            "SELECT COUNT(*) FROM services_agencies WHERE code = 'Army'"
        ).fetchone()[0]
        assert count == 1

    def test_dry_run_no_changes(self, backfill_db):
        summary = backfill(backfill_db, dry_run=True)
        assert summary["services_agencies"] == 5

        # But nothing was actually inserted
        count = backfill_db.execute(
            "SELECT COUNT(*) FROM services_agencies"
        ).fetchone()[0]
        assert count == 0

    def test_idempotent(self, backfill_db):
        """Running backfill twice doesn't create duplicates."""
        backfill(backfill_db)
        backfill(backfill_db)  # second run
        count = backfill_db.execute(
            "SELECT COUNT(*) FROM services_agencies"
        ).fetchone()[0]
        assert count == 5

    def test_empty_budget_lines(self):
        conn = sqlite3.connect(":memory:")
        _create_test_db(conn)
        summary = backfill(conn)
        assert summary["services_agencies"] == 0
        assert summary["exhibit_types"] == 0
        assert summary["appropriation_titles"] == 0
        conn.close()


class TestMainCli:
    def test_dry_run(self, tmp_path):
        """CLI --dry-run mode prints counts but doesn't modify DB."""
        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        _create_test_db(conn)
        conn.execute(
            "INSERT INTO budget_lines "
            "(source_file, exhibit_type, organization_name, account, account_title) "
            "VALUES ('a.xlsx', 'p1', 'Army', '2035', 'Procurement')"
        )
        conn.commit()
        conn.close()

        exit_code = main(["--db", str(db_path), "--dry-run"])
        assert exit_code == 0

        # Verify nothing was inserted
        conn = sqlite3.connect(str(db_path))
        count = conn.execute(
            "SELECT COUNT(*) FROM services_agencies"
        ).fetchone()[0]
        conn.close()
        assert count == 0

    def test_missing_database(self, tmp_path):
        exit_code = main(["--db", str(tmp_path / "missing.sqlite")])
        assert exit_code == 1
