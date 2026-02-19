"""
Tests for scripts/scheduled_download.py — run_scheduled_download()

Mocks dod_budget_downloader to test the orchestration logic without network access.
"""
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_project_root = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _project_root)
sys.path.insert(0, str(Path(_project_root) / "scripts"))


def _make_downloader_mock(
    available_years=None,
    download_summary=None,
    discover_raises=None,
):
    """Create a mock dod_budget_downloader module."""
    mod = types.ModuleType("dod_budget_downloader")

    if available_years is None:
        available_years = {"2026": "https://example.com/2026"}

    mod.ALL_SOURCES = {"comptroller", "army", "navy"}
    mod.BROWSER_REQUIRED_SOURCES = set()
    mod.SERVICE_PAGE_TEMPLATES = {
        "army": {"label": "Army"},
        "navy": {"label": "Navy"},
    }
    mod.SOURCE_DISCOVERERS = {
        "army": lambda sess, yr: [{"url": f"http://army/{yr}"}],
        "navy": lambda sess, yr: [{"url": f"http://navy/{yr}"}],
    }
    mod._is_browser_source = lambda s: False
    mod.get_session = MagicMock(return_value=MagicMock())

    if discover_raises:
        mod.discover_fiscal_years = MagicMock(side_effect=discover_raises)
    else:
        mod.discover_fiscal_years = MagicMock(return_value=available_years)

    mod.discover_comptroller_files = MagicMock(
        return_value=[{"url": "http://comp/file.pdf"}]
    )

    if download_summary is None:
        download_summary = {"downloaded": 5, "skipped": 2, "failed": 0}
    mod.download_all = MagicMock(return_value=download_summary)

    return mod


class TestRunScheduledDownload:
    def test_success(self, tmp_path):
        mock_mod = _make_downloader_mock()
        with patch.dict(sys.modules, {"dod_budget_downloader": mock_mod}):
            from scripts.scheduled_download import run_scheduled_download
            code = run_scheduled_download(tmp_path / "output")
        assert code == 0
        mock_mod.download_all.assert_called_once()

    def test_creates_output_dir(self, tmp_path):
        out = tmp_path / "new" / "sub"
        mock_mod = _make_downloader_mock()
        with patch.dict(sys.modules, {"dod_budget_downloader": mock_mod}):
            from scripts.scheduled_download import run_scheduled_download
            run_scheduled_download(out)
        assert out.is_dir()

    def test_log_file_created(self, tmp_path):
        log = tmp_path / "logs" / "run.log"
        mock_mod = _make_downloader_mock()
        with patch.dict(sys.modules, {"dod_budget_downloader": mock_mod}):
            from scripts.scheduled_download import run_scheduled_download
            run_scheduled_download(tmp_path / "output", log_file=log)
        assert log.exists()
        content = log.read_text()
        assert "Scheduled download started" in content

    def test_failed_downloads_exit_1(self, tmp_path):
        mock_mod = _make_downloader_mock(
            download_summary={"downloaded": 3, "skipped": 0, "failed": 2}
        )
        with patch.dict(sys.modules, {"dod_budget_downloader": mock_mod}):
            from scripts.scheduled_download import run_scheduled_download
            code = run_scheduled_download(tmp_path / "output")
        assert code == 1

    def test_import_error_returns_1(self, tmp_path):
        # Remove the module so import fails
        with patch.dict(sys.modules, {"dod_budget_downloader": None}):
            # Need to clear cached import in the script
            mod_key = "scripts.scheduled_download"
            sys.modules.pop(mod_key, None)
            from scripts.scheduled_download import run_scheduled_download
            log = tmp_path / "err.log"
            code = run_scheduled_download(tmp_path / "output", log_file=log)
        assert code == 1
        assert log.exists()

    def test_discover_error_returns_1(self, tmp_path):
        mock_mod = _make_downloader_mock(
            discover_raises=RuntimeError("No years found")
        )
        with patch.dict(sys.modules, {"dod_budget_downloader": mock_mod}):
            from scripts.scheduled_download import run_scheduled_download
            log = tmp_path / "err.log"
            code = run_scheduled_download(tmp_path / "output", log_file=log)
        assert code == 1
        content = log.read_text()
        assert "FATAL ERROR" in content

    def test_specific_years(self, tmp_path):
        mock_mod = _make_downloader_mock(
            available_years={"2025": "url25", "2026": "url26"}
        )
        with patch.dict(sys.modules, {"dod_budget_downloader": mock_mod}):
            from scripts.scheduled_download import run_scheduled_download
            code = run_scheduled_download(
                tmp_path / "output", years=["2026"]
            )
        assert code == 0

    def test_missing_years_warns(self, tmp_path, capsys):
        mock_mod = _make_downloader_mock(
            available_years={"2026": "url26"}
        )
        with patch.dict(sys.modules, {"dod_budget_downloader": mock_mod}):
            from scripts.scheduled_download import run_scheduled_download
            code = run_scheduled_download(
                tmp_path / "output", years=["2026", "2020"]
            )
        assert code == 0

    def test_all_years_requested(self, tmp_path):
        mock_mod = _make_downloader_mock(
            available_years={"2025": "url25", "2026": "url26"}
        )
        with patch.dict(sys.modules, {"dod_budget_downloader": mock_mod}):
            from scripts.scheduled_download import run_scheduled_download
            code = run_scheduled_download(
                tmp_path / "output", years=["all"]
            )
        assert code == 0

    def test_no_valid_years_returns_1(self, tmp_path):
        mock_mod = _make_downloader_mock(
            available_years={"2026": "url26"}
        )
        with patch.dict(sys.modules, {"dod_budget_downloader": mock_mod}):
            from scripts.scheduled_download import run_scheduled_download
            code = run_scheduled_download(
                tmp_path / "output", years=["2019"]
            )
        assert code == 1


class TestPreCommitChecker:
    """Tests for the PreCommitChecker class from run_precommit_checks.py."""

    def test_check_pass(self, capsys):
        from run_precommit_checks import PreCommitChecker
        checker = PreCommitChecker(verbose=True)
        checker.check("test_pass", lambda: True)
        assert checker.passed == 1
        assert checker.failed == 0

    def test_check_fail(self, capsys):
        from run_precommit_checks import PreCommitChecker
        checker = PreCommitChecker(verbose=True)
        checker.check("test_fail", lambda: False)
        assert checker.passed == 0
        assert checker.failed == 1

    def test_check_exception(self, capsys):
        from run_precommit_checks import PreCommitChecker
        checker = PreCommitChecker(verbose=True)
        checker.check("test_err", lambda: 1 / 0)
        assert checker.failed == 1

    def test_check_assertion_error(self, capsys):
        from run_precommit_checks import PreCommitChecker
        checker = PreCommitChecker(verbose=False)

        def fail_assert():
            raise AssertionError("bad value")

        checker.check("test_assert", fail_assert)
        assert checker.failed == 1

    def test_skip(self, capsys):
        from run_precommit_checks import PreCommitChecker
        checker = PreCommitChecker(verbose=True)
        checker.skip("test_skip", reason="not needed")
        assert checker.skipped == 1

    def test_summary_pass(self, capsys):
        from run_precommit_checks import PreCommitChecker
        checker = PreCommitChecker()
        checker.passed = 5
        checker.failed = 0
        assert checker.summary() is True

    def test_summary_fail(self, capsys):
        from run_precommit_checks import PreCommitChecker
        checker = PreCommitChecker()
        checker.passed = 3
        checker.failed = 2
        assert checker.summary() is False

    def test_check_none_result_passes(self):
        from run_precommit_checks import PreCommitChecker
        checker = PreCommitChecker(verbose=False)
        checker.check("none_result", lambda: None)
        assert checker.passed == 1
