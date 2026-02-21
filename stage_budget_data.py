"""
Parquet Staging CLI for DoD Budget Pipeline

Stages parsed Excel/PDF data as Parquet files, or loads staged data into SQLite.

Usage:
    # Stage all files (parse -> Parquet)
    python stage_budget_data.py --docs-dir DoD_Budget_Documents --staging-dir staging

    # Load staged data into SQLite (Parquet -> SQLite)
    python stage_budget_data.py --load-only --staging-dir staging --db dod_budget.sqlite

    # Both: stage then load
    python stage_budget_data.py --docs-dir DoD_Budget_Documents --staging-dir staging --db dod_budget.sqlite

    # Force re-stage everything
    python stage_budget_data.py --docs-dir DoD_Budget_Documents --staging-dir staging --force

    # Preview what would be staged (no parsing)
    python stage_budget_data.py --docs-dir DoD_Budget_Documents --staging-dir staging --dry-run
"""

import argparse
import signal
import sys
from pathlib import Path


def main():
    """Parse arguments and run staging pipeline."""
    parser = argparse.ArgumentParser(
        description="Stage DoD budget data as Parquet, or load staged data into SQLite"
    )
    parser.add_argument(
        "--docs-dir", type=Path, default=Path("DoD_Budget_Documents"),
        help="Path to DoD_Budget_Documents directory (default: DoD_Budget_Documents)"
    )
    parser.add_argument(
        "--staging-dir", type=Path, default=Path("staging"),
        help="Path to staging output directory (default: staging)"
    )
    parser.add_argument(
        "--db", type=Path, default=Path("dod_budget.sqlite"),
        help="Database path for --load-only (default: dod_budget.sqlite)"
    )
    parser.add_argument(
        "--workers", type=int, default=0, metavar="N",
        help="Parallel workers (0 = auto-detect, 1 = sequential)"
    )
    parser.add_argument(
        "--pdf-timeout", type=int, default=30, metavar="SECS",
        help="Seconds per PDF page table extraction (default: 30)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force re-stage all files regardless of change detection"
    )
    parser.add_argument(
        "--stage-only", action="store_true",
        help="Only run Phase 1 (parse -> Parquet); skip database loading"
    )
    parser.add_argument(
        "--load-only", action="store_true",
        help="Only run Phase 2 (Parquet -> SQLite); skip file parsing"
    )
    parser.add_argument(
        "--rebuild", action="store_true",
        help="Delete existing database before loading (Phase 2)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be staged without parsing any files"
    )

    args = parser.parse_args()

    if args.stage_only and args.load_only:
        print("ERROR: Cannot use both --stage-only and --load-only")
        sys.exit(1)

    from pipeline.staging import stage_all_files, load_staging_to_db, needs_restaging

    def _print_progress(phase, current, total, detail=""):
        if total > 0:
            pct = current / total * 100
            print(f"  [{phase}] {current}/{total} ({pct:.0f}%) {detail}")
        else:
            print(f"  [{phase}] {detail}")

    # ── Dry-run mode ──────────────────────────────────────────────────────
    if args.dry_run:
        docs_dir = args.docs_dir
        staging_dir = args.staging_dir
        if not docs_dir.exists():
            print(f"ERROR: Documents directory not found: {docs_dir}")
            sys.exit(1)

        xlsx_files = sorted(docs_dir.rglob("*.xlsx"))
        pdf_files = sorted(docs_dir.rglob("*.pdf"))
        total = len(xlsx_files) + len(pdf_files)

        need_stage_xlsx = [f for f in xlsx_files
                           if needs_restaging(f, staging_dir, "excel")]
        need_stage_pdf = [f for f in pdf_files
                          if needs_restaging(f, staging_dir, "pdf")]
        need_stage = len(need_stage_xlsx) + len(need_stage_pdf)
        skip = total - need_stage

        total_size = sum(f.stat().st_size for f in need_stage_xlsx + need_stage_pdf)

        print(f"\n{'='*60}")
        print("  DRY RUN: Staging preview (no files will be parsed)")
        print(f"{'='*60}")
        print(f"  Docs dir:       {docs_dir}")
        print(f"  Staging dir:    {staging_dir}")
        print(f"  Total files:    {total} ({len(xlsx_files)} Excel, {len(pdf_files)} PDF)")
        print(f"  Need staging:   {need_stage} ({len(need_stage_xlsx)} Excel, {len(need_stage_pdf)} PDF)")
        print(f"  Already staged: {skip}")
        print(f"  Disk to parse:  {total_size / (1024*1024):.1f} MB")

        if need_stage and need_stage <= 20:
            print(f"\n  Files to stage:")
            for f in need_stage_xlsx + need_stage_pdf:
                print(f"    - {f.relative_to(docs_dir)} ({f.stat().st_size / 1024:.0f} KB)")
        elif need_stage > 20:
            print(f"\n  First 20 files to stage:")
            for f in (need_stage_xlsx + need_stage_pdf)[:20]:
                print(f"    - {f.relative_to(docs_dir)} ({f.stat().st_size / 1024:.0f} KB)")
            print(f"    ... and {need_stage - 20} more")

        print(f"\nTo stage these files, run without --dry-run.")
        return

    # ── Phase 1: Stage ───────────────────────────────────────────────────
    if not args.load_only:
        print(f"\n{'='*60}")
        print("  PHASE 1: Staging files to Parquet")
        print(f"{'='*60}")
        print(f"  Docs dir:    {args.docs_dir}")
        print(f"  Staging dir: {args.staging_dir}")
        print(f"  Workers:     {args.workers or 'auto'}")
        print(f"  Force:       {args.force}")
        print()

        try:
            summary = stage_all_files(
                docs_dir=args.docs_dir,
                staging_dir=args.staging_dir,
                workers=args.workers,
                force=args.force,
                pdf_timeout=args.pdf_timeout,
                progress_callback=_print_progress,
            )
        except FileNotFoundError as e:
            print(f"ERROR: {e}")
            sys.exit(1)

        print(f"\n  Staging complete:")
        print(f"    Total files:  {summary['total_files']}")
        print(f"    Staged:       {summary['staged_count']}")
        print(f"    Skipped:      {summary['skipped_count']}")
        print(f"    Errors:       {summary['error_count']}")
        print(f"    FY columns:   {len(summary['excel_fy_columns'])}")
        print(f"    Elapsed:      {summary['elapsed_sec']}s")

        if summary['errors']:
            print(f"\n  Errors:")
            for err in summary['errors'][:20]:
                print(f"    - {err['file']}: {err['error']}")
            if len(summary['errors']) > 20:
                print(f"    ... and {len(summary['errors']) - 20} more")

    # ── Phase 2: Load ────────────────────────────────────────────────────
    if not args.stage_only:
        print(f"\n{'='*60}")
        print("  PHASE 2: Loading Parquet into SQLite")
        print(f"{'='*60}")
        print(f"  Staging dir: {args.staging_dir}")
        print(f"  Database:    {args.db}")
        print(f"  Rebuild:     {args.rebuild}")
        print()

        try:
            summary = load_staging_to_db(
                staging_dir=args.staging_dir,
                db_path=args.db,
                rebuild=args.rebuild,
                progress_callback=_print_progress,
            )
        except FileNotFoundError as e:
            print(f"ERROR: {e}")
            sys.exit(1)

        print(f"\n  Load complete:")
        print(f"    Budget rows: {summary['total_rows']:,}")
        print(f"    PDF pages:   {summary['total_pages']:,}")
        print(f"    FY columns:  {len(summary['fy_columns'])}")
        print(f"    Elapsed:     {summary['elapsed_sec']}s")

    print("\nDone.")


if __name__ == "__main__":
    main()
