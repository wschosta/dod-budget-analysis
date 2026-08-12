"""Reconcile Exhibit P-40 (PDF) against the P-1 rows ingested from Excel.

Both sources describe the same procurement line items, so before any P-40 data
is written into ``budget_lines`` it has to be established which one is right
where they differ. This script answers that per line item rather than in
aggregate.

The join key is ``(account, sub_activity, line_item, fiscal_year)``. All four
parts are required: Procurement, Defense-Wide line item 30 is "Major
Equipment" for a dozen agencies, each with its own P-40 page and its own
budget sub-activity, so joining without the BSA collapses them together and
double-counts — an earlier account-level pass showed 0300D at 108 PDF pages
against 53 Excel rows, and 0360D at *exactly* +100.0%.

The line item number cannot be read from the flattened page text (the header
is two printed columns pdfplumber concatenates); it comes from
:mod:`pipeline.p40_positional`, which recovers it from word coordinates at
99.0% accuracy.

Usage::

    python scripts/reconcile_p40_vs_p1.py                 # extract, then compare
    python scripts/reconcile_p40_vs_p1.py --cache recs.json
    python scripts/reconcile_p40_vs_p1.py --cache recs.json --reuse-cache

Extraction re-opens every procurement PDF and takes several minutes, hence the
cache.
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import os
import sqlite3
import sys
import warnings
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from pipeline.p40_parser import parse_p40_page  # noqa: E402
from pipeline.p40_positional import extract_header_columns  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# Rows agreeing to within this percentage are treated as consistent. The PDF
# prints millions to three decimals while Excel stores thousands, so exact
# equality is not expected even when both are right.
AGREEMENT_TOLERANCE_PCT = 1.0


def _norm(value: object) -> str | None:
    """Normalise a key part. Excel zero-pads BSA ("01"); the PDF does not."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return str(int(text)) if text.isdigit() else text.upper()


def extract_records(db_path: Path, docs_dir: Path) -> list[dict]:
    """Read every P-40 page that carries a Resource Summary."""
    warnings.filterwarnings("ignore")
    import pdfplumber

    conn = sqlite3.connect(str(db_path))
    pages: dict[str, list[tuple[int, str]]] = collections.defaultdict(list)
    for source_file, page_number, text in conn.execute(
        "SELECT source_file, page_number, page_text FROM pdf_pages "
        "WHERE page_exhibit_type = 'p40' AND page_text LIKE '%Resource Summary%'"
    ):
        pages[source_file].append((page_number, text))
    conn.close()

    records: list[dict] = []
    for source_file, page_list in sorted(pages.items()):
        path = docs_dir / source_file.replace("\\", os.sep)
        try:
            with pdfplumber.open(str(path)) as pdf:
                for page_number, text in page_list:
                    record = parse_p40_page(text)
                    if record is None:
                        continue
                    try:
                        columns = extract_header_columns(pdf.pages[page_number - 1])
                    except IndexError:
                        continue
                    records.append({
                        "source_file": source_file,
                        "page_number": page_number,
                        "fiscal_year": record.fiscal_year,
                        "account": record.appropriation_code,
                        "sub_activity": record.sub_activity,
                        "line_item": columns.line_item,
                        "line_item_title": columns.line_item_title,
                        "pe_number": record.pe_number,
                        "amounts": record.amounts,
                    })
        except Exception as exc:  # a single unreadable book must not stop the run
            log.warning("  %s: %s: %s", source_file, type(exc).__name__, str(exc)[:70])
        log.info("  %s -> %d records", Path(source_file).name, len(page_list))
    return records


def _excel_index(conn: sqlite3.Connection) -> tuple[dict, list[str]]:
    """P-1 rows from Excel, keyed by (account, line item, fiscal year).

    Two filters matter here, and both were learned the hard way.

    **Memo rows are excluded.** A line item can carry "Reserve Equip (MEMO NON
    ADD)" and "NATL Guard Equip (MEMO NON ADD)" entries alongside its real
    "Weapon System Cost" row — 1,141 of them in the corpus. They are explicitly
    non-additive. Note that ``add_non_add`` does *not* flag them: it reads
    "Add" on every P-1 row, so the memo status is only visible in
    ``cost_type_title``. Including them made a Javelin line reconcile as 400
    against the PDF's 61,563, when the real Weapon System Cost row is exactly
    61,563.

    **BSA is not part of the key.** The P-40 text carries a BSA for only 66% of
    records (Navy lines print none), and Excel stores it as "" rather than NULL
    in places, so keying on it drops or mismatches rows. It is used to
    disambiguate *within* a key instead, which is where it is actually needed:
    Defense-Wide line item 30 is "Major Equipment" for a dozen agencies.
    """
    amount_cols = [
        row[1] for row in conn.execute("PRAGMA table_info(budget_lines)")
        if row[1].startswith("amount_fy")
    ]
    index: dict[tuple, list] = collections.defaultdict(list)
    conn.row_factory = sqlite3.Row
    query = (
        "SELECT account, sub_activity, line_item, source_fiscal_year, "
        "cost_type_title, "
        + ", ".join(amount_cols)
        + " FROM budget_lines WHERE exhibit_type IN ('p1','p1r') "
        "AND COALESCE(cost_type_title,'') NOT LIKE '%NON ADD%'"
    )
    for row in conn.execute(query):
        key = (
            row["account"],
            _norm(row["line_item"]),
            str(row["source_fiscal_year"]),
        )
        index[key].append(row)
    return index, amount_cols


def reconcile(records: list[dict], db_path: Path) -> dict:
    """Compare each P-40 record with its Excel counterpart."""
    conn = sqlite3.connect(str(db_path))
    excel, amount_cols = _excel_index(conn)

    summary = {
        "records": len(records), "matched": 0, "unmatched": 0,
        "agree": 0, "disagree": 0, "not_comparable": 0,
    }
    disagreements: list[dict] = []

    for record in records:
        fiscal_year = record["fiscal_year"]
        key = (record["account"], _norm(record["line_item"]), fiscal_year)
        rows = excel.get(key)
        if not rows:
            summary["unmatched"] += 1
            continue

        # Narrow by BSA when both sides have one. Defense-Wide line item 30 is
        # "Major Equipment" for many agencies, distinguished only by their
        # budget sub-activity; without this they would be summed together.
        pdf_bsa = _norm(record["sub_activity"])
        if pdf_bsa is not None:
            narrowed = [r for r in rows if _norm(r["sub_activity"]) == pdf_bsa]
            if narrowed:
                rows = narrowed
        summary["matched"] += 1

        pdf_value = record["amounts"].get(f"fy{fiscal_year}_total")
        if pdf_value is None:
            pdf_value = record["amounts"].get(f"fy{fiscal_year}_base")

        excel_value = None
        for suffix in ("total", "request", "enacted", "actual"):
            column = f"amount_fy{fiscal_year}_{suffix}"
            if column not in amount_cols:
                continue
            values = [r[column] for r in rows if r[column] is not None]
            if values:
                excel_value = sum(values)
                break

        if pdf_value is None or not excel_value:
            summary["not_comparable"] += 1
            continue

        delta_pct = (pdf_value - excel_value) / abs(excel_value) * 100
        if abs(delta_pct) <= AGREEMENT_TOLERANCE_PCT:
            summary["agree"] += 1
        else:
            summary["disagree"] += 1
            disagreements.append({
                "key": key, "pdf": pdf_value, "excel": excel_value,
                "delta_pct": delta_pct, "title": record["line_item_title"],
            })

    conn.close()
    summary["disagreements"] = sorted(
        disagreements, key=lambda d: -abs(d["delta_pct"])
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="dod_budget.sqlite")
    parser.add_argument("--docs", default="DoD_Budget_Documents")
    parser.add_argument("--cache", default="logs/p40_records.json",
                        help="Where extracted records are cached")
    parser.add_argument("--reuse-cache", action="store_true",
                        help="Skip extraction and read the cache")
    args = parser.parse_args(argv)

    cache = Path(args.cache)
    if args.reuse_cache and cache.exists():
        records = json.loads(cache.read_text(encoding="utf-8"))
        log.info("Loaded %d cached record(s) from %s", len(records), cache)
    else:
        log.info("Extracting P-40 records (re-opens every procurement PDF)...")
        records = extract_records(Path(args.db), Path(args.docs))
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(records), encoding="utf-8")
        log.info("Cached %d record(s) to %s", len(records), cache)

    result = reconcile(records, Path(args.db))
    compared = result["agree"] + result["disagree"]

    log.info("")
    log.info("P-40 records                : %d", result["records"])
    log.info("  matched an Excel P-1 row  : %d", result["matched"])
    log.info("  no Excel counterpart      : %d", result["unmatched"])
    log.info("  compared                  : %d", compared)
    log.info("    agree (within %.0f%%)      : %d", AGREEMENT_TOLERANCE_PCT, result["agree"])
    log.info("    disagree                : %d", result["disagree"])
    log.info("  not comparable            : %d", result["not_comparable"])
    if compared:
        log.info("  agreement rate            : %.1f%%", 100 * result["agree"] / compared)

    log.info("")
    log.info("Largest disagreements:")
    for item in result["disagreements"][:10]:
        log.info("   %8.1f%%  %s  pdf=%,.0f excel=%,.0f  %s".replace(",", ""),
                 item["delta_pct"], item["key"], item["pdf"], item["excel"],
                 str(item["title"])[:30])
    return 0


if __name__ == "__main__":
    sys.exit(main())
