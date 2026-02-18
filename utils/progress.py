"""Progress tracking utilities for DoD budget tools.

Provides abstract base class and concrete implementations for:
- Terminal progress tracking with progress bars
- File operation progress
- Summary statistics
"""

import time
from abc import ABC, abstractmethod


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

    def _format_bytes(self, b: int) -> str:
        """Format bytes into human-readable size string.

        Args:
            b: Number of bytes

        Returns:
            Formatted string like "512 KB", "1.5 MB", "2.34 GB"
        """
        if b < 1024 * 1024:
            return f"{b / 1024:.0f} KB"
        if b < 1024 * 1024 * 1024:
            return f"{b / (1024 * 1024):.1f} MB"
        return f"{b / (1024 * 1024 * 1024):.2f} GB"

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
