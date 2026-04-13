"""
Additional progress tracker tests — coverage gap fill

Tests for ProgressTracker base class counter logic and the public methods
mark_completed/mark_skipped/mark_failed, plus TerminalProgressTracker.update()
and FileProgressTracker.add_bytes().

Also covers the shared ``fmt_time`` and ``log_progress`` helper functions
used for standardised CLI progress lines.
"""
import logging
import sys
import time
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.progress import (
    TerminalProgressTracker,
    SilentProgressTracker,
    FileProgressTracker,
    fmt_time,
    log_progress,
)


# ── ProgressTracker base class (via SilentProgressTracker) ───────────────────

class TestProgressTrackerCounters:
    def test_initial_state(self):
        pt = SilentProgressTracker(total_items=10)
        assert pt.total_items == 10
        assert pt.completed == 0
        assert pt.skipped == 0
        assert pt.failed == 0
        assert pt.processed == 0
        assert pt.remaining == 10

    def test_mark_completed(self):
        pt = SilentProgressTracker(total_items=5)
        pt.mark_completed()
        assert pt.completed == 1
        assert pt.processed == 1
        assert pt.remaining == 4

    def test_mark_completed_bulk(self):
        pt = SilentProgressTracker(total_items=10)
        pt.mark_completed(3)
        assert pt.completed == 3
        assert pt.processed == 3

    def test_mark_skipped(self):
        pt = SilentProgressTracker(total_items=5)
        pt.mark_skipped()
        assert pt.skipped == 1
        assert pt.processed == 1

    def test_mark_failed(self):
        pt = SilentProgressTracker(total_items=5)
        pt.mark_failed()
        assert pt.failed == 1
        assert pt.processed == 1

    def test_mixed_marks(self):
        pt = SilentProgressTracker(total_items=10)
        pt.mark_completed(3)
        pt.mark_skipped(2)
        pt.mark_failed(1)
        assert pt.completed == 3
        assert pt.skipped == 2
        assert pt.failed == 1
        assert pt.processed == 6
        assert pt.remaining == 4

    def test_progress_fraction(self):
        pt = SilentProgressTracker(total_items=4)
        pt.mark_completed(2)
        assert pt.progress_fraction == 0.5

    def test_progress_fraction_zero_total(self):
        pt = SilentProgressTracker(total_items=0)
        assert pt.progress_fraction == 0.0

    def test_progress_percent(self):
        pt = SilentProgressTracker(total_items=4)
        pt.mark_completed(3)
        assert pt.progress_percent == 75

    def test_elapsed_seconds(self):
        pt = SilentProgressTracker(total_items=1)
        assert pt.elapsed_seconds >= 0


# ── TerminalProgressTracker ──────────────────────────────────────────────────

class TestTerminalProgressTracker:
    def test_format_bar_empty(self):
        pt = TerminalProgressTracker(total_items=10)
        bar = pt._format_bar(width=10)
        assert bar.startswith("[")
        assert bar.endswith("]")

    def test_format_bar_full(self):
        pt = TerminalProgressTracker(total_items=1)
        pt.mark_completed()
        bar = pt._format_bar(width=10)
        assert "=" * 10 in bar

    def test_format_summary(self):
        pt = TerminalProgressTracker(total_items=10)
        pt.mark_completed(3)
        pt.mark_skipped(1)
        pt.mark_failed(1)
        summary = pt._format_summary()
        assert "(3/5)" in summary
        assert "skipped: 1" in summary
        assert "failed: 1" in summary

    def test_format_elapsed(self):
        pt = TerminalProgressTracker(total_items=1)
        elapsed = pt._format_elapsed()
        assert "m" in elapsed or "s" in elapsed

    def test_update_prints_on_threshold(self, capsys):
        """update() prints when processed count crosses show_every_n."""
        pt = TerminalProgressTracker(total_items=20, show_every_n=5)
        for _ in range(5):
            pt.mark_completed()
        output = capsys.readouterr().out
        assert "%" in output

    def test_update_suppressed_below_threshold(self, capsys):
        """update() doesn't print until show_every_n is reached."""
        pt = TerminalProgressTracker(total_items=20, show_every_n=10)
        pt.mark_completed()  # only 1, threshold is 10
        output = capsys.readouterr().out
        assert output == ""

    def test_finish_prints_summary(self, capsys):
        pt = TerminalProgressTracker(total_items=5)
        pt.mark_completed(5)
        pt.finish()
        output = capsys.readouterr().out
        assert "Completed:" in output
        assert "100%" in output


# ── FileProgressTracker ──────────────────────────────────────────────────────

class TestFileProgressTracker:
    def test_initial_bytes(self):
        pt = FileProgressTracker(total_items=3)
        assert pt.total_bytes == 0
        assert pt.completed_bytes == 0

    def test_add_bytes(self):
        pt = FileProgressTracker(total_items=3)
        pt.add_bytes(1024)
        assert pt.completed_bytes == 1024

    def test_add_bytes_cumulative(self):
        pt = FileProgressTracker(total_items=3)
        pt.add_bytes(512)
        pt.add_bytes(512)
        assert pt.completed_bytes == 1024

    def test_format_bytes_kb(self):
        pt = FileProgressTracker(total_items=1)
        assert pt._format_bytes(512 * 1024) == "512 KB"

    def test_format_bytes_mb(self):
        pt = FileProgressTracker(total_items=1)
        result = pt._format_bytes(1536 * 1024)
        assert "MB" in result

    def test_format_bytes_gb(self):
        pt = FileProgressTracker(total_items=1)
        result = pt._format_bytes(2 * 1024 * 1024 * 1024)
        assert "GB" in result

    def test_update_includes_bytes(self, capsys):
        pt = FileProgressTracker(total_items=2)
        pt.add_bytes(1024 * 1024)
        pt.mark_completed()
        output = capsys.readouterr().out
        # Should show byte counts in output
        assert "KB" in output or "MB" in output

    def test_finish_prints_total(self, capsys):
        pt = FileProgressTracker(total_items=2)
        pt.add_bytes(2048 * 1024)
        pt.mark_completed(2)
        pt.finish()
        output = capsys.readouterr().out
        assert "Completed:" in output
        assert "Total bytes:" in output


# ── SilentProgressTracker ────────────────────────────────────────────────────

class TestSilentProgressTracker:
    def test_update_no_output(self, capsys):
        pt = SilentProgressTracker(total_items=5)
        pt.mark_completed(5)
        output = capsys.readouterr().out
        assert output == ""

    def test_finish_no_output(self, capsys):
        pt = SilentProgressTracker(total_items=5)
        pt.finish()
        output = capsys.readouterr().out
        assert output == ""


# ── fmt_time ────────────────────────────────────────────────────────────────


class TestFmtTime:
    def test_zero_seconds(self):
        assert fmt_time(0) == "0s"

    def test_under_one_minute(self):
        assert fmt_time(45) == "45s"

    def test_exact_one_minute(self):
        assert fmt_time(60) == "1m00s"

    def test_minutes_and_seconds(self):
        assert fmt_time(135) == "2m15s"

    def test_seconds_zero_padded(self):
        # 2 minutes 3 seconds -> "2m03s"
        assert fmt_time(123) == "2m03s"

    def test_hours(self):
        assert fmt_time(3720) == "1h02m"

    def test_large_hours(self):
        assert fmt_time(45000) == "12h30m"

    def test_compact_no_padding(self):
        # fmt_time returns compact strings; log_progress handles alignment
        assert fmt_time(5) == "5s"
        assert " " not in fmt_time(5)


# ── log_progress ────────────────────────────────────────────────────────────


class TestLogProgress:
    def test_basic_format_contains_expected_parts(self):
        start = time.monotonic() - 10
        result = log_progress("Test", 50, 100, start)
        assert "50/100" in result
        assert "50.0%" in result
        assert "Elapsed:" in result
        assert "ETA:" in result
        assert "items/s" in result

    def test_returns_empty_string_on_zero_total(self):
        assert log_progress("Test", 0, 0, time.monotonic()) == ""

    def test_returns_empty_string_on_negative_total(self):
        assert log_progress("Test", 0, -1, time.monotonic()) == ""

    def test_phase_name_appears_in_output(self):
        start = time.monotonic() - 1
        result = log_progress("Build Excel", 5, 10, start)
        assert result.startswith("Build Excel:")

    def test_comma_separated_thousands(self):
        start = time.monotonic() - 1
        result = log_progress("Phase", 1234, 5678, start)
        assert "1,234" in result
        assert "5,678" in result

    def test_completed_right_justified_to_total_width(self):
        start = time.monotonic() - 1
        result = log_progress("X", 5, 5678, start)
        # "5" should be right-justified to match width of "5,678" (5 chars)
        assert "    5/5,678" in result

    def test_extra_suffix_appended(self):
        start = time.monotonic() - 1
        result = log_progress("Phase", 5, 10, start, extra="file.xlsx")
        assert "file.xlsx" in result

    def test_logs_to_logger_when_provided(self):
        test_logger = logging.getLogger("test_log_progress")
        with mock.patch.object(test_logger, "info") as mock_info:
            start = time.monotonic() - 1
            log_progress("Phase", 10, 20, start, logger=test_logger)
            mock_info.assert_called_once()

    def test_no_logging_when_logger_is_none(self):
        # Should not raise and should return the string
        start = time.monotonic() - 1
        result = log_progress("Phase", 5, 10, start, logger=None)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_percentage_fixed_width(self):
        start = time.monotonic() - 1
        result = log_progress("X", 1, 1000, start)
        # Should have leading space for small percentages: "  0.1%"
        assert "0.1%" in result

    def test_100_percent(self):
        start = time.monotonic() - 1
        result = log_progress("X", 100, 100, start)
        assert "100.0%" in result
