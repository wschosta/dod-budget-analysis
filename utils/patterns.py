"""Pre-compiled regex patterns for DoD budget tools.

All patterns are compiled once at module import for maximum performance.
When patterns are pre-compiled, regex operations are ~5-10% faster because
the engine doesn't have to recompile the pattern for each match/search call.

Usage:
    from utils.patterns import PE_NUMBER, FISCAL_YEAR

    if PE_NUMBER.search(text):
        ...
"""

import re

# File extensions for downloadable budget documents
DOWNLOADABLE_EXTENSIONS = re.compile(r'\.(pdf|xlsx?|xls|zip|csv)$', re.IGNORECASE)

# Program Element (PE) numbers: 7 digits followed by a service suffix.
# Standard suffixes: 1-2 letters (e.g., 0602702E, 0801273F).
# Defense-Wide suffixes: letter-digit-letter (e.g., 0603183D8Z).
# PE_SUFFIX_PATTERN is the raw suffix regex for embedding in larger patterns.
PE_SUFFIX_PATTERN = r'(?:[A-Z]{1,2}|[A-Z]\d[A-Z])'
PE_NUMBER = re.compile(rf'\b\d{{7}}{PE_SUFFIX_PATTERN}\b')

# Anchored variant for validating that an entire string is a PE number
# (no surrounding text allowed). Used by pipeline/db_validator.py.
PE_NUMBER_STRICT = re.compile(rf'^[0-9]{{7}}{PE_SUFFIX_PATTERN}$')

# Case-insensitive anchored variant for matching user-supplied PE numbers
# (e.g. keyword search inputs that may use lowercase letters).
PE_NUMBER_STRICT_CI = re.compile(rf'^[0-9]{{7}}{PE_SUFFIX_PATTERN}$', re.IGNORECASE)

# FTS5 special characters that need escaping in full-text search queries
FTS5_SPECIAL_CHARS = re.compile(r'[\"()*:^+]')

# Fiscal year patterns in various formats
# Matches: "FY2026", "FY 2026", "2026", "FY1998", etc.
FISCAL_YEAR = re.compile(r'(FY\s*)?(?:19|20)\d{2}', re.IGNORECASE)

# Account code and title: "1234 Aircraft Procurement, Air Force"
# Captures the code (group 1) and title (group 2)
ACCOUNT_CODE_TITLE = re.compile(r'^(\d+)\s+(.+)$')

# Whitespace normalization: multiple spaces/tabs/newlines
WHITESPACE = re.compile(r'\s+')

# Currency symbols for stripping during numeric conversion
CURRENCY_SYMBOLS = re.compile(r'[\$€£¥₹₽]')

# Alternate Comptroller Excel files: exhibit stem + 'a' (e.g. r1a.xlsx, p1a.xlsx).
# These contain identical data to the base files and should be excluded.
# Previously duplicated in pipeline/builder.py and scripts/fix_data_quality.py.
ALTERNATE_EXHIBIT_FILE = re.compile(r'^(c1|m1|o1|p1|p1r|r1|rf1)a$', re.IGNORECASE)


# ── Page-level exhibit identification ────────────────────────────────────────
#
# pdf_pages.exhibit_type is derived from the *filename*, so every page of a
# procurement justification book inherits one label.  A single PROC_*.pdf book
# is labelled "p5" end to end while actually containing P-1, P-40, P-5, P-21
# and P-3A pages — measured across the corpus, only 9.3% of the pages in the
# "p5" bucket are genuinely Exhibit P-5.
#
# Justification books print their exhibit in a header line on nearly every
# page ("Exhibit P-40, Budget Line Item Justification: PB 2024 ..."), so the
# page can identify itself.  Two forms occur: the explicit "Exhibit <CODE>"
# header, and bare O&M codes (OP-5, OP-32, PB-24) that appear without the
# word "Exhibit".  The bare form is matched only for a known prefix set —
# matching any letter-digit pair would swallow table content and section
# numbers.
_EXHIBIT_HEADER = r'Exhibit\s+([A-Z]{1,3}-\d{1,3}[A-Za-z]?)'
_BARE_EXHIBIT = r'\b((?:OP|PB|PBA|RF|MYP)-\d{1,3}[A-Za-z]?)\b'

PAGE_EXHIBIT_LABEL = re.compile(
    rf'{_EXHIBIT_HEADER}|{_BARE_EXHIBIT}', re.IGNORECASE
)

# How far into a page to look. The header sits at the top; scanning the whole
# page picks up cross-references in body text ("see Exhibit P-5") and
# mislabels the page.
PAGE_EXHIBIT_SCAN_CHARS = 700


def normalize_exhibit_label(label: str) -> str:
    """Normalise an exhibit code to the corpus convention: lowercase, no hyphen.

    ``"P-40"`` → ``"p40"``, ``"R-2A"`` → ``"r2a"``, matching the existing
    ``exhibit_type`` values (``p1``, ``r2``, ``p1r``, ``rf1``).
    """
    return label.replace("-", "").replace(" ", "").lower()


def classify_page_exhibit(page_text: str | None) -> str | None:
    """Identify a PDF page's exhibit from its own header text.

    Returns the normalised exhibit code, or ``None`` when the page carries no
    exhibit header — tables of contents, narrative continuation pages and
    cover sheets legitimately have none, and guessing at those would be worse
    than admitting the page is unclassified.
    """
    if not page_text:
        return None
    match = PAGE_EXHIBIT_LABEL.search(page_text[:PAGE_EXHIBIT_SCAN_CHARS])
    if not match:
        return None
    return normalize_exhibit_label(match.group(1) or match.group(2))
