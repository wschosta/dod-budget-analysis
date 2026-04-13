"""Progress tracking utilities for DoD budget tools.

Provides:
- ``fmt_time`` / ``log_progress`` — lightweight, fixed-width progress
  logging used by the pipeline enricher, builder, and CLI scripts.
- Abstract base class and concrete implementations for progress bars,
  file operation progress, and summary statistics.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

from utils.common import format_bytes


# ── Shared progress-line helpers ─────────────────────────────────────────────


def fmt_time(seconds: float) -> str:
    """Format *seconds* as a fixed-width 7-char right-justified string.

    Examples::

        fmt_time(5)     -> "      5s"   # rjust pads to 7
        fmt_time(135)   -> "  2m15s"
        fmt_time(3720)  -> "  1h02m"
    """
    if seconds < 60:
        return f"{seconds:.0f}s".rjust(7)
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{int(m)}m{int(s):02d}s".rjust(7)
    h, m = divmod(int(m), 60)
    return f"{int(h)}h{int(m):02d}m".rjust(7)


def log_progress(
    phase_name: str,
    completed: int,
    total: int,
    start_time: float,
    *,
    logger: logging.Logger | None = None,
    extra: str = "",
) -> str:
    """Build and optionally log a fixed-width progress line.

    Format (columns stay aligned as values grow)::

        Build Excel:       1/5,678 (  0.0%) | Elapsed:       5s | ETA:   5m02s |      1 items/s
        Build Excel:   5,678/5,678 (100.0%) | Elapsed:   5m02s  | ETA:       0s |    120 items/s

    Args:
        phase_name: Label for the current phase/step.
        completed:  Items finished so far.
        total:      Total items expected.
        start_time: ``time.monotonic()`` value captured when the phase began.
        logger:     If provided the line is emitted at ``INFO`` level.
        extra:      Optional suffix (e.g. a filename) appended after the rate.

    Returns:
        The formatted string (useful when the caller prints directly).
    """
    if total <= 0:
        return ""
    elapsed = time.monotonic() - start_time
    pct = completed / total * 100
    rate = completed / elapsed if elapsed > 0 else 0
    eta_s = (total - completed) / rate if rate > 0 else 0

    total_w = len(f"{total:,}")
    msg = (
        f"{phase_name}: {f'{completed:,}'.rjust(total_w)}/{total:,} "
        f"({pct:5.1f}%) "
        f"| Elapsed: {fmt_time(elapsed)} "
        f"| ETA: {fmt_time(eta_s)} "
        f"| {rate:6.0f} items/s"
    )
    if extra:
        msg += f"  {extra}"
    if logger is not None:
        logger.info("%s", msg)
    return msg


class ProgressTracker(ABC):
    """Abstract base class for progress tracking.

    Subclasses implement concrete progress display in different environments
    (terminal, GUI, logging, etc.).
    """

    def __init__(self, total_items: int):
        """Initialize progress tracker.

        Args:
            total_items: Total number of items to process
        """
        self.total_items = total_items
        self.completed = 0
        self.skipped = 0
        self.failed = 0
        self.start_time = time.time()

    @property
    def processed(self) -> int:
        """Get total items processed (completed + skipped + failed)."""
        return self.completed + self.skipped + self.failed

    @property
    def remaining(self) -> int:
        """Get items remaining."""
        return self.total_items - self.processed

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time in seconds since start."""
        return time.time() - self.start_time

    @property
    def progress_fraction(self) -> float:
        """Get progress as fraction (0.0 to 1.0)."""
        if self.total_items == 0:
            return 0.0
        return min(1.0, self.processed / self.total_items)

    @property
    def progress_percent(self) -> int:
        """Get progress as percentage (0 to 100)."""
        return int(self.progress_fraction * 100)

    def mark_completed(self, count: int = 1) -> None:
        """Mark items as completed successfully.

        Args:
            count: Number of items completed (default: 1)
        """
        self.completed += count
        self.update()

    def mark_skipped(self, count: int = 1) -> None:
        """Mark items as skipped.

        Args:
            count: Number of items skipped (default: 1)
        """
        self.skipped += count
        self.update()

    def mark_failed(self, count: int = 1) -> None:
        """Mark items as failed.

        Args:
            count: Number of items failed (default: 1)
        """
        self.failed += count
        self.update()

    @abstractmethod
    def update(self) -> None:
        """Update progress display. Implemented by subclasses."""
        pass

    @abstractmethod
    def finish(self) -> None:
        """Finish progress tracking. Implemented by subclasses."""
        pass


class TerminalProgressTracker(ProgressTracker):
    """Progress tracker for terminal/CLI output.

    Displays progress bar, statistics, and elapsed time.
    """

    def __init__(self, total_items: int, show_every_n: int = 10):
        """Initialize terminal progress tracker.

        Args:
            total_items: Total number of items
            show_every_n: Update display every N items (for performance)
        """
        super().__init__(total_items)
        self.show_every_n = show_every_n
        self.last_shown = 0

    def _format_bar(self, width: int = 30) -> str:
        """Generate progress bar string.

        Args:
            width: Width of progress bar in characters

        Returns:
            Progress bar string like "[=====>     ]"
        """
        filled = int(self.progress_fraction * width)
        empty = width - filled
        return "[" + "=" * filled + ">" + " " * max(0, empty - 1) + "]"

    def _format_summary(self) -> str:
        """Generate summary statistics string."""
        total = self.processed
        return f"({self.completed}/{total}) [skipped: {self.skipped}, failed: {self.failed}]"

    def _format_elapsed(self) -> str:
        """Format elapsed time as human-readable string."""
        elapsed_sec = int(self.elapsed_seconds)
        minutes, seconds = divmod(elapsed_sec, 60)
        hours, minutes = divmod(minutes, 60)

        if hours > 0:
            return f"{hours}h {minutes:02d}m {seconds:02d}s"
        return f"{minutes}m {seconds:02d}s"

    def update(self) -> None:
        """Update progress display (printed to stdout)."""
        if self.processed - self.last_shown < self.show_every_n:
            return

        self.last_shown = self.processed
        bar = self._format_bar()
        percent = self.progress_percent
        summary = self._format_summary()
        elapsed = self._format_elapsed()

        # Format: [=======>     ] 35% (7/20) [skipped: 2, failed: 1] - 1m 23s
        status_line = f"{bar} {percent:3d}% {summary} - {elapsed}"
        print(status_line)

    def finish(self) -> None:
        """Print final summary."""
        bar = self._format_bar()
        summary = self._format_summary()
        elapsed = self._format_elapsed()
        print(f"\n{bar} 100% {summary} - {elapsed}")
        print(f"Completed: {self.completed}, Skipped: {self.skipped}, Failed: {self.failed}")


class SilentProgressTracker(ProgressTracker):
    """Progress tracker that doesn't display anything.

    Useful for testing or when output should be suppressed.
    """

    def update(self) -> None:
        """No-op update."""
        pass

    def finish(self) -> None:
        """No-op finish."""
        pass


class FileProgressTracker(TerminalProgressTracker):
    """Progress tracker for file download/upload operations.

    Extends TerminalProgressTracker with byte counting.
    Tracks both file count and total bytes transferred.
    """

    def __init__(self, total_items: int):
        """Initialize file progress tracker.

        Args:
            total_items: Total number of files
        """
        super().__init__(total_items, show_every_n=1)
        self.total_bytes = 0
        self.completed_bytes = 0

    def add_bytes(self, bytes_count: int) -> None:
        """Add bytes to the total transferred.

        Args:
            bytes_count: Number of bytes transferred
        """
        self.completed_bytes += bytes_count
        self.update()

    @staticmethod
    def _format_bytes(b: int) -> str:
        """Format bytes into human-readable size string.

        Delegates to :func:`utils.common.format_bytes`.
        """
        return format_bytes(b)

    def update(self) -> None:
        """Update and print file progress with byte counts."""
        bar = self._format_bar()
        percent = self.progress_percent
        completed_bytes = self._format_bytes(self.completed_bytes)
        total_bytes = self._format_bytes(self.total_bytes) if self.total_bytes else "?"

        status_line = (f"{bar} {percent:3d}% ({self.completed}/{self.total_items}) "
                      f"{completed_bytes}/{total_bytes}")
        print(status_line)

    def finish(self) -> None:
        """Print final summary with byte counts."""
        print(f"\nCompleted: {self.completed}/{self.total_items}")
        print(f"Total bytes: {self._format_bytes(self.completed_bytes)}")
