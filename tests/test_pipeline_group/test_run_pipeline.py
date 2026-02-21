"""Tests for the unified pipeline runner (run_pipeline.py)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import run_pipeline


# ── Helpers ───────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clean_state(tmp_path, monkeypatch):
    """Reset module-level state and redirect progress file to tmp_path."""
    run_pipeline._completed_steps.clear()
    monkeypatch.setattr(run_pipeline, "_PROGRESS_FILE", tmp_path / "pipeline_progress.json")
    yield
    run_pipeline._completed_steps.clear()


def _make_db(path: Path) -> None:
    """Create a minimal SQLite DB at `path`."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE test (id INTEGER)")
    conn.close()


# ── _backup_db / _rollback_db tests ──────────────────────────────────────────


class TestBackupRollback:
    def test_backup_creates_copy(self, tmp_path):
        db = tmp_path / "test.sqlite"
        _make_db(db)
        backup = run_pipeline._backup_db(db)
        assert backup is not None
        assert backup.exists()
        assert backup.suffix == ".bak"
        assert backup.stat().st_size == db.stat().st_size

    def test_backup_no_existing_db(self, tmp_path):
        db = tmp_path / "nonexistent.sqlite"
        backup = run_pipeline._backup_db(db)
        assert backup is None

    def test_rollback_restores(self, tmp_path):
        db = tmp_path / "test.sqlite"
        _make_db(db)
        backup = run_pipeline._backup_db(db)
        # Modify the DB
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE extra (val TEXT)")
        conn.close()
        # Rollback
        restored = run_pipeline._rollback_db(db, backup)
        assert restored is True
        # Verify extra table is gone
        conn = sqlite3.connect(db)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        conn.close()
        assert "extra" not in tables

    def test_rollback_no_backup(self, tmp_path):
        db = tmp_path / "test.sqlite"
        result = run_pipeline._rollback_db(db, None)
        assert result is False

    def test_rollback_missing_backup_file(self, tmp_path):
        db = tmp_path / "test.sqlite"
        missing = tmp_path / "missing.bak"
        result = run_pipeline._rollback_db(db, missing)
        assert result is False

    def test_cleanup_backup(self, tmp_path):
        db = tmp_path / "test.sqlite"
        _make_db(db)
        backup = run_pipeline._backup_db(db)
        assert backup.exists()
        run_pipeline._cleanup_backup(backup)
        assert not backup.exists()

    def test_cleanup_backup_none(self):
        # Should not raise
        run_pipeline._cleanup_backup(None)


# ── Progress tracking tests ──────────────────────────────────────────────────


class TestProgressTracking:
    def test_write_progress_creates_json(self, tmp_path):
        run_pipeline._write_progress("build", "running", 1.5, "building db")
        progress_file = tmp_path / "pipeline_progress.json"
        assert progress_file.exists()
        data = json.loads(progress_file.read_text())
        assert data["current_step"] == "build"
        assert data["status"] == "running"
        assert data["elapsed_seconds"] == 1.5
        assert data["detail"] == "building db"
        assert "timestamp" in data
        assert "steps_completed" in data

    def test_write_progress_includes_completed_steps(self, tmp_path):
        run_pipeline._completed_steps["step1"] = "completed in 2.0s"
        run_pipeline._write_progress("step2", "running", 0)
        data = json.loads((tmp_path / "pipeline_progress.json").read_text())
        assert data["steps_completed"]["step1"] == "completed in 2.0s"

    def test_clear_progress_removes_file(self, tmp_path):
        run_pipeline._write_progress("build", "running", 0)
        assert (tmp_path / "pipeline_progress.json").exists()
        run_pipeline._clear_progress()
        assert not (tmp_path / "pipeline_progress.json").exists()

    def test_clear_progress_no_file(self):
        # Should not raise
        run_pipeline._clear_progress()


# ── _run_step tests ──────────────────────────────────────────────────────────


class TestRunStep:
    def test_success(self):
        fn = MagicMock(return_value={"rows": 100})
        ok, result = run_pipeline._run_step("test step", fn, "arg1", key="val")
        assert ok is True
        assert result == {"rows": 100}
        fn.assert_called_once_with("arg1", key="val")
        assert "test step" in run_pipeline._completed_steps

    def test_failure(self):
        fn = MagicMock(side_effect=FileNotFoundError("not found"))
        ok, result = run_pipeline._run_step("failing step", fn)
        assert ok is False
        assert result is None
        assert "failed" in run_pipeline._completed_steps["failing step"]


# ── _parse_args tests ────────────────────────────────────────────────────────


class TestParseArgs:
    def test_defaults(self):
        args = run_pipeline._parse_args([])
        assert args.db == "dod_budget.sqlite"
        assert args.download is False
        assert args.skip_validate is False
        assert args.skip_enrich is False
        assert args.rebuild is False
        assert args.use_staging is False
        assert args.no_rollback is False
        assert args.report is False
        assert args.report_path == "data_quality_report.json"

    def test_download_flags(self):
        args = run_pipeline._parse_args(["--download", "--years", "2026", "2025", "--sources", "all"])
        assert args.download is True
        assert args.years == ["2026", "2025"]
        assert args.sources == ["all"]

    def test_staging_flags(self):
        args = run_pipeline._parse_args(["--use-staging", "--staging-dir", "/tmp/stage"])
        assert args.use_staging is True
        assert args.staging_dir == "/tmp/stage"

    def test_report_flags(self):
        args = run_pipeline._parse_args(["--report", "--report-path", "my_report.json"])
        assert args.report is True
        assert args.report_path == "my_report.json"

    def test_rollback_flag(self):
        args = run_pipeline._parse_args(["--no-rollback"])
        assert args.no_rollback is True

    def test_enrich_phases(self):
        args = run_pipeline._parse_args(["--enrich-phases", "1,2,3"])
        assert args.enrich_phases == "1,2,3"


# ── _download_cmd tests ─────────────────────────────────────────────────────


class TestDownloadCmd:
    def test_basic(self):
        args = run_pipeline._parse_args(["--download"])
        cmd = run_pipeline._download_cmd(args)
        assert "--no-gui" in cmd
        assert str(run_pipeline.STEP_DOWNLOAD) in cmd

    def test_with_years_and_sources(self):
        args = run_pipeline._parse_args(["--download", "--years", "2026", "--sources", "army", "navy"])
        cmd = run_pipeline._download_cmd(args)
        assert "--years" in cmd
        assert "2026" in cmd
        assert "--sources" in cmd
        assert "army" in cmd
        assert "navy" in cmd


# ── main() integration tests ────────────────────────────────────────────────


class TestMainIntegration:
    """Test main() with mocked pipeline functions."""

    @patch("run_pipeline._backup_db", return_value=None)
    @patch("run_pipeline._cleanup_backup")
    @patch("run_pipeline._clear_progress")
    def test_skip_validate_and_enrich(self, mock_clear, mock_cleanup, mock_backup, tmp_path):
        """Skip both validate and enrich — only build runs."""
        db = tmp_path / "test.sqlite"
        docs = tmp_path / "docs"
        docs.mkdir()

        with patch("pipeline.builder.build_database", return_value={"rows": 10}) as mock_build:
            rc = run_pipeline.main([
                "--db", str(db),
                "--docs", str(docs),
                "--skip-validate",
                "--skip-enrich",
            ])

        assert rc == 0
        mock_build.assert_called_once()

    @patch("run_pipeline._backup_db", return_value=None)
    @patch("run_pipeline._cleanup_backup")
    @patch("run_pipeline._clear_progress")
    def test_skip_validate_only(self, mock_clear, mock_cleanup, mock_backup, tmp_path):
        """Skip validate, run enrich."""
        db = tmp_path / "test.sqlite"
        docs = tmp_path / "docs"
        docs.mkdir()

        with (
            patch("pipeline.builder.build_database", return_value={"rows": 10}),
            patch("pipeline.enricher.enrich") as mock_enrich,
        ):
            rc = run_pipeline.main([
                "--db", str(db),
                "--docs", str(docs),
                "--skip-validate",
            ])

        assert rc == 0
        mock_enrich.assert_called_once()

    @patch("run_pipeline._backup_db", return_value=None)
    @patch("run_pipeline._cleanup_backup")
    @patch("run_pipeline._clear_progress")
    def test_skip_enrich_only(self, mock_clear, mock_cleanup, mock_backup, tmp_path):
        """Run validate, skip enrich."""
        db = tmp_path / "test.sqlite"
        docs = tmp_path / "docs"
        docs.mkdir()

        val_result = {"exit_code": 0, "total_checks": 5, "total_warnings": 0, "total_failures": 0, "checks": []}

        with (
            patch("pipeline.builder.build_database", return_value={"rows": 10}),
            patch("pipeline.validator.validate_all", return_value=val_result) as mock_val,
        ):
            rc = run_pipeline.main([
                "--db", str(db),
                "--docs", str(docs),
                "--skip-enrich",
            ])

        assert rc == 0
        mock_val.assert_called_once()

    @patch("run_pipeline._backup_db")
    @patch("run_pipeline._rollback_db")
    @patch("run_pipeline._clear_progress")
    def test_build_failure_triggers_rollback(self, mock_clear, mock_rollback, mock_backup, tmp_path):
        """Build failure should trigger rollback."""
        db = tmp_path / "test.sqlite"
        docs = tmp_path / "docs"
        docs.mkdir()
        backup_path = tmp_path / "test.sqlite.bak"
        mock_backup.return_value = backup_path

        with patch("pipeline.builder.build_database", side_effect=RuntimeError("build failed")):
            rc = run_pipeline.main([
                "--db", str(db),
                "--docs", str(docs),
                "--skip-validate",
                "--skip-enrich",
            ])

        assert rc == 1
        mock_rollback.assert_called_once_with(db, backup_path)

    @patch("run_pipeline._backup_db")
    @patch("run_pipeline._rollback_db")
    @patch("run_pipeline._clear_progress")
    def test_build_failure_no_rollback_flag(self, mock_clear, mock_rollback, mock_backup, tmp_path):
        """--no-rollback should suppress rollback on failure."""
        db = tmp_path / "test.sqlite"
        docs = tmp_path / "docs"
        docs.mkdir()

        with patch("pipeline.builder.build_database", side_effect=RuntimeError("build failed")):
            rc = run_pipeline.main([
                "--db", str(db),
                "--docs", str(docs),
                "--skip-validate",
                "--skip-enrich",
                "--no-rollback",
            ])

        assert rc == 1
        mock_backup.assert_not_called()
        mock_rollback.assert_not_called()

    @patch("run_pipeline._backup_db", return_value=None)
    @patch("run_pipeline._cleanup_backup")
    @patch("run_pipeline._clear_progress")
    def test_strict_validation_failure_aborts(self, mock_clear, mock_cleanup, mock_backup, tmp_path):
        """--strict should abort pipeline on validation failures."""
        db = tmp_path / "test.sqlite"
        docs = tmp_path / "docs"
        docs.mkdir()

        val_result = {"exit_code": 1, "total_checks": 5, "total_warnings": 0, "total_failures": 2, "checks": []}

        with (
            patch("pipeline.builder.build_database", return_value={"rows": 10}),
            patch("pipeline.validator.validate_all", return_value=val_result),
        ):
            rc = run_pipeline.main([
                "--db", str(db),
                "--docs", str(docs),
                "--strict",
                "--skip-enrich",
            ])

        assert rc == 1

    @patch("run_pipeline._run_subprocess", return_value=0)
    @patch("run_pipeline._backup_db", return_value=None)
    @patch("run_pipeline._cleanup_backup")
    @patch("run_pipeline._clear_progress")
    def test_download_flag_calls_subprocess(self, mock_clear, mock_cleanup, mock_backup, mock_sub, tmp_path):
        """--download should invoke subprocess for the downloader."""
        db = tmp_path / "test.sqlite"
        docs = tmp_path / "docs"
        docs.mkdir()

        with (
            patch("pipeline.builder.build_database", return_value={"rows": 10}),
            patch("pipeline.validator.validate_all", return_value={"exit_code": 0, "total_checks": 1, "total_warnings": 0, "total_failures": 0, "checks": []}),
            patch("pipeline.enricher.enrich"),
        ):
            rc = run_pipeline.main([
                "--db", str(db),
                "--docs", str(docs),
                "--download",
                "--years", "2026",
                "--sources", "all",
            ])

        assert rc == 0
        mock_sub.assert_called_once()
        call_args = mock_sub.call_args
        assert "Download" in call_args[0][0]

    @patch("run_pipeline._run_subprocess", return_value=1)
    def test_download_failure_aborts(self, mock_sub, tmp_path):
        """Failed download should abort pipeline."""
        db = tmp_path / "test.sqlite"
        docs = tmp_path / "docs"
        docs.mkdir()

        rc = run_pipeline.main([
            "--db", str(db),
            "--docs", str(docs),
            "--download",
            "--years", "2026",
        ])

        assert rc == 1

    @patch("run_pipeline._backup_db", return_value=None)
    @patch("run_pipeline._cleanup_backup")
    @patch("run_pipeline._clear_progress")
    def test_staging_mode(self, mock_clear, mock_cleanup, mock_backup, tmp_path):
        """--use-staging should call stage_all_files + load_staging_to_db."""
        db = tmp_path / "test.sqlite"
        docs = tmp_path / "docs"
        docs.mkdir()
        staging = tmp_path / "staging"

        stage_result = {"staged_count": 5, "skipped_count": 0, "error_count": 0}
        load_result = {"total_rows": 100, "total_pages": 50, "fy_columns": []}

        with (
            patch("pipeline.staging.stage_all_files", return_value=stage_result) as mock_stage,
            patch("pipeline.staging.load_staging_to_db", return_value=load_result) as mock_load,
            patch("pipeline.validator.validate_all", return_value={"exit_code": 0, "total_checks": 1, "total_warnings": 0, "total_failures": 0, "checks": []}),
            patch("pipeline.enricher.enrich"),
        ):
            rc = run_pipeline.main([
                "--db", str(db),
                "--docs", str(docs),
                "--use-staging",
                "--staging-dir", str(staging),
            ])

        assert rc == 0
        mock_stage.assert_called_once()
        mock_load.assert_called_once()

    @patch("run_pipeline._backup_db", return_value=None)
    @patch("run_pipeline._cleanup_backup")
    @patch("run_pipeline._clear_progress")
    def test_report_flag(self, mock_clear, mock_cleanup, mock_backup, tmp_path):
        """--report should call generate_quality_report."""
        db = tmp_path / "test.sqlite"
        docs = tmp_path / "docs"
        docs.mkdir()

        val_result = {"exit_code": 0, "total_checks": 5, "total_warnings": 0, "total_failures": 0, "checks": []}

        with (
            patch("pipeline.builder.build_database", return_value={"rows": 10}),
            patch("pipeline.validator.validate_all", return_value=val_result),
            patch("pipeline.validator.generate_quality_report", return_value={}) as mock_report,
            patch("pipeline.enricher.enrich"),
        ):
            rc = run_pipeline.main([
                "--db", str(db),
                "--docs", str(docs),
                "--report",
                "--report-path", str(tmp_path / "report.json"),
            ])

        assert rc == 0
        mock_report.assert_called_once()

    @patch("run_pipeline._backup_db", return_value=None)
    @patch("run_pipeline._cleanup_backup")
    @patch("run_pipeline._clear_progress")
    def test_full_pipeline_call_order(self, mock_clear, mock_cleanup, mock_backup, tmp_path):
        """Verify build -> validate -> enrich call order."""
        db = tmp_path / "test.sqlite"
        docs = tmp_path / "docs"
        docs.mkdir()
        call_order = []

        def track_build(**kw):
            call_order.append("build")
            return {"rows": 10}

        def track_validate(**kw):
            call_order.append("validate")
            return {"exit_code": 0, "total_checks": 1, "total_warnings": 0, "total_failures": 0, "checks": []}

        def track_enrich(**kw):
            call_order.append("enrich")

        with (
            patch("pipeline.builder.build_database", side_effect=track_build),
            patch("pipeline.validator.validate_all", side_effect=track_validate),
            patch("pipeline.enricher.enrich", side_effect=track_enrich),
        ):
            rc = run_pipeline.main([
                "--db", str(db),
                "--docs", str(docs),
            ])

        assert rc == 0
        assert call_order == ["build", "validate", "enrich"]

    @patch("run_pipeline._backup_db", return_value=None)
    @patch("run_pipeline._cleanup_backup")
    @patch("run_pipeline._clear_progress")
    def test_enrich_phases_parsing(self, mock_clear, mock_cleanup, mock_backup, tmp_path):
        """--enrich-phases should parse comma-separated values into a set."""
        db = tmp_path / "test.sqlite"
        docs = tmp_path / "docs"
        docs.mkdir()

        val_result = {"exit_code": 0, "total_checks": 1, "total_warnings": 0, "total_failures": 0, "checks": []}

        with (
            patch("pipeline.builder.build_database", return_value={"rows": 10}),
            patch("pipeline.validator.validate_all", return_value=val_result),
            patch("pipeline.enricher.enrich") as mock_enrich,
        ):
            rc = run_pipeline.main([
                "--db", str(db),
                "--docs", str(docs),
                "--enrich-phases", "1,3",
            ])

        assert rc == 0
        call_kwargs = mock_enrich.call_args[1]
        assert call_kwargs["phases"] == {1, 3}
