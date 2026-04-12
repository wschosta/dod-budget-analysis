"""Centralized normalization mappings for organization names and appropriation codes.

Previously duplicated across repair_database.py, pipeline/builder.py, and
scripts/fix_data_quality.py.  All consumers should import from this module
to keep the mappings consistent.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Organization name normalization
# ---------------------------------------------------------------------------
# Maps raw codes / abbreviations found in filenames and spreadsheets to
# canonical organization names.  The superset of repair_database._ORG_NORMALIZE
# and pipeline.builder.ORG_MAP.

ORG_NORMALIZE: dict[str, str] = {
    # Single-letter codes (filename-level)
    "A": "Army",
    "N": "Navy",
    "F": "Air Force",
    "S": "Space Force",
    "D": "Defense-Wide",
    "M": "Marine Corps",
    "J": "Joint Staff",
    # Uppercase multi-letter variants
    "ARMY": "Army",
    "AF": "Air Force",
    "NAVY": "Navy",
    "USAF": "Air Force",
    "USN": "Navy",
    "USMC": "Marine Corps",
    "AIR FORCE": "Air Force",
    "MARINE CORPS": "Marine Corps",
    "SPACE FORCE": "Space Force",
    "DEFENSE-WIDE": "Defense-Wide",
    "DEFENSEWIDE": "Defense-Wide",
    "DW": "Defense-Wide",
    # Title-case variants (identity)
    "Army": "Army",
    "Navy": "Navy",
    "Air Force": "Air Force",
    # Defense agencies and field activities
    "SOCOM": "SOCOM",
    "USSOCOM": "SOCOM",
    "DISA": "DISA",
    "DLA": "DLA",
    "MDA": "MDA",
    "DHA": "DHA",
    "NGB": "NGB",
    "DARPA": "DARPA",
    "NSA": "NSA",
    "DIA": "DIA",
    "NRO": "NRO",
    "NGA": "NGA",
    "DTRA": "DTRA",
    "DCSA": "DCSA",
    "WHS": "WHS",
    "DCMA": "DCMA",
    "DFAS": "DFAS",
    "DODEA": "DODEA",
    "DPAA": "DPAA",
    "TJS": "TJS",
    "DSCA": "DSCA",
    "DECA": "DECA",
    "OSD": "OSD",
    "DAU": "DAU",
    "DTIC": "DTIC",
    "DHRA": "DHRA",
    "DLSA": "DLSA",
    "DTSA": "DTSA",
    "OTE": "OTE",
    "CYBER": "CYBER",
    "CMP": "CMP",
    "DEPS": "DEPS",
    "DEPSDDR": "DEPSDDR",
    "DMACT": "DMACT",
    "OLDCC": "OLDCC",
    "CAAF": "CAAF",
    "CBDP": "CBDP",
    "SDA": "SDA",
    "TRANSCOM": "TRANSCOM",
    "TRANS": "TRANSCOM",
    "BTA": "BTA",
    "DEFW": "DEFW",
    "DEFR": "DEFR",
    "OEA": "OEA",
    "UNDD": "UNDD",
    "DPMO": "DPMO",
    "DSS": "DSS",
    "IG": "IG",
    "TMA": "TMA",
    "NDU": "NDU",
}


def normalize_org_name(raw: str) -> str:
    """Normalize an organization name/code to its canonical form.

    Looks up *raw* in :data:`ORG_NORMALIZE`.  Returns the canonical name if
    found, otherwise returns *raw* unchanged.
    """
    return ORG_NORMALIZE.get(raw, raw)


# ---------------------------------------------------------------------------
# Case-insensitive org alias resolution (includes historical renames)
# ---------------------------------------------------------------------------
# Extends ORG_NORMALIZE with lowercase keys and historical agency renames
# (e.g., DSS → DCSA, DHP/TMA → DHA, DPMO → DPAA).
# Previously duplicated in pipeline/validator.py as _ORG_ALIASES.

_ORG_ALIASES_LOWER: dict[str, str] = {
    k.lower(): v for k, v in ORG_NORMALIZE.items()
}
# Historical renames not in ORG_NORMALIZE
_ORG_ALIASES_LOWER.update({
    "dss": "DCSA",
    "dhp": "DHA",
    "tma": "DHA",
    "dpmo": "DPAA",
})


def normalize_org_loose(name: str) -> str:
    """Case-insensitive org normalization with historical alias support.

    Strips whitespace, lower-cases *name*, and resolves via
    :data:`_ORG_ALIASES_LOWER`.  Returns *name* unchanged if no match.
    """
    return _ORG_ALIASES_LOWER.get(name.lower().strip(), name)


# ---------------------------------------------------------------------------
# Appropriation title → code mapping (exact match, highest confidence)
# ---------------------------------------------------------------------------
# Superset of repair_database._TITLE_TO_CODE and
# scripts/fix_data_quality._TITLE_TO_CODE.

TITLE_TO_CODE: dict[str, str] = {
    # Operation & Maintenance
    "Operation & Maintenance, Navy": "O&M",
    "Operation & Maintenance, Army": "O&M",
    "Operation & Maintenance, Air Force": "O&M",
    "Operation & Maintenance, Marine Corps": "O&M",
    "Operation & Maintenance, Space Force": "O&M",
    "Operation & Maintenance, Defense-Wide": "O&M",
    "Operation & Maintenance, Army Natl Guard": "O&M",
    "Operation & Maintenance, Army Reserve": "O&M",
    "Operation & Maintenance, Navy Res": "O&M",
    "Operation & Maintenance, Navy Reserve": "O&M",
    "Operation & Maintenance, AF Reserve": "O&M",
    "Operation & Maintenance, Air Natl Guard": "O&M",
    "Operation & Maintenance, MC Reserve": "O&M",
    "Operation & Maintenance, ARNG": "O&M",
    "Operation & Maintenance, ANG": "O&M",
    "Operational Test & Eval, Defense": "O&M",
    # Defense Health
    "Defense Health Program": "DHP",
    # Military Construction
    "Mil Con, Def-Wide": "MILCON",
    "Mil Con, Army": "MILCON",
    "Mil Con, Navy": "MILCON",
    "Mil Con, Air Force": "MILCON",
    "Mil Con, Army Natl Guard": "MILCON",
    "Mil Con, AF Reserve": "MILCON",
    "Mil Con, Navy Res": "MILCON",
    "Mil Con, Navy Reserve": "MILCON",
    "MilCon, Air Force": "MILCON",
    "MilCon, ANG": "MILCON",
    "MilCon, AF Res": "MILCON",
    "MILCON, Army": "MILCON",
    "MILCON, ARNG": "MILCON",
    "MILCON, Army R": "MILCON",
    # RDT&E
    "RDT&E, Army": "RDTE",
    "RDT&E, Navy": "RDTE",
    "RDT&E, Air Force": "RDTE",
    "RDT&E, Defense-Wide": "RDTE",
    "RDT&E, Space Force": "RDTE",
    "RDTE, Space Force": "RDTE",
    "Research, Development, Test, and Evaluation, Space Force": "RDTE",
    # Procurement
    "Aircraft Procurement, Army": "APAF",
    "Aircraft Procurement, Navy": "APAF",
    "Aircraft Procurement, Air Force": "APAF",
    "Weapons Procurement, Navy": "WPN",
    "Other Procurement, Army": "OPROC",
    "Other Procurement, Navy": "OPROC",
    "Other Procurement, Air Force": "OPROC",
    "Shipbuilding & Conversion, Navy": "SCN",
    "Shipbuilding and Conversion, Navy": "SCN",
    "Procurement of Ammunition, Army": "AMMO",
    "Procurement of Ammunition, Navy/MC": "AMMO",
    "Procurement, Marine Corps": "PROC",
    "Procurement, Defense-Wide": "PROC",
    "Procurement, Space Force": "PROC",
    "Missile Procurement, Army": "MPAF",
    # Family Housing
    "Fam Hsg O&M, DW": "FHSG",
    "Fam Hsg O&M, Army": "FHSG",
    "Fam Hsg O&M, AF": "FHSG",
    "Fam Hsg O&M, N/MC": "FHSG",
    # Revolving / Working Capital
    "Working Capital Fund, Air Force": "RFUND",
    "Working Capital Fund, Defense-Wide": "RFUND",
    "Working Capital Fund, DECA": "RFUND",
    "Working Capital Fund, Army": "RFUND",
    "Working Capital Fund, Navy": "RFUND",
    "National Defense Sealift Fund": "RFUND",
    # Chemical Agents
    "Chem Agents & Munitions Destruction": "CHEM",
}


# ---------------------------------------------------------------------------
# Keyword-based appropriation code detection (substring match, lower priority)
# ---------------------------------------------------------------------------
# Superset of repair_database._APPROPRIATION_KEYWORDS,
# pipeline.builder._APPROPRIATION_KEYWORDS, and
# scripts/fix_data_quality._EXTRA_KEYWORDS.

APPROPRIATION_KEYWORDS: dict[str, str] = {
    # Core keywords (shared across all consumers)
    "aircraft procurement": "APAF",
    "missile procurement": "MPAF",
    "weapons procurement": "WPN",
    "ammunition procurement": "AMMO",
    "other procurement": "OPROC",
    "shipbuilding and conversion": "SCN",
    "shipbuilding & conversion": "SCN",
    "research, development, test & eval": "RDTE",
    "research, development, test and eval": "RDTE",
    "rdt&e": "RDTE",
    "operation and maintenance": "O&M",
    "operations and maintenance": "O&M",
    "operation & maintenance": "O&M",
    "operations & maintenance": "O&M",
    "operational test & eval": "O&M",
    "operational test and eval": "O&M",
    "military personnel": "MILPERS",
    "military construction": "MILCON",
    "mil con": "MILCON",
    "milcon": "MILCON",
    "revolving fund": "RFUND",
    "working capital fund": "RFUND",
    "sealift fund": "RFUND",
    "family housing": "FHSG",
    "fam hsg": "FHSG",
    "national guard and reserve": "NGRE",
    "chemical agents": "CHEM",
    "chem agents": "CHEM",
    "defense production act": "DPA",
    "environmental restoration": "ER",
    "drug interdiction": "DRUG",
    "defense health program": "DHP",
    "defense health": "DHP",
    "brac": "MILCON",
    "procurement": "PROC",
    # Extended keywords (from fix_data_quality)
    "procurement of ammunition": "AMMO",
    "cooperative threat reduction": "O&M",
    "inspector general": "O&M",
    "court of appeals": "O&M",
    "overseas humanitarian": "O&M",
    "acquisition workforce": "O&M",
    "sporting competitions": "O&M",
    "counter isis": "O&M",
    "improvised explosive device": "O&M",
    "afghanistan security": "O&M",
    "lease of dod": "O&M",
    "disposal of dod": "O&M",
    "operational test": "O&M",
}


def parse_appropriation(
    account_title: str | None,
) -> tuple[str | None, str | None]:
    """Split an account title into (appropriation_code, appropriation_title).

    Strategy order:
      1. Exact match against :data:`TITLE_TO_CODE`.
      2. Leading numeric code  (e.g. ``"2035 Aircraft Procurement, Army"``).
      3. Keyword substring match against :data:`APPROPRIATION_KEYWORDS`.

    Returns:
        ``(code, title)`` tuple.  Either or both may be ``None``.
    """
    if not account_title:
        return None, None
    s = str(account_title).strip()
    if not s:
        return None, None

    # Strategy 1: exact title match
    code = TITLE_TO_CODE.get(s)
    if code is not None:
        return code, s

    # Strategy 2: leading numeric code
    parts = s.split(None, 1)
    if len(parts) == 2 and parts[0].isdigit():
        return parts[0], parts[1]

    # Strategy 3: keyword substring match
    lower = s.lower()
    for keyword, code in APPROPRIATION_KEYWORDS.items():
        if keyword in lower:
            return code, s

    return None, s


# ---------------------------------------------------------------------------
# R-2 PDF sub-element title cleanup
# ---------------------------------------------------------------------------
# PDF-mined R-2 titles often contain embedded budget amounts, table
# headers/footers, or variant project codes. These constants and functions
# provide centralized cleanup used by the parser, cache builder, and pipeline.

R2_JUNK_TITLES: frozenset[str] = frozenset({
    "Total",
    "Total PE",
    "Total PE Cost",
    "Total Cost",
    "Total Program Element",
    "Total Program Element Cost",
    "Total Program Element (PE)",
    "Total Program Element (PE) Cost",
    "R-1 SHOPPING LIST - Item No.",
    "R-1 SHOPPING LIST",
})

R2_JUNK_PREFIXES: tuple[str, ...] = (
    "Total ",
    "R-1 ",
    "# FY",
    "MDAP",
    "MAIS",
    "Note:",
    "* ",
    "Quantity of",
    "Project MDAP",
)

# Trailing budget amounts: sequences like "4,439.845 101.694 - *" at end of string.
# Requires .\d{2,3} to distinguish from calibers like "2.75 Inch" mid-title.
_TRAILING_AMOUNTS_RE = re.compile(
    r"(?:\s+(?:[\d,]+\.\d{2,3}|-{1,2}|\*{1,2})\s*)+\s*$"
)

# Project code with E-prefix: E1662 → 1662
_E_PREFIX_CODE_RE = re.compile(r"^[Ee](\d{3,5})$")

# Project code extraction: "1662: Title" or "DD4: Title" or "672987: Title"
# Allow 1-3 letters + 1-6 digits, or just digits, optionally with trailing dot.
_CODE_COLON_RE = re.compile(r"^([A-Za-z]{0,3}\d{1,6})\.?:\s*(.+)")
_CODE_SPACE_RE = re.compile(r"^([A-Za-z]{0,3}\d{1,6})\s+(.+)")


def normalize_r2_project_code(raw_code: str | None) -> str | None:
    """Normalize a project code for dedup grouping.

    Strips E-prefix (E1662 → 1662), P-prefix (P010 → 010), leading zeros,
    and normalizes dash-separated codes (MED-01 → MED01).
    """
    if not raw_code:
        return None
    code = raw_code.strip()
    # Strip E-prefix (E1662 → 1662)
    m = _E_PREFIX_CODE_RE.match(code)
    if m:
        return m.group(1).lstrip("0") or m.group(1)
    if code.startswith(("E", "e")) and code[1:].isdigit():
        return code[1:].lstrip("0") or code[1:]
    # Strip P-prefix on numeric codes (P010 → 010, OSD convention)
    if code.startswith(("P", "p")) and code[1:].isdigit():
        return code[1:].lstrip("0") or code[1:]
    # Normalize dashes in alpha-numeric codes (MED-01 → MED01)
    if "-" in code:
        return code.replace("-", "")
    return raw_code


def clean_r2_title(raw_title: str) -> tuple[str | None, str | None]:
    """Clean a PDF-mined R-2 sub-element title.

    Returns ``(project_code, clean_title)`` or ``(None, None)`` if the
    title is junk (table header/footer/total row). Idempotent.

    Examples::

        >>> clean_r2_title("1662: F/A-18 Improvement 4,439.845 101.694 -")
        ('1662', 'F/A-18 Improvement')
        >>> clean_r2_title("E1662 F/A-18 Improvements")
        ('1662', 'F/A-18 Improvements')
        >>> clean_r2_title("Total PE")
        (None, None)
        >>> clean_r2_title("D549 2.75 Inch Anti-Air TD")
        ('D549', '2.75 Inch Anti-Air TD')
    """
    if not raw_title:
        return None, None

    s = raw_title.strip()
    if not s:
        return None, None

    # Strip trailing budget amounts (anchored to end of string)
    s = _TRAILING_AMOUNTS_RE.sub("", s).strip()
    # Strip trailing asterisks, dashes, parenthetical abbreviations like (GDI) or (MIP)
    s = re.sub(r"\s*\*+\s*$", "", s).strip()
    s = re.sub(r"\s+-\s*$", "", s).strip()
    s = re.sub(r"\s+\([A-Z]{2,6}\)\s*$", "", s).strip()

    if not s:
        return None, None

    # Reject junk titles
    if s in R2_JUNK_TITLES:
        return None, None
    s_stripped = re.sub(r"\s*[\*\-]+\s*$", "", s).strip()
    if s_stripped in R2_JUNK_TITLES:
        return None, None
    if s.startswith(R2_JUNK_PREFIXES):
        return None, None

    # Extract project code
    m = _CODE_COLON_RE.match(s)
    if m:
        code = normalize_r2_project_code(m.group(1))
        title = m.group(2).strip()
        return code, title

    m = _CODE_SPACE_RE.match(s)
    if m:
        code = normalize_r2_project_code(m.group(1))
        title = m.group(2).strip()
        return code, title

    # No code found — return title as-is
    return None, s
