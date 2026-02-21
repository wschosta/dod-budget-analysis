"""Configuration management utilities for DoD budget tools.

Provides reusable functions for:
- Loading and parsing configuration files
- Managing environment-specific settings
- Organizing constants and known values
- Configuration validation

──────────────────────────────────────────────────────────────────────────────
TODOs for this file
──────────────────────────────────────────────────────────────────────────────

"""

from pathlib import Path
from typing import Dict, Optional, Any
import json
import re


# ── Exhibit Classification Constants ─────────────────────────────────────────
# Used by both downloader (folder layout) and pipeline (data source registration).
# Canonical source; downloader.metadata duplicates for import isolation.

SUMMARY_EXHIBIT_KEYS = frozenset({"p1", "r1", "o1", "m1", "c1", "rf1", "p1r"})
DETAIL_EXHIBIT_KEYS = frozenset({"p5", "r2", "r3", "r4"})

# ── Appropriation-Based Classification Patterns ──────────────────────────────
# Many DoD budget documents use descriptive filenames based on appropriation
# titles rather than exhibit type codes (e.g. "aircraft.pdf" instead of
# "p5_army.xlsx").  These patterns classify such files into summary/detail
# categories matching their budget appropriation type.
#
# NOTE on word boundaries: Standard \b fails between abbreviation and
# underscore/digit (e.g. \bapn\b won't match "apn_ba5") because _ and digits
# are word characters.  We use (?![a-zA-Z]) as a trailing boundary instead,
# which ensures the abbreviation isn't followed by more letters but allows
# underscores, digits, dots, dashes, etc.
_END = r"(?![a-zA-Z])"  # "end of abbreviation" — no more letters after this
# Alternate "start of abbreviation" that matches after _, digits, hyphens, etc.
# Python's \b treats _ as a word char, so \b fails at _X boundaries.
_START = r"(?<![a-zA-Z])"  # no letter immediately before

# Procurement appropriations → detail (equivalent to P-5 exhibits)
_PROCUREMENT_PATTERNS = re.compile(
    r"|".join([
        r"\baircraft" + _END,      # Aircraft Procurement
        r"\bacft" + _END,          # Aircraft (abbreviation)
        r"\bmissiles?" + _END,     # Missile Procurement
        r"\bmsls" + _END,          # Missiles (abbreviation)
        r"\bmissle" + _END,        # Common misspelling
        r"\bammo" + _END,          # Ammunition
        r"\bammunition" + _END,
        r"\bwtcv" + _END,          # Weapons & Tracked Combat Vehicles
        r"\bweapons?" + _END,
        r"\bopa\d*" + _END,        # Other Procurement Army (opa, opa1, opa2, opa34)
        r"\bopn" + _END,           # Other Procurement Navy
        r"\bapn" + _END,           # Aircraft Procurement Navy
        r"\bscn" + _END,           # Shipbuilding & Conversion Navy
        r"\bpanmc" + _END,         # Procurement Ammo Navy/Marine Corps
        r"\bpmc" + _END,           # Procurement Marine Corps
        r"\bprocurement" + _END,
        r"\bshipbuilding" + _END,
        # Defense-Wide per-agency procurement books (PROC_CBDP, PROC_SOCOM, …)
        _START + r"proc_",         # PROC_{agency} files — underscore IS the boundary
        _START + r"pdw" + _END,    # Procurement Defense-Wide (PDW_VOL_1, etc.)
        # Multi-year procurement justifications
        _START + r"myp" + _END,    # Multi-Year Procurement (MYP_1-4, etc.)
    ]),
    re.IGNORECASE,
)

# O&M appropriations → summary (equivalent to O-1 exhibits)
_OM_PATTERNS = re.compile(
    r"|".join([
        r"\boma" + _END,           # Operation & Maintenance Army
        r"\boma[-_v]",             # oma-v1, oma_vol, etc.
        r"\bomar" + _END,          # O&M Army Reserve
        r"\bomng" + _END,          # O&M Army National Guard
        r"\bomnr" + _END,          # O&M Navy Reserve
        r"\bomn" + _END,           # O&M Navy
        r"\bomn[-_v]",             # omn_vol, etc.
        r"\bommc" + _END,          # O&M Marine Corps
        r"\bommcr" + _END,         # O&M Marine Corps Reserve
        r"\boperation[s]?\s*(?:and|&)\s*maintenance" + _END,
        r"(?<![a-zA-Z])op-5" + _END,  # O&M detail by agency (OP-5 exhibit)
        r"(?<![a-zA-Z])op-8" + _END,  # Force structure
        r"(?<![a-zA-Z])op-31",     # Appropriation detail (op-31, op-31q variants)
        r"(?<![a-zA-Z])op-32",     # Appropriation summary (op-32, op-32a variants)
        r"(?<![a-zA-Z])op-34",     # Budget activity detail
        r"\bawcf" + _END,          # Army Working Capital Fund
        r"\bafwcf" + _END,         # Air Force Working Capital Fund
        r"\bnwcf" + _END,          # Navy Working Capital Fund
        r"\bworking\s*capital\s*fund" + _END,
        r"\bo\s+and\s+m" + _END,   # "O and M"
        r"\bo&m" + _END,           # "O&M"
        r"(?<![a-zA-Z])o-1" + _END,  # exhibit O-1 (e.g. "0104_caaf_o-1.pdf")
        # Defense-Wide O&M volume/exhibit patterns (_START handles _ boundaries)
        _START + r"om[_-]volume" + _END,   # OM_Volume1_Part1, OM_Volume1_Part_2
        _START + r"om[_-]overview" + _END, # OM_Overview, FY2026_OM_Overview
        _START + r"pb-\d+" + _END,   # PB-15, PB-24, PB-28, PB-31Q, PB-61
        _START + r"env-\d+" + _END,  # ENV-30 (environmental restoration exhibit)
        _START + r"dwwcf" + _END,    # Defense-Wide Working Capital Fund
        _START + r"revolving[_\s]*funds?" + _END,  # DoD Revolving Funds J-Book
        r"\bdeca" + _END,            # Defense Commissary Agency (DeCA J-Book)
        _START + r"dhp" + _END,      # Defense Health Program
        _START + r"service[_\s]*support" + _END,  # Service Support exhibit
    ]),
    re.IGNORECASE,
)

# Military Personnel appropriations → summary (equivalent to M-1 exhibits)
_MILPERS_PATTERNS = re.compile(
    r"|".join([
        r"\bmpa" + _END,           # Military Personnel Army
        r"\bngpa" + _END,          # National Guard Personnel Army
        r"\brpa" + _END,           # Reserve Personnel Army
        r"\bmpn" + _END,           # Military Personnel Navy
        r"\bmpmc" + _END,          # Military Personnel Marine Corps
        r"\brpmc" + _END,          # Reserve Personnel Marine Corps
        r"\brpn" + _END,           # Reserve Personnel Navy
        r"\bmpaf" + _END,          # Military Personnel Air Force
        r"\bmilpers" + _END,
        r"\bmilitary\s*personnel" + _END,
        r"\breserve\s*personnel" + _END,
        r"\bnational\s*guard\s*personnel" + _END,
    ]),
    re.IGNORECASE,
)

# MILCON appropriations → detail (detailed project justification)
_MILCON_PATTERNS = re.compile(
    r"|".join([
        r"\bmca" + _END,           # Military Construction Army
        r"\bmca[-_]",              # mca-afh, mca_fy, etc.
        r"\bmcar" + _END,          # Military Construction Army Reserve
        r"\bmcng" + _END,          # Military Construction National Guard
        r"\bmcon" + _END,          # Military Construction
        r"\bmilcon" + _END,
        r"\bmilitary\s*construction" + _END,
        r"\bbrac" + _END,          # Base Realignment and Closure
        r"\bbase\s*realignment" + _END,
        r"\bfamily\s*housing" + _END,
        r"\bfh" + _END,            # Family Housing (abbreviation)
        r"\bafh" + _END,           # Army Family Housing
        r"\bhoa" + _END,           # Homeowners Assistance
        r"\bhomeowner" + _END,
        r"\bnsip" + _END,          # NATO Security Investment Program
        _START + r"nato[_\s]*security" + _END,  # NATO Security Investment Program (full)
        _START + r"military[_\s]*construction.*consolidated",  # DW consolidated MCON
        _START + r"brac[_\s]*overview" + _END,  # BRAC Overview files
        _START + r"fhif" + _END,   # Family Housing Improvement Fund
    ]),
    re.IGNORECASE,
)

# RDT&E appropriations → detail (equivalent to R-2/R-3/R-4 exhibits)
_RDTE_PATTERNS = re.compile(
    r"|".join([
        r"\brdte" + _END,          # RDT&E
        r"\brdten" + _END,         # RDT&E Navy
        r"\bresearch.*development" + _END,
        r"\btest\s+and\s+evaluation" + _END,
        r"\bvol[-_]?\d+[a-z]?" + _END,  # vol1, vol_1, vol-2, vol5a
        r"\bvolume[-_]\w+",        # volume_1, volume_i, etc.
        r"\bvolume\s+\w+",         # volume 1, volume i, etc.
        r"\bbudget\s*activity\s*\d",  # Budget Activity 1-7
    ]),
    re.IGNORECASE,
)


def classify_exhibit_category(filename_or_exhibit_type: str) -> str:
    """Classify a filename or exhibit type as summary, detail, or other.

    Accepts either a full filename (e.g. "p1_display.xlsx") or a bare
    exhibit type key (e.g. "p1").  Uses a two-tier classification:

    1. Exhibit type codes: p1, r2, etc. (highest confidence)
    2. Appropriation-based patterns: "aircraft.pdf", "omng_vol_1.pdf", etc.

    Appropriation category mapping:
        - Procurement, MILCON, RDT&E → "detail" (line-item justification books)
        - O&M, Military Personnel → "summary" (summary/overview exhibits)
        - Everything else → "other"

    Returns:
        "summary", "detail", or "other".
    """
    name = filename_or_exhibit_type.lower()

    # ── Tier 1: Exhibit type codes (highest confidence) ──────────────────
    # Check detail first (longer keys like "r2" before "r1")
    for key in sorted(DETAIL_EXHIBIT_KEYS, key=len, reverse=True):
        if key in name:
            return "detail"
    for key in sorted(SUMMARY_EXHIBIT_KEYS, key=len, reverse=True):
        if key in name:
            return "summary"

    # ── Tier 2: Appropriation-based patterns ─────────────────────────────
    # Detail categories: procurement, milcon, RDT&E
    if _PROCUREMENT_PATTERNS.search(name):
        return "detail"
    if _MILCON_PATTERNS.search(name):
        return "detail"
    # Summary categories: O&M, military personnel
    if _OM_PATTERNS.search(name):
        return "summary"
    if _MILPERS_PATTERNS.search(name):
        return "summary"
    # RDT&E detail
    if _RDTE_PATTERNS.search(name):
        return "detail"

    return "other"


class Config:
    """Base configuration class for organizing application settings."""

    def __init__(self):
        """Initialize configuration with default values."""
        pass

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary.

        Returns:
            Dictionary of all config attributes
        """
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        """Create config from dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            Config instance with values from dictionary
        """
        config = cls()
        for key, value in data.items():
            setattr(config, key, value)
        return config

    def save_json(self, path: Path) -> None:
        """Save configuration to JSON file.

        Args:
            path: Path to save configuration file
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    @classmethod
    def load_json(cls, path: Path) -> "Config":
        """Load configuration from JSON file.

        Args:
            path: Path to configuration file

        Returns:
            Config instance loaded from file

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file is not valid JSON
        """
        with open(path, "r") as f:
            data = json.load(f)
        return cls.from_dict(data)


class DatabaseConfig(Config):
    """Configuration for database operations."""

    def __init__(self):
        """Initialize database configuration."""
        super().__init__()
        self.db_path = Path("dod_budget.sqlite")
        self.wal_mode = True
        self.synchronous = "NORMAL"
        self.temp_store = "MEMORY"
        self.cache_size = -64000
        self.batch_size = 1000
        self.max_connections = 5


class DownloadConfig(Config):
    """Configuration for download operations."""

    def __init__(self):
        """Initialize download configuration."""
        super().__init__()
        self.documents_dir = Path("DoD_Budget_Documents")
        self.cache_dir = Path(".discovery_cache")
        self.cache_ttl_hours = 24
        self.max_retries = 3
        self.backoff_factor = 2.0
        self.timeout_seconds = 30
        self.pool_connections = 10
        self.pool_maxsize = 20


class KnownValues:
    """Container for known valid values used in validation."""

    # Organization names
    ORGANIZATIONS = {
        "Army",
        "Navy",
        "Air Force",
        "Space Force",
        "Defense-Wide",
        "Marine Corps",
        "Joint Staff",
    }

    # Organization code mappings
    ORG_CODES = {
        "A": "Army",
        "N": "Navy",
        "F": "Air Force",
        "S": "Space Force",
        "D": "Defense-Wide",
        "M": "Marine Corps",
        "J": "Joint Staff",
    }

    # Budget exhibit types and their descriptions
    EXHIBIT_TYPES = {
        "m1": "Military Personnel (M-1)",
        "o1": "Operation & Maintenance (O-1)",
        "p1": "Procurement (P-1)",
        "p1r": "Procurement (P-1R)",
        "r1": "R&D (R-1)",
        "rf1": "RDT&E (RF-1)",
        "c1": "Budget Activities (C-1)",
    }

    # Budget display categories
    BUDGET_CATEGORIES = {
        "military_personnel": "Military Personnel",
        "operations": "Operations & Maintenance",
        "procurement": "Procurement",
        "research": "Research, Development, Test & Evaluation",
        "defense_wide": "Defense-Wide",
        "other": "Other",
    }

    # Common appropriation accounts
    APPROPRIATIONS = {
        "1105": "Military Personnel, Army",
        "1206": "Military Personnel, Navy",
        "1306": "Military Personnel, Marine Corps",
        "1405": "Military Personnel, Air Force",
        "1505": "Military Personnel, Space Force",
        "2010": "Operation and Maintenance, Army",
        "2040": "Operation and Maintenance, Navy",
        "2080": "Operation and Maintenance, Marine Corps",
        "2020": "Operation and Maintenance, Air Force",
        "3110": "Aircraft Procurement, Air Force",
        "3450": "Missile Procurement, Air Force",
    }

    @classmethod
    def is_valid_org(cls, org: str) -> bool:
        """Check if organization is in known values.

        Args:
            org: Organization name

        Returns:
            True if organization is known
        """
        return org in cls.ORGANIZATIONS

    @classmethod
    def is_valid_exhibit_type(cls, exhibit: str) -> bool:
        """Check if exhibit type is in known values.

        Args:
            exhibit: Exhibit type code

        Returns:
            True if exhibit type is known
        """
        return exhibit.lower() in cls.EXHIBIT_TYPES

    @classmethod
    def get_exhibit_description(cls, exhibit: str) -> Optional[str]:
        """Get description for an exhibit type.

        Args:
            exhibit: Exhibit type code

        Returns:
            Description string or None if not found
        """
        return cls.EXHIBIT_TYPES.get(exhibit.lower())

    @classmethod
    def get_org_code(cls, org_name: str) -> Optional[str]:
        """Get code for organization name.

        Args:
            org_name: Organization name

        Returns:
            Organization code or None if not found
        """
        for code, name in cls.ORG_CODES.items():
            if name == org_name:
                return code
        return None


class ColumnMapping:
    """Maps budget exhibit column headers to standardized names."""

    # Military Personnel columns
    M1_COLUMNS = {
        "account": "account",
        "budget_activity_title": "budget_activity_title",
        "pe_number": "pe_number",
        "fy2024": "amount_fy2024",
        "fy2025_enacted": "amount_fy2025_enacted",
        "fy2026_request": "amount_fy2026_request",
    }

    # Operation & Maintenance columns
    O1_COLUMNS = {
        "account": "account",
        "budget_activity_title": "budget_activity_title",
        "pe_number": "pe_number",
        "fy2024": "amount_fy2024",
        "fy2025_enacted": "amount_fy2025_enacted",
        "fy2026_request": "amount_fy2026_request",
    }

    # Procurement columns
    P1_COLUMNS = {
        "account": "account",
        "item_name": "item_name",
        "pe_number": "pe_number",
        "fy2024": "amount_fy2024",
        "fy2025_enacted": "amount_fy2025_enacted",
        "fy2026_request": "amount_fy2026_request",
        "unit_cost": "unit_cost",
        "quantity": "quantity",
    }

    @classmethod
    def get_mapping(cls, exhibit_type: str) -> Dict[str, str]:
        """Get column mapping for exhibit type.

        Args:
            exhibit_type: Exhibit type code (m1, o1, p1, etc.)

        Returns:
            Dictionary mapping header names to standardized column names
        """
        exhibit = exhibit_type.lower()
        if exhibit in ("m1",):
            return cls.M1_COLUMNS
        if exhibit in ("o1",):
            return cls.O1_COLUMNS
        if exhibit in ("p1", "p1r"):
            return cls.P1_COLUMNS
        return {}

    @classmethod
    def normalize_header(cls, header: str) -> str:
        """Normalize a column header string.

        Args:
            header: Raw header string from spreadsheet

        Returns:
            Normalized header (lowercase, stripped, normalized whitespace)
        """
        if not header:
            return ""
        normalized = str(header).lower().replace("\n", " ").strip()
        # Collapse multiple spaces
        import re
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized


class FilePatterns:
    """Standard file naming and path patterns."""

    # Document discovery patterns
    PDF_FILES = r"\.pdf$"
    EXCEL_FILES = r"\.(xlsx?|xls)$"
    CSV_FILES = r"\.csv$"
    ZIP_FILES = r"\.zip$"

    # Budget file naming patterns
    EXHIBIT_FILE_PATTERN = r".*exhibit.*?(m1|o1|p1|r1).*"
    BUDGET_JUSTIFICATION_PATTERN = r".*budget.*justification.*"
    BUDGET_DOCUMENT_PATTERN = r".*budget.*document.*"

    @staticmethod
    def is_budget_document(filename: str) -> bool:
        """Check if filename matches budget document patterns.

        Args:
            filename: Filename to check

        Returns:
            True if matches budget document naming
        """
        import re
        filename_lower = filename.lower()
        patterns = [
            r"budget.*justification",
            r"exhibit.*[om1pr]",
            r"appropriation.*",
            r"rdt&e",
        ]
        for pattern in patterns:
            if re.search(pattern, filename_lower):
                return True
        return False

    @staticmethod
    def get_fiscal_year_from_filename(filename: str) -> Optional[int]:
        """Extract fiscal year from filename if possible.

        Args:
            filename: Filename to parse

        Returns:
            Fiscal year (2000-2099) or None
        """
        import re
        match = re.search(r'20\d{2}', filename)
        if match:
            try:
                return int(match.group())
            except ValueError:
                pass
        return None


# ── OPT-CFG-001: Consolidated application configuration ───────────────────────

import os as _os  # noqa: E402


class AppConfig(Config):
    """Application-level configuration loaded from environment variables.

    All env vars have sensible defaults so the application works out of the
    box without any configuration.

    Environment variables:
        APP_DB_PATH: Path to the SQLite database file (default: dod_budget.sqlite)
        APP_PORT: API server port (default: 8000)
        APP_HOST: API server bind address (default: 127.0.0.1)
        APP_LOG_FORMAT: Logging format — "text" or "json" (default: text)
        APP_CORS_ORIGINS: Comma-separated allowed origins (default: *)
        RATE_LIMIT_SEARCH: Max search requests per minute per IP (default: 60)
        RATE_LIMIT_DOWNLOAD: Max download requests per minute per IP (default: 10)
        RATE_LIMIT_DEFAULT: Max requests per minute for other endpoints (default: 120)
        APP_DB_POOL_SIZE: Max DB connections in pool (default: 10)
        TRUSTED_PROXIES: Comma-separated proxy IP addresses to trust for forwarded IPs
    """

    def __init__(self) -> None:
        super().__init__()
        self.db_path = Path(_os.getenv("APP_DB_PATH", "dod_budget.sqlite"))
        self.api_port = int(_os.getenv("APP_PORT", "8000"))
        self.api_host = _os.getenv("APP_HOST", "127.0.0.1")
        self.log_format = _os.getenv("APP_LOG_FORMAT", "text")
        raw_origins = _os.getenv("APP_CORS_ORIGINS", "*")
        self.cors_origins: list[str] = (
            ["*"] if raw_origins == "*"
            else [o.strip() for o in raw_origins.split(",") if o.strip()]
        )
        self.rate_limit_search = int(_os.getenv("RATE_LIMIT_SEARCH", "60"))
        self.rate_limit_download = int(_os.getenv("RATE_LIMIT_DOWNLOAD", "10"))
        self.rate_limit_default = int(_os.getenv("RATE_LIMIT_DEFAULT", "120"))
        self.pool_size = int(_os.getenv("APP_DB_POOL_SIZE", "10"))
        raw_proxies = _os.getenv("TRUSTED_PROXIES", "")
        self.trusted_proxies: set[str] = (
            {p.strip() for p in raw_proxies.split(",") if p.strip()}
        )

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Create an AppConfig instance populated from environment variables."""
        return cls()
