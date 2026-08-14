"""The search API's `limit` is per source, and `total` is per response.

Both fields read like their conventional meanings and are not. `limit=3`
returns 6 items when two sources match, and `total` counts what came back
rather than what exists — the FTS scan is deliberately bounded, so a
corpus-wide match count is never computed.

These tests pin the actual behaviour so the documentation and the code cannot
drift apart again. They assert what the API *does*; if a future change makes
`limit` mean per-page, these should be updated deliberately rather than
discovered by a caller.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for _mod in ("pdfplumber", "openpyxl", "pandas"):
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def search_db(tmp_path):
    """A corpus with the same term in budget lines and PDF pages."""
    from pipeline.builder import create_database

    db = tmp_path / "search.sqlite"
    conn = create_database(db)
    rows = [
        (f"p1_{i}.xlsx", "2026", "2026", "p1", "Navy", f"{i}",
         f"Hypersonic Glide Body {i}", 1000.0 + i)
        for i in range(8)
    ]
    conn.executemany(
        "INSERT INTO budget_lines (source_file, fiscal_year, source_fiscal_year,"
        " exhibit_type, organization_name, line_item, line_item_title,"
        " amount_fy2026_request) VALUES (?,?,?,?,?,?,?,?)", rows,
    )
    conn.executemany(
        "INSERT INTO pdf_pages (source_file, fiscal_year, exhibit_type,"
        " page_number, page_text, has_tables)"
        " VALUES (?,?,?,?,?,0)",
        [(f"book_{i}.pdf", "2026", "r2", i,
          f"Hypersonic glide body discussion page {i}") for i in range(8)],
    )
    conn.commit()
    for tbl in ("budget_lines_fts", "pdf_pages_fts"):
        try:
            conn.execute(f"INSERT INTO {tbl}({tbl}) VALUES('rebuild')")
        except Exception:  # pragma: no cover - table may not exist
            pass
    conn.commit()
    conn.close()
    return db


@pytest.fixture()
def client(search_db):
    from api.app import create_app
    return TestClient(create_app(db_path=search_db))


def test_limit_applies_per_source_not_per_page(client):
    """limit=2 across two sources yields up to 4 items, by design."""
    body = client.get("/api/v1/search?q=hypersonic&limit=2&source=both").json()
    per_source = {body["budget_line_count"], body["pdf_page_count"]}
    assert max(per_source) <= 2, "a single source exceeded the limit"
    assert len(body["results"]) == body["total"]
    assert body["total"] > 2, (
        "documented behaviour is per-source limiting; a per-page cap would "
        "make this <= 2 and the field docs need updating with the change"
    )


def test_total_counts_this_response_only(client):
    """total tracks the page, so it grows with limit rather than being fixed."""
    small = client.get("/api/v1/search?q=hypersonic&limit=1&source=both").json()
    large = client.get("/api/v1/search?q=hypersonic&limit=4&source=both").json()
    assert large["total"] > small["total"], (
        "total is per-response; if it became a corpus-wide match count it "
        "would be identical for both requests"
    )


def test_has_more_is_the_pagination_signal(client):
    """Callers must page on has_more, since total cannot tell them."""
    body = client.get("/api/v1/search?q=hypersonic&limit=1&source=both").json()
    assert body["has_more"] is True


def test_no_matches_reports_zero_and_no_more(client):
    body = client.get("/api/v1/search?q=zzzznotarealterm&limit=5").json()
    assert body["total"] == 0
    assert body["results"] == []
    assert body["has_more"] is False
