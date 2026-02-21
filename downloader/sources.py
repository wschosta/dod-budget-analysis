"""
Source discovery for the DoD Budget Downloader.

Contains service-specific discovery functions that locate downloadable budget
documents on DoD Comptroller, Army, Navy, Air Force, and Defense-Wide websites.
Also manages the Playwright browser context used for WAF-protected sources and
browser-based file downloads.
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime

logger = logging.getLogger(__name__)
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

import requests
from bs4 import BeautifulSoup

# Shared utilities
from utils import sanitize_filename
from utils.patterns import DOWNLOADABLE_EXTENSIONS

# Optimization: Try to use lxml parser (3-5x faster), fall back to html.parser
try:
    import lxml  # noqa: F401
    PARSER = "lxml"
except ImportError:
    PARSER = "html.parser"

# Optimization: Pre-compile extension regex pattern (now from utils.patterns)
DOWNLOADABLE_PATTERN = DOWNLOADABLE_EXTENSIONS

# ---- Configuration ----

BASE_URL = "https://comptroller.war.gov"
BUDGET_MATERIALS_URL = f"{BASE_URL}/Budget-Materials/"
DOWNLOADABLE_EXTENSIONS_SET = {".pdf", ".xlsx", ".xls", ".zip", ".csv"}
IGNORED_HOSTS = {"dam.defense.gov"}

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
        "url": (
            "https://www.saffm.hq.af.mil/FM-Resources/Budget/"
            "Air-Force-Presidents-Budget-FY{fy2}/"
        ),
        "label": "US Air Force",
    },
    "navy-archive": {
        "url": "https://www.secnav.navy.mil/fmc/fmb/Pages/archive.aspx",
        "label": "US Navy Archive",
        # SharePoint REST API endpoint for the document library
        "sp_list_guid": "AE8ECF7F-2D4B-4077-8BE2-159CA7CEBBDF",
        "sp_site_url": "https://www.secnav.navy.mil/fmc/fmb",
    },
}


# ---- Adaptive Timeout Management ----

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


# ---- Playwright browser context (lazy init) ----

_pw_instance = None
_pw_browser = None
_pw_context = None


# Playwright browser lifecycle management
# Current approach: Lazy initialization with manual cleanup via _close_browser()
# Optimization: Webdriver detection script added at context level applies
# to all pages created from this context, reducing per-page overhead.
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
    _headless = os.environ.get("PLAYWRIGHT_HEADLESS", "").lower() in (
        "1", "true", "yes",
    )
    _pw_browser = _pw_instance.chromium.launch(
        headless=_headless,
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
        except Exception as exc:
            logger.debug("Page load timeout for %s: %s", url, exc)
            # Proceed with whatever content loaded so far
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
        raw = page.evaluate("""(args) => {
            const [exts, tf] = args;
            const tf_arg = tf;
            const allLinks = Array.from(document.querySelectorAll('a[href]'));
            const files = [];
            const seen = new Set();
            const ignoredHosts = new Set(['dam.defense.gov']);
            for (const a of allLinks) {
                const href = a.href;
                let path, host;
                try { const u = new URL(href); path = u.pathname.toLowerCase();
                    host = u.hostname.toLowerCase(); } catch { continue; }
                if (ignoredHosts.has(host)) continue;
                if (!exts.some(e => path.endsWith(e))) continue;
                if (tf_arg && !href.toLowerCase().includes(tf_arg.toLowerCase())) continue;
                if (seen.has(path)) continue;
                seen.add(path);
                const text = a.textContent.trim();
                const filename = decodeURIComponent(path.split('/').pop());
                const ext = '.' + filename.split('.').pop().toLowerCase();
                files.push({ name: text || filename, url: href,
                    filename: filename, extension: ext });
            }
            return files;
        }""", [list(DOWNLOADABLE_EXTENSIONS_SET), text_filter])

        return [_clean_file_entry(f) for f in raw]

    finally:
        page.close()


def _browser_extract_sharepoint_files(
    page_url: str,
    site_url: str,
    list_guid: str,
    year: str,
) -> list[dict]:
    """Query a SharePoint document library via REST API to discover files.

    SharePoint grouped list views load file links lazily via AJAX when groups
    are expanded.  Instead of clicking through hundreds of nested groups, this
    function calls the SharePoint REST API from within the authenticated browser
    context to retrieve all files for a fiscal year in one request.

    Args:
        page_url: The archive page URL (used to establish the browser session).
        site_url: The SharePoint site URL (e.g. ``https://…/fmc/fmb``).
        list_guid: The GUID of the SharePoint document library list.
        year: Four-digit fiscal year string.

    Returns:
        List of file dicts compatible with the standard discovery format.
    """
    ctx = _get_browser_context()
    page = ctx.new_page()

    try:
        # Navigate to the archive page first to establish auth cookies
        timeout = _timeout_mgr.get_timeout(page_url, is_download=False)
        start = time.time()
        try:
            page.goto(page_url, timeout=timeout, wait_until="domcontentloaded")
        except Exception:
            pass  # proceed with whatever loaded
        elapsed_ms = int((time.time() - start) * 1000)
        _timeout_mgr.record_time(page_url, elapsed_ms)

        # Use the SharePoint REST API to query files filtered by fiscal year.
        # File_x0020_Type ne null excludes folders from the results.
        # $top=500 handles the largest year groups (max observed ~50 files).
        raw = page.evaluate("""(args) => {
            const [siteUrl, listGuid, fiscalYear] = args;
            const apiUrl = siteUrl +
                "/_api/web/lists(guid'" + listGuid + "')/items" +
                "?$top=500" +
                "&$select=Title,FileRef,File_x0020_Type,Section" +
                "&$filter=Fiscal_x0020_Year eq '" + fiscalYear + "'" +
                " and File_x0020_Type ne null" +
                "&$orderby=Title";

            return fetch(apiUrl, {
                headers: { 'Accept': 'application/json;odata=verbose' },
                credentials: 'same-origin'
            })
            .then(r => r.json())
            .then(data => {
                const items = data.d && data.d.results ? data.d.results : [];
                const exts = new Set(['.pdf', '.xlsx', '.xls', '.zip', '.csv']);
                return items.filter(item => {
                    const ref = (item.FileRef || '').toLowerCase();
                    const ext = '.' + ref.split('.').pop();
                    return exts.has(ext);
                }).map(item => {
                    const ref = item.FileRef || '';
                    const filename = decodeURIComponent(ref.split('/').pop());
                    const ext = '.' + filename.split('.').pop().toLowerCase();
                    const title = item.Title || filename;
                    const section = item.Section || '';
                    const fullUrl = new URL(ref, window.location.origin).href;
                    return {
                        name: section ? (title + ' (' + section + ')') : title,
                        url: fullUrl,
                        filename: filename,
                        extension: ext
                    };
                });
            })
            .catch(() => []);
        }""", [site_url, list_guid, year])

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

    Fully automated -- no user clicks required. Uses three strategies:
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
    except Exception as exc:
        logger.debug("Browser strategy 1 (API fetch) failed for %s: %s", url, exc)
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

    except Exception as exc:
        logger.debug("Browser strategy 2 (anchor inject) failed for %s: %s", url, exc)
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
    except Exception as exc:
        logger.debug("Browser strategy 3 (direct nav) failed for %s: %s", url, exc)
        try:
            page.close()
        except Exception:
            pass

    # All strategies failed
    if dest_path.exists() and dest_path.stat().st_size == 0:
        dest_path.unlink()
    return False


# ---- Helpers ----

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


def _is_browser_source(source: str) -> bool:
    """Check if a source requires browser access to work around WAF protection."""
    return source in BROWSER_REQUIRED_SOURCES


# ---- Discovery cache ----

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


# ---- Comptroller (main page) ----

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


# ---- Defense Wide ----

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


# ---- Army (browser required) ----

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


# ---- Navy (browser required) ----

def discover_navy_files(_session: requests.Session, year: str) -> list[dict]:
    """Discover US Navy/Marine Corps budget files for a given fiscal year using a headless browser.

    FY2022+ pages live at /fmc/Pages/Fiscal-Year-{fy}.aspx.
    FY2017-2021 pages use the older /fmc/fmb/Pages/Fiscal-Year-{fy}.aspx URL.
    If the primary URL returns 0 files, the alternate pattern is tried automatically.

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

    # Fallback: older FYs (pre-2022) use a different URL path
    if not files:
        alt_url = (
            f"https://www.secnav.navy.mil/fmc/fmb/Pages/Fiscal-Year-{year}.aspx"
        )
        print("  [Navy] Primary URL returned 0 files, trying alternate URL...")
        files = _browser_extract_links(alt_url)

    _save_cache(cache_key, files)
    return files


# ---- Navy Archive (browser required) ----

def discover_navy_archive_files(_session: requests.Session, year: str) -> list[dict]:
    """Discover Navy budget files from the SECNAV archive via SharePoint REST API.

    The archive page is a SharePoint grouped list view with fiscal year and
    section groups.  File links are loaded lazily when groups are expanded,
    so standard link extraction returns 0 results.  Instead, this function
    uses the SharePoint REST API (authenticated through the browser session)
    to query all files for a given fiscal year in a single request.

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

    config = SERVICE_PAGE_TEMPLATES["navy-archive"]
    page_url = config["url"]
    site_url = config["sp_site_url"]
    list_guid = config["sp_list_guid"]

    print(f"  [Navy Archive] Scanning FY{year} (SharePoint API)...")
    files = _browser_extract_sharepoint_files(page_url, site_url, list_guid, year)

    # Fallback: if REST API returns 0 (e.g. auth issue), try the old
    # link-extraction approach with the corrected text filter.
    if not files:
        yy = year[-2:]
        print(f"  [Navy Archive] REST API returned 0, trying link extraction...")
        files = _browser_extract_links(page_url, text_filter=f"/{yy}pres/")

    _save_cache(cache_key, files)
    return files


# ---- Air Force (browser required) ----

def discover_airforce_files(_session: requests.Session, year: str) -> list[dict]:
    """Discover US Air Force/Space Force budget files for a given fiscal year
    using a headless browser.

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


# ---- Discovery router ----

SOURCE_DISCOVERERS = {
    "defense-wide": discover_defense_wide_files,
    "army": discover_army_files,
    "navy": discover_navy_files,
    "navy-archive": discover_navy_archive_files,
    "airforce": discover_airforce_files,
}
