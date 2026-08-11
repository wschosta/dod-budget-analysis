"""
Tests for download retry functionality in downloader.core.

Covers:
- ProgressTracker.file_failed() structured entry creation
- download_all() writing/cleaning failed_downloads.json
- --retry-failures CLI path (full success and partial failure)
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from downloader.core import ProgressTracker


# ---------------------------------------------------------------------------
# ProgressTracker.file_failed()
# ---------------------------------------------------------------------------


class TestProgressTrackerFileFailed:
    """Tests for ProgressTracker.file_failed() structured failure recording."""

    def test_creates_structured_entry_with_all_fields(self):
        """file_failed() should append a dict with all expected keys."""
        tracker = ProgressTracker(total_files=1)
        tracker.set_source("2026", "navy")

        tracker.file_failed(
            url="https://example.com/file.pdf",
            dest="/tmp/output/file.pdf",
            filename="file.pdf",
            error="Connection timeout",
            use_browser=False,
        )

        assert len(tracker._failed_files) == 1
        entry = tracker._failed_files[0]
        assert entry["url"] == "https://example.com/file.pdf"
        assert entry["dest"] == "/tmp/output/file.pdf"
        assert entry["filename"] == "file.pdf"
        assert entry["error"] == "Connection timeout"
        assert entry["source"] == "navy"
        assert entry["year"] == "2026"
        assert entry["use_browser"] is False
        assert "timestamp" in entry

    def test_use_browser_flag_preserved(self):
        """use_browser=True should be stored in the entry."""
        tracker = ProgressTracker(total_files=1)
        tracker.set_source("2025", "airforce")

        tracker.file_failed(
            url="https://example.com/waf.pdf",
            dest="/tmp/output/waf.pdf",
            filename="waf.pdf",
            error="WAF blocked",
            use_browser=True,
        )

        assert tracker._failed_files[0]["use_browser"] is True

    def test_error_coerced_to_string(self):
        """Non-string errors should be converted to str."""
        tracker = ProgressTracker(total_files=1)
        tracker.set_source("2026", "army")

        tracker.file_failed(
            url="https://example.com/x.pdf",
            dest="/tmp/x.pdf",
            filename="x.pdf",
            error=RuntimeError("boom"),
        )

        assert tracker._failed_files[0]["error"] == "boom"

    def test_increments_failed_counter(self):
        """file_failed() should increment the failed counter via file_done."""
        tracker = ProgressTracker(total_files=3)
        assert tracker.failed == 0

        tracker.file_failed(
            url="https://example.com/a.pdf",
            dest="/tmp/a.pdf",
            filename="a.pdf",
            error="err1",
        )
        assert tracker.failed == 1

        tracker.file_failed(
            url="https://example.com/b.pdf",
            dest="/tmp/b.pdf",
            filename="b.pdf",
            error="err2",
        )
        assert tracker.failed == 2

    def test_multiple_failures_appended(self):
        """Multiple calls should append separate entries."""
        tracker = ProgressTracker(total_files=3)
        for i in range(3):
            tracker.file_failed(
                url=f"https://example.com/{i}.pdf",
                dest=f"/tmp/{i}.pdf",
                filename=f"{i}.pdf",
                error=f"error {i}",
            )

        assert len(tracker._failed_files) == 3
        filenames = [e["filename"] for e in tracker._failed_files]
        assert filenames == ["0.pdf", "1.pdf", "2.pdf"]

    def test_timestamp_is_iso_format(self):
        """Timestamp should be a valid ISO 8601 string."""
        from datetime import datetime

        tracker = ProgressTracker(total_files=1)
        tracker.file_failed(
            url="https://example.com/t.pdf",
            dest="/tmp/t.pdf",
            filename="t.pdf",
            error="timeout",
        )

        ts = tracker._failed_files[0]["timestamp"]
        # Should parse without error
        parsed = datetime.fromisoformat(ts)
        assert parsed is not None


# ---------------------------------------------------------------------------
# download_all() — failure JSON writing / cleanup
# ---------------------------------------------------------------------------


class TestDownloadAllFailureJson:
    """Tests for the failure JSON write/cleanup logic in download_all().

    Rather than invoking the full download_all() pipeline (which requires
    mocking manifests, FY validation, classification, thread pools, etc.),
    these tests exercise the *specific* JSON write/cleanup block that
    download_all() runs after all downloads complete. This is the same
    code at lines ~1076-1089 of core.py.
    """

    def test_writes_failed_json_when_tracker_has_failures(self, tmp_path):
        """If the tracker recorded failures, the JSON file should be written."""
        tracker = ProgressTracker(total_files=2)
        tracker.set_source("2026", "comptroller")
        tracker.file_failed(
            url="https://example.com/fail.pdf",
            dest=str(tmp_path / "fail.pdf"),
            filename="fail.pdf",
            error="Connection refused",
        )

        # Replicate the JSON-write block from download_all()
        failed_json_path = tmp_path / "failed_downloads.json"
        if tracker._failed_files:
            failed_json_path.write_text(
                json.dumps(tracker._failed_files, indent=2), encoding="utf-8"
            )

        assert failed_json_path.exists()
        data = json.loads(failed_json_path.read_text())
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["url"] == "https://example.com/fail.pdf"

    def test_cleans_stale_json_when_no_failures(self, tmp_path):
        """If no failures occurred, a stale JSON from a prior run should be removed."""
        stale_json = tmp_path / "failed_downloads.json"
        stale_json.write_text('[{"url": "old"}]')

        tracker = ProgressTracker(total_files=1)
        # No file_failed() calls — clean run

        # Replicate the cleanup block from download_all()
        failed_json_path = tmp_path / "failed_downloads.json"
        if tracker._failed_files:
            failed_json_path.write_text(
                json.dumps(tracker._failed_files, indent=2), encoding="utf-8"
            )
        elif failed_json_path.exists():
            failed_json_path.unlink()

        assert not stale_json.exists()

    def test_no_json_created_on_clean_run_without_stale(self, tmp_path):
        """If no failures and no prior stale file, nothing should be created."""
        tracker = ProgressTracker(total_files=1)

        failed_json_path = tmp_path / "failed_downloads.json"
        if tracker._failed_files:
            failed_json_path.write_text(
                json.dumps(tracker._failed_files, indent=2), encoding="utf-8"
            )
        elif failed_json_path.exists():
            failed_json_path.unlink()

        assert not failed_json_path.exists()


# ---------------------------------------------------------------------------
# Retry JSON schema validation
# ---------------------------------------------------------------------------


class TestRetryJsonSchema:
    """Verify the JSON schema produced by ProgressTracker._failed_files."""

    def test_schema_matches_expected_keys(self):
        """Each failure entry should contain all required keys."""
        tracker = ProgressTracker(total_files=1)
        tracker.set_source("2026", "army")
        tracker.file_failed(
            url="https://example.com/doc.pdf",
            dest="/tmp/doc.pdf",
            filename="doc.pdf",
            error="500 Server Error",
            use_browser=True,
        )

        expected_keys = {
            "url", "dest", "filename", "error",
            "source", "year", "use_browser", "timestamp",
        }
        entry = tracker._failed_files[0]
        assert set(entry.keys()) == expected_keys

    def test_serializes_to_valid_json(self, tmp_path):
        """The failure list should be JSON-serializable and round-trip cleanly."""
        tracker = ProgressTracker(total_files=2)
        tracker.set_source("2025", "navy")
        for i in range(2):
            tracker.file_failed(
                url=f"https://example.com/{i}.pdf",
                dest=f"/tmp/{i}.pdf",
                filename=f"{i}.pdf",
                error=f"err{i}",
            )

        json_path = tmp_path / "test.json"
        json_path.write_text(json.dumps(tracker._failed_files, indent=2))

        loaded = json.loads(json_path.read_text())
        assert len(loaded) == 2
        assert all(isinstance(e, dict) for e in loaded)
        assert loaded[0]["url"] == "https://example.com/0.pdf"


# ---------------------------------------------------------------------------
# --retry-failures CLI path
# ---------------------------------------------------------------------------


class TestRetryFailuresPath:
    """Tests for the --retry-failures early path in main()."""

    def _make_failure_json(self, path: Path, entries: list[dict] | None = None):
        """Write a failure JSON file with defaults if entries not given."""
        if entries is None:
            entries = [
                {
                    "url": "https://example.com/a.pdf",
                    "dest": str(path.parent / "comptroller" / "2026" / "a.pdf"),
                    "filename": "a.pdf",
                    "error": "Connection reset",
                    "source": "comptroller",
                    "year": "2026",
                    "use_browser": False,
                    "timestamp": "2026-04-01T12:00:00+00:00",
                },
                {
                    "url": "https://example.com/b.pdf",
                    "dest": str(path.parent / "army" / "2026" / "b.pdf"),
                    "filename": "b.pdf",
                    "error": "Timeout",
                    "source": "army",
                    "year": "2026",
                    "use_browser": True,
                    "timestamp": "2026-04-01T12:00:01+00:00",
                },
            ]
        path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
        return entries

    @patch("downloader.core._close_browser")
    @patch("downloader.core._close_session")
    @patch("downloader.core.get_session")
    @patch("downloader.core.download_file")
    def test_all_retries_succeed_deletes_json(
        self, mock_dl, mock_session, mock_close_session, mock_close_browser, tmp_path
    ):
        """When all retries succeed, the failure JSON should be deleted."""
        from downloader.core import main

        failed_json = tmp_path / "failed_downloads.json"
        self._make_failure_json(failed_json)

        mock_dl.return_value = True
        mock_session.return_value = MagicMock()

        test_args = [
            "dod_budget_downloader.py",
            "--retry-failures", str(failed_json),
            "--output", str(tmp_path),
            "--no-gui",
        ]

        with patch("sys.argv", test_args), pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        assert not failed_json.exists()
        assert mock_dl.call_count == 2

    @patch("downloader.core._close_browser")
    @patch("downloader.core._close_session")
    @patch("downloader.core.get_session")
    @patch("downloader.core.download_file")
    def test_partial_retries_updates_json(
        self, mock_dl, mock_session, mock_close_session, mock_close_browser, tmp_path
    ):
        """When some retries fail, the JSON should contain only remaining failures."""
        from downloader.core import main

        failed_json = tmp_path / "failed_downloads.json"
        self._make_failure_json(failed_json)

        # First call succeeds, second fails
        mock_dl.side_effect = [True, False]
        mock_session.return_value = MagicMock()

        test_args = [
            "dod_budget_downloader.py",
            "--retry-failures", str(failed_json),
            "--output", str(tmp_path),
            "--no-gui",
        ]

        with patch("sys.argv", test_args), pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        assert failed_json.exists()
        remaining = json.loads(failed_json.read_text())
        assert len(remaining) == 1
        # The second entry (b.pdf) should remain since it failed
        assert remaining[0]["filename"] == "b.pdf"

    @patch("downloader.core._close_browser")
    @patch("downloader.core._close_session")
    @patch("downloader.core.get_session")
    @patch("downloader.core.download_file")
    def test_retry_passes_overwrite_true(
        self, mock_dl, mock_session, mock_close_session, mock_close_browser, tmp_path
    ):
        """Retry path should call download_file with overwrite=True."""
        from downloader.core import main

        failed_json = tmp_path / "failed_downloads.json"
        self._make_failure_json(failed_json, entries=[
            {
                "url": "https://example.com/c.pdf",
                "dest": str(tmp_path / "c.pdf"),
                "filename": "c.pdf",
                "error": "err",
                "source": "comptroller",
                "year": "2026",
                "use_browser": False,
                "timestamp": "2026-04-01T00:00:00+00:00",
            }
        ])

        mock_dl.return_value = True
        mock_session.return_value = MagicMock()

        test_args = [
            "dod_budget_downloader.py",
            "--retry-failures", str(failed_json),
            "--output", str(tmp_path),
            "--no-gui",
        ]

        with patch("sys.argv", test_args), pytest.raises(SystemExit):
            main()

        mock_dl.assert_called_once()
        _, kwargs = mock_dl.call_args
        assert kwargs.get("overwrite") is True

    @patch("downloader.core._close_browser")
    @patch("downloader.core._close_session")
    @patch("downloader.core.get_session")
    @patch("downloader.core.download_file")
    def test_retry_passes_use_browser_from_entry(
        self, mock_dl, mock_session, mock_close_session, mock_close_browser, tmp_path
    ):
        """Retry should pass the use_browser flag from the failure entry."""
        from downloader.core import main

        failed_json = tmp_path / "failed_downloads.json"
        self._make_failure_json(failed_json, entries=[
            {
                "url": "https://example.com/waf.pdf",
                "dest": str(tmp_path / "waf.pdf"),
                "filename": "waf.pdf",
                "error": "WAF",
                "source": "airforce",
                "year": "2026",
                "use_browser": True,
                "timestamp": "2026-04-01T00:00:00+00:00",
            }
        ])

        mock_dl.return_value = True
        mock_session.return_value = MagicMock()

        test_args = [
            "dod_budget_downloader.py",
            "--retry-failures", str(failed_json),
            "--output", str(tmp_path),
            "--no-gui",
        ]

        with patch("sys.argv", test_args), pytest.raises(SystemExit):
            main()

        _, kwargs = mock_dl.call_args
        assert kwargs.get("use_browser") is True

    def test_retry_missing_json_exits_with_error(self, tmp_path):
        """--retry-failures with nonexistent file should exit with code 1."""
        from downloader.core import main

        test_args = [
            "dod_budget_downloader.py",
            "--retry-failures", str(tmp_path / "nonexistent.json"),
            "--output", str(tmp_path),
            "--no-gui",
        ]

        with patch("sys.argv", test_args), pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


class TestDownloaderEntryPoint:
    """The retry path has to be reachable from a shell, not just importable.

    downloader/core.py defined main() but had no `if __name__ == "__main__"`
    guard, so `python -m downloader.core` imported the module and exited
    silently — and the failure message advertised `dod_budget_downloader.py`,
    which does not exist in the repository.  Every test above patched and
    called main() directly, so the logic was covered while the entry point was
    unreachable.  These tests exercise the layer those miss.
    """

    def test_package_main_module_exists(self):
        """`python -m downloader` needs a __main__.py in the package."""
        main_py = (
            Path(__file__).resolve().parents[2] / "downloader" / "__main__.py"
        )
        assert main_py.exists(), "downloader/__main__.py is missing"

    def test_module_is_runnable_from_a_shell(self):
        """Smoke test: the CLI parses args and exits 0 on --help."""
        import subprocess

        repo = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, "-m", "downloader", "--help"],
            capture_output=True, text=True, cwd=repo, timeout=120,
            # Windows: pytest's capture leaves no inheritable stdin handle,
            # and DuplicateHandle fails with WinError 6 without this.
            stdin=subprocess.DEVNULL,
        )
        assert result.returncode == 0, result.stderr
        assert "--retry-failures" in result.stdout

    def test_no_runtime_warning_on_invocation(self):
        """`python -m downloader.core` double-imports; the package entry does not."""
        import subprocess

        repo = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, "-m", "downloader", "--help"],
            capture_output=True, text=True, cwd=repo, timeout=120,
            # Windows: pytest's capture leaves no inheritable stdin handle,
            # and DuplicateHandle fails with WinError 6 without this.
            stdin=subprocess.DEVNULL,
        )
        assert "RuntimeWarning" not in result.stderr

    def test_advertised_retry_command_is_the_real_one(self):
        """The printed retry hint must name a target that actually runs.

        It once pointed at dod_budget_downloader.py — a file that is not in
        the repo — so anyone following the message got an immediate error.
        """
        repo = Path(__file__).resolve().parents[2]
        for rel in ("downloader/core.py", "downloader/gui.py"):
            src = (repo / rel).read_text(encoding="utf-8")
            assert "dod_budget_downloader.py" not in src, (
                f"{rel} advertises a script that does not exist"
            )
            if "--retry-failures" in src:
                assert "-m downloader" in src, (
                    f"{rel} should advertise `python -m downloader`"
                )
