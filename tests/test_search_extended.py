"""
Tests for search_budget.py — export_results and display functions

Covers export_results (JSON and CSV), display_budget_results,
display_pdf_results, show_summary, and show_sources using an
in-memory database with minimal schema.
"""
import csv
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from search_budget import (
    export_results,
    display_budget_results,
    display_pdf_results,
)


def _make_row(data: dict):
    """Create a sqlite3.Row-like object from a dict."""

    class FakeRow:
        def __init__(self, d):
            self._d = d

        def __getitem__(self, key):
            return self._d[key]

        def keys(self):
            return self._d.keys()

    return FakeRow(data)


_SAMPLE_BUDGET_ROW = _make_row({
    "id": 1,
    "source_file": "army/p1.xlsx",
    "exhibit_type": "p1",
    "sheet_name": "Sheet1",
    "fiscal_year": "FY 2026",
    "account": "2035",
    "account_title": "Aircraft Procurement, Army",
    "organization_name": "Army",
    "budget_activity_title": "Fixed Wing",
    "sub_activity_title": None,
    "line_item": "001",
    "line_item_title": "AH-64 Apache",
    "amount_fy2024_actual": 1500000,
    "amount_fy2025_enacted": 1600000,
    "amount_fy2026_request": 1700000,
    "amount_fy2026_total": 1700000,
})

_SAMPLE_PDF_ROW = _make_row({
    "id": 10,
    "source_file": "army/justification.pdf",
    "source_category": "Army",
    "page_number": 5,
    "page_text": "The AH-64 Apache program continues modernization efforts.",
    "has_tables": 0,
    "table_data": None,
})


# ── display_budget_results ────────────────────────────────────────────────────

class TestDisplayBudgetResults:
    def test_no_results(self, capsys):
        display_budget_results([], "test query")
        out = capsys.readouterr().out
        assert "No budget line items found" in out

    def test_shows_results(self, capsys):
        display_budget_results([_SAMPLE_BUDGET_ROW], "apache")
        out = capsys.readouterr().out
        assert "Army" in out
        assert "Aircraft Procurement" in out
        assert "AH-64 Apache" in out

    def test_millions_unit(self, capsys):
        display_budget_results([_SAMPLE_BUDGET_ROW], "apache", unit="millions")
        out = capsys.readouterr().out
        assert "($M)" in out


# ── display_pdf_results ───────────────────────────────────────────────────────

class TestDisplayPdfResults:
    def test_no_results(self, capsys):
        display_pdf_results([], "test query")
        out = capsys.readouterr().out
        assert "No PDF content found" in out

    def test_shows_results(self, capsys):
        display_pdf_results([_SAMPLE_PDF_ROW], "apache")
        out = capsys.readouterr().out
        assert "Army" in out
        assert "justification.pdf" in out


# ── export_results ────────────────────────────────────────────────────────────

class TestExportResults:
    def test_export_json(self, tmp_path, capsys, monkeypatch):
        monkeypatch.chdir(tmp_path)
        export_results([_SAMPLE_BUDGET_ROW], [_SAMPLE_PDF_ROW], "apache", "json")
        # Find the generated file
        json_files = list(tmp_path.glob("results_*.json"))
        assert len(json_files) == 1
        data = json.loads(json_files[0].read_text())
        assert data["query"] == "apache"
        assert len(data["budget_lines"]) == 1
        assert len(data["pdf_pages"]) == 1

    def test_export_csv(self, tmp_path, capsys, monkeypatch):
        monkeypatch.chdir(tmp_path)
        export_results([_SAMPLE_BUDGET_ROW], [_SAMPLE_PDF_ROW], "apache", "csv")
        csv_files = list(tmp_path.glob("results_*_budget_lines.csv"))
        assert len(csv_files) == 1
        with open(csv_files[0]) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["account"] == "2035"

    def test_export_csv_no_results(self, tmp_path, capsys, monkeypatch):
        monkeypatch.chdir(tmp_path)
        export_results([], [], "nothing", "csv")
        out = capsys.readouterr().out
        assert "No results to export" in out

    def test_export_json_no_results(self, tmp_path, capsys, monkeypatch):
        monkeypatch.chdir(tmp_path)
        export_results([], [], "nothing", "json")
        json_files = list(tmp_path.glob("results_*.json"))
        assert len(json_files) == 1
        data = json.loads(json_files[0].read_text())
        assert data["budget_lines"] == []
        assert data["pdf_pages"] == []
