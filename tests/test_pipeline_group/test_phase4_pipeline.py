"""
Phase 4 — B4.4: Tests for FY normalization utility and builder integration.

Tests normalize_fiscal_year() with various input formats, and verifies that
the builder module applies the normalization during ingestion.
"""

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from utils.strings import normalize_fiscal_year


# ---------------------------------------------------------------------------
# normalize_fiscal_year() unit tests
# ---------------------------------------------------------------------------

class TestNormalizeFiscalYear:
    """Test the normalize_fiscal_year utility function."""

    def test_fy_space_4digit(self):
        """'FY 2026' -> '2026'"""
        assert normalize_fiscal_year("FY 2026") == "2026"

    def test_fy_no_space_4digit(self):
        """'FY2026' -> '2026'"""
        assert normalize_fiscal_year("FY2026") == "2026"

    def test_bare_4digit(self):
        """'2026' -> '2026'"""
        assert normalize_fiscal_year("2026") == "2026"

    def test_fy_2digit(self):
        """'FY26' -> '2026' (assumes 2000s)"""
        assert normalize_fiscal_year("FY26") == "2026"

    def test_fy_space_2digit(self):
        """'FY 26' -> '2026' (assumes 2000s)"""
        assert normalize_fiscal_year("FY 26") == "2026"

    def test_fy_lowercase(self):
        """'fy 2026' -> '2026' (case insensitive)"""
        assert normalize_fiscal_year("fy 2026") == "2026"

    def test_fy_mixed_case(self):
        """'Fy2026' -> '2026' (case insensitive)"""
        assert normalize_fiscal_year("Fy2026") == "2026"

    def test_historical_year(self):
        """'FY 1998' -> '1998' (historical data)"""
        assert normalize_fiscal_year("FY 1998") == "1998"

    def test_bare_historical_year(self):
        """'1998' -> '1998'"""
        assert normalize_fiscal_year("1998") == "1998"

    def test_fy_2digit_low(self):
        """'FY00' -> '2000'"""
        assert normalize_fiscal_year("FY00") == "2000"

    def test_fy_2digit_99(self):
        """'FY99' -> '2099'"""
        assert normalize_fiscal_year("FY99") == "2099"

    # --- Invalid / edge cases ---

    def test_invalid_returns_none(self):
        """Invalid input returns None."""
        assert normalize_fiscal_year("not a year") is None

    def test_empty_string(self):
        """Empty string returns None."""
        assert normalize_fiscal_year("") is None

    def test_none_returns_none(self):
        """None input returns None."""
        assert normalize_fiscal_year(None) is None

    def test_whitespace_only(self):
        """Whitespace-only input returns None."""
        assert normalize_fiscal_year("   ") is None

    def test_partial_match_no_normalize(self):
        """Strings like 'FY 2026 Actuals' do not match (not a pure FY value)."""
        assert normalize_fiscal_year("FY 2026 Actuals") is None

    def test_out_of_range_year(self):
        """Year outside valid range returns None."""
        assert normalize_fiscal_year("FY 2200") is None
        assert normalize_fiscal_year("1800") is None

    def test_with_leading_trailing_whitespace(self):
        """Leading/trailing whitespace is stripped before matching."""
        assert normalize_fiscal_year("  FY 2026  ") == "2026"
        assert normalize_fiscal_year("  2025  ") == "2025"


# ---------------------------------------------------------------------------
# Builder integration tests
# ---------------------------------------------------------------------------

class TestBuilderFYNormalization:
    """Test that pipeline/builder.py correctly imports and uses normalize_fiscal_year."""

    def test_builder_imports_normalize_fy(self):
        """Builder module should import _normalize_fy_value from utils.strings."""
        from pipeline import builder
        assert hasattr(builder, '_normalize_fy_value')

    def test_normalise_fiscal_year_returns_fy_format(self):
        """The existing _normalise_fiscal_year returns 'FY YYYY' format."""
        from pipeline.builder import _normalise_fiscal_year
        assert _normalise_fiscal_year("2026") == "FY 2026"
        assert _normalise_fiscal_year("FY2026") == "FY 2026"
        assert _normalise_fiscal_year("FY 2026") == "FY 2026"

    def test_normalize_fy_value_converts_fy_format(self):
        """_normalize_fy_value should strip 'FY' prefix from _normalise_fiscal_year output."""
        from pipeline.builder import _normalize_fy_value
        # _normalise_fiscal_year("2026") returns "FY 2026"
        # _normalize_fy_value("FY 2026") should return "2026"
        assert _normalize_fy_value("FY 2026") == "2026"
        assert _normalize_fy_value("FY2026") == "2026"
        assert _normalize_fy_value("2026") == "2026"

    def test_pipeline_chain_normalizes_to_4digit(self):
        """Simulates the pipeline chain: sheet_name -> _normalise_fiscal_year -> _normalize_fy_value."""
        from pipeline.builder import _normalise_fiscal_year, _normalize_fy_value

        # Chain: sheet_name "FY 2026" -> "FY 2026" -> "2026"
        fy = _normalise_fiscal_year("FY 2026")
        normalized = _normalize_fy_value(fy)
        assert normalized == "2026"

        # Chain: sheet_name "2026" -> "FY 2026" -> "2026"
        fy = _normalise_fiscal_year("2026")
        normalized = _normalize_fy_value(fy)
        assert normalized == "2026"

        # Chain: sheet_name "FY2025" -> "FY 2025" -> "2025"
        fy = _normalise_fiscal_year("FY2025")
        normalized = _normalize_fy_value(fy)
        assert normalized == "2025"


# ---------------------------------------------------------------------------
# Data changelog table tests (B4.1 verification)
# ---------------------------------------------------------------------------

class TestDataChangelogMigration:
    """Verify that migration 004 creates the data_changelog table."""

    def test_migration_creates_data_changelog(self):
        """After migrate(), data_changelog table should exist."""
        import sqlite3
        from pipeline.schema import migrate

        conn = sqlite3.connect(":memory:")
        migrate(conn)

        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {r[0] for r in tables}
        assert "data_changelog" in table_names
        conn.close()

    def test_data_changelog_columns(self):
        """data_changelog should have the expected columns."""
        import sqlite3
        from pipeline.schema import migrate

        conn = sqlite3.connect(":memory:")
        migrate(conn)

        cols = conn.execute("PRAGMA table_info(data_changelog)").fetchall()
        col_names = {r[1] for r in cols}
        assert "id" in col_names
        assert "action" in col_names
        assert "table_name" in col_names
        assert "record_count" in col_names
        assert "source_file" in col_names
        assert "timestamp" in col_names
        assert "notes" in col_names
        conn.close()

    def test_data_changelog_indexes(self):
        """data_changelog should have indexes on timestamp and action."""
        import sqlite3
        from pipeline.schema import migrate

        conn = sqlite3.connect(":memory:")
        migrate(conn)

        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        idx_names = {r[0] for r in indexes}
        assert "idx_changelog_ts" in idx_names
        assert "idx_changelog_action" in idx_names
        conn.close()

    def test_data_changelog_insert(self):
        """Should be able to insert records into data_changelog."""
        import sqlite3
        from pipeline.schema import migrate

        conn = sqlite3.connect(":memory:")
        migrate(conn)

        conn.execute(
            "INSERT INTO data_changelog (action, table_name, record_count, notes) "
            "VALUES ('insert', 'budget_lines', 1000, 'initial build')"
        )
        conn.commit()

        row = conn.execute("SELECT * FROM data_changelog").fetchone()
        assert row is not None
        assert row[1] == "insert"       # action
        assert row[2] == "budget_lines"  # table_name
        assert row[3] == 1000           # record_count
        conn.close()

    def test_schema_version_is_4(self):
        """After full migration, schema version should be 4."""
        import sqlite3
        from pipeline.schema import migrate, _current_version

        conn = sqlite3.connect(":memory:")
        migrate(conn)
        assert _current_version(conn) == 4
        conn.close()
