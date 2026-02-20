"""
Tests for api/routes/pe.py — PE-centric endpoints.

Calls route functions directly with an in-memory SQLite connection,
following the same pattern as test_budget_lines_endpoint.py.
"""
from __future__ import annotations

import io
import json
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException

from api.routes.pe import (
    get_pe,
    get_pe_years,
    get_pe_changes,
    get_top_changes,
    compare_pes,
    get_pe_subelements,
    get_pe_descriptions,
    get_pe_related,
    list_pes,
    list_tags,
    export_pe_table,
    export_pe_pages,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_db() -> sqlite3.Connection:
    """In-memory DB with all tables needed by pe.py endpoints."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            exhibit_type TEXT,
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
            pe_number TEXT,
            budget_type TEXT,
            appropriation_title TEXT,
            amount_fy2024_actual REAL,
            amount_fy2025_enacted REAL,
            amount_fy2025_total REAL,
            amount_fy2026_request REAL,
            amount_fy2026_total REAL,
            quantity_fy2024 REAL,
            quantity_fy2025 REAL,
            quantity_fy2026_request REAL
        );

        CREATE TABLE pdf_pages (
            id INTEGER PRIMARY KEY,
            source_file TEXT,
            source_category TEXT,
            fiscal_year TEXT,
            exhibit_type TEXT,
            page_number INTEGER,
            page_text TEXT,
            has_tables INTEGER DEFAULT 0,
            table_data TEXT
        );

        CREATE TABLE pdf_pe_numbers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pdf_page_id INTEGER REFERENCES pdf_pages(id),
            pe_number TEXT NOT NULL,
            page_number INTEGER,
            source_file TEXT NOT NULL,
            fiscal_year TEXT
        );

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

        CREATE TABLE pe_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT NOT NULL,
            tag TEXT NOT NULL,
            tag_source TEXT NOT NULL,
            confidence REAL DEFAULT 1.0,
            source_files TEXT,
            UNIQUE(pe_number, tag, tag_source)
        );

        CREATE TABLE pe_lineage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_pe TEXT NOT NULL,
            referenced_pe TEXT NOT NULL,
            fiscal_year TEXT,
            source_file TEXT,
            page_number INTEGER,
            context_snippet TEXT,
            link_type TEXT,
            confidence REAL DEFAULT 1.0
        );
    """)
    return conn


@pytest.fixture()
def db():
    conn = _make_db()
    yield conn
    conn.close()


@pytest.fixture()
def populated_db():
    """DB seeded with two PEs, budget lines, tags, descriptions, and lineage."""
    conn = _make_db()

    # pe_index entries
    conn.executemany("""
        INSERT INTO pe_index (pe_number, display_title, organization_name, budget_type,
                              fiscal_years, exhibit_types)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [
        ("0602120A", "Radar Technology", "Army", "rdte",
         '["2025","2026"]', '["r1","r2"]'),
        ("0603000A", "Fighter Systems", "Air Force", "rdte",
         '["2026"]', '["r1"]'),
    ])

    # budget_lines for 0602120A
    conn.executemany("""
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             line_item_title, pe_number, budget_type, appropriation_title,
             amount_fy2024_actual, amount_fy2025_enacted, amount_fy2025_total,
             amount_fy2026_request, amount_fy2026_total,
             quantity_fy2024, quantity_fy2025, quantity_fy2026_request)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        ("army/r1.xlsx", "r1", "2025", "Army", "Radar Technology",
         "0602120A", "rdte", "RDT&E, Army",
         1000.0, 1200.0, 1200.0, 1400.0, 1400.0, None, None, None),
        ("army/r1.xlsx", "r1", "2026", "Army", "Radar Technology",
         "0602120A", "rdte", "RDT&E, Army",
         1000.0, 1200.0, 1200.0, 1400.0, 1400.0, None, None, None),
        ("army/r2.xlsx", "r2", "2026", "Army", "Radar Sub-element",
         "0602120A", "rdte", "RDT&E, Army",
         500.0, 600.0, 600.0, 700.0, 700.0, 2.0, 3.0, 4.0),
    ])

    # budget_lines for 0603000A
    conn.execute("""
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             line_item_title, pe_number, budget_type, appropriation_title,
             amount_fy2026_request)
        VALUES ('af/r1.xlsx', 'r1', '2026', 'Air Force', 'Fighter Systems',
                '0603000A', 'rdte', 'RDT&E, Air Force', 9000.0)
    """)

    # tags
    conn.executemany("""
        INSERT INTO pe_tags (pe_number, tag, tag_source, confidence)
        VALUES (?, ?, ?, ?)
    """, [
        ("0602120A", "army", "structured", 1.0),
        ("0602120A", "rdte", "structured", 1.0),
        ("0602120A", "radar", "keyword", 0.9),
        ("0603000A", "air-force", "structured", 1.0),
    ])

    # descriptions
    conn.executemany("""
        INSERT INTO pe_descriptions
            (pe_number, fiscal_year, source_file, page_start, page_end, description_text)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [
        ("0602120A", "2026", "army/r2.pdf", 1, 2,
         "Radar technology development for counter-UAS missions."),
        ("0602120A", "2025", "army/r2_fy25.pdf", 5, 6,
         "Early radar prototype testing results."),
    ])

    # pdf_pages (for export/pages test)
    conn.execute("""
        INSERT INTO pdf_pages (source_file, source_category, page_number, page_text)
        VALUES ('army/r2.pdf', 'Army', 1, 'Program Element 0602120A radar development.')
    """)
    conn.execute("""
        INSERT INTO pdf_pages (source_file, source_category, page_number, page_text)
        VALUES ('army/r2.pdf', 'Army', 2, 'Continued radar system testing details.')
    """)

    # lineage
    conn.execute("""
        INSERT INTO pe_lineage
            (source_pe, referenced_pe, fiscal_year, source_file, page_number,
             context_snippet, link_type, confidence)
        VALUES ('0602120A', '0603000A', '2026', 'army/r2.pdf', 1,
                '...supports 0603000A through shared components...', 'explicit_pe_ref', 0.95)
    """)

    conn.commit()
    yield conn
    conn.close()


# ── get_pe tests ──────────────────────────────────────────────────────────────

class TestGetPe:
    def test_returns_full_record(self, populated_db):
        result = get_pe("0602120A", conn=populated_db)
        assert result["pe_number"] == "0602120A"
        assert "index" in result
        assert "funding" in result
        assert "tags" in result
        assert "related" in result

    def test_fiscal_years_parsed(self, populated_db):
        result = get_pe("0602120A", conn=populated_db)
        assert isinstance(result["index"]["fiscal_years"], list)
        assert "2026" in result["index"]["fiscal_years"]

    def test_tags_present(self, populated_db):
        result = get_pe("0602120A", conn=populated_db)
        tag_names = [t["tag"] for t in result["tags"]]
        assert "army" in tag_names
        assert "radar" in tag_names

    def test_related_present(self, populated_db):
        result = get_pe("0602120A", conn=populated_db)
        refs = [r["referenced_pe"] for r in result["related"]]
        assert "0603000A" in refs

    def test_summary_stats(self, populated_db):
        result = get_pe("0602120A", conn=populated_db)
        s = result["summary"]
        assert s["funding_rows"] == 3
        assert s["tag_count"] == 3  # army, rdte, radar
        assert s["description_count"] == 2
        assert s["related_count"] == 1

    def test_not_found_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            get_pe("9999999X", conn=db)
        assert exc_info.value.status_code == 404


# ── get_pe_years tests ────────────────────────────────────────────────────────

class TestGetPeYears:
    def test_returns_year_matrix(self, populated_db):
        result = get_pe_years("0602120A", conn=populated_db)
        assert result["pe_number"] == "0602120A"
        assert len(result["years"]) > 0

    def test_aggregated_amounts(self, populated_db):
        result = get_pe_years("0602120A", conn=populated_db)
        years = {r["fiscal_year"]: r for r in result["years"]}
        # 2026 has two r1 and one r2 row
        assert "2026" in years

    def test_not_found_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            get_pe_years("9999999X", conn=db)
        assert exc_info.value.status_code == 404


# ── get_pe_changes tests ─────────────────────────────────────────────────

class TestGetPeChanges:
    def test_returns_changes(self, populated_db):
        result = get_pe_changes("0602120A", conn=populated_db)
        assert result["pe_number"] == "0602120A"
        assert "total_fy2025" in result
        assert "total_fy2026_request" in result
        assert "total_delta" in result
        assert "pct_change" in result
        assert "line_items" in result

    def test_delta_calculation(self, populated_db):
        result = get_pe_changes("0602120A", conn=populated_db)
        assert result["total_delta"] == result["total_fy2026_request"] - result["total_fy2025"]

    def test_line_items_sorted_by_delta(self, populated_db):
        result = get_pe_changes("0602120A", conn=populated_db)
        if len(result["line_items"]) >= 2:
            deltas = [abs(li["delta"]) for li in result["line_items"]]
            assert deltas == sorted(deltas, reverse=True)

    def test_empty_pe_returns_empty(self, db):
        result = get_pe_changes("9999999X", conn=db)
        assert result["total_delta"] == 0
        assert len(result["line_items"]) == 0


# ── get_top_changes tests ────────────────────────────────────────────────

class TestGetTopChanges:
    def test_returns_ranked_items(self, populated_db):
        result = get_top_changes(direction=None, service=None, limit=20,
                                 conn=populated_db)
        assert result["count"] > 0
        assert all("pe_number" in i for i in result["items"])

    def test_items_sorted_by_abs_delta(self, populated_db):
        result = get_top_changes(direction=None, service=None, limit=20,
                                 conn=populated_db)
        if len(result["items"]) >= 2:
            deltas = [abs(i["delta"]) for i in result["items"]]
            assert deltas == sorted(deltas, reverse=True)

    def test_direction_filter_increase(self, populated_db):
        result = get_top_changes(direction="increase", service=None, limit=20,
                                 conn=populated_db)
        for item in result["items"]:
            assert item["delta"] > 0

    def test_direction_filter_decrease(self, populated_db):
        result = get_top_changes(direction="decrease", service=None, limit=20,
                                 conn=populated_db)
        for item in result["items"]:
            assert item["delta"] < 0

    def test_service_filter(self, populated_db):
        result = get_top_changes(direction=None, service="Army", limit=20,
                                 conn=populated_db)
        for item in result["items"]:
            assert "Army" in item["organization_name"]

    def test_change_type_present(self, populated_db):
        result = get_top_changes(direction=None, service=None, limit=20,
                                 conn=populated_db)
        valid_types = {"new", "terminated", "increase", "decrease", "flat"}
        for item in result["items"]:
            assert item["change_type"] in valid_types


# ── compare_pes tests ────────────────────────────────────────────────────

class TestComparePes:
    def test_compare_two_pes(self, populated_db):
        result = compare_pes(pe=["0602120A", "0603000A"], conn=populated_db)
        assert result["count"] == 2
        pe_nums = [i["pe_number"] for i in result["items"]]
        assert "0602120A" in pe_nums
        assert "0603000A" in pe_nums

    def test_items_have_funding(self, populated_db):
        result = compare_pes(pe=["0602120A", "0603000A"], conn=populated_db)
        for item in result["items"]:
            assert "funding" in item
            if item["pe_number"] == "0603000A":
                assert item["funding"]["fy2026_request"] == 9000.0

    def test_items_have_metadata(self, populated_db):
        result = compare_pes(pe=["0602120A", "0603000A"], conn=populated_db)
        for item in result["items"]:
            assert "display_title" in item
            assert "organization_name" in item

    def test_too_few_pes_raises_400(self, populated_db):
        with pytest.raises(HTTPException) as exc_info:
            compare_pes(pe=["0602120A"], conn=populated_db)
        assert exc_info.value.status_code == 400

    def test_too_many_pes_raises_400(self, populated_db):
        with pytest.raises(HTTPException) as exc_info:
            compare_pes(pe=[f"{i:07d}A" for i in range(11)], conn=populated_db)
        assert exc_info.value.status_code == 400


# ── get_pe_subelements tests ──────────────────────────────────────────────────

class TestGetPeSubelements:
    def test_returns_all_without_fy(self, populated_db):
        result = get_pe_subelements("0602120A", fy=None, conn=populated_db)
        assert result["count"] == 3  # 2 r1 rows + 1 r2 row

    def test_filter_by_fy(self, populated_db):
        result = get_pe_subelements("0602120A", fy="2025", conn=populated_db)
        assert result["fiscal_year"] == "2025"
        assert result["count"] == 1

    def test_fy_2026_includes_r2(self, populated_db):
        result = get_pe_subelements("0602120A", fy="2026", conn=populated_db)
        exhibit_types = {r["exhibit_type"] for r in result["subelements"]}
        assert "r2" in exhibit_types

    def test_empty_pe_returns_zero(self, db):
        result = get_pe_subelements("9999999X", fy=None, conn=db)
        assert result["count"] == 0


# ── get_pe_descriptions tests ─────────────────────────────────────────────────

class TestGetPeDescriptions:
    def test_returns_descriptions(self, populated_db):
        result = get_pe_descriptions("0602120A", fy=None, section=None,
                                     limit=20, offset=0, conn=populated_db)
        assert result["total"] == 2
        assert len(result["descriptions"]) == 2

    def test_filter_by_fy(self, populated_db):
        result = get_pe_descriptions("0602120A", fy="2026", section=None,
                                     limit=20, offset=0, conn=populated_db)
        assert result["total"] == 1
        assert result["descriptions"][0]["fiscal_year"] == "2026"

    def test_pagination(self, populated_db):
        result = get_pe_descriptions("0602120A", fy=None, section=None,
                                     limit=1, offset=0, conn=populated_db)
        assert result["total"] == 2
        assert len(result["descriptions"]) == 1

    def test_offset(self, populated_db):
        result = get_pe_descriptions("0602120A", fy=None, section=None,
                                     limit=1, offset=1, conn=populated_db)
        assert len(result["descriptions"]) == 1

    def test_unknown_pe_returns_empty(self, db):
        result = get_pe_descriptions("9999999X", fy=None, section=None,
                                     limit=20, offset=0, conn=db)
        assert result["total"] == 0

    def test_section_filter(self, populated_db):
        """Section header substring filter returns only matching rows."""
        # Insert a row with section_header
        populated_db.execute("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end,
                 section_header, description_text)
            VALUES ('0602120A', '2026', 'army/r2.pdf', 10, 11,
                    'Accomplishments', 'Prototype testing completed.')
        """)
        populated_db.commit()
        result = get_pe_descriptions("0602120A", fy=None, section="Accomplishment",
                                     limit=20, offset=0, conn=populated_db)
        assert result["total"] == 1
        assert result["descriptions"][0]["section_header"] == "Accomplishments"

    def test_available_sections(self, populated_db):
        """Response includes distinct section headers for UI filtering."""
        populated_db.execute("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end,
                 section_header, description_text)
            VALUES ('0602120A', '2026', 'army/r2.pdf', 10, 11,
                    'Acquisition Strategy', 'Strategy details.')
        """)
        populated_db.commit()
        result = get_pe_descriptions("0602120A", fy=None, section=None,
                                     limit=20, offset=0, conn=populated_db)
        assert "available_sections" in result
        assert "Acquisition Strategy" in result["available_sections"]


# ── get_pe_related tests ──────────────────────────────────────────────────────

class TestGetPeRelated:
    def test_returns_related(self, populated_db):
        result = get_pe_related("0602120A", min_confidence=0.0, conn=populated_db)
        assert result["related_count"] == 1
        assert result["related"][0]["referenced_pe"] == "0603000A"

    def test_link_type_present(self, populated_db):
        result = get_pe_related("0602120A", min_confidence=0.0, conn=populated_db)
        assert result["related"][0]["link_type"] == "explicit_pe_ref"

    def test_confidence_filter(self, populated_db):
        # 0.95 confidence row should pass
        result = get_pe_related("0602120A", min_confidence=0.9, conn=populated_db)
        assert result["related_count"] == 1

    def test_confidence_filter_excludes(self, populated_db):
        # Nothing above 1.0
        result = get_pe_related("0602120A", min_confidence=1.0, conn=populated_db)
        assert result["related_count"] == 0

    def test_no_related_returns_empty(self, populated_db):
        result = get_pe_related("0603000A", min_confidence=0.0, conn=populated_db)
        assert result["related_count"] == 0


# ── list_pes tests ────────────────────────────────────────────────────────────

class TestListPes:
    def test_returns_all(self, populated_db):
        result = list_pes(tag=None, q=None, service=None, budget_type=None, approp=None,
                          fy=None, limit=25, offset=0, conn=populated_db)
        assert result["total"] == 2

    def test_filter_by_service(self, populated_db):
        result = list_pes(tag=None, q=None, service="Army", budget_type=None, approp=None,
                          fy=None, limit=25, offset=0, conn=populated_db)
        assert result["total"] == 1
        assert result["items"][0]["pe_number"] == "0602120A"

    def test_filter_by_budget_type(self, populated_db):
        result = list_pes(tag=None, q=None, service=None, budget_type="rdte",
                          approp=None, fy=None, limit=25, offset=0, conn=populated_db)
        assert result["total"] == 2

    def test_filter_by_fy(self, populated_db):
        result = list_pes(tag=None, q=None, service=None, budget_type=None, approp=None,
                          fy="2025", limit=25, offset=0, conn=populated_db)
        # Only 0602120A has FY2025
        assert result["total"] == 1

    def test_filter_by_tag(self, populated_db):
        result = list_pes(tag=["radar"], q=None, service=None, budget_type=None, approp=None,
                          fy=None, limit=25, offset=0, conn=populated_db)
        assert result["total"] == 1
        assert result["items"][0]["pe_number"] == "0602120A"

    def test_multi_tag_and_logic(self, populated_db):
        # Both "army" and "radar" → 0602120A only
        result = list_pes(tag=["army", "radar"], q=None, service=None,
                          budget_type=None, approp=None, fy=None, limit=25,
                          offset=0, conn=populated_db)
        assert result["total"] == 1

    def test_topic_query(self, populated_db):
        result = list_pes(tag=None, q="radar", service=None, budget_type=None, approp=None,
                          fy=None, limit=25, offset=0, conn=populated_db)
        assert result["total"] == 1

    def test_items_include_tags(self, populated_db):
        result = list_pes(tag=None, q=None, service="Army", budget_type=None, approp=None,
                          fy=None, limit=25, offset=0, conn=populated_db)
        tags = result["items"][0]["tags"]
        assert isinstance(tags, list)
        assert len(tags) > 0

    def test_pagination(self, populated_db):
        result = list_pes(tag=None, q=None, service=None, budget_type=None, approp=None,
                          fy=None, limit=1, offset=0, conn=populated_db)
        assert result["total"] == 2
        assert len(result["items"]) == 1

    def test_fiscal_years_parsed_as_list(self, populated_db):
        result = list_pes(tag=None, q=None, service=None, budget_type=None, approp=None,
                          fy=None, limit=25, offset=0, conn=populated_db)
        for item in result["items"]:
            assert isinstance(item["fiscal_years"], list)

    def test_enrichment_status_indicators(self, populated_db):
        result = list_pes(tag=None, q=None, service=None, budget_type=None, approp=None,
                          fy=None, limit=25, offset=0, conn=populated_db)
        pe_items = {i["pe_number"]: i for i in result["items"]}
        # 0602120A has descriptions and lineage in the fixture
        assert pe_items["0602120A"]["has_descriptions"] is True
        assert pe_items["0602120A"]["has_related"] is True
        # 0603000A has neither
        assert pe_items["0603000A"]["has_descriptions"] is False
        assert pe_items["0603000A"]["has_related"] is False

    def test_funding_total_included(self, populated_db):
        result = list_pes(tag=None, q=None, service=None, budget_type=None, approp=None,
                          fy=None, limit=25, offset=0, conn=populated_db)
        pe_items = {i["pe_number"]: i for i in result["items"]}
        # 0602120A has 1400 + 1400 + 700 = 3500 in fy2026_request
        assert pe_items["0602120A"]["total_fy2026_request"] == 3500.0
        # 0603000A has 9000
        assert pe_items["0603000A"]["total_fy2026_request"] == 9000.0

    def test_filter_by_approp(self, populated_db):
        """Appropriation title substring filter restricts PE results."""
        result = list_pes(tag=None, q=None, service=None, budget_type=None,
                          approp="RDT&E", fy=None, limit=25,
                          offset=0, conn=populated_db)
        # Both PEs have RDTE appropriation title
        assert result["total"] == 2

    def test_filter_by_approp_no_match(self, populated_db):
        """Non-matching appropriation returns empty."""
        result = list_pes(tag=None, q=None, service=None, budget_type=None,
                          approp="Nonexistent Appropriation", fy=None,
                          limit=25, offset=0, conn=populated_db)
        assert result["total"] == 0


# ── list_tags tests ───────────────────────────────────────────────────────────

class TestListTags:
    def test_returns_all_tags(self, populated_db):
        result = list_tags(tag_source=None, conn=populated_db)
        tag_names = [t["tag"] for t in result["tags"]]
        assert "army" in tag_names
        assert "rdte" in tag_names
        assert "radar" in tag_names

    def test_filter_by_source(self, populated_db):
        result = list_tags(tag_source="keyword", conn=populated_db)
        for t in result["tags"]:
            assert t["tag_source"] == "keyword"
        assert result["tags"][0]["tag"] == "radar"

    def test_pe_count_correct(self, populated_db):
        result = list_tags(tag_source="structured", conn=populated_db)
        # "rdte" appears once (only 0602120A has it)
        rdte = next(t for t in result["tags"] if t["tag"] == "rdte")
        assert rdte["pe_count"] == 1

    def test_empty_db_returns_zero(self, db):
        result = list_tags(tag_source=None, conn=db)
        assert result["total"] == 0


# ── export_pe_table tests ─────────────────────────────────────────────────────

class TestExportPeTable:
    def test_returns_csv_response(self, populated_db):
        resp = export_pe_table("0602120A", conn=populated_db)
        assert resp.media_type == "text/csv"
        assert "attachment" in resp.headers["content-disposition"]
        assert "0602120A" in resp.headers["content-disposition"]

    def test_csv_has_header(self, populated_db):
        resp = export_pe_table("0602120A", conn=populated_db)
        content = resp.body.decode("utf-8-sig")
        assert "PE Number" in content
        assert "FY2024 Actual" in content

    def test_csv_has_data_rows(self, populated_db):
        resp = export_pe_table("0602120A", conn=populated_db)
        content = resp.body.decode("utf-8-sig")
        lines = [l for l in content.strip().splitlines() if l]
        # header + 3 data rows
        assert len(lines) == 4

    def test_pct_change_column_present(self, populated_db):
        resp = export_pe_table("0602120A", conn=populated_db)
        content = resp.body.decode("utf-8-sig")
        assert "% Change" in content

    def test_not_found_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            export_pe_table("9999999X", conn=db)
        assert exc_info.value.status_code == 404


# ── export_pe_pages tests ─────────────────────────────────────────────────────

class TestExportPePages:
    def test_returns_zip(self, populated_db):
        resp = export_pe_pages(pe=["0602120A"], fy=None, conn=populated_db)
        assert resp.media_type == "application/zip"
        assert "attachment" in resp.headers["content-disposition"]

    def test_zip_contains_files(self, populated_db):
        resp = export_pe_pages(pe=["0602120A"], fy=None, conn=populated_db)
        zf = zipfile.ZipFile(io.BytesIO(resp.body))
        names = zf.namelist()
        assert len(names) > 0
        assert any("0602120A" in n for n in names)

    def test_zip_file_contents(self, populated_db):
        resp = export_pe_pages(pe=["0602120A"], fy=None, conn=populated_db)
        zf = zipfile.ZipFile(io.BytesIO(resp.body))
        # At least one file should have non-empty text
        texts = [zf.read(n).decode() for n in zf.namelist()]
        assert any(len(t) > 0 for t in texts)

    def test_fy_filter_limits_pages(self, populated_db):
        # The description is only for 2026, so FY filter should still work
        resp = export_pe_pages(pe=["0602120A"], fy="2026", conn=populated_db)
        assert resp.media_type == "application/zip"

    def test_no_pages_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            export_pe_pages(pe=["9999999X"], fy=None, conn=db)
        assert exc_info.value.status_code == 404

    def test_too_many_pes_raises_400(self, db):
        with pytest.raises(HTTPException) as exc_info:
            export_pe_pages(pe=[f"{i:07d}A" for i in range(51)], fy=None, conn=db)
        assert exc_info.value.status_code == 400

    def test_empty_pe_list_raises_400(self, db):
        with pytest.raises(HTTPException) as exc_info:
            export_pe_pages(pe=[], fy=None, conn=db)
        assert exc_info.value.status_code == 400
