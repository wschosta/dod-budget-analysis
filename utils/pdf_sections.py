"""
R-2/R-3 narrative section parser (Step 1.B5-c).

Detects and extracts structured section blocks from R-2 and R-3 exhibit PDF
page text.  These exhibits contain narrative justification sections with
recognizable headers that precede free-text descriptions.

The extracted sections can be used for:
  - More targeted FTS5 queries (e.g., searching only "Accomplishments" blocks)
  - Structured presentation in the UI detail panel
  - Quality assessment of PDF extraction coverage

Usage:
    from utils.pdf_sections import parse_narrative_sections, SECTION_PATTERN

    sections = parse_narrative_sections(page_text, exhibit_type="R-2")
    # Returns: [{"header": "Accomplishments/Planned Program", "text": "..."},  ...]
"""

import re
from typing import Optional

from utils.strings import clean_narrative

# ── Section header patterns for R-2 and R-3 exhibits ─────────────────────────
#
# R-2 (RDT&E Program Summary) sections, per the OSD exhibit instructions:
#   - Accomplishments/Planned Program
#   - Other Program Funding Summary
#   - Acquisition Strategy
#   - Performance Metrics
#
# R-3 (RDT&E Project Schedule) sections:
#   - Mission Description
#   - Program Accomplishments/Planned Programs
#   - Major Performers
#   - Project Accomplishments/Planned Programs
#
# We match all-caps or title-case headers at the start of a line.

_R2_HEADERS = [
    r"Accomplishments\s*/\s*Planned\s+Programs?",
    r"Program\s+Accomplishments?\s*/\s*Planned\s+Programs?",
    r"Other\s+Program\s+Funding\s+Summary",
    r"Acquisition\s+Strategy",
    r"Performance\s+Metrics?",
    r"Congressional\s+Add(?:s|itions?)?",
    r"Program\s+Change\s+Summary",
    r"Notes\s*:",
    r"Technical\s+Description",
    r"FY\s*\d{4}\s+Program\s+Justification",
    r"FY\s*\d{4}\s*(?:/\s*\d{4})?\s+Plans?",
    r"FY\s*\d{4}\s+Accomplishments?",
]

_R3_HEADERS = [
    r"Mission\s+Description",
    r"Major\s+Performers?",
    r"Contract\s+Awards?",
    r"Competitive?\s+Prototype\s+Initiative",
    r"Milestones?",
    r"Project\s+Accomplishments?",
    r"Program\s+Accomplishments?",
    r"Development\s+Approach",
    r"Technical\s+Challenges?",
]

# Combined pattern for both R-2 and R-3
_ALL_HEADERS = _R2_HEADERS + _R3_HEADERS

# Build a single compiled pattern: headers can appear at the start of a line,
# possibly with a section number prefix (e.g., "1.", "A.", "a.").
# Allow all-caps or mixed-case. End with optional colon.
_SECTION_PATTERN_STR = (
    r"(?m)"                          # multiline: ^ matches line start
    r"^(?:\s*(?:[A-Za-z0-9]+\.)\s+)?"  # optional prefix like "1. " or "A. "
    r"("                             # capture the header text
    + r"|".join(f"(?:{h})" for h in _ALL_HEADERS)
    + r")"
    r"\s*:?\s*$"                     # optional colon, end of line
)

SECTION_PATTERN = re.compile(_SECTION_PATTERN_STR, re.IGNORECASE)

# Pre-compiled patterns for project boundary lines in R-2 exhibits.
# Order matters: more specific patterns first to avoid greedy matches.
# Previously compiled on every call to detect_project_boundaries().
_PROJECT_BOUNDARY_PATTERNS: list[re.Pattern[str]] = [
    # "Project Number: 1234   Project Title: Advanced Targeting System"
    re.compile(
        r"^[ \t]*Project\s+Number\s*:\s*(\w[\w\-\.]*)"
        r"(?:\s+Project\s+Title\s*:\s*(.+?))?[ \t]*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    # "Project #1234 Advanced Targeting System"
    re.compile(
        r"^[ \t]*Project\s+#\s*(\w[\w\-\.]*)"
        r"(?:\s+(.+?))?[ \t]*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    # "Project 1234: Advanced Targeting System"
    # (must NOT match "Project Number:" — use negative lookahead)
    re.compile(
        r"^[ \t]*Project\s+(?!Number\s*:)(?!#)(\w[\w\-\.]*)\s*:\s*(.+?)[ \t]*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    # "Project: 1234 — Advanced Targeting System" or "Project: 1234 - Title"
    # (must NOT match "Project Number:" — exclude "Number" after colon)
    re.compile(
        r"^[ \t]*Project\s*:\s*(?!Number\b)(\w[\w\-\.]*)"
        r"(?:\s*[—\-–]\s*(.+?))?[ \t]*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    # R-2A DoD format: "671810 / B-52 AEHF INTEGRATION"
    # Project number (4-7 digits) followed by " / " and an UPPERCASE title.
    # Matches the standard DoD R-2A "Accomplishments/Planned Programs" table
    # where each project appears as "NNNNNN / PROJECT TITLE" on its own line.
    # Title must start with an uppercase letter to exclude numeric ratios
    # like "2024 / 2025" or monetary amounts.
    re.compile(
        r"^[ \t]*(\d{4,7})\s*/\s*([A-Z][A-Z0-9 \-&,()/.]{3,})[ \t]*$",
        re.MULTILINE,
    ),
    # R-2A page-header format: "PE XXXXXXX / PE Title  NNNNNN / Project Title"
    # (appears as page-break artifact in pe_descriptions before cleanup).
    # Captures the project number that trails the PE identifier on this header line.
    re.compile(
        r"PE\s+\w+\s*/\s*[^\n]+?\s+(\d{4,7})\s*/\s*([^\n]+?)[ \t]*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    # Older DoD format: "NNNNNN: Project Title" (pre-2012 R-2A exhibits)
    # e.g. "675144: Global Hawk"
    re.compile(
        r"^[ \t]*(\d{4,7})\s*:\s*([A-Z][A-Z0-9 \-&,()/.]{3,})[ \t]*$",
        re.MULTILINE,
    ),
]

# Document label words that Pattern 3 incorrectly captures as project numbers.
JUNK_PROJECT_LABELS = frozenset({
    "TITLE", "SUBTITLE", "NUMBER", "ELEMENT", "DESCRIPTION",
    "NAME", "CODE", "NONE", "N/A",
})


def is_valid_project_number(proj_num: str) -> bool:
    """Return True if *proj_num* looks like a real DoD project identifier.

    Rejects common false positives from Pattern 3:
    - Document header labels ("TITLE", "ELEMENT", etc.)
    - Single-digit list indices ("1", "2", ...)
    - Lowercase English words ("are", "funds", "supports")
    - Single characters
    """
    if len(proj_num) < 2:
        return False
    if proj_num.upper() in JUNK_PROJECT_LABELS:
        return False
    if proj_num.isdigit() and len(proj_num) <= 2:
        return False
    if proj_num.islower():
        return False
    return True


def parse_narrative_sections(
    page_text: str,
    exhibit_type: Optional[str] = None,
    min_section_len: int = 20,
) -> list[dict[str, str]]:
    """Parse narrative sections from a PDF page text string.

    Splits the page text at recognized R-2/R-3 section headers and returns
    a list of ``{"header": ..., "text": ...}`` dicts.

    Args:
        page_text: Raw extracted text from a single PDF page.
        exhibit_type: Optional hint ("R-2", "R-3", etc.) — currently unused,
            retained for future per-exhibit filtering.
        min_section_len: Minimum length (in characters) for a section body
            to be included in the output.

    Returns:
        List of dicts: [{"header": "Accomplishments/Planned Program",
                         "text": "In FY2024, the program completed..."}, ...]
        Empty list if no recognized headers are found.
    """
    if not page_text:
        return []

    sections: list[dict[str, str]] = []
    last_header: Optional[str] = None
    last_header_end = 0

    for match in SECTION_PATTERN.finditer(page_text):
        # Save the text accumulated since the previous header
        if last_header is not None:
            body = page_text[last_header_end:match.start()].strip()
            if len(body) >= min_section_len:
                sections.append({"header": last_header, "text": body})

        last_header = match.group(1).strip()
        last_header_end = match.end()

    # Capture the final section after the last match
    if last_header is not None:
        body = page_text[last_header_end:].strip()
        if len(body) >= min_section_len:
            sections.append({"header": last_header, "text": body})

    return sections


# ── Exhibit page header patterns for strip_exhibit_headers() ─────────────────
#
# Budget exhibit PDFs (R-1, P-40, etc.) have page headers/banners that the
# enricher Phase 2 fallback path incorrectly stores as description text.
# These patterns match the header blocks so they can be stripped.

# UNCLASSIFIED line, including common OCR split variants
_UNCLASS_LINE = re.compile(
    r"^\s*(?:UN\s?CLA\s?SSI\s?FIED|UNCLASSIFIED)\s*$", re.MULTILINE | re.IGNORECASE
)

# R-1 exhibit header block: "Department of the <service>" + "Exhibit R-1" or
# "R D T & E Program" through a dashed separator line and column headers.
# These are full summary table pages with no real narrative content.
_R1_EXHIBIT_BLOCK = re.compile(
    r"Department\s+of\s+the\s+(?:Army|Navy|Air\s*Force|Defense)\b"
    r".*?"                            # header continuation
    r"(?:Exhibit\s+R-1|R\s+D\s+T\s*&?\s*E\s+Program)"
    r".*?"                            # more header text
    r"(?=\n\s*\d+\s+\d{7}|\Z)",      # stop before first table data row or end
    re.DOTALL | re.IGNORECASE,
)

# Budget Item Justification header (P-40 / R-2 pages): from CLASSIFICATION or
# BUDGET ITEM JUSTIFICATION through COST/QUANTITY lines and dollar amounts.
# Also matches "FY XXXX RDT&E,N BUDGET ITEM JUSTIFICATION SHEET" variant.
_BUDGET_JUSTIFICATION_HEADER = re.compile(
    r"(?:"
    r"CLASSIFICATION\s*:?\s*\n"                  # P-40 variant
    r"|BUDGET\s+ITEM\s+JUSTIFICATION"            # Standard
    r"|FY\s*\d{4}(?:/\d{4})?\s+RDT&E[,\s]\w+\s+BUDGET\s+ITEM"  # Navy RDT&E variant
    r")"
    r".*?"                                       # header content
    r"(?:"
    r"(?:COST|QUANTITY)\s*\n"                    # COST or QUANTITY line
    r"(?:\s*\(.*?\)\s*\n)??"                     # optional "(In Millions)"
    r"(?:\s*\$[\d,.\s$]+\n)?"                    # optional dollar amounts line
    r"|(?=DESCRIPTION\s*:)"                      # or stop before DESCRIPTION:
    r"|(?=\n[A-Z][a-z]{3,})"                     # or stop before mixed-case paragraph
    r")",
    re.DOTALL | re.IGNORECASE,
)

# Exhibit type and date header lines from P-40 / R-2 pages
_EXHIBIT_DATE_LINE = re.compile(
    r"^\s*(?:"
    r"(?:APPROP\s+CODE|APPROPRIATION)[/\s].*"    # Appropriation lines
    r"|P-\d+\s*(?:FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|JAN).*"  # P-40 date
    r"|(?:FEBRUARY|MARCH|APRIL|MAY|JUNE|JULY|AUGUST|SEPTEMBER|OCTOBER|NOVEMBER|DECEMBER|JANUARY)\s+\d{4}"
    r"|DATE\s*:?\s*$"                            # standalone DATE line
    r"|RDT&E\s+BUDGET\s+ITEM\s+JUSTIFICATION\s+SHEET.*"
    r"|BUDGET\s+ACTIVITY\s*:.*"                  # Budget activity lines
    r"|PROGRAM\s+ELEMENT\s*:.*"                  # PE identifier lines
    r"|PROGRAM\s+ELEMENT\s+TITLE\s*:.*"          # PE title lines
    r"|PROJECT\s+NUMBER\s*:\s*$"                  # Standalone "PROJECT NUMBER:" label only
    r"|PROGRAM\s+ELEMENT\s+DESCRIPTIVE\s+SUMMARIES"
    r"|INTRODUCTION\s+AND\s+EXPLANATION\s+OF\s+CONTENTS"
    r")\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# Dashed separator lines (20+ dashes or equals)
_DASHED_LINE = re.compile(r"^[\s\-=]{20,}$", re.MULTILINE)

# Column header lines: "Thousands of Dollars", "Line Element", "No Number",
# FY year column headers, and lines of "--- ---------" separators
_COLUMN_HEADER_LINE = re.compile(
    r"^\s*(?:"
    r"Thousands\s+of\s+Dollars"
    r"|(?:Program|Line|Element)\s+[-\s]*(?:S|e)?"
    r"|No\s+Number\s+Item"
    r"|(?:---\s+){2,}"
    r")\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# Tabular data lines from R-1 summaries: numbered row with PE number followed
# by title text and optional dollar amounts.
# E.g., "175 0301359A 07 SPECIAL ARMY PROGRAM 35"
_TABLE_DATA_LINE = re.compile(
    r"^\s*\d{1,4}\s+\d{7}[A-Z]{0,3}\s+.*$",
    re.MULTILINE,
)

# Budget activity total / subtotal lines: activity name followed by dollar amounts.
# E.g., "Basic Research 181,722 179,059 198,854 210,349"
# Also: "Total: Management support 1,341,545 1,153,980 ..."
_BUDGET_ACTIVITY_TOTAL = re.compile(
    r"^\s*(?:Total\s*:\s*)?[A-Z][A-Za-z &/\-:]+(?:\d[\d,]+\s+){2,}\d[\d,]+\s*$",
    re.MULTILINE,
)

# OCR double-printed lines: characters duplicated (e.g., "FFCCSS RREECCOONNNNAAIISSSSAANNCCEE")
# These appear when OCR misreads overlapping text from scanned PDFs.
# Requires 3+ consecutive DIFFERENT doubled-letter pairs to avoid false positives.
_OCR_DOUBLED_LINE = re.compile(
    r"^.*?([A-Z])\1(?!\1)([A-Z])\2(?!\2)([A-Z])\3.*$",
    re.MULTILINE,
)

# FY column header line (repeated "FY XXXX" entries on one line)
_FY_COLUMN_LINE = re.compile(
    r"^\s*(?:FY\s*\d{2,4}\s+){2,}.*$", re.MULTILINE | re.IGNORECASE
)

# Page markers: "Page A-1", "Page B-3", "Page 5 of 70"
_PAGE_MARKER_LINE = re.compile(
    r"^\s*Page\s+[A-Z]?-?\d+(?:\s+of\s+\d+)?\s*$", re.MULTILINE | re.IGNORECASE
)

# Standalone COST / QUANTITY / dollar-amount lines left over from P-40 headers
_COST_QUANTITY_LINE = re.compile(
    r"^\s*(?:"
    r"(?:COST|QUANTITY)\s*$"                     # standalone COST / QUANTITY
    r"|\$[\s\d,.$]+$"                            # dollar amounts: "$ $58,422 $18,034"
    r"|\(\s*(?:in|In)\s+(?:Thousands|Millions|thousands|millions)\s*\)"  # "(in thousands)"
    r")\s*$",
    re.MULTILINE,
)

# "FY XXXX/XXXX RDT&E, ARMY/NAVY" header lines from service-specific PDFs
_SERVICE_RDTE_LINE = re.compile(
    r"^\s*FY\s*\d{4}(?:/\d{4})?\s+RDT&E[,\s].*$", re.MULTILINE | re.IGNORECASE
)

_MIN_USEFUL_LENGTH = 25


def strip_exhibit_headers(text: str) -> str:
    """Strip exhibit page headers and table artifacts from PDF text.

    Removes header blocks that appear at the top of budget exhibit pages
    (R-1 summaries, P-40 justification sheets, etc.) that were incorrectly
    stored as description text by the enricher fallback path.

    Also applies :func:`utils.strings.clean_narrative` for R-2A page-break
    artifacts.

    Returns:
        Cleaned text, or empty string if nothing meaningful remains after
        stripping (fewer than 20 characters).
    """
    if not text:
        return ""

    # Apply existing R-2A artifact cleaning first
    text = clean_narrative(text)

    # Strip UNCLASSIFIED lines (standalone or OCR-split)
    text = _UNCLASS_LINE.sub("", text)

    # Strip R-1 exhibit header blocks
    text = _R1_EXHIBIT_BLOCK.sub("", text)

    # Strip Budget Item Justification (P-40) header blocks
    text = _BUDGET_JUSTIFICATION_HEADER.sub("", text)

    # Strip individual header-like lines
    text = _EXHIBIT_DATE_LINE.sub("", text)
    text = _DASHED_LINE.sub("", text)
    text = _COLUMN_HEADER_LINE.sub("", text)
    text = _TABLE_DATA_LINE.sub("", text)
    text = _BUDGET_ACTIVITY_TOTAL.sub("", text)
    text = _FY_COLUMN_LINE.sub("", text)
    text = _PAGE_MARKER_LINE.sub("", text)
    text = _COST_QUANTITY_LINE.sub("", text)
    text = _SERVICE_RDTE_LINE.sub("", text)
    text = _OCR_DOUBLED_LINE.sub("", text)

    # Collapse blank lines and trim
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    if len(text) < _MIN_USEFUL_LENGTH:
        return ""

    return text


def detect_project_boundaries(page_text: str) -> list[dict[str, str]]:
    """Detect project number/title boundaries within R-2 narrative text.

    R-2 exhibits often contain project-level breakdowns within a PE.  These
    appear as lines in several formats::

        Project: 1234 — Advanced Targeting System      (R-2 explicit keyword)
        Project 1234: Advanced Targeting System
        Project Number: 1234   Project Title: Advanced Targeting System
        671810 / B-52 AEHF INTEGRATION                 (R-2A numeric format, modern)
        675144: Global Hawk                             (R-2A numeric format, older)
        PE 0101113F / B-52 Squadrons  671810 / B-52    (R-2A page-header artifact)

    Returns a list of dicts with keys ``project_number``, ``project_title``,
    and ``text`` (the narrative text belonging to that project section).  If no
    project boundaries are detected, returns an empty list.
    """
    if not page_text:
        return []

    # Patterns pre-compiled at module level (see _PROJECT_BOUNDARY_PATTERNS).
    _project_patterns = _PROJECT_BOUNDARY_PATTERNS

    # Collect all project boundary matches with their positions
    boundaries: list[tuple[int, str, str | None]] = []
    for pattern in _project_patterns:
        for m in pattern.finditer(page_text):
            proj_num = m.group(1).strip()
            proj_title = m.group(2).strip() if m.group(2) else None
            boundaries.append((m.start(), proj_num, proj_title))

    if not boundaries:
        return []

    # Filter out junk project numbers before dedup/sorting
    boundaries = [(pos, num, title) for pos, num, title in boundaries
                  if is_valid_project_number(num)]

    if not boundaries:
        return []

    # Sort by position and deduplicate by project number
    boundaries.sort(key=lambda x: x[0])
    seen: set[str] = set()
    unique_boundaries: list[tuple[int, str, str | None]] = []
    for pos, num, title in boundaries:
        if num not in seen:
            seen.add(num)
            unique_boundaries.append((pos, num, title))

    # Extract text between consecutive project boundaries
    projects: list[dict[str, str]] = []
    for i, (pos, proj_num, proj_title) in enumerate(unique_boundaries):
        if i + 1 < len(unique_boundaries):
            text = page_text[pos:unique_boundaries[i + 1][0]].strip()
        else:
            text = page_text[pos:].strip()
        projects.append({
            "project_number": proj_num,
            "project_title": proj_title or "",
            "text": text,
        })

    return projects


def is_narrative_exhibit(exhibit_type: Optional[str]) -> bool:
    """Return True if an exhibit type is known to contain R-2/R-3 narrative blocks."""
    if not exhibit_type:
        return False
    normalized = exhibit_type.upper().replace(" ", "").replace("-", "")
    return normalized in {"R2", "R3", "R2A"}


def extract_sections_for_page(
    page_text: str,
    exhibit_type: Optional[str] = None,
) -> str:
    """Extract narrative sections and return them as a single searchable string.

    Suitable for supplementing the FTS5 index with structured section content.
    Returns a string like::

        [Accomplishments/Planned Program]
        In FY2024, the program completed milestone X...

        [Acquisition Strategy]
        The program uses competitive prototyping...

    Returns empty string if no sections are found.
    """
    sections = parse_narrative_sections(page_text, exhibit_type=exhibit_type)
    if not sections:
        return ""
    parts = []
    for sec in sections:
        parts.append(f"[{sec['header']}]\n{sec['text']}")
    return "\n\n".join(parts)
