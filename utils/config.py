"""Configuration management utilities for DoD budget tools.

Provides reusable functions for:
- Loading and parsing configuration files
- Managing environment-specific settings
- Organizing constants and known values
- Configuration validation
"""

from pathlib import Path
from typing import Dict, List, Set, Optional, Any
import json


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
        "2010": "Operation and Maintenance, Air Force",
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
