"""
DoD Comptroller Budget Document Downloader

Downloads budget documents (PDFs, Excel files, ZIPs) from the DoD Comptroller
website and service-specific budget pages for selected fiscal years.

Sources:
  - comptroller : Main DoD summary budget documents (comptroller.war.gov)
  - defense-wide: Defense Wide budget justification books (comptroller.war.gov)
  - army        : US Army budget materials (asafm.army.mil)
  - navy        : US Navy/Marine Corps budget materials (secnav.navy.mil)
  - airforce    : US Air Force & Space Force budget materials (saffm.hq.af.mil)

Requirements:
  pip install requests beautifulsoup4 playwright
  python -m playwright install chromium

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
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

# ── Configuration ──────────────────────────────────────────────────────────────

BASE_URL = "https://comptroller.war.gov"
BUDGET_MATERIALS_URL = f"{BASE_URL}/Budget-Materials/"
DOWNLOADABLE_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".zip", ".csv"}
IGNORED_HOSTS = {"dam.defense.gov"}
DEFAULT_OUTPUT_DIR = Path("DoD_Budget_Documents")

ALL_SOURCES = ["comptroller", "defense-wide", "army", "navy", "airforce"]

# Sources that require a real browser due to WAF/bot protection
BROWSER_REQUIRED_SOURCES = {"army", "navy", "airforce"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
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
        "url": "https://www.secnav.navy.mil/fmc/fmb/Pages/archive.aspx",
        "label": "US Navy",
    },
    "airforce": {
        "url": "https://www.saffm.hq.af.mil/FM-Resources/Budget/Air-Force-Presidents-Budget-FY{fy2}/",
        "label": "US Air Force",
    },
}


# ── Progress Tracker ──────────────────────────────────────────────────────────

class ProgressTracker:
    """Tracks overall download session progress and renders status bars."""

    def __init__(self, total_files: int):
        self.total_files = total_files
        self.completed = 0
        self.skipped = 0
        self.failed = 0
        self.session_bytes = 0   # bytes downloaded this session only
        self.existing_bytes = 0  # bytes of files already on disk (skipped)
        self.start_time = time.time()
        self.current_source = ""
        self.current_year = ""
        self.term_width = shutil.get_terminal_size((80, 24)).columns
        self._last_progress_time = 0.0

    @property
    def processed(self) -> int:
        return self.completed + self.skipped + self.failed

    @property
    def total_bytes(self) -> int:
        """Total database size = downloaded this session + existing files."""
        return self.session_bytes + self.existing_bytes

    def _elapsed(self) -> str:
        secs = int(time.time() - self.start_time)
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}h {m:02d}m {s:02d}s"
        return f"{m}m {s:02d}s"

    def _format_bytes(self, b: int) -> str:
        if b < 1024 * 1024:
            return f"{b / 1024:.0f} KB"
        if b < 1024 * 1024 * 1024:
            return f"{b / (1024 * 1024):.1f} MB"
        return f"{b / (1024 * 1024 * 1024):.2f} GB"

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
        dl = self._format_bytes(self.session_bytes)
        db = self._format_bytes(self.total_bytes)
        elapsed = self._elapsed()
        remaining = self.total_files - self.processed
        line = (
            f"\r  Overall: {bar} {pct:5.1f}%  "
            f"{self.processed}/{self.total_files} files  "
            f"{dl} downloaded  "
            f"({db} total)  "
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
            print(f"\r    Downloading {filename}... {self._format_bytes(downloaded)}",
                  end="", flush=True)
            return

        frac = downloaded / total
        pct = frac * 100
        bar = self._bar(frac, 20)
        elapsed = time.time() - file_start
        speed = downloaded / elapsed if elapsed > 0 else 0
        speed_str = f"{self._format_bytes(int(speed))}/s"
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
            f"{self._format_bytes(downloaded)}/{self._format_bytes(total)}  "
            f"{speed_str}  {eta}"
        )
        print(f"{line:<{self.term_width}}", end="", flush=True)

    def file_done(self, filename: str, size: int, status: str):
        """Record a completed file and print result."""
        tag = {"ok": "OK", "skip": "SKIP", "redownload": "OK",
               "fail": "FAIL"}.get(status, status.upper())

        if status == "ok" or status == "redownload":
            self.completed += 1
            self.session_bytes += size
        elif status == "skip":
            self.skipped += 1
            self.existing_bytes += size
        elif status == "fail":
            self.failed += 1

        size_str = self._format_bytes(size) if size > 0 else ""
        line = f"    [{tag}] {filename} ({size_str})" if size_str else f"    [{tag}] {filename}"
        print(f"\r{line:<{self.term_width}}")
        self.print_overall()


# ── GUI Progress Tracker ─────────────────────────────────────────────────────

class GuiProgressTracker:
    """Tkinter GUI window that displays download progress.

    Supports two phases:
      1. Discovery — scanning data sources (own progress bar)
      2. Download  — downloading files (main progress bar + file bar)
    """

    def __init__(self, total_files: int = 0):
        self.total_files = total_files
        self.completed = 0
        self.skipped = 0
        self.failed = 0
        self.session_bytes = 0   # bytes downloaded this session only
        self.existing_bytes = 0  # bytes of files already on disk (skipped)
        self.start_time = time.time()
        self.current_source = ""
        self.current_year = ""

        # Discovery phase state
        self._discovery_total = 0
        self._discovery_done = 0
        self._discovery_label = ""
        self._discovery_results: list[str] = []  # log lines during discovery
        self._discovery_finished = False

        # Per-file state (read by GUI thread)
        self._file_name = ""
        self._file_downloaded = 0
        self._file_total = 0
        self._file_start = 0.0
        self._log_lines: list[str] = []

        self._closed = False
        self._ready = threading.Event()

        self._thread = threading.Thread(target=self._run_gui, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    @property
    def processed(self) -> int:
        return self.completed + self.skipped + self.failed

    @property
    def total_bytes(self) -> int:
        """Total database size = downloaded this session + existing files."""
        return self.session_bytes + self.existing_bytes

    def _format_bytes(self, b: int) -> str:
        if b < 1024 * 1024:
            return f"{b / 1024:.0f} KB"
        if b < 1024 * 1024 * 1024:
            return f"{b / (1024 * 1024):.1f} MB"
        return f"{b / (1024 * 1024 * 1024):.2f} GB"

    def _elapsed(self) -> str:
        secs = int(time.time() - self.start_time)
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}h {m:02d}m {s:02d}s"
        return f"{m}m {s:02d}s"

    def _run_gui(self):
        import tkinter as tk
        from tkinter import ttk

        self._root = root = tk.Tk()
        root.title("DoD Budget Downloader")
        root.geometry("620x460")
        root.resizable(True, True)
        root.attributes("-topmost", True)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        style = ttk.Style()
        style.configure("Overall.Horizontal.TProgressbar",
                         troughcolor="#e0e0e0", background="#2196F3")
        style.configure("File.Horizontal.TProgressbar",
                         troughcolor="#e0e0e0", background="#4CAF50")
        style.configure("Discovery.Horizontal.TProgressbar",
                         troughcolor="#e0e0e0", background="#FF9800")

        pad = {"padx": 10, "pady": 4}

        # ══════════════════════════════════════════════════════════════════
        #  DISCOVERY PHASE widgets
        # ══════════════════════════════════════════════════════════════════
        self._disc_frame = disc_frame = ttk.LabelFrame(
            root, text="  Scanning Data Sources  ", padding=8)
        disc_frame.pack(fill="x", **pad)

        self._disc_lbl = tk.StringVar(value="Initializing...")
        ttk.Label(disc_frame, textvariable=self._disc_lbl,
                  font=("Segoe UI", 9)).pack(anchor="w")

        self._disc_bar = ttk.Progressbar(
            disc_frame, length=560, mode="determinate",
            style="Discovery.Horizontal.TProgressbar")
        self._disc_bar.pack(fill="x", pady=4)

        self._disc_stats = tk.StringVar(value="")
        ttk.Label(disc_frame, textvariable=self._disc_stats,
                  font=("Segoe UI", 9)).pack(anchor="w")

        # Discovery results log
        self._disc_log = tk.Text(disc_frame, height=4, wrap="none",
                                  font=("Consolas", 8), state="disabled",
                                  bg="#f5f5f5")
        self._disc_log.pack(fill="x", pady=(4, 0))

        # ══════════════════════════════════════════════════════════════════
        #  DOWNLOAD PHASE widgets (initially hidden)
        # ══════════════════════════════════════════════════════════════════
        self._dl_frame = dl_frame = ttk.Frame(root)
        # dl_frame is NOT packed yet — shown after discovery finishes

        # ── Source label ──
        self._src_var = tk.StringVar(value="")
        ttk.Label(dl_frame, textvariable=self._src_var,
                  font=("Segoe UI", 11, "bold")).pack(**pad, anchor="w")

        # ── Overall progress ──
        frm_overall = ttk.Frame(dl_frame)
        frm_overall.pack(fill="x", **pad)

        self._overall_lbl = tk.StringVar(value="0.0%  -  0 / 0 files")
        ttk.Label(frm_overall, textvariable=self._overall_lbl,
                  font=("Segoe UI", 9)).pack(anchor="w")
        self._overall_bar = ttk.Progressbar(
            frm_overall, length=580, mode="determinate",
            style="Overall.Horizontal.TProgressbar")
        self._overall_bar.pack(fill="x", pady=2)

        # ── Stats row ──
        self._stats_var = tk.StringVar(value="")
        ttk.Label(dl_frame, textvariable=self._stats_var,
                  font=("Segoe UI", 9)).pack(**pad, anchor="w")

        # ── Current file ──
        sep1 = ttk.Separator(dl_frame, orient="horizontal")
        sep1.pack(fill="x", padx=10, pady=2)

        self._file_lbl = tk.StringVar(value="Waiting...")
        ttk.Label(dl_frame, textvariable=self._file_lbl,
                  font=("Segoe UI", 9)).pack(padx=10, pady=2, anchor="w")
        self._file_bar = ttk.Progressbar(
            dl_frame, length=580, mode="determinate",
            style="File.Horizontal.TProgressbar")
        self._file_bar.pack(fill="x", padx=10, pady=2)

        self._file_stats_var = tk.StringVar(value="")
        ttk.Label(dl_frame, textvariable=self._file_stats_var,
                  font=("Segoe UI", 9)).pack(padx=10, anchor="w")

        # ── Counters ──
        sep2 = ttk.Separator(dl_frame, orient="horizontal")
        sep2.pack(fill="x", padx=10, pady=4)

        frm_counts = ttk.Frame(dl_frame)
        frm_counts.pack(fill="x", padx=10)
        self._count_var = tk.StringVar(
            value="Downloaded: 0    Skipped: 0    Failed: 0")
        ttk.Label(frm_counts, textvariable=self._count_var,
                  font=("Segoe UI", 9, "bold")).pack(anchor="w")

        # ── File log ──
        sep3 = ttk.Separator(dl_frame, orient="horizontal")
        sep3.pack(fill="x", padx=10, pady=4)

        log_frame = ttk.Frame(dl_frame)
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
        """Called every 50ms in the GUI thread to refresh widgets."""
        if self._closed:
            return

        # ── Discovery phase updates ──
        if not self._discovery_finished:
            if self._discovery_total > 0:
                dfrac = self._discovery_done / self._discovery_total
                self._disc_bar["value"] = dfrac * 100
                self._disc_lbl.set(
                    f"{self._discovery_label}  "
                    f"({self._discovery_done} / {self._discovery_total})")
                self._disc_stats.set(
                    f"{dfrac*100:.0f}% complete  |  {self._elapsed()} elapsed")
            else:
                self._disc_lbl.set(self._discovery_label or "Initializing...")

            # Discovery log
            if self._discovery_results:
                results = self._discovery_results.copy()
                self._discovery_results.clear()
                self._disc_log.configure(state="normal")
                for ln in results:
                    self._disc_log.insert("end", ln + "\n")
                self._disc_log.see("end")
                self._disc_log.configure(state="disabled")

            self._root.after(50, self._poll)
            return

        # ── Download phase updates ──

        # Transition: show download frame if not yet visible
        if not self._dl_frame.winfo_ismapped():
            self._dl_frame.pack(fill="both", expand=True)

        # Overall
        frac = self.processed / self.total_files if self.total_files else 0
        self._overall_bar["value"] = frac * 100
        self._overall_lbl.set(
            f"{frac*100:.1f}%  -  {self.processed} / {self.total_files} files")
        remaining = self.total_files - self.processed
        elapsed_secs = time.time() - self.start_time
        if self.processed > 0 and remaining > 0 and elapsed_secs > 2:
            avg_per_file = elapsed_secs / self.processed
            eta_secs = int(avg_per_file * remaining)
            em, es = divmod(eta_secs, 60)
            eh, em = divmod(em, 60)
            if eh:
                eta_str = f"~{eh}h {em:02d}m {es:02d}s left"
            else:
                eta_str = f"~{em}m {es:02d}s left"
        elif remaining == 0:
            eta_str = "done"
        else:
            eta_str = "estimating..."
        self._stats_var.set(
            f"{self._format_bytes(self.session_bytes)} downloaded  |  "
            f"{self._format_bytes(self.total_bytes)} total  |  "
            f"{self._elapsed()} elapsed  |  {eta_str}")
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
                speed_str = f"{self._format_bytes(int(speed))}/s"
                self._file_lbl.set(fname)
                self._file_stats_var.set(
                    f"{self._format_bytes(dl)} / {self._format_bytes(total)}  "
                    f"  {speed_str}")
            else:
                self._file_bar["value"] = 0
                self._file_lbl.set(f"{fname}  ({self._format_bytes(dl)})")
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

        self._root.after(50, self._poll)

    def _on_close(self):
        self._closed = True
        self._root.destroy()

    # ── Discovery phase API ──

    def set_discovery_total(self, total: int):
        """Set the total number of discovery steps (year × source combos)."""
        self._discovery_total = total

    def discovery_step(self, label: str, file_count: int | None = None):
        """Record completion of one discovery step."""
        self._discovery_done += 1
        self._discovery_label = label
        result = f"  {label}"
        if file_count is not None:
            result += f" — {file_count} file(s) found"
        self._discovery_results.append(result)

    def finish_discovery(self, total_files: int):
        """End the discovery phase and transition to download phase."""
        self.total_files = total_files
        self._discovery_done = self._discovery_total  # ensure bar shows 100%
        self._discovery_label = f"Scan complete — {total_files} file(s) found"
        self.start_time = time.time()  # reset elapsed for download phase
        self._discovery_finished = True

    # ── Download phase API ──

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
            self.session_bytes += size
        elif status == "skip":
            self.skipped += 1
            self.existing_bytes += size
        elif status == "fail":
            self.failed += 1

        size_str = f" ({self._format_bytes(size)})" if size > 0 else ""
        self._log_lines.append(f"[{tag}] {filename}{size_str}")

        # Reset file bar
        self._file_name = ""
        self._file_downloaded = 0
        self._file_total = 0

    def close(self):
        """Close the GUI window."""
        if not self._closed and hasattr(self, '_root'):
            self._closed = True
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass


# Global tracker, set during main()
_tracker: ProgressTracker | GuiProgressTracker | None = None
_failure_log: list[dict] = []  # {"filename": ..., "url": ..., "source": ..., "year": ...}


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
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1920, "height": 1080},
        accept_downloads=True,
    )
    return _pw_context


def _close_browser():
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
        raw = page.evaluate(f"""() => {{
            const tf = {js_filter};
            const allLinks = Array.from(document.querySelectorAll('a[href]'));
            const files = [];
            const seen = new Set();
            const ignoredHosts = new Set(['dam.defense.gov']);
            for (const a of allLinks) {{
                const href = a.href;
                let path, host;
                try {{ const u = new URL(href); path = u.pathname.toLowerCase(); host = u.hostname.toLowerCase(); }} catch {{ continue; }}
                if (ignoredHosts.has(host)) continue;
                const exts = ['.pdf', '.xlsx', '.xls', '.zip', '.csv'];
                if (!exts.some(e => path.endsWith(e))) continue;
                if (tf && !href.toLowerCase().includes(tf.toLowerCase())) continue;
                if (seen.has(path)) continue;
                seen.add(path);
                const text = a.textContent.trim();
                const filename = decodeURIComponent(path.split('/').pop());
                const ext = '.' + filename.split('.').pop().toLowerCase();
                files.push({{ name: text || filename, url: href, filename: filename, extension: ext }});
            }}
            return files;
        }}""")

        return [_clean_file_entry(f) for f in raw]

    finally:
        page.close()


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
        page = ctx.new_page()
        page.add_init_script(
            'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        )
        # First navigate to the domain so cookies/session are established
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        page.goto(origin, timeout=15000, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

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
        page = ctx.new_page()
        page.add_init_script(
            'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        )
        # Navigate to file's origin first
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        page.goto(origin, timeout=15000, wait_until="domcontentloaded")
        page.wait_for_timeout(500)

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


# ── Navy (browser required — SharePoint site) ────────────────────────────────

# Cache: load the archive page once, reuse for all years
_navy_archive_cache: list[dict] | None = None


def discover_navy_files(_session: requests.Session, year: str) -> list[dict]:
    global _navy_archive_cache
    url = SERVICE_PAGE_TEMPLATES["navy"]["url"]
    fy2 = year[-2:]
    print(f"  [Navy] Scanning FY{year} (browser, archive page)...")

    # Load archive page once and cache all links
    if _navy_archive_cache is None:
        print(f"    Loading Navy archive (first scan, may take a moment)...")
        _navy_archive_cache = _browser_extract_links(url)

    # Filter cached links for this fiscal year
    # Navy URLs typically contain patterns like /26pres/ or /FY26/ or /2026/
    matched = [f for f in _navy_archive_cache
               if f"{fy2}pres" in f["url"].lower()
               or f"/{fy2}/" in f["url"].lower()
               or f"/fy{fy2}" in f["url"].lower()
               or f"/{year}/" in f["url"]]
    return matched


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
        local_size = dest_path.stat().st_size
        if local_size > 1024:
            # File exists and is >1KB — skip immediately without HEAD request
            if _tracker:
                _tracker.file_done(fname, local_size, "skip")
            else:
                print(f"    [SKIP] Already exists: {fname}")
            return True
        # File is suspiciously small — verify via HEAD
        status = _check_existing_file(session, url, dest_path, use_browser)
        if status == "skip":
            if _tracker:
                _tracker.file_done(fname, local_size, "skip")
            else:
                print(f"    [SKIP] Already exists: {fname}")
            return True
        if status == "redownload":
            local_mb = local_size / (1024 * 1024)
            print(f"\r    [REDOWNLOAD] Size mismatch for {fname} "
                  f"(local {local_mb:.1f} MB)")

    if use_browser:
        ok = _browser_download_file(url, dest_path, overwrite=True)
        if _tracker:
            size = dest_path.stat().st_size if dest_path.exists() else 0
            _tracker.file_done(fname, size, "ok" if ok else "fail")
        if not ok:
            _failure_log.append({
                "filename": fname, "url": url,
                "source": _tracker.current_source if _tracker else "",
                "year": _tracker.current_year if _tracker else "",
                "error": "All browser download strategies failed",
            })
        return ok

    file_start = time.time()
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
        if _tracker:
            _tracker.file_done(fname, 0, "fail")
        else:
            print(f"\r    [FAIL] {fname}: {e}          ")
        _failure_log.append({
            "filename": fname, "url": url,
            "source": _tracker.current_source if _tracker else "",
            "year": _tracker.current_year if _tracker else "",
            "error": str(e),
        })
        if dest_path.exists():
            dest_path.unlink()
        return False


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

def interactive_select_years(available: dict[str, str]) -> list[str]:
    years = list(available.keys())
    print("\nAvailable Fiscal Years:")
    print("-" * 40)
    for i, year in enumerate(years, 1):
        print(f"  {i:2d}. FY{year}")
    print(f"  {len(years)+1:2d}. All fiscal years")
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

        if len(years) + 1 in choices:
            return years

        selected = []
        valid = True
        for c in choices:
            if 1 <= c <= len(years):
                selected.append(years[c - 1])
            else:
                print(f"Invalid choice: {c}")
                valid = False
                break
        if valid and selected:
            return selected


def interactive_select_sources() -> list[str]:
    labels = {
        "comptroller": "Comptroller (main DoD summary documents)",
        "defense-wide": "Defense Wide (budget justification books)",
        "army": "US Army",
        "navy": "US Navy / Marine Corps",
        "airforce": "US Air Force / Space Force",
    }
    print("\nAvailable Sources:")
    print("-" * 50)
    for i, src in enumerate(ALL_SOURCES, 1):
        print(f"  {i}. {labels[src]}")
    print(f"  {len(ALL_SOURCES)+1}. All sources")
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
            print("Invalid input.")
            continue

        if len(ALL_SOURCES) + 1 in choices:
            return list(ALL_SOURCES)

        selected = []
        valid = True
        for c in choices:
            if 1 <= c <= len(ALL_SOURCES):
                selected.append(ALL_SOURCES[c - 1])
            else:
                print(f"Invalid choice: {c}")
                valid = False
                break
        if valid and selected:
            return selected


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

    # ── Set up GUI before discovery ──
    global _tracker
    use_gui = not args.no_gui and not args.list_only

    if use_gui:
        _tracker = GuiProgressTracker()  # start with 0 total, discovery phase
        discovery_steps = len(selected_years) * len(selected_sources)
        _tracker.set_discovery_total(discovery_steps)

    # ── Discover files ──
    all_files: dict[str, dict[str, list[dict]]] = {}
    # Track which source labels need browser downloads
    browser_labels: set[str] = set()

    for year in selected_years:
        all_files[year] = {}

        for source in selected_sources:
            label = (SERVICE_PAGE_TEMPLATES[source]["label"]
                     if source != "comptroller" else "Comptroller")
            step_label = f"FY{year} / {label}"

            if source == "comptroller":
                url = available_years[year]
                files = discover_comptroller_files(session, year, url)
            else:
                discoverer = SOURCE_DISCOVERERS[source]
                files = discoverer(session, year)

            if type_filter:
                files = [f for f in files if f["extension"] in type_filter]

            all_files[year][label] = files

            if _is_browser_source(source):
                browser_labels.add(label)

            if use_gui:
                _tracker.discovery_step(step_label, len(files))

            time.sleep(0.5)

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

    if use_gui:
        _tracker.finish_discovery(total_files)
    else:
        _tracker = ProgressTracker(total_files)
        _tracker.print_overall()
        print()  # newline after initial overall bar

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

            for file_info in files:
                dest = dest_dir / file_info["filename"]
                download_file(
                    session, file_info["url"], dest,
                    args.overwrite, use_browser=use_browser,
                )
                time.sleep(0.3)

    # ── Cleanup ──
    _close_browser()

    # ── Summary ──
    elapsed = _tracker._elapsed()
    session_dl = _tracker._format_bytes(_tracker.session_bytes)
    total_db = _tracker._format_bytes(_tracker.total_bytes)
    print(f"\n\n{'='*70}")
    print(f"  Download Complete")
    print(f"{'='*70}")
    print(f"  Downloaded: {_tracker.completed}  ({session_dl})")
    print(f"  Skipped:    {_tracker.skipped}")
    print(f"  Failed:     {_tracker.failed}")
    print(f"  Database:   {total_db}")
    print(f"  Elapsed:    {elapsed}")
    print(f"  Location:   {args.output.resolve()}")

    if _failure_log:
        from datetime import datetime
        log_path = args.output / f"failures_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"DoD Budget Downloader - Failure Log\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total failures: {len(_failure_log)}\n")
            f.write(f"{'='*80}\n\n")
            for i, entry in enumerate(_failure_log, 1):
                f.write(f"{i}. {entry['filename']}\n")
                f.write(f"   Source: FY{entry['year']} / {entry['source']}\n")
                f.write(f"   URL:    {entry['url']}\n")
                f.write(f"   Error:  {entry['error']}\n\n")
        print(f"  Failures: {log_path.resolve()}")

    if isinstance(_tracker, GuiProgressTracker):
        # Keep GUI open for a moment so user can see final state
        _tracker._log_lines.append(
            f"\n--- Complete: {_tracker.completed} downloaded ({session_dl}), "
            f"{_tracker.skipped} skipped, {_tracker.failed} failed "
            f"(DB: {total_db}, {elapsed}) ---")
        time.sleep(2)
        _tracker.close()
    _tracker = None


if __name__ == "__main__":
    main()
