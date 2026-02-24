"""
Tests for Phase 3 Stream B API changes:
  B3.1: Spruill-style comparison table endpoint
  B3.2: Description search via source parameter
  B3.3: pe_descriptions_fts FTS5 search
  B3.4: Spruill detail=true sub-element rows (part of B3.1)
  B3.5: Enrichment coverage metadata endpoint
"""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient
from api.app import create_app
from api.database import get_db


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Create a test app with full schema for Phase 3 tests."""
    tmp = tmp_path_factory.mktemp("phase3_api_test")
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
            page_text TEXT, has_tables INTEGER, table_data TEXT,
            fiscal_year TEXT, exhibit_type TEXT
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
            exhibit_types TEXT,
            source TEXT NOT NULL DEFAULT 'budget_lines',
            updated_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE pe_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT,
            project_number TEXT,
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
        CREATE TABLE project_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT NOT NULL,
            project_number TEXT,
            project_title TEXT,
            fiscal_year TEXT,
            section_header TEXT NOT NULL,
            description_text TEXT NOT NULL,
            source_file TEXT,
            page_start INTEGER,
            page_end INTEGER,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE pdf_pe_numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT, pdf_page_id INTEGER,
            page_number INTEGER, source_file TEXT, fiscal_year TEXT
        );
        CREATE TABLE services_agencies (
            code TEXT PRIMARY KEY, full_name TEXT
        );
        CREATE TABLE exhibit_types (
            code TEXT PRIMARY KEY, display_name TEXT
        );

        -- FTS5 for pe_descriptions
        CREATE VIRTUAL TABLE pe_descriptions_fts USING fts5(
            pe_number, section_header, description_text,
            content='pe_descriptions', content_rowid='id'
        );

        INSERT INTO services_agencies VALUES ('Army', 'U.S. Army');
        INSERT INTO services_agencies VALUES ('Navy', 'U.S. Navy');
        INSERT INTO services_agencies VALUES ('DARPA', 'DARPA');
        INSERT INTO exhibit_types VALUES ('r1', 'RDT&E Summary');
        INSERT INTO exhibit_types VALUES ('r2', 'RDT&E Detail');

        -- PE 1: Army helicopter program
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title, pe_number,
             appropriation_code, appropriation_title,
             amount_fy2024_actual, amount_fy2025_enacted,
             amount_fy2025_total, amount_fy2026_request, amount_fy2026_total)
        VALUES
            ('army_r2.xlsx', 'r2', '2026', 'Army',
             'RDT&E Budget', 'Apache AH-64 Block III', '0604131A',
             'RDTE', 'RDT&E', 120000.0, 140000.0, 140000.0, 150000.0, 150000.0);

        -- PE 1: Second line item for detail view
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title, pe_number,
             appropriation_code, appropriation_title,
             amount_fy2024_actual, amount_fy2025_enacted,
             amount_fy2025_total, amount_fy2026_request, amount_fy2026_total)
        VALUES
            ('army_r2.xlsx', 'r2', '2026', 'Army',
             'RDT&E Budget', 'Apache Sensor Upgrade', '0604131A',
             'RDTE', 'RDT&E', 30000.0, 35000.0, 35000.0, 40000.0, 40000.0);

        -- PE 2: Navy sensor program
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title, pe_number,
             appropriation_code, appropriation_title,
             amount_fy2024_actual, amount_fy2025_enacted,
             amount_fy2025_total, amount_fy2026_request, amount_fy2026_total)
        VALUES
            ('navy_r2.xlsx', 'r2', '2026', 'Navy',
             'RDT&E Budget', 'Advanced Sensor Suite', '0603292N',
             'RDTE', 'RDT&E', 0.0, 0.0, 0.0, 250000.0, 250000.0);

        -- PE 3: DARPA program
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title, pe_number,
             appropriation_code, appropriation_title,
             amount_fy2024_actual, amount_fy2025_enacted,
             amount_fy2025_total, amount_fy2026_request, amount_fy2026_total)
        VALUES
            ('darpa_r2.xlsx', 'r2', '2026', 'DARPA',
             'RDT&E Budget', 'Tactical Technology', '0602702E',
             'RDTE', 'RDT&E', 500000.0, 520000.0, 520000.0, 550000.0, 550000.0);

        INSERT INTO budget_lines_fts(rowid, account_title, line_item_title,
            budget_activity_title)
        SELECT id, account_title, line_item_title, budget_activity_title
        FROM budget_lines;

        INSERT INTO pe_index (pe_number, display_title, organization_name,
            budget_type, fiscal_years, exhibit_types) VALUES
            ('0604131A', 'Apache AH-64 Block III', 'Army', 'RDT&E',
             '["2026"]', '["r2"]'),
            ('0603292N', 'Advanced Sensor Suite', 'Navy', 'RDT&E',
             '["2026"]', '["r2"]'),
            ('0602702E', 'Tactical Technology', 'DARPA', 'RDT&E',
             '["2026"]', '["r2"]');

        INSERT INTO pe_tags VALUES
            (NULL, '0604131A', NULL, 'aviation', 'structured', 1.0, '["army_r1.xlsx"]'),
            (NULL, '0603292N', NULL, 'sensors', 'structured', 1.0, '["navy_r1.xlsx"]'),
            (NULL, '0602702E', NULL, 'applied-research', 'structured', 1.0, '["darpa_r1.xlsx"]');

        INSERT INTO pe_lineage VALUES
            (NULL, '0604131A', '0603292N', 'name_match', 0.6, '2026', 'aviation sensors'),
            (NULL, '0602702E', '0604131A', 'explicit_pe_ref', 0.95, '2026', 'PE ref');

        INSERT INTO pe_descriptions VALUES
            (NULL, '0604131A', '2026', 'army_r2.pdf', 1, 3, 'Mission Description',
             'The Apache AH-64 Block III program provides advanced helicopter capabilities.'),
            (NULL, '0604131A', '2026', 'army_r2.pdf', 4, 5, 'Accomplishments',
             'Completed flight testing of the new avionics suite.'),
            (NULL, '0603292N', '2026', 'navy_r2.pdf', 1, 2, 'Mission Description',
             'Advanced sensor technology for maritime reconnaissance operations.'),
            (NULL, '0602702E', '2026', 'darpa_r2.pdf', 1, 2, 'Mission Description',
             'Tactical technology development for hypersonic weapons and directed energy.');

        -- Populate pe_descriptions_fts
        INSERT INTO pe_descriptions_fts(rowid, pe_number, section_header, description_text)
        SELECT id, pe_number, section_header, description_text
        FROM pe_descriptions;

        INSERT INTO project_descriptions VALUES
            (NULL, '0604131A', 'P001', 'Apache Block III', '2026',
             'Mission Description', 'Apache project details', 'army_r2.pdf', 1, 2,
             datetime('now'));

        -- PDF pages
        INSERT INTO pdf_pages (id, source_file, page_number, page_text, has_tables,
            fiscal_year, exhibit_type)
        VALUES
            (1, 'army_r2.pdf', 5, 'Apache AH-64 Block III details...', 0,
             '2026', 'r2'),
            (2, 'navy_r2.pdf', 1, 'Advanced sensor technology for maritime ops', 0,
             '2026', 'r2');
    """)
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)

    def _get_db_override():
        c = sqlite3.connect(str(db_path), check_same_thread=False)
        c.row_factory = sqlite3.Row
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_db] = _get_db_override
    return TestClient(app, raise_server_exceptions=False)


# ── B3.1: Spruill Endpoint Tests ─────────────────────────────────────────────

class TestSpruillEndpoint:
    """Tests for GET /api/v1/pe/spruill."""

    def test_spruill_returns_correct_structure(self, client):
        """Spruill endpoint with 2+ PEs returns correct structure."""
        resp = client.get(
            "/api/v1/pe/spruill",
            params={"pe": ["0604131A", "0603292N"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pe_count"] == 2
        assert "fiscal_years" in data
        assert "rows" in data
        assert isinstance(data["rows"], list)

    def test_spruill_subtotal_rows(self, client):
        """Spruill endpoint returns subtotal rows for each PE."""
        resp = client.get(
            "/api/v1/pe/spruill",
            params={"pe": ["0604131A", "0603292N"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        subtotal_rows = [r for r in data["rows"] if r["is_subtotal"]]
        assert len(subtotal_rows) == 2
        pe_numbers = [r["pe_number"] for r in subtotal_rows]
        assert "0604131A" in pe_numbers
        assert "0603292N" in pe_numbers

    def test_spruill_subtotal_has_amounts(self, client):
        """Spruill subtotal rows contain amounts."""
        resp = client.get(
            "/api/v1/pe/spruill",
            params={"pe": ["0604131A", "0603292N"]},
        )
        data = resp.json()
        for row in data["rows"]:
            if row["is_subtotal"]:
                assert "amounts" in row
                assert "fy2026_request" in row["amounts"]

    def test_spruill_subtotal_aggregates_line_items(self, client):
        """Spruill subtotal should aggregate multiple line items for a PE."""
        resp = client.get(
            "/api/v1/pe/spruill",
            params={"pe": ["0604131A", "0603292N"]},
        )
        data = resp.json()
        for row in data["rows"]:
            if row["is_subtotal"] and row["pe_number"] == "0604131A":
                # 150000 + 40000 = 190000
                assert row["amounts"]["fy2026_request"] == 190000.0

    def test_spruill_with_three_pes(self, client):
        """Spruill endpoint works with 3 PEs."""
        resp = client.get(
            "/api/v1/pe/spruill",
            params={"pe": ["0604131A", "0603292N", "0602702E"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pe_count"] == 3
        subtotals = [r for r in data["rows"] if r["is_subtotal"]]
        assert len(subtotals) == 3

    def test_spruill_display_title_from_pe_index(self, client):
        """Spruill rows include display_title from pe_index."""
        resp = client.get(
            "/api/v1/pe/spruill",
            params={"pe": ["0602702E", "0604131A"]},
        )
        data = resp.json()
        darpa_row = next(r for r in data["rows"] if r["pe_number"] == "0602702E" and r["is_subtotal"])
        assert darpa_row["display_title"] == "Tactical Technology"
        assert darpa_row["organization_name"] == "DARPA"

    def test_spruill_fiscal_years_included(self, client):
        """Spruill response includes fiscal_years list."""
        resp = client.get(
            "/api/v1/pe/spruill",
            params={"pe": ["0604131A", "0603292N"]},
        )
        data = resp.json()
        assert "2026" in data["fiscal_years"]

    def test_spruill_invalid_pe_count_too_few(self, client):
        """Spruill with <2 PEs returns 400."""
        resp = client.get(
            "/api/v1/pe/spruill",
            params={"pe": ["0604131A"]},
        )
        assert resp.status_code == 400
        assert "At least 2" in resp.json()["detail"]

    def test_spruill_invalid_pe_count_too_many(self, client):
        """Spruill with >20 PEs returns 400."""
        pes = [f"060000{i:02d}A" for i in range(21)]
        resp = client.get(
            "/api/v1/pe/spruill",
            params={"pe": pes},
        )
        assert resp.status_code == 400
        assert "Maximum 20" in resp.json()["detail"]


# ── B3.4: Spruill Detail Tests ───────────────────────────────────────────────

class TestSpruillDetail:
    """Tests for Spruill endpoint with detail=true (sub-element rows)."""

    def test_spruill_detail_has_subelement_rows(self, client):
        """With detail=true, sub-element rows follow each PE subtotal."""
        resp = client.get(
            "/api/v1/pe/spruill",
            params={"pe": ["0604131A", "0603292N"], "detail": "true"},
        )
        assert resp.status_code == 200
        data = resp.json()
        detail_rows = [r for r in data["rows"] if not r["is_subtotal"]]
        assert len(detail_rows) > 0

    def test_spruill_detail_rows_have_line_item_title(self, client):
        """Detail rows include line_item_title and exhibit_type."""
        resp = client.get(
            "/api/v1/pe/spruill",
            params={"pe": ["0604131A", "0603292N"], "detail": "true"},
        )
        data = resp.json()
        detail_rows = [r for r in data["rows"] if not r["is_subtotal"]]
        for row in detail_rows:
            assert "line_item_title" in row
            assert "exhibit_type" in row
            assert "amounts" in row

    def test_spruill_detail_false_no_subelement_rows(self, client):
        """With detail=false, no sub-element rows appear."""
        resp = client.get(
            "/api/v1/pe/spruill",
            params={"pe": ["0604131A", "0603292N"], "detail": "false"},
        )
        data = resp.json()
        detail_rows = [r for r in data["rows"] if not r["is_subtotal"]]
        assert len(detail_rows) == 0

    def test_spruill_detail_pe_has_two_line_items(self, client):
        """PE 0604131A has 2 line items visible in detail mode."""
        resp = client.get(
            "/api/v1/pe/spruill",
            params={"pe": ["0604131A", "0603292N"], "detail": "true"},
        )
        data = resp.json()
        pe_a_details = [
            r for r in data["rows"]
            if r["pe_number"] == "0604131A" and not r["is_subtotal"]
        ]
        assert len(pe_a_details) == 2
        titles = {r["line_item_title"] for r in pe_a_details}
        assert "Apache AH-64 Block III" in titles
        assert "Apache Sensor Upgrade" in titles


# ── B3.2: Description Search Tests ───────────────────────────────────────────

class TestDescriptionSearch:
    """Tests for search endpoint with source parameter."""

    def test_search_default_source_budget_lines(self, client):
        """Default source=budget_lines searches only budget lines."""
        resp = client.get(
            "/api/v1/search",
            params={"q": "Apache"},
        )
        assert resp.status_code == 200
        data = resp.json()
        result_types = {r["result_type"] for r in data["results"]}
        # Should not include "description" results
        assert "description" not in result_types

    def test_search_source_descriptions(self, client):
        """source=descriptions searches pe_descriptions only."""
        resp = client.get(
            "/api/v1/search",
            params={"q": "helicopter", "source": "descriptions"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # All results should be description type (or empty if no matches)
        for r in data["results"]:
            assert r["result_type"] == "description"

    def test_search_source_descriptions_returns_data(self, client):
        """Description search results contain pe_number and section_header."""
        resp = client.get(
            "/api/v1/search",
            params={"q": "Apache", "source": "descriptions"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) > 0
        for r in data["results"]:
            assert r["result_type"] == "description"
            assert "pe_number" in r["data"]
            assert "section_header" in r["data"]

    def test_search_source_both(self, client):
        """source=both returns budget_line + description results."""
        resp = client.get(
            "/api/v1/search",
            params={"q": "Apache", "source": "both"},
        )
        assert resp.status_code == 200
        data = resp.json()
        result_types = {r["result_type"] for r in data["results"]}
        # Should have at least budget_line from FTS
        assert "budget_line" in result_types or "description" in result_types

    def test_search_source_descriptions_hypersonic(self, client):
        """Searching for 'hypersonic' in descriptions returns DARPA PE."""
        resp = client.get(
            "/api/v1/search",
            params={"q": "hypersonic", "source": "descriptions"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) > 0
        pe_numbers = [r["data"]["pe_number"] for r in data["results"]]
        assert "0602702E" in pe_numbers

    def test_search_source_descriptions_no_budget_lines(self, client):
        """source=descriptions should NOT include budget_line results."""
        resp = client.get(
            "/api/v1/search",
            params={"q": "Apache", "source": "descriptions"},
        )
        data = resp.json()
        for r in data["results"]:
            assert r["result_type"] != "budget_line"
            assert r["result_type"] != "pdf_page"


# ── B3.3: pe_descriptions_fts Search Tests ───────────────────────────────────

class TestPeDescriptionsFts:
    """Tests for FTS5 search on pe_descriptions_fts."""

    def test_fts_search_finds_helicopter(self, client):
        """FTS5 search for 'helicopter' finds Apache PE description."""
        resp = client.get(
            "/api/v1/search",
            params={"q": "helicopter", "source": "descriptions"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) > 0
        pe_numbers = [r["data"]["pe_number"] for r in data["results"]]
        assert "0604131A" in pe_numbers

    def test_fts_search_finds_maritime(self, client):
        """FTS5 search for 'maritime' finds Navy PE."""
        resp = client.get(
            "/api/v1/search",
            params={"q": "maritime", "source": "descriptions"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) > 0
        pe_numbers = [r["data"]["pe_number"] for r in data["results"]]
        assert "0603292N" in pe_numbers

    def test_fts_search_no_results(self, client):
        """FTS5 search for nonexistent term returns empty."""
        resp = client.get(
            "/api/v1/search",
            params={"q": "zznonexistent", "source": "descriptions"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 0


# ── B3.5: Enrichment Metadata Endpoint Tests ─────────────────────────────────

class TestEnrichmentMetadata:
    """Tests for GET /api/v1/metadata/enrichment."""

    def test_enrichment_metadata_returns_200(self, client):
        """Enrichment metadata endpoint returns 200."""
        resp = client.get("/api/v1/metadata/enrichment")
        assert resp.status_code == 200

    def test_enrichment_metadata_has_structure(self, client):
        """Enrichment metadata has the expected top-level structure."""
        resp = client.get("/api/v1/metadata/enrichment")
        data = resp.json()
        assert "enrichment" in data
        enr = data["enrichment"]
        assert "pe_count" in enr
        assert "pe_with_descriptions" in enr
        assert "pe_with_tags" in enr
        assert "pe_with_lineage" in enr
        assert "total_tags" in enr
        assert "total_descriptions" in enr
        assert "last_enrichment" in enr

    def test_enrichment_metadata_pe_count(self, client):
        """pe_count reflects the pe_index table."""
        resp = client.get("/api/v1/metadata/enrichment")
        data = resp.json()["enrichment"]
        # We inserted 3 PEs into pe_index
        assert data["pe_count"] == 3

    def test_enrichment_metadata_pe_with_descriptions(self, client):
        """pe_with_descriptions reflects distinct PEs in pe_descriptions."""
        resp = client.get("/api/v1/metadata/enrichment")
        data = resp.json()["enrichment"]
        # 3 PEs have descriptions
        assert data["pe_with_descriptions"] == 3

    def test_enrichment_metadata_pe_with_tags(self, client):
        """pe_with_tags reflects distinct PEs in pe_tags."""
        resp = client.get("/api/v1/metadata/enrichment")
        data = resp.json()["enrichment"]
        assert data["pe_with_tags"] == 3

    def test_enrichment_metadata_pe_with_lineage(self, client):
        """pe_with_lineage reflects distinct source PEs in pe_lineage."""
        resp = client.get("/api/v1/metadata/enrichment")
        data = resp.json()["enrichment"]
        # 2 source_pe values in pe_lineage (0604131A, 0602702E)
        assert data["pe_with_lineage"] == 2

    def test_enrichment_metadata_total_tags(self, client):
        """total_tags reflects total rows in pe_tags."""
        resp = client.get("/api/v1/metadata/enrichment")
        data = resp.json()["enrichment"]
        assert data["total_tags"] == 3

    def test_enrichment_metadata_total_descriptions(self, client):
        """total_descriptions reflects total rows in pe_descriptions."""
        resp = client.get("/api/v1/metadata/enrichment")
        data = resp.json()["enrichment"]
        assert data["total_descriptions"] == 4

    def test_enrichment_metadata_tag_sources(self, client):
        """tag_sources breakdown is included."""
        resp = client.get("/api/v1/metadata/enrichment")
        data = resp.json()["enrichment"]
        assert "tag_sources" in data
        assert data["tag_sources"]["structured"] == 3

    def test_enrichment_metadata_total_projects(self, client):
        """total_projects reflects project_descriptions count."""
        resp = client.get("/api/v1/metadata/enrichment")
        data = resp.json()["enrichment"]
        assert data["total_projects"] == 1

    def test_enrichment_metadata_last_enrichment(self, client):
        """last_enrichment is a non-None timestamp."""
        resp = client.get("/api/v1/metadata/enrichment")
        data = resp.json()["enrichment"]
        assert data["last_enrichment"] is not None
