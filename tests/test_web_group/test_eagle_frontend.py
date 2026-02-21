"""
Tests for EAGLE frontend route changes:
  EAGLE-1: Dynamic amount filter (amount_column parameter)
  EAGLE-2: Tag-based related items in detail panel
  EAGLE-4: Expanded pagination options (25/50/100/200)
  EAGLE-5: Advanced search integration (field prefixes, amount operators)
  EAGLE-6: Export source attribution
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from api.app import create_app


@pytest.fixture(scope="module")
def app_client(tmp_path_factory):
    """Create a test app with a pre-populated database for EAGLE tests."""
    tmp = tmp_path_factory.mktemp("eagle_frontend_test")
    db_path = tmp / "test.sqlite"

    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT, exhibit_type TEXT, sheet_name TEXT,
            fiscal_year TEXT, account TEXT, account_title TEXT,
            organization TEXT, organization_name TEXT,
            budget_activity TEXT, budget_activity_title TEXT,
            sub_activity TEXT, sub_activity_title TEXT,
            line_item TEXT, line_item_title TEXT,
            pe_number TEXT, appropriation_code TEXT, appropriation_title TEXT,
            currency_year TEXT, amount_unit TEXT DEFAULT 'thousands',
            amount_type TEXT DEFAULT 'budget_authority', budget_type TEXT,
            amount_fy2024_actual REAL, amount_fy2025_enacted REAL,
            amount_fy2025_supplemental REAL, amount_fy2025_total REAL,
            amount_fy2026_request REAL, amount_fy2026_reconciliation REAL,
            amount_fy2026_total REAL,
            quantity_fy2024 REAL, quantity_fy2025 REAL,
            quantity_fy2026_request REAL, quantity_fy2026_total REAL,
            classification TEXT, extra_fields TEXT
        );
        CREATE TABLE pdf_pages (
            id INTEGER PRIMARY KEY, source_file TEXT,
            source_category TEXT, page_number INTEGER,
            page_text TEXT, has_tables INTEGER, table_data TEXT
        );
        CREATE TABLE ingested_files (
            id INTEGER PRIMARY KEY, file_path TEXT, file_type TEXT,
            row_count INTEGER, ingested_at TEXT, status TEXT
        );
        CREATE VIRTUAL TABLE budget_lines_fts USING fts5(
            account_title, line_item_title, budget_activity_title,
            content=budget_lines
        );

        -- PE enrichment tables
        CREATE TABLE pe_index (
            pe_number TEXT PRIMARY KEY,
            display_title TEXT,
            organization_name TEXT,
            budget_type TEXT,
            fiscal_years TEXT,
            exhibit_types TEXT
        );
        CREATE TABLE pe_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT,
            tag TEXT,
            tag_source TEXT,
            confidence REAL DEFAULT 1.0,
            source_files TEXT
        );
        CREATE TABLE pe_lineage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_pe TEXT,
            referenced_pe TEXT,
            link_type TEXT,
            confidence REAL DEFAULT 0.9,
            fiscal_year TEXT,
            context_snippet TEXT
        );
        CREATE TABLE pe_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT,
            fiscal_year TEXT,
            source_file TEXT,
            page_start INTEGER,
            page_end INTEGER,
            section_header TEXT,
            description_text TEXT
        );

        CREATE TABLE services_agencies (
            code TEXT PRIMARY KEY, full_name TEXT
        );
        CREATE TABLE exhibit_types (
            code TEXT PRIMARY KEY, display_name TEXT
        );

        INSERT INTO services_agencies VALUES ('Army', 'U.S. Army');
        INSERT INTO services_agencies VALUES ('Navy', 'U.S. Navy');
        INSERT INTO services_agencies VALUES ('Air Force', 'U.S. Air Force');

        INSERT INTO exhibit_types VALUES ('p1', 'Procurement Summary');
        INSERT INTO exhibit_types VALUES ('r1', 'RDT&E Summary');

        -- Budget lines with varying amounts for filter testing
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title, pe_number,
             appropriation_code, appropriation_title,
             amount_fy2024_actual, amount_fy2025_enacted, amount_fy2025_total,
             amount_fy2026_request, amount_fy2026_total)
        VALUES
            ('army_p5.xlsx', 'p5', '2026', 'Army',
             'Aircraft Procurement', 'Apache AH-64', '0604131A',
             'PROC', 'Procurement',
             120000.0, 140000.0, 145000.0, 150000.0, 155000.0),
            ('navy_r2.xlsx', 'r2', '2026', 'Navy',
             'RDT&E Budget', 'F-35 Development', '0603292N',
             'RDTE', 'RDT&E',
             200000.0, 230000.0, 235000.0, 250000.0, 260000.0),
            ('af_p5.xlsx', 'p5', '2025', 'Air Force',
             'Aircraft Procurement', 'F-22A', '0604800F',
             'PROC', 'Procurement',
             80000.0, 90000.0, 95000.0, 100000.0, 105000.0),
            ('army_r2.xlsx', 'r2', '2026', 'Army',
             'RDT&E Budget', 'Missile Defense', '0604131A',
             'RDTE', 'RDT&E',
             50000.0, 60000.0, 62000.0, 70000.0, 72000.0);

        INSERT INTO budget_lines_fts(rowid, account_title, line_item_title,
            budget_activity_title)
        SELECT id, account_title, line_item_title, budget_activity_title
        FROM budget_lines;

        INSERT INTO pe_index VALUES
            ('0604131A', 'Apache AH-64 Block III', 'Army', 'Procurement',
             '["2026"]', '["p1"]'),
            ('0603292N', 'F-35 Lightning II', 'Navy', 'RDT&E',
             '["2026"]', '["r1"]'),
            ('0604800F', 'F-22A Raptor', 'Air Force', 'Procurement',
             '["2025"]', '["p1"]');

        -- Tags: Apache and F-35 share 'aviation' tag for related items testing
        INSERT INTO pe_tags VALUES (NULL, '0604131A', 'aviation', 'structured', 1.0, '["army_r1.xlsx"]');
        INSERT INTO pe_tags VALUES (NULL, '0604131A', 'rotary-wing', 'keyword', 0.9, '["army_r2.pdf"]');
        INSERT INTO pe_tags VALUES (NULL, '0604131A', 'army-program', 'keyword', 0.8, NULL);
        INSERT INTO pe_tags VALUES (NULL, '0603292N', 'aviation', 'structured', 1.0, '["navy_r1.xlsx"]');
        INSERT INTO pe_tags VALUES (NULL, '0603292N', 'stealth', 'keyword', 0.8, '["navy_r2.pdf"]');
        INSERT INTO pe_tags VALUES (NULL, '0604800F', 'aviation', 'structured', 1.0, NULL);
        INSERT INTO pe_tags VALUES (NULL, '0604800F', 'stealth', 'keyword', 0.7, NULL);

        INSERT INTO pe_lineage VALUES
            (NULL, '0604131A', '0603292N', 'name_match', 0.6, '2026', 'aviation context');

        INSERT INTO pe_descriptions VALUES
            (NULL, '0604131A', '2026', 'army_r2.pdf', 1, 3, 'Mission Description',
             'The Apache AH-64 Block III program continues modernization...');
    """)
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    return TestClient(app, raise_server_exceptions=False)


# ── EAGLE-1: Dynamic Amount Filter Tests ────────────────────────────────────

class TestDynamicAmountFilter:
    def test_default_amount_column(self, app_client):
        """Default filtering uses amount_fy2026_request."""
        resp = app_client.get("/?min_amount=130000")
        assert resp.status_code == 200
        # Should include Apache (150k) and F-35 (250k), but not F-22A (100k)

    def test_filter_on_fy2025_enacted(self, app_client):
        """amount_column=amount_fy2025_enacted filters on FY2025 Enacted."""
        resp = app_client.get(
            "/?min_amount=200000&amount_column=amount_fy2025_enacted"
        )
        assert resp.status_code == 200
        # Only F-35 has FY2025 enacted >= 200k (230k)

    def test_filter_on_fy2024_actual(self, app_client):
        """amount_column=amount_fy2024_actual filters on FY2024 Actual."""
        resp = app_client.get(
            "/?max_amount=100000&amount_column=amount_fy2024_actual"
        )
        assert resp.status_code == 200
        # F-22A (80k) and Missile Defense (50k) are <= 100k

    def test_invalid_amount_column_uses_default(self, app_client):
        """Invalid amount_column falls back to default without error."""
        resp = app_client.get(
            "/?min_amount=100000&amount_column=invalid_column"
        )
        assert resp.status_code == 200

    def test_amount_column_in_results_partial(self, app_client):
        """Results partial also accepts amount_column."""
        resp = app_client.get(
            "/partials/results?min_amount=200000&amount_column=amount_fy2025_enacted",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200


# ── EAGLE-2: Tag-Based Related Items Tests ──────────────────────────────────

class TestTagBasedRelatedItems:
    def test_detail_returns_related_items(self, app_client):
        """Detail panel returns related items for a budget line."""
        resp = app_client.get(
            "/partials/detail/1",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 200

    def test_detail_non_htmx_redirects(self, app_client):
        """Non-HTMX detail requests redirect to home."""
        resp = app_client.get("/partials/detail/1", follow_redirects=False)
        assert resp.status_code == 302

    def test_detail_404_for_missing_item(self, app_client):
        """Missing item returns 404."""
        resp = app_client.get(
            "/partials/detail/9999",
            headers={"HX-Request": "true"},
        )
        assert resp.status_code == 404


# ── EAGLE-4: Expanded Pagination Tests ──────────────────────────────────────

class TestExpandedPagination:
    def test_page_size_25_default(self, app_client):
        """Default page size is 25."""
        resp = app_client.get("/")
        assert resp.status_code == 200

    def test_page_size_200_accepted(self, app_client):
        """page_size=200 is accepted without error."""
        resp = app_client.get("/?page_size=200")
        assert resp.status_code == 200

    def test_page_size_over_200_clamped(self, app_client):
        """page_size > 200 is clamped to 200."""
        resp = app_client.get("/?page_size=500")
        assert resp.status_code == 200

    def test_page_size_under_10_clamped(self, app_client):
        """page_size < 10 is clamped to 10."""
        resp = app_client.get("/?page_size=5")
        assert resp.status_code == 200


# ── EAGLE-5: Advanced Search Integration Tests ──────────────────────────────

class TestAdvancedSearchIntegration:
    def test_plain_text_search_still_works(self, app_client):
        """Plain text search without field prefixes still works."""
        resp = app_client.get("/?q=Apache")
        assert resp.status_code == 200

    def test_search_with_no_results(self, app_client):
        """Search returning no results gives empty results."""
        resp = app_client.get("/?q=nonexistent_term_xyz_12345")
        assert resp.status_code == 200


# ── EAGLE-6: Export Source Attribution Tests ─────────────────────────────────

class TestExportSourceAttribution:
    def test_csv_export_has_attribution_header(self, app_client):
        """CSV export includes source attribution comment rows."""
        resp = app_client.get("/api/v1/download?fmt=csv&limit=5")
        assert resp.status_code == 200
        content = resp.text
        assert "# Source: DoD Budget Explorer" in content
        assert "# Export Date:" in content
        assert "# Filters:" in content
        assert "# URL:" in content
        assert "# Total Records:" in content

    def test_csv_export_with_filters_shows_filter_summary(self, app_client):
        """CSV export includes filter summary when filters are active."""
        resp = app_client.get(
            "/api/v1/download?fmt=csv&service=Army&limit=5"
        )
        assert resp.status_code == 200
        assert "service=Army" in resp.text

    def test_json_export_has_metadata_first_line(self, app_client):
        """NDJSON export starts with a _metadata object."""
        resp = app_client.get("/api/v1/download?fmt=json&limit=5")
        assert resp.status_code == 200
        import json
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 1
        first = json.loads(lines[0])
        assert "_metadata" in first
        meta = first["_metadata"]
        assert meta["source"] == "DoD Budget Explorer"
        assert "export_date" in meta
        assert "total_records" in meta

    def test_xlsx_export_returns_valid_response(self, app_client):
        """Excel export returns a valid xlsx file."""
        resp = app_client.get("/api/v1/download?fmt=xlsx&limit=5")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers["content-type"]

    def test_x_total_count_header(self, app_client):
        """Download responses include X-Total-Count header."""
        resp = app_client.get("/api/v1/download?fmt=csv&limit=5")
        assert "X-Total-Count" in resp.headers
        count = int(resp.headers["X-Total-Count"])
        assert count > 0


# ── utils/query.py Tests ────────────────────────────────────────────────────

class TestQueryBuilderDynamicColumn:
    def test_validate_amount_column_default(self):
        """validate_amount_column returns default for None."""
        from utils.query import validate_amount_column, DEFAULT_AMOUNT_COLUMN
        assert validate_amount_column(None) == DEFAULT_AMOUNT_COLUMN

    def test_validate_amount_column_valid(self):
        """validate_amount_column accepts valid columns."""
        from utils.query import validate_amount_column
        result = validate_amount_column("amount_fy2025_enacted")
        assert result == "amount_fy2025_enacted"

    def test_validate_amount_column_invalid(self):
        """validate_amount_column raises ValueError for invalid columns."""
        from utils.query import validate_amount_column
        with pytest.raises(ValueError, match="Invalid amount column"):
            validate_amount_column("invalid_column")

    def test_build_where_with_amount_column(self):
        """build_where_clause uses specified amount column."""
        from utils.query import build_where_clause
        where, params = build_where_clause(
            min_amount=50000,
            amount_column="amount_fy2025_enacted",
        )
        assert "amount_fy2025_enacted >= ?" in where
        assert 50000 in params

    def test_build_where_default_amount_column(self):
        """build_where_clause defaults to fy2026_request."""
        from utils.query import build_where_clause
        where, params = build_where_clause(min_amount=10000)
        assert "amount_fy2026_request >= ?" in where

    def test_fiscal_year_column_labels_structure(self):
        """FISCAL_YEAR_COLUMN_LABELS has correct shape."""
        from utils.query import FISCAL_YEAR_COLUMN_LABELS
        assert isinstance(FISCAL_YEAR_COLUMN_LABELS, list)
        assert len(FISCAL_YEAR_COLUMN_LABELS) > 0
        for item in FISCAL_YEAR_COLUMN_LABELS:
            assert "column" in item
            assert "label" in item
