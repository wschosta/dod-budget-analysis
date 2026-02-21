"""Tests for HAWK-5: Metadata API endpoint and collection utilities.

Tests both the utils/metadata.py collection functions and the
/api/v1/metadata API endpoint.
"""

import sqlite3

import pytest

from utils.metadata import collect_metadata


@pytest.fixture
def metadata_db(tmp_path):
    """Create a test database with budget_lines, enrichment tables, and sample data."""
    db_path = tmp_path / "test_meta.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            exhibit_type TEXT,
            sheet_name TEXT,
            fiscal_year TEXT,
            account TEXT,
            account_title TEXT,
            organization_name TEXT,
            budget_activity_title TEXT,
            sub_activity_title TEXT,
            line_item TEXT,
            line_item_title TEXT,
            pe_number TEXT,
            amount_type TEXT,
            amount_fy2024_actual REAL,
            amount_fy2025_enacted REAL,
            amount_fy2026_request REAL
        );

        CREATE TABLE pdf_pages (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            page_number INTEGER,
            page_text TEXT
        );

        CREATE TABLE pe_index (
            pe_number TEXT PRIMARY KEY,
            display_title TEXT,
            organization_name TEXT,
            budget_type TEXT,
            fiscal_years TEXT,
            exhibit_types TEXT
        );

        CREATE TABLE pe_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT NOT NULL,
            fiscal_year TEXT,
            source_file TEXT,
            page_start INTEGER,
            page_end INTEGER,
            section_header TEXT,
            description_text TEXT
        );

        CREATE TABLE pe_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT NOT NULL,
            project_number TEXT,
            tag TEXT NOT NULL,
            tag_source TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            source_files TEXT
        );

        CREATE TABLE pe_lineage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_pe TEXT NOT NULL,
            referenced_pe TEXT NOT NULL,
            link_type TEXT NOT NULL,
            confidence REAL DEFAULT 0.5
        );

        CREATE TABLE project_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT NOT NULL,
            project_number TEXT,
            project_title TEXT,
            fiscal_year TEXT,
            section_header TEXT NOT NULL,
            description_text TEXT NOT NULL
        );

        -- Insert sample data
        INSERT INTO budget_lines (id, source_file, exhibit_type, fiscal_year,
            organization_name, pe_number, amount_fy2024_actual,
            amount_fy2025_enacted, amount_fy2026_request)
        VALUES
            (1, 'army_r1.xlsx', 'R-1', '2026', 'Army', '0602120A', 100.0, 200.0, 300.0),
            (2, 'navy_r1.xlsx', 'R-1', '2026', 'Navy', '0603292N', 150.0, 250.0, 350.0),
            (3, 'army_r2.pdf', 'R-2', '2025', 'Army', '0602120A', 90.0, 180.0, 270.0);

        INSERT INTO pe_index (pe_number, display_title) VALUES
            ('0602120A', 'Advanced Sensors'),
            ('0603292N', 'Naval Aviation');

        INSERT INTO pe_descriptions (pe_number, fiscal_year, description_text) VALUES
            ('0602120A', '2026', 'Advanced sensor development program');

        INSERT INTO pe_tags (pe_number, tag, tag_source, confidence) VALUES
            ('0602120A', 'army', 'structured', 1.0),
            ('0602120A', 'rdte', 'structured', 1.0),
            ('0603292N', 'navy', 'structured', 1.0);

        INSERT INTO pe_lineage (source_pe, referenced_pe, link_type) VALUES
            ('0602120A', '0603292N', 'name_match');

        INSERT INTO project_descriptions (pe_number, project_number, project_title,
            fiscal_year, section_header, description_text) VALUES
            ('0602120A', '1234', 'Sensor Dev', '2026', 'Description', 'Sensor development');
    """)
    conn.commit()
    yield conn
    conn.close()


class TestCollectMetadata:
    """Tests for the collect_metadata utility function."""

    def test_table_counts(self, metadata_db):
        """Table counts are reported correctly."""
        meta = collect_metadata(metadata_db)
        assert meta["tables"]["budget_lines"] == 3
        assert meta["tables"]["pe_index"] == 2
        assert meta["tables"]["pe_descriptions"] == 1
        assert meta["tables"]["pe_tags"] == 3
        assert meta["tables"]["pe_lineage"] == 1
        assert meta["tables"]["project_descriptions"] == 1

    def test_fiscal_years(self, metadata_db):
        """Distinct fiscal years are extracted."""
        meta = collect_metadata(metadata_db)
        assert "2025" in meta["fiscal_years"]
        assert "2026" in meta["fiscal_years"]

    def test_services(self, metadata_db):
        """Distinct services are extracted."""
        meta = collect_metadata(metadata_db)
        assert "Army" in meta["services"]
        assert "Navy" in meta["services"]

    def test_exhibit_types(self, metadata_db):
        """Distinct exhibit types are extracted."""
        meta = collect_metadata(metadata_db)
        assert "R-1" in meta["exhibit_types"]
        assert "R-2" in meta["exhibit_types"]

    def test_enrichment_pe_index(self, metadata_db):
        """PE index enrichment coverage is reported."""
        meta = collect_metadata(metadata_db)
        pe_idx = meta["enrichment"]["pe_index"]
        assert pe_idx["total"] == 2
        assert pe_idx["budget_lines_distinct_pes"] == 2
        assert pe_idx["coverage_pct"] == 100.0

    def test_enrichment_tags(self, metadata_db):
        """Tag enrichment statistics are reported."""
        meta = collect_metadata(metadata_db)
        tags = meta["enrichment"]["pe_tags"]
        assert tags["total"] == 3
        assert tags["distinct_tags"] == 3
        assert "structured" in tags["by_source"]

    def test_enrichment_descriptions(self, metadata_db):
        """Description enrichment coverage is reported."""
        meta = collect_metadata(metadata_db)
        desc = meta["enrichment"]["pe_descriptions"]
        assert desc["total"] == 1
        assert desc["distinct_pes"] == 1

    def test_enrichment_project_descriptions(self, metadata_db):
        """Project description enrichment coverage is reported."""
        meta = collect_metadata(metadata_db)
        proj = meta["enrichment"]["project_descriptions"]
        assert proj["total"] == 1
        assert proj["with_project_number"] == 1
        assert proj["pe_level_fallback"] == 0

    def test_enrichment_lineage(self, metadata_db):
        """Lineage enrichment count is reported."""
        meta = collect_metadata(metadata_db)
        lineage = meta["enrichment"]["pe_lineage"]
        assert lineage["total"] == 1

    def test_amounts(self, metadata_db):
        """Amount summaries are reported."""
        meta = collect_metadata(metadata_db)
        amounts = meta["amounts"]
        assert amounts["total_fy2026_request"] == 920.0  # 300+350+270
        assert amounts["total_fy2025_enacted"] == 630.0   # 200+250+180
        assert amounts["total_fy2024_actual"] == 340.0     # 100+150+90

    def test_generated_at(self, metadata_db):
        """Generated timestamp is included."""
        meta = collect_metadata(metadata_db)
        assert "generated_at" in meta
        assert "T" in meta["generated_at"]  # ISO format

    def test_missing_table_returns_none(self):
        """Missing tables return None for count instead of erroring."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        # No tables created at all
        meta = collect_metadata(conn)
        assert meta["tables"]["budget_lines"] is None
        assert meta["tables"]["pe_index"] is None
        assert meta["fiscal_years"] == []
        assert meta["services"] == []
        conn.close()

    def test_empty_database(self):
        """Empty tables return zero counts."""
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE budget_lines (
                id INTEGER PRIMARY KEY,
                fiscal_year TEXT,
                organization_name TEXT,
                exhibit_type TEXT,
                pe_number TEXT,
                amount_fy2024_actual REAL,
                amount_fy2025_enacted REAL,
                amount_fy2026_request REAL
            );
            CREATE TABLE pe_index (pe_number TEXT PRIMARY KEY);
            CREATE TABLE pe_descriptions (id INTEGER PRIMARY KEY, pe_number TEXT);
            CREATE TABLE pe_tags (id INTEGER PRIMARY KEY, pe_number TEXT, tag TEXT, tag_source TEXT);
            CREATE TABLE pe_lineage (id INTEGER PRIMARY KEY, source_pe TEXT, referenced_pe TEXT);
            CREATE TABLE project_descriptions (
                id INTEGER PRIMARY KEY, pe_number TEXT,
                project_number TEXT, section_header TEXT, description_text TEXT
            );
            CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY);
        """)
        meta = collect_metadata(conn)
        assert meta["tables"]["budget_lines"] == 0
        assert meta["fiscal_years"] == []
        assert meta["services"] == []
        conn.close()


class TestMetadataAPI:
    """Tests for the /api/v1/metadata endpoint."""

    @pytest.fixture
    def app_client(self, metadata_db, tmp_path):
        """Create a test FastAPI client with the metadata DB."""
        import os
        db_path = tmp_path / "test_api_meta.sqlite"

        # Copy the in-memory DB to a file for the API
        # We need to dump and reload since metadata_db is in-memory
        file_conn = sqlite3.connect(str(db_path))
        metadata_db.backup(file_conn)
        file_conn.close()

        os.environ["APP_DB_PATH"] = str(db_path)

        # Reload the database module to pick up new path
        import importlib
        import api.database
        importlib.reload(api.database)

        from api.app import create_app
        app = create_app()

        from fastapi.testclient import TestClient
        client = TestClient(app)
        yield client

        # Cleanup
        os.environ.pop("APP_DB_PATH", None)

    def test_metadata_endpoint_returns_200(self, app_client):
        """GET /api/v1/metadata returns 200."""
        resp = app_client.get("/api/v1/metadata")
        assert resp.status_code == 200

    def test_metadata_endpoint_has_tables(self, app_client):
        """Response includes table counts."""
        resp = app_client.get("/api/v1/metadata")
        data = resp.json()
        assert "tables" in data
        assert "budget_lines" in data["tables"]

    def test_metadata_endpoint_has_fiscal_years(self, app_client):
        """Response includes fiscal years."""
        resp = app_client.get("/api/v1/metadata")
        data = resp.json()
        assert "fiscal_years" in data

    def test_metadata_endpoint_has_enrichment(self, app_client):
        """Response includes enrichment coverage."""
        resp = app_client.get("/api/v1/metadata")
        data = resp.json()
        assert "enrichment" in data
