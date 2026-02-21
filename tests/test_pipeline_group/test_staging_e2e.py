"""
End-to-end integration tests for the Parquet staging layer.

Validates that data integrity is preserved across the full
parse → Parquet → SQLite roundtrip, including FTS search,
dynamic FY columns, PE mentions, and ingested_files tracking.
"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

try:
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
    load_staging_to_db,
    discover_fy_columns,
)


# ── Synthetic data generators ─────────────────────────────────────────────────


def _create_excel_staging(
    staging_dir: Path,
    files: list[dict],
) -> None:
    """Create multiple synthetic Excel Parquet + sidecar files.

    Each entry in `files` should have:
        rel_subpath, fy_columns, rows (list of dicts keyed by column name)
    """
    for spec in files:
        rel_subpath = spec["rel_subpath"]
        fy_columns = spec["fy_columns"]
        rows = spec["rows"]
        n_rows = len(rows)
        exhibit_type = spec.get("exhibit_type", "p1")

        parquet_path = staging_dir / "excel" / f"{rel_subpath}.parquet"
        meta_path = staging_dir / "excel" / f"{rel_subpath}.meta.json"
        parquet_path.parent.mkdir(parents=True, exist_ok=True)

        source_file_value = f"{rel_subpath}.xlsx"

        fields = []
        for col in EXCEL_FIXED_COLUMNS:
            fields.append(pa.field(col, pa.string()))
        for col in fy_columns:
            fields.append(pa.field(col, pa.float64()))
        for col in EXCEL_TAIL_COLUMNS:
            fields.append(pa.field(col, pa.string()))

        schema = pa.schema(fields)

        arrays = []
        for col in EXCEL_FIXED_COLUMNS:
            col_data = [r.get(col) for r in rows]
            if col == "source_file":
                col_data = [source_file_value] * n_rows
            elif col == "exhibit_type":
                col_data = [exhibit_type] * n_rows
            arrays.append(pa.array(col_data, type=pa.string()))

        for col in fy_columns:
            col_data = [r.get(col) for r in rows]
            arrays.append(pa.array(col_data, type=pa.float64()))

        for col in EXCEL_TAIL_COLUMNS:
            col_data = [r.get(col) for r in rows]
            arrays.append(pa.array(col_data, type=pa.string()))

        table = pa.table(arrays, schema=schema)
        pq.write_table(table, str(parquet_path), compression="snappy")

        meta = {
            "staging_version": 1,
            "source_file": source_file_value,
            "source_file_size": 12345,
            "source_file_mtime": 1708123456.789,
            "exhibit_type": exhibit_type,
            "fy_columns": fy_columns,
            "row_count": n_rows,
            "parse_timestamp": "2026-02-21T14:30:00Z",
            "parser_version": "pipeline.staging:v1",
            "error": None,
        }
        meta_path.write_text(json.dumps(meta, indent=2))


def _create_pdf_staging(
    staging_dir: Path,
    files: list[dict],
) -> None:
    """Create multiple synthetic PDF Parquet + sidecar files.

    Each entry in `files` should have:
        rel_subpath, pages (list of dicts with page_text etc.),
        pe_mentions (list of dicts with pe_number, page_number)
    """
    for spec in files:
        rel_subpath = spec["rel_subpath"]
        pages = spec["pages"]
        pe_mentions = spec.get("pe_mentions", [])
        n_pages = len(pages)
        source_file = f"{rel_subpath}.pdf"

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
            pa.array([source_file] * n_pages, type=pa.string()),
            pa.array([p.get("category", "rdte") for p in pages], type=pa.string()),
            pa.array([p.get("fiscal_year", "FY 2026") for p in pages], type=pa.string()),
            pa.array([p.get("exhibit_type", "r2") for p in pages], type=pa.string()),
            pa.array([p.get("page_number", i + 1) for i, p in enumerate(pages)], type=pa.int32()),
            pa.array([p["page_text"] for p in pages], type=pa.string()),
            pa.array([p.get("has_tables", 0) for p in pages], type=pa.int32()),
            pa.array([p.get("table_data") for p in pages], type=pa.string()),
        ]

        table = pa.table(arrays, schema=schema)
        pq.write_table(table, str(parquet_path), compression="snappy")

        meta = {
            "staging_version": 1,
            "source_file": source_file,
            "source_file_size": 98765,
            "source_file_mtime": 1708123456.789,
            "source_category": pages[0].get("category", "rdte") if pages else None,
            "page_count": n_pages,
            "total_pages": n_pages,
            "pe_mentions": pe_mentions,
            "extraction_issues": [],
            "parse_timestamp": "2026-02-21T14:30:00Z",
            "parser_version": "pipeline.staging:v1",
            "error": None,
        }
        meta_path.write_text(json.dumps(meta, indent=2))


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def realistic_staging(tmp_path):
    """Create a staging directory with realistic multi-source, multi-FY data."""
    staging = tmp_path / "staging"

    # ── Excel: Army P-1 for FY2025 and FY2026 ──
    army_rows_2026 = [
        {
            "fiscal_year": "FY 2026", "account": "2035",
            "account_title": "Other Procurement, Army",
            "organization": "A", "organization_name": "Army",
            "budget_activity": "01", "budget_activity_title": "Tactical Vehicles",
            "sub_activity": "01", "sub_activity_title": "Medium Tactical Vehicles",
            "line_item": "001", "line_item_title": "Family of Medium Tactical Vehicles",
            "classification": "UNCLASSIFIED",
            "cost_type": None, "cost_type_title": None,
            "add_non_add": "add", "sheet_name": "P-1",
            "amount_fy2025_enacted": 450000.0,
            "amount_fy2026_request": 525000.0,
            "pe_number": "0203750A", "amount_unit": "thousands",
            "amount_type": "budget_authority",
        },
        {
            "fiscal_year": "FY 2026", "account": "2035",
            "account_title": "Other Procurement, Army",
            "organization": "A", "organization_name": "Army",
            "budget_activity": "02", "budget_activity_title": "Communications",
            "sub_activity": "01", "sub_activity_title": "Tactical Radios",
            "line_item": "002", "line_item_title": "Joint Tactical Radio System",
            "classification": "UNCLASSIFIED",
            "cost_type": None, "cost_type_title": None,
            "add_non_add": "add", "sheet_name": "P-1",
            "amount_fy2025_enacted": 300000.0,
            "amount_fy2026_request": 350000.0,
            "pe_number": "0305210A", "amount_unit": "thousands",
            "amount_type": "budget_authority",
        },
    ]

    navy_rows_2025 = [
        {
            "fiscal_year": "FY 2025", "account": "1506",
            "account_title": "Aircraft Procurement, Navy",
            "organization": "N", "organization_name": "Navy",
            "budget_activity": "01", "budget_activity_title": "Combat Aircraft",
            "sub_activity": "01", "sub_activity_title": "F/A-18 Series",
            "line_item": "001", "line_item_title": "F/A-18E/F Super Hornet",
            "classification": "UNCLASSIFIED",
            "cost_type": None, "cost_type_title": None,
            "add_non_add": "add", "sheet_name": "P-1",
            "amount_fy2024_actual": 2100000.0,
            "amount_fy2025_enacted": 1900000.0,
            "pe_number": "0204136N", "amount_unit": "thousands",
            "amount_type": "budget_authority",
        },
    ]

    _create_excel_staging(staging, [
        {
            "rel_subpath": "FY2026/PB/US_Army/summary/p1_army",
            "fy_columns": ["amount_fy2025_enacted", "amount_fy2026_request"],
            "rows": army_rows_2026,
            "exhibit_type": "p1",
        },
        {
            "rel_subpath": "FY2025/PB/US_Navy/summary/p1_navy",
            "fy_columns": ["amount_fy2024_actual", "amount_fy2025_enacted"],
            "rows": navy_rows_2025,
            "exhibit_type": "p1",
        },
    ])

    # ── PDF: R-2 detail with PE mentions ──
    _create_pdf_staging(staging, [
        {
            "rel_subpath": "FY2026/PB/US_Army/detail/r2_army",
            "pages": [
                {"page_text": "Program Element 0203750A - Family of Medium Tactical Vehicles",
                 "category": "rdte", "exhibit_type": "r2", "page_number": 1},
                {"page_text": "Accomplishments: Delivered 500 FMTV units in FY2025",
                 "category": "rdte", "exhibit_type": "r2", "page_number": 2},
                {"page_text": "Program Element 0305210A - Joint Tactical Radio System JTRS",
                 "category": "rdte", "exhibit_type": "r2", "page_number": 3},
            ],
            "pe_mentions": [
                {"pe_number": "0203750A", "page_number": 1},
                {"pe_number": "0305210A", "page_number": 3},
            ],
        },
    ])

    return staging


# ── E2E Tests ─────────────────────────────────────────────────────────────────


class TestStagingE2ERoundtrip:
    """Full roundtrip: synthetic Parquet staging → SQLite, verify data integrity."""

    def test_all_budget_rows_loaded(self, tmp_path, realistic_staging):
        """Every row in staging Parquet appears in budget_lines."""
        db_path = tmp_path / "e2e.sqlite"
        summary = load_staging_to_db(realistic_staging, db_path, rebuild=True)

        assert summary["total_rows"] == 3  # 2 Army + 1 Navy
        assert summary["total_pages"] == 3

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        count = conn.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0]
        assert count == 3
        conn.close()

    def test_fy_columns_correctly_null_filled(self, tmp_path, realistic_staging):
        """Army rows lack fy2024, Navy rows lack fy2026 → both are NULL."""
        db_path = tmp_path / "e2e.sqlite"
        load_staging_to_db(realistic_staging, db_path, rebuild=True)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Army rows: fy2024 should be NULL
        army = conn.execute(
            "SELECT amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request "
            "FROM budget_lines WHERE organization_name = 'Army'"
        ).fetchall()
        assert len(army) == 2
        for row in army:
            assert row["amount_fy2024_actual"] is None
            assert row["amount_fy2025_enacted"] is not None
            assert row["amount_fy2026_request"] is not None

        # Navy rows: fy2026 should be NULL
        navy = conn.execute(
            "SELECT amount_fy2024_actual, amount_fy2025_enacted, amount_fy2026_request "
            "FROM budget_lines WHERE organization_name = 'Navy'"
        ).fetchall()
        assert len(navy) == 1
        assert navy[0]["amount_fy2024_actual"] is not None
        assert navy[0]["amount_fy2025_enacted"] is not None
        assert navy[0]["amount_fy2026_request"] is None

        conn.close()

    def test_amount_values_preserved(self, tmp_path, realistic_staging):
        """Dollar amounts survive the Parquet roundtrip without loss."""
        db_path = tmp_path / "e2e.sqlite"
        load_staging_to_db(realistic_staging, db_path, rebuild=True)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT amount_fy2026_request FROM budget_lines "
            "WHERE line_item_title = 'Family of Medium Tactical Vehicles'"
        ).fetchone()
        assert row is not None
        assert row[0] == 525000.0

        row2 = conn.execute(
            "SELECT amount_fy2024_actual FROM budget_lines "
            "WHERE line_item_title LIKE '%Super Hornet%'"
        ).fetchone()
        assert row2 is not None
        assert row2[0] == 2100000.0
        conn.close()

    def test_pdf_pages_loaded(self, tmp_path, realistic_staging):
        """PDF pages appear in pdf_pages with correct text."""
        db_path = tmp_path / "e2e.sqlite"
        load_staging_to_db(realistic_staging, db_path, rebuild=True)

        conn = sqlite3.connect(str(db_path))
        pages = conn.execute(
            "SELECT page_number, page_text FROM pdf_pages ORDER BY page_number"
        ).fetchall()
        assert len(pages) == 3
        assert "Family of Medium Tactical Vehicles" in pages[0][1]
        assert "Accomplishments" in pages[1][1]
        assert "Joint Tactical Radio System" in pages[2][1]
        conn.close()

    def test_pe_mentions_linked(self, tmp_path, realistic_staging):
        """PE mentions from sidecar are inserted into pdf_pe_numbers."""
        db_path = tmp_path / "e2e.sqlite"
        load_staging_to_db(realistic_staging, db_path, rebuild=True)

        conn = sqlite3.connect(str(db_path))
        pes = conn.execute(
            "SELECT pe_number, page_number FROM pdf_pe_numbers "
            "ORDER BY page_number"
        ).fetchall()
        assert len(pes) == 2
        assert pes[0][0] == "0203750A"
        assert pes[0][1] == 1
        assert pes[1][0] == "0305210A"
        assert pes[1][1] == 3
        conn.close()

    def test_ingested_files_tracked(self, tmp_path, realistic_staging):
        """All source files are recorded in ingested_files."""
        db_path = tmp_path / "e2e.sqlite"
        load_staging_to_db(realistic_staging, db_path, rebuild=True)

        conn = sqlite3.connect(str(db_path))
        files = conn.execute(
            "SELECT file_path, file_type, row_count, status "
            "FROM ingested_files ORDER BY file_path"
        ).fetchall()

        # 2 Excel + 1 PDF = 3 files
        assert len(files) == 3
        types = {f[1] for f in files}
        assert types == {"xlsx", "pdf"}

        # All should be "ok"
        for f in files:
            assert f[3] == "ok"

        conn.close()

    def test_fts_search_works_after_load(self, tmp_path, realistic_staging):
        """Full-text search returns results after staging load."""
        db_path = tmp_path / "e2e.sqlite"
        load_staging_to_db(realistic_staging, db_path, rebuild=True)

        conn = sqlite3.connect(str(db_path))

        # Search budget_lines FTS for a line item title
        results = conn.execute(
            "SELECT COUNT(*) FROM budget_lines_fts "
            "WHERE budget_lines_fts MATCH 'Tactical'"
        ).fetchone()[0]
        assert results >= 1  # "Family of Medium Tactical Vehicles" and "Tactical Radios"

        # Search pdf_pages FTS for page text
        pdf_results = conn.execute(
            "SELECT COUNT(*) FROM pdf_pages_fts "
            "WHERE pdf_pages_fts MATCH 'Accomplishments'"
        ).fetchone()[0]
        assert pdf_results >= 1

        conn.close()

    def test_discover_fy_columns_finds_all(self, realistic_staging):
        """discover_fy_columns() returns the union of all FY columns."""
        cols = discover_fy_columns(realistic_staging)
        assert "amount_fy2024_actual" in cols
        assert "amount_fy2025_enacted" in cols
        assert "amount_fy2026_request" in cols
        assert len(cols) == 3

    def test_rebuild_is_idempotent(self, tmp_path, realistic_staging):
        """Loading twice with rebuild=True yields same row counts."""
        db_path = tmp_path / "e2e.sqlite"

        s1 = load_staging_to_db(realistic_staging, db_path, rebuild=True)
        s2 = load_staging_to_db(realistic_staging, db_path, rebuild=True)

        assert s1["total_rows"] == s2["total_rows"]
        assert s1["total_pages"] == s2["total_pages"]

        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0]
        assert count == 3  # Not doubled
        conn.close()

    def test_cross_service_query(self, tmp_path, realistic_staging):
        """Can query across services after loading multi-source data."""
        db_path = tmp_path / "e2e.sqlite"
        load_staging_to_db(realistic_staging, db_path, rebuild=True)

        conn = sqlite3.connect(str(db_path))

        # Sum by organization
        rows = conn.execute(
            "SELECT organization_name, COUNT(*) as cnt "
            "FROM budget_lines GROUP BY organization_name ORDER BY organization_name"
        ).fetchall()
        org_counts = {r[0]: r[1] for r in rows}
        assert org_counts["Army"] == 2
        assert org_counts["Navy"] == 1
        conn.close()

    def test_progress_callback_invoked(self, tmp_path, realistic_staging):
        """Progress callback receives calls for each phase."""
        db_path = tmp_path / "e2e.sqlite"
        phases_seen = []

        def callback(phase, current, total, detail=""):
            phases_seen.append(phase)

        load_staging_to_db(
            realistic_staging, db_path, rebuild=True,
            progress_callback=callback,
        )

        # Should see at least load_excel, load_pdf, index, done
        assert "load_excel" in phases_seen
        assert "load_pdf" in phases_seen
        assert "index" in phases_seen
        assert "done" in phases_seen
