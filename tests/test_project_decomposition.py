"""Tests for HAWK-1: Project-level narrative decomposition.

Tests both the detect_project_boundaries() parser in utils/pdf_sections.py
and the Phase 5 enrichment that populates the project_descriptions table.
"""

import sqlite3

import pytest

from utils.pdf_sections import detect_project_boundaries


# ── detect_project_boundaries tests ──────────────────────────────────────────


class TestDetectProjectBoundaries:
    """Tests for the project boundary detection in R-2 narrative text."""

    def test_colon_dash_format(self):
        """Detect 'Project: 1234 — Title' format."""
        text = (
            "Some intro text\n"
            "Project: 1234 — Advanced Targeting System\n"
            "This project develops targeting capabilities.\n"
            "Project: 5678 — Sensor Integration\n"
            "This project integrates sensors.\n"
        )
        projects = detect_project_boundaries(text)
        assert len(projects) == 2
        assert projects[0]["project_number"] == "1234"
        assert projects[0]["project_title"] == "Advanced Targeting System"
        assert "targeting capabilities" in projects[0]["text"]
        assert projects[1]["project_number"] == "5678"
        assert projects[1]["project_title"] == "Sensor Integration"

    def test_number_colon_format(self):
        """Detect 'Project 1234: Title' format."""
        text = (
            "Project 1234: Advanced Targeting System\n"
            "FY2025 accomplishments include...\n"
        )
        projects = detect_project_boundaries(text)
        assert len(projects) == 1
        assert projects[0]["project_number"] == "1234"
        assert projects[0]["project_title"] == "Advanced Targeting System"

    def test_project_number_title_format(self):
        """Detect 'Project Number: X  Project Title: Y' format."""
        text = (
            "Project Number: ABC-123   Project Title: Missile Defense\n"
            "The program provides...\n"
        )
        projects = detect_project_boundaries(text)
        assert len(projects) == 1
        assert projects[0]["project_number"] == "ABC-123"
        assert projects[0]["project_title"] == "Missile Defense"

    def test_hash_format(self):
        """Detect 'Project #1234 Title' format."""
        text = (
            "Project #9999 Next Gen Fighter\n"
            "Development of a next generation fighter.\n"
        )
        projects = detect_project_boundaries(text)
        assert len(projects) == 1
        assert projects[0]["project_number"] == "9999"
        assert projects[0]["project_title"] == "Next Gen Fighter"

    def test_no_projects(self):
        """Return empty list when no project boundaries found."""
        text = "This is just regular PE-level description text with no projects."
        projects = detect_project_boundaries(text)
        assert projects == []

    def test_empty_input(self):
        """Handle empty/None input gracefully."""
        assert detect_project_boundaries("") == []
        assert detect_project_boundaries(None) == []

    def test_case_insensitive(self):
        """Project boundary detection should be case-insensitive."""
        text = "PROJECT: 1234 — Test\nSome description.\n"
        projects = detect_project_boundaries(text)
        assert len(projects) == 1
        assert projects[0]["project_number"] == "1234"

    def test_multiple_projects_with_text_between(self):
        """Each project captures text up to the next boundary."""
        text = (
            "Project: A001 — First Project\n"
            "First project does X and Y.\n"
            "It also handles Z.\n"
            "Project: B002 — Second Project\n"
            "Second project focuses on W.\n"
            "Project: C003 — Third Project\n"
            "Third project covers V.\n"
        )
        projects = detect_project_boundaries(text)
        assert len(projects) == 3
        assert "First project does X" in projects[0]["text"]
        assert "Second project focuses" in projects[1]["text"]
        assert "Third project covers" in projects[2]["text"]

    def test_deduplication_by_project_number(self):
        """Duplicate project numbers are deduplicated (first occurrence wins)."""
        text = (
            "Project: 1234 — Title A\n"
            "First mention.\n"
            "Project: 1234 — Title A\n"
            "Duplicate mention.\n"
        )
        projects = detect_project_boundaries(text)
        assert len(projects) == 1
        assert projects[0]["project_number"] == "1234"


# ── Phase 5 integration tests ───────────────────────────────────────────────


class TestPhase5Integration:
    """Integration tests for Phase 5 project-level decomposition."""

    @pytest.fixture
    def enrichment_db(self, tmp_path):
        """Create a minimal in-memory DB with pe_index and pe_descriptions."""
        db_path = tmp_path / "test.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        conn.executescript("""
            CREATE TABLE pe_index (
                pe_number TEXT PRIMARY KEY,
                display_title TEXT,
                organization_name TEXT,
                budget_type TEXT,
                fiscal_years TEXT,
                exhibit_types TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
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
            CREATE INDEX idx_proj_desc_pe ON project_descriptions(pe_number);
            CREATE INDEX idx_proj_desc_proj ON project_descriptions(project_number);
            CREATE INDEX idx_proj_desc_fy ON project_descriptions(fiscal_year);
        """)

        # Insert test data
        conn.execute("""
            INSERT INTO pe_index (pe_number, display_title)
            VALUES ('0603285E', 'Advanced Targeting')
        """)
        conn.commit()
        yield conn
        conn.close()

    def test_phase5_with_project_boundaries(self, enrichment_db):
        """Phase 5 decomposes text into project-level rows."""
        from enrich_budget_db import run_phase5

        enrichment_db.execute("""
            INSERT INTO pe_descriptions (pe_number, fiscal_year, source_file,
                page_start, page_end, section_header, description_text)
            VALUES ('0603285E', '2026', 'test.pdf', 1, 3,
                'Accomplishments/Planned Program',
                'Project: 1234 — Targeting Sensor
Accomplishments/Planned Program
In FY2025, the program completed sensor testing.
Project: 5678 — Integration Hub
Accomplishments/Planned Program
In FY2025, integration testing was completed.')
        """)
        enrichment_db.commit()

        count = run_phase5(enrichment_db)
        assert count > 0

        rows = enrichment_db.execute(
            "SELECT * FROM project_descriptions ORDER BY project_number"
        ).fetchall()
        # Should have project-level rows
        proj_nums = [r["project_number"] for r in rows if r["project_number"]]
        assert "1234" in proj_nums or "5678" in proj_nums

    def test_phase5_pe_level_fallback(self, enrichment_db):
        """Phase 5 uses PE-level fallback when no project boundaries found."""
        from enrich_budget_db import run_phase5

        enrichment_db.execute("""
            INSERT INTO pe_descriptions (pe_number, fiscal_year, source_file,
                page_start, page_end, section_header, description_text)
            VALUES ('0603285E', '2026', 'test2.pdf', 1, 2,
                'Description',
                'This PE covers general research activities with no project-level breakdown. It includes various efforts across multiple domains.')
        """)
        enrichment_db.commit()

        count = run_phase5(enrichment_db)
        assert count > 0

        rows = enrichment_db.execute(
            "SELECT * FROM project_descriptions"
        ).fetchall()
        # Should have PE-level fallback rows (project_number IS NULL)
        assert any(r["project_number"] is None for r in rows)

    def test_phase5_empty_descriptions(self, enrichment_db):
        """Phase 5 returns 0 when pe_descriptions is empty."""
        from enrich_budget_db import run_phase5

        count = run_phase5(enrichment_db)
        assert count == 0
