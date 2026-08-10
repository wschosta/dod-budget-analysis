"""Guards against enrichment phase drift between the enricher and its callers.

`scripts/run_pipeline.py` once hardcoded `{1..10}` while the enricher had
registered a Phase 11 (P-5 BLI↔PE mining), so a full pipeline run silently
left `bli_pe_map` empty.  `pipeline/refresh.py` had the same bug earlier with
`{1..5}`.  Both callers now derive their "run everything" set from
`pipeline.enricher.ALL_PHASES`; these tests fail if that constant falls behind
the dispatch table, or if a caller goes back to a literal.
"""

from __future__ import annotations

import sqlite3
from unittest.mock import patch

import run_pipeline
from pipeline.enricher import ALL_PHASES, _build_phase_runners
from pipeline.refresh import RefreshWorkflow


def test_all_phases_matches_dispatch_table():
    """ALL_PHASES must name every phase enrich() knows how to run.

    Registering a phase in _build_phase_runners() without widening ALL_PHASES
    means every default-path caller skips it.
    """
    conn = sqlite3.connect(":memory:")
    try:
        # The values are lambdas — building the dict never touches the DB.
        registered = set(_build_phase_runners(conn))
    finally:
        conn.close()

    assert registered == set(ALL_PHASES), (
        f"ALL_PHASES={sorted(ALL_PHASES)} does not match the phases registered "
        f"in _build_phase_runners(): {sorted(registered)}"
    )


def test_all_phases_is_contiguous_from_one():
    """Phases are numbered 1..N with no gaps — a missing number is a typo."""
    assert sorted(ALL_PHASES) == list(range(1, max(ALL_PHASES) + 1))


@patch("run_pipeline._backup_db", return_value=None)
@patch("run_pipeline._cleanup_backup")
@patch("run_pipeline._clear_progress")
def test_run_pipeline_default_covers_all_phases(
    mock_clear, mock_cleanup, mock_backup, tmp_path, monkeypatch
):
    """A plain `run_pipeline.py` run enriches with every registered phase."""
    monkeypatch.setattr(run_pipeline, "_PROGRESS_FILE", tmp_path / "pipeline_progress.json")
    run_pipeline._completed_steps.clear()
    run_pipeline._stop_event.clear()

    db = tmp_path / "test.sqlite"
    docs = tmp_path / "docs"
    docs.mkdir()

    val_result = {
        "exit_code": 0,
        "total_checks": 1,
        "total_warnings": 0,
        "total_failures": 0,
        "checks": [],
    }

    try:
        with (
            patch("pipeline.builder.build_database", return_value={"rows": 10}),
            patch(
                "repair_database.repair",
                return_value={"org_normalized": 0, "approp_backfilled": 0, "reference": {}},
            ),
            patch("pipeline.validator.validate_all", return_value=val_result),
            patch("pipeline.enricher.enrich") as mock_enrich,
        ):
            rc = run_pipeline.main([
                "--db", str(db),
                "--docs", str(docs),
                "--skip-download",
            ])
    finally:
        run_pipeline._completed_steps.clear()
        run_pipeline._stop_event.clear()

    assert rc == 0
    assert mock_enrich.call_args[1]["phases"] == set(ALL_PHASES)


def test_refresh_stage_5_covers_all_phases(tmp_path, monkeypatch):
    """RefreshWorkflow stage 5 enriches with every registered phase."""
    import pipeline.refresh as refresh_mod

    monkeypatch.setattr(refresh_mod, "_PROGRESS_FILE", tmp_path / "refresh_progress.json")

    db = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db)
    # Minimal tables for stage 5's post-enrichment integrity queries.
    conn.execute("CREATE TABLE budget_lines (pe_number TEXT)")
    conn.execute("CREATE TABLE pe_index (pe_number TEXT)")
    conn.execute("CREATE TABLE pe_tags (pe_number TEXT, tag TEXT)")
    conn.execute("CREATE TABLE pe_descriptions (pe_number TEXT)")
    conn.commit()
    conn.close()

    wf = RefreshWorkflow(db_path=db)

    with patch("pipeline.enricher.enrich") as mock_enrich:
        assert wf.stage_5_enrich() is True

    assert mock_enrich.call_args[1]["phases"] == set(ALL_PHASES)
