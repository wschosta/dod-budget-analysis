"""
Tests for refresh_data.py — RefreshWorkflow

Verifies workflow orchestration, dry-run mode, stage sequencing,
logging behaviour, and webhook notification logic without network calls.
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from refresh_data import RefreshWorkflow


# ── RefreshWorkflow initialisation ────────────────────────────────────────────

class TestRefreshWorkflowInit:
    def test_defaults(self):
        wf = RefreshWorkflow()
        assert wf.verbose is False
        assert wf.dry_run is False
        assert wf.workers == 4
        assert wf.notify_url is None
        assert wf.db_path == Path("dod_budget.sqlite")
        assert wf.results == {}

    def test_custom_params(self):
        wf = RefreshWorkflow(
            verbose=True, dry_run=True, workers=8,
            notify_url="https://hooks.example.com/notify",
            db_path="/tmp/test.sqlite",
        )
        assert wf.verbose is True
        assert wf.dry_run is True
        assert wf.workers == 8
        assert wf.notify_url == "https://hooks.example.com/notify"
        assert wf.db_path == Path("/tmp/test.sqlite")


# ── Logging ───────────────────────────────────────────────────────────────────

class TestLogging:
    def test_log_info(self, capsys):
        wf = RefreshWorkflow()
        wf.log("hello")
        out = capsys.readouterr().out
        assert "hello" in out
        assert "] " in out  # has timestamp

    def test_log_warn(self, capsys):
        wf = RefreshWorkflow()
        wf.log("caution", "warn")
        assert "WARNING" in capsys.readouterr().out

    def test_log_error(self, capsys):
        wf = RefreshWorkflow()
        wf.log("bad thing", "error")
        assert "ERROR" in capsys.readouterr().out

    def test_log_ok(self, capsys):
        wf = RefreshWorkflow()
        wf.log("success", "ok")
        out = capsys.readouterr().out
        assert "success" in out

    def test_log_detail_verbose(self, capsys):
        wf = RefreshWorkflow(verbose=True)
        wf.log("details here", "detail")
        assert "details here" in capsys.readouterr().out

    def test_log_detail_not_verbose(self, capsys):
        wf = RefreshWorkflow(verbose=False)
        wf.log("details here", "detail")
        assert capsys.readouterr().out == ""


# ── run_command ───────────────────────────────────────────────────────────────

class TestRunCommand:
    def test_dry_run_returns_true(self, capsys):
        wf = RefreshWorkflow(dry_run=True, verbose=True)
        result = wf.run_command(["echo", "hi"], "test echo")
        assert result is True
        out = capsys.readouterr().out
        assert "DRY RUN" in out

    @patch("refresh_data.subprocess.run")
    def test_success(self, mock_run, capsys):
        mock_run.return_value = MagicMock(returncode=0)
        wf = RefreshWorkflow()
        result = wf.run_command(["echo", "hi"], "test echo")
        assert result is True
        mock_run.assert_called_once()

    @patch("refresh_data.subprocess.run")
    def test_failure_exit_code(self, mock_run, capsys):
        mock_run.return_value = MagicMock(returncode=1)
        wf = RefreshWorkflow()
        result = wf.run_command(["false"], "will fail")
        assert result is False
        assert "Failed" in capsys.readouterr().out

    @patch("refresh_data.subprocess.run", side_effect=Exception("boom"))
    def test_exception(self, mock_run, capsys):
        wf = RefreshWorkflow()
        result = wf.run_command(["bad"], "broken cmd")
        assert result is False
        assert "Exception" in capsys.readouterr().out


# ── Individual stages in dry-run mode ─────────────────────────────────────────

class TestStagesDryRun:
    def test_stage_1_dry_run(self, capsys):
        wf = RefreshWorkflow(dry_run=True)
        assert wf.stage_1_download([2026], ["army"]) is True
        assert wf.results["download"] == "completed"

    def test_stage_2_dry_run(self, capsys):
        wf = RefreshWorkflow(dry_run=True)
        assert wf.stage_2_build() is True
        assert wf.results["build"] == "completed"

    def test_stage_3_dry_run(self, capsys):
        wf = RefreshWorkflow(dry_run=True)
        assert wf.stage_3_validate() is True
        assert wf.results["validate"] == "completed"

    def test_stage_4_dry_run(self, capsys):
        wf = RefreshWorkflow(dry_run=True)
        assert wf.stage_4_report() is True
        assert wf.results["report"] == "completed"


# ── Full workflow dry-run ─────────────────────────────────────────────────────

class TestFullWorkflowDryRun:
    def test_dry_run_returns_zero(self, capsys):
        wf = RefreshWorkflow(dry_run=True)
        exit_code = wf.run([2026], ["all"])
        assert exit_code == 0
        assert wf.results["download"] == "completed"
        assert wf.results["build"] == "completed"
        assert wf.results["validate"] == "completed"
        assert wf.results["report"] == "completed"

    def test_dry_run_populates_start_time(self):
        wf = RefreshWorkflow(dry_run=True)
        wf.run([2026], ["all"])
        assert wf.start_time is not None


# ── Notification ──────────────────────────────────────────────────────────────

class TestNotification:
    @patch("refresh_data.urllib.request.urlopen")
    def test_sends_notification(self, mock_urlopen):
        wf = RefreshWorkflow(dry_run=True, notify_url="https://hooks.example.com/wh")
        wf.results = {"download": "completed"}
        wf._send_notification(True, 42.5)
        mock_urlopen.assert_called_once()
        # Inspect the request body
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        assert body["workflow_success"] is True
        assert body["elapsed_seconds"] == 42.5
        assert "succeeded" in body["text"]

    @patch("refresh_data.urllib.request.urlopen", side_effect=Exception("network down"))
    def test_notification_failure_is_non_fatal(self, mock_urlopen, capsys):
        wf = RefreshWorkflow(dry_run=True, notify_url="https://hooks.example.com/wh")
        wf.results = {}
        wf._send_notification(False, 10.0)
        out = capsys.readouterr().out
        assert "non-fatal" in out

    def test_workflow_calls_notify_when_url_set(self, capsys):
        wf = RefreshWorkflow(dry_run=True, notify_url="https://hooks.example.com/wh")
        with patch.object(wf, "_send_notification") as mock_notify:
            wf.run([2026], ["all"])
            mock_notify.assert_called_once()

    def test_workflow_skips_notify_when_no_url(self, capsys):
        wf = RefreshWorkflow(dry_run=True, notify_url=None)
        with patch.object(wf, "_send_notification") as mock_notify:
            wf.run([2026], ["all"])
            mock_notify.assert_not_called()


# ── stage_4_report missing db ─────────────────────────────────────────────────

class TestStage4Report:
    def test_missing_db_returns_false(self, tmp_path, capsys):
        wf = RefreshWorkflow(db_path=str(tmp_path / "nonexistent.sqlite"))
        result = wf.stage_4_report()
        assert result is False
        assert wf.results["report"] == "skipped"
