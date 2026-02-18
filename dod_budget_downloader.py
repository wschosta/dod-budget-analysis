"""
DoD Comptroller Budget Document Downloader

Downloads budget documents (PDFs, Excel files, ZIPs) from the DoD Comptroller
website and service-specific budget pages for selected fiscal years.

Sources:
  - comptroller  : Main DoD summary budget documents (comptroller.war.gov)
  - defense-wide : Defense Wide budget justification books (comptroller.war.gov)
  - army         : US Army budget materials (asafm.army.mil)
  - navy         : US Navy/Marine Corps budget materials (secnav.navy.mil)
  - navy-archive : US Navy archive alternate source (secnav.navy.mil/fmc/fmb)
  - airforce     : US Air Force & Space Force budget materials (saffm.hq.af.mil)

Requirements:
  pip install requests beautifulsoup4 playwright
  python -m playwright install chromium

Usage Examples
--------------
  python dod_budget_downloader.py                              # Interactive
  python dod_budget_downloader.py --years 2026                 # FY2026 comptroller
  python dod_budget_downloader.py --years 2026 --sources all   # FY2026 all sources
  python dod_budget_downloader.py --years 2026 --sources army navy
  python dod_budget_downloader.py --years 2026 --list          # Dry-run listing
  python dod_budget_downloader.py --years all --sources all    # Everything
  python dod_budget_downloader.py --no-gui                     # Terminal-only mode

──────────────────────────────────────────────────────────────────────────────
Roadmap TODOs for this file (Step 1.A)
──────────────────────────────────────────────────────────────────────────────

TODO 1.A1-a: Audit source coverage by running --list --years all --sources all.
    Capture the output and compare against the known universe of DoD budget
    document types.  Record: which sources produce files, how many files per
    source/FY, and which file types (PDF, XLSX, ZIP, CSV) are found.
    Token-efficient tip: pipe output to a file, then write a 20-line script
    that parses the listing and produces a coverage matrix (source × FY).
    This is an investigative task — run in a live environment with network.

TODO 1.A1-b: Identify missing DoD component sources.
    The following agencies are NOT currently covered and may publish their own
    budget justification books:
    - Defense Logistics Agency (DLA)
    - Missile Defense Agency (MDA) — may have standalone exhibits on mda.mil
    - SOCOM (Special Operations Command) — socom.mil
    - Defense Health Agency (DHA)
    - Defense Information Systems Agency (DISA)
    - National Guard Bureau
    For each: manually check whether they publish budget materials at a distinct
    URL (separate from the Defense-Wide page on comptroller.war.gov).  If yes,
    add to SERVICE_PAGE_TEMPLATES with url and label.
    Token-efficient tip: this requires web browsing.  For each agency, try a
    single search query like "site:mda.mil budget justification" and check
    the top result.  Record findings in DATA_SOURCES.md.

TODO 1.A1-c: Verify that defense-wide discovery captures all J-Books.
    The Defense-Wide page at comptroller.war.gov/Budget-Materials/FY{fy}
    BudgetJustification/ may contain links to individual agency justification
    books.  Run discover_defense_wide_files() for a sample FY and compare the
    file list against the known set of defense agency J-Books.
    Token-efficient tip: run with --list --years 2026 --sources defense-wide
    and inspect output.  ~5 minutes of manual review.

TODO 1.A2-a: Test historical fiscal year reach.
    Run discover_fiscal_years() and record all years returned.  Then attempt
    discover_comptroller_files() for the oldest year found.  Goal: confirm
    data is available back to at least FY2017.
    Token-efficient tip: run --list --years 2017 2018 2019 --sources comptroller
    and check for non-empty results.  If the comptroller site doesn't list
    years before a certain point, check the Wayback Machine or alternate
    archive URLs.  This is investigative — must run with network access.

TODO 1.A2-b: Handle alternate URL patterns for older fiscal years.
    Older FYs may use different URL structures on comptroller.war.gov (e.g.,
    different subdirectory naming, or documents hosted on a legacy domain).
    If TODO 1.A2-a finds gaps, inspect the actual page HTML for those years
    and add pattern variants to discover_comptroller_files().
    Dependency: TODO 1.A2-a must be done first to identify which years fail.

TODO 1.A2-c: Handle service-specific historical URL changes.
    Each service site (Army, Navy, Air Force) may have reorganized over the
    years.  Test discover_army_files(), discover_navy_files(), and
    discover_airforce_files() for FY2017–FY2020 and record which succeed.
    For failures, inspect the site and add alternate URL patterns.
    Token-efficient tip: run --list --years 2017 2018 --sources army navy
    airforce and check output.  Fix one service at a time.

TODO 1.A3-a: Add download manifest generation.
    After discovery (but before download), write a manifest.json to the output
    directory listing every file to be downloaded: url, expected_filename,
    source, fiscal_year, extension.  After download, update each entry with
    status (ok/skip/fail), file_size, and file_hash (SHA-256).
    Token-efficient tip: add ~30 lines to main() — serialize all_files to JSON
    before the download loop, then update entries inside download_file().

TODO 1.A3-b: Add SHA-256 checksum verification.
    After downloading a file, compute its SHA-256 hash.  On subsequent runs,
    compare the hash to the manifest.  If a file exists but its hash doesn't
    match the manifest (corrupted), redownload it.
    Modify _check_existing_file() to accept an optional expected_hash param.
    Token-efficient tip: add hashlib.sha256() inside download_file() after
    writing — ~10 lines.  Modify _check_existing_file() to read and compare.

TODO 1.A3-c: Improve WAF/bot detection handling.
    Currently, if a WAF blocks a request, the error is generic ("All browser
    download strategies failed").  Detect common WAF block signatures:
    - HTTP 403 with "Access Denied" body
    - HTTP 200 with a CAPTCHA/challenge page (check for "captcha", "challenge",
      "verify you are human" in response text)
    - Cloudflare challenge (check for "cf-browser-verification")
    When detected, log a specific warning and optionally pause to let the user
    solve the CAPTCHA manually (in browser mode).
    Token-efficient tip: add a 15-line _detect_waf_block(response) helper
    called from download_file() and _browser_download_file().


TODO 1.A4-a: Create a CLI-only download script (no GUI dependency).
    Extract the core download logic into a function that can be called
    programmatically: download_all(years, sources, output_dir, **opts).
    This decouples the pipeline from the interactive/GUI code so it can be
    called from cron, CI, or the refresh script (see TODO 2.B4-a).
    Token-efficient tip: the logic already exists in main() — refactor by
    pulling lines 1286–1406 into a download_all() function that takes args
    as parameters instead of parsing sys.argv.  ~20 lines of refactoring.

TODO 1.A4-b: Add a --since flag for incremental updates.
    Accept --since YYYY-MM-DD.  During discovery, filter out files whose
    page was last updated before that date (if the server provides
    Last-Modified headers).  More practically: compare against the manifest
    from the previous run — skip files already in the manifest with matching
    hashes.
    Dependency: TODO 1.A3-a (manifest) should be done first.

TODO 1.A4-c: Create a GitHub Actions workflow for scheduled downloads.
    Write .github/workflows/update-data.yml that:
    1. Checks out the repo
    2. Installs dependencies (including playwright)
    3. Runs the download pipeline for the most recent 2 FYs
    4. Runs build_budget_db.py
    5. Commits and pushes updated data (or uploads as artifact)
    Schedule: weekly or on workflow_dispatch.
    Token-efficient tip: ~40 lines of YAML.  Use actions/cache for playwright
    browsers.  Store the manifest as a committed file for diffing.

TODO 1.A5-a: Create DATA_SOURCES.md documenting all data sources.
    For each source (comptroller, defense-wide, army, navy, airforce, plus
    any new ones from TODO 1.A1-b): document the base URL, URL pattern per FY,
    file types available, fiscal years confirmed available, any access
    requirements (WAF, browser needed), and notes on site behavior.
    See DATA_SOURCES.md for the skeleton.
    Token-efficient tip: most of this information is already in this file's
    SERVICE_PAGE_TEMPLATES and source-specific functions — extract and format
    as markdown.  ~100 lines.
Usage:
    python dod_budget_downloader.py                              # Interactive
    python dod_budget_downloader.py --years 2025                 # FY2025 comptroller only
    python dod_budget_downloader.py --years 2025 --sources all   # FY2025 all sources
    python dod_budget_downloader.py --years 2025 --sources army navy
    python dod_budget_downloader.py --years 2025 --list          # List without downloading
    python dod_budget_downloader.py --years all --sources all    # Everything
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests
import socket
from bs4 import BeautifulSoup

# Shared utilities: Import from utils package for consistency across codebase
from utils import format_bytes, elapsed, sanitize_filename
from utils.patterns import DOWNLOADABLE_EXTENSIONS

# Optimization: Try to use lxml parser (3-5x faster), fall back to html.parser
try:
    import lxml
    PARSER = "lxml"
except ImportError:
    PARSER = "html.parser"

# Optimization: Pre-compile extension regex pattern (now from utils.patterns)
DOWNLOADABLE_PATTERN = DOWNLOADABLE_EXTENSIONS

# ── Configuration ──────────────────────────────────────────────────────────────
global tracker

BASE_URL = "https://comptroller.war.gov"
BUDGET_MATERIALS_URL = f"{BASE_URL}/Budget-Materials/"
DOWNLOADABLE_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".zip", ".csv"}
IGNORED_HOSTS = {"dam.defense.gov"}
DEFAULT_OUTPUT_DIR = Path("DoD_Budget_Documents")

# Optimization: Cache directory for discovery results
DISCOVERY_CACHE_DIR = Path("discovery_cache")

ALL_SOURCES = ["comptroller", "defense-wide", "army", "navy", "navy-archive", "airforce"]

# Sources that require a real browser due to WAF/bot protection
BROWSER_REQUIRED_SOURCES = {"army", "navy", "navy-archive", "airforce"}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

SERVICE_PAGE_TEMPLATES = {
    "defense-wide": {
        "url": "https://comptroller.war.gov/Budget-Materials/FY{fy}BudgetJustification/",
        "label": "Defense Wide",
    },
    "army": {
        "url": "https://www.asafm.army.mil/Budget-Materials/",
        "label": "US Army",
    },
    "navy": {
        "url": "https://www.secnav.navy.mil/fmc/Pages/Fiscal-Year-{fy}.aspx",
        "label": "US Navy",
    },
    "airforce": {
        "url": "https://www.saffm.hq.af.mil/FM-Resources/Budget/Air-Force-Presidents-Budget-FY{fy2}/",
        "label": "US Air Force",
    },
    "navy-archive": {
        "url": "https://www.secnav.navy.mil/fmc/fmb/Pages/archive.aspx",
        "label": "US Navy Archive",
    },
}


# ── Progress Tracker ──────────────────────────────────────────────────────────

# format_bytes and elapsed are now imported from utils.common
# This consolidates utilities across the codebase for easier maintenance
# and ensures consistent behavior across all tools.


# Optimization: Adaptive timeout management based on response history
class TimeoutManager:
    """Manages adaptive timeouts based on response history."""
    def __init__(self):
        """Initialize with an empty per-domain response-time history."""
        self.response_times = {}  # domain -> list of response times (in ms)

    def get_timeout(self, url: str, is_download: bool = False) -> int:
        """Get adaptive timeout in milliseconds."""
        domain = urlparse(url).netloc

        if domain not in self.response_times:
            self.response_times[domain] = []

        times = self.response_times[domain]
        if not times:
            return 120000 if is_download else 15000

        avg_time = sum(times) / len(times)
        percentile_95 = sorted(times)[-1] if len(times) > 0 else avg_time

        # Use 95th percentile + 50% buffer
        adaptive = int(percentile_95 * 1.5)

        if is_download:
            # Downloads get longer timeout (up to 120s)
            return min(adaptive, 120000)
        else:
            # Page loads get shorter timeout (up to 30s)
            return min(adaptive, 30000)

    def record_time(self, url: str, elapsed_ms: int):
        """Record response time for timeout learning."""
        domain = urlparse(url).netloc
        if domain not in self.response_times:
            self.response_times[domain] = []
        self.response_times[domain].append(elapsed_ms)
        # Keep only last 20 samples to avoid memory bloat
        if len(self.response_times[domain]) > 20:
            self.response_times[domain].pop(0)


# Global timeout manager
_timeout_mgr = TimeoutManager()

# Global flag for cache refresh
_refresh_cache = False


class ProgressTracker:
    """Tracks overall download session progress and renders status bars."""

    def __init__(self, total_files: int):
        """Initialize counters, timers, and terminal width for progress rendering.

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
        self.term_width = shutil.get_terminal_size((80, 24)).columns
        self._last_progress_time = 0.0
        # Structured failure records for --retry-failures (TODO 1.A6-a)
        # Schema: {url, dest, filename, error, source, year, use_browser, timestamp}
        self._failed_files: list[dict] = []

    @property
    def processed(self) -> int:
        """Total files handled so far (completed + skipped + failed)."""
        return self.completed + self.skipped + self.failed

    def _bar(self, fraction: float, width: int = 30) -> str:
        """Render an ASCII progress bar of the given width for the given fraction."""
        filled = int(width * fraction)
        return f"[{'#' * filled}{'-' * (width - filled)}]"

    def set_source(self, year: str, source: str):
        """Update the current fiscal year and source label for display."""
        self.current_year = year
        self.current_source = source

    def print_overall(self):
        """Print the overall progress line."""
        frac = self.processed / self.total_files if self.total_files else 0
        pct = frac * 100
        bar = self._bar(frac, 25)
        dl = format_bytes(self.total_bytes)
        elapsed_str = elapsed(self.start_time)
        remaining = self.total_files - self.processed
        line = (
            f"\r  Overall: {bar} {pct:5.1f}%  "
            f"{self.processed}/{self.total_files} files  "
            f"{dl} downloaded  "
            f"{elapsed_str} elapsed  "
            f"({remaining} remaining)"
        )
        # Pad to terminal width to clear previous line
        print(f"{line:<{self.term_width}}", end="", flush=True)

    def print_file_progress(self, filename: str, downloaded: int, total: int,
                            file_start: float):
        """Print per-file download progress with speed."""
        # Throttle updates to at most every 0.25 seconds
        now = time.time()
        if now - self._last_progress_time < 0.25:
            return
        self._last_progress_time = now

        if total <= 0:
            print(f"\r    Downloading {filename}... {format_bytes(downloaded)}",
                  end="", flush=True)
            return

        frac = downloaded / total
        pct = frac * 100
        bar = self._bar(frac, 20)
        file_elapsed = time.time() - file_start
        speed = downloaded / file_elapsed if file_elapsed > 0 else 0
        speed_str = f"{format_bytes(int(speed))}/s"
        eta = ""
        if speed > 0:
            remaining_bytes = total - downloaded
            eta_secs = int(remaining_bytes / speed)
            if eta_secs < 60:
                eta = f"ETA {eta_secs}s"
            else:
                eta = f"ETA {eta_secs // 60}m {eta_secs % 60:02d}s"

        name = filename[:40] + "..." if len(filename) > 43 else filename
        line = (
            f"\r    {name}  {bar} {pct:5.1f}%  "
            f"{format_bytes(downloaded)}/{format_bytes(total)}  "
            f"{speed_str}  {eta}"
        )
        print(f"{line:<{self.term_width}}", end="", flush=True)

    def file_done(self, filename: str, size: int, status: str):
        """Record a completed file and print result."""
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

        size_str = format_bytes(size) if size > 0 else ""
        line = f"    [{tag}] {filename} ({size_str})" if size_str else f"    [{tag}] {filename}"
        print(f"\r{line:<{self.term_width}}")
        self.print_overall()

    def file_failed(self, url: str, dest: str, filename: str, error: str,
                    use_browser: bool = False) -> None:
        """Record a structured failure entry and update counters (TODO 1.A6-a).

        Stores the full metadata needed to retry the download later via
        ``--retry-failures``, then delegates to ``file_done`` for display.
        """
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
        self.file_done(filename, 0, "fail")


# ── GUI Progress Tracker ─────────────────────────────────────────────────────

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

        # ── Source label ──
        self._src_var = tk.StringVar(value="Initializing...")
        ttk.Label(root, textvariable=self._src_var,
                  font=("Segoe UI", 11, "bold")).pack(**pad, anchor="w")

        # ── Overall progress ──
        frm_overall = ttk.Frame(root)
        frm_overall.pack(fill="x", **pad)

        self._overall_lbl = tk.StringVar(value="0.0%  -  0 / 0 files")
        ttk.Label(frm_overall, textvariable=self._overall_lbl,
                  font=("Segoe UI", 9)).pack(anchor="w")
        self._overall_bar = ttk.Progressbar(
            frm_overall, length=580, mode="determinate",
            style="Overall.Horizontal.TProgressbar")
        self._overall_bar.pack(fill="x", pady=2)

        # ── Stats row ──
        self._stats_var = tk.StringVar(value="0 KB downloaded  |  0m 00s elapsed  |  0 remaining")
        ttk.Label(root, textvariable=self._stats_var,
                  font=("Segoe UI", 9)).pack(**pad, anchor="w")

        # ── Current file ──
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

        # ── Counters ──
        sep2 = ttk.Separator(root, orient="horizontal")
        sep2.pack(fill="x", padx=10, pady=4)

        frm_counts = ttk.Frame(root)
        frm_counts.pack(fill="x", padx=10)
        self._count_var = tk.StringVar(
            value="Downloaded: 0    Skipped: 0    Failed: 0")
        ttk.Label(frm_counts, textvariable=self._count_var,
                  font=("Segoe UI", 9, "bold")).pack(anchor="w")

        # ── File log ──
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


# Global state management: tracker, session, and browser context
# Current approach: module-level globals for simplicity and performance
# Advantages: Minimal overhead for single-threaded downloads, easy reuse across functions
# Future improvement: Could wrap in DownloadSession class for better testability and
# thread-safety, but current single-threaded design doesn't require it.
#
# Global tracker, set during main()
_tracker: ProgressTracker | GuiProgressTracker | None = None

# Optimization: Global session reuse for connection pooling
_global_session = None

# ── Manifest (TODO 1.A3-a & 1.A3-b) ─────────────────────────────────────────

# In-memory manifest; written to disk by write_manifest() / update_manifest_entry()
_manifest: dict = {}
_manifest_path: Path | None = None


def _compute_sha256(file_path: Path) -> str:
    """Compute the SHA-256 hex digest of a file.

    Reads in 64 KB chunks to avoid loading large files into memory.
    Implements TODO 1.A3-b.
    """
    h = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(output_dir: Path, all_files: dict, manifest_path: Path) -> None:
    """Write an initial manifest.json listing all files to be downloaded.

    Each entry records: url, expected_filename, source, fiscal_year, extension.
    After downloading, call update_manifest_entry() to add status/size/hash.
    Implements TODO 1.A3-a.
    """
    global _manifest, _manifest_path
    _manifest_path = manifest_path

    entries: dict[str, dict] = {}
    for year, sources in all_files.items():
        for source_label, files in sources.items():
            for f in files:
                key = f["url"]
                entries[key] = {
                    "url": f["url"],
                    "filename": f["filename"],
                    "source": source_label,
                    "fiscal_year": year,
                    "extension": f.get("extension", ""),
                    "status": "pending",
                    "file_size": None,
                    "sha256": None,
                    "downloaded_at": None,
                }

    _manifest = entries
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(), "files": entries}, fh, indent=2)


def update_manifest_entry(url: str, status: str, file_size: int,
                          file_hash: str | None) -> None:
    """Update a manifest entry after a download attempt.

    Writes the updated manifest to disk immediately so it survives crashes.
    Implements TODO 1.A3-a / 1.A3-b.
    """
    global _manifest, _manifest_path
    if not _manifest_path or url not in _manifest:
        return
    _manifest[url].update({
        "status": status,
        "file_size": file_size,
        "sha256": file_hash,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        with open(_manifest_path, "w", encoding="utf-8") as fh:
            json.dump(
                {"generated_at": _manifest.get("_meta_generated_at", ""),
                 "files": _manifest},
                fh, indent=2,
            )
    except OSError:
        pass  # Non-fatal: manifest update failures don't block downloads


# ── Session ────────────────────────────────────────────────────────────────────

def get_session() -> requests.Session:
    """Get or create global HTTP session with retry/pooling config."""
    global _global_session
    if _global_session is not None:
        return _global_session

    _global_session = requests.Session()
    _global_session.headers.update(HEADERS)
    # Optimization: Enhanced connection pool configuration
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=20,      # Increased from default 10
        pool_maxsize=30,          # Increased from default 10
        max_retries=requests.adapters.Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        ),
    )
    _global_session.mount("https://", adapter)
    _global_session.mount("http://", adapter)
    return _global_session


def _close_session():
    """Close global session and cleanup."""
    global _global_session
    if _global_session:
        _global_session.close()
    _global_session = None


# ── Playwright browser context (lazy init) ─────────────────────────────────────

_pw_instance = None
_pw_browser = None
_pw_context = None


# Playwright browser lifecycle management
# Current approach: Lazy initialization with manual cleanup via _close_browser()
# Optimization: Webdriver detection script added at context level (line ~868) applies
# to all pages created from this context, reducing per-page overhead.
# Future improvement: Could create a BrowserContextManager class to ensure cleanup
# via __exit__, but current approach works for single-threaded script.
def _get_browser_context():
    """Lazily initialize a Playwright browser context for WAF-protected sites."""
    global _pw_instance, _pw_browser, _pw_context
    if _pw_context is not None:
        return _pw_context

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\nERROR: Playwright is required for Army and Air Force sources.")
        print("Install it with:")
        print("  pip install playwright")
        print("  python -m playwright install chromium")
        sys.exit(1)

    print("  Starting browser for WAF-protected sites...")
    _pw_instance = sync_playwright().start()
    _pw_browser = _pw_instance.chromium.launch(
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--window-position=-32000,-32000",
        ],
    )
    _pw_context = _pw_browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1920, "height": 1080},
        accept_downloads=True,
    )
    # Optimization: Move webdriver detection script to context level (executed for all pages)
    _pw_context.add_init_script(
        'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
    )
    return _pw_context


def _close_browser():
    """Clean up and close the Playwright browser instance."""
    global _pw_instance, _pw_browser, _pw_context
    if _pw_browser:
        _pw_browser.close()
    if _pw_instance:
        _pw_instance.stop()
    _pw_instance = _pw_browser = _pw_context = None


def _browser_extract_links(url: str, text_filter: str | None = None,
                           expand_all: bool = False) -> list[dict]:
    """Use Playwright to load a page and extract downloadable file links."""
    ctx = _get_browser_context()
    page = ctx.new_page()

    try:
        # Optimization: Use adaptive timeout based on domain history
        timeout = _timeout_mgr.get_timeout(url, is_download=False)
        start = time.time()
        try:
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        except Exception:
            # If page load times out, proceed with what we have
            pass
        elapsed_ms = int((time.time() - start) * 1000)
        _timeout_mgr.record_time(url, elapsed_ms)

        if expand_all:
            btn = page.query_selector("text=Expand All")
            if btn:
                btn.click()
                # Optimization: Dynamic wait instead of fixed timeout
                try:
                    page.wait_for_selector("a[href]", timeout=5000)
                except Exception:
                    # If wait times out, proceed with current content
                    pass

        # Extract links via JavaScript in the browser
        raw = page.evaluate(f"""(args) => {{
            const [exts, tf] = args;
            const tf_arg = tf;
            const allLinks = Array.from(document.querySelectorAll('a[href]'));
            const files = [];
            const seen = new Set();
            const ignoredHosts = new Set(['dam.defense.gov']);
            for (const a of allLinks) {{
                const href = a.href;
                let path, host;
                try {{ const u = new URL(href); path = u.pathname.toLowerCase(); host = u.hostname.toLowerCase(); }} catch {{ continue; }}
                if (ignoredHosts.has(host)) continue;
                if (!exts.some(e => path.endsWith(e))) continue;
                if (tf_arg && !href.toLowerCase().includes(tf_arg.toLowerCase())) continue;
                if (seen.has(path)) continue;
                seen.add(path);
                const text = a.textContent.trim();
                const filename = decodeURIComponent(path.split('/').pop());
                const ext = '.' + filename.split('.').pop().toLowerCase();
                files.push({{ name: text || filename, url: href, filename: filename, extension: ext }});
            }}
            return files;
        }}""", [list(DOWNLOADABLE_EXTENSIONS), text_filter])

        return [_clean_file_entry(f) for f in raw]

    finally:
        page.close()


def _new_browser_page(ctx, url: str):
    """Create and initialize a new browser page navigated to the URL's origin.

    Sets up anti-bot/webdriver detection bypass and navigates to the origin
    to establish cookies/session before strategy-specific actions.

    Returns the page object. Caller is responsible for closing it.
    """
    page = ctx.new_page()
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    page.goto(origin, timeout=15000, wait_until="domcontentloaded")
    page.wait_for_timeout(500)
    return page


def _browser_download_file(url: str, dest_path: Path, overwrite: bool = False) -> bool:
    """Download a file using Playwright's browser context to bypass WAF.

    Fully automated — no user clicks required. Uses three strategies:
    1. Inject an anchor with download attribute to force download (no PDF viewer)
    2. Intercept via page.request.get() (API-level fetch with browser cookies)
    3. Navigate directly as last resort
    """
    if dest_path.exists() and not overwrite and dest_path.stat().st_size > 0:
        print(f"    [SKIP] Already exists: {dest_path.name}")
        return True

    ctx = _get_browser_context()
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Strategy 1: Use page.request API (fetch with browser session/cookies, no UI)
    try:
        page = _new_browser_page(ctx, url)
        resp = page.request.get(url, timeout=120000)
        if resp.ok and len(resp.body()) > 0:
            dest_path.write_bytes(resp.body())
            page.close()
            return True
        page.close()
    except Exception:
        try:
            page.close()
        except Exception:
            pass

    # Strategy 2: Trigger download via injected anchor element
    try:
        page = _new_browser_page(ctx, url)
        # Escape the URL for JS
        safe_url = url.replace("'", "\\'")
        safe_filename = dest_path.name.replace("'", "\\'")
        with page.expect_download(timeout=120000) as download_info:
            page.evaluate(f"""() => {{
                const a = document.createElement('a');
                a.href = '{safe_url}';
                a.download = '{safe_filename}';
                a.style.display = 'none';
                document.body.appendChild(a);
                a.click();
                a.remove();
            }}""")

        download = download_info.value
        download.save_as(str(dest_path))
        page.close()
        return True

    except Exception:
        try:
            page.close()
        except Exception:
            pass

    # Strategy 3: Direct navigation (may open PDF viewer, but content still loads)
    try:
        page = ctx.new_page()
        # Navigate directly to the URL (bypasses origin setup for simpler direct fetch)
        resp = page.goto(url, timeout=120000, wait_until="load")
        if resp and resp.ok:
            body = resp.body()
            if body and len(body) > 0:
                dest_path.write_bytes(body)
                page.close()
                return True
        page.close()
    except Exception:
        try:
            page.close()
        except Exception:
            pass

    # All strategies failed
    if dest_path.exists() and dest_path.stat().st_size == 0:
        dest_path.unlink()
    return False


# ── Helpers ────────────────────────────────────────────────────────────────────

# Magic-byte signatures for common DoD budget file types (Step 1.A3-b)
_MAGIC_BYTES: dict[str, bytes] = {
    ".pdf":  b"%PDF",           # PDF
    ".xlsx": b"PK\x03\x04",    # ZIP-based Office Open XML
    ".xlsm": b"PK\x03\x04",
    ".xls":  b"\xd0\xcf\x11\xe0",  # OLE2 Compound Document
    ".zip":  b"PK\x03\x04",
    ".docx": b"PK\x03\x04",
    ".pptx": b"PK\x03\x04",
}


def _verify_download(dest_path: Path) -> bool:
    """Verify a downloaded file has the expected magic bytes (Step 1.A3-b).

    Checks the first 4 bytes of the file against known signatures for PDF,
    Excel (both OOXML and legacy OLE2), and ZIP archives.  Files with
    unrecognised extensions are accepted if they are non-empty.

    Returns True if the file appears valid, False if it is empty or has an
    unexpected magic signature (e.g. an HTML error page saved as a .pdf).
    """
    try:
        size = dest_path.stat().st_size
    except OSError:
        return False

    if size == 0:
        return False

    ext = dest_path.suffix.lower()
    expected_magic = _MAGIC_BYTES.get(ext)
    if expected_magic is None:
        return True  # Unknown extension — accept as long as non-empty

    try:
        with open(dest_path, "rb") as fh:
            header = fh.read(len(expected_magic))
        return header == expected_magic
    except OSError:
        return False


def _clean_file_entry(f: dict) -> dict:
    """Sanitize a file entry dict."""
    f["filename"] = sanitize_filename(f["filename"])
    return f


def _extract_downloadable_links(soup: BeautifulSoup, page_url: str,
                                text_filter: str | None = None) -> list[dict]:
    """Extract all downloadable file links from a parsed page."""
    files = []
    seen_urls = set()

    # Optimization: Pre-compile filter if needed
    text_filter_lower = text_filter.lower() if text_filter else None

    for link in soup.find_all("a", href=True):
        href = link["href"]
        full_url = urljoin(page_url, href)

        parsed = urlparse(full_url)

        # Optimization: Predicate reordering - cheap checks first
        # Check #1: hostname (O(1) set lookup)
        if parsed.hostname and parsed.hostname.lower() in IGNORED_HOSTS:
            continue

        clean_path = parsed.path.lower()

        # Check #2: extension using compiled regex (O(1))
        if not DOWNLOADABLE_PATTERN.search(clean_path):
            continue

        # Check #3: text filter (O(n) substring search) - expensive, so check last
        if text_filter_lower and text_filter_lower not in full_url.lower():
            continue

        # Check #4: dedup (O(1) set lookup)
        dedup_key = parsed._replace(query="", fragment="").geturl()
        if dedup_key in seen_urls:
            continue
        seen_urls.add(dedup_key)

        # Only now extract text/filename
        link_text = link.get_text(strip=True)
        filename = unquote(Path(parsed.path).name)
        ext = Path(clean_path).suffix

        files.append({
            "name": link_text if link_text else filename,
            "url": full_url,
            "filename": sanitize_filename(filename),
            "extension": ext,
        })

    return files


# sanitize_filename is now imported from utils.common for consistency


def _is_browser_source(source: str) -> bool:
    """Check if a source requires browser access to work around WAF protection."""
    return source in BROWSER_REQUIRED_SOURCES


# ── Comptroller (main page) ───────────────────────────────────────────────────

# Cache fiscal years to avoid repeated discovery
_fiscal_years_cache = None


# Optimization: Discovery results caching
def _get_cache_key(source: str, year: str) -> str:
    """Generate cache key for discovery results."""
    return f"{source}_{year}"


def _load_cache(cache_key: str) -> list[dict] | None:
    """Load cached discovery results if still fresh (24 hours)."""
    cache_file = DISCOVERY_CACHE_DIR / f"{cache_key}.json"
    if not cache_file.exists():
        return None

    try:
        with open(cache_file, "r") as f:
            data = json.load(f)

        # Cache valid for 24 hours
        cached_time = datetime.fromisoformat(data.get("timestamp", ""))
        if (datetime.now() - cached_time).days < 1:
            return data.get("files", [])
    except (json.JSONDecodeError, OSError, ValueError):
        pass

    return None


def _save_cache(cache_key: str, files: list[dict]):
    """Save discovery results to cache."""
    try:
        DISCOVERY_CACHE_DIR.mkdir(exist_ok=True)
        cache_file = DISCOVERY_CACHE_DIR / f"{cache_key}.json"

        with open(cache_file, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "files": files
            }, f, indent=2)
    except Exception:
        # Silently fail if caching doesn't work
        pass


def discover_fiscal_years(session: requests.Session) -> dict[str, str]:
    """Scrape available fiscal years from the DoD Comptroller budget materials page.

    Returns:
        Dict mapping year strings (e.g. '2026') to their budget materials URLs,
        sorted newest-first. Cached after the first call.
    """
    global _fiscal_years_cache
    # Optimization: Cache fiscal years discovery
    if _fiscal_years_cache is not None:
        return _fiscal_years_cache

    print("Discovering available fiscal years...")
    resp = session.get(BUDGET_MATERIALS_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, PARSER)

    fy_links = {}
    for link in soup.find_all("a", href=True):
        text = link.get_text(strip=True)
        if re.fullmatch(r"(19|20)\d{2}", text):
            href = urljoin(BUDGET_MATERIALS_URL, link["href"])
            fy_links[text] = href

    _fiscal_years_cache = dict(sorted(fy_links.items(), key=lambda x: x[0], reverse=True))
    return _fiscal_years_cache


def discover_comptroller_files(session: requests.Session, year: str,
                               page_url: str) -> list[dict]:
    """Discover downloadable budget files on the DoD Comptroller page for a given fiscal year.

    Args:
        session: Active requests.Session for HTTP requests.
        year: Four-digit fiscal year string (e.g. '2026').
        page_url: URL of the comptroller budget materials page for this year.

    Returns:
        List of file dicts with keys: url, name, extension, source.
    """
    global _refresh_cache
    # Optimization: Check cache before fetching
    cache_key = _get_cache_key("comptroller", year)
    if not _refresh_cache:
        cached = _load_cache(cache_key)
        if cached is not None:
            print(f"  [Comptroller] Using cached results for FY{year}")
            return cached

    print(f"  [Comptroller] Scanning FY{year}...")
    resp = session.get(page_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, PARSER)
    files = _extract_downloadable_links(soup, page_url)
    _save_cache(cache_key, files)
    return files


# ── Defense Wide ──────────────────────────────────────────────────────────────

def discover_defense_wide_files(session: requests.Session, year: str) -> list[dict]:
    """Discover Defense-Wide budget justification files for a given fiscal year.

    Args:
        session: Active requests.Session.
        year: Four-digit fiscal year string.

    Returns:
        List of file dicts (url, name, extension, source).
    """
    global _refresh_cache
    # Optimization: Check cache before fetching
    cache_key = _get_cache_key("defense-wide", year)
    if not _refresh_cache:
        cached = _load_cache(cache_key)
        if cached is not None:
            print(f"  [Defense Wide] Using cached results for FY{year}")
            return cached

    url = SERVICE_PAGE_TEMPLATES["defense-wide"]["url"].format(fy=year)
    print(f"  [Defense Wide] Scanning FY{year}...")
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"    WARNING: Could not fetch Defense Wide page for FY{year}: {e}")
        return []
    soup = BeautifulSoup(resp.text, PARSER)
    files = _extract_downloadable_links(soup, url)
    _save_cache(cache_key, files)
    return files


# ── Army (browser required) ──────────────────────────────────────────────────

def discover_army_files(_session: requests.Session, year: str) -> list[dict]:
    """Discover US Army budget files for a given fiscal year using a headless browser.

    The Army website requires browser automation due to WAF protections on plain HTTP.

    Args:
        _session: Unused (browser handles HTTP); kept for interface consistency.
        year: Four-digit fiscal year string.

    Returns:
        List of file dicts (url, name, extension, source).
    """
    global _refresh_cache
    # Optimization: Check cache before fetching
    cache_key = _get_cache_key("army", year)
    if not _refresh_cache:
        cached = _load_cache(cache_key)
        if cached is not None:
            print(f"  [Army] Using cached results for FY{year}")
            return cached

    url = SERVICE_PAGE_TEMPLATES["army"]["url"]
    print(f"  [Army] Scanning FY{year} (browser)...")
    files = _browser_extract_links(url, text_filter=f"/{year}/")
    _save_cache(cache_key, files)
    return files


# ── Navy (browser required) ──────────────────────────────────────────────────

def discover_navy_files(_session: requests.Session, year: str) -> list[dict]:
    """Discover US Navy/Marine Corps budget files for a given fiscal year using a headless browser.

    Args:
        _session: Unused (browser handles HTTP); kept for interface consistency.
        year: Four-digit fiscal year string.

    Returns:
        List of file dicts (url, name, extension, source).
    """
    global _refresh_cache
    # Optimization: Check cache before fetching
    cache_key = _get_cache_key("navy", year)
    if not _refresh_cache:
        cached = _load_cache(cache_key)
        if cached is not None:
            print(f"  [Navy] Using cached results for FY{year}")
            return cached

    url = SERVICE_PAGE_TEMPLATES["navy"]["url"].format(fy=year)
    print(f"  [Navy] Scanning FY{year} (browser)...")
    files = _browser_extract_links(url)
    _save_cache(cache_key, files)
    return files


# ── Navy Archive (browser required) ────────────────────────────────────────────

def discover_navy_archive_files(_session: requests.Session, year: str) -> list[dict]:
    """Discover Navy budget files from the SECNAV archive page using a headless browser.

    Alternate source for Navy/Marine Corps exhibits hosted on the archive URL.

    Args:
        _session: Unused (browser handles HTTP); kept for interface consistency.
        year: Four-digit fiscal year string.

    Returns:
        List of file dicts (url, name, extension, source).
    """
    global _refresh_cache
    # Optimization: Check cache before fetching
    cache_key = _get_cache_key("navy-archive", year)
    if not _refresh_cache:
        cached = _load_cache(cache_key)
        if cached is not None:
            print(f"  [Navy Archive] Using cached results for FY{year}")
            return cached

    url = SERVICE_PAGE_TEMPLATES["navy-archive"]["url"]
    print(f"  [Navy Archive] Scanning FY{year} (browser)...")
    files = _browser_extract_links(url, text_filter=f"/{year}/")
    _save_cache(cache_key, files)
    return files


# ── Air Force (browser required) ─────────────────────────────────────────────

def discover_airforce_files(_session: requests.Session, year: str) -> list[dict]:
    """Discover US Air Force/Space Force budget files for a given fiscal year using a headless browser.

    Args:
        _session: Unused (browser handles HTTP); kept for interface consistency.
        year: Four-digit fiscal year string.

    Returns:
        List of file dicts (url, name, extension, source).
    """
    global _refresh_cache
    # Optimization: Check cache before fetching
    cache_key = _get_cache_key("airforce", year)
    if not _refresh_cache:
        cached = _load_cache(cache_key)
        if cached is not None:
            print(f"  [Air Force] Using cached results for FY{year}")
            return cached

    fy2 = year[-2:]
    url = SERVICE_PAGE_TEMPLATES["airforce"]["url"].format(fy2=fy2)
    print(f"  [Air Force] Scanning FY{year} (browser)...")
    files = _browser_extract_links(url, text_filter=f"FY{fy2}", expand_all=True)
    _save_cache(cache_key, files)
    return files


# ── Discovery router ─────────────────────────────────────────────────────────

SOURCE_DISCOVERERS = {
    "defense-wide": discover_defense_wide_files,
    "army": discover_army_files,
    "navy": discover_navy_files,
    "navy-archive": discover_navy_archive_files,
    "airforce": discover_airforce_files,
}


# ── Download ──────────────────────────────────────────────────────────────────
def _check_existing_file(session: requests.Session, url: str, dest_path: Path,
                         use_browser: bool = False,
                         expected_hash: str | None = None) -> str:
    """Check if a local file matches the remote.

    If expected_hash is provided (from the manifest, TODO 1.A3-b), verifies
    the local file's SHA-256 digest against it and triggers a redownload on
    mismatch (handles silent corruption).

    Returns:
        "skip"       - file exists and content matches (size or hash check)
        "redownload" - file exists but is corrupt/mismatched
        "download"   - file does not exist
    """
    if not dest_path.exists():
        return "download"

    local_size = dest_path.stat().st_size
    if local_size == 0:
        return "redownload"

    # TODO 1.A3-b: if we have a previously-recorded hash, verify it
    if expected_hash:
        local_hash = _compute_sha256(dest_path)
        if local_hash != expected_hash:
            print(f"\r    [HASH MISMATCH] {dest_path.name} — will redownload")
            return "redownload"
        return "skip"

    # Try to get remote size via HEAD request
    remote_size = None
    try:
        if use_browser:
            # For browser sources we can't easily HEAD, so trust local file
            # if it's non-empty
            return "skip"
        head = session.head(url, timeout=15, allow_redirects=True)
        if head.status_code < 400:
            cl = head.headers.get("content-length")
            if cl and cl.isdigit():
                remote_size = int(cl)
    except requests.RequestException:
        pass

    if remote_size is None:
        # Can't determine remote size — trust the local file
        return "skip"

    if local_size == remote_size:
        return "skip"

    return "redownload"


# Optimization: Adaptive chunk sizing based on file size
def _get_chunk_size(total_size: int) -> int:
    """Determine optimal chunk size based on file size."""
    if total_size <= 0:
        return 8192  # Default for unknown size
    if total_size < 5 * 1024 * 1024:  # < 5 MB
        return 4096   # Small chunks for small files
    if total_size < 100 * 1024 * 1024:  # < 100 MB
        return 8192   # Default
    if total_size < 1024 * 1024 * 1024:  # < 1 GB
        return 65536  # 64 KB chunks for large files
    return 262144  # 256 KB for huge files


def download_file(session: requests.Session, url: str, dest_path: Path,
                  overwrite: bool = False, use_browser: bool = False) -> bool:
    """Download a single file from url to dest_path, skipping if already current.

    Handles both direct HTTP downloads and browser-based downloads for WAF-protected
    sources. Updates the global progress tracker and manifest on completion.

    Args:
        session: Active requests.Session for HTTP downloads.
        url: Source URL to download from.
        dest_path: Local destination path.
        overwrite: If True, re-download even if the file already exists.
        use_browser: If True, use Playwright browser for the download.

    Returns:
        True if the file was successfully obtained (new, skipped, or redownloaded),
        False on error.
    """
    global _tracker
    fname = dest_path.name

    # Retrieve expected hash from manifest for integrity check (TODO 1.A3-b)
    expected_hash = (_manifest.get(url) or {}).get("sha256")

    if not overwrite and dest_path.exists():
        status = _check_existing_file(session, url, dest_path, use_browser,
                                      expected_hash=expected_hash)
        if status == "skip":
            size = dest_path.stat().st_size
            if _tracker:
                _tracker.file_done(fname, size, "skip")
            else:
                print(f"    [SKIP] Already exists: {fname}")
            update_manifest_entry(url, "skip", size, expected_hash)
            return True
        if status == "redownload":
            local_mb = dest_path.stat().st_size / (1024 * 1024)
            print(f"\r    [REDOWNLOAD] Size mismatch for {fname} "
                  f"(local {local_mb:.1f} MB)")

    if use_browser:
        ok = _browser_download_file(url, dest_path, overwrite=True)
        # Magic-byte integrity check after browser download (Step 1.A3-b)
        if ok and not _verify_download(dest_path):
            print(f"\r    [CORRUPT] {fname}: unexpected file format "
                  f"(HTML error page from browser?)          ")
            dest_path.unlink(missing_ok=True)
            ok = False

        size = dest_path.stat().st_size if dest_path.exists() else 0
        file_hash = _compute_sha256(dest_path) if ok and dest_path.exists() else None
        if _tracker:
            if ok:
                _tracker.file_done(fname, size, "ok")
            else:
                _tracker.file_failed(url, str(dest_path), fname,
                                     "browser download failed", use_browser=True)
        update_manifest_entry(url, "ok" if ok else "fail", size, file_hash)
        return ok

    file_start = time.time()
    _retry_delays = [2, 4, 8]
    last_exc = None
    for attempt in range(len(_retry_delays) + 1):
        if attempt > 0:
            delay = _retry_delays[attempt - 1]
            print(f"\r    [RETRY {attempt}/{len(_retry_delays)}] {fname}: "
                  f"retrying in {delay}s...          ")
            time.sleep(delay)
        try:
            # Optimization: Check if we can resume from partial download
            resume_from = 0
            if dest_path.exists() and dest_path.stat().st_size > 0:
                resume_from = dest_path.stat().st_size
                # Verify server supports range requests
                try:
                    head_resp = session.head(url, timeout=15)
                    accept_ranges = head_resp.headers.get("accept-ranges", "none").lower()
                    if accept_ranges == "none":
                        # Server doesn't support resume, delete and restart
                        dest_path.unlink()
                        resume_from = 0
                except Exception:
                    # If HEAD fails, just restart
                    dest_path.unlink()
                    resume_from = 0

            headers = {}
            mode = "ab" if resume_from > 0 else "wb"
            if resume_from > 0:
                headers["Range"] = f"bytes={resume_from}-"

            resp = session.get(url, headers=headers, timeout=120, stream=True)
            resp.raise_for_status()

            # Validate Content-Range header if resuming
            if resume_from > 0 and resp.status_code != 206:
                # Server doesn't support range, restart
                dest_path.unlink()
                resp = session.get(url, timeout=120, stream=True)
                resp.raise_for_status()
                mode = "wb"
                resume_from = 0

            total_size = int(resp.headers.get("content-length", 0)) + resume_from
            downloaded = resume_from
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # Optimization: Adaptive chunk sizing based on file size
            # TODO 1.A3-b: compute SHA-256 while streaming (no extra I/O pass)
            chunk_size = _get_chunk_size(total_size)

            sha256 = hashlib.sha256()
            with open(dest_path, mode) as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    f.write(chunk)
                    sha256.update(chunk)
                    downloaded += len(chunk)
                    if _tracker:
                        _tracker.print_file_progress(
                            fname, downloaded, total_size, file_start
                        )

            file_hash = sha256.hexdigest()

            # Magic-byte integrity check after write (Step 1.A3-b)
            if not _verify_download(dest_path):
                print(f"\r    [CORRUPT] {fname}: unexpected file format "
                      f"(HTML error page?)          ")
                dest_path.unlink(missing_ok=True)
                last_exc = RuntimeError("magic-byte verification failed")
                continue  # Retry loop

            if _tracker:
                _tracker.file_done(fname, downloaded, "ok")
            else:
                size_mb = downloaded / (1024 * 1024)
                print(f"\r    [OK] {fname} ({size_mb:.1f} MB)          ")
            update_manifest_entry(url, "ok", downloaded, file_hash)
            return True

        except requests.RequestException as e:
            last_exc = e
            # Don't delete file on error - we'll try to resume next attempt
            if dest_path.exists() and dest_path.stat().st_size == 0:
                dest_path.unlink()

    if _tracker:
        _tracker.file_failed(url, str(dest_path), fname, str(last_exc),
                             use_browser=False)
    else:
        print(f"\r    [FAIL] {fname}: {last_exc}          ")
    update_manifest_entry(url, "fail", 0, None)
    return False


def _extract_zip(zip_path: Path, dest_dir: Path):
    """Extract a ZIP archive into dest_dir and log the result."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            zf.extractall(dest_dir)
            print(f"    [ZIP] Extracted {len(names)} file(s) from {zip_path.name}")
    except zipfile.BadZipFile as e:
        print(f"    [ZIP] Bad ZIP, skipping extraction of {zip_path.name}: {e}")


# ── Display ───────────────────────────────────────────────────────────────────

def list_files(all_files: dict[str, dict[str, list[dict]]]) -> None:
    """Print a dry-run listing of all discovered files grouped by fiscal year and source.

    Args:
        all_files: Nested dict {year: {source_label: [file_dict, ...]}} from discovery.
    """
    grand_total = 0
    for year in sorted(all_files.keys(), reverse=True):
        sources = all_files[year]
        year_total = sum(len(f) for f in sources.values())
        print(f"\n{'='*70}")
        print(f"  FY{year} - {year_total} file(s)")
        print(f"{'='*70}")
        for source_label, files in sources.items():
            print(f"\n  [{source_label}] ({len(files)} files)")
            print(f"  {'-'*50}")
            for f in files:
                print(f"    [{f['extension'].upper().strip('.')}] {f['name']}")
                print(f"          {f['url']}")
        grand_total += year_total
    print(f"\nTotal: {grand_total} file(s)")


# ── Interactive ───────────────────────────────────────────────────────────────

def _interactive_select(title: str, items: list[str], item_labels: dict[str, str] | None = None,
                        all_label: str = "All") -> list[str]:
    """Generic interactive selection menu for numbered list input.

    Args:
        title: Header to display above the menu
        items: List of items to choose from
        item_labels: Optional dict mapping items to display labels (defaults to items themselves)
        all_label: Label for the "All items" option

    Returns:
        List of selected items
    """
    if item_labels is None:
        item_labels = {item: item for item in items}

    print(f"\n{title}")
    print("-" * 50)
    for i, item in enumerate(items, 1):
        print(f"  {i}. {item_labels.get(item, item)}")
    print(f"  {len(items)+1}. All {all_label.lower()}")
    print()

    while True:
        raw = input(
            "Enter numbers separated by commas (e.g. 1,2,3) or 'q' to quit: "
        ).strip()
        if raw.lower() == "q":
            sys.exit(0)
        try:
            choices = [int(x.strip()) for x in raw.split(",")]
        except ValueError:
            print("Invalid input. Please enter numbers separated by commas.")
            continue

        # Check if "all" was selected
        if len(items) + 1 in choices:
            return items

        selected = []
        valid = True
        for c in choices:
            if 1 <= c <= len(items):
                selected.append(items[c - 1])
            else:
                print(f"Invalid choice: {c}")
                valid = False
                break
        if valid and selected:
            return selected


def interactive_select_years(available: dict[str, str]) -> list[str]:
    """Prompt the user to select fiscal years interactively.

    Args:
        available: Dict mapping year strings to URLs (from discover_fiscal_years).

    Returns:
        List of selected year strings.
    """
    years = list(available.keys())
    year_labels = {year: f"FY{year}" for year in years}
    return _interactive_select("Available Fiscal Years:", years, year_labels, "fiscal years")


def interactive_select_sources() -> list[str]:
    """Prompt the user to select download sources interactively.

    Returns:
        List of selected source identifier strings (e.g. ['army', 'navy']).
    """
    labels = {
        "comptroller": "Comptroller (main DoD summary documents)",
        "defense-wide": "Defense Wide (budget justification books)",
        "army": "US Army",
        "navy": "US Navy / Marine Corps",
        "navy-archive": "US Navy Archive",
        "airforce": "US Air Force / Space Force",
    }
    return _interactive_select("Available Sources:", list(ALL_SOURCES), labels, "sources")


# ── Programmatic download entry point (TODO 1.A4-a) ─────────────────────────


def download_all(
    all_files: dict,
    output_dir: Path,
    browser_labels: set,
    *,
    overwrite: bool = False,
    delay: float = 0.5,
    extract_zips: bool = False,
    use_gui: bool = False,
    manifest_path: Path | None = None,
) -> dict:
    """Download all discovered files and return a summary dict.

    This is the programmatic interface decoupled from argparse/sys.argv, so it
    can be called from cron jobs, CI pipelines, or the data-refresh script
    (TODO 2.B4-a) without depending on the interactive/GUI layer.

    Args:
        all_files:      Nested dict {year: {source_label: [file_info, ...]}}
                        as returned by the discover_* functions.
        output_dir:     Root directory to write downloaded files into.
        browser_labels: Set of source labels that require Playwright.
        overwrite:      Re-download files that already exist locally.
        delay:          Seconds to sleep between requests (rate-limit courtesy).
        extract_zips:   Automatically extract .zip archives after downloading.
        use_gui:        Show a Tkinter GUI progress window (requires display).
        manifest_path:  Where to write/update the download manifest JSON.
                        Defaults to output_dir/manifest.json.

    Returns:
        Summary dict with keys: downloaded, skipped, failed, total_bytes.
    """
    global _tracker

    if manifest_path is None:
        manifest_path = output_dir / "manifest.json"

    # Write initial manifest before downloading (TODO 1.A3-a)
    write_manifest(output_dir, all_files, manifest_path)

    session = get_session()

    total_files = sum(
        len(f) for yr in all_files.values() for f in yr.values()
    )
    print(f"\nReady to download {total_files} file(s) to: {output_dir.resolve()}\n")

    if use_gui:
        _tracker = GuiProgressTracker(total_files)
    else:
        _tracker = ProgressTracker(total_files)
        _tracker.print_overall()
        print()

    for year in sorted(all_files.keys(), reverse=True):
        sources = all_files[year]
        year_total = sum(len(f) for f in sources.values())
        if year_total == 0:
            print(f"\n  FY{year}: No matching files found.")
            continue

        for source_label, files in sources.items():
            if not files:
                continue

            use_browser = source_label in browser_labels
            safe_label = source_label.replace(" ", "_")
            dest_dir = output_dir / f"FY{year}" / safe_label
            print(f"\n{'='*70}")
            method = "browser" if use_browser else "direct"
            print(f"  FY{year} / {source_label} "
                  f"({len(files)} files, {method}) -> {dest_dir}")
            print(f"{'='*70}")
            _tracker.set_source(year, source_label)

            # Pre-filter: skip files that already exist locally (non-empty)
            to_download = []
            if not overwrite:
                for file_info in files:
                    dest = dest_dir / file_info["filename"]
                    if dest.exists() and dest.stat().st_size > 0:
                        size = dest.stat().st_size
                        if _tracker:
                            _tracker.file_done(dest.name, size, "skip")
                        else:
                            print(f"    [SKIP] Already exists: {dest.name}")
                        update_manifest_entry(file_info["url"], "skip", size,
                                              (_manifest.get(file_info["url"]) or {}).get("sha256"))
                    else:
                        to_download.append(file_info)
            else:
                to_download = files

            for file_info in to_download:
                dest = dest_dir / file_info["filename"]
                ok = download_file(
                    session, file_info["url"], dest,
                    overwrite, use_browser=use_browser,
                )
                if ok and extract_zips and dest.suffix.lower() == ".zip":
                    _extract_zip(dest, dest_dir)
                time.sleep(delay)

    summary = {
        "downloaded": _tracker.completed,
        "skipped": _tracker.skipped,
        "failed": _tracker.failed,
        "total_bytes": _tracker.total_bytes,
    }

    # Write structured failure log for --retry-failures (TODO 1.A6-a)
    # JSON schema: list of {url, dest, filename, error, source, year,
    #                        use_browser, timestamp}
    failed_json_path = output_dir / "failed_downloads.json"
    if _tracker._failed_files:
        failed_json_path.write_text(
            json.dumps(_tracker._failed_files, indent=2), encoding="utf-8"
        )
        print(f"\n  Failure log: {failed_json_path}")
        print(f"  Retry with: python dod_budget_downloader.py "
              f"--retry-failures {failed_json_path}")
    elif failed_json_path.exists():
        # Clean up stale failure log from a previous run
        failed_json_path.unlink()

    if isinstance(_tracker, GuiProgressTracker):
        total_dl = format_bytes(_tracker.total_bytes)
        elapsed_str = elapsed(_tracker.start_time)
        _tracker._log_lines.append(
            f"\n--- Complete: {_tracker.completed} downloaded, "
            f"{_tracker.skipped} skipped, {_tracker.failed} failed "
            f"({total_dl}, {elapsed_str}) ---")
        time.sleep(0.3)
        summary_str = (
            f"Downloaded: {_tracker.completed}   Skipped: {_tracker.skipped}   "
            f"Failed: {_tracker.failed}\n"
            f"Total size: {total_dl}   Elapsed: {elapsed_str}"
        )
        _tracker.show_completion_dialog(summary_str)

    _tracker = None
    _close_browser()
    return summary


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    """Parse CLI arguments and run the interactive or unattended download pipeline."""
    parser = argparse.ArgumentParser(
        description="Download budget documents from DoD Comptroller and service websites."
    )
    parser.add_argument(
        "--years", nargs="+",
        help='Fiscal years to download (e.g. 2026 2025) or "all"',
    )
    parser.add_argument(
        "--sources", nargs="+",
        help=(
            'Sources to download from: comptroller, defense-wide, army, navy, '
            'airforce, or "all". Default: comptroller only.'
        ),
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_only",
        help="List available files without downloading",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing files instead of skipping",
    )
    parser.add_argument(
        "--types", nargs="+", default=None,
        help='File types to download (e.g. pdf xlsx). Default: all types',
    )
    parser.add_argument(
        "--no-gui", action="store_true",
        help="Disable GUI progress window (terminal-only output)",
    )
    parser.add_argument(
        "--delay", type=float, default=0.5,
        help="Seconds to wait between requests (default: 0.5)",
    )
    parser.add_argument(
        "--extract-zips", action="store_true", dest="extract_zips",
        help="Extract ZIP archives after downloading them",
    )
    parser.add_argument(
        "--refresh-cache", action="store_true", dest="refresh_cache",
        help="Ignore cache and refresh discovery from source",
    )
    parser.add_argument(
        "--retry-failures", nargs="?", const=None, default=False,
        metavar="PATH",
        dest="retry_failures",
        help=(
            "Re-download only previously failed files. Reads from "
            "failed_downloads.json in the output directory by default, "
            "or from PATH if specified. Skips discovery. (TODO 1.A6-b)"
        ),
    )
    args = parser.parse_args()

    # Optimization: Set global flag for cache refresh
    global _refresh_cache
    _refresh_cache = args.refresh_cache

    # ── Retry-failures early path (TODO 1.A6-b) ──────────────────────────────
    if args.retry_failures is not False:
        # Determine the path to read failures from
        failures_path = (
            Path(args.retry_failures)
            if args.retry_failures is not None
            else args.output / "failed_downloads.json"
        )
        if not failures_path.exists():
            print(f"ERROR: Failure log not found: {failures_path}")
            print("Run a download first to generate the failure log.")
            sys.exit(1)

        with open(failures_path) as fp:
            failed_entries: list[dict] = json.load(fp)

        if not failed_entries:
            print("No failures to retry.")
            sys.exit(0)

        print(f"Retrying {len(failed_entries)} failed download(s)...")
        session = get_session()
        tracker = (ProgressTracker if args.no_gui else GuiProgressTracker)(len(failed_entries))
        global _tracker
        _tracker = tracker

        still_failed: list[dict] = []
        for entry in failed_entries:
            url = entry["url"]
            dest = Path(entry["dest"])
            fname = entry["filename"]
            use_browser = entry.get("use_browser", False)
            source = entry.get("source", "")
            year = entry.get("year", "")

            _tracker.set_source(year, source)
            ok = download_file(session, url, dest, overwrite=True,
                               use_browser=use_browser)
            if not ok:
                still_failed.append(entry)

        # Write updated failure log: only entries that failed again
        if still_failed:
            failures_path.write_text(
                json.dumps(still_failed, indent=2), encoding="utf-8"
            )
            print(f"\n  {len(still_failed)} file(s) still failed — "
                  f"log updated: {failures_path}")
        else:
            failures_path.unlink(missing_ok=True)
            print("\n  All retries succeeded.")

        _tracker = None
        _close_browser()
        _close_session()
        sys.exit(1 if still_failed else 0)

    session = get_session()

    # ── Discover fiscal years ──
    available_years = discover_fiscal_years(session)
    if not available_years:
        print("ERROR: Could not find any fiscal year links on the website.")
        sys.exit(1)

    print(f"Found {len(available_years)} fiscal years: "
          f"{', '.join(list(available_years.keys())[:5])}...")

    # ── Select years ──
    if args.years:
        if "all" in [y.lower() for y in args.years]:
            selected_years = list(available_years.keys())
        else:
            selected_years = []
            for y in args.years:
                if y in available_years:
                    selected_years.append(y)
                else:
                    print(f"WARNING: FY{y} not found. Available: "
                          f"{', '.join(available_years.keys())}")
            if not selected_years:
                print("No valid fiscal years selected.")
                sys.exit(1)
    else:
        selected_years = interactive_select_years(available_years)

    print(f"\nSelected years: {', '.join(f'FY{y}' for y in selected_years)}")

    # ── Select sources ──
    if args.sources:
        if "all" in [s.lower() for s in args.sources]:
            selected_sources = list(ALL_SOURCES)
        else:
            selected_sources = []
            for s in args.sources:
                s_lower = s.lower().replace("_", "-")
                if s_lower in ALL_SOURCES:
                    selected_sources.append(s_lower)
                else:
                    print(f"WARNING: Unknown source '{s}'. "
                          f"Available: {', '.join(ALL_SOURCES)}")
            if not selected_sources:
                print("No valid sources selected.")
                sys.exit(1)
    else:
        if args.years:
            selected_sources = ["comptroller"]
        else:
            selected_sources = interactive_select_sources()

    print(f"Selected sources: {', '.join(selected_sources)}")

    # Track which sources need browser for download
    needs_browser = any(s in BROWSER_REQUIRED_SOURCES for s in selected_sources)

    # ── File type filter ──
    type_filter = None
    if args.types:
        type_filter = {f".{t.lower().strip('.')}" for t in args.types}
        print(f"File type filter: {', '.join(type_filter)}")

    # ── Discover files ──
    all_files: dict[str, dict[str, list[dict]]] = {}
    # Track which source labels need browser downloads
    browser_labels: set[str] = set()

    for year in selected_years:
        all_files[year] = {}

        for source in selected_sources:
            if source == "comptroller":
                url = available_years[year]
                files = discover_comptroller_files(session, year, url)
            else:
                discoverer = SOURCE_DISCOVERERS[source]
                files = discoverer(session, year)

            if type_filter:
                files = [f for f in files if f["extension"] in type_filter]

            label = (SERVICE_PAGE_TEMPLATES[source]["label"]
                     if source != "comptroller" else "Comptroller")
            all_files[year][label] = files

            if _is_browser_source(source):
                browser_labels.add(label)

            time.sleep(args.delay)

    # ── List mode ──
    if args.list_only:
        list_files(all_files)
        _close_browser()
        return

    # ── Download via download_all() (TODO 1.A4-a) ──
    summary = download_all(
        all_files,
        args.output,
        browser_labels,
        overwrite=args.overwrite,
        delay=args.delay,
        extract_zips=args.extract_zips,
        use_gui=not args.no_gui,
        manifest_path=args.output / "manifest.json",
    )

    # ── Terminal summary (GUI summary is shown inside download_all) ──
    if args.no_gui:
        total_dl = format_bytes(summary["total_bytes"])
        print(f"\n\n{'='*70}")
        print(f"  Download Complete")
        print(f"{'='*70}")
        print(f"  Downloaded: {summary['downloaded']}")
        print(f"  Skipped:    {summary['skipped']}")
        print(f"  Failed:     {summary['failed']}")
        print(f"  Total size: {total_dl}")
        print(f"  Location:   {args.output.resolve()}")
        print(f"  Manifest:   {args.output / 'manifest.json'}")

    # Optimization: Cleanup browser and session
    _close_browser()
    _close_session()


if __name__ == "__main__":
    main()
