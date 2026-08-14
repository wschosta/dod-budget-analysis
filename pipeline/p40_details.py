"""Persist the P-40 detail that the Excel P-1 rows do not carry.

Reconciling Exhibit P-40 against the Excel P-1 rows produced 89.5% agreement
with structural exceptions — ship lines funded through advance procurement,
and multi-agency line items the PDF cannot always disambiguate. On that
evidence P-40 funding is **not** merged into ``budget_lines``: P-1 stays
authoritative for line-item money, and importing a second opinion would put
ambiguity into totals that currently agree with themselves.

What P-40 has and P-1 does not is still worth keeping:

* the **out-year horizon** — budget year +1 through +4, To Complete, and Total
* **procurement quantities** per year
* the **Code B program element**, which links procurement to RDT&E
* the **line item title** as printed in the justification book

Those live in ``p40_line_details`` / ``p40_line_amounts`` (migration 008),
keyed on ``(account, sub_activity, line_item, fiscal_year)`` so they join to
``budget_lines`` rather than compete with it.

Reading the line item number requires word coordinates: the P-40 header is two
printed columns that ``extract_text()`` flattens together. See
:mod:`pipeline.p40_positional`, which recovers it at 99.0% accuracy against
the Excel line items.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path

from pipeline.p40_parser import parse_p40_page
from pipeline.p40_positional import extract_header_columns

logger = logging.getLogger(__name__)

# Columns whose values are quantities rather than money live in the same rows;
# the amount/quantity split is preserved from the parser.
_PAGE_QUERY = (
    "SELECT source_file, page_number, page_text FROM pdf_pages "
    "WHERE page_exhibit_type = 'p40' AND page_text LIKE '%Resource Summary%' "
    "ORDER BY source_file, page_number"
)


def _rows_for_page(record, columns, source_file: str, page_number: int) -> tuple[tuple, list[tuple]]:
    """Build the detail row and its amount rows for one parsed page."""
    detail = (
        record.appropriation_code,
        record.sub_activity,
        columns.line_item,
        record.fiscal_year,
        columns.line_item_title,
        record.pe_number,
        record.organization,
        source_file,
        page_number,
    )

    labels = set(record.amounts) | set(record.quantities)
    amounts = [
        (
            label,
            record.amounts.get(label),
            record.quantities.get(label),
            1 if label in record.continuing_columns else 0,
        )
        for label in sorted(labels)
    ]
    return detail, amounts


def populate_p40_details(
    db_path: Path,
    docs_dir: Path,
    progress_callback: Callable[[int, int], None] | None = None,
) -> dict:
    """Extract P-40 detail into the p40_* tables.

    Rebuilds both tables: they are derived wholly from ``pdf_pages`` plus the
    source PDFs, so a partial refresh would leave stale rows that nothing
    would ever correct.

    Requires the source PDFs, because the line item number is only recoverable
    from word coordinates. Pages whose line item cannot be read are skipped and
    counted rather than stored with a null key, which would collapse unrelated
    line items onto one row through the UNIQUE constraint.

    Returns a summary dict: pages, details, amounts, skipped_no_line_item.
    """
    import pdfplumber

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    pages: dict[str, list[tuple[int, str]]] = {}
    for row in conn.execute(_PAGE_QUERY):
        pages.setdefault(row["source_file"], []).append(
            (row["page_number"], row["page_text"])
        )

    total_pages = sum(len(v) for v in pages.values())
    logger.info(
        "P-40 detail: %d page(s) across %d book(s)", total_pages, len(pages)
    )

    conn.execute("DELETE FROM p40_line_amounts")
    conn.execute("DELETE FROM p40_line_details")
    conn.commit()

    seen = 0
    stored = 0
    amount_rows = 0
    skipped = 0

    for source_file, page_list in sorted(pages.items()):
        pdf_path = docs_dir / source_file.replace("\\", os.sep)
        try:
            pdf = pdfplumber.open(str(pdf_path))
        except Exception as exc:
            logger.warning(
                "  %s unreadable (%s); %d page(s) skipped",
                source_file, type(exc).__name__, len(page_list),
            )
            skipped += len(page_list)
            continue

        try:
            for page_number, page_text in page_list:
                seen += 1
                if progress_callback and seen % 100 == 0:
                    progress_callback(seen, total_pages)

                record = parse_p40_page(page_text)
                if record is None:
                    continue
                try:
                    columns = extract_header_columns(pdf.pages[page_number - 1])
                except IndexError:
                    skipped += 1
                    continue

                # Without a line item the row has no usable key: the UNIQUE
                # constraint would fold every such page onto one row.
                if not columns.line_item or not record.appropriation_code:
                    skipped += 1
                    continue

                detail, amounts = _rows_for_page(
                    record, columns, source_file, page_number
                )
                cur = conn.execute(
                    "INSERT OR REPLACE INTO p40_line_details "
                    "(account, sub_activity, line_item, fiscal_year, "
                    " line_item_title, pe_number, organization, source_file, "
                    " page_number) VALUES (?,?,?,?,?,?,?,?,?)",
                    detail,
                )
                detail_id = cur.lastrowid
                stored += 1

                if amounts:
                    conn.executemany(
                        "INSERT OR REPLACE INTO p40_line_amounts "
                        "(detail_id, column_label, amount, quantity, is_continuing) "
                        "VALUES (?,?,?,?,?)",
                        [(detail_id, *a) for a in amounts],
                    )
                    amount_rows += len(amounts)
        finally:
            pdf.close()

        conn.commit()

    summary = {
        "pages": seen,
        "details": stored,
        "amounts": amount_rows,
        "skipped_no_line_item": skipped,
    }
    logger.info(
        "P-40 detail: %(details)d line item(s), %(amounts)d amount row(s), "
        "%(skipped_no_line_item)d page(s) skipped", summary
    )
    conn.close()
    return summary
