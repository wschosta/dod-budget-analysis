"""String processing utilities for DoD budget tools.

Optimization: Critical functions like safe_float() are called thousands of times
during data ingestion. Using pre-compiled patterns and efficient string operations
yields ~10-15% speedup in build_budget_db.py.
"""

import re

from utils.patterns import WHITESPACE, CURRENCY_SYMBOLS, FTS5_SPECIAL_CHARS

# Pre-compiled pattern for fiscal year normalization
_FY_NORMALIZE_RE = re.compile(
    r"^(?:FY\s*)?(\d{4})$", re.IGNORECASE
)
_FY_SHORT_RE = re.compile(
    r"^FY\s*(\d{2})$", re.IGNORECASE
)


def safe_float(val, default: float = 0.0) -> float:
    """Safely convert value to float with fallback default.

    Handles:
    - None, empty strings -> default
    - Numeric types -> float
    - Strings with currency symbols, whitespace, commas
    - Invalid input -> default

    Performance: Optimized for fast execution in data ingestion loops
    where this is called thousands of times.

    Args:
        val: Value to convert (any type)
        default: Value to return on failure (default: 0.0)

    Returns:
        float: Parsed value or default
    """
    if val is None or val == '':
        return default
    if isinstance(val, (int, float)):
        return float(val)

    try:
        s = str(val).strip()
        # Remove currency symbols and normalize whitespace
        s = CURRENCY_SYMBOLS.sub('', s)
        s = s.replace(',', '').strip()
        return float(s) if s else default
    except (ValueError, TypeError):
        return default


def normalize_whitespace(s: str) -> str:
    """Normalize multiple whitespace characters to single spaces.

    Converts tabs, newlines, multiple spaces to single space.
    Useful for cleaning up parsed text from PDFs and spreadsheets.

    Example:
        "Aircraft   Procurement\\n  Air Force" -> "Aircraft Procurement Air Force"

    Performance: Pre-compiled WHITESPACE pattern is ~10% faster than inline
    string operations for text with heavy whitespace.
    """
    return WHITESPACE.sub(' ', s).strip()


def sanitize_fts5_query(query: str, prefix: bool = False) -> str:
    """Sanitize user input for safe use in SQLite FTS5 MATCH expressions.

    FTS5 has special operators (AND, OR, NOT, NEAR) and special characters
    that interfere with simple literal search. This function:
    1. Strips FTS5 operator characters
    2. Removes FTS5 boolean keywords
    3. Wraps terms in quotes for literal matching
    4. Joins with OR for broad matching
    5. Optionally appends * for prefix matching

    Example:
        'missile defense system' -> '"missile" OR "defense" OR "system"'
        'army "R&D"' -> '"army" OR "rd"'
        'conventional prompt' (prefix=True) ->
            '"conventional" OR "conventional"* OR "prompt" OR "prompt"*'

    Args:
        query: Raw user search query
        prefix: If True, also add prefix-wildcard variants for partial matching

    Returns:
        Sanitized FTS5 query string safe for MATCH expressions
    """
    FTS5_KEYWORDS = {"AND", "OR", "NOT", "NEAR"}

    # Strip FTS5 operator characters
    cleaned = FTS5_SPECIAL_CHARS.sub(" ", query)
    # Split into individual terms
    terms = cleaned.split()
    # Drop FTS5 boolean keywords and empty/dash-only terms
    terms = [t for t in terms if t.upper() not in FTS5_KEYWORDS and t.strip("-")]

    if not terms:
        return ""

    if prefix:
        # Include both exact and prefix-wildcard variants for broader matching
        parts = []
        for t in terms:
            parts.append(f'"{t}"')
            parts.append(f'"{t}"*')
        return " OR ".join(parts)

    # Wrap each term in double quotes for literal matching
    return " OR ".join(f'"{t}"' for t in terms)


def normalize_fiscal_year(value: str) -> str | None:
    """Normalize a fiscal year string to a consistent 4-digit format.

    Converts various fiscal year representations to a bare 4-digit year string.
    This is used during data ingestion to ensure fiscal year values are stored
    consistently in the database.

    Supported formats:
        "FY 2026"  -> "2026"
        "FY2026"   -> "2026"
        "2026"     -> "2026"
        "FY26"     -> "2026"  (assumes 2000s for 2-digit years)
        "FY 26"    -> "2026"  (assumes 2000s for 2-digit years)

    Args:
        value: Raw fiscal year string from spreadsheet or metadata.

    Returns:
        4-digit year string (e.g. "2026"), or None if input is not
        a recognizable fiscal year format.
    """
    if not value or not isinstance(value, str):
        return None

    stripped = value.strip()
    if not stripped:
        return None

    # Match "FY 2026", "FY2026", or bare "2026"
    m = _FY_NORMALIZE_RE.match(stripped)
    if m:
        year = int(m.group(1))
        # Sanity check: valid fiscal years are in a reasonable range
        if 1900 <= year <= 2100:
            return str(year)
        return None

    # Match "FY26" or "FY 26" (2-digit year)
    m = _FY_SHORT_RE.match(stripped)
    if m:
        short_year = int(m.group(1))
        # Assume 2000s for all 2-digit FY values (DoD data is modern)
        return str(2000 + short_year)

    return None
