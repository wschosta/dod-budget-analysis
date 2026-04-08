"""Tests for api/routes/hypersonics.py — hypersonics PE lines endpoints."""

import csv
import io

import pytest

from api.routes.hypersonics import _HYPERSONICS_KEYWORDS, _DESC_KEYWORDS


@pytest.fixture(scope="module", autouse=True)
def _rebuild_hypersonics_cache(client):
    """Rebuild the hypersonics cache once for the entire module."""
    client.post("/api/v1/hypersonics/rebuild")


class TestRebuildCache:
    def test_rebuild_returns_200(self, client):
        resp = client.post("/api/v1/hypersonics/rebuild")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "rows" in body


class TestGetHypersonics:
    def test_get_returns_200(self, client):
        resp = client.get("/api/v1/hypersonics")
        assert resp.status_code == 200

    def test_response_structure(self, client):
        body = client.get("/api/v1/hypersonics").json()
        assert "count" in body
        assert "fiscal_years" in body
        assert "keywords" in body
        assert "rows" in body
        assert isinstance(body["rows"], list)
        assert isinstance(body["fiscal_years"], list)
        assert isinstance(body["keywords"], list)

    def test_filter_by_service(self, client):
        resp = client.get("/api/v1/hypersonics", params={"service": "Army"})
        assert resp.status_code == 200

    def test_filter_by_exhibit(self, client):
        resp = client.get("/api/v1/hypersonics", params={"exhibit": "r1"})
        assert resp.status_code == 200


class TestDownloadCSV:
    def test_csv_download(self, client):
        resp = client.get("/api/v1/hypersonics/download")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_csv_has_content_disposition(self, client):
        resp = client.get("/api/v1/hypersonics/download")
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert "csv" in resp.headers.get("content-disposition", "")

    def test_csv_parseable(self, client):
        resp = client.get("/api/v1/hypersonics/download")
        text = resp.content.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        headers = next(reader)
        assert "PE Number" in headers
        assert "Service/Org" in headers


class TestGetDescription:
    def test_desc_existing_pe(self, client):
        resp = client.get("/api/v1/hypersonics/desc/0602702E")
        assert resp.status_code == 200
        body = resp.json()
        assert "description" in body

    def test_desc_nonexistent_pe(self, client):
        resp = client.get("/api/v1/hypersonics/desc/ZZZZZZZZ")
        assert resp.status_code == 200
        assert resp.json()["description"] is None


class TestDebug:
    def test_debug_returns_200(self, client):
        body = client.get("/api/v1/hypersonics/debug").json()
        assert "cache" in body

    def test_debug_cache_status(self, client):
        cache = client.get("/api/v1/hypersonics/debug").json()["cache"]
        assert "table_exists" in cache
        assert "row_count" in cache


class TestKeywordLists:
    """Validate that required search terms are present in keyword lists."""

    # Every term listed here must appear in _HYPERSONICS_KEYWORDS (case-insensitive).
    REQUIRED_KEYWORDS = [
        # Generic / cross-program
        "hypersonic", "boost glide", "glide body", "glide vehicle", "scramjet",
        # Offensive — Air Force
        "ARRW", "AGM-183", "HACM", "HCSW",
        # Offensive — Army
        "LRHW", "Dark Eagle", "OpFires",
        # Offensive — Navy / Joint
        "C-HGB", "CHGB", "conventional prompt strike", "prompt strike",
        # SM-6 / OASUW
        "offensive anti", "oasuw", "standard missile 6", "sm-6", "blk ib",
        "increment ii",
        # Generic speed / regime
        "high speed", "mach", "conventional prompt",
        # Defensive / tracking
        "Glide Phase Interceptor", "HBTSS",
    ]

    # Subset that must also be in _DESC_KEYWORDS
    REQUIRED_DESC_KEYWORDS = [
        "hypersonic", "boost glide", "glide vehicle", "scramjet",
        "ARRW", "HACM", "HCSW", "LRHW", "Dark Eagle",
        "C-HGB", "CHGB", "conventional prompt strike", "conventional prompt",
        "prompt strike", "Glide Phase Interceptor", "HBTSS", "OpFires",
        "offensive anti", "oasuw", "standard missile 6", "sm-6",
        "blk ib", "increment ii", "high speed", "mach",
    ]

    def test_all_required_keywords_present(self):
        kw_lower = [kw.lower() for kw in _HYPERSONICS_KEYWORDS]
        missing = [kw for kw in self.REQUIRED_KEYWORDS if kw.lower() not in kw_lower]
        assert not missing, f"Missing from _HYPERSONICS_KEYWORDS: {missing}"

    def test_all_required_desc_keywords_present(self):
        kw_lower = [kw.lower() for kw in _DESC_KEYWORDS]
        missing = [kw for kw in self.REQUIRED_DESC_KEYWORDS if kw.lower() not in kw_lower]
        assert not missing, f"Missing from _DESC_KEYWORDS: {missing}"

    def test_no_duplicates_in_keywords(self):
        seen: set[str] = set()
        dupes = []
        for kw in _HYPERSONICS_KEYWORDS:
            low = kw.lower()
            if low in seen:
                dupes.append(kw)
            seen.add(low)
        assert not dupes, f"Duplicate entries in _HYPERSONICS_KEYWORDS: {dupes}"

    def test_no_duplicates_in_desc_keywords(self):
        seen: set[str] = set()
        dupes = []
        for kw in _DESC_KEYWORDS:
            low = kw.lower()
            if low in seen:
                dupes.append(kw)
            seen.add(low)
        assert not dupes, f"Duplicate entries in _DESC_KEYWORDS: {dupes}"

    def test_desc_keywords_subset_of_main(self):
        """Every desc keyword should also be in the main keyword list."""
        main_lower = {kw.lower() for kw in _HYPERSONICS_KEYWORDS}
        extras = [kw for kw in _DESC_KEYWORDS if kw.lower() not in main_lower]
        assert not extras, f"In _DESC_KEYWORDS but not _HYPERSONICS_KEYWORDS: {extras}"


class TestDownloadXLSX:
    def test_no_rows_selected_returns_400(self, client):
        resp = client.post(
            "/api/v1/hypersonics/download/xlsx",
            json={"show_ids": [], "total_ids": []},
        )
        assert resp.status_code == 400
