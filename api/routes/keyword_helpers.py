"""Shared constants, SQL utilities, and normalization for keyword-search modules.

Leaf module with no intra-package dependencies — imported by keyword_search,
keyword_xlsx, and keyword_r2.
"""

from __future__ import annotations

import json
import re
from typing import Any

from utils.normalization import BA_CANONICAL, R2_JUNK_TITLES
from utils.patterns import PE_NUMBER_STRICT_CI, PE_SUFFIX_PATTERN  # noqa: F401 (PE_NUMBER_STRICT_CI re-exported)

# ── Constants ─────────────────────────────────────────────────────────────────

SEARCH_COLS = ["line_item_title", "account_title", "budget_activity_title"]

FY_START = 2015
FY_END = 2026

# Regex to extract PE number and title from PDF exhibit header lines
PE_TITLE_RE = re.compile(
    rf"PE\s+(\d{{7}}{PE_SUFFIX_PATTERN})\s*[/:]\s*(.+?)(?:\s+\d|$)"
)

# Levenshtein merge threshold for R-2 dedup
LEVENSHTEIN_THRESHOLD = 0.20

# Lowercased version of R2_JUNK_TITLES + "page" — used as fallback filter
SKIP_RAW_TITLES = frozenset(t.lower() for t in R2_JUNK_TITLES) | {"page"}

# Organization name from source_file path fragments (API-side fallback)
ORG_FROM_PATH = [
    ("US_Army", "Army"),
    ("US_Air_Force", "Air Force"),
    ("US_Navy", "Navy"),
    ("Defense_Wide", "Defense-Wide"),
    ("DARPA", "DARPA"),
    ("SOCOM", "SOCOM"),
]


# ── SQL / JSON helpers ────────────────────────────────────────────────────────


def in_clause(params: list | set) -> tuple[str, list]:
    """Return ``'?,?,?'`` placeholder string and flat param list."""
    p = list(params)
    return ", ".join("?" for _ in p), p


def like_clauses(columns: list[str], keywords: list[str]) -> tuple[str, list[str]]:
    """Build OR-joined ``col LIKE ?`` clauses for keyword search."""
    clauses = [f"{col} LIKE ?" for col in columns for _ in keywords]
    params = [f"%{kw}%" for _ in columns for kw in keywords]
    return " OR ".join(clauses), params


def safe_json_list(val: Any) -> list:
    """Parse a JSON string to list, returning ``[]`` on failure."""
    if isinstance(val, list):
        return val
    try:
        return json.loads(val) if val else []
    except (json.JSONDecodeError, TypeError):
        return []


# ── Cache DDL ─────────────────────────────────────────────────────────────────


def cache_ddl(table_name: str, fy_start: int = FY_START, fy_end: int = FY_END) -> str:
    """Return the CREATE TABLE DDL for a keyword-search cache table."""
    fy_cols = "\n".join(
        f"    fy{yr} REAL, fy{yr}_ref TEXT," for yr in range(fy_start, fy_end + 1)
    )
    fy_cols = fy_cols.rstrip(",")
    return f"""
CREATE TABLE IF NOT EXISTS {table_name} (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    pe_number               TEXT NOT NULL,
    organization_name       TEXT,
    exhibit_type            TEXT,
    line_item_title         TEXT,
    budget_activity         TEXT,
    budget_activity_title   TEXT,
    budget_activity_norm    TEXT,
    appropriation_title     TEXT,
    account_title           TEXT,
    color_of_money          TEXT,
    matched_keywords_row    TEXT,
    matched_keywords_desc   TEXT,
    description_text        TEXT,
    lineage_note            TEXT,
{fy_cols}
);
"""


# ── Normalization helpers ─────────────────────────────────────────────────────


def normalize_budget_activity(ba_number: str | None, ba_title: str | None) -> str:
    """Map budget_activity number to canonical BA label, falling back to title."""
    if ba_number and ba_number.strip() in BA_CANONICAL:
        return BA_CANONICAL[ba_number.strip()]
    if ba_title:
        return ba_title.strip()
    return "Unknown"


def color_of_money(approp_title: str | None) -> str:
    """Map appropriation title to a standard color-of-money category."""
    if not approp_title:
        return "Unknown"
    t = approp_title.upper()
    if any(k in t for k in ("RDT", "RESEARCH", "DEVELOPMENT", "R&D")):
        return "RDT&E"
    if "PROCURE" in t:
        return "Procurement"
    if any(k in t for k in ("OPER", "MAINT", "O&M")):
        return "O&M"
    if any(k in t for k in ("MILCON", "CONSTRUCTION")):
        return "MILCON"
    if any(k in t for k in ("MILPERS", "PERSONNEL")):
        return "Military Personnel"
    return approp_title


# ── Keyword matching ─────────────────────────────────────────────────────────


def find_matched_keywords(
    text_fields: list[str | None],
    keywords: list[str],
) -> list[str]:
    """Return which of *keywords* match (case-insensitive) in *text_fields*.

    Uses word-boundary matching to avoid false positives like
    "mach" matching "machine".
    """
    combined = " ".join((t or "") for t in text_fields).lower()
    if not combined.strip():
        return []
    matched = []
    for kw in keywords:
        kw_lower = kw.lower().strip()
        if not kw_lower:
            continue
        if kw_lower in combined and re.search(
            r"(?<!\w)" + re.escape(kw_lower) + r"(?!\w)", combined
        ):
            matched.append(kw)
    return matched


# ── Garbage description filter ───────────────────────────────────────────────


def is_garbage_description(text: str | None) -> bool:
    """Detect R-1 page header text or other artifacts masquerading as descriptions."""
    if not text:
        return True
    stripped = text.strip()
    if len(stripped) < 80:
        return True
    garbage_markers = [
        "Exhibit R-1",
        "President's Budget",
        "Total Obligational Authority",
        "R D T & E Program Exhibit",
        "RDT&E PROGRAM EXHIBIT",
    ]
    for marker in garbage_markers:
        if marker in stripped[:300]:
            return True
    return False
