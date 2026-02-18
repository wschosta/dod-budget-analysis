#!/usr/bin/env python3
"""
Scheduled download pipeline script for unattended budget document downloads.

Step 1.A4-b implementation: Imports and calls download_all() directly from
dod_budget_downloader for scheduled/CI execution without subprocess overhead.

Usage:
    python scripts/scheduled_download.py [--output DIR] [--years YEAR ...] \\
        [--sources SOURCE ...] [--log LOGFILE]

Exit codes:
    0 — all files downloaded or skipped successfully
    1 — one or more files failed, or a fatal error occurred
"""

import argparse
import sys
import traceback
from datetime import datetime
from pathlib import Path

# Ensure the project root is on sys.path so we can import the downloader
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def run_scheduled_download(
    output_dir: Path,
    years: list[str] | None = None,
    sources: list[str] | None = None,
    log_file: Path | None = None,
) -> int:
    """Run the downloader in unattended mode with logging and error tracking.

    Calls download_all() directly from dod_budget_downloader (1.A4-b) to
    avoid subprocess overhead and gain access to the structured summary dict.
    Writes a timestamped log entry recording the outcome.

    Args:
        output_dir: Root directory to write downloaded files into.
        years:      Fiscal years to download (``None`` or ``["all"]`` = all).
        sources:    Source keys to download (``None`` or ``["all"]`` = all).
        log_file:   Where to write the run log.  Defaults to a timestamped
                    file inside *output_dir*.

    Returns:
        0 on full success, 1 if any downloads failed or a fatal error occurred.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if log_file is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = output_dir / f"download_log_{stamp}.txt"
    else:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"Starting scheduled download → {output_dir}")
    print(f"Log: {log_file}")

    # Import the downloader components we need
    try:
        from dod_budget_downloader import (
            ALL_SOURCES,
            BROWSER_REQUIRED_SOURCES,
            SERVICE_PAGE_TEMPLATES,
            SOURCE_DISCOVERERS,
            _is_browser_source,
            discover_comptroller_files,
            discover_fiscal_years,
            download_all,
            get_session,
        )
    except ImportError as exc:
        msg = f"ERROR: Could not import dod_budget_downloader: {exc}\n"
        print(msg, end="", file=sys.stderr)
        log_file.write_text(
            f"=== Scheduled download FAILED {datetime.now().isoformat()} ===\n{msg}"
        )
        return 1

    start_time = datetime.now()
    log_lines: list[str] = [
        f"=== Scheduled download started {start_time.isoformat()} ===\n"
    ]

    def log(msg: str) -> None:
        print(msg)
        log_lines.append(msg + "\n")

    try:
        session = get_session()

        # ── Discover available fiscal years ───────────────────────────────────
        available_years = discover_fiscal_years(session)
        if not available_years:
            raise RuntimeError("Could not find any fiscal year links on the website.")

        # ── Select years ──────────────────────────────────────────────────────
        if years is None or "all" in [y.lower() for y in years]:
            selected_years = list(available_years.keys())
        else:
            selected_years = [y for y in years if y in available_years]
            missing = [y for y in years if y not in available_years]
            if missing:
                log(f"WARNING: Fiscal years not found: {', '.join(missing)}")
            if not selected_years:
                raise RuntimeError(f"None of the requested years are available: {years}")

        log(f"Years: {', '.join(f'FY{y}' for y in selected_years)}")

        # ── Select sources ────────────────────────────────────────────────────
        if sources is None or "all" in [s.lower() for s in (sources or [])]:
            selected_sources = list(ALL_SOURCES)
        else:
            normalised = [s.lower().replace("_", "-") for s in sources]
            selected_sources = [s for s in normalised if s in ALL_SOURCES]
            unknown = [s for s in normalised if s not in ALL_SOURCES]
            if unknown:
                log(f"WARNING: Unknown sources ignored: {', '.join(unknown)}")
            if not selected_sources:
                raise RuntimeError(f"No valid sources in: {sources}")

        log(f"Sources: {', '.join(selected_sources)}")

        # ── Discover files ────────────────────────────────────────────────────
        all_files: dict[str, dict[str, list[dict]]] = {}
        browser_labels: set[str] = set()

        for year in selected_years:
            all_files[year] = {}
            for source in selected_sources:
                if source == "comptroller":
                    files = discover_comptroller_files(session, year,
                                                       available_years[year])
                else:
                    files = SOURCE_DISCOVERERS[source](session, year)

                label = (SERVICE_PAGE_TEMPLATES[source]["label"]
                         if source != "comptroller" else "Comptroller")
                all_files[year][label] = files
                if _is_browser_source(source):
                    browser_labels.add(label)

        # ── Download ──────────────────────────────────────────────────────────
        summary = download_all(
            all_files,
            output_dir,
            browser_labels,
            use_gui=False,          # Always headless for scheduled runs (1.A4-d)
            manifest_path=output_dir / "manifest.json",
        )

        elapsed = (datetime.now() - start_time).total_seconds()
        result_line = (
            f"=== Complete: {summary['downloaded']} downloaded, "
            f"{summary['skipped']} skipped, {summary['failed']} failed "
            f"({elapsed:.0f}s) ==="
        )
        log(result_line)

        exit_code = 1 if summary["failed"] > 0 else 0
        if exit_code:
            print(f"WARN: {summary['failed']} file(s) failed — see log: {log_file}")
        else:
            print(f"OK: manifest → {output_dir / 'manifest.json'}")

    except Exception as exc:
        elapsed = (datetime.now() - start_time).total_seconds()
        error_block = (
            f"=== FATAL ERROR after {elapsed:.0f}s ===\n"
            f"{traceback.format_exc()}"
        )
        print(f"ERROR: {exc}", file=sys.stderr)
        log_lines.append(error_block)
        exit_code = 1

    # Write the accumulated log
    log_file.write_text("".join(log_lines), encoding="utf-8")
    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unattended scheduled download of DoD budget documents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # Download everything (all years, all sources)\n"
            "  python scripts/scheduled_download.py\n\n"
            "  # Download specific years from comptroller only\n"
            "  python scripts/scheduled_download.py --years 2026 2025 "
            "--sources comptroller\n"
        ),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("DoD_Budget_Documents"),
        help="Output directory for downloaded files (default: DoD_Budget_Documents)",
    )
    parser.add_argument(
        "--years", nargs="+", default=None,
        help='Fiscal years to download (e.g. 2026 2025) or "all". Default: all',
    )
    parser.add_argument(
        "--sources", nargs="+", default=None,
        help=(
            'Sources to download from: comptroller, defense-wide, army, navy, '
            'airforce, or "all". Default: all'
        ),
    )
    parser.add_argument(
        "--log", type=Path, default=None,
        help="Log file path (default: timestamped file in output directory)",
    )
    args = parser.parse_args()

    sys.exit(run_scheduled_download(args.output, args.years, args.sources, args.log))


if __name__ == "__main__":
    main()
