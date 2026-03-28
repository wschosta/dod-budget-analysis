"""
Fuzzy keyword matching for budget line text fields.

Three-pass algorithm:
1. Acronym expansion — expand user keywords via DoD acronym lookup
2. Prefix/substring — case-insensitive ``keyword in text``
3. Edit-distance fallback — Levenshtein distance for typo tolerance

Used by the explorer cache builder to find matching budget lines.
"""

from __future__ import annotations

from utils.dod_acronyms import ACRONYM_LOOKUP


def expand_keywords(keywords: list[str]) -> list[str]:
    """Expand keywords with acronym alternatives.

    Returns the original keywords plus any acronym expansions.
    Deduplicates (case-insensitive) while preserving order.
    """
    seen: set[str] = set()
    expanded: list[str] = []
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower not in seen:
            seen.add(kw_lower)
            expanded.append(kw)
        # Add acronym expansions
        for alt in ACRONYM_LOOKUP.get(kw_lower, []):
            if alt not in seen:
                seen.add(alt)
                expanded.append(alt)
    return expanded


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def _max_edit_distance(keyword: str) -> int:
    """Compute the maximum allowed edit distance for a keyword.

    Scales with keyword length:
    - 1-4 chars: distance 1
    - 5-8 chars: distance 2
    - 9+ chars: distance 3 (capped)
    """
    n = len(keyword)
    if n <= 4:
        return 1
    if n <= 8:
        return 2
    return 3


def fuzzy_match_keyword(keyword: str, text: str) -> str | None:
    """Check if *keyword* fuzzy-matches anywhere in *text*.

    Returns the match type if found:
    - ``"exact"`` — case-insensitive substring match
    - ``"fuzzy"`` — edit-distance match against a word token in text

    Returns ``None`` if no match.
    """
    kw_lower = keyword.lower()
    text_lower = text.lower()

    # Pass 1: exact substring
    if kw_lower in text_lower:
        return "exact"

    # Pass 2: edit-distance against individual word tokens
    max_dist = _max_edit_distance(kw_lower)
    # Only try edit-distance for keywords of reasonable length (>=3)
    if len(kw_lower) < 3:
        return None

    for token in text_lower.split():
        # Skip very short tokens (articles, etc.) unless keyword is also short
        if len(token) < 3:
            continue
        # Only compare tokens of similar length
        if abs(len(token) - len(kw_lower)) > max_dist:
            continue
        dist = _levenshtein_distance(kw_lower, token)
        if dist <= max_dist:
            return "fuzzy"

    return None


def find_matched_keywords_fuzzy(
    text_fields: list[str | None],
    keywords: list[str],
    use_fuzzy: bool = True,
) -> list[dict[str, str]]:
    """Return which keywords match in the given text fields, with match metadata.

    Returns a list of dicts: ``[{"keyword": "...", "match_type": "exact|acronym|fuzzy"}]``

    When *use_fuzzy* is False, only exact substring matching is used (same
    behavior as the original hypersonics implementation).
    """
    combined = " ".join((t or "") for t in text_fields)
    if not combined.strip():
        return []

    # Expand keywords with acronym alternatives
    original_set = {kw.lower() for kw in keywords}
    expanded = expand_keywords(keywords) if use_fuzzy else keywords

    results: list[dict[str, str]] = []
    seen_keywords: set[str] = set()  # Avoid duplicate matches

    for kw in expanded:
        kw_lower = kw.lower()
        if kw_lower in seen_keywords:
            continue

        if use_fuzzy:
            match_type = fuzzy_match_keyword(kw, combined)
        else:
            match_type = "exact" if kw.lower() in combined.lower() else None

        if match_type:
            seen_keywords.add(kw_lower)
            # Determine if this is an acronym expansion match
            if kw_lower not in original_set:
                reported_type = "acronym"
            else:
                reported_type = match_type
            results.append({"keyword": kw, "match_type": reported_type})

    return results


def find_matched_keywords_simple(
    text_fields: list[str | None],
    keywords: list[str],
) -> list[str]:
    """Simple substring matching — returns just keyword strings.

    Drop-in replacement for the original ``find_matched_keywords`` that
    also checks acronym expansions but returns the same ``list[str]`` format.
    """
    results = find_matched_keywords_fuzzy(text_fields, keywords, use_fuzzy=True)
    return [r["keyword"] for r in results]
