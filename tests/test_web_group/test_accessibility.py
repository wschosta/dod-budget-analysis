"""
TEST-006: Static HTML accessibility checks.

Parses rendered HTML from GET / and GET /charts and asserts that key
accessibility requirements are met.  This is static analysis (parsing the
server-side rendered HTML) — not a full Lighthouse or axe-core audit.

Checks:
  - All <img> elements have a non-empty alt attribute
  - Form inputs are associated with a <label for="…"> element
  - Key filter labels carry data-tooltip attributes
  - The results container div is present in the index page
  - Chart canvas elements are present in the charts page
"""
import sqlite3
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import api.app as app_module
from fastapi.testclient import TestClient
from api.app import create_app


# ── Simple HTML parser utilities ──────────────────────────────────────────────

class _TagCollector(HTMLParser):
    """Collect all tags and their attributes from an HTML document."""

    def __init__(self):
        super().__init__()
        self.tags: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append({"tag": tag.lower(), "attrs": dict(attrs)})

    def _find(self, tag: str) -> list[dict]:
        return [t for t in self.tags if t["tag"] == tag]

    def imgs(self) -> list[dict]:
        return self._find("img")

    def inputs(self) -> list[dict]:
        # Include <input>, <select>, <textarea>
        return [t for t in self.tags if t["tag"] in ("input", "select", "textarea")]

    def labels(self) -> list[dict]:
        return self._find("label")

    def divs_by_id(self, div_id: str) -> list[dict]:
        return [
            t for t in self._find("div")
            if t["attrs"].get("id") == div_id
        ]

    def canvas_ids(self) -> list[str]:
        return [
            t["attrs"]["id"]
            for t in self._find("canvas")
            if "id" in t["attrs"]
        ]


def _parse(html: str) -> _TagCollector:
    collector = _TagCollector()
    collector.feed(html)
    return collector


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def a11y_client(tmp_path_factory):
    """App client with minimal test data for accessibility checks."""
    tmp = tmp_path_factory.mktemp("a11y_test")
    db_path = tmp / "a11y.sqlite"

    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE budget_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT, exhibit_type TEXT, sheet_name TEXT,
            fiscal_year TEXT, account TEXT, account_title TEXT,
            organization TEXT, organization_name TEXT,
            budget_activity TEXT, budget_activity_title TEXT,
            sub_activity TEXT, sub_activity_title TEXT,
            line_item TEXT, line_item_title TEXT,
            pe_number TEXT, appropriation_code TEXT, appropriation_title TEXT,
            currency_year TEXT, amount_unit TEXT, amount_type TEXT,
            amount_fy2024_actual REAL, amount_fy2025_enacted REAL,
            amount_fy2025_supplemental REAL, amount_fy2025_total REAL,
            amount_fy2026_request REAL, amount_fy2026_reconciliation REAL,
            amount_fy2026_total REAL,
            quantity_fy2024 REAL, quantity_fy2025 REAL,
            quantity_fy2026_request REAL, quantity_fy2026_total REAL,
            classification TEXT, extra_fields TEXT, budget_type TEXT
        );
        CREATE TABLE pdf_pages (
            id INTEGER PRIMARY KEY, source_file TEXT,
            source_category TEXT, page_number INTEGER,
            page_text TEXT, has_tables INTEGER, table_data TEXT
        );
        CREATE TABLE ingested_files (
            id INTEGER PRIMARY KEY, file_path TEXT, file_type TEXT,
            row_count INTEGER, ingested_at TEXT, status TEXT
        );
        CREATE VIRTUAL TABLE budget_lines_fts USING fts5(
            account_title, line_item_title, budget_activity_title,
            content=budget_lines
        );
        CREATE VIRTUAL TABLE pdf_pages_fts USING fts5(
            page_text, content=pdf_pages
        );
        INSERT INTO budget_lines
            (source_file, exhibit_type, fiscal_year, organization_name,
             account_title, line_item_title, amount_fy2026_request)
        VALUES
            ('army_p1.xlsx', 'p1', 'FY 2026', 'Army',
             'Aircraft Procurement', 'Apache AH-64', 120.0),
            ('navy_r1.xlsx', 'r1', 'FY 2025', 'Navy',
             'RDT&E', 'DDG Research', 80.0);
        INSERT INTO budget_lines_fts(rowid, account_title, line_item_title,
            budget_activity_title)
        SELECT id, account_title, line_item_title, budget_activity_title
        FROM budget_lines;
    """)
    conn.commit()
    conn.close()

    app = create_app(db_path=db_path)
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_rate_counters():
    app_module._rate_counters.clear()
    yield
    app_module._rate_counters.clear()


@pytest.fixture(scope="module")
def index_html(a11y_client):
    resp = a11y_client.get("/")
    assert resp.status_code == 200
    return resp.text


@pytest.fixture(scope="module")
def charts_html(a11y_client):
    resp = a11y_client.get("/charts")
    assert resp.status_code == 200
    return resp.text


# ── Image alt-text checks ─────────────────────────────────────────────────────

class TestImageAltText:
    def test_index_images_have_alt_attribute(self, index_html):
        """All <img> elements on the index page must have an alt attribute."""
        parsed = _parse(index_html)
        imgs = parsed.imgs()
        missing = [img for img in imgs if not img["attrs"].get("alt")]
        assert not missing, (
            f"{len(missing)} <img> element(s) missing alt attribute: {missing}"
        )

    def test_charts_images_have_alt_attribute(self, charts_html):
        """All <img> elements on the charts page must have an alt attribute."""
        parsed = _parse(charts_html)
        imgs = parsed.imgs()
        missing = [img for img in imgs if not img["attrs"].get("alt")]
        assert not missing, (
            f"{len(missing)} <img> element(s) missing alt attribute: {missing}"
        )


# ── Label association checks ──────────────────────────────────────────────────

class TestLabelAssociation:
    """Form inputs on the index page should have associated <label for> elements."""

    _EXPECTED_LABELED_INPUTS = ["q", "fiscal_year", "service", "exhibit_type"]

    def test_keyword_search_has_label(self, index_html):
        """The keyword search input must have an associated label."""
        parsed = _parse(index_html)
        label_fors = {lbl["attrs"].get("for") for lbl in parsed.labels()}
        assert "q" in label_fors, (
            "No <label for='q'> found for the keyword search input"
        )

    def test_fiscal_year_select_has_label(self, index_html):
        """The fiscal year select must have an associated label."""
        parsed = _parse(index_html)
        label_fors = {lbl["attrs"].get("for") for lbl in parsed.labels()}
        assert "fiscal_year" in label_fors, (
            "No <label for='fiscal_year'> found"
        )

    def test_service_select_has_label(self, index_html):
        """The service select must have an associated label."""
        parsed = _parse(index_html)
        label_fors = {lbl["attrs"].get("for") for lbl in parsed.labels()}
        assert "service" in label_fors, (
            "No <label for='service'> found"
        )

    def test_exhibit_type_select_has_label(self, index_html):
        """The exhibit type select must have an associated label."""
        parsed = _parse(index_html)
        label_fors = {lbl["attrs"].get("for") for lbl in parsed.labels()}
        assert "exhibit_type" in label_fors, (
            "No <label for='exhibit_type'> found"
        )

    def test_all_expected_inputs_are_labeled(self, index_html):
        """All expected form inputs must have an associated label."""
        parsed = _parse(index_html)
        label_fors = {lbl["attrs"].get("for") for lbl in parsed.labels()}
        missing = [
            inp_id for inp_id in self._EXPECTED_LABELED_INPUTS
            if inp_id not in label_fors
        ]
        assert not missing, (
            f"Form inputs missing labels: {missing}"
        )


# ── data-tooltip checks ───────────────────────────────────────────────────────

class TestDataTooltips:
    """Key filter labels must carry data-tooltip attributes for user guidance."""

    _TOOLTIP_INPUT_IDS = ["q", "fiscal_year", "service", "exhibit_type"]

    def test_keyword_label_has_tooltip(self, index_html):
        parsed = _parse(index_html)
        q_labels = [
            lbl for lbl in parsed.labels()
            if lbl["attrs"].get("for") == "q"
        ]
        assert q_labels, "No <label for='q'> found"
        assert any("data-tooltip" in lbl["attrs"] for lbl in q_labels), (
            "<label for='q'> is missing a data-tooltip attribute"
        )

    def test_fiscal_year_label_has_tooltip(self, index_html):
        parsed = _parse(index_html)
        fy_labels = [
            lbl for lbl in parsed.labels()
            if lbl["attrs"].get("for") == "fiscal_year"
        ]
        assert fy_labels, "No <label for='fiscal_year'> found"
        assert any("data-tooltip" in lbl["attrs"] for lbl in fy_labels), (
            "<label for='fiscal_year'> is missing a data-tooltip attribute"
        )

    def test_service_label_has_tooltip(self, index_html):
        parsed = _parse(index_html)
        svc_labels = [
            lbl for lbl in parsed.labels()
            if lbl["attrs"].get("for") == "service"
        ]
        assert svc_labels, "No <label for='service'> found"
        assert any("data-tooltip" in lbl["attrs"] for lbl in svc_labels), (
            "<label for='service'> is missing a data-tooltip attribute"
        )

    def test_exhibit_type_label_has_tooltip(self, index_html):
        parsed = _parse(index_html)
        et_labels = [
            lbl for lbl in parsed.labels()
            if lbl["attrs"].get("for") == "exhibit_type"
        ]
        assert et_labels, "No <label for='exhibit_type'> found"
        assert any("data-tooltip" in lbl["attrs"] for lbl in et_labels), (
            "<label for='exhibit_type'> is missing a data-tooltip attribute"
        )


# ── Dynamic container presence checks ────────────────────────────────────────

class TestDynamicContainers:
    """Key dynamic containers must be present so HTMX can target them."""

    def test_results_container_present_on_index(self, index_html):
        """The #results-container div must exist in the index page."""
        parsed = _parse(index_html)
        containers = parsed.divs_by_id("results-container")
        assert containers, "No <div id='results-container'> found on index page"

    def test_detail_container_present_on_index(self, index_html):
        """The #detail-container div must exist for the detail partial."""
        parsed = _parse(index_html)
        containers = parsed.divs_by_id("detail-container")
        assert containers, "No <div id='detail-container'> found on index page"


# ── Chart canvas element checks ───────────────────────────────────────────────

class TestChartContainers:
    """Chart canvas elements must be present in the charts page."""

    _EXPECTED_CANVAS_IDS = ["chart-service", "chart-yoy", "chart-topn"]

    def test_service_chart_canvas_present(self, charts_html):
        parsed = _parse(charts_html)
        assert "chart-service" in parsed.canvas_ids(), (
            "No <canvas id='chart-service'> found on charts page"
        )

    def test_yoy_chart_canvas_present(self, charts_html):
        parsed = _parse(charts_html)
        assert "chart-yoy" in parsed.canvas_ids(), (
            "No <canvas id='chart-yoy'> found on charts page"
        )

    def test_topn_chart_canvas_present(self, charts_html):
        parsed = _parse(charts_html)
        assert "chart-topn" in parsed.canvas_ids(), (
            "No <canvas id='chart-topn'> found on charts page"
        )

    def test_all_expected_chart_canvases_present(self, charts_html):
        parsed = _parse(charts_html)
        found = set(parsed.canvas_ids())
        missing = [c for c in self._EXPECTED_CANVAS_IDS if c not in found]
        assert not missing, (
            f"Chart canvas elements missing from /charts page: {missing}"
        )
