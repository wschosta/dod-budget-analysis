"""
DoD Budget Document Downloader Package.

Downloads budget documents (PDFs, Excel files, ZIPs) from the DoD Comptroller
website and service-specific budget pages for selected fiscal years.

This package re-exports all public names from the original monolithic
dod_budget_downloader.py module so that ``from downloader import X`` works
identically to the old ``from dod_budget_downloader import X``.
"""

# ---- Shared utilities (re-exported for backward compatibility) ----
from utils import format_bytes, elapsed, sanitize_filename

# ---- Sources: discovery functions and configuration ----
from downloader.sources import (
    ALL_SOURCES,
    BASE_URL,
    BROWSER_REQUIRED_SOURCES,
    BUDGET_MATERIALS_URL,
    DISCOVERY_CACHE_DIR,
    DOWNLOADABLE_EXTENSIONS_SET as DOWNLOADABLE_EXTENSIONS,
    DOWNLOADABLE_PATTERN,
    HEADERS,
    IGNORED_HOSTS,
    PARSER,
    SERVICE_PAGE_TEMPLATES,
    SOURCE_DISCOVERERS,
    TimeoutManager,
    USER_AGENT,
    _browser_download_file,
    _browser_extract_links,
    _clean_file_entry,
    _close_browser,
    _extract_downloadable_links,
    _get_browser_context,
    _get_cache_key,
    _is_browser_source,
    _load_cache,
    _new_browser_page,
    _save_cache,
    discover_airforce_files,
    discover_army_files,
    discover_comptroller_files,
    discover_defense_wide_files,
    discover_fiscal_years,
    discover_navy_archive_files,
    discover_navy_files,
)

# ---- GUI ----
from downloader.gui import GuiProgressTracker

# ---- Manifest ----
from downloader.manifest import (
    _compute_sha256,
    load_manifest_ok_urls,
    update_manifest_entry,
    write_manifest,
)

# ---- Core: download orchestration, CLI, progress tracking ----
from downloader.core import (
    DEFAULT_OUTPUT_DIR,
    DomainRateLimiter,
    ProgressTracker,
    _check_existing_file,
    _close_session,
    _detect_waf_block,
    _extract_zip,
    _get_chunk_size,
    _interactive_select,
    _verify_download,
    download_all,
    download_file,
    get_session,
    interactive_select_sources,
    interactive_select_years,
    list_files,
    main,
)

__all__ = [
    # Shared utilities (re-exported for backward compatibility)
    "format_bytes",
    "elapsed",
    "sanitize_filename",
    # Sources / configuration
    "ALL_SOURCES",
    "BASE_URL",
    "BROWSER_REQUIRED_SOURCES",
    "BUDGET_MATERIALS_URL",
    "DISCOVERY_CACHE_DIR",
    "DOWNLOADABLE_EXTENSIONS",
    "DOWNLOADABLE_PATTERN",
    "HEADERS",
    "IGNORED_HOSTS",
    "PARSER",
    "SERVICE_PAGE_TEMPLATES",
    "SOURCE_DISCOVERERS",
    "TimeoutManager",
    "USER_AGENT",
    # Discovery functions
    "discover_fiscal_years",
    "discover_comptroller_files",
    "discover_defense_wide_files",
    "discover_army_files",
    "discover_navy_files",
    "discover_navy_archive_files",
    "discover_airforce_files",
    # Browser helpers
    "_browser_extract_links",
    "_browser_download_file",
    "_close_browser",
    "_get_browser_context",
    "_new_browser_page",
    "_is_browser_source",
    # Link extraction helpers
    "_extract_downloadable_links",
    "_clean_file_entry",
    # Cache helpers
    "_get_cache_key",
    "_load_cache",
    "_save_cache",
    # GUI
    "GuiProgressTracker",
    # Manifest
    "_compute_sha256",
    "load_manifest_ok_urls",
    "update_manifest_entry",
    "write_manifest",
    # Core / download
    "DEFAULT_OUTPUT_DIR",
    "DomainRateLimiter",
    "ProgressTracker",
    "download_all",
    "download_file",
    "get_session",
    "_close_session",
    "_check_existing_file",
    "_detect_waf_block",
    "_extract_zip",
    "_get_chunk_size",
    "_interactive_select",
    "_verify_download",
    "interactive_select_sources",
    "interactive_select_years",
    "list_files",
    "main",
]
