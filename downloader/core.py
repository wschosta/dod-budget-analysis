"""
Core download orchestration for the DoD Budget Downloader.

Contains the main download pipeline including download_all(), download_file(),
the ProgressTracker, DomainRateLimiter, session management, and the CLI
entry point (main).
"""

import argparse
import hashlib
import json
import shutil
import sys
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

# Shared utilities
from utils import format_bytes, elapsed

# Intra-package imports
from downloader.manifest import (
    _compute_sha256,
    _manifest,
    load_manifest_ok_urls,
    update_manifest_entry,
    write_manifest,
)
from downloader.sources import (
    ALL_SOURCES,
    BROWSER_REQUIRED_SOURCES,
    HEADERS,
    SERVICE_PAGE_TEMPLATES,
    SOURCE_DISCOVERERS,
    _browser_download_file,
    _close_browser,
    _is_browser_source,
    _refresh_cache,
    discover_comptroller_files,
    discover_fiscal_years,
)
from downloader.gui import GuiProgressTracker


# ---- Configuration ----

DEFAULT_OUTPUT_DIR = Path("DoD_Budget_Documents")


# ---- Progress Tracker ----

# format_bytes and elapsed are now imported from utils.common
# This consolidates utilities across the codebase for easier maintenance
# and ensures consistent behavior across all tools.


class ProgressTracker:
    """Tracks overall download session progress and renders status bars.

    Thread-safe: all counter mutations and print calls are protected by an
    RLock so concurrent download workers can update progress safely.
    Source/year context uses thread-local storage so each worker thread
    records the correct metadata for failure entries.
    """

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
        # Thread-safety primitives
        self._lock = threading.RLock()
        self._tls = threading.local()

    @property
    def processed(self) -> int:
        """Total files handled so far (completed + skipped + failed)."""
        return self.completed + self.skipped + self.failed

    def _bar(self, fraction: float, width: int = 30) -> str:
        """Render an ASCII progress bar of the given width for the given fraction."""
        filled = int(width * fraction)
        return f"[{'#' * filled}{'-' * (width - filled)}]"

    def set_source(self, year: str, source: str):
        """Update the current fiscal year and source label.

        Uses thread-local storage so concurrent workers each track their own
        context without overwriting each other.
        """
        self._tls.current_year = year
        self._tls.current_source = source
        # Also set instance attrs (last-writer-wins, used for display only)
        self.current_year = year
        self.current_source = source

    def print_overall(self):
        """Print the overall progress line."""
        with self._lock:
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

        with self._lock:
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
        with self._lock:
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
        Reads source/year from thread-local storage for correct concurrent context.
        """
        source = getattr(self._tls, "current_source", self.current_source)
        year = getattr(self._tls, "current_year", self.current_year)
        self._failed_files.append({
            "url": url,
            "dest": dest,
            "filename": filename,
            "error": str(error),
            "source": source,
            "year": year,
            "use_browser": use_browser,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.file_done(filename, 0, "fail")


# ---- Domain Rate Limiter ----

class DomainRateLimiter:
    """Enforces per-domain minimum delay between requests (Option B).

    Each domain gets its own lock so threads downloading from *different*
    domains proceed in parallel, while requests to the *same* domain are
    serialised with the configured delay.
    """

    def __init__(self, delay: float):
        self._delay = delay
        self._meta_lock = threading.Lock()
        self._domain_locks: dict[str, threading.Lock] = {}
        self._last_request: dict[str, float] = {}

    def _get_domain_lock(self, domain: str) -> threading.Lock:
        with self._meta_lock:
            if domain not in self._domain_locks:
                self._domain_locks[domain] = threading.Lock()
            return self._domain_locks[domain]

    def wait(self, url: str) -> None:
        """Block until at least ``delay`` seconds have passed since the last
        request to the same domain, then mark the current time."""
        domain = urlparse(url).netloc
        lock = self._get_domain_lock(domain)
        with lock:
            now = time.time()
            last = self._last_request.get(domain, 0.0)
            wait_time = self._delay - (now - last)
            if wait_time > 0:
                time.sleep(wait_time)
            self._last_request[domain] = time.time()


# ---- Global state ----

# Global state management: tracker, session, and browser context
# Current approach: module-level globals for simplicity and performance
# Advantages: Minimal overhead for single-threaded downloads, easy reuse across functions
#
# Global tracker, set during main()
_tracker: ProgressTracker | GuiProgressTracker | None = None

# Optimization: Global session reuse for connection pooling
_global_session = None


# ---- Session ----

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


# ---- Download helpers ----

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
        return True  # Unknown extension -- accept as long as non-empty

    try:
        with open(dest_path, "rb") as fh:
            header = fh.read(len(expected_magic))
        return header == expected_magic
    except OSError:
        return False


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
            print(f"\r    [HASH MISMATCH] {dest_path.name} -- will redownload")
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
        # Can't determine remote size -- trust the local file
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


# WAF/bot detection helper
_WAF_STATUS_CODES = {403, 429, 503}
_WAF_BODY_SIGNALS = [
    b"access denied",
    b"cloudflare",
    b"captcha",
    b"bot protection",
    b"ddos-guard",
    b"please enable javascript",
    b"ray id",
]


def _detect_waf_block(response: "requests.Response") -> bool:
    """Return True if the HTTP response looks like a WAF or bot-protection block.

    Checks for:
    - HTTP status codes commonly used by WAFs (403, 429, 503)
    - Known WAF provider signatures in the response body
    - ``cf-ray`` / ``x-ddos-guard`` response headers (Cloudflare / DDos-Guard)

    When True is returned, the caller should log a clear warning and avoid
    treating the response as a successful file download.
    """
    if response.status_code in _WAF_STATUS_CODES:
        body_preview = response.content[:2048].lower()
        for signal in _WAF_BODY_SIGNALS:
            if signal in body_preview:
                return True
        # Cloudflare and DDos-Guard inject custom headers
        if "cf-ray" in response.headers or "x-ddos-guard" in response.headers:
            return True
    return False


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

            # WAF / bot-protection detection (TODO 1.A3-c)
            if _detect_waf_block(resp):
                print(f"\r    [WAF] {fname}: WAF/bot-protection block detected "
                      f"(HTTP {resp.status_code}) -- skipping retry          ")
                update_manifest_entry(url, "waf_block", 0, None)
                return False

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
            # SHA-256 computed inline while streaming (1.A3-b)
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


# ---- Display ----

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


# ---- Interactive ----

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


# ---- Programmatic download entry point (TODO 1.A4-a) ----


def download_all(
    all_files: dict,
    output_dir: Path,
    browser_labels: set,
    *,
    overwrite: bool = False,
    delay: float = 0.1,
    extract_zips: bool = False,
    use_gui: bool = False,
    manifest_path: Path | None = None,
    workers: int = 4,
) -> dict:
    """Download all discovered files and return a summary dict.

    This is the programmatic interface decoupled from argparse/sys.argv, so it
    can be called from cron jobs, CI pipelines, or the data-refresh script
    without depending on the interactive/GUI layer.

    Uses concurrent downloads (Option A) with per-domain rate limiting
    (Option B) for significant speed improvements over sequential downloading.
    HTTP downloads run on ``workers`` threads in parallel; browser-based
    downloads (Playwright, not thread-safe) run on a single dedicated thread
    that overlaps with the HTTP pool.

    Args:
        all_files:      Nested dict {year: {source_label: [file_info, ...]}}
                        as returned by the discover_* functions.
        output_dir:     Root directory to write downloaded files into.
        browser_labels: Set of source labels that require Playwright.
        overwrite:      Re-download files that already exist locally.
        delay:          Per-domain minimum seconds between requests (rate-limit
                        courtesy).  Default 0.1 (Option C).
        extract_zips:   Automatically extract .zip archives after downloading.
        use_gui:        Show a Tkinter GUI progress window (requires display).
        manifest_path:  Where to write/update the download manifest JSON.
                        Defaults to output_dir/manifest.json.
        workers:        Number of concurrent HTTP download threads (default 4).
                        Browser downloads always use a single dedicated thread.

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
    print(f"\nReady to download {total_files} file(s) to: {output_dir.resolve()}")
    print(f"  Workers: {workers} HTTP + 1 browser  |  Per-domain delay: {delay}s\n")

    if use_gui:
        _tracker = GuiProgressTracker(total_files)
    else:
        _tracker = ProgressTracker(total_files)
        _tracker.print_overall()
        print()

    # -- Phase 1: Flatten files into a task list, pre-filtering skips --
    http_tasks: list[dict] = []
    browser_tasks: list[dict] = []

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
            method = "browser" if use_browser else "direct"
            print(f"  FY{year} / {source_label} "
                  f"({len(files)} files, {method}) -> {dest_dir}")

            # Pre-filter: skip files that already exist locally (non-empty)
            _tracker.set_source(year, source_label)
            for file_info in files:
                dest = dest_dir / file_info["filename"]
                if not overwrite and dest.exists() and dest.stat().st_size > 0:
                    size = dest.stat().st_size
                    _tracker.file_done(dest.name, size, "skip")
                    update_manifest_entry(
                        file_info["url"], "skip", size,
                        (_manifest.get(file_info["url"]) or {}).get("sha256"),
                    )
                    continue

                task = {
                    "file_info": file_info,
                    "dest": dest,
                    "dest_dir": dest_dir,
                    "use_browser": use_browser,
                    "source_label": source_label,
                    "year": year,
                }
                if use_browser:
                    browser_tasks.append(task)
                else:
                    http_tasks.append(task)

    pending = len(http_tasks) + len(browser_tasks)
    if pending:
        print(f"\n  Queued: {len(http_tasks)} HTTP + {len(browser_tasks)} browser "
              f"({pending} total, {total_files - pending} skipped)")

    # -- Phase 2: Concurrent download with per-domain rate limiting --
    rate_limiter = DomainRateLimiter(delay)

    def _download_worker(task: dict) -> bool:
        """Download a single file (called from a thread-pool worker)."""
        _tracker.set_source(task["year"], task["source_label"])
        rate_limiter.wait(task["file_info"]["url"])
        ok = download_file(
            session,
            task["file_info"]["url"],
            task["dest"],
            overwrite,
            use_browser=task["use_browser"],
        )
        if ok and extract_zips and task["dest"].suffix.lower() == ".zip":
            _extract_zip(task["dest"], task["dest_dir"])
        return ok

    futures: list = []

    # HTTP pool: N worker threads
    http_pool = None
    if http_tasks:
        n_http = min(workers, len(http_tasks))
        http_pool = ThreadPoolExecutor(max_workers=n_http,
                                       thread_name_prefix="http-dl")
        for task in http_tasks:
            futures.append(http_pool.submit(_download_worker, task))

    # Browser pool: 1 dedicated thread (Playwright is not thread-safe)
    browser_pool = None
    if browser_tasks:
        browser_pool = ThreadPoolExecutor(max_workers=1,
                                          thread_name_prefix="browser-dl")
        for task in browser_tasks:
            futures.append(browser_pool.submit(_download_worker, task))

    # Wait for all futures to complete
    for future in as_completed(futures):
        try:
            future.result()
        except Exception:
            pass  # Individual failures already recorded by download_file

    if http_pool:
        http_pool.shutdown(wait=True)
    if browser_pool:
        browser_pool.shutdown(wait=True)

    # -- Phase 3: Summary and cleanup --
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


# ---- Main ----

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
        "--delay", type=float, default=0.1,
        help="Per-domain seconds between requests (default: 0.1)",
    )
    parser.add_argument(
        "--workers", type=int, default=4,
        help="Number of concurrent HTTP download threads (default: 4). "
             "Browser downloads always use 1 dedicated thread.",
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
    parser.add_argument(
        "--since", metavar="YYYY-MM-DD", default=None,
        help=(
            "Skip files already in the manifest with status=ok and "
            "downloaded on or after YYYY-MM-DD. Enables fast incremental "
            "updates without re-downloading unchanged files. (1.A4-b)"
        ),
    )
    args = parser.parse_args()

    # Optimization: Set global flag for cache refresh
    import downloader.sources as _sources_mod
    _sources_mod._refresh_cache = args.refresh_cache

    # -- Retry-failures early path (TODO 1.A6-b) --
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
        global _tracker
        tracker = (ProgressTracker if args.no_gui else GuiProgressTracker)(len(failed_entries))
        _tracker = tracker

        still_failed: list[dict] = []
        for entry in failed_entries:
            url = entry["url"]
            dest = Path(entry["dest"])
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
            print(f"\n  {len(still_failed)} file(s) still failed -- "
                  f"log updated: {failures_path}")
        else:
            failures_path.unlink(missing_ok=True)
            print("\n  All retries succeeded.")

        _tracker = None
        _close_browser()
        _close_session()
        sys.exit(1 if still_failed else 0)

    session = get_session()

    # -- Discover fiscal years --
    available_years = discover_fiscal_years(session)
    if not available_years:
        print("ERROR: Could not find any fiscal year links on the website.")
        sys.exit(1)

    print(f"Found {len(available_years)} fiscal years: "
          f"{', '.join(list(available_years.keys())[:5])}...")

    # -- Select years --
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

    # -- Select sources --
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

    # -- File type filter --
    type_filter = None
    if args.types:
        type_filter = {f".{t.lower().strip('.')}" for t in args.types}
        print(f"File type filter: {', '.join(type_filter)}")

    # -- Discover files --
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

    # -- List mode --
    if args.list_only:
        list_files(all_files)
        _close_browser()
        return

    # -- --since incremental filter (1.A4-b) --
    if args.since:
        manifest_path = args.output / "manifest.json"
        ok_urls = load_manifest_ok_urls(manifest_path, args.since)
        if ok_urls:
            skipped_count = 0
            for year in all_files:
                for label in all_files[year]:
                    before = len(all_files[year][label])
                    all_files[year][label] = [
                        f for f in all_files[year][label]
                        if f["url"] not in ok_urls
                    ]
                    skipped_count += before - len(all_files[year][label])
            if skipped_count:
                print(f"\n  [--since {args.since}] Skipping {skipped_count} "
                      f"already-current file(s) from manifest.")

    # -- Download via download_all() --
    summary = download_all(
        all_files,
        args.output,
        browser_labels,
        overwrite=args.overwrite,
        delay=args.delay,
        extract_zips=args.extract_zips,
        use_gui=not args.no_gui,
        manifest_path=args.output / "manifest.json",
        workers=args.workers,
    )

    # -- Terminal summary (GUI summary is shown inside download_all) --
    if args.no_gui:
        total_dl = format_bytes(summary["total_bytes"])
        print(f"\n\n{'='*70}")
        print("  Download Complete")
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
