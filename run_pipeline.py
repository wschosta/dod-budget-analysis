"""
Full pipeline runner -- downloads, builds, validates, and enriches the DoD budget database.

Steps (in order):
  0. dod_budget_downloader.py  -- download budget documents (optional, --download)
  1. build / stage+load        -- ingest Excel + PDF source files into SQLite
  2. validate_budget_data      -- QA checks against the populated DB
  3. enrich_budget_db          -- populate pe_index, pe_descriptions,
                                  pe_tags, pe_lineage

Features:
  - Direct function imports for build/stage/validate/enrich (no subprocess overhead)
  - Automatic DB backup before build; rollback on failure
  - JSON progress file for external monitoring
  - Download step via subprocess (Playwright deps are heavy/optional)

Usage:
    python run_pipeline.py                        # full run, incremental
    python run_pipeline.py --rebuild              # full rebuild from scratch
    python run_pipeline.py --download --years 2026 --sources all  # include download
    python run_pipeline.py --use-staging          # use Parquet staging layer
    python run_pipeline.py --report               # generate data_quality_report.json
    python run_pipeline.py --skip-validate        # skip validation step
    python run_pipeline.py --skip-enrich          # stop after validation
    python run_pipeline.py --no-rollback          # disable automatic rollback
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


HERE = Path(__file__).resolve().parent

# Download step uses subprocess (heavy optional deps: Playwright, GUI)
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
    """Restore the database from backup after a failed build."""
    if backup and backup.exists():
        shutil.copy2(backup, db_path)
        print(f"  Database restored from {backup}", flush=True)
        return True
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


# ── Argument parser ───────────────────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Run the full DoD budget pipeline: "
            "[download] -> build/stage -> validate -> enrich"
        ),
    )

    # Shared
    p.add_argument(
        "--db", default="dod_budget.sqlite",
        help="Database path (default: dod_budget.sqlite)",
    )

    # Download options
    p.add_argument(
        "--download", action="store_true",
        help="Include document download step (runs dod_budget_downloader.py)",
    )
    p.add_argument(
        "--years", nargs="+", default=None, metavar="YEAR",
        help="Fiscal years to download (e.g., 2026 2025). Requires --download.",
    )
    p.add_argument(
        "--sources", nargs="+", default=None, metavar="SRC",
        help="Sources to download (e.g., all, comptroller, army). Requires --download.",
    )
    p.add_argument(
        "--skip-download", action="store_true",
        help="Skip the download step (even if --download is set)",
    )

    # Staging options
    p.add_argument(
        "--use-staging", action="store_true",
        help="Use Parquet staging layer (Stage -> Load -> Validate -> Enrich)",
    )
    p.add_argument(
        "--staging-dir", default="staging",
        help="Staging directory for Parquet files (default: staging)",
    )
    p.add_argument(
        "--stage-only", action="store_true",
        help="Only run staging (Phase 1: parse -> Parquet); skip DB build",
    )
    p.add_argument(
        "--load-only", action="store_true",
        help="Only run load (Phase 2: Parquet -> SQLite); skip file parsing",
    )

    # Build options
    p.add_argument(
        "--docs", default=None,
        help="Documents directory (default: DoD_Budget_Documents)",
    )
    p.add_argument(
        "--rebuild", action="store_true",
        help="Force full rebuild of the database",
    )
    p.add_argument(
        "--resume", action="store_true",
        help="Resume build from last checkpoint",
    )
    p.add_argument(
        "--workers", type=int, default=None,
        help="Parallel PDF workers (default: auto-detect CPU count)",
    )
    p.add_argument(
        "--checkpoint-interval", type=int, default=None, metavar="N",
        help="Checkpoint every N files (default: 10)",
    )
    p.add_argument(
        "--pdf-timeout", type=int, default=30, metavar="SECS",
        help="Seconds per PDF page table extraction (default: 30)",
    )

    # Validate options
    p.add_argument(
        "--skip-validate", action="store_true",
        help="Skip the validation step",
    )
    p.add_argument(
        "--strict", action="store_true",
        help="Abort the pipeline on validation failures",
    )
    p.add_argument(
        "--pedantic", action="store_true",
        help="Abort the pipeline on any validation warnings or failures",
    )
    p.add_argument(
        "--report", action="store_true",
        help="Generate a data quality report after validation",
    )
    p.add_argument(
        "--report-path", default="data_quality_report.json", metavar="PATH",
        help="Path for the quality report (default: data_quality_report.json)",
    )

    # Enrich options
    p.add_argument(
        "--skip-enrich", action="store_true",
        help="Skip the enrichment step",
    )
    p.add_argument(
        "--with-llm", action="store_true",
        help="Enable LLM-based tagging (requires ANTHROPIC_API_KEY)",
    )
    p.add_argument(
        "--enrich-phases", default=None, metavar="PHASES",
        help="Comma-separated enrichment phases to run (default: 1,2,3,4,5)",
    )
    p.add_argument(
        "--rebuild-enrich", action="store_true",
        help="Drop and rebuild enrichment tables only (not the full DB)",
    )

    # Rollback options
    p.add_argument(
        "--no-rollback", action="store_true",
        help="Skip automatic database rollback on build failure",
    )

    return p.parse_args(argv)


# ── Download step (subprocess) ────────────────────────────────────────────────


def _download_cmd(args: argparse.Namespace) -> list[str]:
    """Build command for the downloader."""
    cmd = [PYTHON, str(STEP_DOWNLOAD), "--no-gui"]
    if args.years:
        cmd += ["--years"] + [str(y) for y in args.years]
    if args.sources:
        cmd += ["--sources"] + args.sources
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
    use_staging = args.use_staging or args.stage_only or args.load_only
    db_path = Path(args.db)
    docs_dir = Path(args.docs) if args.docs else Path("DoD_Budget_Documents")
    staging_dir = Path(args.staging_dir)

    # ── Print config summary ──────────────────────────────────────────────
    print("\nDoD Budget Pipeline")
    print(f"  Database : {db_path}")
    print(f"  Docs dir : {docs_dir}")
    print(f"  Rebuild  : {'yes (full)' if args.rebuild else 'no (incremental)'}")
    if args.download and not args.skip_download:
        print(f"  Download : yes"
              + (f" [years: {' '.join(str(y) for y in args.years)}]" if args.years else "")
              + (f" [sources: {' '.join(args.sources)}]" if args.sources else ""))
    if use_staging:
        print(f"  Staging  : {staging_dir}")
        if args.stage_only:
            print(f"  Mode     : stage-only (Phase 1)")
        elif args.load_only:
            print(f"  Mode     : load-only (Phase 2)")
        else:
            print(f"  Mode     : full staging (Phase 1 + 2)")
    validate_mode = " [pedantic]" if args.pedantic else " [strict]" if args.strict else ""
    print(
        f"  Validate : {'skip' if args.skip_validate else 'yes'}"
        + validate_mode
        + (" [+report]" if args.report else "")
    )
    print(
        f"  Enrich   : {'skip' if args.skip_enrich else 'yes'}"
        + (f" [phases {args.enrich_phases}]" if args.enrich_phases else "")
        + (" [+LLM]" if args.with_llm else "")
    )
    print(f"  Rollback : {'disabled' if args.no_rollback else 'enabled'}")

    # ── Step 0: Download (optional, subprocess) ──────────────────────────
    if args.download and not args.skip_download:
        rc = _run_subprocess("Step 0 / 4 -- Download documents", _download_cmd(args))
        if rc != 0:
            print(f"\nPipeline aborted: download step failed (exit {rc}).", flush=True)
            return rc
        if _check_stopped("download"):
            return 0

    # ── Step 1: Build or Stage+Load ──────────────────────────────────────
    backup = None
    if not args.no_rollback:
        backup = _backup_db(db_path)

    if use_staging:
        # Staging path: parse -> Parquet -> SQLite
        from pipeline.staging import stage_all_files, load_staging_to_db

        if not args.load_only:
            ok, stage_summary = _run_step(
                "Step 1a / 4 -- Stage files to Parquet",
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
                _rollback_db(db_path, backup) if not args.no_rollback else None
                print("\nPipeline aborted: staging step failed.", flush=True)
                return 1

            if stage_summary:
                print(f"  Staged: {stage_summary.get('staged_count', 0)} files, "
                      f"Skipped: {stage_summary.get('skipped_count', 0)}, "
                      f"Errors: {stage_summary.get('error_count', 0)}")

        if args.stage_only:
            total = time.monotonic() - pipeline_start
            _banner(f"Staging complete -- {total:.1f}s total")
            print(f"Staged data in: {staging_dir.resolve()}", flush=True)
            _clear_progress()
            return 0

        ok, load_summary = _run_step(
            "Step 1b / 4 -- Load Parquet into SQLite",
            load_staging_to_db,
            staging_dir=staging_dir,
            db_path=db_path,
            rebuild=args.rebuild,
            progress_callback=_staging_progress,
            stop_event=_stop_event,
        )
        if not ok:
            if not args.no_rollback:
                _rollback_db(db_path, backup)
            print("\nPipeline aborted: load step failed.", flush=True)
            return 1

        if load_summary:
            print(f"  Rows: {load_summary.get('total_rows', 0):,}, "
                  f"PDF pages: {load_summary.get('total_pages', 0):,}")

    else:
        # Direct build path: Excel/PDF -> SQLite
        from pipeline.builder import build_database

        build_kwargs: dict[str, Any] = {
            "docs_dir": docs_dir,
            "db_path": db_path,
            "rebuild": args.rebuild,
            "resume": args.resume,
            "workers": args.workers or 0,
            "pdf_timeout": args.pdf_timeout,
            "progress_callback": _build_progress,
            "stop_event": _stop_event,
        }
        if args.checkpoint_interval is not None:
            build_kwargs["checkpoint_interval"] = args.checkpoint_interval

        ok, build_result = _run_step(
            "Step 1 / 4 -- Build database",
            build_database,
            **build_kwargs,
        )
        if not ok:
            if not args.no_rollback:
                _rollback_db(db_path, backup)
            print("\nPipeline aborted: build step failed.", flush=True)
            return 1

    if _check_stopped("build"):
        _cleanup_backup(backup)
        return 0

    # ── Step 2: Validate ─────────────────────────────────────────────────
    if not args.skip_validate:
        from pipeline.validator import validate_all

        ok, val_summary = _run_step(
            "Step 2 / 4 -- Validate database",
            validate_all,
            db_path=db_path,
            strict=args.strict,
            pedantic=args.pedantic,
            stop_event=_stop_event,
        )

        if ok and val_summary:
            exit_code = val_summary.get("exit_code", 0)
            warnings = val_summary.get("total_warnings", 0)
            failures = val_summary.get("total_failures", 0)
            print(f"  Checks: {val_summary.get('total_checks', 0)}, "
                  f"Warnings: {warnings}, Failures: {failures}")

            if exit_code != 0:
                mode = "pedantic" if args.pedantic else "strict"
                print(
                    f"\nPipeline aborted: validation failed.\n"
                    f"Re-run without --{mode} to continue past issues.",
                    flush=True,
                )
                return 1

            if warnings > 0:
                print(
                    "\nValidation reported warnings -- continuing pipeline.\n"
                    "Use --strict to fail on errors, --pedantic to fail on warnings.",
                    flush=True,
                )

        if not ok:
            print("\nValidation step raised an exception -- continuing pipeline.", flush=True)

        # Generate quality report if requested
        if args.report:
            from pipeline.validator import generate_quality_report

            report_path = Path(args.report_path)
            ok_report, _ = _run_step(
                "Step 2b / 4 -- Generate quality report",
                generate_quality_report,
                db_path=db_path,
                output_path=report_path,
                print_console=True,
            )
            if ok_report:
                print(f"  Report: {report_path.resolve()}")
    else:
        print("\n[Step 2 / 4 -- Validate database] SKIPPED", flush=True)

    if _check_stopped("validate"):
        _cleanup_backup(backup)
        return 0

    # ── Step 3: Enrich ───────────────────────────────────────────────────
    if not args.skip_enrich:
        from pipeline.enricher import enrich

        # Parse enrichment phases
        if args.enrich_phases:
            phases = {int(p.strip()) for p in args.enrich_phases.split(",")}
        else:
            phases = {1, 2, 3, 4, 5}

        ok, _ = _run_step(
            "Step 3 / 4 -- Enrich database",
            enrich,
            db_path=db_path,
            phases=phases,
            with_llm=args.with_llm,
            rebuild=args.rebuild_enrich or args.rebuild,
            stop_event=_stop_event,
        )
        if not ok:
            print(
                "\nPipeline aborted: enrichment step failed.",
                flush=True,
            )
            return 1
    else:
        print("\n[Step 3 / 4 -- Enrich database] SKIPPED", flush=True)

    # ── Done ─────────────────────────────────────────────────────────────
    _cleanup_backup(backup)
    _clear_progress()

    total = time.monotonic() - pipeline_start
    _banner(f"Pipeline complete -- {total:.1f}s total")
    print(f"Database ready: {db_path.resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
