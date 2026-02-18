"""Shared utilities for DoD Budget tools."""

# Common utilities
from utils.common import format_bytes, elapsed, sanitize_filename, get_connection

# Pattern definitions
from utils.patterns import (
    DOWNLOADABLE_EXTENSIONS,
    PE_NUMBER,
    FTS5_SPECIAL_CHARS,
    FISCAL_YEAR,
    ACCOUNT_CODE_TITLE,
)

# String utilities
from utils.strings import safe_float, normalize_whitespace, sanitize_fts5_query

# Database utilities
from utils.database import (
    init_pragmas,
    batch_insert,
    get_table_count,
    get_table_schema,
    table_exists,
    create_fts5_index,
    disable_fts5_triggers,
    enable_fts5_triggers,
    query_to_dicts,
    vacuum_database,
)

# Validation utilities
from utils.validation import (
    ValidationIssue,
    ValidationResult,
    ValidationRegistry,
    is_valid_fiscal_year,
    is_valid_amount,
    is_valid_organization,
    is_valid_exhibit_type,
)

# Progress tracking
from utils.progress import (
    ProgressTracker,
    TerminalProgressTracker,
    SilentProgressTracker,
    FileProgressTracker,
)

# HTTP utilities
from utils.http import (
    RetryStrategy,
    SessionManager,
    TimeoutManager,
    CacheManager,
    download_file,
)

# Output formatting
from utils.formatting import (
    format_amount,
    format_percent,
    format_count,
    truncate_text,
    extract_snippet,
    highlight_terms,
    TableFormatter,
    ReportFormatter,
)

# Configuration
from utils.config import (
    Config,
    DatabaseConfig,
    DownloadConfig,
    KnownValues,
    ColumnMapping,
    FilePatterns,
)

__all__ = [
    # Common
    "format_bytes",
    "elapsed",
    "sanitize_filename",
    "get_connection",
    # Patterns
    "DOWNLOADABLE_EXTENSIONS",
    "PE_NUMBER",
    "FTS5_SPECIAL_CHARS",
    "FISCAL_YEAR",
    "ACCOUNT_CODE_TITLE",
    # Strings
    "safe_float",
    "normalize_whitespace",
    "sanitize_fts5_query",
    # Database
    "init_pragmas",
    "batch_insert",
    "get_table_count",
    "get_table_schema",
    "table_exists",
    "create_fts5_index",
    "disable_fts5_triggers",
    "enable_fts5_triggers",
    "query_to_dicts",
    "vacuum_database",
    # Validation
    "ValidationIssue",
    "ValidationResult",
    "ValidationRegistry",
    "is_valid_fiscal_year",
    "is_valid_amount",
    "is_valid_organization",
    "is_valid_exhibit_type",
    # Progress
    "ProgressTracker",
    "TerminalProgressTracker",
    "SilentProgressTracker",
    "FileProgressTracker",
    # HTTP
    "RetryStrategy",
    "SessionManager",
    "TimeoutManager",
    "CacheManager",
    "download_file",
    # Formatting
    "format_amount",
    "format_percent",
    "format_count",
    "truncate_text",
    "extract_snippet",
    "highlight_terms",
    "TableFormatter",
    "ReportFormatter",
    # Config
    "Config",
    "DatabaseConfig",
    "DownloadConfig",
    "KnownValues",
    "ColumnMapping",
    "FilePatterns",
]
