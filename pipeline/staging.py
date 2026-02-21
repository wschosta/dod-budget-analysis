"""
Parquet Staging Layer for DoD Budget Pipeline

Decouples expensive file parsing (hours) from cheap database rebuilds (minutes)
by writing parsed data to Parquet files as an intermediate format.

    Current:   Excel/PDF → parse (hours) → SQLite
    With staging: Excel/PDF → parse (hours) → Parquet staging → SQLite (minutes)

Phase 1: Parse source files → Parquet + sidecar .meta.json
Phase 2: Read Parquet staging → bulk INSERT into SQLite

Usage:
    # Stage all files (Phase 1)
    python stage_budget_data.py --docs-dir DoD_Budget_Documents --staging-dir staging

    # Load staged data into SQLite (Phase 2)
    python stage_budget_data.py --load-only --staging-dir staging --db dod_budget.sqlite
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Workaround for pyarrow 23+ / pandas 3.0+ incompatibility:
# pyarrow's pandas shim checks pandas.__version__ which was removed in pandas 3.0.
try:
    import pandas as _pd
    if not hasattr(_pd, "__version__"):
        import importlib.metadata as _meta
        _pd.__version__ = _meta.version("pandas")  # type: ignore[attr-defined]
except ImportError:
    pass  # pandas is optional; pyarrow works without it

import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

STAGING_VERSION = 1

# Fixed columns for Excel Parquet files (matches builder.py tuple order)
EXCEL_FIXED_COLUMNS = [
    "source_file",
    "exhibit_type",
    "sheet_name",
    "fiscal_year",
    "account",
    "account_title",
    "organization",
    "organization_name",
    "budget_activity",
    "budget_activity_title",
    "sub_activity",
    "sub_activity_title",
    "line_item",
    "line_item_title",
    "classification",
    "cost_type",
    "cost_type_title",
    "add_non_add",
]

# Tail columns that come after FY columns in the tuple
EXCEL_TAIL_COLUMNS = [
    "extra_fields",
    "pe_number",
    "currency_year",
    "appropriation_code",
    "appropriation_title",
    "amount_unit",
    "budget_type",
    "amount_type",
]

# PDF page columns (matches _extract_pdf_data pages_data tuple order)
PDF_COLUMNS = [
    "source_file",
    "source_category",
    "fiscal_year",
    "exhibit_type",
    "page_number",
    "page_text",
    "has_tables",
    "table_data",
]


# ── Phase 1: Parse → Parquet ────────────────────────────────────────────────


def needs_restaging(source_file: Path, staging_dir: Path, file_type: str) -> bool:
    """Check whether a source file needs to be re-staged.

    Compares the source file's size and mtime against the sidecar metadata.
    Returns True if the file is new, modified, or the sidecar is missing/corrupt.
    """
    meta_path = _sidecar_path(source_file, staging_dir, file_type)
    if not meta_path.exists():
        return True
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        stat = source_file.stat()
        if meta.get("source_file_size") != stat.st_size:
            return True
        if abs((meta.get("source_file_mtime") or 0) - stat.st_mtime) > 1:
            return True
        if meta.get("staging_version", 0) != STAGING_VERSION:
            return True
        if meta.get("error") is not None:
            return True  # Re-stage files that errored previously
        return False
    except (json.JSONDecodeError, OSError):
        return True


def stage_excel_file(
    file_path: Path,
    docs_dir: Path,
    staging_dir: Path,
    force: bool = False,
) -> dict[str, Any]:
    """Stage a single Excel file to Parquet.

    Calls the existing _extract_excel_rows() worker, writes the result as
    a Parquet file + .meta.json sidecar.

    Returns:
        Dict with keys: relative_path, row_count, fy_columns, error.
    """
    rel_path = str(file_path.relative_to(docs_dir))

    if not force and not needs_restaging(file_path, staging_dir, "excel"):
        return {
            "relative_path": rel_path,
            "row_count": -1,  # -1 = skipped
            "fy_columns": [],
            "error": None,
            "skipped": True,
        }

    # Import here to avoid circular imports and keep module lightweight
    from pipeline.builder import _extract_excel_rows

    result = _extract_excel_rows((str(file_path), str(docs_dir)))

    parquet_path = _parquet_path(file_path, staging_dir, "excel")
    meta_path = _sidecar_path(file_path, staging_dir, "excel")
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    error = result.get("error")
    rows = result.get("rows", [])
    fy_columns = sorted(result.get("columns", []))

    if error or not rows:
        # Write sidecar even on error (records the failure for inspection)
        _write_sidecar(meta_path, file_path, rel_path, result.get("exhibit_type"),
                        fy_columns, 0, error)
        # Remove stale parquet if it exists
        if parquet_path.exists():
            parquet_path.unlink()
        return {
            "relative_path": rel_path,
            "row_count": 0,
            "fy_columns": fy_columns,
            "error": error,
            "skipped": False,
        }

    # Build column names: fixed + sorted FY columns + tail
    all_col_names = EXCEL_FIXED_COLUMNS + fy_columns + EXCEL_TAIL_COLUMNS
    n_fixed = len(EXCEL_FIXED_COLUMNS)
    n_fy = len(fy_columns)
    n_tail = len(EXCEL_TAIL_COLUMNS)

    # Transpose rows (list of tuples) into columnar dict for Arrow
    columns: dict[str, list] = {col: [] for col in all_col_names}
    for row_tuple in rows:
        # row_tuple layout: (fixed..., fy_values..., tail...)
        for i, col in enumerate(EXCEL_FIXED_COLUMNS):
            columns[col].append(row_tuple[i] if i < len(row_tuple) else None)
        for j, col in enumerate(fy_columns):
            idx = n_fixed + j
            columns[col].append(row_tuple[idx] if idx < len(row_tuple) else None)
        for k, col in enumerate(EXCEL_TAIL_COLUMNS):
            idx = n_fixed + n_fy + k
            columns[col].append(row_tuple[idx] if idx < len(row_tuple) else None)

    # Build Arrow schema: strings for fixed/tail, float64 for FY columns
    fields = []
    for col in EXCEL_FIXED_COLUMNS:
        fields.append(pa.field(col, pa.string()))
    for col in fy_columns:
        fields.append(pa.field(col, pa.float64()))
    for col in EXCEL_TAIL_COLUMNS:
        fields.append(pa.field(col, pa.string()))

    schema = pa.schema(fields)

    # Build arrays, coercing types
    arrays = []
    for col in all_col_names:
        data = columns[col]
        if col in fy_columns:
            # FY columns are float64
            arrays.append(pa.array(data, type=pa.float64()))
        else:
            # String columns — coerce everything to str or None
            arrays.append(pa.array(
                [str(v) if v is not None else None for v in data],
                type=pa.string(),
            ))

    table = pa.table(arrays, schema=schema)
    pq.write_table(table, str(parquet_path), compression="snappy")

    _write_sidecar(meta_path, file_path, rel_path, result.get("exhibit_type"),
                    fy_columns, len(rows), None)

    return {
        "relative_path": rel_path,
        "row_count": len(rows),
        "fy_columns": fy_columns,
        "error": None,
        "skipped": False,
    }


def stage_pdf_file(
    file_path: Path,
    docs_dir: Path,
    staging_dir: Path,
    pdf_timeout: int = 30,
    force: bool = False,
) -> dict[str, Any]:
    """Stage a single PDF file to Parquet.

    Calls the existing _extract_pdf_data() worker, writes the result as
    a Parquet file + .meta.json sidecar.

    Returns:
        Dict with keys: relative_path, row_count, pe_mentions, error.
    """
    rel_path = str(file_path.relative_to(docs_dir))

    if not force and not needs_restaging(file_path, staging_dir, "pdf"):
        return {
            "relative_path": rel_path,
            "row_count": -1,
            "pe_mentions": [],
            "error": None,
            "skipped": True,
        }

    from pipeline.builder import _extract_pdf_data

    result = _extract_pdf_data((str(file_path), str(docs_dir), pdf_timeout))

    parquet_path = _parquet_path(file_path, staging_dir, "pdf")
    meta_path = _sidecar_path(file_path, staging_dir, "pdf")
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    error = result.get("error")
    pages_data = result.get("pages_data", [])
    pe_mentions = result.get("pe_mentions", [])
    issues = result.get("issues", [])

    if error or not pages_data:
        _write_pdf_sidecar(meta_path, file_path, rel_path,
                            result.get("category"), 0,
                            result.get("num_pages", 0),
                            pe_mentions, issues, error)
        if parquet_path.exists():
            parquet_path.unlink()
        return {
            "relative_path": rel_path,
            "row_count": 0,
            "pe_mentions": pe_mentions,
            "error": error,
            "skipped": False,
        }

    # Transpose pages_data (list of tuples) into columnar dict
    columns: dict[str, list] = {col: [] for col in PDF_COLUMNS}
    for page_tuple in pages_data:
        for i, col in enumerate(PDF_COLUMNS):
            columns[col].append(page_tuple[i] if i < len(page_tuple) else None)

    # Build Arrow table
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

    arrays = []
    for col in PDF_COLUMNS:
        data = columns[col]
        if col in ("page_number", "has_tables"):
            arrays.append(pa.array(
                [int(v) if v is not None else None for v in data],
                type=pa.int32(),
            ))
        else:
            arrays.append(pa.array(
                [str(v) if v is not None else None for v in data],
                type=pa.string(),
            ))

    table = pa.table(arrays, schema=schema)
    pq.write_table(table, str(parquet_path), compression="snappy")

    _write_pdf_sidecar(meta_path, file_path, rel_path,
                        result.get("category"), len(pages_data),
                        result.get("num_pages", 0),
                        pe_mentions, issues, None)

    return {
        "relative_path": rel_path,
        "row_count": len(pages_data),
        "pe_mentions": pe_mentions,
        "error": None,
        "skipped": False,
    }


def _stage_excel_worker(args: tuple) -> dict[str, Any]:
    """Subprocess-safe wrapper for stage_excel_file.

    Accepts (file_path_str, docs_dir_str, staging_dir_str, force) for pickling.
    Does parse + write in one step inside the worker process (avoids large IPC).
    """
    file_path_str, docs_dir_str, staging_dir_str, force = args
    try:
        return stage_excel_file(
            Path(file_path_str), Path(docs_dir_str),
            Path(staging_dir_str), force=force,
        )
    except Exception as e:
        return {
            "relative_path": str(Path(file_path_str).relative_to(Path(docs_dir_str))),
            "row_count": 0,
            "fy_columns": [],
            "error": f"{type(e).__name__}: {e}",
            "skipped": False,
        }


def _stage_pdf_worker(args: tuple) -> dict[str, Any]:
    """Subprocess-safe wrapper for stage_pdf_file."""
    file_path_str, docs_dir_str, staging_dir_str, pdf_timeout, force = args
    try:
        return stage_pdf_file(
            Path(file_path_str), Path(docs_dir_str),
            Path(staging_dir_str), pdf_timeout=pdf_timeout, force=force,
        )
    except Exception as e:
        return {
            "relative_path": str(Path(file_path_str).relative_to(Path(docs_dir_str))),
            "row_count": 0,
            "pe_mentions": [],
            "error": f"{type(e).__name__}: {e}",
            "skipped": False,
        }


def stage_all_files(
    docs_dir: Path,
    staging_dir: Path,
    workers: int = 0,
    force: bool = False,
    pdf_timeout: int = 30,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Stage all Excel and PDF files from docs_dir into staging_dir.

    Orchestrates parallel extraction using ProcessPoolExecutor.

    Args:
        docs_dir: Path to DoD_Budget_Documents directory.
        staging_dir: Path to staging output directory.
        workers: Number of parallel workers (0 = auto).
        force: If True, restage all files regardless of change detection.
        pdf_timeout: Seconds per PDF page table extraction timeout.
        progress_callback: Optional callable(phase, current, total, detail).

    Returns:
        Summary dict with total_files, staged_count, skipped_count,
        error_count, excel_fy_columns, elapsed_sec.
    """
    if not docs_dir.exists():
        raise FileNotFoundError(f"Documents directory not found: {docs_dir}")

    staging_dir.mkdir(parents=True, exist_ok=True)
    num_workers = workers if workers > 0 else min(os.cpu_count() or 1, 4)

    xlsx_files = sorted(docs_dir.rglob("*.xlsx"))
    pdf_files = sorted(docs_dir.rglob("*.pdf"))
    total_files = len(xlsx_files) + len(pdf_files)

    if progress_callback:
        progress_callback("scan", 0, total_files,
                          f"Found {len(xlsx_files)} Excel + {len(pdf_files)} PDF files")

    logger.info("Staging %d files (%d Excel, %d PDF) with %d workers",
                total_files, len(xlsx_files), len(pdf_files), num_workers)

    t_start = time.time()
    all_fy_columns: set[str] = set()
    staged_count = 0
    skipped_count = 0
    error_count = 0
    errors: list[dict] = []

    # ── Stage Excel files ────────────────────────────────────────────────
    if xlsx_files:
        xl_args = [
            (str(f), str(docs_dir), str(staging_dir), force)
            for f in xlsx_files
        ]
        if num_workers > 1 and len(xlsx_files) > 1:
            with ProcessPoolExecutor(max_workers=num_workers) as pool:
                futures = {
                    pool.submit(_stage_excel_worker, a): a[0]
                    for a in xl_args
                }
                for i, future in enumerate(as_completed(futures)):
                    result = future.result()
                    _tally_result(result, all_fy_columns, errors)
                    if result.get("skipped"):
                        skipped_count += 1
                    elif result.get("error"):
                        error_count += 1
                    else:
                        staged_count += 1
                    if progress_callback:
                        progress_callback(
                            "excel", i + 1, len(xlsx_files),
                            f"{'Skipped' if result.get('skipped') else 'Staged'}: "
                            f"{Path(result['relative_path']).name}"
                        )
        else:
            for i, a in enumerate(xl_args):
                result = _stage_excel_worker(a)
                _tally_result(result, all_fy_columns, errors)
                if result.get("skipped"):
                    skipped_count += 1
                elif result.get("error"):
                    error_count += 1
                else:
                    staged_count += 1
                if progress_callback:
                    progress_callback(
                        "excel", i + 1, len(xlsx_files),
                        f"{'Skipped' if result.get('skipped') else 'Staged'}: "
                        f"{Path(result['relative_path']).name}"
                    )

    # ── Stage PDF files ──────────────────────────────────────────────────
    if pdf_files:
        pdf_args = [
            (str(f), str(docs_dir), str(staging_dir), pdf_timeout, force)
            for f in pdf_files
        ]
        if num_workers > 1 and len(pdf_files) > 1:
            with ProcessPoolExecutor(max_workers=num_workers) as pool:
                futures = {
                    pool.submit(_stage_pdf_worker, a): a[0]
                    for a in pdf_args
                }
                for i, future in enumerate(as_completed(futures)):
                    result = future.result()
                    if result.get("skipped"):
                        skipped_count += 1
                    elif result.get("error"):
                        error_count += 1
                        errors.append({
                            "file": result["relative_path"],
                            "error": result["error"],
                        })
                    else:
                        staged_count += 1
                    if progress_callback:
                        progress_callback(
                            "pdf", i + 1, len(pdf_files),
                            f"{'Skipped' if result.get('skipped') else 'Staged'}: "
                            f"{Path(result['relative_path']).name}"
                        )
        else:
            for i, a in enumerate(pdf_args):
                result = _stage_pdf_worker(a)
                if result.get("skipped"):
                    skipped_count += 1
                elif result.get("error"):
                    error_count += 1
                    errors.append({
                        "file": result["relative_path"],
                        "error": result["error"],
                    })
                else:
                    staged_count += 1
                if progress_callback:
                    progress_callback(
                        "pdf", i + 1, len(pdf_files),
                        f"{'Skipped' if result.get('skipped') else 'Staged'}: "
                        f"{Path(result['relative_path']).name}"
                    )

    elapsed = time.time() - t_start

    # Write staging metadata
    _write_staging_metadata(staging_dir, sorted(all_fy_columns),
                             total_files, staged_count, skipped_count,
                             error_count)

    summary = {
        "total_files": total_files,
        "staged_count": staged_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "excel_fy_columns": sorted(all_fy_columns),
        "elapsed_sec": round(elapsed, 1),
        "errors": errors,
    }

    if progress_callback:
        progress_callback("done", total_files, total_files,
                          f"Staged {staged_count} files in {elapsed:.1f}s "
                          f"({skipped_count} skipped, {error_count} errors)")

    logger.info("Staging complete: %d staged, %d skipped, %d errors in %.1fs",
                staged_count, skipped_count, error_count, elapsed)
    return summary


# ── Phase 2: Parquet → SQLite ────────────────────────────────────────────────


def discover_fy_columns(staging_dir: Path) -> list[str]:
    """Scan all Excel sidecar .meta.json files to collect union of FY columns.

    Returns sorted list of all FY column names across all staged Excel files.
    """
    all_fy: set[str] = set()
    excel_dir = staging_dir / "excel"
    if not excel_dir.exists():
        return []
    for meta_file in excel_dir.rglob("*.meta.json"):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            for col in meta.get("fy_columns", []):
                all_fy.add(col)
        except (json.JSONDecodeError, OSError):
            continue
    return sorted(all_fy)


def load_staging_to_db(
    staging_dir: Path,
    db_path: Path,
    rebuild: bool = False,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> dict[str, Any]:
    """Load all staged Parquet files into a SQLite database.

    Phase 2 always does a full reload from staging (simpler and fast enough).

    Args:
        staging_dir: Path to the staging directory with Parquet files.
        db_path: Path for the SQLite database file.
        rebuild: If True, delete existing database first.
        progress_callback: Optional callable(phase, current, total, detail).

    Returns:
        Summary dict with total_rows, total_pages, elapsed_sec, fy_columns.
    """
    if not staging_dir.exists():
        raise FileNotFoundError(f"Staging directory not found: {staging_dir}")

    if rebuild and db_path.exists():
        db_path.unlink()
        logger.info("Removed existing database for rebuild: %s", db_path)

    # Import create_database for schema setup
    from pipeline.builder import create_database, _ensure_fy_columns

    t_start = time.time()

    # Discover all FY columns first
    all_fy_columns = discover_fy_columns(staging_dir)
    logger.info("Discovered %d FY columns across staged files", len(all_fy_columns))

    conn = create_database(db_path)

    # Ensure all dynamic FY columns exist
    if all_fy_columns:
        _ensure_fy_columns(conn, all_fy_columns)

    # Drop FTS triggers for bulk loading performance
    conn.execute("DROP TRIGGER IF EXISTS budget_lines_ai")
    conn.execute("DROP TRIGGER IF EXISTS budget_lines_ad")
    conn.execute("DROP TRIGGER IF EXISTS pdf_pages_ai")
    conn.execute("DROP TRIGGER IF EXISTS pdf_pages_ad")
    conn.commit()

    if rebuild:
        # Clear tables for full reload
        conn.execute("DELETE FROM budget_lines")
        conn.execute("DELETE FROM pdf_pages")
        conn.execute("DELETE FROM pdf_pe_numbers")
        conn.execute("DELETE FROM ingested_files")
        conn.commit()

    # ── Load Excel Parquets ──────────────────────────────────────────────
    total_rows = _load_excel_parquets(conn, staging_dir, all_fy_columns,
                                       progress_callback)

    # ── Load PDF Parquets ────────────────────────────────────────────────
    total_pages = _load_pdf_parquets(conn, staging_dir, progress_callback)

    # ── Rebuild FTS indexes ──────────────────────────────────────────────
    if progress_callback:
        progress_callback("index", 0, 2, "Rebuilding FTS indexes...")

    _rebuild_fts_indexes(conn)

    if progress_callback:
        progress_callback("index", 2, 2, "FTS indexes rebuilt")

    conn.commit()
    elapsed = time.time() - t_start

    # Register data sources
    from pipeline.builder import _register_data_source, DOCS_DIR
    # Try to determine docs_dir from staging metadata
    staging_meta_path = staging_dir / "_metadata.json"
    if staging_meta_path.exists():
        try:
            smeta = json.loads(staging_meta_path.read_text(encoding="utf-8"))
            docs_dir_str = smeta.get("docs_dir")
            if docs_dir_str:
                docs_dir = Path(docs_dir_str)
                if docs_dir.exists():
                    _register_data_source(conn, docs_dir)
        except (json.JSONDecodeError, OSError):
            pass

    conn.close()

    summary = {
        "total_rows": total_rows,
        "total_pages": total_pages,
        "elapsed_sec": round(elapsed, 1),
        "fy_columns": all_fy_columns,
    }

    logger.info("Loaded %d budget rows + %d PDF pages in %.1fs",
                total_rows, total_pages, elapsed)

    if progress_callback:
        progress_callback("done", 1, 1,
                          f"Loaded {total_rows:,} rows + {total_pages:,} pages "
                          f"in {elapsed:.1f}s")

    return summary


# ── Internal helpers ─────────────────────────────────────────────────────────


def _parquet_path(source_file: Path, staging_dir: Path, file_type: str) -> Path:
    """Compute the Parquet file path for a source file.

    Mirrors the source directory structure under staging/{file_type}/.
    Example: FY2026/Comptroller/p1_display.xlsx
           → staging/excel/FY2026/Comptroller/p1_display.parquet
    """
    # Use the relative path from the nearest FY* directory upward
    parts = source_file.parts
    fy_idx = None
    for i, p in enumerate(parts):
        if p.startswith("FY") and len(p) >= 4:
            fy_idx = i
            break
    if fy_idx is not None:
        rel = Path(*parts[fy_idx:])
    else:
        rel = Path(source_file.name)

    return staging_dir / file_type / rel.with_suffix(".parquet")


def _sidecar_path(source_file: Path, staging_dir: Path, file_type: str) -> Path:
    """Compute the .meta.json sidecar path for a source file."""
    parq = _parquet_path(source_file, staging_dir, file_type)
    return parq.with_suffix(".meta.json")


def _write_sidecar(
    meta_path: Path,
    source_file: Path,
    rel_path: str,
    exhibit_type: str | None,
    fy_columns: list[str],
    row_count: int,
    error: str | None,
) -> None:
    """Write an Excel sidecar .meta.json file."""
    stat = source_file.stat()
    meta = {
        "staging_version": STAGING_VERSION,
        "source_file": rel_path,
        "source_file_size": stat.st_size,
        "source_file_mtime": stat.st_mtime,
        "exhibit_type": exhibit_type,
        "fy_columns": fy_columns,
        "row_count": row_count,
        "parse_timestamp": datetime.now(timezone.utc).isoformat(),
        "parser_version": "pipeline.staging:v1",
        "error": error,
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _write_pdf_sidecar(
    meta_path: Path,
    source_file: Path,
    rel_path: str,
    category: str | None,
    page_count: int,
    total_pages: int,
    pe_mentions: list[tuple],
    issues: list[tuple],
    error: str | None,
) -> None:
    """Write a PDF sidecar .meta.json file."""
    stat = source_file.stat()
    meta = {
        "staging_version": STAGING_VERSION,
        "source_file": rel_path,
        "source_file_size": stat.st_size,
        "source_file_mtime": stat.st_mtime,
        "source_category": category,
        "page_count": page_count,
        "total_pages": total_pages,
        "pe_mentions": [{"pe_number": pe, "page_number": pg}
                        for pe, pg in pe_mentions],
        "extraction_issues": [
            {"file": i[0], "page": i[1], "type": i[2], "detail": i[3]}
            for i in issues
        ],
        "parse_timestamp": datetime.now(timezone.utc).isoformat(),
        "parser_version": "pipeline.staging:v1",
        "error": error,
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _write_staging_metadata(
    staging_dir: Path,
    fy_columns: list[str],
    total_files: int,
    staged_count: int,
    skipped_count: int,
    error_count: int,
    docs_dir: Path | None = None,
) -> None:
    """Write the top-level _metadata.json for the staging directory."""
    meta = {
        "staging_version": STAGING_VERSION,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_files": total_files,
        "staged_count": staged_count,
        "skipped_count": skipped_count,
        "error_count": error_count,
        "excel_fy_columns": fy_columns,
    }
    if docs_dir:
        meta["docs_dir"] = str(docs_dir)
    (staging_dir / "_metadata.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )


def _tally_result(
    result: dict,
    all_fy_columns: set[str],
    errors: list[dict],
) -> None:
    """Accumulate FY columns and errors from a staging result."""
    for col in result.get("fy_columns", []):
        all_fy_columns.add(col)
    if result.get("error"):
        errors.append({
            "file": result["relative_path"],
            "error": result["error"],
        })


def _load_excel_parquets(
    conn: sqlite3.Connection,
    staging_dir: Path,
    all_fy_columns: list[str],
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> int:
    """Load all Excel Parquet files into the budget_lines table.

    Handles dynamic FY columns by NULL-filling columns absent in each file.

    Returns total rows inserted.
    """
    excel_dir = staging_dir / "excel"
    if not excel_dir.exists():
        return 0

    parquet_files = sorted(excel_dir.rglob("*.parquet"))
    if not parquet_files:
        return 0

    total_rows = 0
    # Build the full column list for INSERT
    all_col_names = EXCEL_FIXED_COLUMNS + all_fy_columns + EXCEL_TAIL_COLUMNS

    col_str = ", ".join(all_col_names)
    placeholders = ", ".join(["?"] * len(all_col_names))
    insert_sql = f"INSERT INTO budget_lines ({col_str}) VALUES ({placeholders})"

    for fi, pf in enumerate(parquet_files):
        if progress_callback:
            progress_callback("load_excel", fi + 1, len(parquet_files),
                              f"Loading: {pf.stem}")

        try:
            table = pq.read_table(str(pf))
        except Exception as e:
            logger.warning("Failed to read %s: %s", pf, e)
            continue

        pf_col_names = table.column_names
        n_rows = table.num_rows
        if n_rows == 0:
            continue

        # Read each column into a Python list
        col_data: dict[str, list] = {}
        for col_name in pf_col_names:
            col_data[col_name] = table.column(col_name).to_pylist()

        # Build rows with NULL-fill for missing FY columns
        batch = []
        for row_idx in range(n_rows):
            row_values = []
            for col_name in all_col_names:
                if col_name in col_data:
                    row_values.append(col_data[col_name][row_idx])
                else:
                    row_values.append(None)
            batch.append(tuple(row_values))

        conn.executemany(insert_sql, batch)
        total_rows += n_rows

        # Record in ingested_files
        meta_path = pf.with_suffix(".meta.json")
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                rel_path = meta.get("source_file", pf.stem)
                conn.execute(
                    "INSERT OR REPLACE INTO ingested_files "
                    "(file_path, file_type, file_size, file_modified, "
                    "ingested_at, row_count, status) "
                    "VALUES (?, ?, ?, ?, datetime('now'), ?, ?)",
                    (rel_path, "xlsx",
                     meta.get("source_file_size"),
                     meta.get("source_file_mtime"),
                     n_rows, "ok" if not meta.get("error") else f"error: {meta['error']}")
                )
            except (json.JSONDecodeError, OSError):
                pass

        # Commit in batches for performance
        if fi % 50 == 0:
            conn.commit()

    conn.commit()
    logger.info("Loaded %d budget rows from %d Excel parquets", total_rows, len(parquet_files))
    return total_rows


def _load_pdf_parquets(
    conn: sqlite3.Connection,
    staging_dir: Path,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> int:
    """Load all PDF Parquet files into the pdf_pages table.

    Also loads PE mentions from sidecars into pdf_pe_numbers.

    Returns total pages inserted.
    """
    pdf_dir = staging_dir / "pdf"
    if not pdf_dir.exists():
        return 0

    parquet_files = sorted(pdf_dir.rglob("*.parquet"))
    if not parquet_files:
        return 0

    total_pages = 0
    insert_sql = (
        "INSERT INTO pdf_pages "
        "(source_file, source_category, fiscal_year, exhibit_type, "
        "page_number, page_text, has_tables, table_data) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    )
    pe_insert_sql = (
        "INSERT INTO pdf_pe_numbers "
        "(pdf_page_id, pe_number, page_number, source_file, fiscal_year) "
        "VALUES (?, ?, ?, ?, ?)"
    )

    for fi, pf in enumerate(parquet_files):
        if progress_callback:
            progress_callback("load_pdf", fi + 1, len(parquet_files),
                              f"Loading: {pf.stem}")

        try:
            table = pq.read_table(str(pf))
        except Exception as e:
            logger.warning("Failed to read %s: %s", pf, e)
            continue

        n_rows = table.num_rows
        if n_rows == 0:
            continue

        # Read columns
        col_data: dict[str, list] = {}
        for col_name in table.column_names:
            col_data[col_name] = table.column(col_name).to_pylist()

        # Build batch
        batch = []
        for row_idx in range(n_rows):
            row_values = []
            for col_name in PDF_COLUMNS:
                if col_name in col_data:
                    val = col_data[col_name][row_idx]
                    if col_name in ("page_number", "has_tables") and val is not None:
                        val = int(val)
                    row_values.append(val)
                else:
                    row_values.append(None)
            batch.append(tuple(row_values))

        conn.executemany(insert_sql, batch)
        total_pages += n_rows

        # Load PE mentions from sidecar
        meta_path = pf.with_suffix(".meta.json")
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                pe_mentions = meta.get("pe_mentions", [])
                rel_path = meta.get("source_file", "")
                fiscal_year = None

                # Get fiscal year from the first page's data if available
                if "fiscal_year" in col_data and col_data["fiscal_year"]:
                    fiscal_year = col_data["fiscal_year"][0]

                if pe_mentions:
                    # We need the pdf_page_id for each PE mention.
                    # Query for recently inserted pages for this source file.
                    page_id_map = {}
                    cursor = conn.execute(
                        "SELECT id, page_number FROM pdf_pages "
                        "WHERE source_file = ? ORDER BY page_number",
                        (rel_path,)
                    )
                    for row in cursor:
                        page_id_map[row[1]] = row[0]

                    pe_batch = []
                    for pm in pe_mentions:
                        pe_num = pm.get("pe_number") if isinstance(pm, dict) else pm[0]
                        page_num = pm.get("page_number") if isinstance(pm, dict) else pm[1]
                        page_id = page_id_map.get(page_num)
                        pe_batch.append((page_id, pe_num, page_num, rel_path, fiscal_year))

                    if pe_batch:
                        conn.executemany(pe_insert_sql, pe_batch)

                # Record in ingested_files
                conn.execute(
                    "INSERT OR REPLACE INTO ingested_files "
                    "(file_path, file_type, file_size, file_modified, "
                    "ingested_at, row_count, status) "
                    "VALUES (?, ?, ?, ?, datetime('now'), ?, ?)",
                    (rel_path, "pdf",
                     meta.get("source_file_size"),
                     meta.get("source_file_mtime"),
                     n_rows, "ok" if not meta.get("error") else f"error: {meta['error']}")
                )

                # Record extraction issues
                for issue in meta.get("extraction_issues", []):
                    conn.execute(
                        "INSERT INTO extraction_issues "
                        "(file_path, page_number, issue_type, issue_detail) "
                        "VALUES (?, ?, ?, ?)",
                        (issue.get("file"), issue.get("page"),
                         issue.get("type"), issue.get("detail"))
                    )

            except (json.JSONDecodeError, OSError):
                pass

        if fi % 50 == 0:
            conn.commit()

    conn.commit()
    logger.info("Loaded %d PDF pages from %d parquets", total_pages, len(parquet_files))
    return total_pages


def _rebuild_fts_indexes(conn: sqlite3.Connection) -> None:
    """Rebuild FTS5 indexes and recreate triggers for both tables."""
    # Rebuild budget_lines FTS
    try:
        conn.execute("INSERT INTO budget_lines_fts(budget_lines_fts) VALUES('rebuild')")
    except Exception as e:
        logger.warning("Failed to rebuild budget_lines_fts: %s", e)

    # Recreate budget_lines FTS triggers
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS budget_lines_ai AFTER INSERT ON budget_lines BEGIN
            INSERT INTO budget_lines_fts(rowid, account_title, budget_activity_title,
                sub_activity_title, line_item_title, organization_name, pe_number)
            VALUES (new.id, new.account_title, new.budget_activity_title,
                new.sub_activity_title, new.line_item_title, new.organization_name,
                new.pe_number);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS budget_lines_ad AFTER DELETE ON budget_lines BEGIN
            INSERT INTO budget_lines_fts(budget_lines_fts, rowid, account_title,
                budget_activity_title, sub_activity_title, line_item_title,
                organization_name, pe_number)
            VALUES ('delete', old.id, old.account_title, old.budget_activity_title,
                old.sub_activity_title, old.line_item_title, old.organization_name,
                old.pe_number);
        END
    """)

    # Rebuild pdf_pages FTS
    try:
        conn.execute("INSERT INTO pdf_pages_fts(pdf_pages_fts) VALUES('rebuild')")
    except Exception as e:
        logger.warning("Failed to rebuild pdf_pages_fts: %s", e)

    # Recreate pdf_pages FTS triggers
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS pdf_pages_ai AFTER INSERT ON pdf_pages BEGIN
            INSERT INTO pdf_pages_fts(rowid, page_text, source_file, table_data)
            VALUES (new.id, new.page_text, new.source_file, new.table_data);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS pdf_pages_ad AFTER DELETE ON pdf_pages BEGIN
            INSERT INTO pdf_pages_fts(pdf_pages_fts, rowid, page_text, source_file, table_data)
            VALUES ('delete', old.id, old.page_text, old.source_file, old.table_data);
        END
    """)
