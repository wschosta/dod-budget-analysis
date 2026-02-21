#!/usr/bin/env python3
"""
Data Refresh Workflow Script — Step 2.B4-a

Orchestrates the complete data refresh pipeline:
1. Download budget documents for specified fiscal year(s) and source(s)
2. Build/update the database incrementally
3. Run validation checks
4. Generate quality report
5. Run enrichment pipeline (PE index, descriptions, tags, lineage, project decomposition)

Usage:
    python refresh_data.py --years 2026                    # Refresh FY2026 (all sources)
    python refresh_data.py --years 2026 --sources army navy # FY2026 Army+Navy only
    python refresh_data.py --years 2025 2026 --sources all  # Multiple years
    python refresh_data.py --dry-run --years 2026           # Preview without downloading
    python refresh_data.py --schedule daily --at-hour 02:00 # Schedule daily at 2am
    python refresh_data.py --help                           # Show full options

DONE REFRESH-001: Stages 2 (build) and 3 (validate) now call Python functions
  directly instead of subprocess. Stage 1 (download) still uses subprocess
  since the downloader has heavy optional deps (Playwright, GUI).
DONE REFRESH-002: --notify flag added; POSTs summary JSON to webhook URL on
  completion or failure.
DONE REFRESH-003: Automatic rollback on failed refresh. DB is backed up before
  Stage 2; restored on failure unless --no-rollback is specified.
DONE REFRESH-004: Progress file (refresh_progress.json) written at each stage
  transition. Deleted on successful completion.
DONE REFRESH-005: --schedule flag for periodic refresh (daily/weekly/monthly).
  Uses a sleep loop with configurable --at-hour.

──────────────────────────────────────────────────────────────────────────────
LION TODOs — Rebuild Orchestration
──────────────────────────────────────────────────────────────────────────────

LION-107: Add rebuild orchestration with timing and integrity checks.
    The current refresh_data.py runs download → build → validate → report but
    does NOT run enrichment (enrich_budget_db.py). After a rebuild, the
    enrichment tables (pe_index, pe_descriptions, pe_tags, pe_lineage) are
    stale or empty. Fix: add a Stage 2b between build and validate that runs
    enrich_budget_db.enrich() with rebuild=True. Add timing output for each
    stage. Also add a post-enrichment integrity check that verifies:
    (a) every PE in budget_lines has a pe_index entry,
    (b) pe_tags is non-empty,
    (c) pe_descriptions covers expected PE/FY combinations.

"""

# DONE [Group: BEAR] BEAR-010: Data refresh e2e test — tests/test_bear_refresh_e2e.py (14 tests)

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

# REFRESH-004: Path for the progress file polled by external monitors
_PROGRESS_FILE = Path("refresh_progress.json")


class RefreshWorkflow:
    """Orchestrates the complete data refresh pipeline."""

    def __init__(self, verbose=False, dry_run=False, workers=4, notify_url=None,
                 db_path=None, no_rollback=False, phases=None):
        """Initialize workflow state.

        Args:
            verbose:     If True, emit detailed stage output.
            dry_run:     If True, log commands without executing them.
            workers:     Number of concurrent HTTP download threads.
            notify_url:  Optional webhook URL; if set, a JSON summary is POSTed
                         there after the workflow completes (REFRESH-002).
            db_path:     Path to the SQLite database (default: dod_budget.sqlite).
            no_rollback: If True, skip the automatic rollback on failure (REFRESH-003).
            phases:      Set of stage numbers to run (default: {1,2,3,4,5}).
                         HAWK-3: Stage 5 = enrichment pipeline.
        """
        self.verbose = verbose
        self.dry_run = dry_run
        self.workers = workers
        if notify_url is not None:
            parsed = urlparse(notify_url)
            if parsed.scheme not in ("http", "https"):
                raise ValueError(
                    f"notify_url must use http or https scheme, got: {parsed.scheme!r}"
                )
        self.notify_url = notify_url
        self.db_path = Path(db_path) if db_path else Path("dod_budget.sqlite")
        self.no_rollback = no_rollback
        self.phases = phases if phases is not None else {1, 2, 3, 4, 5}
        self.start_time = None
        self.results = {}
        # REFRESH-003: path for the pre-build backup
        self._backup_path: Path | None = None

    def log(self, msg: str, level="info"):
        """Print a timestamped log message."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if level == "info":
            print(f"[{timestamp}] {msg}")
        elif level == "warn":
            print(f"[{timestamp}] WARNING: {msg}")
        elif level == "error":
            print(f"[{timestamp}] ERROR: {msg}")
        elif level == "ok":
            print(f"[{timestamp}] OK: {msg}")
        elif level == "detail" and self.verbose:
            print(f"  -> {msg}")

    # ── REFRESH-004: Progress file ──────────────────────────────────────────

    def _write_progress(self, stage: str, status: str, detail: str = "") -> None:
        """Write refresh_progress.json for external monitoring (REFRESH-004)."""
        elapsed = round(time.time() - (self.start_time or time.time()), 1)
        progress = {
            "current_stage": stage,
            "stage_status": status,
            "elapsed_seconds": elapsed,
            "stage_detail": detail,
            "timestamp": datetime.now().isoformat(),
            "stages_completed": dict(self.results),
        }
        try:
            with open(_PROGRESS_FILE, "w") as f:
                json.dump(progress, f, indent=2)
        except OSError as e:
            self.log(f"Could not write progress file: {e}", "warn")

    def _clear_progress(self) -> None:
        """Remove the progress file on successful completion (REFRESH-004)."""
        try:
            _PROGRESS_FILE.unlink(missing_ok=True)
        except OSError:
            pass

    # ── REFRESH-003: Rollback helpers ───────────────────────────────────────

    def _backup_db(self) -> bool:
        """Copy the current database to a .bak file before Stage 2 (REFRESH-003)."""
        if self.dry_run or not self.db_path.exists():
            return True
        self._backup_path = self.db_path.with_suffix(".sqlite.bak")
        try:
            shutil.copy2(self.db_path, self._backup_path)
            self.log(f"REFRESH-003: Database backed up to {self._backup_path}", "detail")
            return True
        except OSError as e:
            self.log(f"REFRESH-003: Backup failed: {e}", "warn")
            return False

    def _rollback_db(self) -> bool:
        """Restore the database from backup after a failed refresh (REFRESH-003)."""
        if self.no_rollback:
            self.log("REFRESH-003: Rollback skipped (--no-rollback)", "warn")
            return False
        if not self._backup_path or not self._backup_path.exists():
            self.log("REFRESH-003: No backup available to roll back to", "warn")
            return False
        try:
            shutil.copy2(self._backup_path, self.db_path)
            self.log(f"REFRESH-003: Database restored from {self._backup_path}", "ok")
            return True
        except OSError as e:
            self.log(f"REFRESH-003: Rollback failed: {e}", "error")
            return False

    def _cleanup_backup(self) -> None:
        """Remove the backup file after a successful refresh (REFRESH-003)."""
        if self._backup_path and self._backup_path.exists():
            try:
                self._backup_path.unlink()
            except OSError:
                pass

    # ── Stages ─────────────────────────────────────────────────────────────

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
        self._write_progress("stage_1_download", "running", "Downloading budget documents")

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
        self._write_progress("stage_1_download", "completed" if success else "failed",
                             f"Download {'succeeded' if success else 'failed'}")
        return success

    def stage_2_build(self) -> bool:
        """Stage 2: Build or update the database (REFRESH-001: direct import)."""
        self.log("=" * 60)
        self.log("STAGE 2: BUILD DATABASE")
        self.log("=" * 60)
        self._write_progress("stage_2_build", "running", "Building database")

        if self.dry_run:
            self.log("[DRY RUN] Would call build_database()", "detail")
            self.results["build"] = "completed"
            self._write_progress("stage_2_build", "completed")
            return True

        # REFRESH-003: Back up before building
        self._backup_db()

        try:
            from build_budget_db import build_database  # noqa: PLC0415
            docs_dir = Path("DoD_Budget_Documents")
            build_database(docs_dir, self.db_path)
            self.log("Completed: Database build/update", "ok")
            self.results["build"] = "completed"
            self._write_progress("stage_2_build", "completed", "Database built successfully")
            return True
        except Exception as e:
            self.log(f"Exception during Database build/update: {e}", "error")
            self.results["build"] = "failed"
            self._write_progress("stage_2_build", "failed", str(e))
            # REFRESH-003: Rollback on failure
            rolled_back = self._rollback_db()
            self.results["rollback"] = "completed" if rolled_back else "skipped"
            return False

    def stage_5_enrich(self) -> bool:
        """Stage 5: Run enrichment pipeline (HAWK-3, formerly LION-107 stage 2b).

        Runs enrich_budget_db.enrich() with rebuild=True to populate
        pe_index, pe_descriptions, pe_tags, pe_lineage, and
        project_descriptions after a build.
        Also performs post-enrichment integrity checks.

        Enrichment failure warns but does not trigger rollback.
        """
        self.log("=" * 60)
        self.log("STAGE 5: ENRICH DATABASE")
        self.log("=" * 60)
        self._write_progress("stage_5_enrich", "running", "Running enrichment pipeline")

        if self.dry_run:
            self.log("[DRY RUN] Would call enrich_budget_db.enrich()", "detail")
            self.results["enrich"] = "completed"
            self._write_progress("stage_5_enrich", "completed")
            return True

        if not self.db_path.exists():
            self.log("Database not found; skipping enrichment", "warn")
            self.results["enrich"] = "skipped"
            self._write_progress("stage_5_enrich", "skipped", "DB not found")
            return False

        t0 = time.time()
        try:
            from enrich_budget_db import enrich  # noqa: PLC0415
            enrich(self.db_path, phases={1, 2, 3, 4, 5}, rebuild=True)
            elapsed = time.time() - t0
            self.log(f"Enrichment complete in {elapsed:.1f}s", "ok")

            # LION-107: Post-enrichment integrity checks
            import sqlite3
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row

            # (a) Every PE in budget_lines should have a pe_index entry
            orphan_pes = conn.execute("""
                SELECT COUNT(DISTINCT pe_number) FROM budget_lines
                WHERE pe_number IS NOT NULL
                  AND pe_number NOT IN (SELECT pe_number FROM pe_index)
            """).fetchone()[0]
            if orphan_pes > 0:
                self.log(f"LION-107 WARNING: {orphan_pes} PE(s) in budget_lines "
                         f"without pe_index entry", "warn")

            # (b) pe_tags should be non-empty
            tag_count = conn.execute(
                "SELECT COUNT(*) FROM pe_tags"
            ).fetchone()[0]
            if tag_count == 0:
                self.log("LION-107 WARNING: pe_tags is empty", "warn")
            else:
                self.log(f"pe_tags: {tag_count:,} tag rows", "detail")

            # (c) pe_descriptions should cover expected PE/FY combinations
            desc_coverage = conn.execute("""
                SELECT COUNT(DISTINCT pe_number) FROM pe_descriptions
            """).fetchone()[0]
            pe_count = conn.execute(
                "SELECT COUNT(*) FROM pe_index"
            ).fetchone()[0]
            coverage_pct = (desc_coverage / pe_count * 100) if pe_count else 0
            self.log(f"pe_descriptions covers {desc_coverage}/{pe_count} PEs "
                     f"({coverage_pct:.0f}%)", "detail")

            conn.close()
            self.results["enrich"] = "completed"
            self._write_progress("stage_5_enrich", "completed",
                                 f"{elapsed:.1f}s, {tag_count} tags")
            return True

        except Exception as e:
            self.log(f"Exception during enrichment: {e}", "error")
            self.results["enrich"] = "failed"
            self._write_progress("stage_5_enrich", "failed", str(e))
            return False

    def stage_3_validate(self) -> bool:
        """Stage 3: Run validation checks (REFRESH-001: direct import)."""
        self.log("=" * 60)
        self.log("STAGE 3: VALIDATE DATABASE")
        self.log("=" * 60)
        self._write_progress("stage_3_validate", "running", "Running validation checks")

        if self.dry_run:
            self.log("[DRY RUN] Would call validate_all()", "detail")
            self.results["validate"] = "completed"
            self._write_progress("stage_3_validate", "completed")
            return True

        try:
            from validate_budget_data import validate_all, print_report  # noqa: PLC0415
            summary = validate_all(self.db_path)
            print_report(summary)
            success = summary["total_failures"] == 0
            self.log("Completed: Data validation", "ok" if success else "warn")
            self.results["validate"] = "completed" if success else "failed"
            self._write_progress(
                "stage_3_validate",
                "completed" if success else "failed",
                f"{summary.get('total_failures', 0)} failures"
            )
            if not success:
                # REFRESH-003: Rollback on validation failure
                rolled_back = self._rollback_db()
                self.results["rollback"] = "completed" if rolled_back else "skipped"
            return success
        except Exception as e:
            self.log(f"Exception during Data validation: {e}", "error")
            self.results["validate"] = "failed"
            self._write_progress("stage_3_validate", "failed", str(e))
            rolled_back = self._rollback_db()
            self.results["rollback"] = "completed" if rolled_back else "skipped"
            return False

    def stage_4_report(self) -> bool:
        """Stage 4: Generate quality report (2.B3-a: extended data-quality JSON)."""
        self.log("=" * 60)
        self.log("STAGE 4: GENERATE QUALITY REPORT")
        self.log("=" * 60)
        self._write_progress("stage_4_report", "running", "Generating quality report")

        if self.dry_run:
            self.log("[DRY RUN] Would call generate_quality_report()", "detail")
            self.results["report"] = "completed"
            self._write_progress("stage_4_report", "completed")
            return True

        if not self.db_path.exists():
            self.log("Database not found; skipping report generation", "warn")
            self.results["report"] = "skipped"
            self._write_progress("stage_4_report", "skipped", "DB not found")
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
            self._write_progress("stage_4_report", "completed",
                                 f"{quality_report['total_budget_lines']:,} budget lines")
            return True

        except Exception as e:
            self.log(f"Error generating report: {e}", "error")
            self.results["report"] = "failed"
            self._write_progress("stage_4_report", "failed", str(e))
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
        self.log(f"Rollback on failure: {not self.no_rollback}")
        self.log(f"Phases: {sorted(self.phases)}")
        self.log("")

        # REFRESH-004: Initial progress entry
        self._write_progress("starting", "running", "Refresh workflow starting")

        # Execute stages (HAWK-3: controlled by --phases flag)
        success = True

        if 1 in self.phases:
            success = self.stage_1_download(years, sources) and success
            if not success:
                self.log("Download failed; proceeding with build anyway...", "warn")

        if 2 in self.phases:
            success = self.stage_2_build() and success
            if not success:
                self.log("Database build failed; proceeding anyway...", "warn")

        if 3 in self.phases:
            success = self.stage_3_validate() and success

        if 4 in self.phases:
            success = self.stage_4_report() and success

        # HAWK-3: Stage 5 = enrichment pipeline (runs after validation)
        # Enrichment failure warns but does not roll back the entire refresh
        if 5 in self.phases:
            enrich_ok = self.stage_5_enrich()
            if not enrich_ok:
                self.log("Enrichment failed (non-fatal); database is still valid.", "warn")

        # Summary
        elapsed = time.time() - self.start_time
        self.log("=" * 60)
        self.log("REFRESH WORKFLOW SUMMARY")
        self.log("=" * 60)
        for stage, result in self.results.items():
            icon = "OK" if result == "completed" else "skip" if result == "skipped" else "FAIL"
            print(f"  [{icon}] {stage:15s}: {result}")
        self.log(f"Total time: {elapsed:.1f}s")
        self.log("")

        # REFRESH-002: Send webhook notification if --notify was supplied
        if self.notify_url:
            self._send_notification(success, elapsed)

        if success:
            # REFRESH-003: Clean up backup on success
            self._cleanup_backup()
            # REFRESH-004: Clear progress file on successful completion
            self._clear_progress()
        else:
            self._write_progress("done", "failed",
                                 f"Workflow failed after {elapsed:.1f}s")

        return 0 if success else 1

    def _send_notification(self, success: bool, elapsed: float) -> None:
        """POST a JSON summary to the configured webhook URL (REFRESH-002)."""
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


# ── REFRESH-005: Periodic scheduler ──────────────────────────────────────────

_SCHEDULE_INTERVALS = {
    "daily": 86400,
    "weekly": 604800,
    "monthly": 2592000,  # 30 days
}


def _next_run_time(at_hour: str | None) -> float:
    """Compute the next run time as a Unix timestamp (REFRESH-005).

    If at_hour is "HH:MM", schedules for that time today (or tomorrow if past).
    Otherwise returns now + a short delay.
    """
    if not at_hour:
        return time.time()
    try:
        hh, mm = at_hour.split(":")
        now = datetime.now()
        run_today = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        if run_today <= now:
            run_today += timedelta(days=1)
        return run_today.timestamp()
    except ValueError:
        print(f"WARNING: Invalid --at-hour value '{at_hour}'; running immediately.")
        return time.time()


def run_scheduled(args, workflow_kwargs: dict) -> None:
    """Run the refresh workflow on a schedule (REFRESH-005).

    Uses a simple sleep loop rather than sched to avoid drift on long intervals.
    """
    interval = _SCHEDULE_INTERVALS[args.schedule]
    next_run = _next_run_time(args.at_hour)

    print(f"REFRESH-005: Scheduled refresh every {args.schedule}")
    print(f"  Interval: {interval}s")
    print(f"  Next run: {datetime.fromtimestamp(next_run).isoformat()}")
    print("  Press Ctrl+C to stop.")

    while True:
        wait = max(0, next_run - time.time())
        if wait > 0:
            print(f"  Sleeping {wait:.0f}s until {datetime.fromtimestamp(next_run).isoformat()}...")
            time.sleep(wait)

        print(f"\n[{datetime.now().isoformat()}] REFRESH-005: Starting scheduled run")
        workflow = RefreshWorkflow(**workflow_kwargs)
        workflow.run(args.years or [2026], args.sources or ["all"])

        next_run = time.time() + interval
        print(f"  Next run scheduled for {datetime.fromtimestamp(next_run).isoformat()}")


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
  python refresh_data.py --schedule daily --at-hour 02:00
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
    # REFRESH-003: Rollback control
    parser.add_argument(
        "--no-rollback",
        action="store_true",
        help="Disable automatic rollback on failed refresh (REFRESH-003)",
    )
    # HAWK-3: Stage selection
    parser.add_argument(
        "--phases",
        default="1,2,3,4,5",
        help="Comma-separated stages to run (default: 1,2,3,4,5). "
             "1=download, 2=build, 3=validate, 4=report, 5=enrich",
    )
    # REFRESH-005: Scheduling
    parser.add_argument(
        "--schedule",
        choices=["daily", "weekly", "monthly"],
        default=None,
        help="Run refresh on a repeating schedule (REFRESH-005)",
    )
    parser.add_argument(
        "--at-hour",
        metavar="HH:MM",
        default=None,
        help="Time of day for scheduled refresh, e.g. 02:00 (REFRESH-005)",
    )

    args = parser.parse_args()

    try:
        phases = {int(p.strip()) for p in args.phases.split(",")}
    except ValueError:
        print("ERROR: --phases must be comma-separated integers, e.g. '1,2,3,4,5'")
        sys.exit(1)

    workflow_kwargs = {
        "verbose": args.verbose,
        "dry_run": args.dry_run,
        "workers": args.workers,
        "notify_url": args.notify,
        "db_path": args.db,
        "no_rollback": args.no_rollback,
        "phases": phases,
    }

    if args.schedule:
        # REFRESH-005: Enter the scheduling loop
        run_scheduled(args, workflow_kwargs)
    else:
        workflow = RefreshWorkflow(**workflow_kwargs)
        exit_code = workflow.run(args.years or [2026], args.sources or ["all"])
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
