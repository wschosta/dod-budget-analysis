"""
GUI Progress Tracker for the DoD Budget Downloader.

Provides a Tkinter-based progress window that displays real-time download
status including per-file progress bars, speed, ETA, and a scrollable log.
"""

import threading
import time
from datetime import datetime, timezone

from utils import format_bytes, elapsed

from downloader.manifest import _manifest_path


class GuiProgressTracker:
    """Tkinter GUI window that displays download progress."""

    def __init__(self, total_files: int):
        """Launch the Tkinter GUI in a background daemon thread and wait for it to be ready.

        Args:
            total_files: Total number of files expected in this download session.
        """
        self.total_files = total_files
        self.completed = 0
        self.skipped = 0
        self.failed = 0
        self.total_bytes = 0
        self.start_time = time.time()
        self.current_source = ""
        self.current_year = ""

        # Per-file state (read by GUI thread)
        self._file_name = ""
        self._file_downloaded = 0
        self._file_total = 0
        self._file_start = 0.0
        self._log_lines: list[str] = []
        self._failure_lines: list[str] = []
        # Structured failure records for --retry-failures (TODO 1.A6-a)
        self._failed_files: list[dict] = []

        self._closed = False
        self._ready = threading.Event()

        self._thread = threading.Thread(target=self._run_gui, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    @property
    def processed(self) -> int:
        """Total files handled so far (completed + skipped + failed)."""
        return self.completed + self.skipped + self.failed

    def _run_gui(self):
        """Build and run the Tkinter progress window (called on the GUI daemon thread)."""
        import tkinter as tk
        from tkinter import ttk

        self._root = root = tk.Tk()
        root.title("DoD Budget Downloader")
        root.geometry("620x420")
        root.resizable(True, True)
        root.attributes("-topmost", True)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        style = ttk.Style()
        style.configure("Overall.Horizontal.TProgressbar",
                         troughcolor="#e0e0e0", background="#2196F3")
        style.configure("File.Horizontal.TProgressbar",
                         troughcolor="#e0e0e0", background="#4CAF50")

        pad = {"padx": 10, "pady": 4}

        # -- Source label --
        self._src_var = tk.StringVar(value="Initializing...")
        ttk.Label(root, textvariable=self._src_var,
                  font=("Segoe UI", 11, "bold")).pack(**pad, anchor="w")

        # -- Overall progress --
        frm_overall = ttk.Frame(root)
        frm_overall.pack(fill="x", **pad)

        self._overall_lbl = tk.StringVar(value="0.0%  -  0 / 0 files")
        ttk.Label(frm_overall, textvariable=self._overall_lbl,
                  font=("Segoe UI", 9)).pack(anchor="w")
        self._overall_bar = ttk.Progressbar(
            frm_overall, length=580, mode="determinate",
            style="Overall.Horizontal.TProgressbar")
        self._overall_bar.pack(fill="x", pady=2)

        # -- Stats row --
        self._stats_var = tk.StringVar(value="0 KB downloaded  |  0m 00s elapsed  |  0 remaining")
        ttk.Label(root, textvariable=self._stats_var,
                  font=("Segoe UI", 9)).pack(**pad, anchor="w")

        # -- Current file --
        sep1 = ttk.Separator(root, orient="horizontal")
        sep1.pack(fill="x", padx=10, pady=2)

        self._file_lbl = tk.StringVar(value="Waiting...")
        ttk.Label(root, textvariable=self._file_lbl,
                  font=("Segoe UI", 9)).pack(padx=10, pady=2, anchor="w")
        self._file_bar = ttk.Progressbar(
            root, length=580, mode="determinate",
            style="File.Horizontal.TProgressbar")
        self._file_bar.pack(fill="x", padx=10, pady=2)

        self._file_stats_var = tk.StringVar(value="")
        ttk.Label(root, textvariable=self._file_stats_var,
                  font=("Segoe UI", 9)).pack(padx=10, anchor="w")

        # -- Counters --
        sep2 = ttk.Separator(root, orient="horizontal")
        sep2.pack(fill="x", padx=10, pady=4)

        frm_counts = ttk.Frame(root)
        frm_counts.pack(fill="x", padx=10)
        self._count_var = tk.StringVar(
            value="Downloaded: 0    Skipped: 0    Failed: 0")
        ttk.Label(frm_counts, textvariable=self._count_var,
                  font=("Segoe UI", 9, "bold")).pack(anchor="w")

        # -- File log --
        sep3 = ttk.Separator(root, orient="horizontal")
        sep3.pack(fill="x", padx=10, pady=4)

        log_frame = ttk.Frame(root)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._log_text = tk.Text(log_frame, height=8, wrap="none",
                                  font=("Consolas", 8), state="disabled",
                                  bg="#f5f5f5")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical",
                                   command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=scrollbar.set)
        self._log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._ready.set()
        self._poll()
        root.mainloop()

    def _poll(self):
        """Called every 150ms in the GUI thread to refresh widgets."""
        if self._closed:
            return

        # Overall
        frac = self.processed / self.total_files if self.total_files else 0
        self._overall_bar["value"] = frac * 100
        self._overall_lbl.set(
            f"{frac*100:.1f}%  -  {self.processed} / {self.total_files} files")
        self._stats_var.set(
            f"{format_bytes(self.total_bytes)} downloaded  |  "
            f"{elapsed(self.start_time)} elapsed  |  "
            f"{self.total_files - self.processed} remaining")
        self._count_var.set(
            f"Downloaded: {self.completed}    "
            f"Skipped: {self.skipped}    "
            f"Failed: {self.failed}")

        # Source
        if self.current_year and self.current_source:
            self._src_var.set(f"FY{self.current_year} / {self.current_source}")

        # Current file
        fname = self._file_name
        if fname:
            dl = self._file_downloaded
            total = self._file_total
            if total > 0:
                file_frac = dl / total
                self._file_bar["value"] = file_frac * 100
                file_elapsed = time.time() - self._file_start
                speed = dl / file_elapsed if file_elapsed > 0 else 0
                speed_str = f"{format_bytes(int(speed))}/s"
                self._file_lbl.set(fname)
                self._file_stats_var.set(
                    f"{format_bytes(dl)} / {format_bytes(total)}  "
                    f"  {speed_str}")
            else:
                self._file_bar["value"] = 0
                self._file_lbl.set(f"{fname}  ({format_bytes(dl)})")
                self._file_stats_var.set("")

        # Log lines
        if self._log_lines:
            lines = self._log_lines.copy()
            self._log_lines.clear()
            self._log_text.configure(state="normal")
            for ln in lines:
                self._log_text.insert("end", ln + "\n")
            self._log_text.see("end")
            self._log_text.configure(state="disabled")

        self._root.after(150, self._poll)

    def _cleanup_vars(self):
        """Delete StringVar references on the GUI thread before destroying root.

        StringVar.__del__ calls into the Tcl interpreter. If Python's garbage
        collector runs these destructors from the main thread (e.g. at interpreter
        shutdown) after the GUI thread has exited, tkinter raises:
            RuntimeError: main thread is not in main loop
        Explicitly deleting the attributes here and forcing a GC cycle ensures
        the destructors run on the GUI thread while the Tcl interpreter is still
        valid.
        """
        import gc
        for attr in ('_src_var', '_overall_lbl', '_stats_var',
                     '_file_lbl', '_file_stats_var', '_count_var'):
            if hasattr(self, attr):
                delattr(self, attr)
        gc.collect()

    def _on_close(self):
        """Handle window close: set the closed flag and destroy the root widget."""
        self._closed = True
        self._cleanup_vars()
        self._root.destroy()

    def _do_close(self):
        """Destroy the root window on the GUI thread after cleaning up StringVars."""
        self._cleanup_vars()
        self._root.destroy()

    def set_source(self, year: str, source: str):
        """Update the current fiscal year and source for the GUI source label."""
        self.current_year = year
        self.current_source = source

    def print_overall(self):
        """No-op: overall progress is updated by the polling loop."""
        pass  # GUI updates via _poll

    def print_file_progress(self, filename: str, downloaded: int, total: int,
                            file_start: float):
        """Update per-file download state; the GUI polling loop reads these values."""
        self._file_name = filename
        self._file_downloaded = downloaded
        self._file_total = total
        self._file_start = file_start

    def file_done(self, filename: str, size: int, status: str):
        tag = {"ok": "OK", "skip": "SKIP", "redownload": "OK",
               "fail": "FAIL"}.get(status, status.upper())

        if status == "ok" or status == "redownload":
            self.completed += 1
            self.total_bytes += size
        elif status == "skip":
            self.skipped += 1
            self.total_bytes += size
        elif status == "fail":
            self.failed += 1

        size_str = f" ({format_bytes(size)})" if size > 0 else ""
        log_entry = f"[{tag}] {filename}{size_str}"
        self._log_lines.append(log_entry)
        if status == "fail":
            self._failure_lines.append(log_entry)

        # Reset file bar
        self._file_name = ""
        self._file_downloaded = 0
        self._file_total = 0

    def file_failed(self, url: str, dest: str, filename: str, error: str,
                    use_browser: bool = False) -> None:
        """Record a structured failure entry and update counters (TODO 1.A6-a)."""
        self._failed_files.append({
            "url": url,
            "dest": dest,
            "filename": filename,
            "error": str(error),
            "source": self.current_source,
            "year": self.current_year,
            "use_browser": use_browser,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Also append URL info to failure_lines for the GUI dialog (1.A6-c)
        self._failure_lines.append(f"[FAIL] {filename}\n       URL: {url}")
        self.file_done(filename, 0, "fail")

    def show_completion_dialog(self, summary: str):
        """Replace the progress window with a completion dialog.

        Shows a summary message, a Close button, and (if there were
        failures) a View Failures button that opens the failure lines
        in a scrollable text window.
        """
        import tkinter as tk
        from tkinter import ttk

        failure_lines = list(self._failure_lines)
        failed_json_path = str(_manifest_path).replace("manifest.json",
                                                        "failed_downloads.json") \
            if _manifest_path else "failed_downloads.json"
        retry_cmd = f"python dod_budget_downloader.py --retry-failures {failed_json_path}"

        # Destroy the old progress window
        self.close()

        # Build completion dialog (1.A6-c)
        dlg = tk.Tk()
        dlg.title("Download Complete")
        dlg.geometry("460x220")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)

        ttk.Label(dlg, text="Download Complete",
                  font=("Segoe UI", 13, "bold")).pack(pady=(18, 6))
        ttk.Label(dlg, text=summary,
                  font=("Segoe UI", 10), wraplength=420,
                  justify="center").pack(pady=(0, 14))

        btn_frame = ttk.Frame(dlg)
        btn_frame.pack(pady=(0, 14))

        def _view_failures():
            """Open a scrollable text window listing all failed downloads."""
            win = tk.Toplevel(dlg)
            win.title("Failed Downloads")
            win.geometry("620x360")
            win.attributes("-topmost", True)
            txt = tk.Text(win, wrap="word", font=("Consolas", 9))
            sb = ttk.Scrollbar(win, orient="vertical", command=txt.yview)
            txt.configure(yscrollcommand=sb.set)
            txt.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            txt.insert("end", "\n".join(failure_lines) if failure_lines
                       else "No failure details available.")
            txt.configure(state="disabled")

        def _copy_retry_cmd():
            dlg.clipboard_clear()
            dlg.clipboard_append(retry_cmd)

        if self.failed > 0 and failure_lines:
            ttk.Button(btn_frame, text="View Failures",
                       command=_view_failures).pack(side="left", padx=6)
            ttk.Button(btn_frame, text="Copy Retry Command",
                       command=_copy_retry_cmd).pack(side="left", padx=6)

        ttk.Button(btn_frame, text="Close",
                   command=dlg.destroy).pack(side="left", padx=6)

        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.mainloop()

    def close(self):
        """Close the GUI window."""
        if not self._closed and hasattr(self, '_root'):
            self._closed = True
            try:
                self._root.after(0, self._do_close)
            except Exception:
                pass
