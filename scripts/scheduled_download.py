#!/usr/bin/env python3
"""
Scheduled Download Pipeline Wrapper for dod_budget_downloader.py

This script wraps the downloader for unattended/scheduled execution (e.g., cron, CI).

Behavior:
  - Runs downloader with --years all --sources all --no-gui
  - Captures stdout/stderr to a timestamped log file
  - Exits with non-zero status if any downloads fail
  - Writes download manifest to {output_dir}/manifest.json

Usage:
  python scripts/scheduled_download.py [--output DoD_Budget_Documents]

See docs/TODO_1A4_automate_download_scheduling.md for full specification.
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def main():
    """Run the scheduled download pipeline."""
    parser = argparse.ArgumentParser(
        description="Scheduled download wrapper for DoD Budget Documents."
    )
    parser.add_argument(
        "--output", type=Path, default=Path("DoD_Budget_Documents"),
        help="Output directory for downloaded files (default: DoD_Budget_Documents)",
    )
    parser.add_argument(
        "--log-dir", type=Path, default=None,
        help="Directory for log files (default: {output}/logs/)",
    )
    args = parser.parse_args()

    # Create output directory if needed
    args.output.mkdir(parents=True, exist_ok=True)

    # Set up log directory
    log_dir = args.log_dir or (args.output / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create timestamped log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"download_{timestamp}.log"

    print(f"Starting scheduled download to {args.output.resolve()}")
    print(f"Logging to {log_file}")

    # Build downloader command
    downloader_path = Path(__file__).parent.parent / "dod_budget_downloader.py"
    cmd = [
        sys.executable,
        str(downloader_path),
        "--years", "all",
        "--sources", "all",
        "--output", str(args.output),
        "--no-gui",
    ]

    # Run downloader and capture output
    try:
        with open(log_file, "w", encoding="utf-8") as log_fh:
            result = subprocess.run(
                cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=3600,  # 1 hour timeout
            )

        print(f"Download completed with exit code {result.returncode}")

        # Check for manifest
        manifest_path = args.output / "manifest.json"
        if manifest_path.exists():
            print(f"Manifest written to {manifest_path}")

        # Exit with same code as downloader
        sys.exit(result.returncode)

    except subprocess.TimeoutExpired:
        print(f"ERROR: Download timed out after 1 hour", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
