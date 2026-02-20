"""
Additional progress tracker tests — coverage gap fill

Tests for ProgressTracker base class counter logic and the public methods
mark_completed/mark_skipped/mark_failed, plus TerminalProgressTracker.update()
and FileProgressTracker.add_bytes().
"""
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.progress import (
    TerminalProgressTracker,
    SilentProgressTracker,
    FileProgressTracker,
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
