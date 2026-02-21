"""
Full pipeline runner -- builds, validates, and enriches the DoD budget database.

Steps (in order):
  1. build_budget_db.py      -- ingest Excel + PDF source files
  2. validate_budget_data.py -- QA checks against the populated DB
  3. enrich_budget_db.py     -- populate pe_index, pe_descriptions,
                                pe_tags, pe_lineage

Usage:
    python run_pipeline.py                        # full run, incremental
    python run_pipeline.py --rebuild              # full rebuild from scratch
    python run_pipeline.py --with-llm             # enable LLM tagging in Phase 3
    python run_pipeline.py --db mydb.sqlite       # custom database path
    python run_pipeline.py --docs /path/to/docs   # custom documents directory
    python run_pipeline.py --workers 4            # parallel PDF workers
    python run_pipeline.py --skip-validate        # skip validation step
    python run_pipeline.py --skip-enrich          # stop after validation
    python run_pipeline.py --enrich-phases 1,2    # run only specific enrich phases
    python run_pipeline.py --strict               # fail pipeline on validation warnings
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent

def _find_python() -> str:
    """Return a console-mode python.exe, never pythonw.exe."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        candidate = exe.with_name("python.exe")
        if candidate.exists():
            return str(candidate)
    return str(exe)

PYTHON = _find_python()

STEP_BUILD    = HERE / "build_budget_db.py"
STEP_VALIDATE = HERE / "validate_budget_data.py"
STEP_ENRICH   = HERE / "enrich_budget_db.py"


def _banner(text: str) -> None:
    bar = "=" * 60
    print(f"\n{bar}")
    print(f"  {text}")
    print(f"{bar}\n", flush=True)


def _run(label: str, cmd: list[str]) -> int:
    """Run a subprocess, stream its output live, and return its exit code."""
    _banner(label)
    print(f"Command: {' '.join(cmd)}\n", flush=True)
    t0 = time.monotonic()
    result = subprocess.run(cmd)
    elapsed = time.monotonic() - t0
    status = "OK" if result.returncode == 0 else f"FAILED (exit {result.returncode})"
    print(f"\n[{label}] {status} -- {elapsed:.1f}s", flush=True)
    return result.returncode


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Run the full DoD budget pipeline: "
            "build -> validate -> enrich"
        ),
    )

    # Shared
    p.add_argument(
        "--db", default="dod_budget.sqlite",
        help="Database path (default: dod_budget.sqlite)",
    )

    # build_budget_db options
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

    # validate_budget_data options
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

    # enrich_budget_db options
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
        help="Comma-separated enrichment phases to run (default: 1,2,3,4)",
    )
    p.add_argument(
        "--rebuild-enrich", action="store_true",
        help="Drop and rebuild enrichment tables only (not the full DB)",
    )

    return p.parse_args()


def _build_cmd(args: argparse.Namespace) -> list[str]:
    cmd = [PYTHON, str(STEP_BUILD), "--db", args.db]
    if args.docs:
        cmd += ["--docs", args.docs]
    if args.rebuild:
        cmd.append("--rebuild")
    if args.resume:
        cmd.append("--resume")
    if args.workers is not None:
        cmd += ["--workers", str(args.workers)]
    if args.checkpoint_interval is not None:
        cmd += ["--checkpoint-interval", str(args.checkpoint_interval)]
    return cmd


def _validate_cmd(args: argparse.Namespace) -> list[str]:
    cmd = [PYTHON, str(STEP_VALIDATE), "--db", args.db]
    if args.pedantic:
        cmd.append("--pedantic")
    elif args.strict:
        cmd.append("--strict")
    return cmd


def _enrich_cmd(args: argparse.Namespace) -> list[str]:
    cmd = [PYTHON, str(STEP_ENRICH), "--db", args.db]
    if args.with_llm:
        cmd.append("--with-llm")
    if args.enrich_phases:
        cmd += ["--phases", args.enrich_phases]
    if args.rebuild_enrich:
        cmd.append("--rebuild")
    return cmd


def main() -> int:
    args = _parse_args()

    pipeline_start = time.monotonic()
    print("\nDoD Budget Pipeline")
    print(f"  Database : {args.db}")
    print(f"  Rebuild  : {'yes (full)' if args.rebuild else 'no (incremental)'}")
    validate_mode = " [pedantic]" if args.pedantic else " [strict]" if args.strict else ""
    print(
        f"  Validate : {'skip' if args.skip_validate else 'yes'}"
        + validate_mode
    )
    print(
        f"  Enrich   : {'skip' if args.skip_enrich else 'yes'}"
        + (f" [phases {args.enrich_phases}]" if args.enrich_phases else "")
        + (" [+LLM]" if args.with_llm else "")
    )

    # Step 1: Build
    rc = _run("Step 1 / 3 -- Build database", _build_cmd(args))
    if rc != 0:
        print(f"\nPipeline aborted: build step failed (exit {rc}).", flush=True)
        return rc

    # Step 2: Validate
    if not args.skip_validate:
        rc = _run("Step 2 / 3 -- Validate database", _validate_cmd(args))
        if rc != 0:
            if args.strict or args.pedantic:
                mode = "pedantic" if args.pedantic else "strict"
                print(
                    f"\nPipeline aborted: validation failed (exit {rc}).\n"
                    f"Re-run without --{mode} to continue past issues.",
                    flush=True,
                )
                return rc
            print(
                "\nValidation reported warnings -- continuing pipeline.\n"
                "Use --strict to fail on errors, --pedantic to fail on warnings.",
                flush=True,
            )
    else:
        print("\n[Step 2 / 3 -- Validate database] SKIPPED", flush=True)

    # Step 3: Enrich
    if not args.skip_enrich:
        rc = _run("Step 3 / 3 -- Enrich database", _enrich_cmd(args))
        if rc != 0:
            print(
                f"\nPipeline aborted: enrichment step failed (exit {rc}).",
                flush=True,
            )
            return rc
    else:
        print("\n[Step 3 / 3 -- Enrich database] SKIPPED", flush=True)

    total = time.monotonic() - pipeline_start
    _banner(f"Pipeline complete -- {total:.1f}s total")
    print(f"Database ready: {Path(args.db).resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
