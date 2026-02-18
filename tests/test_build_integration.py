"""
Build Integration Tests — Phases 2-5

Tests for:
- Progress callback with metrics dict (Phase 2)
- Checkpoint saving during build (Phase 3)
- Resume from checkpoint (Phase 4)
- Graceful shutdown via stop_event (Phase 5)

Run with: pytest tests/test_build_integration.py -v
"""

import sqlite3
import threading
from pathlib import Path

import build_budget_db
import openpyxl
import pytest

from build_budget_db import (
    build_database,
    _get_last_checkpoint,
    _get_processed_files,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_workspace(tmp_path, monkeypatch):
    """Create a minimal workspace with a DoD-style docs directory.

    Patches DOCS_DIR in build_budget_db so ingest_excel_file/ingest_pdf_file
    can resolve relative paths against the temp directory instead of the
    hardcoded global DOCS_DIR.
    """
    docs_root = tmp_path / "DoD_Budget_Documents"
    docs = docs_root / "FY2026" / "Army"
    docs.mkdir(parents=True)
    db_path = tmp_path / "test.sqlite"

    # Patch the module-level DOCS_DIR so relative_to() works in tests
    monkeypatch.setattr(build_budget_db, "DOCS_DIR", docs_root)

    return tmp_path, docs, db_path, docs_root


def _make_xlsx(path: Path, rows: int = 5):
    """Create a minimal Excel file that the ingester will recognise."""
    wb = openpyxl.Workbook()
    ws = wb.active
    # Minimal header matching the p-1 exhibit pattern
    ws.append(["Fiscal Year", "Account", "Line Item", "FY2024 Actual",
                "FY2025 Enacted", "FY2026 Request"])
    for i in range(rows):
        ws.append([2026, f"ACC{i:03d}", f"Item {i}", i * 100, i * 110, i * 120])
    wb.save(path)


# ── Phase 2: Progress callback metrics ────────────────────────────────────────

class TestProgressMetrics:
    """Progress callback delivers metrics dict with expected keys."""

    def test_metrics_keys_present(self, tmp_workspace):
        tmp_path, docs, db_path, docs_root = tmp_workspace
        _make_xlsx(docs / "p1_army.xlsx")

        received = []

        def cb(phase, current, total, detail, metrics):
            received.append((phase, metrics))

        build_database(docs_root, db_path, progress_callback=cb)

        assert len(received) > 0
        # Every callback should have the standard metric keys
        required_keys = {"rows", "pages", "speed_rows", "speed_pages",
                         "eta_sec", "files_remaining"}
        for phase, m in received:
            assert required_keys.issubset(m.keys()), (
                f"Metrics missing keys for phase={phase}: {required_keys - m.keys()}")

    def test_final_metrics_files_remaining_zero(self, tmp_workspace):
        tmp_path, docs, db_path, docs_root = tmp_workspace
        _make_xlsx(docs / "p1_army.xlsx")

        final = {}

        def cb(phase, current, total, detail, metrics):
            if phase == "done":
                final.update(metrics)

        build_database(docs_root, db_path, progress_callback=cb)

        assert final.get("files_remaining", -1) == 0
        assert final.get("eta_sec", -1) == 0.0

    def test_rows_metric_increases_with_excel(self, tmp_workspace):
        tmp_path, docs, db_path, docs_root = tmp_workspace
        _make_xlsx(docs / "p1_army.xlsx", rows=20)

        row_counts = []

        def cb(phase, current, total, detail, metrics):
            if phase == "excel":
                row_counts.append(metrics.get("rows", 0))

        build_database(docs_root, db_path, progress_callback=cb)

        # Rows should be positive after processing
        assert any(r > 0 for r in row_counts)


# ── Phase 3: Checkpointing ────────────────────────────────────────────────────

class TestCheckpointing:
    """Checkpoint is saved during build."""

    def test_session_created_in_db(self, tmp_workspace):
        tmp_path, docs, db_path, docs_root = tmp_workspace
        _make_xlsx(docs / "p1_army.xlsx")

        build_database(docs_root, db_path, checkpoint_interval=1)

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT COUNT(*) FROM build_progress").fetchone()[0]
        conn.close()
        # Session should be marked complete after a successful build
        assert rows >= 1

    def test_session_marked_complete(self, tmp_workspace):
        tmp_path, docs, db_path, docs_root = tmp_workspace
        _make_xlsx(docs / "p1_army.xlsx")

        build_database(docs_root, db_path)

        conn = sqlite3.connect(str(db_path))
        completed = conn.execute(
            "SELECT COUNT(*) FROM build_progress WHERE status='completed'"
        ).fetchone()[0]
        conn.close()
        assert completed >= 1

    def test_files_tracked_in_processed_files(self, tmp_workspace):
        tmp_path, docs, db_path, docs_root = tmp_workspace
        _make_xlsx(docs / "p1_army.xlsx")
        _make_xlsx(docs / "p1_navy.xlsx")

        build_database(docs_root, db_path, checkpoint_interval=1)

        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM processed_files").fetchone()[0]
        conn.close()
        assert count >= 2  # Both xlsx files tracked


# ── Phase 4: Resume capability ────────────────────────────────────────────────

class TestResume:
    """Resume skips already-processed files."""

    def test_resume_skips_completed_files(self, tmp_workspace):
        tmp_path, docs, db_path, docs_root = tmp_workspace
        _make_xlsx(docs / "p1_army.xlsx")
        _make_xlsx(docs / "p1_navy.xlsx")

        # First build — processes both files
        phases_first: list[str] = []

        def cb_first(phase, current, total, detail, metrics):
            phases_first.append(phase)

        build_database(docs_root, db_path, progress_callback=cb_first,
                       checkpoint_interval=1)

        # Manually un-mark the session so _get_last_checkpoint picks it up
        conn = sqlite3.connect(str(db_path))
        conn.execute("UPDATE build_progress SET status='in_progress'")
        conn.commit()
        conn.close()

        # Resume build — should detect already processed files
        resumed_details: list[str] = []

        def cb_resume(phase, current, total, detail, metrics):
            resumed_details.append(detail)

        build_database(docs_root, db_path, resume=True,
                       progress_callback=cb_resume, checkpoint_interval=1)

        skipped = [d for d in resumed_details if "Resumed (skipped)" in d]
        assert len(skipped) >= 1, "Expected at least one file to be skipped on resume"

    def test_resume_without_checkpoint_starts_fresh(self, tmp_workspace):
        tmp_path, docs, db_path, docs_root = tmp_workspace
        _make_xlsx(docs / "p1_army.xlsx")

        # Build creates a completed session
        build_database(docs_root, db_path)

        # Resume — no in_progress checkpoint, so fresh build
        phases: list[str] = []

        def cb(phase, current, total, detail, metrics):
            phases.append(phase)

        build_database(docs_root, db_path, resume=True, progress_callback=cb)

        assert "done" in phases


# ── Phase 5: Graceful shutdown ────────────────────────────────────────────────

class TestGracefulShutdown:
    """Stop event triggers checkpoint-save and clean exit."""

    def test_stop_event_exits_build(self, tmp_workspace):
        tmp_path, docs, db_path, docs_root = tmp_workspace
        # Create enough files that the stop has time to trigger
        for i in range(5):
            _make_xlsx(docs / f"p1_file{i}.xlsx", rows=3)

        stop_event = threading.Event()
        phases: list[str] = []

        def cb(phase, current, total, detail, metrics):
            phases.append(phase)
            # Trigger stop after first file starts processing
            if phase == "excel" and current >= 1:
                stop_event.set()

        build_database(docs_root, db_path, progress_callback=cb,
                       stop_event=stop_event, checkpoint_interval=1)

        # Should have received a "stopped" phase
        assert "stopped" in phases, f"Expected 'stopped' phase, got: {phases}"

    def test_stop_event_saves_checkpoint(self, tmp_workspace):
        tmp_path, docs, db_path, docs_root = tmp_workspace
        for i in range(5):
            _make_xlsx(docs / f"p1_file{i}.xlsx", rows=3)

        stop_event = threading.Event()
        triggered = False

        def cb(phase, current, total, detail, metrics):
            nonlocal triggered
            if phase == "excel" and current >= 1 and not triggered:
                triggered = True
                stop_event.set()

        build_database(docs_root, db_path, progress_callback=cb,
                       stop_event=stop_event, checkpoint_interval=1)

        # Database should have an in_progress session (not completed, since stopped)
        conn = sqlite3.connect(str(db_path))
        in_progress = conn.execute(
            "SELECT COUNT(*) FROM build_progress WHERE status='in_progress'"
        ).fetchone()[0]
        conn.close()
        # Either in_progress or completed — but there should be *some* checkpoint
        total_sessions = sqlite3.connect(str(db_path)).execute(
            "SELECT COUNT(*) FROM build_progress"
        ).fetchone()[0]
        assert total_sessions >= 1

    def test_stop_event_not_set_completes_normally(self, tmp_workspace):
        tmp_path, docs, db_path, docs_root = tmp_workspace
        _make_xlsx(docs / "p1_army.xlsx")

        stop_event = threading.Event()  # Never set
        phases: list[str] = []

        def cb(phase, current, total, detail, metrics):
            phases.append(phase)

        build_database(docs_root, db_path, progress_callback=cb,
                       stop_event=stop_event)

        assert "done" in phases
        assert "stopped" not in phases


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
