"""
Full pipeline runner -- downloads, builds, repairs, validates, and enriches
the DoD budget database.

Steps (in order):
  0. download              -- download budget documents from DoD websites
  1. build / stage+load    -- ingest Excel + PDF source files into SQLite
  2. repair                -- normalize data, create reference tables,
                              add indexes, rebuild FTS
  3. validate              -- QA checks against the populated DB
  4. enrich                -- populate pe_index, pe_descriptions,
                              pe_tags, pe_lineage

Features:
  - Direct function imports for all steps (no subprocess overhead)
  - Automatic DB backup before build; rollback on failure
  - JSON progress file for external monitoring
  - Per-step log files under logs/pipeline/<run-id>/ with full accountability
  - Append-only JSONL ledger for cross-run history

Usage:
    python run_pipeline.py                            # full pipeline (download → enrich)
    python run_pipeline.py --skip-download            # skip download, build existing docs
    python run_pipeline.py --rebuild                  # full rebuild from scratch
    python run_pipeline.py --rebuild --years 2026     # rebuild, only download FY2026
    python run_pipeline.py --years 2026 --sources all # download all sources for FY2026
    python run_pipeline.py --use-staging              # use Parquet staging layer
    python run_pipeline.py --repair-only              # only run the repair step
    python run_pipeline.py --report                   # generate data_quality_report.json
    python run_pipeline.py --skip-validate            # skip validation step
    python run_pipeline.py --skip-enrich              # stop after validation
    python run_pipeline.py --skip-repair              # skip the repair step
    python run_pipeline.py --no-rollback              # disable automatic rollback
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import shutil
import subprocess
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from pipeline.logging import PipelineLogger, StepReport


HERE = Path(__file__).resolve().parent

# Download step uses subprocess as a fallback when direct import fails
STEP_DOWNLOAD = HERE / "dod_budget_downloader.py"

# Progress file for external monitors
_PROGRESS_FILE = Path("pipeline_progress.json")

# Track completed steps for progress reporting
_completed_steps: dict[str, str] = {}

# Graceful shutdown event — shared across all pipeline steps
_stop_event = threading.Event()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _find_python() -> str:
    """Return a console-mode python.exe, never pythonw.exe."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        candidate = exe.with_name("python.exe")
        if candidate.exists():
            return str(candidate)
    return str(exe)


PYTHON = _find_python()


def _banner(text: str) -> None:
    bar = "=" * 60
    print(f"\n{bar}")
    print(f"  {text}")
    print(f"{bar}\n", flush=True)


def _write_progress(step: str, status: str, elapsed: float, detail: str = "") -> None:
    """Write pipeline_progress.json for external monitoring."""
    progress = {
        "current_step": step,
        "status": status,
        "elapsed_seconds": round(elapsed, 1),
        "detail": detail,
        "timestamp": datetime.now().isoformat(),
        "steps_completed": dict(_completed_steps),
    }
    try:
        with open(_PROGRESS_FILE, "w") as f:
            json.dump(progress, f, indent=2)
    except OSError:
        pass


def _clear_progress() -> None:
    """Remove the progress file on successful completion."""
    try:
        _PROGRESS_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _backup_db(db_path: Path) -> Path | None:
    """Copy the current database to a .bak file before building."""
    if not db_path.exists():
        return None
    backup = db_path.with_suffix(".sqlite.bak")
    shutil.copy2(db_path, backup)
    print(f"  Database backed up to {backup}", flush=True)
    return backup


def _rollback_db(db_path: Path, backup: Path | None) -> bool:
    """Restore the database from backup after a failed build.

    On Windows, SQLite may keep the database file memory-mapped even after
    the connection is closed. We retry with a short delay to allow the OS
    to release the file handle.
    """
    if not backup or not backup.exists():
        return False

    import time as _time
    for attempt in range(5):
        try:
            shutil.copy2(backup, db_path)
            print(f"  Database restored from {backup}", flush=True)
            return True
        except OSError as e:
            # WinError 1224: file with user-mapped section open
            if attempt < 4:
                _time.sleep(0.5 * (attempt + 1))
            else:
                print(f"  Warning: could not restore backup — {e}", flush=True)
                print(f"  Backup is preserved at: {backup}", flush=True)
                return False
    return False


def _cleanup_backup(backup: Path | None) -> None:
    """Remove the backup file after a successful pipeline run."""
    if backup and backup.exists():
        try:
            backup.unlink()
        except OSError:
            pass


def _build_progress(phase: str, current: int, total: int, detail: str = "",
                     metrics: dict | None = None) -> None:
    """Progress callback for build_database() — prints live file-by-file status."""
    if phase == "scan":
        if total > 0:
            print(f"  Scanning... {total} files found", flush=True)
        else:
            print(f"  {detail}", flush=True)
    elif phase in ("excel", "pdf"):
        label = "Excel" if phase == "excel" else "PDF"
        pct = (current / total * 100) if total > 0 else 0
        eta = ""
        if metrics and metrics.get("eta_sec", 0) > 0:
            eta_min = metrics["eta_sec"] / 60
            eta = f"  ETA: {eta_min:.0f}m" if eta_min >= 1 else f"  ETA: {metrics['eta_sec']:.0f}s"
        # Truncate detail (filename) to keep output clean
        short_detail = detail[:60] + "..." if len(detail) > 63 else detail
        print(f"  [{label}] {current}/{total} ({pct:.0f}%){eta}  {short_detail}", flush=True)
    elif phase == "index":
        print(f"  {detail}", flush=True)
    elif phase == "done":
        if isinstance(detail, dict):
            rows = detail.get("total_rows", 0)
            pages = detail.get("total_pages", 0)
            print(f"  Build complete: {rows:,} rows, {pages:,} PDF pages", flush=True)
        elif isinstance(detail, str) and detail:
            print(f"  {detail}", flush=True)
    elif phase == "error":
        print(f"  ERROR: {detail}", flush=True)


def _staging_progress(phase: str, current: int, total: int, detail: str = "") -> None:
    """Progress callback for stage_all_files() and load_staging_to_db()."""
    if phase == "scan":
        if total > 0:
            print(f"  Scanning... {total} files", flush=True)
        elif detail:
            print(f"  {detail}", flush=True)
    elif phase in ("excel", "pdf", "load_excel", "load_pdf"):
        label = {"excel": "Stage Excel", "pdf": "Stage PDF",
                 "load_excel": "Load Excel", "load_pdf": "Load PDF"}.get(phase, phase)
        pct = (current / total * 100) if total > 0 else 0
        short_detail = detail[:60] + "..." if len(detail) > 63 else detail
        print(f"  [{label}] {current}/{total} ({pct:.0f}%)  {short_detail}", flush=True)
    elif phase == "index":
        print(f"  {detail}", flush=True)
    elif phase == "done":
        if detail:
            print(f"  {detail}", flush=True)


def _check_stopped(step_name: str = "") -> bool:
    """Return True and print a message if graceful shutdown was requested."""
    if _stop_event.is_set():
        where = f" during {step_name}" if step_name else ""
        print(f"\n  Pipeline stopped gracefully{where}.", flush=True)
        _write_progress(step_name or "shutdown", "stopped", 0, "Graceful shutdown")
        return True
    return False


def _run_step(label: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[bool, Any]:
    """Run a pipeline step with timing, progress tracking, and error handling."""
    _banner(label)
    _write_progress(label, "running", 0)
    t0 = time.monotonic()
    try:
        result = fn(*args, **kwargs)
        elapsed = time.monotonic() - t0
        print(f"\n[{label}] OK -- {elapsed:.1f}s", flush=True)
        _write_progress(label, "completed", elapsed)
        _completed_steps[label] = f"completed in {elapsed:.1f}s"
        return True, result
    except KeyboardInterrupt:
        elapsed = time.monotonic() - t0
        _stop_event.set()
        print(f"\n[{label}] INTERRUPTED -- {elapsed:.1f}s", flush=True)
        _write_progress(label, "interrupted", elapsed)
        _completed_steps[label] = f"interrupted after {elapsed:.1f}s"
        return False, None
    except Exception as e:
        elapsed = time.monotonic() - t0
        print(f"\n[{label}] FAILED -- {elapsed:.1f}s: {e}", flush=True)
        _write_progress(label, "failed", elapsed, str(e))
        _completed_steps[label] = f"failed: {e}"
        return False, None


def _run_subprocess(label: str, cmd: list[str]) -> int:
    """Run a subprocess step, stream its output live, and return its exit code."""
    _banner(label)
    print(f"Command: {' '.join(cmd)}\n", flush=True)
    _write_progress(label, "running", 0)
    t0 = time.monotonic()
    result = subprocess.run(cmd)
    elapsed = time.monotonic() - t0
    status = "OK" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
    print(f"\n[{label}] {status} -- {elapsed:.1f}s", flush=True)
    step_status = f"completed in {elapsed:.1f}s" if result.returncode == 0 else f"failed (exit {result.returncode})"
    _write_progress(label, "completed" if result.returncode == 0 else "failed", elapsed)
    _completed_steps[label] = step_status
    return result.returncode


# ── StepReport population helpers ─────────────────────────────────────────────


def _build_report_from_download(report: StepReport, result: dict | None) -> None:
    """Populate a StepReport from download_all()'s return dict."""
    if not result or not isinstance(result, dict):
        return
    report.items_processed = result.get("downloaded", 0)
    report.metrics = {
        "downloaded": result.get("downloaded", 0),
        "skipped": result.get("skipped", 0),
        "failed": result.get("failed", 0),
        "total_bytes": result.get("total_bytes", 0),
    }
    skipped = result.get("skipped", 0)
    if skipped:
        report.add_skip("incremental_skip", f"{skipped} file(s) already on disk")
    failed = result.get("failed", 0)
    if failed:
        report.add_error(f"{failed} file(s) failed to download")


def _build_report_from_builder(report: StepReport, result: dict | None) -> None:
    """Populate a StepReport from build_database()'s return dict."""
    if not result or not isinstance(result, dict):
        return
    report.items_processed = (
        result.get("excel_files", 0) - result.get("skipped_excel", 0)
        + result.get("pdf_files", 0) - result.get("skipped_pdf", 0)
    )
    report.metrics = {
        "total_rows": result.get("total_rows", 0),
        "total_pages": result.get("total_pages", 0),
        "db_size_mb": result.get("db_size_mb", 0),
    }
    # Account for skips
    skipped_excel = result.get("skipped_excel", 0)
    skipped_pdf = result.get("skipped_pdf", 0)
    if skipped_excel:
        report.add_skip("incremental_skip",
                         f"{skipped_excel} unchanged Excel file(s)")
    if skipped_pdf:
        report.add_skip("incremental_skip",
                         f"{skipped_pdf} unchanged PDF file(s)")
    # Account for errors
    for err_file in result.get("error_files", []):
        report.add_error(f"Failed to process: {err_file}")


def _build_report_from_staging(report: StepReport, result: dict | None) -> None:
    """Populate a StepReport from stage_all_files()'s return dict."""
    if not result or not isinstance(result, dict):
        return
    report.items_processed = result.get("staged_count", 0)
    skipped = result.get("skipped_count", 0)
    if skipped:
        report.add_skip("incremental_skip", f"{skipped} unchanged file(s)")
    for err in result.get("errors", []):
        err_detail = err if isinstance(err, str) else str(err)
        report.add_error(err_detail)


def _build_report_from_load(report: StepReport, result: dict | None) -> None:
    """Populate a StepReport from load_staging_to_db()'s return dict."""
    if not result or not isinstance(result, dict):
        return
    report.metrics = {
        "total_rows": result.get("total_rows", 0),
        "total_pages": result.get("total_pages", 0),
    }


def _build_report_from_repair(report: StepReport, result: dict | None) -> None:
    """Populate a StepReport from repair()'s return dict."""
    if not result or not isinstance(result, dict):
        return
    report.items_processed = (
        result.get("org_normalized", 0)
        + result.get("approp_backfilled", 0)
    )
    ref_summary = result.get("reference", {})
    report.metrics = {
        "org_normalized": result.get("org_normalized", 0),
        "approp_backfilled": result.get("approp_backfilled", 0),
        "reference_services": ref_summary.get("services_agencies", 0),
        "reference_exhibits": ref_summary.get("exhibit_types", 0),
        "reference_appropriations": ref_summary.get("appropriation_titles", 0),
    }


def _build_report_from_validator(report: StepReport, result: dict | None) -> None:
    """Populate a StepReport from validate_all()'s return dict."""
    if not result or not isinstance(result, dict):
        return
    checks = result.get("checks", [])
    report.items_processed = len(checks)
    report.metrics = {
        "total_checks": result.get("total_checks", 0),
        "total_warnings": result.get("total_warnings", 0),
        "total_failures": result.get("total_failures", 0),
    }
    # Record each failed/warning check as an error or skip
    for check in checks:
        if check.get("status") == "fail":
            report.add_error(f"{check.get('name', '?')}: {check.get('message', '')}")
        elif check.get("status") == "warn":
            report.add_skip("dependency_skip",
                             f"Warning: {check.get('message', '')}",
                             item=check.get("name", ""))


def _build_report_from_enricher(report: StepReport, result: dict | None) -> None:
    """Populate a StepReport from enrich()'s return dict."""
    if not result or not isinstance(result, dict):
        return
    phase_results = result.get("phase_results", {})
    total_rows = sum(phase_results.values())
    report.items_processed = total_rows
    report.metrics = {
        "phases_run": result.get("phases_run", []),
        "table_counts": result.get("table_counts", {}),
    }
    if result.get("stopped_after") is not None:
        report.detail = f"Stopped after phase {result['stopped_after']}"
    # Record skipped phases
    for skip in result.get("phases_skipped", []):
        phase = skip.get("phase", "?")
        reason = skip.get("reason", "unknown")
        if reason == "not selected":
            report.add_skip("user_skipped",
                             f"Phase {phase} not in selected phases")
        else:
            report.add_skip("already_done",
                             f"Phase {phase}: {reason}")


# ── Argument parser ───────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Run the full DoD budget pipeline: "
            "download -> build -> repair -> validate -> enrich"
        ),
    )

    # Shared
    p.add_argument(
        "--db", default="dod_budget.sqlite",
        help="Database path (default: dod_budget.sqlite)",
    )

    # Download options (download is ON by default)
    dl_group = p.add_argument_group("download options")
    dl_group.add_argument(
        "--skip-download", action="store_true",
        help="Skip the document download step",
    )
    dl_group.add_argument(
        "--years", nargs="+", default=None, metavar="YEAR",
        help="Fiscal years to download (e.g., 2026 2025). Default: all available.",
    )
    dl_group.add_argument(
        "--sources", nargs="+", default=None, metavar="SRC",
        help=(
            "Sources to download (e.g., all, comptroller, army, navy, "
            "airforce, defense-wide). Default: comptroller."
        ),
    )
    dl_group.add_argument(
        "--download-workers", type=int, default=4, metavar="N",
        help="HTTP download threads (default: 4)",
    )
    dl_group.add_argument(
        "--download-delay", type=float, default=0.1, metavar="SECS",
        help="Delay between per-source page fetches (default: 0.1s)",
    )
    dl_group.add_argument(
        "--overwrite-downloads", action="store_true",
        help="Re-download files that already exist on disk",
    )
    dl_group.add_argument(
        "--extract-zips", action="store_true",
        help="Extract ZIP files after downloading",
    )

    # Staging options
    stg_group = p.add_argument_group("staging options")
    stg_group.add_argument(
        "--use-staging", action="store_true",
        help="Use Parquet staging layer (Stage -> Load -> Validate -> Enrich)",
    )
    stg_group.add_argument(
        "--staging-dir", default="staging",
        help="Staging directory for Parquet files (default: staging)",
    )
    stg_group.add_argument(
        "--stage-only", action="store_true",
        help="Only run staging (Phase 1: parse -> Parquet); skip DB build",
    )
    stg_group.add_argument(
        "--load-only", action="store_true",
        help="Only run load (Phase 2: Parquet -> SQLite); skip file parsing",
    )

    # Build options
    build_group = p.add_argument_group("build options")
    build_group.add_argument(
        "--docs", default=None,
        help="Documents directory (default: DoD_Budget_Documents)",
    )
    build_group.add_argument(
        "--rebuild", action="store_true",
        help="Force full rebuild of the database (drops and recreates all tables)",
    )
    build_group.add_argument(
        "--resume", action="store_true",
        help="Resume build from last checkpoint",
    )
    build_group.add_argument(
        "--workers", type=int, default=None,
        help="Parallel PDF workers (default: auto-detect CPU count)",
    )
    build_group.add_argument(
        "--checkpoint-interval", type=int, default=None, metavar="N",
        help="Checkpoint every N files (default: 10)",
    )
    build_group.add_argument(
        "--pdf-timeout", type=int, default=30, metavar="SECS",
        help="Seconds per PDF page table extraction (default: 30)",
    )

    # Repair options
    repair_group = p.add_argument_group("repair options")
    repair_group.add_argument(
        "--skip-repair", action="store_true",
        help="Skip the database repair step",
    )
    repair_group.add_argument(
        "--repair-only", action="store_true",
        help="Run only the repair step (skip download, build, validate, enrich)",
    )

    # Validate options
    val_group = p.add_argument_group("validate options")
    val_group.add_argument(
        "--skip-validate", action="store_true",
        help="Skip the validation step",
    )
    val_group.add_argument(
        "--strict", action="store_true",
        help="Abort the pipeline on validation failures",
    )
    val_group.add_argument(
        "--pedantic", action="store_true",
        help="Abort the pipeline on any validation warnings or failures",
    )
    val_group.add_argument(
        "--report", action="store_true",
        help="Generate a data quality report after validation",
    )
    val_group.add_argument(
        "--report-path", default="data_quality_report.json", metavar="PATH",
        help="Path for the quality report (default: data_quality_report.json)",
    )

    # Enrich options
    enr_group = p.add_argument_group("enrich options")
    enr_group.add_argument(
        "--skip-enrich", action="store_true",
        help="Skip the enrichment step",
    )
    enr_group.add_argument(
        "--with-llm", action="store_true",
        help="Enable LLM-based tagging (requires ANTHROPIC_API_KEY)",
    )
    enr_group.add_argument(
        "--enrich-phases", default=None, metavar="PHASES",
        help="Comma-separated enrichment phases to run (default: 1,2,3,4,5)",
    )
    enr_group.add_argument(
        "--rebuild-enrich", action="store_true",
        help="Drop and rebuild enrichment tables only (not the full DB)",
    )

    # Rollback options
    p.add_argument(
        "--no-rollback", action="store_true",
        help="Skip automatic database rollback on build failure",
    )

    # Logging options
    p.add_argument(
        "--logs-dir", default="logs/pipeline",
        help="Directory for pipeline run logs (default: logs/pipeline)",
    )

    # Legacy compat: --download is silently accepted (no-op, download is default)
    p.add_argument("--download", action="store_true", help=argparse.SUPPRESS)

    return p.parse_args(argv)


# ── Download step (direct call with subprocess fallback) ──────────────────────


def _run_download(args: argparse.Namespace, docs_dir: Path) -> dict:
    """Discover and download budget documents.

    Uses direct Python imports for structured return values and StepReport
    integration.  Falls back to subprocess if downloader imports fail
    (e.g. Playwright not installed).

    Returns:
        Summary dict with keys: downloaded, skipped, failed, total_bytes.
    """
    import time as _time

    from downloader.core import (
        download_all,
        get_session,
        deduplicate_across_sources,
    )
    from downloader.sources import (
        ALL_SOURCES,
        SERVICE_PAGE_TEMPLATES,
        SOURCE_DISCOVERERS,
        _is_browser_source,
        _close_browser,
        discover_fiscal_years,
        discover_comptroller_files,
    )
    from downloader.manifest import write_manifest
    from downloader.metadata import validate_fy_match

    session = get_session()

    # Discover available fiscal years
    print("  Discovering available fiscal years...", flush=True)
    available_years = discover_fiscal_years(session)
    if not available_years:
        print("  WARNING: No fiscal years discovered from Comptroller page.", flush=True)
        return {"downloaded": 0, "skipped": 0, "failed": 0, "total_bytes": 0}

    # Select years
    if args.years:
        selected_years = [str(y) for y in args.years]
        # Validate against available
        for y in selected_years:
            if y not in available_years:
                print(f"  WARNING: FY{y} not found on Comptroller page "
                      f"(available: {', '.join(sorted(available_years.keys()))})")
    else:
        selected_years = sorted(available_years.keys(), reverse=True)

    print(f"  Fiscal years: {', '.join(f'FY{y}' for y in selected_years)}", flush=True)

    # Select sources
    if args.sources:
        if "all" in [s.lower() for s in args.sources]:
            selected_sources = list(ALL_SOURCES)
        else:
            selected_sources = []
            for s in args.sources:
                s_lower = s.lower().replace("_", "-")
                if s_lower in ALL_SOURCES:
                    selected_sources.append(s_lower)
                else:
                    print(f"  WARNING: Unknown source '{s}'. "
                          f"Available: {', '.join(ALL_SOURCES)}")
    else:
        # Default: comptroller only (fastest, most reliable)
        selected_sources = ["comptroller"]

    print(f"  Sources: {', '.join(selected_sources)}", flush=True)

    # Discover files
    all_files: dict[str, dict[str, list[dict]]] = {}
    browser_labels: set[str] = set()

    for year in selected_years:
        all_files[year] = {}
        for source in selected_sources:
            if source == "comptroller":
                if year not in available_years:
                    continue
                url = available_years[year]
                files = discover_comptroller_files(session, year, url)
            else:
                discoverer = SOURCE_DISCOVERERS.get(source)
                if discoverer is None:
                    continue
                files = discoverer(session, year)

            # FY validation: filter out misrouted files
            pre_count = len(files)
            files = [f for f in files if validate_fy_match(f["filename"], year)]
            fy_dropped = pre_count - len(files)
            if fy_dropped:
                print(f"  [FY FILTER] {source} FY{year}: dropped {fy_dropped} "
                      f"file(s) with mismatched fiscal year in filename")

            label = (SERVICE_PAGE_TEMPLATES[source]["label"]
                     if source != "comptroller" else "Comptroller")
            all_files[year][label] = files

            if _is_browser_source(source):
                browser_labels.add(label)

            _time.sleep(args.download_delay)

    # Cross-source deduplication
    dedup_stats = deduplicate_across_sources(all_files, output_dir=docs_dir)
    dedup_total = dedup_stats.get("removed", 0) + dedup_stats.get("disk_dedup", 0)
    if dedup_total:
        print(f"  Deduplicated: {dedup_total} file(s)", flush=True)

    # Count total files
    total_discovered = sum(
        len(files) for year_sources in all_files.values()
        for files in year_sources.values()
    )
    print(f"  Discovered {total_discovered} file(s) to download", flush=True)

    if total_discovered == 0:
        return {"downloaded": 0, "skipped": 0, "failed": 0, "total_bytes": 0}

    # Write manifest
    manifest_path = docs_dir / "manifest.json"
    write_manifest(docs_dir, all_files, manifest_path)

    # Download
    summary = download_all(
        all_files,
        docs_dir,
        browser_labels,
        overwrite=args.overwrite_downloads,
        delay=args.download_delay,
        extract_zips=args.extract_zips,
        use_gui=False,
        manifest_path=manifest_path,
        workers=args.download_workers,
    )

    # Cleanup browser if used
    try:
        _close_browser()
    except Exception:
        pass

    return summary


def _download_cmd_fallback(args: argparse.Namespace) -> list[str]:
    """Build a subprocess command for the downloader (fallback)."""
    cmd = [PYTHON, str(STEP_DOWNLOAD), "--no-gui"]
    if args.years:
        cmd += ["--years"] + [str(y) for y in args.years]
    if args.sources:
        cmd += ["--sources"] + args.sources
    if args.overwrite_downloads:
        cmd.append("--overwrite")
    if args.extract_zips:
        cmd.append("--extract-zips")
    cmd += ["--workers", str(args.download_workers)]
    cmd += ["--delay", str(args.download_delay)]
    return cmd


# ── Main ──────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    # Configure logging so pipeline modules (builder, enricher, validator, staging)
    # emit visible status messages instead of being silently swallowed.
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        force=True,
    )

    # Reset global state for testability
    _completed_steps.clear()
    _stop_event.clear()

    # ── Initialise pipeline logger ───────────────────────────────────────
    pl = PipelineLogger(logs_dir=args.logs_dir)
    pl.args_dict = {
        k: v for k, v in vars(args).items()
        if v is not None and v is not False
    }

    # ── Graceful shutdown via Ctrl+C ──────────────────────────────────────
    def _sigint_handler(sig: int, frame: Any) -> None:
        if not _stop_event.is_set():
            print(
                "\n\n  Keyboard interrupt — finishing current operation and shutting down...",
                flush=True,
            )
            _stop_event.set()
        else:
            print("\n  Force-quitting...", flush=True)
            sys.exit(1)

    signal.signal(signal.SIGINT, _sigint_handler)

    pipeline_start = time.monotonic()
    pl.pipeline_start = pipeline_start
    use_staging = args.use_staging or args.stage_only or args.load_only
    db_path = Path(args.db)
    docs_dir = Path(args.docs) if args.docs else Path("DoD_Budget_Documents")
    staging_dir = Path(args.staging_dir)

    # ── Print config summary ──────────────────────────────────────────────
    print("\nDoD Budget Pipeline")
    print(f"  Database : {db_path}")
    print(f"  Docs dir : {docs_dir}")
    print(f"  Rebuild  : {'yes (full)' if args.rebuild else 'no (incremental)'}")

    # Download summary
    if args.repair_only:
        print(f"  Mode     : repair-only")
    elif not args.skip_download:
        dl_detail = "yes"
        if args.years:
            dl_detail += f" [years: {' '.join(str(y) for y in args.years)}]"
        if args.sources:
            dl_detail += f" [sources: {' '.join(args.sources)}]"
        print(f"  Download : {dl_detail}")
    else:
        print(f"  Download : skip")

    if use_staging and not args.repair_only:
        print(f"  Staging  : {staging_dir}")
        if args.stage_only:
            print(f"  Mode     : stage-only (Phase 1)")
        elif args.load_only:
            print(f"  Mode     : load-only (Phase 2)")
        else:
            print(f"  Mode     : full staging (Phase 1 + 2)")

    print(f"  Repair   : {'skip' if args.skip_repair else 'yes'}")

    validate_mode = " [pedantic]" if args.pedantic else " [strict]" if args.strict else ""
    print(
        f"  Validate : {'skip' if args.skip_validate or args.repair_only else 'yes'}"
        + validate_mode
        + (" [+report]" if args.report else "")
    )
    print(
        f"  Enrich   : {'skip' if args.skip_enrich or args.repair_only else 'yes'}"
        + (f" [phases {args.enrich_phases}]" if args.enrich_phases else "")
        + (" [+LLM]" if args.with_llm else "")
    )
    print(f"  Rollback : {'disabled' if args.no_rollback else 'enabled'}")
    print(f"  Logs     : {pl.run_dir}")

    # ── Repair-only mode ─────────────────────────────────────────────────
    if args.repair_only:
        from repair_database import repair

        repair_report = pl.start_step("repair")
        ok, repair_result = _run_step(
            "Repair database (repair-only mode)",
            repair,
            db_path=db_path,
        )
        if not ok:
            repair_report.status = "failed"
            repair_report.add_error("repair() raised an exception")
            pl.finish_step("repair", repair_report)
            print("\nRepair failed.", flush=True)
            _finalize_pipeline(pl, 1)
            return 1

        _build_report_from_repair(repair_report, repair_result)
        repair_report.status = "completed"
        pl.finish_step("repair", repair_report)

        total = time.monotonic() - pipeline_start
        _banner(f"Repair complete -- {total:.1f}s total")
        print(f"Database: {db_path.resolve()}", flush=True)
        _finalize_pipeline(pl, 0)
        return 0

    # ── Step 1 / 5: Download (default ON, skip with --skip-download) ─────
    if not args.skip_download:
        dl_report = pl.start_step("download")

        # Try direct Python import; fall back to subprocess if unavailable
        try:
            ok, dl_result = _run_step(
                "Step 1 / 5 -- Download documents",
                _run_download,
                args, docs_dir,
            )
            if not ok:
                dl_report.status = "failed"
                dl_report.add_error("Download step raised an exception")
                pl.finish_step("download", dl_report)
                print("\nPipeline aborted: download step failed.", flush=True)
                _finalize_pipeline(pl, 1)
                return 1

            _build_report_from_download(dl_report, dl_result)
            dl_report.status = "completed"
            pl.finish_step("download", dl_report)

            if dl_result:
                print(f"  Downloaded: {dl_result.get('downloaded', 0)}, "
                      f"Skipped: {dl_result.get('skipped', 0)}, "
                      f"Failed: {dl_result.get('failed', 0)}", flush=True)

        except ImportError as imp_err:
            # Fallback: run downloader as subprocess
            print(f"  Direct download import failed ({imp_err}), "
                  f"falling back to subprocess...", flush=True)
            rc = _run_subprocess(
                "Step 1 / 5 -- Download documents (subprocess)",
                _download_cmd_fallback(args),
            )
            if rc != 0:
                dl_report.status = "failed"
                dl_report.add_error(f"Download subprocess exited with code {rc}")
                pl.finish_step("download", dl_report)
                print(f"\nPipeline aborted: download step failed (exit {rc}).", flush=True)
                _finalize_pipeline(pl, rc)
                return rc
            dl_report.status = "completed"
            pl.finish_step("download", dl_report)

        if _check_stopped("download"):
            _finalize_pipeline(pl, 0)
            return 0
    else:
        print("\n[Step 1 / 5 -- Download documents] SKIPPED (--skip-download)", flush=True)
        pl.record_user_skip("download", "User passed --skip-download")

    # ── Step 2 / 5: Build or Stage+Load ──────────────────────────────────
    backup = None
    if not args.no_rollback:
        backup = _backup_db(db_path)

    if use_staging:
        # Staging path: parse -> Parquet -> SQLite
        from pipeline.staging import stage_all_files, load_staging_to_db

        if not args.load_only:
            stage_report = pl.start_step("stage")
            ok, stage_summary = _run_step(
                "Step 2a / 5 -- Stage files to Parquet",
                stage_all_files,
                docs_dir=docs_dir,
                staging_dir=staging_dir,
                workers=args.workers or 0,
                force=args.rebuild,
                pdf_timeout=args.pdf_timeout,
                progress_callback=_staging_progress,
                stop_event=_stop_event,
            )
            if not ok:
                stage_report.status = "failed"
                stage_report.add_error("stage_all_files raised an exception")
                pl.finish_step("stage", stage_report)
                _rollback_db(db_path, backup) if not args.no_rollback else None
                print("\nPipeline aborted: staging step failed.", flush=True)
                _finalize_pipeline(pl, 1)
                return 1

            _build_report_from_staging(stage_report, stage_summary)
            stage_report.status = "completed"
            pl.finish_step("stage", stage_report)

            if stage_summary:
                print(f"  Staged: {stage_summary.get('staged_count', 0)} files, "
                      f"Skipped: {stage_summary.get('skipped_count', 0)}, "
                      f"Errors: {stage_summary.get('error_count', 0)}")

        if args.stage_only:
            total = time.monotonic() - pipeline_start
            _banner(f"Staging complete -- {total:.1f}s total")
            print(f"Staged data in: {staging_dir.resolve()}", flush=True)
            _finalize_pipeline(pl, 0)
            return 0

        load_report = pl.start_step("load")
        ok, load_summary = _run_step(
            "Step 2b / 5 -- Load Parquet into SQLite",
            load_staging_to_db,
            staging_dir=staging_dir,
            db_path=db_path,
            rebuild=args.rebuild,
            progress_callback=_staging_progress,
            stop_event=_stop_event,
        )
        if not ok:
            load_report.status = "failed"
            load_report.add_error("load_staging_to_db raised an exception")
            pl.finish_step("load", load_report)
            if not args.no_rollback:
                _rollback_db(db_path, backup)
            print("\nPipeline aborted: load step failed.", flush=True)
            _finalize_pipeline(pl, 1)
            return 1

        _build_report_from_load(load_report, load_summary)
        load_report.status = "completed"
        pl.finish_step("load", load_report)

        if load_summary:
            print(f"  Rows: {load_summary.get('total_rows', 0):,}, "
                  f"PDF pages: {load_summary.get('total_pages', 0):,}")

    else:
        # Direct build path: Excel/PDF -> SQLite
        from pipeline.builder import build_database

        build_report = pl.start_step("build")

        build_kwargs: dict[str, Any] = {
            "docs_dir": docs_dir,
            "db_path": db_path,
            "rebuild": args.rebuild,
            "resume": args.resume,
            "workers": args.workers or 0,
            "pdf_timeout": args.pdf_timeout,
            "progress_callback": _build_progress,
            "stop_event": _stop_event,
            # Skip the builder's internal quality report when validation will
            # run as a separate pipeline step (Step 3), avoiding ~50s duplicate.
            "skip_quality_report": not args.skip_validate,
        }
        if args.checkpoint_interval is not None:
            build_kwargs["checkpoint_interval"] = args.checkpoint_interval

        ok, build_result = _run_step(
            "Step 2 / 5 -- Build database",
            build_database,
            **build_kwargs,
        )
        if not ok:
            build_report.status = "failed"
            build_report.add_error("build_database raised an exception")
            pl.finish_step("build", build_report)
            if not args.no_rollback:
                _rollback_db(db_path, backup)
            print("\nPipeline aborted: build step failed.", flush=True)
            _finalize_pipeline(pl, 1)
            return 1

        _build_report_from_builder(build_report, build_result)
        build_report.status = "completed"
        pl.finish_step("build", build_report)

    if _check_stopped("build"):
        _cleanup_backup(backup)
        _finalize_pipeline(pl, 0)
        return 0

    # ── Step 3 / 5: Repair ───────────────────────────────────────────────
    if not args.skip_repair:
        from repair_database import repair

        repair_report = pl.start_step("repair")
        ok, repair_result = _run_step(
            "Step 3 / 5 -- Repair database",
            repair,
            db_path=db_path,
        )
        if not ok:
            repair_report.status = "failed"
            repair_report.add_error("repair() raised an exception")
            pl.finish_step("repair", repair_report)
            # Repair failure is non-fatal — continue the pipeline
            print("\nRepair step failed -- continuing pipeline.", flush=True)
        else:
            _build_report_from_repair(repair_report, repair_result)
            repair_report.status = "completed"
            pl.finish_step("repair", repair_report)

            if repair_result:
                print(f"  Org normalized: {repair_result.get('org_normalized', 0):,}, "
                      f"Approp backfilled: {repair_result.get('approp_backfilled', 0):,}",
                      flush=True)
    else:
        print("\n[Step 2 / 5 -- Repair database] SKIPPED (--skip-repair)", flush=True)
        pl.record_user_skip("repair", "User passed --skip-repair")

    if _check_stopped("repair"):
        _cleanup_backup(backup)
        _finalize_pipeline(pl, 0)
        return 0

    # ── Step 4 / 5: Validate ─────────────────────────────────────────────
    if not args.skip_validate:
        from pipeline.validator import validate_all

        val_report = pl.start_step("validate")

        ok, val_summary = _run_step(
            "Step 4 / 5 -- Validate database",
            validate_all,
            db_path=db_path,
            strict=args.strict,
            pedantic=args.pedantic,
            stop_event=_stop_event,
        )

        if ok and val_summary:
            _build_report_from_validator(val_report, val_summary)
            exit_code = val_summary.get("exit_code", 0)
            warnings = val_summary.get("total_warnings", 0)
            failures = val_summary.get("total_failures", 0)
            print(f"  Checks: {val_summary.get('total_checks', 0)}, "
                  f"Warnings: {warnings}, Failures: {failures}")

            if exit_code != 0:
                mode = "pedantic" if args.pedantic else "strict"
                val_report.status = "failed"
                pl.finish_step("validate", val_report)
                print(
                    f"\nPipeline aborted: validation failed.\n"
                    f"Re-run without --{mode} to continue past issues.",
                    flush=True,
                )
                _finalize_pipeline(pl, 1)
                return 1

            if warnings > 0:
                print(
                    "\nValidation reported warnings -- continuing pipeline.\n"
                    "Use --strict to fail on errors, --pedantic to fail on warnings.",
                    flush=True,
                )

        if not ok:
            val_report.status = "failed"
            val_report.add_error("validate_all raised an exception")
            print("\nValidation step raised an exception -- continuing pipeline.", flush=True)

        val_report.status = val_report.status if val_report.status == "failed" else "completed"
        pl.finish_step("validate", val_report)

        # Generate quality report if requested
        if args.report:
            from pipeline.validator import generate_quality_report

            report_path = Path(args.report_path)
            ok_report, _ = _run_step(
                "Step 3b / 5 -- Generate quality report",
                generate_quality_report,
                db_path=db_path,
                output_path=report_path,
                print_console=True,
            )
            if ok_report:
                print(f"  Report: {report_path.resolve()}")
    else:
        print("\n[Step 4 / 5 -- Validate database] SKIPPED (--skip-validate)", flush=True)
        pl.record_user_skip("validate", "User passed --skip-validate")

    if _check_stopped("validate"):
        _cleanup_backup(backup)
        _finalize_pipeline(pl, 0)
        return 0

    # ── Step 5 / 5: Enrich ───────────────────────────────────────────────
    if not args.skip_enrich:
        from pipeline.enricher import enrich

        enrich_report = pl.start_step("enrich")

        # Parse enrichment phases
        if args.enrich_phases:
            phases = {int(p.strip()) for p in args.enrich_phases.split(",")}
        else:
            phases = {1, 2, 3, 4, 5}

        ok, enrich_result = _run_step(
            "Step 5 / 5 -- Enrich database",
            enrich,
            db_path=db_path,
            phases=phases,
            with_llm=args.with_llm,
            rebuild=args.rebuild_enrich or args.rebuild,
            stop_event=_stop_event,
        )
        if not ok:
            enrich_report.status = "failed"
            enrich_report.add_error("enrich() raised an exception")
            pl.finish_step("enrich", enrich_report)
            print(
                "\nPipeline aborted: enrichment step failed.",
                flush=True,
            )
            _finalize_pipeline(pl, 1)
            return 1

        _build_report_from_enricher(enrich_report, enrich_result)
        enrich_report.status = "completed"
        pl.finish_step("enrich", enrich_report)
    else:
        print("\n[Step 5 / 5 -- Enrich database] SKIPPED (--skip-enrich)", flush=True)
        pl.record_user_skip("enrich", "User passed --skip-enrich")

    # ── Done ─────────────────────────────────────────────────────────────
    _cleanup_backup(backup)

    total = time.monotonic() - pipeline_start
    _banner(f"Pipeline complete -- {total:.1f}s total")
    print(f"Database ready: {db_path.resolve()}", flush=True)

    _finalize_pipeline(pl, 0)
    return 0


def _finalize_pipeline(pl: PipelineLogger, exit_code: int) -> None:
    """Write run summary JSON, append to the cross-run ledger, and clean up."""
    # Always clear stale progress file on any exit (success, failure, interrupt)
    _clear_progress()

    summary_path = pl.write_summary()

    from pipeline.run_ledger import append_to_ledger
    ledger_path = append_to_ledger(pl, exit_code)

    print(f"\n  Run logs : {pl.run_dir}", flush=True)
    print(f"  Summary  : {summary_path}", flush=True)
    print(f"  Ledger   : {ledger_path}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
