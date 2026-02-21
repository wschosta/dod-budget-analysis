"""Advanced search query parser for structured + free-text queries (HAWK-4).

Supports a structured query mini-language on top of the existing FTS5 search:

    pe:0602120A                     → filter by PE number
    service:army                    → filter by service/organization
    exhibit:R-2                     → filter by exhibit type
    fy:2026                         → filter by fiscal year
    tag:stealth                     → filter by tag
    "stealth aircraft"              → quoted phrase (exact FTS5 match)
    pe:0602120A "stealth aircraft"  → combined: filter + text search
    amount>1000                     → amount filter (>, <, >=, <=)
    stealth aircraft                → plain terms (FTS5 OR search)

The parser extracts structured filters into a dict and returns the remaining
free-text portion for FTS5 MATCH.

Usage:
    from utils.search_parser import parse_search_query

    parsed = parse_search_query('pe:0602120A service:army "stealth aircraft"')
    # parsed.filters == {"pe_number": ["0602120A"], "service": ["army"]}
    # parsed.text_query == '"stealth aircraft"'
    # parsed.fts5_query == '"stealth" OR "aircraft"'
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from utils.strings import sanitize_fts5_query


# ── Structured filter prefixes ───────────────────────────────────────────────
# Maps user-facing prefix → internal filter key used by build_where_clause()
_FILTER_PREFIXES: dict[str, str] = {
    "pe": "pe_number",
    "service": "service",
    "exhibit": "exhibit_type",
    "fy": "fiscal_year",
    "tag": "tag",
    "year": "fiscal_year",
    "type": "exhibit_type",
    "org": "service",
    "approp": "appropriation_code",
}

# Amount comparison operators
_AMOUNT_PATTERN = re.compile(
    r"^amount\s*(>=|<=|>|<)\s*([0-9]+(?:\.[0-9]+)?)$",
    re.IGNORECASE,
)

# Quoted phrase pattern (handles both single and double quotes)
_QUOTED_PHRASE = re.compile(r"""(?:"([^"]+)"|'([^']+)')""")

# Filter token pattern: prefix:value (value can be quoted or unquoted)
_FILTER_TOKEN = re.compile(
    r"^(" + "|".join(re.escape(k) for k in _FILTER_PREFIXES) + r"):"
    r"""(?:"([^"]+)"|'([^']+)'|(\S+))""",
    re.IGNORECASE,
)


@dataclass
class ParsedQuery:
    """Result of parsing a structured search query."""

    filters: dict[str, list[str]] = field(default_factory=dict)
    """Structured filters extracted from the query (e.g., pe_number, service)."""

    text_query: str = ""
    """Free-text portion of the query (after removing structured filters)."""

    fts5_query: str = ""
    """Sanitized FTS5 MATCH expression for the free-text portion."""

    amount_filters: list[tuple[str, float]] = field(default_factory=list)
    """Amount comparison filters as (operator, value) pairs."""

    raw_query: str = ""
    """Original query string before parsing."""

    @property
    def has_filters(self) -> bool:
        """Return True if any structured filters were extracted."""
        return bool(self.filters) or bool(self.amount_filters)

    @property
    def has_text(self) -> bool:
        """Return True if there is a free-text search component."""
        return bool(self.fts5_query)


def parse_search_query(query: str) -> ParsedQuery:
    """Parse a search query string into structured filters and free text.

    Examples::

        >>> parse_search_query('pe:0602120A "stealth aircraft"')
        ParsedQuery(filters={"pe_number": ["0602120A"]},
                    text_query='"stealth aircraft"', ...)

        >>> parse_search_query('service:army fy:2026 missile')
        ParsedQuery(filters={"service": ["army"], "fiscal_year": ["2026"]},
                    text_query='missile', ...)

        >>> parse_search_query('amount>1000 radar')
        ParsedQuery(amount_filters=[('>', 1000.0)],
                    text_query='radar', ...)

    Args:
        query: Raw search query string from the user.

    Returns:
        ParsedQuery with extracted filters and remaining text.
    """
    if not query or not query.strip():
        return ParsedQuery(raw_query=query or "")

    query = query.strip()
    result = ParsedQuery(raw_query=query)

    # Tokenize the query respecting quoted strings.
    # We use a regex that matches either:
    #   1. A filter token like pe:"value" or pe:value
    #   2. An amount filter like amount>1000
    #   3. A quoted phrase like "stealth aircraft"
    #   4. A plain word
    _token_re = re.compile(
        r"""(?:"""
        # filter with quoted value: prefix:"value" or prefix:'value'
        r"""((?:""" + "|".join(re.escape(k) for k in _FILTER_PREFIXES)
        + r"""):"[^"]+"|"""
        + r"""(?:""" + "|".join(re.escape(k) for k in _FILTER_PREFIXES)
        + r"""):'[^']+')"""
        # filter with plain value: prefix:value
        r"""|(?:""" + "|".join(re.escape(k) for k in _FILTER_PREFIXES)
        + r"""):(\S+)"""
        # amount filter
        r"""|(amount\s*(?:>=|<=|>|<)\s*[0-9]+(?:\.[0-9]+)?)"""
        # quoted phrase
        r"""|"([^"]+)"|'([^']+)'"""
        # plain word
        r"""|(\S+)"""
        r""")""",
        re.IGNORECASE,
    )

    text_parts: list[str] = []

    for m in _token_re.finditer(query):
        filter_quoted = m.group(1)  # prefix:"quoted value"
        filter_plain = m.group(2)   # value after prefix:
        amount_tok = m.group(3)     # amount>N
        phrase_dq = m.group(4)      # double-quoted phrase
        phrase_sq = m.group(5)      # single-quoted phrase
        plain = m.group(6)          # plain word

        if filter_quoted:
            # Extract prefix and value from prefix:"value" or prefix:'value'
            colon_pos = filter_quoted.index(":")
            prefix = filter_quoted[:colon_pos].lower()
            value = filter_quoted[colon_pos + 1:].strip("\"'")
            filter_key = _FILTER_PREFIXES[prefix]
            result.filters.setdefault(filter_key, []).append(value)

        elif filter_plain is not None:
            # The match includes the whole prefix:value, extract prefix from position
            full = m.group(0)
            colon_pos = full.index(":")
            prefix = full[:colon_pos].lower()
            filter_key = _FILTER_PREFIXES[prefix]
            result.filters.setdefault(filter_key, []).append(filter_plain)

        elif amount_tok:
            amount_match = _AMOUNT_PATTERN.match(amount_tok)
            if amount_match:
                op = amount_match.group(1)
                val = float(amount_match.group(2))
                result.amount_filters.append((op, val))

        elif phrase_dq:
            text_parts.append(f'"{phrase_dq}"')

        elif phrase_sq:
            text_parts.append(f'"{phrase_sq}"')

        elif plain:
            text_parts.append(plain)

    result.text_query = " ".join(text_parts).strip()

    # Generate FTS5 query from the text portion
    if result.text_query:
        result.fts5_query = sanitize_fts5_query(result.text_query)

    return result


def apply_parsed_filters(
    parsed: ParsedQuery,
    base_params: dict | None = None,
) -> dict:
    """Convert a ParsedQuery into keyword arguments for build_where_clause().

    Merges parsed filters with any existing base parameters (e.g., from
    explicit query string parameters in the API).

    Args:
        parsed: A ParsedQuery from parse_search_query().
        base_params: Optional existing filter parameters to merge with.

    Returns:
        Dict of keyword arguments suitable for build_where_clause().
    """
    params = dict(base_params or {})

    for key, values in parsed.filters.items():
        existing = params.get(key)
        if existing:
            if isinstance(existing, list):
                existing.extend(values)
            else:
                params[key] = [existing] + values
        else:
            params[key] = values

    # Amount filters → min_amount / max_amount
    for op, val in parsed.amount_filters:
        if op in (">", ">="):
            current_min = params.get("min_amount")
            if current_min is None or val > current_min:
                params["min_amount"] = val
        elif op in ("<", "<="):
            current_max = params.get("max_amount")
            if current_max is None or val < current_max:
                params["max_amount"] = val

    return params
