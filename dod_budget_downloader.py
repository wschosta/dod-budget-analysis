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
import os
import re
import shutil
import sys
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

# ── Configuration ──────────────────────────────────────────────────────────────
global tracker

BASE_URL = "https://comptroller.war.gov"
BUDGET_MATERIALS_URL = f"{BASE_URL}/Budget-Materials/"
DOWNLOADABLE_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".zip", ".csv"}
IGNORED_HOSTS = {"dam.defense.gov"}
DEFAULT_OUTPUT_DIR = Path("DoD_Budget_Documents")

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

def _format_bytes(b: int) -> str:
    """Format bytes into human-readable size string."""
    if b < 1024 * 1024:
        return f"{b / 1024:.0f} KB"
    if b < 1024 * 1024 * 1024:
        return f"{b / (1024 * 1024):.1f} MB"
    return f"{b / (1024 * 1024 * 1024):.2f} GB"


def _elapsed(start_time: float) -> str:
    """Format elapsed time from start_time to now as human-readable string."""
    secs = int(time.time() - start_time)
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


class ProgressTracker:
    """Tracks overall download session progress and renders status bars."""

    def __init__(self, total_files: int):
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

    @property
    def processed(self) -> int:
        return self.completed + self.skipped + self.failed

    def _bar(self, fraction: float, width: int = 30) -> str:
        filled = int(width * fraction)
        return f"[{'#' * filled}{'-' * (width - filled)}]"

    def set_source(self, year: str, source: str):
        self.current_year = year
        self.current_source = source

    def print_overall(self):
        """Print the overall progress line."""
        frac = self.processed / self.total_files if self.total_files else 0
        pct = frac * 100
        bar = self._bar(frac, 25)
        dl = _format_bytes(self.total_bytes)
        elapsed = _elapsed(self.start_time)
        remaining = self.total_files - self.processed
        line = (
            f"\r  Overall: {bar} {pct:5.1f}%  "
            f"{self.processed}/{self.total_files} files  "
            f"{dl} downloaded  "
            f"{elapsed} elapsed  "
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
            print(f"\r    Downloading {filename}... {_format_bytes(downloaded)}",
                  end="", flush=True)
            return

        frac = downloaded / total
        pct = frac * 100
        bar = self._bar(frac, 20)
        elapsed = time.time() - file_start
        speed = downloaded / elapsed if elapsed > 0 else 0
        speed_str = f"{_format_bytes(int(speed))}/s"
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
            f"{_format_bytes(downloaded)}/{_format_bytes(total)}  "
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

        size_str = _format_bytes(size) if size > 0 else ""
        line = f"    [{tag}] {filename} ({size_str})" if size_str else f"    [{tag}] {filename}"
        print(f"\r{line:<{self.term_width}}")
        self.print_overall()


# ── GUI Progress Tracker ─────────────────────────────────────────────────────

class GuiProgressTracker:
    """Tkinter GUI window that displays download progress."""

    def __init__(self, total_files: int):
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

        self._closed = False
        self._ready = threading.Event()

        self._thread = threading.Thread(target=self._run_gui, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    @property
    def processed(self) -> int:
        return self.completed + self.skipped + self.failed

    def _run_gui(self):
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
            f"{_format_bytes(self.total_bytes)} downloaded  |  "
            f"{_elapsed(self.start_time)} elapsed  |  "
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
                elapsed = time.time() - self._file_start
                speed = dl / elapsed if elapsed > 0 else 0
                speed_str = f"{_format_bytes(int(speed))}/s"
                self._file_lbl.set(fname)
                self._file_stats_var.set(
                    f"{_format_bytes(dl)} / {_format_bytes(total)}  "
                    f"  {speed_str}")
            else:
                self._file_bar["value"] = 0
                self._file_lbl.set(f"{fname}  ({_format_bytes(dl)})")
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

    def _on_close(self):
        self._closed = True
        self._root.destroy()

    def set_source(self, year: str, source: str):
        self.current_year = year
        self.current_source = source

    def print_overall(self):
        pass  # GUI updates via _poll

    def print_file_progress(self, filename: str, downloaded: int, total: int,
                            file_start: float):
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

        size_str = f" ({_format_bytes(size)})" if size > 0 else ""
        log_entry = f"[{tag}] {filename}{size_str}"
        self._log_lines.append(log_entry)
        if status == "fail":
            self._failure_lines.append(log_entry)

        # Reset file bar
        self._file_name = ""
        self._file_downloaded = 0
        self._file_total = 0

    def show_completion_dialog(self, summary: str):
        """Replace the progress window with a completion dialog.

        Shows a summary message, a Close button, and (if there were
        failures) a View Failures button that opens the failure lines
        in a scrollable text window.
        """
        import tkinter as tk
        from tkinter import ttk

        failure_lines = list(self._failure_lines)

        # Destroy the old progress window
        self.close()

        # Build completion dialog
        dlg = tk.Tk()
        dlg.title("Download Complete")
        dlg.geometry("460x200")
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
            win = tk.Toplevel(dlg)
            win.title("Failed Downloads")
            win.geometry("560x320")
            win.attributes("-topmost", True)
            txt = tk.Text(win, wrap="word", font=("Consolas", 9))
            sb = ttk.Scrollbar(win, orient="vertical", command=txt.yview)
            txt.configure(yscrollcommand=sb.set)
            txt.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
            txt.insert("end", "\n".join(failure_lines) if failure_lines
                       else "No failure details available.")
            txt.configure(state="disabled")

        if self.failed > 0 and failure_lines:
            ttk.Button(btn_frame, text="View Failures",
                       command=_view_failures).pack(side="left", padx=6)

        ttk.Button(btn_frame, text="Close",
                   command=dlg.destroy).pack(side="left", padx=6)

        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.mainloop()

    def close(self):
        """Close the GUI window."""
        if not self._closed and hasattr(self, '_root'):
            self._closed = True
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass


# TODO: Replace global mutable state (_tracker, _failure_log, _pw_instance,
# _pw_browser, _pw_context) with a DownloadSession class that encapsulates
# tracker, failure log, and browser lifecycle. This would make the code more
# testable and avoid implicit coupling through module globals.

# Global tracker, set during main()
_tracker: ProgressTracker | GuiProgressTracker | None = None


# ── Session ────────────────────────────────────────────────────────────────────

def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)
    adapter = requests.adapters.HTTPAdapter(
        max_retries=requests.adapters.Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ── Playwright browser context (lazy init) ─────────────────────────────────────

_pw_instance = None
_pw_browser = None
_pw_context = None


# TODO: Encapsulate Playwright lifecycle in a context manager class so the
# browser is reliably cleaned up, and replace the 5 repeated calls to
# page.add_init_script('Object.defineProperty(navigator, "webdriver", ...)')
# with a shared helper that creates pre-configured pages.
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
    page.add_init_script(
        'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
    )

    try:
        page.goto(url, timeout=30000, wait_until="networkidle")

        if expand_all:
            btn = page.query_selector("text=Expand All")
            if btn:
                btn.click()
                page.wait_for_timeout(1500)

        # Extract links via JavaScript in the browser
        js_filter = f"'{text_filter}'" if text_filter else "null"
        raw = page.evaluate(f"""(exts, tf) => {{
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
        }}""", list(DOWNLOADABLE_EXTENSIONS), text_filter)

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
    page.add_init_script(
        'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
    )
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
        with page.expect_download(timeout=120000) as download_info:
            page.evaluate(f"""() => {{
                const a = document.createElement('a');
                a.href = '{safe_url}';
                a.download = '{dest_path.name.replace("'", "\\'")}';
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
        page.add_init_script(
            'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        )
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

def _clean_file_entry(f: dict) -> dict:
    """Sanitize a file entry dict."""
    f["filename"] = _sanitize_filename(f["filename"])
    return f


def _extract_downloadable_links(soup: BeautifulSoup, page_url: str,
                                text_filter: str | None = None) -> list[dict]:
    """Extract all downloadable file links from a parsed page."""
    files = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        full_url = urljoin(page_url, href)

        parsed = urlparse(full_url)
        if parsed.hostname and parsed.hostname.lower() in IGNORED_HOSTS:
            continue

        clean_path = parsed.path.lower()

        ext = Path(clean_path).suffix
        if ext not in DOWNLOADABLE_EXTENSIONS:
            continue

        if text_filter and text_filter.lower() not in full_url.lower():
            continue

        dedup_key = parsed._replace(query="", fragment="").geturl()
        if dedup_key in seen_urls:
            continue
        seen_urls.add(dedup_key)

        link_text = link.get_text(strip=True)
        filename = unquote(Path(parsed.path).name)

        files.append({
            "name": link_text if link_text else filename,
            "url": full_url,
            "filename": _sanitize_filename(filename),
            "extension": ext,
        })

    return files


def _sanitize_filename(name: str) -> str:
    if "?" in name:
        name = name.split("?")[0]
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    return name


def _is_browser_source(source: str) -> bool:
    return source in BROWSER_REQUIRED_SOURCES


# ── Comptroller (main page) ───────────────────────────────────────────────────

def discover_fiscal_years(session: requests.Session) -> dict[str, str]:
    print("Discovering available fiscal years...")
    resp = session.get(BUDGET_MATERIALS_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    fy_links = {}
    for link in soup.find_all("a", href=True):
        text = link.get_text(strip=True)
        if re.fullmatch(r"(19|20)\d{2}", text):
            href = urljoin(BUDGET_MATERIALS_URL, link["href"])
            fy_links[text] = href

    return dict(sorted(fy_links.items(), key=lambda x: x[0], reverse=True))


def discover_comptroller_files(session: requests.Session, year: str,
                               page_url: str) -> list[dict]:
    print(f"  [Comptroller] Scanning FY{year}...")
    resp = session.get(page_url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return _extract_downloadable_links(soup, page_url)


# ── Defense Wide ──────────────────────────────────────────────────────────────

def discover_defense_wide_files(session: requests.Session, year: str) -> list[dict]:
    url = SERVICE_PAGE_TEMPLATES["defense-wide"]["url"].format(fy=year)
    print(f"  [Defense Wide] Scanning FY{year}...")
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"    WARNING: Could not fetch Defense Wide page for FY{year}: {e}")
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    return _extract_downloadable_links(soup, url)


# ── Army (browser required) ──────────────────────────────────────────────────

def discover_army_files(_session: requests.Session, year: str) -> list[dict]:
    url = SERVICE_PAGE_TEMPLATES["army"]["url"]
    print(f"  [Army] Scanning FY{year} (browser)...")
    files = _browser_extract_links(url, text_filter=f"/{year}/")
    return files


# ── Navy (browser required) ──────────────────────────────────────────────────

def discover_navy_files(_session: requests.Session, year: str) -> list[dict]:
    url = SERVICE_PAGE_TEMPLATES["navy"]["url"].format(fy=year)
    print(f"  [Navy] Scanning FY{year} (browser)...")
    files = _browser_extract_links(url)
    return files


# ── Navy Archive (browser required) ────────────────────────────────────────────

def discover_navy_archive_files(_session: requests.Session, year: str) -> list[dict]:
    url = SERVICE_PAGE_TEMPLATES["navy-archive"]["url"]
    print(f"  [Navy Archive] Scanning FY{year} (browser)...")
    files = _browser_extract_links(url, text_filter=f"/{year}/")
    return files


# ── Air Force (browser required) ─────────────────────────────────────────────

def discover_airforce_files(_session: requests.Session, year: str) -> list[dict]:
    fy2 = year[-2:]
    url = SERVICE_PAGE_TEMPLATES["airforce"]["url"].format(fy2=fy2)
    print(f"  [Air Force] Scanning FY{year} (browser)...")
    files = _browser_extract_links(url, text_filter=f"FY{fy2}", expand_all=True)
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
                         use_browser: bool = False) -> str:
    """Check if a local file matches the remote.

    Returns:
        "skip"     - file exists and size matches (or remote size unknown)
        "redownload" - file exists but size mismatch (partial/corrupt)
        "download" - file does not exist
    """
    if not dest_path.exists():
        return "download"

    local_size = dest_path.stat().st_size
    if local_size == 0:
        return "redownload"

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


def download_file(session: requests.Session, url: str, dest_path: Path,
                  overwrite: bool = False, use_browser: bool = False) -> bool:
    global _tracker
    fname = dest_path.name

    if not overwrite and dest_path.exists():
        status = _check_existing_file(session, url, dest_path, use_browser)
        if status == "skip":
            size = dest_path.stat().st_size
            if _tracker:
                _tracker.file_done(fname, size, "skip")
            else:
                print(f"    [SKIP] Already exists: {fname}")
            return True
        if status == "redownload":
            local_mb = dest_path.stat().st_size / (1024 * 1024)
            print(f"\r    [REDOWNLOAD] Size mismatch for {fname} "
                  f"(local {local_mb:.1f} MB)")

    if use_browser:
        ok = _browser_download_file(url, dest_path, overwrite=True)
        if _tracker:
            size = dest_path.stat().st_size if dest_path.exists() else 0
            _tracker.file_done(fname, size, "ok" if ok else "fail")
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
            resp = session.get(url, timeout=120, stream=True)
            resp.raise_for_status()

            total_size = int(resp.headers.get("content-length", 0))
            downloaded = 0
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if _tracker:
                        _tracker.print_file_progress(
                            fname, downloaded, total_size, file_start
                        )

            if _tracker:
                _tracker.file_done(fname, downloaded, "ok")
            else:
                size_mb = downloaded / (1024 * 1024)
                print(f"\r    [OK] {fname} ({size_mb:.1f} MB)          ")
            return True

        except requests.RequestException as e:
            last_exc = e
            if dest_path.exists():
                dest_path.unlink()

    if _tracker:
        _tracker.file_done(fname, 0, "fail")
    else:
        print(f"\r    [FAIL] {fname}: {last_exc}          ")
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
    years = list(available.keys())
    year_labels = {year: f"FY{year}" for year in years}
    return _interactive_select("Available Fiscal Years:", years, year_labels, "fiscal years")


def interactive_select_sources() -> list[str]:
    labels = {
        "comptroller": "Comptroller (main DoD summary documents)",
        "defense-wide": "Defense Wide (budget justification books)",
        "army": "US Army",
        "navy": "US Navy / Marine Corps",
        "navy-archive": "US Navy Archive",
        "airforce": "US Air Force / Space Force",
    }
    return _interactive_select("Available Sources:", list(ALL_SOURCES), labels, "sources")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
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
    args = parser.parse_args()

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

            #if use_gui:
            #    _tracker.discovery_step(step_label, len(files))

            time.sleep(args.delay)

    # ── List mode ──
    if args.list_only:
        list_files(all_files)
        _close_browser()
        return

    # ── Download ──
    total_files = sum(
        len(f) for yr in all_files.values() for f in yr.values()
    )
    print(f"\nReady to download {total_files} file(s) to: {args.output.resolve()}\n")

    if args.no_gui:
        _tracker = ProgressTracker(total_files)
        _tracker.print_overall()
        print()  # newline after initial overall bar
    else:
        _tracker = GuiProgressTracker(total_files)

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
            dest_dir = args.output / f"FY{year}" / safe_label
            print(f"\n{'='*70}")
            method = "browser" if use_browser else "direct"
            print(f"  FY{year} / {source_label} "
                  f"({len(files)} files, {method}) -> {dest_dir}")
            print(f"{'='*70}")
            _tracker.set_source(year, source_label)

            # Pre-filter: skip files that already exist locally (non-empty)
            # to avoid per-file HEAD requests when not overwriting.
            to_download = []
            if not args.overwrite:
                for file_info in files:
                    dest = dest_dir / file_info["filename"]
                    if dest.exists() and dest.stat().st_size > 0:
                        size = dest.stat().st_size
                        if _tracker:
                            _tracker.file_done(dest.name, size, "skip")
                        else:
                            print(f"    [SKIP] Already exists: {dest.name}")
                    else:
                        to_download.append(file_info)
            else:
                to_download = files

            for file_info in to_download:
                dest = dest_dir / file_info["filename"]
                ok = download_file(
                    session, file_info["url"], dest,
                    args.overwrite, use_browser=use_browser,
                )
                if ok and args.extract_zips and dest.suffix.lower() == ".zip":
                    _extract_zip(dest, dest_dir)
                time.sleep(args.delay)

    # ── Cleanup ──
    _close_browser()

    # ── Summary ──
    elapsed = _tracker._elapsed()
    total_dl = _tracker._format_bytes(_tracker.total_bytes)
    print(f"\n\n{'='*70}")
    print(f"  Download Complete")
    print(f"{'='*70}")
    print(f"  Downloaded: {_tracker.completed}")
    print(f"  Skipped:    {_tracker.skipped}")
    print(f"  Failed:     {_tracker.failed}")
    print(f"  Total size: {total_dl}")
    print(f"  Elapsed:    {elapsed}")
    print(f"  Location:   {args.output.resolve()}")

    if isinstance(_tracker, GuiProgressTracker):
        # Append final log line so it appears in the log widget before we grab it
        _tracker._log_lines.append(
            f"\n--- Complete: {_tracker.completed} downloaded, "
            f"{_tracker.skipped} skipped, {_tracker.failed} failed "
            f"({total_dl}, {elapsed}) ---")
        # Give the GUI poll loop one cycle to flush the log lines
        time.sleep(0.3)
        summary = (f"Downloaded: {_tracker.completed}   Skipped: {_tracker.skipped}   "
                   f"Failed: {_tracker.failed}\n"
                   f"Total size: {total_dl}   Elapsed: {elapsed}")
        _tracker.show_completion_dialog(summary)
    _tracker = None


if __name__ == "__main__":
    main()
