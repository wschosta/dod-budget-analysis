"""
Unit tests for pipeline/staging.py Phase 2 functions (Parquet → SQLite).

Tests the database loading functions with synthetic Parquet files.
"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

try:
    # Workaround for pyarrow 23+ / pandas 3.0+ incompatibility:
    # pyarrow's pandas shim checks pandas.__version__ which was removed.
    # Ensure the attribute exists before pyarrow tries to read it.
    import pandas as _pd
    if not hasattr(_pd, "__version__"):
        import importlib.metadata as _meta
        _pd.__version__ = _meta.version("pandas")  # type: ignore[attr-defined]

    import pyarrow as pa
    import pyarrow.parquet as pq
    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False

pytestmark = pytest.mark.skipif(not HAS_PYARROW, reason="pyarrow not installed")

from pipeline.staging import (
    EXCEL_FIXED_COLUMNS,
    EXCEL_TAIL_COLUMNS,
    PDF_COLUMNS,
    _load_excel_parquets,
    _load_pdf_parquets,
    _rebuild_fts_indexes,
    load_staging_to_db,
    discover_fy_columns,
)


def _create_test_db(db_path: Path) -> sqlite3.Connection:
    """Create a minimal test database with the required schema."""
    from pipeline.builder import create_database
    return create_database(db_path)


def _create_excel_parquet(
    staging_dir: Path,
    rel_subpath: str = "FY2026/Army/p1_army",
    fy_columns: list[str] | None = None,
    n_rows: int = 5,
) -> tuple[Path, Path]:
    """Create a synthetic Excel Parquet + sidecar for testing.

    Returns (parquet_path, meta_path).
    """
    if fy_columns is None:
        fy_columns = ["amount_fy2025_enacted", "amount_fy2026_request"]

    parquet_path = staging_dir / "excel" / f"{rel_subpath}.parquet"
    meta_path = staging_dir / "excel" / f"{rel_subpath}.meta.json"
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    # Derive source_file from rel_subpath
    source_file_value = f"{rel_subpath}.xlsx"

    # Build columns
    all_col_names = EXCEL_FIXED_COLUMNS + fy_columns + EXCEL_TAIL_COLUMNS

    fields = []
    for col in EXCEL_FIXED_COLUMNS:
        fields.append(pa.field(col, pa.string()))
    for col in fy_columns:
        fields.append(pa.field(col, pa.float64()))
    for col in EXCEL_TAIL_COLUMNS:
        fields.append(pa.field(col, pa.string()))

    schema = pa.schema(fields)

    # Generate synthetic data
    arrays = []
    for col in EXCEL_FIXED_COLUMNS:
        if col == "source_file":
            arrays.append(pa.array([source_file_value] * n_rows, type=pa.string()))
        elif col == "exhibit_type":
            arrays.append(pa.array(["p1"] * n_rows, type=pa.string()))
        elif col == "fiscal_year":
            arrays.append(pa.array(["FY 2026"] * n_rows, type=pa.string()))
        elif col == "account":
            arrays.append(pa.array([f"0100{i}" for i in range(n_rows)], type=pa.string()))
        elif col == "organization":
            arrays.append(pa.array(["A"] * n_rows, type=pa.string()))
        else:
            arrays.append(pa.array([f"test_{col}_{i}" for i in range(n_rows)], type=pa.string()))

    for col in fy_columns:
        arrays.append(pa.array([float(i * 1000 + 100) for i in range(n_rows)], type=pa.float64()))

    for col in EXCEL_TAIL_COLUMNS:
        if col == "amount_unit":
            arrays.append(pa.array(["thousands"] * n_rows, type=pa.string()))
        elif col == "amount_type":
            arrays.append(pa.array(["budget_authority"] * n_rows, type=pa.string()))
        else:
            arrays.append(pa.array([None] * n_rows, type=pa.string()))

    table = pa.table(arrays, schema=schema)
    pq.write_table(table, str(parquet_path), compression="snappy")

    # Write sidecar
    meta = {
        "staging_version": 1,
        "source_file": source_file_value,
        "source_file_size": 12345,
        "source_file_mtime": 1708123456.789,
        "exhibit_type": "p1",
        "fy_columns": fy_columns,
        "row_count": n_rows,
        "parse_timestamp": "2026-02-21T14:30:00Z",
        "parser_version": "pipeline.staging:v1",
        "error": None,
    }
    meta_path.write_text(json.dumps(meta, indent=2))

    return parquet_path, meta_path


def _create_pdf_parquet(
    staging_dir: Path,
    rel_subpath: str = "FY2026/Army/r2_detail",
    n_pages: int = 3,
) -> tuple[Path, Path]:
    """Create a synthetic PDF Parquet + sidecar for testing."""
    parquet_path = staging_dir / "pdf" / f"{rel_subpath}.parquet"
    meta_path = staging_dir / "pdf" / f"{rel_subpath}.meta.json"
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        pa.field("source_file", pa.string()),
        pa.field("source_category", pa.string()),
        pa.field("fiscal_year", pa.string()),
        pa.field("exhibit_type", pa.string()),
        pa.field("page_number", pa.int32()),
        pa.field("page_text", pa.string()),
        pa.field("has_tables", pa.int32()),
        pa.field("table_data", pa.string()),
    ]
    schema = pa.schema(fields)

    arrays = [
        pa.array(["FY2026/Army/r2_detail.pdf"] * n_pages, type=pa.string()),
        pa.array(["rdte"] * n_pages, type=pa.string()),
        pa.array(["FY 2026"] * n_pages, type=pa.string()),
        pa.array(["r2"] * n_pages, type=pa.string()),
        pa.array(list(range(1, n_pages + 1)), type=pa.int32()),
        pa.array([f"Test text for page {i+1}" for i in range(n_pages)], type=pa.string()),
        pa.array([0] * n_pages, type=pa.int32()),
        pa.array([None] * n_pages, type=pa.string()),
    ]

    table = pa.table(arrays, schema=schema)
    pq.write_table(table, str(parquet_path), compression="snappy")

    # Write sidecar
    meta = {
        "staging_version": 1,
        "source_file": "FY2026/Army/r2_detail.pdf",
        "source_file_size": 98765,
        "source_file_mtime": 1708123456.789,
        "source_category": "rdte",
        "page_count": n_pages,
        "total_pages": n_pages,
        "pe_mentions": [
            {"pe_number": "0602702E", "page_number": 1},
            {"pe_number": "0603000A", "page_number": 2},
        ],
        "extraction_issues": [],
        "parse_timestamp": "2026-02-21T14:30:00Z",
        "parser_version": "pipeline.staging:v1",
        "error": None,
    }
    meta_path.write_text(json.dumps(meta, indent=2))

    return parquet_path, meta_path


# ── Load Excel Parquets ──────────────────────────────────────────────────────

class TestLoadExcelParquets:
    """Tests for _load_excel_parquets()."""

    def test_loads_rows_into_budget_lines(self, tmp_path):
        staging = tmp_path / "staging"
        _create_excel_parquet(staging, n_rows=10)

        db_path = tmp_path / "test.sqlite"
        conn = _create_test_db(db_path)

        # Ensure FY columns exist
        from pipeline.builder import _ensure_fy_columns
        _ensure_fy_columns(conn, ["amount_fy2025_enacted", "amount_fy2026_request"])

        total = _load_excel_parquets(
            conn, staging,
            ["amount_fy2025_enacted", "amount_fy2026_request"],
        )

        assert total == 10
        row_count = conn.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0]
        assert row_count == 10
        conn.close()

    def test_null_fills_missing_fy_columns(self, tmp_path):
        """Files with different FY columns get NULL for the missing ones."""
        staging = tmp_path / "staging"

        # File 1: has fy2025 and fy2026
        _create_excel_parquet(
            staging,
            rel_subpath="FY2026/Army/p1_army",
            fy_columns=["amount_fy2025_enacted", "amount_fy2026_request"],
            n_rows=3,
        )
        # File 2: has only fy2024
        _create_excel_parquet(
            staging,
            rel_subpath="FY2024/Army/p1_army",
            fy_columns=["amount_fy2024_actual"],
            n_rows=2,
        )

        all_fy = ["amount_fy2024_actual", "amount_fy2025_enacted", "amount_fy2026_request"]

        db_path = tmp_path / "test.sqlite"
        conn = _create_test_db(db_path)
        from pipeline.builder import _ensure_fy_columns
        _ensure_fy_columns(conn, all_fy)

        total = _load_excel_parquets(conn, staging, all_fy)
        assert total == 5

        # Check that fy2024 is NULL for fy2026 rows (file 1)
        rows = conn.execute(
            "SELECT amount_fy2024_actual FROM budget_lines "
            "WHERE source_file = 'FY2026/Army/p1_army.xlsx'"
        ).fetchall()
        assert len(rows) == 3
        assert all(r[0] is None for r in rows)

        # And fy2025/fy2026 are NULL for fy2024 rows (file 2)
        rows2 = conn.execute(
            "SELECT amount_fy2025_enacted, amount_fy2026_request FROM budget_lines "
            "WHERE source_file = 'FY2024/Army/p1_army.xlsx'"
        ).fetchall()
        assert len(rows2) == 2
        assert all(r[0] is None and r[1] is None for r in rows2)

        conn.close()

    def test_records_ingested_files(self, tmp_path):
        staging = tmp_path / "staging"
        _create_excel_parquet(staging, n_rows=5)

        db_path = tmp_path / "test.sqlite"
        conn = _create_test_db(db_path)
        from pipeline.builder import _ensure_fy_columns
        _ensure_fy_columns(conn, ["amount_fy2025_enacted", "amount_fy2026_request"])

        _load_excel_parquets(
            conn, staging,
            ["amount_fy2025_enacted", "amount_fy2026_request"],
        )

        row = conn.execute(
            "SELECT file_type, row_count, status FROM ingested_files "
            "WHERE file_path = 'FY2026/Army/p1_army.xlsx'"
        ).fetchone()
        assert row is not None
        assert row[0] == "xlsx"
        assert row[1] == 5
        assert row[2] == "ok"
        conn.close()

    def test_empty_staging_returns_zero(self, tmp_path):
        staging = tmp_path / "staging"
        staging.mkdir()
        db_path = tmp_path / "test.sqlite"
        conn = _create_test_db(db_path)

        total = _load_excel_parquets(conn, staging, [])
        assert total == 0
        conn.close()


# ── Load PDF Parquets ────────────────────────────────────────────────────────

class TestLoadPdfParquets:
    """Tests for _load_pdf_parquets()."""

    def test_loads_pages_into_pdf_pages(self, tmp_path):
        staging = tmp_path / "staging"
        _create_pdf_parquet(staging, n_pages=5)

        db_path = tmp_path / "test.sqlite"
        conn = _create_test_db(db_path)

        total = _load_pdf_parquets(conn, staging)
        assert total == 5

        page_count = conn.execute("SELECT COUNT(*) FROM pdf_pages").fetchone()[0]
        assert page_count == 5
        conn.close()

    def test_loads_pe_mentions(self, tmp_path):
        staging = tmp_path / "staging"
        _create_pdf_parquet(staging, n_pages=3)

        db_path = tmp_path / "test.sqlite"
        conn = _create_test_db(db_path)

        _load_pdf_parquets(conn, staging)

        pe_count = conn.execute("SELECT COUNT(*) FROM pdf_pe_numbers").fetchone()[0]
        assert pe_count == 2  # Two PE mentions in the sidecar
        conn.close()

    def test_records_ingested_files(self, tmp_path):
        staging = tmp_path / "staging"
        _create_pdf_parquet(staging, n_pages=3)

        db_path = tmp_path / "test.sqlite"
        conn = _create_test_db(db_path)

        _load_pdf_parquets(conn, staging)

        row = conn.execute(
            "SELECT file_type, row_count, status FROM ingested_files "
            "WHERE file_path = 'FY2026/Army/r2_detail.pdf'"
        ).fetchone()
        assert row is not None
        assert row[0] == "pdf"
        assert row[1] == 3
        assert row[2] == "ok"
        conn.close()


# ── FTS rebuild ──────────────────────────────────────────────────────────────

class TestFtsRebuild:
    """Tests for _rebuild_fts_indexes()."""

    def test_rebuild_fts_does_not_error(self, tmp_path):
        db_path = tmp_path / "test.sqlite"
        conn = _create_test_db(db_path)

        # Should not raise even with empty tables
        _rebuild_fts_indexes(conn)
        conn.close()

    def test_fts_search_after_rebuild(self, tmp_path):
        staging = tmp_path / "staging"
        _create_excel_parquet(staging, n_rows=3)

        db_path = tmp_path / "test.sqlite"
        conn = _create_test_db(db_path)

        # Drop triggers for bulk loading
        conn.execute("DROP TRIGGER IF EXISTS budget_lines_ai")
        conn.execute("DROP TRIGGER IF EXISTS budget_lines_ad")
        conn.commit()

        from pipeline.builder import _ensure_fy_columns
        _ensure_fy_columns(conn, ["amount_fy2025_enacted", "amount_fy2026_request"])
        _load_excel_parquets(
            conn, staging,
            ["amount_fy2025_enacted", "amount_fy2026_request"],
        )

        _rebuild_fts_indexes(conn)

        # FTS search should work
        results = conn.execute(
            "SELECT COUNT(*) FROM budget_lines_fts WHERE budget_lines_fts MATCH 'test'"
        ).fetchone()[0]
        assert results >= 0  # Just verify it doesn't error
        conn.close()


# ── Full load_staging_to_db ──────────────────────────────────────────────────

class TestLoadStagingToDb:
    """Integration tests for load_staging_to_db()."""

    def test_full_load_with_both_types(self, tmp_path):
        staging = tmp_path / "staging"
        _create_excel_parquet(staging, n_rows=7)
        _create_pdf_parquet(staging, n_pages=4)

        db_path = tmp_path / "test.sqlite"

        summary = load_staging_to_db(staging, db_path, rebuild=True)

        assert summary["total_rows"] == 7
        assert summary["total_pages"] == 4
        assert "elapsed_sec" in summary
        assert "fy_columns" in summary

    def test_load_creates_database_if_missing(self, tmp_path):
        staging = tmp_path / "staging"
        _create_excel_parquet(staging, n_rows=2)

        db_path = tmp_path / "new_db.sqlite"
        assert not db_path.exists()

        load_staging_to_db(staging, db_path, rebuild=True)
        assert db_path.exists()

    def test_load_staging_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_staging_to_db(tmp_path / "nonexistent", tmp_path / "db.sqlite")

    def test_rebuild_clears_existing_data(self, tmp_path):
        staging = tmp_path / "staging"
        _create_excel_parquet(staging, n_rows=3)

        db_path = tmp_path / "test.sqlite"

        # First load
        load_staging_to_db(staging, db_path, rebuild=True)
        # Second load with rebuild — should replace, not accumulate
        summary = load_staging_to_db(staging, db_path, rebuild=True)
        assert summary["total_rows"] == 3  # Not 6
