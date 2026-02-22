"""
Pipeline Run Ledger — append-only JSONL history of pipeline runs.

Every time ``run_pipeline.py`` completes (successfully or not), a single JSON
line is appended to ``logs/pipeline/ledger.jsonl``.  This makes it trivial to
review recent pipeline history::

    tail -5 logs/pipeline/ledger.jsonl | python -m json.tool

The ledger is intentionally append-only and never truncated so that it
serves as a durable audit trail.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.logging import PipelineLogger


def append_to_ledger(
    pl: PipelineLogger,
    exit_code: int,
    ledger_path: Path | None = None,
) -> Path:
    """Append a one-line JSON record summarising this run to the ledger.

    Args:
        pl: The PipelineLogger for the current run (holds reports + args).
        exit_code: The pipeline exit code (0 = success).
        ledger_path: Override the default ``logs/pipeline/ledger.jsonl``.

    Returns:
        The path to the ledger file.
    """
    if ledger_path is None:
        ledger_path = pl.logs_root / "ledger.jsonl"

    reports = pl.get_reports()
    steps_summary: dict[str, Any] = {}
    for name, rpt in reports.items():
        entry: dict[str, Any] = {
            "status": rpt.status,
            "elapsed": round(rpt.elapsed_seconds, 1),
            "processed": rpt.items_processed,
            "skipped": rpt.items_skipped,
            "errored": rpt.items_errored,
        }
        if rpt.metrics:
            entry["metrics"] = rpt.metrics
        skip_cats = rpt.skip_counts_by_category()
        if skip_cats:
            entry["skip_categories"] = skip_cats
        steps_summary[name] = entry

    import time
    record = {
        "run_id": pl.run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_seconds": round(time.monotonic() - pl.pipeline_start, 1),
        "exit_code": exit_code,
        "args": pl.args_dict,
        "steps": steps_summary,
    }

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger_path, "a") as f:
        f.write(json.dumps(record, separators=(",", ":")) + "\n")

    return ledger_path
