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

---
TODOs for this file
---

DONE REFRESH-001: Stages 2 (build) and 3 (validate) now call Python functions
  directly instead of subprocess. Stage 1 (download) still uses subprocess
  since the downloader has heavy optional deps (Playwright, GUI).
DONE REFRESH-002: --notify flag added; POSTs summary JSON to webhook URL on
  completion or failure.
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path


class RefreshWorkflow:
    """Orchestrates the complete data refresh pipeline."""

    def __init__(self, verbose=False, dry_run=False, workers=4, notify_url=None,
                 db_path=None):
        """Initialize workflow state.

        Args:
            verbose:    If True, emit detailed stage output.
            dry_run:    If True, log commands without executing them.
            workers:    Number of concurrent HTTP download threads.
            notify_url: Optional webhook URL; if set, a JSON summary is POSTed
                        there after the workflow completes (REFRESH-002).
            db_path:    Path to the SQLite database (default: dod_budget.sqlite).
        """
        self.verbose = verbose
        self.dry_run = dry_run
        self.workers = workers
        self.notify_url = notify_url
        self.db_path = Path(db_path) if db_path else Path("dod_budget.sqlite")
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
        """Stage 2: Build or update the database (REFRESH-001: direct import)."""
        self.log("=" * 60)
        self.log("STAGE 2: BUILD DATABASE")
        self.log("=" * 60)

        if self.dry_run:
            self.log("[DRY RUN] Would call build_database()", "detail")
            self.results["build"] = "completed"
            return True

        try:
            from build_budget_db import build_database  # noqa: PLC0415
            docs_dir = Path("DoD_Budget_Documents")
            build_database(docs_dir, self.db_path)
            self.log("Completed: Database build/update", "ok")
            self.results["build"] = "completed"
            return True
        except Exception as e:
            self.log(f"Exception during Database build/update: {e}", "error")
            self.results["build"] = "failed"
            return False

    def stage_3_validate(self) -> bool:
        """Stage 3: Run validation checks (REFRESH-001: direct import)."""
        self.log("=" * 60)
        self.log("STAGE 3: VALIDATE DATABASE")
        self.log("=" * 60)

        if self.dry_run:
            self.log("[DRY RUN] Would call validate_all()", "detail")
            self.results["validate"] = "completed"
            return True

        try:
            from validate_budget_data import validate_all, print_report  # noqa: PLC0415
            summary = validate_all(self.db_path)
            print_report(summary)
            success = summary["total_failures"] == 0
            self.log("Completed: Data validation", "ok" if success else "warn")
            self.results["validate"] = "completed" if success else "failed"
            return success
        except Exception as e:
            self.log(f"Exception during Data validation: {e}", "error")
            self.results["validate"] = "failed"
            return False

    def stage_4_report(self) -> bool:
        """Stage 4: Generate quality report (2.B3-a: extended data-quality JSON)."""
        self.log("=" * 60)
        self.log("STAGE 4: GENERATE QUALITY REPORT")
        self.log("=" * 60)

        if self.dry_run:
            self.log("[DRY RUN] Would call generate_quality_report()", "detail")
            self.results["report"] = "completed"
            return True

        if not self.db_path.exists():
            self.log("Database not found; skipping report generation", "warn")
            self.results["report"] = "skipped"
            return False

        try:
            from validate_budget_data import (  # noqa: PLC0415
                generate_quality_report,
            )
            quality_report = generate_quality_report(
                self.db_path,
                output_path=Path("data_quality_report.json"),
                print_console=self.verbose,
            )

            # Also write a lean refresh_report.json with workflow metadata
            db_size_mb = self.db_path.stat().st_size / (1024 * 1024)
            refresh_report = {
                "timestamp": datetime.now().isoformat(),
                "database_file": str(self.db_path),
                "database_size_mb": round(db_size_mb, 2),
                "total_budget_lines": quality_report["total_budget_lines"],
                "validation_summary": quality_report["validation_summary"],
                "workflow_stages": self.results,
            }
            report_path = Path("refresh_report.json")
            with open(report_path, "w") as f:
                json.dump(refresh_report, f, indent=2)

            self.log(
                f"Quality report: {quality_report['total_budget_lines']:,} budget lines, "
                f"{quality_report['validation_summary']['total_warnings']} warning(s)",
                "ok",
            )
            self.log(f"Reports saved: data_quality_report.json, {report_path}", "ok")
            self.results["report"] = "completed"
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

        # REFRESH-002: Send webhook notification if --notify was supplied
        if self.notify_url:
            self._send_notification(success, elapsed)

        return 0 if success else 1

    def _send_notification(self, success: bool, elapsed: float) -> None:
        """POST a JSON summary to the configured webhook URL (REFRESH-002).

        Silently ignores failures so a broken webhook never stops the workflow.
        The payload shape is compatible with Slack incoming-webhook format as
        well as generic HTTP webhook receivers.
        """
        payload = {
            "text": (
                f"DoD Budget Refresh {'succeeded' if success else 'failed'} "
                f"in {elapsed:.0f}s"
            ),
            "workflow_success": success,
            "elapsed_seconds": round(elapsed, 1),
            "stages": self.results,
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.notify_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10):
                pass
            self.log(f"Notification sent to {self.notify_url}", "ok")
        except Exception as e:
            self.log(f"Notification failed (non-fatal): {e}", "warn")


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
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to SQLite database (default: dod_budget.sqlite)",
    )
    parser.add_argument(
        "--notify",
        metavar="WEBHOOK_URL",
        default=None,
        help="Webhook URL to POST a JSON summary on completion/failure (REFRESH-002)",
    )

    args = parser.parse_args()

    workflow = RefreshWorkflow(
        verbose=args.verbose,
        dry_run=args.dry_run,
        workers=args.workers,
        notify_url=args.notify,
        db_path=args.db,
    )
    exit_code = workflow.run(args.years or [2026], args.sources or ["all"])
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
