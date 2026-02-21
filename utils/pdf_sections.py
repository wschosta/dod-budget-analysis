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


def detect_project_boundaries(page_text: str) -> list[dict[str, str]]:
    """Detect project number/title boundaries within R-2 narrative text.

    R-2 exhibits often contain project-level breakdowns within a PE.  These
    appear as lines like::

        Project: 1234 — Advanced Targeting System
        Project 1234: Advanced Targeting System
        Project Number: 1234   Project Title: Advanced Targeting System

    Returns a list of dicts with keys ``project_number``, ``project_title``,
    and ``text`` (the narrative text belonging to that project section).  If no
    project boundaries are detected, returns an empty list.
    """
    if not page_text:
        return []

    # Patterns for project boundary lines in R-2 exhibits.
    # Order matters: more specific patterns first to avoid greedy matches.
    _project_patterns = [
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
    ]

    # Collect all project boundary matches with their positions
    boundaries: list[tuple[int, str, str | None]] = []
    for pattern in _project_patterns:
        for m in pattern.finditer(page_text):
            proj_num = m.group(1).strip()
            proj_title = m.group(2).strip() if m.group(2) else None
            boundaries.append((m.start(), proj_num, proj_title))

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
