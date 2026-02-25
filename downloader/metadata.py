"""
Download Metadata Enrichment

Pure functions to detect exhibit type, category, budget cycle, and service/org
from information available at download time (filename, URL, source label).

These mirror logic in pipeline/builder.py but are kept separate to avoid
importing heavy pipeline dependencies into the downloader module.
"""

from __future__ import annotations

import re


# ── Exhibit type constants (duplicated from builder to avoid heavy import) ──

_EXHIBIT_TYPES = {
    "m1":  "Military Personnel (M-1)",
    "o1":  "Operation & Maintenance (O-1)",
    "p1r": "Procurement (P-1R Reserves)",
    "p1":  "Procurement (P-1)",
    "r1":  "RDT&E (R-1)",
    "rf1": "Revolving Funds (RF-1)",
    "c1":  "Military Construction (C-1)",
    "p5":  "Procurement Detail (P-5)",
    "r2":  "RDT&E PE Detail (R-2)",
    "r3":  "RDT&E Project Schedule (R-3)",
    "r4":  "RDT&E Budget Item Justification (R-4)",
    # Special / non-standard exhibit types (long names safe for substring matching)
    "ogsi":         "Overseas/Global Security & Intelligence (OGSI)",
    "supplemental": "Supplemental Budget Request",
    "amendment":    "Budget Amendment / Update",
}

SUMMARY_EXHIBIT_KEYS = frozenset({
    "p1", "r1", "o1", "m1", "c1", "rf1", "p1r",
    "ogsi", "supplemental", "amendment",
})
DETAIL_EXHIBIT_KEYS = frozenset({"p5", "r2", "r3", "r4"})

# Short exhibit type keys that are summary-level but too short for safe
# substring matching in filenames (e.g. "oco" is a substring of "socom").
_SHORT_SUMMARY_KEYS = frozenset({"oco", "enl", "toa"})

# Navy/DoN appropriation justification book → exhibit type mapping.
# Mirrors NAVY_APPROPRIATION_TO_EXHIBIT in pipeline.builder (kept separate to
# avoid importing the heavy pipeline module into the downloader).
_NAVY_APPROPRIATION_TO_EXHIBIT: dict[str, str] = {
    "apn": "p5", "wpn": "p5", "scn": "p5", "opn": "p5", "pmc": "p5", "panmc": "p5",
    "omn": "o1", "ommc": "o1", "omnr": "o1", "ommcr": "o1", "nwcf": "o1",
    "mpn": "m1", "mpmc": "m1", "rpn": "m1", "rpmc": "m1",
    "rdten": "r2",
    "mcon": "c1", "mcnr": "c1", "brac": "c1",
}

# Source label → normalized service name
_SOURCE_SERVICE_MAP = {
    "us army": "Army",
    "army": "Army",
    "us navy": "Navy",
    "navy": "Navy",
    "navy-archive": "Navy",
    "us air force": "Air Force",
    "air force": "Air Force",
    "airforce": "Air Force",
    "us marine corps": "Marine Corps",
    "marine corps": "Marine Corps",
    "space force": "Space Force",
    "defense-wide": "Defense-Wide",
    "comptroller": "Comptroller",
    "socom": "SOCOM",
    "disa": "DISA",
    "dla": "DLA",
    "mda": "MDA",
    "dha": "DHA",
    "darpa": "DARPA",
}

# Keyword-based exhibit type patterns for Tier 3 detection.
# Catches Comptroller/special files that don't match standard exhibit codes
# or Navy abbreviations. Must stay in sync with _KEYWORD_EXHIBIT_PATTERNS
# in pipeline/builder.py.
_KEYWORD_EXHIBIT_PATTERNS: list[tuple[str, str]] = [
    ("budget_amendment", "amendment"),
    ("amendment_update", "amendment"),
    ("amendment", "amendment"),
    ("overseas_contingency", "oco"),
    ("_oco_", "oco"),
    ("oco_", "oco"),
    ("_oco", "oco"),
    ("ogsi", "ogsi"),
    ("supplemental", "supplemental"),
    ("_toa_", "toa"),
    ("toa_summary", "toa"),
    ("_enl_", "enl"),
    ("enl_summary", "enl"),
]

# Budget cycle detection patterns
_CYCLE_PATTERNS = [
    (re.compile(r"\benacted\b", re.I), "enacted"),
    (re.compile(r"\bndaa\b", re.I), "ndaa"),
    (re.compile(r"\bsupplemental\b", re.I), "supplemental"),
    (re.compile(r"\bamendment\b", re.I), "amendment"),
    (re.compile(r"\bappropriation\b", re.I), "appropriation"),
    (re.compile(r"\b(president|pb|budget)\b", re.I), "pb"),
]


def detect_exhibit_type_from_filename(filename: str) -> str:
    """Detect the exhibit type from a filename.

    Uses a four-tier strategy mirroring pipeline.builder._detect_exhibit_type():
    1. Standard exhibit codes (p1, r2, …).
    2. Appropriation book abbreviations (apn→p5, rdten→r2, proc_*→p5).
    3. Keyword-based detection (oco, supplemental, amendment, …).
    4. Fallback to ``"unknown"``.

    All matching is case-insensitive.

    Args:
        filename: The filename (not full path), e.g. "p1_display.xlsx".

    Returns:
        Exhibit type key like "p1", "r2", etc., or "unknown".
    """
    name = filename.lower().replace("_display", "").replace(".xlsx", "").replace(".pdf", "")
    # Tier 1: standard exhibit type codes (longest first so "p1r" matches before "p1")
    for key in sorted(_EXHIBIT_TYPES.keys(), key=len, reverse=True):
        if key in name:
            return key
    # Tier 2: Navy appropriation book abbreviations
    for abbr, etype in sorted(
        _NAVY_APPROPRIATION_TO_EXHIBIT.items(), key=lambda x: len(x[0]), reverse=True
    ):
        if abbr in name:
            return etype
    # Tier 2b: Defense-Wide PROC_{agency} files → p5
    if name.startswith("proc_"):
        return "p5"
    # Tier 3: keyword-based detection for Comptroller/special files
    for keyword, etype in _KEYWORD_EXHIBIT_PATTERNS:
        if keyword in name:
            return etype
    return "unknown"


def classify_exhibit_category(exhibit_type: str) -> str:
    """Classify an exhibit type as summary, detail, or other.

    Args:
        exhibit_type: Exhibit type key like "p1", "r2", or "unknown".

    Returns:
        "summary", "detail", or "other".
    """
    et = exhibit_type.lower()
    if et in SUMMARY_EXHIBIT_KEYS or et in _SHORT_SUMMARY_KEYS:
        return "summary"
    if et in DETAIL_EXHIBIT_KEYS:
        return "detail"
    return "other"


def detect_budget_cycle(
    source_label: str,
    url: str = "",
    link_text: str = "",
) -> str:
    """Detect the budget cycle from source context.

    Checks URL path and link text for keywords indicating enacted,
    NDAA, supplemental, etc. Defaults to "pb" (President's Budget).

    Args:
        source_label: The source label, e.g. "US Army".
        url: The download URL.
        link_text: The link text from the page.

    Returns:
        Budget cycle string: "pb", "enacted", "ndaa", "supplemental",
        "amendment", or "appropriation".
    """
    combined = f"{url} {link_text} {source_label}"
    for pattern, cycle in _CYCLE_PATTERNS:
        if pattern.search(combined):
            return cycle
    return "pb"


def map_source_to_service(
    source_label: str,
    filename: str = "",
) -> str | None:
    """Map a download source label to a normalized service/org name.

    Checks the source label first, then falls back to filename prefix
    detection (Comptroller files use single-letter prefixes like
    "ap1_display.xlsx" → Army).

    Args:
        source_label: The source label from the downloader,
            e.g. "US Army", "Comptroller".
        filename: The filename, used for Comptroller prefix detection.

    Returns:
        Normalized service name like "Army", "Navy", etc., or None
        if unrecognizable.
    """
    # Try source label first
    label_lower = source_label.lower().strip()
    service = _SOURCE_SERVICE_MAP.get(label_lower)
    if service and service != "Comptroller":
        return service

    # For Comptroller sources, try to detect from filename prefix
    if label_lower == "comptroller" and filename:
        return _detect_service_from_comptroller_filename(filename)

    return service  # "Comptroller" or None


def _detect_service_from_comptroller_filename(filename: str) -> str | None:
    """Detect service from a Comptroller-source filename.

    Comptroller files use single-letter prefixes:
    ap1_display.xlsx → Army (A), np1_display.xlsx → Navy (N), etc.

    Returns:
        Normalized service name or "Comptroller" as fallback.
    """
    name = filename.lower()
    # Single-letter prefix mapping
    _prefix_map = {
        "a": "Army",
        "n": "Navy",
        "f": "Air Force",
        "s": "Space Force",
        "d": "Defense-Wide",
        "m": "Marine Corps",
        "j": "Joint Staff",
    }

    # Check for single-letter prefix before exhibit type pattern
    # e.g., "ap1_" or "nr2_" or "fp5_"
    match = re.match(r"^([a-z])(?:p1|p1r|p5|r[1-4]|o1|m1|c1|rf1)", name)
    if match:
        prefix = match.group(1)
        return _prefix_map.get(prefix, "Comptroller")

    return "Comptroller"


def extract_fy_from_filename(filename: str) -> str | None:
    """Extract a four-digit fiscal year from a filename.

    Looks for patterns like ``FY2026``, ``fy2026``, ``FY_2026``, or bare
    ``2026`` in filenames such as ``FY2026_Budget_Request.pdf`` or
    ``p1_display.xlsx``.

    Returns:
        Four-digit year string (e.g. "2026") if found, else None.
    """
    # Try explicit FY prefix first (most reliable).
    # Use (?=\D|$) instead of \b because \b fails between digits and underscores
    # (both are word characters), e.g. "FY2026_Budget_Request.pdf".
    m = re.search(r"\bFY[_\s-]?(\d{4})(?=\D|$)", filename, re.IGNORECASE)
    if m:
        return m.group(1)
    # Fallback: bare 4-digit year in a reasonable range
    m = re.search(r"(?:^|\D)(19\d{2}|20[0-4]\d)(?=\D|$)", filename)
    if m:
        return m.group(1)
    return None


def validate_fy_match(filename: str, expected_year: str) -> bool:
    """Check whether a filename's embedded FY matches the expected year.

    Returns True if either:
    - The filename contains no detectable FY (benefit of the doubt), or
    - The detected FY matches expected_year.

    Returns False if the filename clearly belongs to a different FY.
    """
    detected = extract_fy_from_filename(filename)
    if detected is None:
        return True  # No FY in filename — can't reject
    return detected == expected_year


def enrich_file_metadata(
    filename: str,
    url: str = "",
    source_label: str = "",
    link_text: str = "",
) -> dict[str, str | None]:
    """Compute all metadata fields for a single file.

    Convenience function that calls all detection functions and returns
    a dict suitable for inclusion in a manifest entry.

    Returns:
        Dict with keys: exhibit_type, exhibit_category, budget_cycle,
        service_org, link_text.
    """
    exhibit_type = detect_exhibit_type_from_filename(filename)
    return {
        "exhibit_type": exhibit_type,
        "exhibit_category": classify_exhibit_category(exhibit_type),
        "budget_cycle": detect_budget_cycle(source_label, url, link_text),
        "service_org": map_source_to_service(source_label, filename),
        "link_text": link_text or "",
    }
