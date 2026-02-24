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

---
Backward-compatible shim.

This module re-exports everything from the ``downloader`` package so that
existing imports (``from dod_budget_downloader import X``) continue to work
after the code was split into downloader/{sources,gui,manifest,core}.py.
"""

# Re-export all public names from the downloader package
from downloader import *  # noqa: F401, F403
from downloader import (  # explicit imports for static analysis tools
    # Shared utilities (re-exported for backward compat)
    format_bytes,
    elapsed,
    sanitize_filename,
    # Configuration and constants
    ALL_SOURCES,
    BASE_URL,
    BROWSER_REQUIRED_SOURCES,
    BUDGET_MATERIALS_URL,
    DEFAULT_OUTPUT_DIR,
    DISCOVERY_CACHE_DIR,
    DOWNLOADABLE_EXTENSIONS,
    DOWNLOADABLE_PATTERN,
    DomainRateLimiter,
    GuiProgressTracker,
    HEADERS,
    IGNORED_HOSTS,
    PARSER,
    ProgressTracker,
    SERVICE_PAGE_TEMPLATES,
    SOURCE_DISCOVERERS,
    TimeoutManager,
    USER_AGENT,
    _browser_download_file,
    _browser_extract_links,
    _check_existing_file,
    _clean_file_entry,
    _close_browser,
    _close_session,
    _compute_sha256,
    _detect_waf_block,
    _extract_downloadable_links,
    _extract_zip,
    _get_browser_context,
    _get_cache_key,
    _get_chunk_size,
    _interactive_select,
    _is_browser_source,
    _load_cache,
    _new_browser_page,
    _save_cache,
    _verify_download,
    discover_airforce_files,
    discover_army_files,
    discover_comptroller_files,
    discover_defense_wide_files,
    discover_fiscal_years,
    discover_navy_archive_files,
    discover_navy_files,
    download_all,
    download_file,
    get_session,
    interactive_select_sources,
    interactive_select_years,
    list_files,
    load_manifest_ok_urls,
    main,
    update_manifest_entry,
    write_manifest,
)

if __name__ == "__main__":
    main()
