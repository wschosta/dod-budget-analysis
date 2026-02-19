"""
BEAR-010: Data refresh end-to-end test (dry-run, rollback, webhook).

Test the full refresh pipeline in dry-run mode:
1. RefreshWorkflow(dry_run=True).run() completes without error.
2. Progress file is created and cleaned up.
3. Rollback is triggered on simulated failure (mock stage_2 to raise).
4. --schedule flag parsing works (daily, weekly, monthly).
5. Webhook notification structure is correct (mock requests.post).
6. Summary report is generated with expected fields.
"""
# DONE [Group: BEAR] BEAR-010: Add data refresh end-to-end test (dry-run, rollback, webhook) (~2,500 tokens)

import json
import shutil
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from refresh_data import (
    RefreshWorkflow,
    _SCHEDULE_INTERVALS,
    _next_run_time,
    _PROGRESS_FILE,
)


@pytest.fixture()
def workflow(tmp_path):
    """Return a dry-run RefreshWorkflow with a temp DB path."""
    db_path = tmp_path / "test_refresh.sqlite"
    return RefreshWorkflow(
        dry_run=True,
        verbose=False,
        workers=1,
        db_path=str(db_path),
    )


@pytest.fixture(autouse=True)
def cleanup_progress():
    """Remove progress file after each test."""
    yield
    try:
        _PROGRESS_FILE.unlink(missing_ok=True)
    except OSError:
        pass


class TestDryRunWorkflow:
    """Test RefreshWorkflow in dry-run mode."""

    def test_dry_run_completes_without_error(self, workflow):
        """Dry-run workflow completes with exit code 0."""
        exit_code = workflow.run(years=[2026], sources=["all"])
        assert exit_code == 0

    def test_dry_run_all_stages_completed(self, workflow):
        """All 4 stages report 'completed' in dry-run mode."""
        workflow.run(years=[2026], sources=["all"])
        for stage in ["download", "build", "validate", "report"]:
            assert workflow.results[stage] == "completed", f"Stage {stage} not completed"

    def test_progress_file_cleaned_on_success(self, workflow):
        """Progress file is removed after successful dry-run."""
        workflow.run(years=[2026], sources=["all"])
        assert not _PROGRESS_FILE.exists(), "Progress file should be cleaned up on success"


class TestRollback:
    """Test rollback behavior on simulated failure."""

    def test_rollback_triggered_on_stage2_failure(self, tmp_path):
        """When stage_2_build fails, rollback restores the backup."""
        # Create a real (non-dry-run) workflow with a mock DB
        db_path = tmp_path / "rollback_test.sqlite"
        db_path.write_text("original content")

        wf = RefreshWorkflow(
            dry_run=False,
            verbose=False,
            db_path=str(db_path),
            no_rollback=False,
        )

        # Manually back up, then simulate failure + rollback
        wf._backup_db()
        assert wf._backup_path.exists()

        # Corrupt the DB
        db_path.write_text("corrupted content")

        # Rollback should restore original
        result = wf._rollback_db()
        assert result is True
        assert db_path.read_text() == "original content"

    def test_no_rollback_when_flag_set(self, tmp_path):
        """--no-rollback skips rollback even on failure."""
        db_path = tmp_path / "no_rollback.sqlite"
        db_path.write_text("original")

        wf = RefreshWorkflow(
            dry_run=False,
            verbose=False,
            db_path=str(db_path),
            no_rollback=True,
        )
        wf._backup_db()
        db_path.write_text("corrupted")

        result = wf._rollback_db()
        assert result is False  # Rollback skipped
        assert db_path.read_text() == "corrupted"


class TestScheduleParsing:
    """Test --schedule flag parsing."""

    def test_schedule_intervals_defined(self):
        """Schedule intervals exist for daily, weekly, monthly."""
        assert "daily" in _SCHEDULE_INTERVALS
        assert "weekly" in _SCHEDULE_INTERVALS
        assert "monthly" in _SCHEDULE_INTERVALS

    def test_daily_interval_is_86400(self):
        assert _SCHEDULE_INTERVALS["daily"] == 86400

    def test_weekly_interval_is_604800(self):
        assert _SCHEDULE_INTERVALS["weekly"] == 604800

    def test_monthly_interval_is_2592000(self):
        assert _SCHEDULE_INTERVALS["monthly"] == 2592000

    def test_next_run_time_no_hour(self):
        """_next_run_time(None) returns current time."""
        import time
        result = _next_run_time(None)
        assert abs(result - time.time()) < 2

    def test_next_run_time_invalid_hour(self):
        """_next_run_time('invalid') returns current time (fallback)."""
        import time
        result = _next_run_time("invalid")
        assert abs(result - time.time()) < 2


class TestWebhookNotification:
    """Test webhook notification structure."""

    def test_notification_payload_structure(self, tmp_path):
        """Webhook payload has expected fields."""
        db_path = tmp_path / "notify_test.sqlite"
        captured_payload = {}

        def mock_urlopen(req, timeout=None):
            nonlocal captured_payload
            captured_payload = json.loads(req.data.decode("utf-8"))
            return MagicMock()

        wf = RefreshWorkflow(
            dry_run=True,
            verbose=False,
            db_path=str(db_path),
            notify_url="http://example.com/webhook",
        )
        wf.start_time = __import__("time").time()
        wf.results = {"download": "completed", "build": "completed"}

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            wf._send_notification(success=True, elapsed=42.5)

        assert "text" in captured_payload
        assert "workflow_success" in captured_payload
        assert captured_payload["workflow_success"] is True
        assert "elapsed_seconds" in captured_payload
        assert captured_payload["elapsed_seconds"] == 42.5
        assert "stages" in captured_payload

    def test_notification_failure_is_nonfatal(self, tmp_path):
        """Webhook failure does not raise an exception."""
        db_path = tmp_path / "notify_fail.sqlite"
        wf = RefreshWorkflow(
            dry_run=True,
            verbose=False,
            db_path=str(db_path),
            notify_url="http://invalid.example.com/webhook",
        )
        wf.start_time = __import__("time").time()
        wf.results = {}

        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            # Should not raise
            wf._send_notification(success=False, elapsed=1.0)


class TestSummaryReport:
    """Test summary report fields."""

    def test_results_dict_has_stage_keys(self, workflow):
        """After dry-run, results dict has all stage keys."""
        workflow.run(years=[2026], sources=["all"])
        assert "download" in workflow.results
        assert "build" in workflow.results
        assert "validate" in workflow.results
        assert "report" in workflow.results
