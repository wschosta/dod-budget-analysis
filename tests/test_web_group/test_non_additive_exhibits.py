"""P-1R is a memo exhibit and must not be summed alongside P-1.

P-1R restates Reserve and National Guard equipment that the P-1 rows already
count: 1,141 of its 1,143 corpus rows are titled "NATL Guard Equip (MEMO NON
ADD)" or "Reserve Equip (MEMO NON ADD)". Summing both inflates procurement
totals by 2.76% overall and up to 6.35% on individual fiscal-year columns —
about $80.5 billion.

The obvious guard does not work: `add_non_add` reads "Add" on all 6,758 P-1
rows including every memo row, so the exclusion has to key on the exhibit.

Scope matters. This applies to aggregation only — P-1R rows stay visible in
search, browse and detail views, and a caller who explicitly filters to P-1R
still gets its totals rather than an empty result.
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

from utils.query import (  # noqa: E402
    NON_ADDITIVE_EXHIBIT_TYPES,
    exclude_non_additive,
)


class TestExcludeNonAdditiveHelper:
    def test_builds_a_where_clause_from_nothing(self):
        assert exclude_non_additive("").startswith("WHERE")
        assert "p1r" in exclude_non_additive("")

    def test_appends_to_an_existing_where_clause(self):
        result = exclude_non_additive("WHERE fiscal_year = ?")
        assert result.startswith("WHERE fiscal_year = ?")
        assert "p1r" in result
        assert result.count("WHERE") == 1

    def test_accepts_a_clause_without_the_where_keyword(self):
        result = exclude_non_additive("fiscal_year = ?")
        assert result.startswith("WHERE fiscal_year = ?")

    def test_adds_no_bound_parameters(self):
        """Callers pass their own params list; the filter must not shift it.

        The exclusion is a literal comparison, so a caller can append it to a
        clause without touching the parameter sequence.
        """
        added = exclude_non_additive("WHERE fiscal_year = ?")
        assert added.count("?") == 1  # only the caller's own placeholder

    @pytest.mark.parametrize("requested", ["p1r", ["p1r"], ["p1", "p1r"], "P1R"])
    def test_skips_exclusion_when_caller_asked_for_that_exhibit(self, requested):
        """An empty chart is worse than showing memo totals someone chose."""
        clause = "WHERE fiscal_year = ?"
        assert exclude_non_additive(clause, requested) == clause

    @pytest.mark.parametrize("requested", [None, [], "p1", ["p1", "r1"]])
    def test_still_excludes_for_unrelated_filters(self, requested):
        assert "p1r" in exclude_non_additive("WHERE x = ?", requested)

    def test_p1r_is_the_declared_non_additive_exhibit(self):
        assert "p1r" in NON_ADDITIVE_EXHIBIT_TYPES


@pytest.fixture()
def memo_db(tmp_path):
    """A P-1 row of 1,000 and a P-1R memo row of 250 for the same line item."""
    from pipeline.builder import create_database

    db = tmp_path / "memo.sqlite"
    # Real schema rather than a hand-rolled subset: the row-listing endpoint
    # selects a wide column set, and a trimmed fixture only proves which
    # columns the test happened to guess.
    conn = create_database(db)
    conn.executescript("""
        INSERT INTO budget_lines
            (source_file, fiscal_year, source_fiscal_year, exhibit_type,
             organization_name, line_item, line_item_title, cost_type_title,
             add_non_add, budget_type, amount_fy2026_request)
        VALUES
            ('p1.xlsx','2026','2026','p1','Navy','1000','Widget','Weapon System Cost','Add','Procurement',1000.0),
            ('p1r.xlsx','2026','2026','p1r','Navy','1000','Widget','Reserve Equip (MEMO NON ADD)','Add','Procurement',250.0);
    """)
    conn.commit()
    conn.close()
    return db


@pytest.fixture()
def client(memo_db):
    from api.app import create_app
    return TestClient(create_app(db_path=memo_db))


class TestAggregationEndpoint:
    def test_memo_row_is_not_summed(self, client):
        resp = client.get("/api/v1/aggregations?group_by=service")
        assert resp.status_code == 200
        rows = resp.json()["rows"]
        navy = next(r for r in rows if r["group_value"] == "Navy")
        total = navy["fy_totals"]["amount_fy2026_request"]
        assert total == pytest.approx(1000.0), (
            "P-1R memo row was included; totals are inflated"
        )

    def test_explicit_p1r_filter_still_returns_its_total(self, client):
        resp = client.get("/api/v1/aggregations?group_by=service&exhibit_type=p1r")
        assert resp.status_code == 200
        rows = resp.json()["rows"]
        assert rows, "filtering to p1r returned nothing"
        navy = next(r for r in rows if r["group_value"] == "Navy")
        assert navy["fy_totals"]["amount_fy2026_request"] == pytest.approx(250.0)


class TestNonAggregateViewsUnaffected:
    def test_memo_rows_remain_searchable(self, client):
        """Someone looking for Guard equipment should still find it."""
        resp = client.get("/api/v1/budget-lines?limit=50")
        assert resp.status_code == 200
        exhibits = {row["exhibit_type"] for row in resp.json()["items"]}
        assert "p1r" in exhibits, "memo rows disappeared from the row listing"


class TestDashboardNotEmptiedBySummaryExclusion:
    """The dashboard must not exclude the only exhibit types the data has.

    `build_where_clause(exclude_summary=True)` drops P-1, R-1, O-1, M-1, C-1,
    RF-1 and P-1R. Every row in budget_lines comes from a summary workbook —
    the detail exhibits (P-5, R-2) live in pdf_pages — so passing that flag
    matched zero of 18,200 rows and the dashboard served total_lines 0, null
    totals and an empty array for every chart.

    Nor is it needed: the six appropriation summaries cover disjoint
    appropriations, so summing them is a total rather than a double count.
    """

    def test_totals_are_not_zero(self, client):
        resp = client.get("/api/v1/dashboard/summary")
        assert resp.status_code == 200
        totals = resp.json()["totals"]
        assert totals["total_lines"] > 0, "dashboard excluded every row"
        assert totals["total_fy26_request"], "dashboard reported no funding"

    def test_charts_are_populated(self, client):
        resp = client.get("/api/v1/dashboard/summary")
        body = resp.json()
        assert body["by_service"], "service breakdown empty"
        assert body["by_fiscal_year"], "fiscal year breakdown empty"

    def test_memo_row_excluded_from_dashboard_totals(self, client):
        """1,000 from the P-1 row; the 250 memo row must not be added."""
        totals = client.get("/api/v1/dashboard/summary").json()["totals"]
        assert totals["total_fy26_request"] == pytest.approx(1000.0)

    def test_memo_row_absent_from_top_programs(self, client):
        """A memo line presented among Top Programs reads as new spending."""
        body = client.get("/api/v1/dashboard/summary").json()
        amounts = [p.get("fy26_request") for p in body["top_programs"]]
        assert 250.0 not in amounts


class TestProgramElementTotals:
    """Phase 11 backfills pe_number onto P-1R rows, so PE views are exposed too.

    46 memo rows carry a PE number in the corpus, inflating individual program
    elements by up to 8.1%.
    """

    def test_pe_totals_exclude_memo_rows(self, memo_db):
        """/pe/top-changes groups budget_lines by pe_number and sums it."""
        import sqlite3 as _sqlite3

        conn = _sqlite3.connect(str(memo_db))
        conn.execute(
            "UPDATE budget_lines SET pe_number = '0204571N' "
            "WHERE exhibit_type IN ('p1','p1r')"
        )
        conn.commit()
        conn.close()

        from api.app import create_app
        local = TestClient(create_app(db_path=memo_db))
        resp = local.get("/api/v1/pe/top-changes?limit=5")
        assert resp.status_code == 200

        rows = resp.json()
        rows = rows["items"] if isinstance(rows, dict) else rows
        entry = next((r for r in rows if r.get("pe_number") == "0204571N"), None)
        assert entry is not None, "PE missing from top-changes"
        # 1,000 from the P-1 row; the 250 memo row must not be added.
        assert entry["fy2026_request"] == pytest.approx(1000.0)


class TestHasDetailExhibits:
    """Whether summaries should be excluded depends on what the table holds.

    FIX-006 was right for a corpus carrying both detail and summary exhibits;
    it was wrong for one carrying only summaries. The decision cannot be made
    statically, so it is read from the database.
    """

    def _db(self, tmp_path, rows):
        import sqlite3 as _sqlite3
        db = tmp_path / "detect.sqlite"
        conn = _sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE budget_lines (id INTEGER PRIMARY KEY, exhibit_type TEXT)"
        )
        conn.executemany(
            "INSERT INTO budget_lines (exhibit_type) VALUES (?)", [(r,) for r in rows]
        )
        conn.commit()
        return conn

    def test_summary_only_corpus_reports_no_detail(self, tmp_path):
        from utils.query import has_detail_exhibits
        conn = self._db(tmp_path, ["p1", "r1", "o1", "c1", "m1", "rf1", "p1r"])
        assert has_detail_exhibits(conn) is False
        conn.close()

    def test_corpus_with_detail_reports_detail(self, tmp_path):
        from utils.query import has_detail_exhibits
        conn = self._db(tmp_path, ["p1", "r1", "r2"])
        assert has_detail_exhibits(conn) is True
        conn.close()

    def test_missing_table_is_not_an_error(self, tmp_path):
        """Called during request handling; a bad database must not 500."""
        import sqlite3 as _sqlite3
        from utils.query import has_detail_exhibits
        conn = _sqlite3.connect(str(tmp_path / "empty.sqlite"))
        assert has_detail_exhibits(conn) is False
        conn.close()
