"""Shared R-2 COST table parser.

Low-level parser for R-2/R-2A exhibit cost tables found in PDF pages.
Used by both the pipeline build (r2_pdf_extractor) and the keyword
explorer cache builder (keyword_r2).
"""

from __future__ import annotations

import re

from utils.normalization import BA_CANONICAL, infer_ba_from_pe
from utils.patterns import PE_NUMBER as _PE_RE

# Appropriation code extraction (used by parse_r2_cost_table)
_APPROP_RE = re.compile(r"(\d{4}[A-Z]?)\s*[:/]")


# ── Row labels to skip in R-2 cost tables (aggregation/metadata rows) ────────

SKIP_LINE_LABELS: frozenset[str] = frozenset({
    "Total Program Element",
    "Total PE Cost",
    "Total Cost",
    "Total Program Element (PE) Cost",
    "Total Program Element Cost",
})

SKIP_LABEL_PREFIXES: tuple[str, ...] = (
    "# FY",
    "MDAP/MAIS Code",
    "MDAP Code",
    "MAIS Code",
    "Quantity of RDT&E",
    "Other MDAP",
    "Other MAIS",
    "Program MDAP",
)

# ── COST table parsing ───────────────────────────────────────────────────────

# Matches the COST header line in various formats:
# "COST ($ in Millions)", "Cost (in millions)", "$'s in Millions", etc.
_COST_HEADER_RE = re.compile(
    r"(?:COST|Cost|\$['\u2019]s)\s*\(\$?\s*(?:['\u2019]s\s*)?in\s*(Millions?|Thousands?)\)",
    re.IGNORECASE,
)

# FY column labels: "FY 2025", "FY2025", "FY 98", "FY98", or bare "1998"
_FY_4DIGIT_RE = re.compile(r"FY\s*(\d{4})")
_FY_2DIGIT_RE = re.compile(r"FY\s*(\d{2})(?!\d)")
_BARE_YEAR_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")

# Tokens that represent a valid "no value" entry in a cost table column.
# These must be recognized as null amounts (not label text) so the
# right-to-left scanner doesn't stop prematurely.
_NULL_AMOUNT_TOKENS: frozenset[str] = frozenset({
    "-", "--", "TBD", "N/A", "Continuing", "CONTINUING", "Complete", "Cost",
})

# ── Budget Activity and Appropriation from page headers ─────────────────────

# "BUDGET ACTIVITY: 2", "Budget Activity 5: System Dev...", "BA 3 / Advanced..."
_BA_NUMBER_RE = re.compile(
    r"(?:BUDGET\s+ACTIVITY|BA)\s*:?\s*(\d)\s*(?:[:/\-]\s*(.+?))?(?:\n|$)",
    re.IGNORECASE,
)

# "Appropriation: 0400 / Research, Development, Test & Eval, Defense-Wide"
# "Appropriation/Budget Activity: 0400 / ..."
_APPROP_TITLE_RE = re.compile(
    r"Appropriation\s*(?:/[^:]+)?\s*:\s*\d{4}[A-Z]?\s*[:/]\s*(.+?)(?:\n|$)",
    re.IGNORECASE,
)

_HEADER_SCAN_CHARS = 800


def parse_r2_header_metadata(text: str) -> dict[str, str | None]:
    """Extract budget activity and appropriation from R-2 page header text.

    Scans the first *_HEADER_SCAN_CHARS* characters for structured header fields.

    Returns a dict with keys:
        budget_activity: str | None  (e.g., "03")
        budget_activity_title: str | None (e.g., "BA 3: Advanced Technology Development")
        appropriation_title: str | None
    """
    header = text[:_HEADER_SCAN_CHARS]
    result: dict[str, str | None] = {
        "budget_activity": None,
        "budget_activity_title": None,
        "appropriation_title": None,
    }

    m = _BA_NUMBER_RE.search(header)
    if m:
        ba_num = m.group(1).zfill(2)
        result["budget_activity"] = ba_num
        # Prefer canonical title, fall back to what's in the header
        canonical = BA_CANONICAL.get(ba_num)
        if canonical:
            result["budget_activity_title"] = canonical
        elif m.group(2):
            result["budget_activity_title"] = m.group(2).strip()

    m = _APPROP_TITLE_RE.search(header)
    if m:
        result["appropriation_title"] = m.group(1).strip()

    return result


def _parse_amount(token: str) -> float | None:
    """Parse a single amount token, returning None for non-numeric values."""
    token = token.strip().replace(",", "")
    # Strip footnote markers like "19.708*" or "0****"
    token = token.rstrip("*#")
    if not token or token in _NULL_AMOUNT_TOKENS:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def parse_r2_cost_table(
    text: str,
) -> dict | None:
    """Parse an R-2 page's COST table, returning structured data.

    Returns a dict with:
        pe_number: str
        approp_code: str | None
        unit_multiplier: float (1000 for millions, 1 for thousands)
        fy_amounts: dict[str, list[tuple[str, float|None]]]
            Maps row label -> [(fy_year, amount), ...]
    Returns None if the page doesn't contain a parseable COST table.
    """
    # Must contain a COST header
    cost_match = _COST_HEADER_RE.search(text)
    if not cost_match:
        return None

    # Determine unit: millions → multiply by 1000 to get $K
    unit_str = cost_match.group(1).lower()
    unit_multiplier = 1000.0 if "million" in unit_str else 1.0

    # Extract PE number from header area
    pe_match = _PE_RE.search(text[:800])
    if not pe_match:
        return None
    pe_number = pe_match.group(0)

    # Extract appropriation code
    approp_match = _APPROP_RE.search(text[:500])
    approp_code = approp_match.group(1) if approp_match else None

    # Find the COST header line and extract FY columns
    lines = text.split("\n")
    cost_line_idx = None
    for i, line in enumerate(lines):
        if cost_match.group(0) in line:
            cost_line_idx = i
            break

    if cost_line_idx is None:
        return None

    # FY columns may be on the same line as COST or adjacent lines
    fy_header_area = lines[max(0, cost_line_idx - 1)] + " " + lines[cost_line_idx]
    if cost_line_idx + 1 < len(lines):
        fy_header_area += " " + lines[cost_line_idx + 1]

    # Try 4-digit FY first, then 2-digit, then bare years
    fy_labels = _FY_4DIGIT_RE.findall(fy_header_area)
    if not fy_labels:
        # 2-digit: FY 98 → 1998/2098 (heuristic: <50 → 20xx, >=50 → 19xx)
        short = _FY_2DIGIT_RE.findall(fy_header_area)
        if short:
            fy_labels = [f"{'20' if int(y) < 50 else '19'}{y}" for y in short]
    if not fy_labels:
        # Bare 4-digit years (1998, 1999, ...) — filter to plausible FY range
        bare = _BARE_YEAR_RE.findall(fy_header_area)
        fy_labels = [y for y in bare if 1990 <= int(y) <= 2035]
    if not fy_labels:
        return None

    # Parse data rows after the COST header
    fy_amounts: dict[str, list[tuple[str, float | None]]] = {}
    data_start = cost_line_idx + 1
    # Skip continuation lines from the header (e.g., "Complete", "Years FY...")
    while data_start < len(lines):
        stripped = lines[data_start].strip()
        if not stripped:
            data_start += 1
            continue
        # Skip header continuation lines that contain FY labels or "Complete"
        if stripped in ("Complete", "Complete Cost") or stripped.startswith("Years "):
            data_start += 1
            continue
        break

    for i in range(data_start, min(data_start + 20, len(lines))):
        line = lines[i].strip()
        if not line:
            continue
        # Stop at section headers
        if line.startswith(("A.", "B.", "C.", "D.", "E.", "Note", "R-1 Line")):
            break

        tokens = line.split()
        if len(tokens) < 2:
            continue

        amounts: list[float | None] = []
        label_end = len(tokens)
        for j in range(len(tokens) - 1, -1, -1):
            clean_tok = tokens[j].strip().replace(",", "").rstrip("*#")
            if clean_tok in _NULL_AMOUNT_TOKENS:
                amounts.append(None)
                label_end = j
            else:
                parsed = _parse_amount(tokens[j])
                if parsed is not None:
                    amounts.append(parsed)
                    label_end = j
                else:
                    break
        amounts.reverse()

        if not amounts or all(a is None for a in amounts):
            continue

        label = " ".join(tokens[:label_end]).strip()
        if not label:
            continue

        # Skip aggregation/metadata rows (Total PE, MDAP codes, etc.)
        if label in SKIP_LINE_LABELS or label.startswith(SKIP_LABEL_PREFIXES):
            continue

        # Pair amounts with FY labels (amounts may be fewer than FY labels)
        paired = list(zip(fy_labels, amounts))
        if paired:
            fy_amounts[label] = paired

    if not fy_amounts:
        return None

    # Extract budget activity and appropriation title from page header
    header_meta = parse_r2_header_metadata(text)

    # Fall back to PE-number inference if header didn't yield BA
    if not header_meta["budget_activity"]:
        ba_num, ba_title = infer_ba_from_pe(pe_number)
        if ba_num:
            header_meta["budget_activity"] = ba_num
            header_meta["budget_activity_title"] = ba_title

    return {
        "pe_number": pe_number,
        "approp_code": approp_code,
        "unit_multiplier": unit_multiplier,
        "fy_amounts": fy_amounts,
        **header_meta,
    }


