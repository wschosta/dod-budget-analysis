#!/usr/bin/env python3
"""
Scheduled download pipeline script for unattended budget document downloads.

Step 1.A4-a implementation: Wraps dod_budget_downloader.py for scheduled/cron execution.

Usage:
    python scripts/scheduled_download.py [--output DoD_Budget_Documents] [--log LOGFILE]

Behavior:
    - Downloads all budget documents (--years all --sources all)
    - Captures output to timestamped log file
    - Returns non-zero exit code on any failures
    - Generates manifest.json for downloaded files
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_scheduled_download(output_dir: Path, log_file: Path | None = None) -> int:
    """
    Run the downloader in unattended mode with logging and error tracking.

    Args:
        output_dir: Where to store downloaded files
        log_file: Optional log file path (defaults to timestamped file)

    Returns:
        Exit code: 0 on success, 1 on failure
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create timestamped log file if not specified
    if log_file is None:
        log_file = output_dir / f"download_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    else:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"Starting scheduled download to {output_dir}")
    print(f"Log file: {log_file}")

    # Build downloader command
    script_path = Path(__file__).parent.parent / "dod_budget_downloader.py"
    cmd = [
        sys.executable,
        str(script_path),
        "--years", "all",
        "--sources", "all",
        "--output", str(output_dir),
        "--no-gui",  # Unattended mode
    ]

    try:
        # Run downloader and capture output
        with open(log_file, "w") as logf:
            result = subprocess.run(
                cmd,
                stdout=logf,
                stderr=subprocess.STDOUT,
                text=True,
            )

        # Log completion
        with open(log_file, "a") as logf:
            if result.returncode == 0:
                logf.write(f"\n[SUCCESS] Download completed at {datetime.now().isoformat()}\n")
                print(f"✓ Download completed successfully")
                print(f"  Output: {output_dir}")
                print(f"  Manifest: {output_dir / 'manifest.json'}")
                return 0
            else:
                logf.write(f"\n[FAILURE] Download failed with exit code {result.returncode}\n")
                print(f"✗ Download failed with exit code {result.returncode}")
                print(f"  See log: {log_file}")
                return 1

    except Exception as e:
        print(f"✗ Error running downloader: {e}")
        with open(log_file, "a") as logf:
            logf.write(f"\n[ERROR] {e}\n")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Unattended scheduled download of DoD budget documents"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("DoD_Budget_Documents"),
        help="Output directory for downloaded files (default: DoD_Budget_Documents)",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Log file path (default: timestamped file in output directory)",
    )
    args = parser.parse_args()

    exit_code = run_scheduled_download(args.output, args.log)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
