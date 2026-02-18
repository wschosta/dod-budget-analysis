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

# Program Element (PE) numbers: 7 digits followed by 1-2 letters
# Examples: 0602702E, 0801273F
PE_NUMBER = re.compile(r'\b\d{7}[A-Z]{1,2}\b')

# FTS5 special characters that need escaping in full-text search queries
FTS5_SPECIAL_CHARS = re.compile(r'[\"()*:^+]')

# Fiscal year patterns in various formats
# Matches: "FY2026", "FY 2026", "2026", etc.
FISCAL_YEAR = re.compile(r'(FY\s*)?20\d{2}', re.IGNORECASE)

# Account code and title: "1234 Aircraft Procurement, Air Force"
# Captures the code (group 1) and title (group 2)
ACCOUNT_CODE_TITLE = re.compile(r'^(\d+)\s+(.+)$')

# Whitespace normalization: multiple spaces/tabs/newlines
WHITESPACE = re.compile(r'\s+')

# Currency symbols for stripping during numeric conversion
CURRENCY_SYMBOLS = re.compile(r'[\$€£¥₹₽]')
