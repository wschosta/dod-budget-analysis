"""
Pipeline Logging — per-step log files and structured skip/error accounting.

Provides:
  - PipelineLogger: manages a ``logs/pipeline/`` directory with one log file per
    pipeline step per run, plus a console handler that mirrors key events.
  - StepReport: lightweight dataclass that captures what a step did, what it
    skipped, and why.
  - SkipRecord: single skip event with a category and detail string.

Usage inside run_pipeline.py::

    from pipeline.logging import PipelineLogger

    pl = PipelineLogger()                   # creates logs/pipeline/<run_id>_*.log
    pl.start_step("build")                  # opens build log handler
    ...                                      # builder writes to logging normally
    pl.finish_step("build", report)         # detaches handler, records report
    pl.write_summary()                      # writes <run_id>_summary.json

Skip categories (for SkipRecord.category):
    user_skipped        — user passed --skip-validate / --skip-enrich
    incremental_skip    — file unchanged since last ingest (size + mtime match)
    dependency_skip     — prerequisite empty (e.g. pe_index has 0 rows)
    already_done        — item already processed in a previous run
    error_skip          — item skipped due to a parse/extraction error
    config_skip         — feature disabled by config (e.g. no ANTHROPIC_API_KEY)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Data structures ───────────────────────────────────────────────────────────


@dataclass
class SkipRecord:
    """One thing that was skipped, with a machine-readable category."""

    category: str          # e.g. "incremental_skip", "dependency_skip"
    detail: str            # human-readable explanation
    item: str = ""         # optional: file path, phase name, check name, etc.

    def to_dict(self) -> dict[str, str]:
        d: dict[str, str] = {"category": self.category, "detail": self.detail}
        if self.item:
            d["item"] = self.item
        return d


@dataclass
class StepReport:
    """Structured summary of what one pipeline step accomplished."""

    step_name: str
    status: str = "not_started"               # started | completed | failed | skipped
    elapsed_seconds: float = 0.0
    items_processed: int = 0
    items_skipped: int = 0
    items_errored: int = 0
    skips: list[SkipRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    detail: str = ""                           # free-form human note

    # ── helpers ───────────────────────────────────────────────────────────

    def add_skip(self, category: str, detail: str, item: str = "") -> None:
        self.skips.append(SkipRecord(category=category, detail=detail, item=item))
        self.items_skipped += 1

    def add_error(self, message: str) -> None:
        self.errors.append(message)
        self.items_errored += 1

    def skip_counts_by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for s in self.skips:
            counts[s.category] = counts.get(s.category, 0) + 1
        return counts

    def console_summary(self) -> str:
        """One-paragraph summary suitable for the terminal."""
        parts: list[str] = []
        if self.items_processed:
            parts.append(f"{self.items_processed:,} processed")
        if self.items_skipped:
            cats = self.skip_counts_by_category()
            skip_parts = [f"{v} {k.replace('_', ' ')}" for k, v in sorted(cats.items())]
            parts.append(f"{self.items_skipped:,} skipped ({', '.join(skip_parts)})")
        if self.items_errored:
            parts.append(f"{self.items_errored:,} errors")
        if self.detail:
            parts.append(self.detail)
        for key, val in self.metrics.items():
            if isinstance(val, (int, float)):
                parts.append(f"{key}: {val:,}" if isinstance(val, int) else f"{key}: {val:.1f}")
        return " | ".join(parts) if parts else "no activity"

    def to_dict(self) -> dict[str, Any]:
        d = {
            "step_name": self.step_name,
            "status": self.status,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "items_processed": self.items_processed,
            "items_skipped": self.items_skipped,
            "items_errored": self.items_errored,
            "metrics": self.metrics,
        }
        if self.detail:
            d["detail"] = self.detail
        if self.skips:
            d["skips"] = [s.to_dict() for s in self.skips]
        if self.errors:
            d["errors"] = self.errors
        return d


# ── PipelineLogger ────────────────────────────────────────────────────────────


class PipelineLogger:
    """Manages per-run, per-step log files under ``logs/pipeline/``.

    Creates a directory like::

        logs/pipeline/2026-02-22T14-30-00/
            build.log
            validate.log
            enrich.log
            summary.json
    """

    def __init__(self, logs_dir: Path | str = "logs/pipeline") -> None:
        self.logs_root = Path(logs_dir)
        self.run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        self.run_dir = self.logs_root / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

        self._step_handlers: dict[str, logging.FileHandler] = {}
        self._step_start_times: dict[str, float] = {}
        self._reports: dict[str, StepReport] = {}

        self.pipeline_start = time.monotonic()
        self.args_dict: dict[str, Any] = {}

    # ── step lifecycle ────────────────────────────────────────────────────

    def start_step(self, step_name: str) -> StepReport:
        """Open a log file for *step_name* and attach it to the root logger."""
        log_path = self.run_dir / f"{step_name}.log"
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
            datefmt="%H:%M:%S",
        ))
        logging.getLogger().addHandler(handler)
        self._step_handlers[step_name] = handler
        self._step_start_times[step_name] = time.monotonic()

        report = StepReport(step_name=step_name, status="started")
        self._reports[step_name] = report
        return report

    def finish_step(self, step_name: str, report: StepReport | None = None) -> None:
        """Detach the log handler for *step_name* and finalise the report."""
        # Timing
        t0 = self._step_start_times.pop(step_name, self.pipeline_start)
        elapsed = time.monotonic() - t0

        # Finalise report
        if report is None:
            report = self._reports.get(step_name, StepReport(step_name=step_name))
        report.elapsed_seconds = elapsed
        if report.status == "started":
            report.status = "completed"
        self._reports[step_name] = report

        # Print skip accounting to console
        if report.items_skipped > 0 or report.items_errored > 0:
            print(f"  [{step_name}] {report.console_summary()}", flush=True)

        # Detach file handler
        handler = self._step_handlers.pop(step_name, None)
        if handler:
            # Write the step summary into the log file itself before closing
            handler.stream.write(f"\n{'=' * 60}\n")
            handler.stream.write(f"STEP SUMMARY: {step_name}\n")
            handler.stream.write(f"  Status:    {report.status}\n")
            handler.stream.write(f"  Elapsed:   {elapsed:.1f}s\n")
            handler.stream.write(f"  Processed: {report.items_processed}\n")
            handler.stream.write(f"  Skipped:   {report.items_skipped}\n")
            handler.stream.write(f"  Errors:    {report.items_errored}\n")
            if report.skips:
                handler.stream.write("  Skip breakdown:\n")
                for cat, count in sorted(report.skip_counts_by_category().items()):
                    handler.stream.write(f"    {cat}: {count}\n")
            if report.errors:
                handler.stream.write("  Error details:\n")
                for err in report.errors[:20]:
                    handler.stream.write(f"    - {err}\n")
                if len(report.errors) > 20:
                    handler.stream.write(
                        f"    ... and {len(report.errors) - 20} more\n"
                    )
            handler.stream.write(f"{'=' * 60}\n")
            handler.close()
            logging.getLogger().removeHandler(handler)

    def record_user_skip(self, step_name: str, reason: str) -> None:
        """Record that a step was skipped entirely by user flags."""
        report = StepReport(
            step_name=step_name,
            status="skipped",
        )
        report.add_skip("user_skipped", reason)
        self._reports[step_name] = report

    # ── summary output ────────────────────────────────────────────────────

    def write_summary(self) -> Path:
        """Write a JSON summary of the entire run to the run directory."""
        total_elapsed = time.monotonic() - self.pipeline_start
        summary = {
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_elapsed_seconds": round(total_elapsed, 2),
            "args": self.args_dict,
            "steps": {name: rpt.to_dict() for name, rpt in self._reports.items()},
        }
        path = self.run_dir / "summary.json"
        with open(path, "w") as f:
            json.dump(summary, f, indent=2)
        return path

    def get_reports(self) -> dict[str, StepReport]:
        return dict(self._reports)

    @property
    def summary_path(self) -> Path:
        return self.run_dir / "summary.json"
