"""
Unit tests for pipeline/staging.py Phase 1 functions.

Tests the Parquet staging layer: file staging, change detection,
sidecar metadata, and parallel orchestration.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pipeline.staging import (
    STAGING_VERSION,
    EXCEL_FIXED_COLUMNS,
    EXCEL_TAIL_COLUMNS,
    PDF_COLUMNS,
    needs_restaging,
    _parquet_path,
    _sidecar_path,
    _write_sidecar,
    _write_pdf_sidecar,
    _write_staging_metadata,
    discover_fy_columns,
)


# ── Path computation ─────────────────────────────────────────────────────────

class TestParquetPath:
    """Tests for _parquet_path and _sidecar_path."""

    def test_parquet_path_preserves_fy_structure(self, tmp_path):
        source = tmp_path / "docs" / "FY2026" / "Comptroller" / "p1_display.xlsx"
        source.parent.mkdir(parents=True)
        source.touch()
        staging = tmp_path / "staging"

        result = _parquet_path(source, staging, "excel")
        assert result == staging / "excel" / "FY2026" / "Comptroller" / "p1_display.parquet"

    def test_sidecar_path_matches_parquet(self, tmp_path):
        source = tmp_path / "docs" / "FY2026" / "Army" / "p1_army.xlsx"
        source.parent.mkdir(parents=True)
        source.touch()
        staging = tmp_path / "staging"

        parq = _parquet_path(source, staging, "excel")
        meta = _sidecar_path(source, staging, "excel")
        assert meta == parq.with_suffix(".meta.json")

    def test_parquet_path_no_fy_dir(self, tmp_path):
        """File not under FY* directory uses filename only."""
        source = tmp_path / "random" / "budget.xlsx"
        source.parent.mkdir(parents=True)
        source.touch()
        staging = tmp_path / "staging"

        result = _parquet_path(source, staging, "excel")
        assert result == staging / "excel" / "budget.parquet"

    def test_pdf_parquet_path(self, tmp_path):
        source = tmp_path / "docs" / "FY2025" / "Navy" / "r2_detail.pdf"
        source.parent.mkdir(parents=True)
        source.touch()
        staging = tmp_path / "staging"

        result = _parquet_path(source, staging, "pdf")
        assert result == staging / "pdf" / "FY2025" / "Navy" / "r2_detail.parquet"


# ── Change detection ─────────────────────────────────────────────────────────

class TestNeedsRestaging:
    """Tests for needs_restaging()."""

    def test_new_file_needs_staging(self, tmp_path):
        source = tmp_path / "docs" / "FY2026" / "test.xlsx"
        source.parent.mkdir(parents=True)
        source.write_text("data")
        staging = tmp_path / "staging"

        assert needs_restaging(source, staging, "excel") is True

    def test_unchanged_file_skipped(self, tmp_path):
        source = tmp_path / "docs" / "FY2026" / "test.xlsx"
        source.parent.mkdir(parents=True)
        source.write_text("data")
        staging = tmp_path / "staging"

        # Write matching sidecar
        meta_path = _sidecar_path(source, staging, "excel")
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        stat = source.stat()
        meta = {
            "staging_version": STAGING_VERSION,
            "source_file_size": stat.st_size,
            "source_file_mtime": stat.st_mtime,
            "error": None,
        }
        meta_path.write_text(json.dumps(meta))

        assert needs_restaging(source, staging, "excel") is False

    def test_modified_file_needs_staging(self, tmp_path):
        source = tmp_path / "docs" / "FY2026" / "test.xlsx"
        source.parent.mkdir(parents=True)
        source.write_text("data")
        staging = tmp_path / "staging"

        # Write sidecar with wrong size
        meta_path = _sidecar_path(source, staging, "excel")
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta = {
            "staging_version": STAGING_VERSION,
            "source_file_size": 999,  # wrong
            "source_file_mtime": source.stat().st_mtime,
            "error": None,
        }
        meta_path.write_text(json.dumps(meta))

        assert needs_restaging(source, staging, "excel") is True

    def test_errored_file_needs_restaging(self, tmp_path):
        source = tmp_path / "docs" / "FY2026" / "test.xlsx"
        source.parent.mkdir(parents=True)
        source.write_text("data")
        staging = tmp_path / "staging"

        meta_path = _sidecar_path(source, staging, "excel")
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        stat = source.stat()
        meta = {
            "staging_version": STAGING_VERSION,
            "source_file_size": stat.st_size,
            "source_file_mtime": stat.st_mtime,
            "error": "PreviousParseError",
        }
        meta_path.write_text(json.dumps(meta))

        assert needs_restaging(source, staging, "excel") is True

    def test_old_version_needs_restaging(self, tmp_path):
        source = tmp_path / "docs" / "FY2026" / "test.xlsx"
        source.parent.mkdir(parents=True)
        source.write_text("data")
        staging = tmp_path / "staging"

        meta_path = _sidecar_path(source, staging, "excel")
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        stat = source.stat()
        meta = {
            "staging_version": 0,  # old version
            "source_file_size": stat.st_size,
            "source_file_mtime": stat.st_mtime,
            "error": None,
        }
        meta_path.write_text(json.dumps(meta))

        assert needs_restaging(source, staging, "excel") is True

    def test_corrupt_sidecar_needs_restaging(self, tmp_path):
        source = tmp_path / "docs" / "FY2026" / "test.xlsx"
        source.parent.mkdir(parents=True)
        source.write_text("data")
        staging = tmp_path / "staging"

        meta_path = _sidecar_path(source, staging, "excel")
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text("INVALID JSON{{{")

        assert needs_restaging(source, staging, "excel") is True


# ── Sidecar writing ──────────────────────────────────────────────────────────

class TestSidecarWriting:
    """Tests for sidecar metadata writing."""

    def test_write_excel_sidecar(self, tmp_path):
        source = tmp_path / "test.xlsx"
        source.write_text("data")
        meta_path = tmp_path / "test.meta.json"

        _write_sidecar(meta_path, source, "FY2026/test.xlsx", "p1",
                        ["amount_fy2025_enacted", "amount_fy2026_request"],
                        100, None)

        meta = json.loads(meta_path.read_text())
        assert meta["staging_version"] == STAGING_VERSION
        assert meta["source_file"] == "FY2026/test.xlsx"
        assert meta["exhibit_type"] == "p1"
        assert meta["fy_columns"] == ["amount_fy2025_enacted", "amount_fy2026_request"]
        assert meta["row_count"] == 100
        assert meta["error"] is None
        assert "parse_timestamp" in meta
        assert meta["parser_version"] == "pipeline.staging:v1"

    def test_write_excel_sidecar_with_error(self, tmp_path):
        source = tmp_path / "bad.xlsx"
        source.write_text("bad data")
        meta_path = tmp_path / "bad.meta.json"

        _write_sidecar(meta_path, source, "FY2026/bad.xlsx", "p1",
                        [], 0, "Failed to open workbook")

        meta = json.loads(meta_path.read_text())
        assert meta["error"] == "Failed to open workbook"
        assert meta["row_count"] == 0

    def test_write_pdf_sidecar(self, tmp_path):
        source = tmp_path / "test.pdf"
        source.write_text("pdf data")
        meta_path = tmp_path / "test.meta.json"

        pe_mentions = [("0602702E", 1), ("0603000A", 3)]
        issues = [("file.pdf", 5, "timeout", "Table extraction timed out")]

        _write_pdf_sidecar(meta_path, source, "FY2026/test.pdf", "rdte",
                            10, 15, pe_mentions, issues, None)

        meta = json.loads(meta_path.read_text())
        assert meta["staging_version"] == STAGING_VERSION
        assert meta["source_category"] == "rdte"
        assert meta["page_count"] == 10
        assert meta["total_pages"] == 15
        assert len(meta["pe_mentions"]) == 2
        assert meta["pe_mentions"][0]["pe_number"] == "0602702E"
        assert len(meta["extraction_issues"]) == 1
        assert meta["error"] is None


# ── Staging metadata ─────────────────────────────────────────────────────────

class TestStagingMetadata:
    """Tests for top-level staging _metadata.json."""

    def test_write_staging_metadata(self, tmp_path):
        _write_staging_metadata(
            tmp_path,
            ["amount_fy2025_enacted", "amount_fy2026_request"],
            100, 80, 15, 5,
        )

        meta_path = tmp_path / "_metadata.json"
        assert meta_path.exists()
        meta = json.loads(meta_path.read_text())
        assert meta["staging_version"] == STAGING_VERSION
        assert meta["total_files"] == 100
        assert meta["staged_count"] == 80
        assert meta["skipped_count"] == 15
        assert meta["error_count"] == 5
        assert len(meta["excel_fy_columns"]) == 2


# ── Discover FY columns ─────────────────────────────────────────────────────

class TestDiscoverFyColumns:
    """Tests for discover_fy_columns()."""

    def test_discovers_from_sidecars(self, tmp_path):
        staging = tmp_path / "staging"
        excel_dir = staging / "excel" / "FY2026" / "Army"
        excel_dir.mkdir(parents=True)

        # Write two sidecars with different FY columns
        (excel_dir / "p1_army.meta.json").write_text(json.dumps({
            "fy_columns": ["amount_fy2025_enacted", "amount_fy2026_request"]
        }))
        (excel_dir / "o1_army.meta.json").write_text(json.dumps({
            "fy_columns": ["amount_fy2024_actual", "amount_fy2026_request"]
        }))

        result = discover_fy_columns(staging)
        assert result == [
            "amount_fy2024_actual",
            "amount_fy2025_enacted",
            "amount_fy2026_request",
        ]

    def test_empty_staging_returns_empty(self, tmp_path):
        result = discover_fy_columns(tmp_path / "nonexistent")
        assert result == []

    def test_corrupt_sidecar_skipped(self, tmp_path):
        staging = tmp_path / "staging"
        excel_dir = staging / "excel" / "FY2026"
        excel_dir.mkdir(parents=True)

        (excel_dir / "corrupt.meta.json").write_text("NOT JSON{{{")
        (excel_dir / "good.meta.json").write_text(json.dumps({
            "fy_columns": ["amount_fy2026_request"]
        }))

        result = discover_fy_columns(staging)
        assert result == ["amount_fy2026_request"]


# ── Column constants ─────────────────────────────────────────────────────────

class TestColumnConstants:
    """Verify column constants are consistent."""

    def test_excel_fixed_columns_count(self):
        assert len(EXCEL_FIXED_COLUMNS) == 18

    def test_excel_tail_columns_count(self):
        assert len(EXCEL_TAIL_COLUMNS) == 8

    def test_pdf_columns_count(self):
        assert len(PDF_COLUMNS) == 8

    def test_excel_fixed_starts_with_source_file(self):
        assert EXCEL_FIXED_COLUMNS[0] == "source_file"

    def test_excel_tail_ends_with_amount_type(self):
        assert EXCEL_TAIL_COLUMNS[-1] == "amount_type"

    def test_pdf_columns_starts_with_source_file(self):
        assert PDF_COLUMNS[0] == "source_file"
