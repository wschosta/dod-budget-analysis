#!/usr/bin/env python3
"""
Data Refresh Workflow Script — Step 2.B4-a

Orchestrates the complete data refresh pipeline:
1. Download budget documents for specified fiscal year(s) and source(s)
2. Build/update the database incrementally
3. Run validation checks
4. Generate quality report

Usage:
    python refresh_data.py --years 2026                    # Refresh FY2026 (all sources)
    python refresh_data.py --years 2026 --sources army navy # FY2026 Army+Navy only
    python refresh_data.py --years 2025 2026 --sources all  # Multiple years
    python refresh_data.py --dry-run --years 2026           # Preview without downloading
    python refresh_data.py --help                           # Show full options
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


class RefreshWorkflow:
    """Orchestrates the complete data refresh pipeline."""

    def __init__(self, verbose=False, dry_run=False, workers=4):
        """Initialize workflow state.

        Args:
            verbose: If True, emit detailed stage output.
            dry_run: If True, log commands without executing them.
            workers: Number of concurrent HTTP download threads.
        """
        self.verbose = verbose
        self.dry_run = dry_run
        self.workers = workers
        self.start_time = None
        self.results = {}

    def log(self, msg: str, level="info"):
        """Print a timestamped log message."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if level == "info":
            print(f"[{timestamp}] {msg}")
        elif level == "warn":
            print(f"[{timestamp}] ⚠ WARNING: {msg}")
        elif level == "error":
            print(f"[{timestamp}] ✗ ERROR: {msg}")
        elif level == "ok":
            print(f"[{timestamp}] ✓ {msg}")
        elif level == "detail" and self.verbose:
            print(f"  → {msg}")

    def run_command(self, cmd: list, description: str) -> bool:
        """Run a shell command and return success status."""
        self.log(f"Starting: {description}")
        if self.dry_run:
            self.log(f"[DRY RUN] Would execute: {' '.join(cmd)}", "detail")
            return True

        try:
            result = subprocess.run(
                cmd,
                capture_output=False,
                text=True,
                timeout=3600,  # 1 hour timeout per stage
            )
            if result.returncode == 0:
                self.log(f"Completed: {description}", "ok")
                return True
            else:
                self.log(f"Failed: {description} (exit code {result.returncode})", "error")
                return False
        except subprocess.TimeoutExpired:
            self.log(f"Timeout: {description} exceeded 1 hour", "error")
            return False
        except Exception as e:
            self.log(f"Exception during {description}: {e}", "error")
            return False

    def stage_1_download(self, years: list, sources: list) -> bool:
        """Stage 1: Download budget documents."""
        self.log("=" * 60)
        self.log("STAGE 1: DOWNLOAD BUDGET DOCUMENTS")
        self.log("=" * 60)

        cmd = ["python", "dod_budget_downloader.py", "--no-gui",
               "--workers", str(self.workers)]
        if years:
            cmd.extend(["--years"] + [str(y) for y in years])
        if sources:
            cmd.extend(["--sources"] + sources)
        if self.verbose:
            cmd.append("--verbose")

        success = self.run_command(cmd, "Budget document download")
        self.results["download"] = "completed" if success else "failed"
        return success

    def stage_2_build(self) -> bool:
        """Stage 2: Build or update the database."""
        self.log("=" * 60)
        self.log("STAGE 2: BUILD DATABASE")
        self.log("=" * 60)

        # Use incremental mode (no --rebuild) to preserve existing data
        cmd = ["python", "build_budget_db.py"]
        if self.verbose:
            cmd.append("--verbose")

        success = self.run_command(cmd, "Database build/update")
        self.results["build"] = "completed" if success else "failed"
        return success

    def stage_3_validate(self) -> bool:
        """Stage 3: Run validation checks."""
        self.log("=" * 60)
        self.log("STAGE 3: VALIDATE DATABASE")
        self.log("=" * 60)

        cmd = ["python", "validate_budget_data.py"]
        if self.verbose:
            cmd.append("--verbose")

        success = self.run_command(cmd, "Data validation")
        self.results["validate"] = "completed" if success else "failed"
        return success

    def stage_4_report(self) -> bool:
        """Stage 4: Generate quality report."""
        self.log("=" * 60)
        self.log("STAGE 4: GENERATE QUALITY REPORT")
        self.log("=" * 60)

        try:
            # Gather stats from the database
            from pathlib import Path
            import sqlite3

            db_path = Path("dod_budget.sqlite")
            if not db_path.exists():
                self.log("Database not found; skipping report generation", "warn")
                self.results["report"] = "skipped"
                return False

            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            budget_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM budget_lines"
            ).fetchone()["cnt"]
            pdf_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM pdf_pages"
            ).fetchone()["cnt"]
            files_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM ingested_files"
            ).fetchone()["cnt"]

            # Generate report
            report = {
                "timestamp": datetime.now().isoformat(),
                "database_file": str(db_path),
                "database_size_mb": db_path.stat().st_size / (1024 * 1024),
                "statistics": {
                    "budget_lines": budget_count,
                    "pdf_pages": pdf_count,
                    "files_ingested": files_count,
                },
            }

            # Write report to file
            report_path = Path("refresh_report.json")
            with open(report_path, "w") as f:
                json.dump(report, f, indent=2)

            self.log(f"Quality report saved to {report_path}", "ok")
            self.results["report"] = "completed"
            conn.close()
            return True

        except Exception as e:
            self.log(f"Error generating report: {e}", "error")
            self.results["report"] = "failed"
            return False

    def run(self, years: list, sources: list) -> int:
        """Execute the complete refresh workflow."""
        self.start_time = time.time()

        self.log("=" * 60)
        self.log("DoD BUDGET DATA REFRESH WORKFLOW")
        self.log("=" * 60)
        self.log(f"Fiscal Years: {years if years else 'all'}")
        self.log(f"Sources: {sources if sources else 'all'}")
        self.log(f"Dry Run: {self.dry_run}")
        self.log("")

        # Execute stages
        success = True
        success = self.stage_1_download(years, sources) and success
        if not success:
            self.log("Download failed; proceeding with build anyway...", "warn")

        success = self.stage_2_build() and success
        if not success:
            self.log("Database build failed; proceeding with validation anyway...", "warn")

        success = self.stage_3_validate() and success
        success = self.stage_4_report() and success

        # Summary
        elapsed = time.time() - self.start_time
        self.log("=" * 60)
        self.log("REFRESH WORKFLOW SUMMARY")
        self.log("=" * 60)
        for stage, result in self.results.items():
            icon = "✓" if result == "completed" else "⚠" if result == "skipped" else "✗"
            print(f"  {icon} {stage:15s}: {result}")
        self.log(f"Total time: {elapsed:.1f}s")
        self.log("")

        return 0 if success else 1


def main():
    """Parse CLI arguments and run the four-stage data refresh workflow."""
    parser = argparse.ArgumentParser(
        description="Refresh DoD Budget Database with latest data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python refresh_data.py --years 2026
  python refresh_data.py --years 2025 2026 --sources army navy
  python refresh_data.py --dry-run --years 2026
        """,
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=None,
        help="Fiscal year(s) to refresh (default: latest year)",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["comptroller", "defense-wide", "army", "navy", "airforce", "all"],
        default=None,
        help="Data source(s) to refresh (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without executing",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose output with detailed progress",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent HTTP download threads (default: 4)",
    )

    args = parser.parse_args()

    workflow = RefreshWorkflow(verbose=args.verbose, dry_run=args.dry_run,
                              workers=args.workers)
    exit_code = workflow.run(args.years or [2026], args.sources or ["all"])
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
