"""Shared utilities for DoD Budget tools.

──────────────────────────────────────────────────────────────────────────────
Cross-cutting Utility TODOs
──────────────────────────────────────────────────────────────────────────────

TODO OPT-FE-001 / UTIL-001 [Group: TIGER] [Complexity: MEDIUM] [Tokens: ~2500] [User: NO]
    Create utils/query.py — shared SQL query builder module.
    The WHERE clause construction logic is duplicated in three places:
    - api/routes/budget_lines.py (_build_where)
    - api/routes/frontend.py (imports from budget_lines)
    - api/routes/download.py (inline implementation)
    Steps:
      1. Create utils/query.py with:
         - build_where_clause(fiscal_year, service, exhibit_type, pe_number,
           appropriation_code, min_amount, max_amount) -> (str, list)
         - build_order_clause(sort_by, sort_dir, allowed_sorts) -> str
      2. Move _build_where from budget_lines.py to utils/query.py
      3. Update budget_lines.py, frontend.py, download.py to import from utils
      4. Add utils/query.py to this __init__.py imports and __all__
      5. Add comprehensive tests in tests/test_query_utils.py
    Acceptance: Single query builder; all 3 routes use it; all tests pass.

TODO UTIL-002 [Group: TIGER] [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Create utils/cache.py — lightweight in-memory TTL cache.
    Multiple components need TTL caching (reference data, aggregations,
    connection pool stats). Steps:
      1. Create utils/cache.py with TTLCache class:
         - __init__(maxsize=128, ttl_seconds=300)
         - get(key) -> value | None
         - set(key, value) -> None
         - clear() -> None
         - stats() -> dict (hits, misses, size)
      2. Use in frontend.py for _get_services(), _get_exhibit_types()
      3. Use in aggregations.py for expensive GROUP BY queries
      4. Add to this __init__.py imports
      5. Add tests in tests/test_cache_utils.py
    Acceptance: TTL cache reduces repeated DB queries; tests pass.
"""

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

# Manifest management
from utils.manifest import (
    Manifest,
    ManifestEntry,
    compute_file_hash,
)

# PDF narrative section parser (1.B5-c)
from utils.pdf_sections import (
    parse_narrative_sections,
    extract_sections_for_page,
    is_narrative_exhibit,
    SECTION_PATTERN,
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
    # Manifest
    "Manifest",
    "ManifestEntry",
    "compute_file_hash",
    # PDF sections
    "parse_narrative_sections",
    "extract_sections_for_page",
    "is_narrative_exhibit",
    "SECTION_PATTERN",
]
