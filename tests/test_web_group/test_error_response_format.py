"""Error responses must match the caller: JSON for data routes, HTML for pages.

The handlers were previously registered per status code (404 and 500 only),
which had two consequences: REST clients received a full HTML document for a
missing record, and any other status raised from a page route — a 503 from an
unavailable consolidated database, for instance — leaked raw JSON into the
browser window.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.app import create_app


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("error_fmt")
    db_path = tmp / "test.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT, exhibit_type TEXT, sheet_name TEXT,
            fiscal_year TEXT, account TEXT, account_title TEXT,
            organization_name TEXT, budget_activity_title TEXT,
            sub_activity_title TEXT, line_item TEXT, line_item_title TEXT,
            pe_number TEXT, amount_type TEXT, amount_unit TEXT,
            currency_year TEXT, appropriation_code TEXT, appropriation_title TEXT,
            budget_type TEXT,
            amount_fy2024_actual REAL, amount_fy2025_enacted REAL,
            amount_fy2025_supplemental REAL, amount_fy2025_total REAL,
            amount_fy2026_request REAL, amount_fy2026_reconciliation REAL,
            amount_fy2026_total REAL,
            quantity_fy2024 REAL, quantity_fy2025 REAL,
            quantity_fy2026_request REAL, quantity_fy2026_total REAL
        );
        """
    )
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)

    # A page route that raises a status other than 404/500, mirroring the
    # /consolidated 503 that surfaced this.
    @app.get("/_test_unavailable")
    def _unavailable():
        raise HTTPException(status_code=503, detail="Backing store unavailable")

    return TestClient(app, raise_server_exceptions=False)


class TestDataRoutesReturnJson:
    def test_api_404_is_json_not_html(self, client):
        resp = client.get("/api/v1/budget-lines/999999")
        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("application/json")
        assert not resp.text.lstrip().startswith("<!DOCTYPE")
        assert resp.json()["detail"]

    def test_api_404_body_is_parseable(self, client):
        body = client.get("/api/v1/budget-lines/999999").json()
        assert body["status_code"] == 404

    def test_unknown_api_path_is_json(self, client):
        resp = client.get("/api/v1/no-such-endpoint")
        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("application/json")


class TestPageRoutesReturnHtml:
    def test_unknown_page_renders_html_404(self, client):
        resp = client.get("/no-such-page")
        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith("text/html")
        assert "<html" in resp.text.lower()

    def test_html_error_page_is_accessible(self, client):
        # axe-core flagged both of these on a JSON error rendered in a browser.
        text = client.get("/no-such-page").text.lower()
        assert 'lang="en"' in text
        assert "<title>" in text

    def test_non_404_page_error_still_renders_html(self, client):
        resp = client.get("/_test_unavailable")
        assert resp.status_code == 503
        assert resp.headers["content-type"].startswith("text/html")
        assert "<html" in resp.text.lower()

    def test_error_page_shows_the_actual_status_code(self, client):
        # The template hardcoded 500; a 503 must not claim to be a 500.
        assert "503" in client.get("/_test_unavailable").text
