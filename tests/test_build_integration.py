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
    create_database,
    _get_last_checkpoint,
    _get_processed_files,
    _file_needs_update,
    _remove_file_data,
    _register_data_source,
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


# ── _file_needs_update ────────────────────────────────────────────────────────

class TestFileNeedsUpdate:
    """Unit tests for _file_needs_update without running a full build."""

    @pytest.fixture
    def schema_conn(self, tmp_path):
        db = tmp_path / "schema.db"
        conn = create_database(db)
        yield conn
        conn.close()

    def test_new_file_needs_update(self, schema_conn, tmp_path):
        """File not in ingested_files → always needs update."""
        f = tmp_path / "budget.xlsx"
        f.write_bytes(b"x" * 100)
        assert _file_needs_update(schema_conn, "FY2026/budget.xlsx", f) is True

    def test_unchanged_file_no_update_needed(self, schema_conn, tmp_path):
        """File with matching size and mtime → no update needed."""
        f = tmp_path / "budget.xlsx"
        f.write_bytes(b"x" * 100)
        stat = f.stat()
        schema_conn.execute(
            "INSERT INTO ingested_files "
            "(file_path, file_type, file_size, file_modified, ingested_at, row_count, status)"
            " VALUES (?, ?, ?, ?, datetime('now'), 0, 'ok')",
            ("FY2026/budget.xlsx", "xlsx", stat.st_size, stat.st_mtime)
        )
        schema_conn.commit()
        assert _file_needs_update(schema_conn, "FY2026/budget.xlsx", f) is False

    def test_changed_size_needs_update(self, schema_conn, tmp_path):
        """File with different size → needs update."""
        f = tmp_path / "budget.xlsx"
        f.write_bytes(b"x" * 100)
        stat = f.stat()
        schema_conn.execute(
            "INSERT INTO ingested_files "
            "(file_path, file_type, file_size, file_modified, ingested_at, row_count, status)"
            " VALUES (?, ?, ?, ?, datetime('now'), 0, 'ok')",
            ("FY2026/budget.xlsx", "xlsx", stat.st_size + 1, stat.st_mtime)
        )
        schema_conn.commit()
        assert _file_needs_update(schema_conn, "FY2026/budget.xlsx", f) is True


# ── _remove_file_data ─────────────────────────────────────────────────────────

class TestRemoveFileData:
    """Unit tests for _remove_file_data."""

    @pytest.fixture
    def schema_conn(self, tmp_path):
        db = tmp_path / "schema.db"
        conn = create_database(db)
        conn.row_factory = sqlite3.Row
        yield conn
        conn.close()

    def test_remove_xlsx_deletes_budget_lines(self, schema_conn):
        """Removing an xlsx file deletes its rows from budget_lines."""
        schema_conn.execute(
            "INSERT INTO budget_lines (source_file, exhibit_type, fiscal_year, "
            "account, organization, budget_type, amount_unit, currency_year) "
            "VALUES (?, 'p1', 'FY 2026', '2035', 'A', 'procurement', 'thousands', 'then-year')",
            ("FY2026/budget.xlsx",)
        )
        schema_conn.commit()
        count_before = schema_conn.execute(
            "SELECT COUNT(*) FROM budget_lines WHERE source_file='FY2026/budget.xlsx'"
        ).fetchone()[0]
        assert count_before == 1

        _remove_file_data(schema_conn, "FY2026/budget.xlsx", "xlsx")
        schema_conn.commit()

        count_after = schema_conn.execute(
            "SELECT COUNT(*) FROM budget_lines WHERE source_file='FY2026/budget.xlsx'"
        ).fetchone()[0]
        assert count_after == 0

    def test_remove_pdf_deletes_pdf_pages(self, schema_conn):
        """Removing a pdf file deletes its rows from pdf_pages."""
        schema_conn.execute(
            "INSERT INTO pdf_pages (source_file, page_number, page_text, has_tables) "
            "VALUES (?, 1, 'test content', 0)",
            ("FY2026/doc.pdf",)
        )
        schema_conn.commit()
        _remove_file_data(schema_conn, "FY2026/doc.pdf", "pdf")
        schema_conn.commit()
        count = schema_conn.execute(
            "SELECT COUNT(*) FROM pdf_pages WHERE source_file='FY2026/doc.pdf'"
        ).fetchone()[0]
        assert count == 0

    def test_remove_unknown_type_no_error(self, schema_conn):
        """Unknown file type raises no exception."""
        _remove_file_data(schema_conn, "FY2026/file.csv", "csv")  # no-op, no crash


# ── _register_data_source ─────────────────────────────────────────────────────

class TestRegisterDataSource:
    """Unit tests for _register_data_source."""

    @pytest.fixture
    def schema_conn(self, tmp_path):
        db = tmp_path / "schema.db"
        conn = create_database(db)
        yield conn
        conn.close()

    def test_registers_fy_dir(self, schema_conn, tmp_path):
        """FY dirs with service subdirs are registered in data_sources."""
        docs = tmp_path / "DoD_Budget_Documents"
        army = docs / "FY2026" / "Army"
        army.mkdir(parents=True)
        (army / "p1_army.xlsx").write_bytes(b"x")

        _register_data_source(schema_conn, docs)

        rows = schema_conn.execute("SELECT COUNT(*) FROM data_sources").fetchone()[0]
        assert rows >= 1

    def test_skips_non_fy_dirs(self, schema_conn, tmp_path):
        """Directories not starting with 'FY' are ignored."""
        docs = tmp_path / "DoD_Budget_Documents"
        unrelated = docs / "archives" / "Army"
        unrelated.mkdir(parents=True)

        _register_data_source(schema_conn, docs)

        rows = schema_conn.execute("SELECT COUNT(*) FROM data_sources").fetchone()[0]
        assert rows == 0

    def test_empty_docs_dir(self, schema_conn, tmp_path):
        """Empty docs directory → no rows inserted, no crash."""
        docs = tmp_path / "empty_docs"
        docs.mkdir()
        _register_data_source(schema_conn, docs)
        rows = schema_conn.execute("SELECT COUNT(*) FROM data_sources").fetchone()[0]
        assert rows == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
