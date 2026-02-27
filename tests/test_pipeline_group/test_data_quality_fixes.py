"""
Tests for scripts/fix_data_quality.py — Round 5 data quality fixes.

Verifies each migration step works correctly on synthetic data:
  0. *a.xlsx alternate file removal
  1. Cross-file deduplication
  2. Appropriation code backfill
  3. Budget type backfill
  4. Empty organization name fill
  5. Appropriation titles reference table cleanup
  6. NULL title row handling
  7. FTS rebuild (smoke test)
"""
import sqlite3

import pytest


# ---------------------------------------------------------------------------
# Schema helper — creates the minimal budget_lines + ref tables for testing
# ---------------------------------------------------------------------------

def _create_schema(conn: sqlite3.Connection) -> None:
    """Create a minimal schema for data quality fix tests."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS budget_lines (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            fiscal_year         INTEGER,
            pe_number           TEXT,
            line_item_title     TEXT,
            organization_name   TEXT,
            exhibit_type        TEXT,
            amount_type         TEXT,
            appropriation_code  TEXT,
            appropriation_title TEXT,
            account_title       TEXT,
            budget_type         TEXT,
            source_file         TEXT,
            amount              REAL
        );

        CREATE TABLE IF NOT EXISTS ingested_files (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path   TEXT NOT NULL UNIQUE,
            file_type   TEXT,
            row_count   INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS appropriation_titles (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            code  TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            color_of_money TEXT
        );
    """)


def _insert_rows(conn: sqlite3.Connection, rows: list[dict]) -> None:
    """Insert rows into budget_lines from a list of dicts."""
    cols = [
        "fiscal_year", "pe_number", "line_item_title", "organization_name",
        "exhibit_type", "amount_type", "appropriation_code",
        "appropriation_title", "account_title", "budget_type",
        "source_file", "amount",
    ]
    placeholders = ", ".join("?" * len(cols))
    col_names = ", ".join(cols)
    for row in rows:
        vals = [row.get(c) for c in cols]
        conn.execute(
            f"INSERT INTO budget_lines ({col_names}) VALUES ({placeholders})",
            vals,
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def dq_db():
    """In-memory database with schema for data quality tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _create_schema(conn)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Step 0: Remove *a.xlsx alternate files
# ---------------------------------------------------------------------------

class TestStep0RemoveAlternateFiles:
    def test_removes_alternate_files(self, dq_db):
        from scripts.fix_data_quality import step_0_remove_alternate_files

        _insert_rows(dq_db, [
            {"fiscal_year": 2014, "pe_number": "PE1", "line_item_title": "Item A",
             "organization_name": "Army", "exhibit_type": "r1",
             "source_file": "FY2014\\PB\\Comptroller\\summary\\r1.xlsx",
             "amount": 100.0},
            {"fiscal_year": 2014, "pe_number": "PE1", "line_item_title": "Item A",
             "organization_name": "Army", "exhibit_type": "r1",
             "source_file": "FY2014\\PB\\Comptroller\\summary\\r1a.xlsx",
             "amount": 100.0},
            {"fiscal_year": 2014, "pe_number": "PE2", "line_item_title": "Item B",
             "organization_name": "Navy", "exhibit_type": "p1",
             "source_file": "FY2014\\PB\\Comptroller\\summary\\p1a.xlsx",
             "amount": 200.0},
        ])
        dq_db.execute(
            "INSERT INTO ingested_files (file_path, file_type, row_count) "
            "VALUES ('FY2014\\PB\\Comptroller\\summary\\r1a.xlsx', 'xlsx', 1)"
        )
        dq_db.commit()

        removed = step_0_remove_alternate_files(dq_db)
        assert removed == 2  # r1a.xlsx row + p1a.xlsx row

        remaining = dq_db.execute(
            "SELECT COUNT(*) FROM budget_lines"
        ).fetchone()[0]
        assert remaining == 1  # Only r1.xlsx row survives

    def test_does_not_remove_non_alternate_files(self, dq_db):
        from scripts.fix_data_quality import step_0_remove_alternate_files

        _insert_rows(dq_db, [
            {"fiscal_year": 2020, "pe_number": "PE1", "line_item_title": "Item A",
             "organization_name": "Navy", "exhibit_type": "r1",
             "source_file": "FY2020/PB/navy/r1.xlsx", "amount": 100.0},
            {"fiscal_year": 2020, "pe_number": "PE2", "line_item_title": "Item B",
             "organization_name": "Defense-Wide", "exhibit_type": "r1",
             "source_file": "FY2020/PB/disa/r1.xlsx", "amount": 200.0},
        ])

        removed = step_0_remove_alternate_files(dq_db)
        assert removed == 0
        assert dq_db.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0] == 2

    def test_dry_run(self, dq_db):
        from scripts.fix_data_quality import step_0_remove_alternate_files

        _insert_rows(dq_db, [
            {"fiscal_year": 2014, "pe_number": "PE1", "line_item_title": "Item A",
             "organization_name": "Army", "exhibit_type": "r1",
             "source_file": "FY2014\\PB\\Comptroller\\summary\\r1a.xlsx",
             "amount": 100.0},
        ])

        removed = step_0_remove_alternate_files(dq_db, dry_run=True)
        assert removed == 1  # Reports the count
        # But data is unchanged
        assert dq_db.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# Step 1: Cross-file deduplication
# ---------------------------------------------------------------------------

class TestStep1CrossFileDedup:
    def test_removes_cross_file_duplicates(self, dq_db):
        from scripts.fix_data_quality import step_1_cross_file_dedup

        # Same logical row from two different source files
        base = {
            "fiscal_year": 2020, "pe_number": "0602702E",
            "line_item_title": "Advanced Research", "organization_name": "Army",
            "exhibit_type": "r1", "amount_type": "Base",
            "appropriation_code": "RDTE",
        }
        _insert_rows(dq_db, [
            {**base, "source_file": "FY2020/PB/army/r1.xlsx", "amount": 100.0},
            {**base, "source_file": "FY2021/PB/army/r1.xlsx", "amount": 100.0},
        ])

        deleted = step_1_cross_file_dedup(dq_db)
        assert deleted == 1

        remaining = dq_db.execute(
            "SELECT COUNT(*) FROM budget_lines"
        ).fetchone()[0]
        assert remaining == 1

    def test_prefers_matching_fy_source(self, dq_db):
        from scripts.fix_data_quality import step_1_cross_file_dedup

        base = {
            "fiscal_year": 2020, "pe_number": "0602702E",
            "line_item_title": "Advanced Research", "organization_name": "Army",
            "exhibit_type": "r1", "amount_type": "Base",
            "appropriation_code": "RDTE",
        }
        _insert_rows(dq_db, [
            {**base, "source_file": "FY2021/PB/army/r1.xlsx", "amount": 100.0},
            {**base, "source_file": "FY2020/PB/army/r1.xlsx", "amount": 100.0},
        ])

        step_1_cross_file_dedup(dq_db)

        # Should keep the row from FY2020 source (matches fiscal_year=2020)
        row = dq_db.execute("SELECT source_file FROM budget_lines").fetchone()
        assert "FY2020" in row[0]

    def test_no_duplicates_no_change(self, dq_db):
        from scripts.fix_data_quality import step_1_cross_file_dedup

        _insert_rows(dq_db, [
            {"fiscal_year": 2020, "pe_number": "PE1", "line_item_title": "Item A",
             "organization_name": "Army", "exhibit_type": "r1",
             "amount_type": "Base", "source_file": "FY2020/r1.xlsx",
             "amount": 100.0},
            {"fiscal_year": 2020, "pe_number": "PE2", "line_item_title": "Item B",
             "organization_name": "Navy", "exhibit_type": "r1",
             "amount_type": "Base", "source_file": "FY2020/r1.xlsx",
             "amount": 200.0},
        ])

        deleted = step_1_cross_file_dedup(dq_db)
        assert deleted == 0
        assert dq_db.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0] == 2

    def test_dry_run(self, dq_db):
        from scripts.fix_data_quality import step_1_cross_file_dedup

        base = {
            "fiscal_year": 2020, "pe_number": "PE1",
            "line_item_title": "Item A", "organization_name": "Army",
            "exhibit_type": "r1", "amount_type": "Base",
            "appropriation_code": "RDTE",
        }
        _insert_rows(dq_db, [
            {**base, "source_file": "FY2020/r1.xlsx", "amount": 100.0},
            {**base, "source_file": "FY2021/r1.xlsx", "amount": 100.0},
        ])

        estimate = step_1_cross_file_dedup(dq_db, dry_run=True)
        assert estimate >= 1
        # Data unchanged
        assert dq_db.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0] == 2


# ---------------------------------------------------------------------------
# Step 2: Appropriation code backfill
# ---------------------------------------------------------------------------

class TestStep2AppropriationBackfill:
    def test_exact_title_match(self, dq_db):
        from scripts.fix_data_quality import step_2_backfill_appropriation_codes

        _insert_rows(dq_db, [
            {"fiscal_year": 2020, "pe_number": "PE1",
             "appropriation_title": "Operation & Maintenance, Navy",
             "appropriation_code": None, "amount": 100.0},
        ])

        updated = step_2_backfill_appropriation_codes(dq_db)
        assert updated == 1

        code = dq_db.execute(
            "SELECT appropriation_code FROM budget_lines WHERE id = 1"
        ).fetchone()[0]
        assert code == "O&M"

    def test_keyword_match(self, dq_db):
        from scripts.fix_data_quality import step_2_backfill_appropriation_codes

        _insert_rows(dq_db, [
            {"fiscal_year": 2020, "pe_number": "PE1",
             "appropriation_title": "Military Construction, Something Special",
             "appropriation_code": None, "amount": 100.0},
        ])

        updated = step_2_backfill_appropriation_codes(dq_db)
        assert updated == 1

        code = dq_db.execute(
            "SELECT appropriation_code FROM budget_lines"
        ).fetchone()[0]
        assert code == "MILCON"

    def test_leading_numeric_code(self, dq_db):
        from scripts.fix_data_quality import step_2_backfill_appropriation_codes

        _insert_rows(dq_db, [
            {"fiscal_year": 2020, "pe_number": "PE1",
             "appropriation_title": "2035 Aircraft Procurement, Army",
             "appropriation_code": None, "amount": 100.0},
        ])

        updated = step_2_backfill_appropriation_codes(dq_db)
        assert updated == 1

        code = dq_db.execute(
            "SELECT appropriation_code FROM budget_lines"
        ).fetchone()[0]
        assert code == "2035"

    def test_skips_already_populated(self, dq_db):
        from scripts.fix_data_quality import step_2_backfill_appropriation_codes

        _insert_rows(dq_db, [
            {"fiscal_year": 2020, "pe_number": "PE1",
             "appropriation_title": "Operation & Maintenance, Navy",
             "appropriation_code": "EXISTING", "amount": 100.0},
        ])

        updated = step_2_backfill_appropriation_codes(dq_db)
        assert updated == 0

        code = dq_db.execute(
            "SELECT appropriation_code FROM budget_lines"
        ).fetchone()[0]
        assert code == "EXISTING"

    def test_dry_run(self, dq_db):
        from scripts.fix_data_quality import step_2_backfill_appropriation_codes

        _insert_rows(dq_db, [
            {"fiscal_year": 2020, "pe_number": "PE1",
             "appropriation_title": "Operation & Maintenance, Navy",
             "appropriation_code": None, "amount": 100.0},
        ])

        updated = step_2_backfill_appropriation_codes(dq_db, dry_run=True)
        assert updated == 1
        # Data unchanged
        code = dq_db.execute(
            "SELECT appropriation_code FROM budget_lines"
        ).fetchone()[0]
        assert code is None


# ---------------------------------------------------------------------------
# Step 3: Budget type backfill
# ---------------------------------------------------------------------------

class TestStep3BudgetTypeBackfill:
    def test_maps_appropriation_to_budget_type(self, dq_db):
        from scripts.fix_data_quality import step_3_backfill_budget_types

        _insert_rows(dq_db, [
            {"fiscal_year": 2020, "pe_number": "PE1",
             "appropriation_code": "RDTE", "budget_type": None, "amount": 100.0},
            {"fiscal_year": 2020, "pe_number": "PE2",
             "appropriation_code": "O&M", "budget_type": None, "amount": 200.0},
            {"fiscal_year": 2020, "pe_number": "PE3",
             "appropriation_code": "DHP", "budget_type": None, "amount": 300.0},
            {"fiscal_year": 2020, "pe_number": "PE4",
             "appropriation_code": "AMMO", "budget_type": None, "amount": 400.0},
        ])

        updated = step_3_backfill_budget_types(dq_db)
        assert updated == 4

        rows = dq_db.execute(
            "SELECT pe_number, budget_type FROM budget_lines ORDER BY pe_number"
        ).fetchall()
        result = {r[0]: r[1] for r in rows}
        assert result["PE1"] == "RDT&E"
        assert result["PE2"] == "O&M"
        assert result["PE3"] == "O&M"       # DHP → O&M
        assert result["PE4"] == "Procurement"  # AMMO → Procurement

    def test_skips_already_populated(self, dq_db):
        from scripts.fix_data_quality import step_3_backfill_budget_types

        _insert_rows(dq_db, [
            {"fiscal_year": 2020, "pe_number": "PE1",
             "appropriation_code": "RDTE", "budget_type": "RDT&E", "amount": 100.0},
        ])

        updated = step_3_backfill_budget_types(dq_db)
        assert updated == 0


# ---------------------------------------------------------------------------
# Step 4: Empty organization name fill
# ---------------------------------------------------------------------------

class TestStep4FillEmptyOrg:
    def test_infers_org_from_source_file(self, dq_db):
        from scripts.fix_data_quality import step_4_fill_empty_org

        _insert_rows(dq_db, [
            {"fiscal_year": 2020, "pe_number": "PE1", "organization_name": "",
             "source_file": "FY2020/PB/army/r1.xlsx", "amount": 100.0},
            {"fiscal_year": 2020, "pe_number": "PE2", "organization_name": None,
             "source_file": "FY2020\\PB\\navy\\p1.xlsx", "amount": 200.0},
        ])

        filled = step_4_fill_empty_org(dq_db)
        assert filled == 2

        rows = dq_db.execute(
            "SELECT pe_number, organization_name FROM budget_lines ORDER BY pe_number"
        ).fetchall()
        result = {r[0]: r[1] for r in rows}
        assert result["PE1"] == "Army"
        assert result["PE2"] == "Navy"

    def test_unresolvable_gets_unspecified(self, dq_db):
        from scripts.fix_data_quality import step_4_fill_empty_org

        _insert_rows(dq_db, [
            {"fiscal_year": 2020, "pe_number": "PE1", "organization_name": "",
             "source_file": "FY2020/PB/other/r1.xlsx", "amount": 100.0},
        ])

        filled = step_4_fill_empty_org(dq_db)
        assert filled == 1

        org = dq_db.execute(
            "SELECT organization_name FROM budget_lines"
        ).fetchone()[0]
        assert org == "Unspecified"

    def test_does_not_modify_existing_orgs(self, dq_db):
        from scripts.fix_data_quality import step_4_fill_empty_org

        _insert_rows(dq_db, [
            {"fiscal_year": 2020, "pe_number": "PE1", "organization_name": "Army",
             "source_file": "FY2020/PB/army/r1.xlsx", "amount": 100.0},
        ])

        filled = step_4_fill_empty_org(dq_db)
        assert filled == 0


# ---------------------------------------------------------------------------
# Step 5: Appropriation titles cleanup
# ---------------------------------------------------------------------------

class TestStep5CleanAppropTitles:
    def test_removes_footnote_entries(self, dq_db):
        from scripts.fix_data_quality import step_5_clean_appropriation_titles

        dq_db.executemany(
            "INSERT INTO appropriation_titles (code, title) VALUES (?, ?)",
            [
                ("O&M", "Operation & Maintenance"),
                ("*1", "Footnote 1 text"),
                ("**", "Double asterisk note"),
                ("RDTE", "Research, Development, Test & Evaluation"),
                ("", "Blank code"),
            ],
        )
        dq_db.commit()

        removed = step_5_clean_appropriation_titles(dq_db)
        assert removed == 3  # *1, **, and blank

        remaining = dq_db.execute(
            "SELECT code FROM appropriation_titles ORDER BY code"
        ).fetchall()
        codes = [r[0] for r in remaining]
        assert "O&M" in codes
        assert "RDTE" in codes
        assert "*1" not in codes
        assert "**" not in codes

    def test_no_table_no_crash(self):
        """Step 5 handles missing appropriation_titles table gracefully."""
        from scripts.fix_data_quality import step_5_clean_appropriation_titles

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        result = step_5_clean_appropriation_titles(conn)
        assert result == 0
        conn.close()

    def test_dry_run(self, dq_db):
        from scripts.fix_data_quality import step_5_clean_appropriation_titles

        dq_db.executemany(
            "INSERT INTO appropriation_titles (code, title) VALUES (?, ?)",
            [("*1", "Footnote"), ("O&M", "Operation & Maintenance")],
        )
        dq_db.commit()

        removed = step_5_clean_appropriation_titles(dq_db, dry_run=True)
        assert removed == 1  # Reports the count
        # But data unchanged
        count = dq_db.execute(
            "SELECT COUNT(*) FROM appropriation_titles"
        ).fetchone()[0]
        assert count == 2


# ---------------------------------------------------------------------------
# Step 6: Handle NULL title rows
# ---------------------------------------------------------------------------

class TestStep6HandleNullTitleRows:
    def test_resolves_from_account_title(self, dq_db):
        from scripts.fix_data_quality import step_6_handle_null_title_rows

        _insert_rows(dq_db, [
            {"fiscal_year": 2020, "pe_number": "PE1",
             "appropriation_code": None, "appropriation_title": None,
             "account_title": "RDT&E, Navy", "amount": 100.0},
        ])

        updated = step_6_handle_null_title_rows(dq_db)
        assert updated == 1

        row = dq_db.execute(
            "SELECT appropriation_code FROM budget_lines"
        ).fetchone()
        assert row[0] == "RDTE"

    def test_skips_when_account_title_null(self, dq_db):
        from scripts.fix_data_quality import step_6_handle_null_title_rows

        _insert_rows(dq_db, [
            {"fiscal_year": 2020, "pe_number": "PE1",
             "appropriation_code": None, "appropriation_title": None,
             "account_title": None, "amount": 100.0},
        ])

        updated = step_6_handle_null_title_rows(dq_db)
        assert updated == 0


# ---------------------------------------------------------------------------
# _resolve_code helper
# ---------------------------------------------------------------------------

class TestResolveCode:
    def test_exact_match(self):
        from scripts.fix_data_quality import _resolve_code
        assert _resolve_code("Operation & Maintenance, Navy") == "O&M"
        assert _resolve_code("RDT&E, Army") == "RDTE"
        assert _resolve_code("Mil Con, Def-Wide") == "MILCON"
        assert _resolve_code("Defense Health Program") == "DHP"

    def test_leading_numeric(self):
        from scripts.fix_data_quality import _resolve_code
        assert _resolve_code("2035 Aircraft Procurement, Army") == "2035"

    def test_keyword_match(self):
        from scripts.fix_data_quality import _resolve_code
        assert _resolve_code("Some Military Construction Project") == "MILCON"
        assert _resolve_code("Operation & Maintenance, Something") == "O&M"

    def test_no_match_returns_none(self):
        from scripts.fix_data_quality import _resolve_code
        assert _resolve_code("Completely Unknown Title XYZ") is None

    def test_dhp_mapping(self):
        from scripts.fix_data_quality import _resolve_code
        assert _resolve_code("Defense Health Program") == "DHP"

    def test_ampersand_variants(self):
        from scripts.fix_data_quality import _resolve_code
        # Keyword "operation & maintenance" should match
        assert _resolve_code("Operation & Maintenance, Special Forces") == "O&M"


# ---------------------------------------------------------------------------
# Backfill.py footnote filtering
# ---------------------------------------------------------------------------

class TestBackfillFootnoteFiltering:
    def test_footnote_codes_excluded(self):
        """backfill() should not ingest footnote accounts (* prefixed)."""
        from pipeline.backfill import backfill

        conn = sqlite3.connect(":memory:")
        conn.executescript("""
            CREATE TABLE budget_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT, exhibit_type TEXT, organization_name TEXT,
                account TEXT, account_title TEXT
            );
            CREATE TABLE services_agencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE, full_name TEXT NOT NULL,
                category TEXT NOT NULL
            );
            CREATE TABLE exhibit_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
                exhibit_class TEXT NOT NULL, description TEXT
            );
            CREATE TABLE appropriation_titles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE, title TEXT NOT NULL,
                color_of_money TEXT
            );
        """)
        conn.executemany(
            "INSERT INTO budget_lines "
            "(source_file, exhibit_type, organization_name, account, account_title) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                ("a.xlsx", "p1", "Army", "2035", "Aircraft Procurement"),
                ("a.xlsx", "p1", "Army", "*1", "Footnote text"),
                ("a.xlsx", "p1", "Army", "**", "Double footnote"),
                ("a.xlsx", "p1", "Army", "A", "Single char code"),
            ],
        )
        conn.commit()

        summary = backfill(conn)

        # Only "2035" should be in appropriation_titles (others filtered)
        assert summary["appropriation_titles"] == 1

        rows = conn.execute(
            "SELECT code FROM appropriation_titles"
        ).fetchall()
        codes = [r[0] for r in rows]
        assert "2035" in codes
        assert "*1" not in codes
        assert "**" not in codes
        assert "A" not in codes

        conn.close()


# ---------------------------------------------------------------------------
# fix_budget_types.py DHP/AMMO mapping
# ---------------------------------------------------------------------------

class TestFixBudgetTypesMappings:
    def test_dhp_mapping(self):
        from scripts.fix_budget_types import APPROP_TO_BUDGET_TYPE
        assert "DHP" in APPROP_TO_BUDGET_TYPE
        assert APPROP_TO_BUDGET_TYPE["DHP"] == "O&M"

    def test_ammo_mapping(self):
        from scripts.fix_budget_types import APPROP_TO_BUDGET_TYPE
        assert "AMMO" in APPROP_TO_BUDGET_TYPE
        assert APPROP_TO_BUDGET_TYPE["AMMO"] == "Procurement"

    def test_fix_budget_types_function(self):
        """Integration test: fix_budget_types handles DHP and AMMO."""
        from scripts.fix_budget_types import fix_budget_types

        conn = sqlite3.connect(":memory:")
        conn.execute("""
            CREATE TABLE budget_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                budget_type TEXT,
                appropriation_code TEXT
            )
        """)
        conn.executemany(
            "INSERT INTO budget_lines (appropriation_code, budget_type) VALUES (?, ?)",
            [
                ("DHP", None),
                ("AMMO", None),
                ("RDTE", None),
                ("O&M", "O&M"),  # Already populated, should be skipped
            ],
        )
        conn.commit()

        updated = fix_budget_types(conn)
        assert updated == 3  # DHP, AMMO, RDTE

        rows = conn.execute(
            "SELECT appropriation_code, budget_type FROM budget_lines ORDER BY id"
        ).fetchall()
        result = {r[0]: r[1] for r in rows}
        assert result["DHP"] == "O&M"
        assert result["AMMO"] == "Procurement"
        assert result["RDTE"] == "RDT&E"
        assert result["O&M"] == "O&M"  # Unchanged

        conn.close()


# ---------------------------------------------------------------------------
# Orchestrator (run_all) - smoke test
# ---------------------------------------------------------------------------

class TestRunAll:
    def test_run_all_dry_run(self, tmp_path):
        """run_all in dry-run mode doesn't modify the database."""
        from scripts.fix_data_quality import run_all

        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        _create_schema(conn)
        _insert_rows(conn, [
            {"fiscal_year": 2020, "pe_number": "PE1", "line_item_title": "Item",
             "organization_name": "Army", "exhibit_type": "r1",
             "amount_type": "Base", "appropriation_code": None,
             "appropriation_title": "Operation & Maintenance, Army",
             "source_file": "FY2020/r1.xlsx", "amount": 100.0},
        ])
        conn.close()

        run_all(str(db_path), dry_run=True)

        # Verify database is untouched
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT appropriation_code FROM budget_lines"
        ).fetchone()
        assert row[0] is None  # Not backfilled
        conn.close()

    def test_run_single_step(self, tmp_path):
        """run_all with only_step runs just that one step."""
        from scripts.fix_data_quality import run_all

        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        _create_schema(conn)
        _insert_rows(conn, [
            {"fiscal_year": 2020, "pe_number": "PE1", "line_item_title": "Item",
             "organization_name": "Army", "exhibit_type": "r1",
             "amount_type": "Base", "appropriation_code": None,
             "appropriation_title": "Operation & Maintenance, Army",
             "source_file": "FY2020/r1.xlsx", "amount": 100.0},
        ])
        conn.close()

        results = run_all(str(db_path), only_step=2)

        # Step 2 ran, so appropriation code should be backfilled
        conn = sqlite3.connect(str(db_path))
        code = conn.execute(
            "SELECT appropriation_code FROM budget_lines"
        ).fetchone()[0]
        conn.close()
        assert code == "O&M"

        # Only step 2 should be in results
        assert 2 in results
        assert 0 not in results
