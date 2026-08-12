"""Parse Exhibit P-40 (Budget Line Item Justification) pages into records.

P-40 is the procurement line-item justification: one line item, its funding
across a twelve-column horizon, and narrative. It is the PDF-side counterpart
to the P-1 rows that arrive via Excel, which makes it the surface where the
two sources can be reconciled against each other.

Three properties of these pages drive the design:

**The financial grid is text, not a table.** pdfplumber reports has_tables=0
for essentially every P-40 page — the Resource Summary is laid out with
whitespace, so it must be parsed from page text. Measured over the corpus the
layout is highly regular: of 1,830 P-40 pages carrying a Resource Summary,
100% expose the exhibit header and the appropriation line, and 1,826 (99.8%)
have a Net Procurement row of exactly twelve values.

**Amounts are in millions.** budget_lines stores thousands. Every value is
scaled by 1,000 on the way out; getting this wrong is a 1000x error that would
look plausible in a chart.

**The header is two columns pdfplumber concatenates.** The line reading
"0300D: Procurement, Defense-Wide / BA 01: Major Equipment / BSA 9: Major"
followed by "20 / Major Equipment, DCSA" is really a left column
(Appropriation / BA / BSA) printed beside a right column (P-1 Line Item Number
/ Title), and the BSA title wraps. The appropriation code, budget activity and
BSA are recoverable from the flattened text; the line item number is not —
see :mod:`pipeline.p40_positional`, which recovers it from word coordinates at
99.0% accuracy against the Excel P-1 rows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Page anchors ─────────────────────────────────────────────────────────────

# "Exhibit P-40, Budget Line Item Justification: PB 2024 <Agency> Date: March 2023"
_EXHIBIT_HEADER = re.compile(
    r"Exhibit\s+P-40[A-Za-z]?[^:]*:\s*PB\s*(?P<fy>\d{4})\s+(?P<org>.+?)\s+Date:",
    re.S,
)

# "0300D: Procurement, Defense-Wide / BA 01: Major Equipment / BSA 9: Major"
_APPROPRIATION = re.compile(
    r"^(?P<code>\d{4}[A-Z]?):\s*(?P<title>.+?)\s*/\s*BA\s*(?P<ba>\d+)\s*:\s*(?P<ba_title>[^/]+)",
    re.M,
)

# "... / BSA 9: Major" — the budget sub-activity number.
#
# This is the discriminator that makes a line item unique. Procurement,
# Defense-Wide line item 30 is "Major Equipment" for a dozen different
# agencies, each with its own P-40 page and its own BSA; joining on
# (account, line_item) alone collapses them together and double-counts. Excel
# carries the same value in budget_lines.sub_activity.
#
# Optional by design: Navy lines of the form "BA 07: <title> / 8081 / <title>"
# carry no BSA segment at all.
_BSA = re.compile(r"/\s*BSA\s*(?P<bsa>[A-Za-z0-9]+)\s*:")

# "Program Elements for Code B Items: 0901220SE"
_CODE_B_PE = re.compile(
    r"Program Elements for Code B Items:\s*(?P<pe>[0-9]{7}[A-Z0-9]{1,3})\b"
)

# Resource Summary rows. The label text is stable across fiscal years; the
# trailing run of values is captured whole and split afterwards.
_ROW_PATTERNS = {
    "quantity": r"^Procurement Quantity \(Units in Each\)\s+(?P<vals>.+)$",
    "gross_cost": r"^Gross/Weapon System Cost \(\$ in Millions\)\s+(?P<vals>.+)$",
    "less_py_advance": r"^Less PY Advance Procurement \(\$ in Millions\)\s+(?P<vals>.+)$",
    "net_procurement": r"^Net Procurement \(P-1\) \(\$ in Millions\)\s+(?P<vals>.+)$",
    "plus_cy_advance": r"^Plus CY Advance Procurement \(\$ in Millions\)\s+(?P<vals>.+)$",
    "total_obligation_authority": r"^Total Obligation Authority \(\$ in Millions\)\s+(?P<vals>.+)$",
}
_ROWS = {k: re.compile(v, re.M) for k, v in _ROW_PATTERNS.items()}

# Everything below this note is explicitly not a budget request.
_INFORMATIONAL_MARKER = "for informational purposes only"

# A cell that carries no number. "Continuing" means the program extends beyond
# the horizon — it is not zero, and must not be recorded as zero.
_NON_NUMERIC = {"-", "--", "N/A", "TBD"}
_CONTINUING = {"Continuing", "Cont", "Continuing."}

# Amounts are printed in millions; the database stores thousands.
_MILLIONS_TO_THOUSANDS = 1000


@dataclass
class P40Record:
    """One P-40 line item as read from a single page."""

    fiscal_year: str
    organization: str | None = None
    appropriation_code: str | None = None
    appropriation_title: str | None = None
    budget_activity: str | None = None
    budget_activity_title: str | None = None
    sub_activity: str | None = None
    pe_number: str | None = None
    # column label -> value in thousands (None where the source printed "-"),
    # keyed by the semantic column name, e.g. "fy2024_base", "prior_years".
    amounts: dict[str, float | None] = field(default_factory=dict)
    quantities: dict[str, float | None] = field(default_factory=dict)
    # Columns whose source cell read "Continuing" rather than a number.
    continuing_columns: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _column_labels(base_fy: int, n_values: int) -> list[str] | None:
    """Semantic name for each Resource Summary column.

    The canonical procurement layout is twelve columns::

        Prior Years | FY b-2 | FY b-1 | FY b Base | FY b OCO | FY b Total
                    | FY b+1 | FY b+2 | FY b+3 | FY b+4 | To Complete | Total

    where *b* is the budget year from the exhibit header. Deriving the labels
    from that header rather than from the printed column titles avoids two
    traps: FY2026 and FY2027 books print "OOC" where earlier books print "OCO",
    and the year captions are split across two physical lines.

    Returns None for a column count this layout does not describe — Navy's SCN
    book, for instance, omits the Base/OCO split. Guessing there would silently
    attribute money to the wrong year.
    """
    if n_values != 12:
        return None
    return [
        "prior_years",
        f"fy{base_fy - 2}",
        f"fy{base_fy - 1}",
        f"fy{base_fy}_base",
        f"fy{base_fy}_oco",
        f"fy{base_fy}_total",
        f"fy{base_fy + 1}",
        f"fy{base_fy + 2}",
        f"fy{base_fy + 3}",
        f"fy{base_fy + 4}",
        "to_complete",
        "total",
    ]


def _parse_cell(token: str) -> tuple[float | None, bool]:
    """Return ``(value, is_continuing)`` for one Resource Summary cell.

    "-" is absent rather than zero; "Continuing" means the program runs past
    the horizon. Both come back as None, with continuing flagged separately so
    a caller can tell "no money" from "money not shown here".
    """
    tok = token.strip()
    if tok in _CONTINUING:
        return None, True
    if tok in _NON_NUMERIC or not tok:
        return None, False
    cleaned = tok.replace(",", "").replace("$", "")
    try:
        return float(cleaned), False
    except ValueError:
        return None, False


def _strip_informational(page_text: str) -> str:
    """Drop the rows below the "informational purposes only" note.

    Initial Spares and the unit-cost rows repeat the Resource Summary shape but
    are documented elsewhere; including them would double-count.
    """
    idx = page_text.find(_INFORMATIONAL_MARKER)
    return page_text if idx == -1 else page_text[:idx]


def parse_p40_page(page_text: str | None) -> P40Record | None:
    """Parse one P-40 page, or return None if it is not a parseable P-40.

    Continuation pages carry the same exhibit header but only narrative — no
    Resource Summary — and yield None rather than an empty record.
    """
    if not page_text:
        return None

    header = _EXHIBIT_HEADER.search(page_text)
    if not header:
        return None
    if "Resource Summary" not in page_text:
        return None  # narrative continuation of a preceding P-40

    base_fy = int(header.group("fy"))
    record = P40Record(
        fiscal_year=str(base_fy),
        organization=" ".join(header.group("org").split()) or None,
    )

    approp = _APPROPRIATION.search(page_text)
    if approp:
        record.appropriation_code = approp.group("code")
        record.appropriation_title = " ".join(approp.group("title").split())
        record.budget_activity = approp.group("ba")
        record.budget_activity_title = " ".join(approp.group("ba_title").split())
    else:
        record.warnings.append("appropriation line not found")

    bsa = _BSA.search(page_text)
    if bsa:
        record.sub_activity = bsa.group("bsa")

    code_b = _CODE_B_PE.search(page_text)
    if code_b:
        record.pe_number = code_b.group("pe")

    body = _strip_informational(page_text)

    # Only two rows are stored: the quantity, and Net Procurement (P-1) —
    # the latter because it is the figure the P-1 exhibit itself carries, and
    # therefore the one that can be reconciled against the Excel P-1 rows.
    # Gross cost and Total Obligation Authority are deliberately not recorded:
    # they differ from Net Procurement by advance-procurement adjustments and
    # mixing them into one column would make the totals incomparable.
    labels: list[str] | None = None
    for name in ("quantity", "net_procurement"):
        match = _ROWS[name].search(body)
        if not match:
            continue
        tokens = match.group("vals").split()

        if labels is None:
            labels = _column_labels(base_fy, len(tokens))
            if labels is None:
                record.warnings.append(
                    f"unrecognised Resource Summary layout ({len(tokens)} columns)"
                )
                return record
        if len(tokens) != len(labels):
            record.warnings.append(
                f"{name}: {len(tokens)} values, expected {len(labels)}"
            )
            continue

        for label, token in zip(labels, tokens):
            value, continuing = _parse_cell(token)
            if continuing and label not in record.continuing_columns:
                record.continuing_columns.append(label)
            if name == "quantity":
                record.quantities[label] = value
            else:
                record.amounts[label] = (
                    None if value is None else value * _MILLIONS_TO_THOUSANDS
                )

    if not record.amounts:
        record.warnings.append("no Net Procurement (P-1) row found")

    return record
