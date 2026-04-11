"""Tests for api/routes/hypersonics.py — hypersonics PE lines endpoints."""

import csv
import io

import openpyxl
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

    @pytest.mark.parametrize("required, actual, label", [
        ("REQUIRED_KEYWORDS", _HYPERSONICS_KEYWORDS, "_HYPERSONICS_KEYWORDS"),
        ("REQUIRED_DESC_KEYWORDS", _DESC_KEYWORDS, "_DESC_KEYWORDS"),
    ])
    def test_all_required_present(self, required, actual, label):
        required_list = getattr(self, required) if isinstance(required, str) else required
        actual_lower = [kw.lower() for kw in actual]
        missing = [kw for kw in required_list if kw.lower() not in actual_lower]
        assert not missing, f"Missing from {label}: {missing}"

    @pytest.mark.parametrize("keywords, label", [
        (_HYPERSONICS_KEYWORDS, "_HYPERSONICS_KEYWORDS"),
        (_DESC_KEYWORDS, "_DESC_KEYWORDS"),
    ])
    def test_no_duplicates(self, keywords, label):
        seen: set[str] = set()
        dupes = [kw for kw in keywords if (low := kw.lower()) in seen or seen.add(low)]  # type: ignore[func-returns-value]
        assert not dupes, f"Duplicate entries in {label}: {dupes}"

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

    def _pick_show_ids(self, client, limit: int = 4) -> list[str]:
        """Read hypersonics JSON and construct ``pe-{idx}`` identifiers."""
        body = client.get("/api/v1/hypersonics").json()
        rows = body.get("rows", [])
        if not rows:
            pytest.skip("No hypersonics rows in test DB")
        ids: list[str] = []
        pe_counts: dict[str, int] = {}
        for row in rows:
            pe = row.get("pe_number")
            if not pe:
                continue
            idx = pe_counts.get(pe, 0)
            ids.append(f"{pe}-{idx}")
            pe_counts[pe] = idx + 1
            if len(ids) >= limit:
                break
        return ids

    def test_interleaved_fy_headers(self, client):
        """Each FY should be followed immediately by its Source and Description."""
        show_ids = self._pick_show_ids(client, limit=4)
        resp = client.post(
            "/api/v1/hypersonics/download/xlsx",
            json={"show_ids": show_ids, "total_ids": show_ids[:2]},
        )
        assert resp.status_code == 200
        wb = openpyxl.load_workbook(io.BytesIO(resp.content))
        ws = wb.active
        headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]

        # Fixed headers at the front
        assert headers[:7] == [
            "PE Number", "Service/Org", "Exhibit", "Line Item / Sub-Program",
            "Budget Activity", "Color of Money", "In Totals",
        ]

        # Remaining headers must form triples: [FY{yr} ($K), FY{yr} Source, FY{yr} Description]
        remainder = headers[7:]
        assert len(remainder) % 3 == 0, f"FY columns not in triples: {remainder}"
        for i in range(0, len(remainder), 3):
            val_h, src_h, desc_h = remainder[i : i + 3]
            assert val_h.endswith("($K)"), f"Expected value header at {i}: {val_h}"
            year = val_h.replace("FY", "").replace(" ($K)", "").strip()
            assert src_h == f"FY{year} Source"
            assert desc_h == f"FY{year} Description"

    def test_totals_row_uses_sumif_formula(self, client):
        """Bottom totals row should contain SUMIF formulas keyed off 'In Totals'."""
        show_ids = self._pick_show_ids(client, limit=4)
        resp = client.post(
            "/api/v1/hypersonics/download/xlsx",
            json={"show_ids": show_ids, "total_ids": show_ids[:2]},
        )
        assert resp.status_code == 200
        wb = openpyxl.load_workbook(io.BytesIO(resp.content))
        ws = wb.active
        last_row = ws.max_row
        assert ws.cell(row=last_row, column=1).value == "TOTALS"

        # Locate the first FY value column (position 8: right after fixed headers)
        fy_val_cell = ws.cell(row=last_row, column=8).value
        assert isinstance(fy_val_cell, str) and fy_val_cell.startswith("=SUMIF("), (
            f"Expected SUMIF formula in FY totals cell, got: {fy_val_cell!r}"
        )
        assert '"Yes"' in fy_val_cell
