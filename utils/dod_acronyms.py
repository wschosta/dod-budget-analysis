"""
Common DoD acronym ↔ expansion lookup table.

Used by the fuzzy matcher to expand user-entered acronyms into their full
forms (and vice versa) before searching budget line text fields.

This is intentionally a small, curated list of acronyms that appear frequently
in DoD budget documents. It is not intended to be exhaustive.
"""

from __future__ import annotations

# Bidirectional mapping: each tuple is (acronym, expanded_form).
# The matcher will search both directions — if the user types the acronym,
# it also searches the expansion, and vice versa.
_ACRONYM_PAIRS: list[tuple[str, str]] = [
    # Weapon systems / platforms
    ("UAV", "unmanned aerial vehicle"),
    ("UAS", "unmanned aircraft system"),
    ("USV", "unmanned surface vehicle"),
    ("UUV", "unmanned underwater vehicle"),
    ("UCAV", "unmanned combat aerial vehicle"),
    ("ICBM", "intercontinental ballistic missile"),
    ("SLBM", "submarine launched ballistic missile"),
    ("ALCM", "air launched cruise missile"),
    ("ASAT", "anti-satellite"),
    ("ABM", "anti-ballistic missile"),
    ("SAM", "surface to air missile"),
    ("THAAD", "terminal high altitude area defense"),
    ("HIMARS", "high mobility artillery rocket system"),
    ("JDAM", "joint direct attack munition"),
    ("JASSM", "joint air to surface standoff missile"),
    ("LRASM", "long range anti-ship missile"),
    ("ARRW", "air launched rapid response weapon"),
    ("HACM", "hypersonic attack cruise missile"),
    ("LRHW", "long range hypersonic weapon"),
    ("C-HGB", "common hypersonic glide body"),
    ("GPI", "glide phase interceptor"),
    ("HBTSS", "hypersonic and ballistic tracking space sensor"),
    ("NGI", "next generation interceptor"),

    # Aircraft
    ("F-35", "joint strike fighter"),
    ("F-22", "raptor"),
    ("B-21", "raider"),
    ("B-2", "spirit"),
    ("KC-46", "pegasus"),
    ("MQ-9", "reaper"),
    ("MQ-25", "stingray"),
    ("CCA", "collaborative combat aircraft"),
    ("NGAD", "next generation air dominance"),

    # Ships
    ("DDG", "destroyer"),
    ("CVN", "aircraft carrier"),
    ("SSN", "attack submarine"),
    ("SSBN", "ballistic missile submarine"),
    ("LCS", "littoral combat ship"),
    ("FFG", "frigate"),

    # Space / satellites
    ("GPS", "global positioning system"),
    ("SBIRS", "space based infrared system"),
    ("OPIR", "overhead persistent infrared"),
    ("SDA", "space development agency"),
    ("NRO", "national reconnaissance office"),

    # C4ISR / electronics
    ("C4ISR", "command control communications computers intelligence surveillance reconnaissance"),
    ("EW", "electronic warfare"),
    ("SIGINT", "signals intelligence"),
    ("ISR", "intelligence surveillance reconnaissance"),
    ("JADC2", "joint all domain command and control"),
    ("ABMS", "advanced battle management system"),
    ("IBCS", "integrated battle command system"),

    # Cyber / AI
    ("AI", "artificial intelligence"),
    ("ML", "machine learning"),
    ("CDAO", "chief digital and artificial intelligence office"),

    # Nuclear
    ("NNSA", "national nuclear security administration"),
    ("GBSD", "ground based strategic deterrent"),
    ("LRSO", "long range standoff weapon"),
    ("NC3", "nuclear command control communications"),

    # Research categories
    ("RDT&E", "research development test evaluation"),
    ("S&T", "science and technology"),
    ("ATD", "advanced technology development"),
    ("SDD", "system development demonstration"),
    ("FYDP", "future years defense program"),

    # Organizations
    ("DARPA", "defense advanced research projects agency"),
    ("MDA", "missile defense agency"),
    ("DISA", "defense information systems agency"),
    ("SOCOM", "special operations command"),
    ("STRATCOM", "strategic command"),
    ("INDOPACOM", "indo pacific command"),
    ("CENTCOM", "central command"),
    ("EUCOM", "european command"),
    ("DLA", "defense logistics agency"),
    ("DTRA", "defense threat reduction agency"),

    # Acquisition / policy
    ("POM", "program objective memorandum"),
    ("PPBE", "planning programming budgeting execution"),
    ("ACAT", "acquisition category"),
    ("MDAP", "major defense acquisition program"),
    ("MTA", "middle tier acquisition"),
    ("DAU", "defense acquisition university"),
    ("JROC", "joint requirements oversight council"),
    ("CDD", "capability development document"),
    ("ICD", "initial capabilities document"),

    # Directed energy / emerging tech
    ("DEW", "directed energy weapon"),
    ("HEL", "high energy laser"),
    ("HPM", "high power microwave"),
    ("EMP", "electromagnetic pulse"),
    ("QIS", "quantum information science"),
    ("5G", "fifth generation wireless"),
    ("CJADC2", "combined joint all domain command and control"),

    # Logistics / sustainment
    ("PBL", "performance based logistics"),
    ("DMS", "diminishing manufacturing sources"),
    ("DMSMS", "diminishing manufacturing sources and material shortages"),
]


def build_acronym_lookup() -> dict[str, list[str]]:
    """Build a bidirectional lookup: term → list of alternative forms.

    Both acronyms and expanded forms are keys. Values are the other direction(s).
    All keys are lowercased for case-insensitive lookup.
    """
    lookup: dict[str, list[str]] = {}
    for acronym, expansion in _ACRONYM_PAIRS:
        acr_lower = acronym.lower()
        exp_lower = expansion.lower()
        lookup.setdefault(acr_lower, []).append(exp_lower)
        lookup.setdefault(exp_lower, []).append(acr_lower)
    return lookup


# Module-level singleton for fast repeated access
ACRONYM_LOOKUP = build_acronym_lookup()
