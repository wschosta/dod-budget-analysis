"""Centralized organization name inference from source file paths and page text.

Single source of truth for org mapping — used by the pipeline build
(r2_pdf_extractor), cache builder (keyword_search), and repair scripts.
"""

from __future__ import annotations

import re


# ── Organization from source_file path ───────────────────────────────────────

ORG_FROM_FILE: list[tuple[str, str]] = [
    ("RDTE_OSD", "OSD"),
    ("RDTE_DARPA", "DARPA"),
    ("RDTE_SOCOM", "SOCOM"),
    ("RDTE_MDA", "MDA"),
    ("RDTE_DTRA", "DTRA"),
    ("RDTE_DISA", "DISA"),
    ("RDTE_DLA", "DLA"),
    ("RDTE_DCSA", "DCSA"),
    ("RDTE_DCMA", "DCMA"),
    ("RDTE_DCAA", "DCAA"),
    ("RDTE_DTIC", "DTIC"),
    ("RDTE_DHRA", "DHRA"),
    ("RDTE_DSCA", "DSCA"),
    ("RDTE_CBDP", "CBDP"),
    ("RDTE_CHIPS", "OSD"),
    ("RDTE_CYBERCOM", "CYBER"),
    ("RDTE_OTE", "OSD"),
    ("RDTE_TJS", "TJS"),
    ("Missile_Defense", "MDA"),
    ("DHP", "DHP"),
    ("Joint_Staff", "TJS"),
    ("jcs", "TJS"),
    ("whs", "WHS"),
    ("US_Army", "Army"),
    ("Army", "Army"),
    ("US_Navy", "Navy"),
    ("Navy", "Navy"),
    ("US_Air_Force", "Air Force"),
    ("Air_Force", "Air Force"),
    ("AirForce", "Air Force"),
    ("USMC", "Marine Corps"),
    ("MarineCorps", "Marine Corps"),
    ("Space_Force", "Space Force"),
    ("SpaceForce", "Space Force"),
    # Bare agency codes for older filenames ("DARPA PB09", "CBDP.pdf", etc.)
    ("CBDP", "CBDP"),
    ("DARPA", "DARPA"),
    ("DLA", "DLA"),
    ("DSCA", "DSCA"),
    ("DTIC", "DTIC"),
    ("DTRA", "DTRA"),
    ("DISA", "DISA"),
    ("DHRA", "DHRA"),
    ("DCSA", "DCSA"),
    ("DCMA", "DCMA"),
    ("DCAA", "DCAA"),
    ("OSD", "OSD"),
    ("SDA", "SDA"),
    ("mda", "MDA"),
    ("volume", "OSD"),  # older "volumeN" files
]

# ── Agency name extraction from page text (fallback for org inference) ────────

# Modern R-2 exhibit headers: "PB 2024 <Agency Name> Date: ..."
R2_AGENCY_RE = re.compile(
    r"(?:PBR?|FY)\s+\d{4}\s+(.+?)\s+Date:", re.IGNORECASE
)

# Older R-2 headers: "<AGENCY> RDT&E BUDGET ITEM JUSTIFICATION"
OLDER_AGENCY_RE = re.compile(
    r"^(?:UNCLASSIFIED\s+)?(\w[\w\s&,]+?)\s+RDT&E\s+BUDGET\s+ITEM",
    re.IGNORECASE | re.MULTILINE,
)

# Trailing text sometimes captured as part of agency name by R2_AGENCY_RE
STRIP_JUSTIFICATION_RE = re.compile(
    r"\s+RDT&E\s+Budget\s+Item\s+Justification$", re.IGNORECASE
)

# Map agency full names (from R-2 headers) to standardized org codes.
# Keys are uppercase for case-insensitive lookup.
AGENCY_NAME_MAP: dict[str, str] = {
    "OFFICE OF SECRETARY OF DEFENSE": "OSD",
    "OFFICE OF THE SECRETARY OF DEFENSE": "OSD",
    "DEFENSE CONTRACT AUDIT AGENCY": "DCAA",
    "DEFENSE CONTRACT MANAGEMENT AGENCY": "DCMA",
    "DEFENSE COUNTERINTELLIGENCE AND SECURITY AGENCY": "DCSA",
    "DEFENSE INFORMATION SYSTEMS AGENCY": "DISA",
    "DEFENSE LOGISTICS AGENCY": "DLA",
    "DEFENSE SECURITY COOPERATION AGENCY": "DSCA",
    "DEFENSE SECURITY SERVICE": "DCSA",  # renamed to DCSA
    "DEFENSE TECHNICAL INFORMATION CENTER": "DTIC",
    "DEFENSE THREAT REDUCTION AGENCY": "DTRA",
    "DOD HUMAN RESOURCES ACTIVITY": "DHRA",
    "THE JOINT STAFF": "TJS",
    "UNITED STATES SPECIAL OPERATIONS COMMAND": "SOCOM",
    "CHEMICAL AND BIOLOGICAL DEFENSE PROGRAM": "CBDP",
    "WASHINGTON HEADQUARTERS SERVICE": "WHS",
    "WASHINGTON HEADQUARTERS SERVICES": "WHS",
    "OPERATIONAL TEST AND EVALUATION, DEFENSE": "OSD",
    "DEFENSE BUSINESS TRANSFORMATION AGENCY": "OSD",
    "MISSILE DEFENSE AGENCY": "MDA",
    "BALLISTIC MISSILE DEFENSE ORGANIZATION": "MDA",
    "DEFENSE ADVANCED RESEARCH PROJECTS AGENCY": "DARPA",
    "DEFENSE HEALTH PROGRAM": "DHP",
    "UNITED STATES CYBER COMMAND": "CYBER",
    "SPACE DEVELOPMENT AGENCY": "SDA",
    # Older header prefixes (from OLDER_AGENCY_RE)
    "BMDO": "MDA",
    "DARPA": "DARPA",
}

# Substring patterns for cases where the full name doesn't match the map.
# Checked case-insensitively against the first 500 chars of page text.
DEPT_FROM_TEXT: list[tuple[str, str]] = [
    ("DEPARTMENT OF THE ARMY", "Army"),
    ("DEPARTMENT OF THE NAVY", "Navy"),
    ("DEPARTMENT OF THE AIR FORCE", "Air Force"),
    ("DEFENSE ADVANCED RESEARCH", "DARPA"),
    ("SPECIAL OPERATIONS COMMAND", "SOCOM"),
    ("DEFENSE THREAT REDUCTION", "DTRA"),
    ("DEFENSE INFORMATION SYSTEMS", "DISA"),
    ("DEFENSE LOGISTICS AGENCY", "DLA"),
    ("DEFENSE HEALTH", "DHP"),
    ("MISSILE DEFENSE", "MDA"),
]


def infer_org(source_file: str, page_text: str | None = None) -> str | None:
    """Infer organization name from source_file path or page header text.

    Tries filename patterns first (fast, high confidence), then falls back
    to scanning the first 500 characters of page text for department names.
    """
    source_lower = source_file.lower()
    for fragment, org in ORG_FROM_FILE:
        if fragment.lower() in source_lower:
            return org

    if not page_text:
        return None

    header = page_text[:500]

    # Try R-2 exhibit header: "PB 2024 <Agency Name> Date: ..."
    m = R2_AGENCY_RE.search(header)
    if m:
        agency = STRIP_JUSTIFICATION_RE.sub("", m.group(1).strip())
        mapped = AGENCY_NAME_MAP.get(agency.upper())
        if mapped:
            return mapped

    # Try older header: "<AGENCY> RDT&E BUDGET ITEM JUSTIFICATION"
    m = OLDER_AGENCY_RE.search(header)
    if m:
        prefix = m.group(1).strip().upper()
        mapped = AGENCY_NAME_MAP.get(prefix)
        if mapped:
            return mapped

    # Last resort: substring scan for department names
    header_upper = header.upper()
    for phrase, org in DEPT_FROM_TEXT:
        if phrase in header_upper:
            return org

    return None
