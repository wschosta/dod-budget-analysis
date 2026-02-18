# Utilities Reference

The `utils/` package provides shared functionality used across all DoD Budget Analysis
tools. Import from the package directly (`from utils import ...`) or from sub-modules.

All public names are re-exported from `utils/__init__.py`.

---

## Module Overview

| Module | Purpose |
|--------|---------|
| `utils/common.py` | General-purpose helpers: byte formatting, elapsed time, filenames, SQLite connections |
| `utils/strings.py` | String processing: `safe_float`, whitespace normalization, FTS5 query sanitization |
| `utils/patterns.py` | Pre-compiled regex patterns for PE numbers, fiscal years, extensions |
| `utils/database.py` | SQLite helpers: PRAGMA init, batch inserts, FTS5 index management |
| `utils/formatting.py` | Output formatting: `TableFormatter`, `ReportFormatter`, amount/percent display |
| `utils/config.py` | Configuration: `DatabaseConfig`, `DownloadConfig`, `KnownValues`, `ColumnMapping` |
| `utils/http.py` | HTTP utilities: `RetryStrategy`, `SessionManager`, `TimeoutManager`, `CacheManager` |
| `utils/manifest.py` | Download manifest tracking: `Manifest`, `ManifestEntry`, hash verification |
| `utils/progress.py` | Progress tracking: `ProgressTracker`, `TerminalProgressTracker`, `FileProgressTracker` |
| `utils/validation.py` | Validation framework: `ValidationResult`, `ValidationRegistry`, type validators |

---

## utils/common.py

### `format_bytes(b: int) -> str`
Format an integer byte count into a human-readable string (KB, MB, GB).

```python
from utils import format_bytes
format_bytes(1536)        # "2 KB"
format_bytes(2_000_000)   # "1.9 MB"
format_bytes(1_500_000_000)  # "1.40 GB"
```

### `elapsed(start_time: float) -> str`
Format the time elapsed since a `time.time()` timestamp.

```python
import time
from utils import elapsed
t0 = time.time()
# ... do work ...
print(elapsed(t0))   # "1m 23s"
```

### `sanitize_filename(name: str) -> str`
Strip URL query parameters and replace invalid filesystem characters with underscores.

### `get_connection(db_path: Path, cached: bool = False) -> sqlite3.Connection`
Open a SQLite database with `row_factory = sqlite3.Row`. Exits with an error message
if the file does not exist (useful for CLI tools).

- `cached=False` (default): new connection each call — for single-query CLI tools
- `cached=True`: reuses a module-level connection — ~20-30% faster for bulk operations

---

## utils/strings.py

### `safe_float(val, default: float = 0.0) -> float`
Safely convert any value to float. Handles `None`, empty strings, currency symbols
(`$`, `€`, etc.), commas, and whitespace.

```python
from utils import safe_float
safe_float("$1,234.56")   # 1234.56
safe_float(None)          # 0.0
safe_float("n/a", -1.0)   # -1.0
```

Performance: Called thousands of times per build; uses pre-compiled regex from
`utils/patterns.py` for ~10-15% speedup.

### `normalize_whitespace(s: str) -> str`
Collapse multiple spaces, tabs, and newlines to a single space and strip.

```python
from utils import normalize_whitespace
normalize_whitespace("Aircraft   Procurement\n  Air Force")
# "Aircraft Procurement Air Force"
```

### `sanitize_fts5_query(query: str) -> str`
Sanitize user input for safe use in SQLite FTS5 MATCH expressions. Strips operator
characters and wraps terms in double quotes.

```python
from utils import sanitize_fts5_query
sanitize_fts5_query("missile defense system")
# '"missile" OR "defense" OR "system"'
sanitize_fts5_query("cyber AND NOT classified")
# '"cyber" OR "classified"'
```

---

## utils/patterns.py

Pre-compiled `re.Pattern` objects for common patterns:

| Name | Pattern | Example Match |
|------|---------|---------------|
| `PE_NUMBER` | `\b\d{7}[A-Z]{1,2}\b` | `0602702E` |
| `FISCAL_YEAR` | `(FY\s*)?20\d{2}` | `FY2026`, `2026` |
| `DOWNLOADABLE_EXTENSIONS` | `\.(pdf\|xlsx?\|zip\|csv)$` | `.xlsx`, `.pdf` |
| `ACCOUNT_CODE_TITLE` | `^(\d+)\s+(.+)$` | `2035 Aircraft Procurement` |
| `WHITESPACE` | `\s+` | multiple spaces/tabs |
| `CURRENCY_SYMBOLS` | `[\$€£¥₹₽]` | `$`, `€` |
| `FTS5_SPECIAL_CHARS` | `[\"()*:^+]` | FTS5 operators |

```python
from utils import PE_NUMBER, FISCAL_YEAR
PE_NUMBER.search("Program 0602702E Aircraft")  # matches
FISCAL_YEAR.findall("FY2025 to FY2026")        # ['FY2025', 'FY2026']
```

---

## utils/database.py

### `init_pragmas(conn: sqlite3.Connection) -> None`
Apply performance-optimized SQLite PRAGMAs:
- `journal_mode = WAL` (better concurrent access)
- `synchronous = NORMAL` (faster writes, safe for non-critical data)
- `cache_size = -128000` (128 MB page cache)
- `temp_store = MEMORY`

### `batch_insert(conn, table, rows, columns, batch_size=1000) -> int`
Insert rows in batches using `executemany`. Returns total rows inserted.

### `create_fts5_index(conn, fts_table, source_table, columns, content_rowid) -> None`
Create or recreate an FTS5 content-backed virtual table and populate it from
the source table.

### `disable_fts5_triggers(conn, fts_table) -> None` / `enable_fts5_triggers(conn, fts_table) -> None`
Disable and re-enable the auto-sync triggers on an FTS5 content table. Disabling
triggers before a bulk insert and re-enabling after improves insert performance
by ~30%.

### `table_exists(conn, table_name) -> bool`
Return True if a table exists in the database.

### `query_to_dicts(conn, sql, params=None) -> list[dict]`
Execute a SQL query and return results as a list of plain `dict` objects (instead of
`sqlite3.Row` objects).

### `vacuum_database(conn) -> None`
Run `VACUUM` to reclaim space and defragment the database file.

---

## utils/formatting.py

### `format_amount(amount: float | None, unit: str = "thousands") -> str`
Format a budget amount for display. Handles None, zero, and very large values.

```python
from utils import format_amount
format_amount(1500)      # "$1,500"  (thousands)
format_amount(None)      # "—"
format_amount(0)         # "$0"
```

### `format_percent(value: float, decimals: int = 1) -> str`
Format a fraction (0.0–1.0) as a percentage string.

### `format_count(n: int) -> str`
Format an integer with comma separators.

### `truncate_text(text: str, max_len: int = 80) -> str`
Truncate text to max_len characters, appending `...` if needed.

### `extract_snippet(text: str, terms: list[str], context: int = 40) -> str`
Extract a snippet from `text` centred on the first occurrence of any search term.

### `highlight_terms(text: str, terms: list[str]) -> str`
Wrap matching terms in `**...**` for terminal bold rendering.

### `TableFormatter`
Formats a list of dicts as a fixed-width ASCII table. Key methods:
- `add_column(name, key, width, align)` — define columns
- `format(rows)` — return formatted table string
- `print(rows)` — print directly to stdout

### `ReportFormatter`
Generates structured text reports with sections, tables, and summaries.
Key methods:
- `section(title)`, `table(headers, rows)`, `summary(stats_dict)`, `render()`

---

## utils/config.py

### `DatabaseConfig`
Configuration for the SQLite database.

```python
from utils import DatabaseConfig
cfg = DatabaseConfig(db_path="dod_budget.sqlite")
cfg.db_path       # Path to database file
cfg.docs_dir      # Path to documents directory
```

### `DownloadConfig`
Configuration for the downloader.

```python
from utils import DownloadConfig
cfg = DownloadConfig()
cfg.output_dir    # Download destination directory
cfg.delay         # Inter-file delay in seconds
cfg.timeout       # HTTP timeout in seconds
```

### `KnownValues`
Static lookup tables for DoD-specific values.

```python
from utils import KnownValues
KnownValues.is_valid_org("Army")     # True
KnownValues.get_org_code("Navy")     # "N"
KnownValues.is_valid_exhibit_type("p1")  # True
KnownValues.get_exhibit_description("r1")  # "Research, Development, Test & Evaluation"
```

### `ColumnMapping`
Maps raw spreadsheet headers to canonical field names.

```python
from utils import ColumnMapping
ColumnMapping.normalize_header("FY 2026 Budget Estimate")  # "amount_fy2026_request"
ColumnMapping.get_mapping("p1")  # dict of header patterns for P-1 exhibits
```

### `FilePatterns`
Identifies DoD budget documents from filenames.

```python
from utils import FilePatterns
FilePatterns.is_budget_document("fy2026_army_p1.xlsx")  # True
FilePatterns.get_fiscal_year_from_filename("fy2026_r1_army.xlsx")  # "2026"
```

---

## utils/http.py

### `RetryStrategy`
Configures exponential-backoff retry behavior for HTTP requests.

```python
from utils import RetryStrategy
strategy = RetryStrategy(max_retries=3, backoff_factor=2.0)
# Retries up to 3 times with 2s, 4s, 8s delays
```

### `SessionManager`
Manages a `requests.Session` with connection pooling and retry adapters.

```python
from utils import SessionManager
mgr = SessionManager()
session = mgr.get_session()
```

### `TimeoutManager`
Tracks per-domain response times and returns adaptive timeout values. Favors
shorter timeouts for fast domains and longer timeouts for slow ones.

### `CacheManager`
Caches HTTP responses to disk to avoid re-fetching discovery pages.

### `download_file(session, url, dest_path, ...) -> bool`
Download a file from `url` to `dest_path`, checking existing size before downloading.

---

## utils/manifest.py

### `Manifest`
Tracks all files in a download session with status, size, and SHA-256 hash.

```python
from utils import Manifest
m = Manifest(output_dir="DoD_Budget_Documents")
m.add_file(url="...", filename="fy2026_p1.xlsx", source="army",
           fiscal_year="2026", extension=".xlsx")
m.save()  # writes manifest.json
m.load()  # loads existing manifest.json
```

### `ManifestEntry`
Single file entry: `url`, `filename`, `source`, `fiscal_year`, `extension`,
`file_size`, `sha256_hash`, `status`.

### `compute_file_hash(file_path: Path) -> str`
Compute SHA-256 hash of a file (streaming, memory-efficient).

---

## utils/progress.py

### `ProgressTracker` (abstract base class)
Interface for progress tracking. Subclasses implement `update()` and `finish()`.

```python
from utils import TerminalProgressTracker
tracker = TerminalProgressTracker(total_items=100)
for item in items:
    process(item)
    tracker.mark_completed()
tracker.finish()
```

### `TerminalProgressTracker`
Prints ASCII progress bars and statistics to stdout. Updates every N items
(configurable, default 10) to avoid flooding output.

### `SilentProgressTracker`
No-op tracker for tests or suppressed output.

### `FileProgressTracker`
Extends `TerminalProgressTracker` with byte-level tracking for file downloads.

---

## utils/validation.py

### `ValidationIssue`
Represents a single issue found by a validation check.

### `ValidationResult`
Collects issues from all checks; provides `is_valid()`, `error_count()`,
`warning_count()`, `summary_text()`, and `to_dict()`.

### `ValidationRegistry`
Register and run named validation functions against a database connection.

```python
from utils import ValidationRegistry, ValidationResult

registry = ValidationRegistry()
registry.register("check_duplicates", my_check_fn)
result = registry.run_all(conn)
print(result.summary_text())
```

### Standalone validators

| Function | Description |
|----------|-------------|
| `is_valid_fiscal_year(year)` | True if year is 2000–2099 |
| `is_valid_amount(value)` | True if non-negative and ≤ 999 billion |
| `is_valid_organization(org, known_orgs)` | True if non-empty string and in known set |
| `is_valid_exhibit_type(exhibit, known_exhibits)` | True if 1–3 alphanumeric chars and in known set |

---

## Performance Notes

Several utilities were added as part of the Phase 1 optimization pass (see
[Performance Optimizations](Performance-Optimizations.md)):

- `safe_float` — pre-compiled regex patterns replace inline operations (~10-15% faster)
- `normalize_whitespace` — pre-compiled WHITESPACE pattern (~10% faster)
- `batch_insert` — batching 1000 rows per execute call vs. single-row inserts (~40% faster)
- `init_pragmas` — WAL mode + large cache significantly reduces lock contention
- `disable_fts5_triggers` — disabling auto-sync during bulk insert, then re-enabling
  is ~30% faster than per-row trigger updates
