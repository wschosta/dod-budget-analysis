"""Discovery must degrade rather than abort, and prefer plain HTTP when it works.

Two failures motivated these tests, both observed against the live sites:

1. `discover_navy_files` drove secnav.navy.mil through Playwright, which raised
   "Execution context was destroyed, most likely because of a navigation" after
   ~95s. The exception propagated out of `downloader.core.main()` and killed a
   six-source, four-year download before a single file was fetched.
2. The same page answers a plain `requests` GET with HTTP 200 and 36 downloadable
   links — the Navy justification books, including the APN/OPN/WPN procurement
   volumes that carry P-5 exhibits. The browser path returned zero.

So: try HTTP first, treat the browser as a fallback, and never let one source's
failure end the run.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from downloader.sources import (  # noqa: E402
    BROWSER_REQUIRED_SOURCES,
    _http_extract_links,
    discover_navy_files,
)


@pytest.fixture(autouse=True)
def _no_discovery_cache():
    """Bypass the on-disk discovery cache so tests exercise the real path."""
    with patch("downloader.sources._load_cache", return_value=None), \
         patch("downloader.sources._save_cache"):
        yield


class TestHttpExtractLinks:
    def test_returns_empty_list_when_fetch_fails(self):
        """A WAF 403 must be a signal to fall back, not an exception."""
        session = MagicMock()
        session.get.side_effect = requests.RequestException("403 Forbidden")
        assert _http_extract_links(session, "https://example.invalid/x") == []

    def test_returns_empty_list_on_http_error_status(self):
        session = MagicMock()
        resp = MagicMock()
        resp.raise_for_status.side_effect = requests.HTTPError("403")
        session.get.return_value = resp
        assert _http_extract_links(session, "https://example.invalid/x") == []

    def test_parses_links_from_a_successful_response(self):
        session = MagicMock()
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.text = (
            '<html><body>'
            '<a href="/docs/APN_BA1-4_Book.pdf">APN</a>'
            '<a href="/docs/notes.txt">notes</a>'
            '</body></html>'
        )
        session.get.return_value = resp
        files = _http_extract_links(session, "https://example.test/page")
        names = {f["filename"] for f in files}
        assert "APN_BA1-4_Book.pdf" in names


class TestNavyDiscovery:
    def test_prefers_http_and_does_not_touch_the_browser(self):
        """When plain HTTP finds files, Playwright must not be started."""
        session = MagicMock()
        found = [{"filename": "APN_BA1-4_Book.pdf", "url": "https://x/y.pdf",
                  "extension": ".pdf", "source": "navy"}]
        with patch("downloader.sources._http_extract_links", return_value=found), \
             patch("downloader.sources._browser_extract_links") as browser:
            result = discover_navy_files(session, "2026")

        assert result == found
        browser.assert_not_called()

    def test_falls_back_to_browser_when_http_finds_nothing(self):
        session = MagicMock()
        from_browser = [{"filename": "x.pdf", "url": "https://x/x.pdf",
                         "extension": ".pdf", "source": "navy"}]
        with patch("downloader.sources._http_extract_links", return_value=[]), \
             patch("downloader.sources._browser_extract_links",
                   return_value=from_browser) as browser:
            result = discover_navy_files(session, "2026")

        assert result == from_browser
        assert browser.called

    def test_browser_failure_is_swallowed(self):
        """The exact crash: Playwright raising must not escape discovery."""
        session = MagicMock()
        with patch("downloader.sources._http_extract_links", return_value=[]), \
             patch("downloader.sources._browser_extract_links",
                   side_effect=Exception("Execution context was destroyed")):
            result = discover_navy_files(session, "2026")

        assert result == []

    def test_tries_the_alternate_url_for_older_fiscal_years(self):
        """Pre-2022 pages live under /fmc/fmb/; both URLs get an HTTP attempt."""
        session = MagicMock()
        with patch("downloader.sources._http_extract_links",
                   return_value=[]) as http, \
             patch("downloader.sources._browser_extract_links", return_value=[]):
            discover_navy_files(session, "2019")

        urls = [c.args[1] for c in http.call_args_list]
        assert any("/fmc/Pages/" in u for u in urls)
        assert any("/fmc/fmb/Pages/" in u for u in urls)


class TestBrowserRequiredSources:
    def test_navy_downloads_do_not_require_a_browser(self):
        """Verified end to end: a 4.6 MB APN book downloads with a plain GET."""
        assert "navy" not in BROWSER_REQUIRED_SOURCES

    def test_sources_that_still_need_a_browser_are_unchanged(self):
        # army returns HTTP 403 to plain requests; navy-archive is a SharePoint
        # REST view that renders its file list client-side.
        assert {"army", "navy-archive", "airforce"} <= BROWSER_REQUIRED_SOURCES


class TestDiscoveryLoopResilience:
    """A raising discoverer must not abort the remaining sources."""

    def test_core_main_guards_the_discoverer_call(self):
        src = (Path(__file__).resolve().parents[2] / "downloader" / "core.py"
               ).read_text(encoding="utf-8")
        idx = src.find("files = discoverer(session, year)")
        assert idx != -1, "discoverer call not found — test needs updating"
        # The call must sit inside a try block that continues on failure.
        assert "try:" in src[max(0, idx - 600):idx], (
            "discoverer() call is not wrapped in try/except — one bad source "
            "would abort the entire download run"
        )

    def test_run_pipeline_guards_the_discoverer_call(self):
        src = (Path(__file__).resolve().parents[2] / "scripts" / "run_pipeline.py"
               ).read_text(encoding="utf-8")
        idx = src.find("files = discoverer(session, year)")
        assert idx != -1, "discoverer call not found — test needs updating"
        assert "try:" in src[max(0, idx - 800):idx], (
            "pipeline download step does not guard discovery failures"
        )
