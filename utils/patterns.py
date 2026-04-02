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
