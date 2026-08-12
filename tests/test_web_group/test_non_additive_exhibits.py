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
