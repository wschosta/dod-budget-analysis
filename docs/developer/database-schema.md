# Database Schema

Documentation of the SQLite database schema used by the DoD Budget Analysis
project. The database is created by `build_budget_db.py`, enriched by
`enrich_budget_db.py`, validated by `validate_budget_data.py` and
`validate_budget_db.py`, and served by the FastAPI application in `api/`.

---

## Entity Relationship Overview

```
                    ingested_files ──┐
                                     ├──> budget_lines ──> budget_lines_fts (FTS5)
                    data_sources   ──┘
                                     ├──> pdf_pages    ──> pdf_pages_fts (FTS5)

Reference Tables:
  services_agencies  |  exhibit_types  |  appropriation_titles  |  budget_cycles

Enrichment Tables:
  pe_index  |  pe_descriptions  |  pe_tags  |  pe_lineage

Schema Versioning:
  schema_version
```

---

## Core Tables

### `budget_lines`

Primary table for structured budget data. Each row is a single line item
extracted from an Excel exhibit. See the
[Data Dictionary](../user-guide/data-dictionary.md) for complete field definitions.

- **Primary key:** `id` (auto-increment)
- **27 columns** covering identification, organizational hierarchy, dollar
  amounts, quantities, and metadata

Key columns include:

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Auto-increment primary key |
| `source_file` | TEXT | Filename of the source Excel document |
| `exhibit_type` | TEXT | Exhibit type code (e.g., `p1`, `r2`) |
| `fiscal_year` | TEXT | Fiscal year label (e.g., `FY 2026`) |
| `organization_name` | TEXT | Service or agency name |
| `pe_number` | TEXT | Program element number |
| `line_item_title` | TEXT | Budget line item title |
| `appropriation_code` | TEXT | Appropriation code |
| `appropriation_title` | TEXT | Appropriation title |
| `amount_unit` | TEXT | Unit of amounts (typically `$K`) |
| `amount_fy2024_actual` | REAL | FY2024 actual amount |
| `amount_fy2025_enacted` | REAL | FY2025 enacted amount |
| `amount_fy2026_request` | REAL | FY2026 requested amount |

### `budget_lines_fts`

FTS5 virtual table for full-text search over budget line items. Indexed
fields: `account_title`, `budget_activity_title`, `sub_activity_title`,
`line_item_title`, `organization_name`.

Kept in sync via `AFTER INSERT` / `AFTER DELETE` triggers.

### `pdf_pages`

Page-level text and table data extracted from PDF documents.

- **Primary key:** `id` (auto-increment)
- Contains raw text, table detection flag, and extracted table JSON

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Auto-increment primary key |
| `source_file` | TEXT | Filename of the source PDF |
| `page_number` | INTEGER | Page number within the PDF |
| `page_text` | TEXT | Extracted text content |
| `has_table` | INTEGER | Boolean flag: 1 if tables were detected |
| `table_data` | TEXT | JSON representation of extracted tables |

### `pdf_pages_fts`

FTS5 virtual table for full-text search over PDF content. Indexed fields:
`page_text`, `source_file`, `table_data`.

### `ingested_files`

Tracks which files have been processed for incremental update support.

- **Primary key:** `file_path`
- Records file hash, size, modification time, ingestion timestamp, row count,
  and status (`ok` or error description)

| Column | Type | Description |
|--------|------|-------------|
| `file_path` | TEXT | Primary key; relative path to the source file |
| `file_size` | INTEGER | File size in bytes |
| `file_hash` | TEXT | SHA-256 hash of the file |
| `modified_time` | TEXT | File modification timestamp |
| `ingested_at` | TEXT | When the file was processed |
| `row_count` | INTEGER | Number of rows extracted |
| `file_type` | TEXT | File type (e.g., `xlsx`, `pdf`) |
| `status` | TEXT | Processing status (`ok` or error message) |

### `data_sources`

Registry of download sources for provenance tracking.

- **Primary key:** `source_id`
- Tracks source name, URL, fiscal year, freshness, and file counts

---

## Reference Tables

Reference tables provide normalized lookup data for services, exhibit types,
appropriation titles, and budget cycles. They are populated by
`backfill_reference_tables.py` and seeded during schema creation by
`schema_design.py`.

### `services_agencies`

Canonical list of DoD services and agencies.

| Column | Type | Description |
|--------|------|-------------|
| `code` | TEXT | Short code (e.g., `Army`, `Navy`) |
| `full_name` | TEXT | Full name (e.g., `Department of the Army`) |
| `category` | TEXT | Category (e.g., `Military Department`, `Defense Agency`) |

### `exhibit_types`

Catalog of budget exhibit types (P-1, P-5, R-1, R-2, O-1, etc.).

| Column | Type | Description |
|--------|------|-------------|
| `code` | TEXT | Exhibit type code (e.g., `p1`, `r2`) |
| `display_name` | TEXT | Human-readable name |
| `exhibit_class` | TEXT | Classification (e.g., `procurement`, `rdte`) |
| `description` | TEXT | Detailed description |

### `appropriation_titles`

Standardized appropriation titles mapped to codes.

### `budget_cycles`

Tracks budget submission cycles (President's Budget, amended submissions, etc.).

---

## Enrichment Tables

Enrichment tables are populated by `enrich_budget_db.py` and provide
additional context for program elements (PEs).

### `pe_index`

Master index of all program elements discovered across budget documents.

| Column | Type | Description |
|--------|------|-------------|
| `pe_number` | TEXT | Primary key; program element number |
| `pe_title` | TEXT | Program element title |
| `organization_name` | TEXT | Owning service or agency |
| `appropriation_title` | TEXT | Associated appropriation |
| `first_seen_fy` | TEXT | Earliest fiscal year with data |
| `last_seen_fy` | TEXT | Most recent fiscal year with data |

### `pe_descriptions`

Extended narrative descriptions for program elements, extracted from
R-2 exhibits and PDF documents.

| Column | Type | Description |
|--------|------|-------------|
| `pe_number` | TEXT | Foreign key to `pe_index` |
| `description` | TEXT | Narrative description text |
| `source` | TEXT | Source of the description (e.g., `r2_exhibit`, `pdf`) |

### `pe_tags`

Keyword tags and categorizations applied to program elements for
enhanced searchability and filtering.

| Column | Type | Description |
|--------|------|-------------|
| `pe_number` | TEXT | Foreign key to `pe_index` |
| `tag` | TEXT | Tag value (e.g., `hypersonics`, `cyber`, `space`) |
| `tag_type` | TEXT | Tag category (e.g., `domain`, `technology`, `mission`) |

### `pe_lineage`

Tracks changes to program elements over time, including merges, splits,
renumbering, and other organizational changes.

| Column | Type | Description |
|--------|------|-------------|
| `pe_number` | TEXT | Current program element number |
| `predecessor_pe` | TEXT | Previous program element number |
| `change_type` | TEXT | Type of change (e.g., `rename`, `merge`, `split`) |
| `effective_fy` | TEXT | Fiscal year the change took effect |

---

## Schema Versioning

The database schema is versioned via the `schema_version` table, managed by
`schema_design.py`.

### `schema_version`

| Column | Type | Description |
|--------|------|-------------|
| `version` | INTEGER | Current schema version number |
| `applied_at` | TEXT | Timestamp when this version was applied |
| `description` | TEXT | Description of the migration |

### Migration System

Schema migrations are implemented in the `migrate()` function within
`schema_design.py`. Each migration:

1. Checks the current `schema_version`
2. Applies incremental DDL changes (new tables, columns, indexes)
3. Updates the `schema_version` row with the new version number

To apply migrations:

```python
from schema_design import migrate
import sqlite3

conn = sqlite3.connect("dod_budget.sqlite")
migrate(conn)
```

Migrations are idempotent -- running `migrate()` on an already-current
database is a no-op. The full pipeline (`run_pipeline.py`) calls `migrate()`
automatically before ingestion.

---

## Indexes

The schema includes several index types:

- **FTS5 indexes** on `budget_lines_fts` and `pdf_pages_fts` for full-text search
- **Primary key indexes** on all tables (implicit)
- **Additional B-tree indexes** on frequently filtered columns such as
  `fiscal_year`, `organization_name`, `exhibit_type`, and `pe_number`

Indexes are defined in `schema_design.py` and applied during schema creation
and migration.

---

## Full-Text Search

The database uses SQLite FTS5 for full-text search with two virtual tables:

- **`budget_lines_fts`** -- Searches across budget line item titles and
  organization names
- **`pdf_pages_fts`** -- Searches across PDF page text and table data

Both are content-synced with their source tables via triggers. The API's
`/api/v1/search` endpoint uses BM25 ranking for relevance scoring.

For details on the FTS5 implementation rationale, see
[ADR 003: FTS5 Search](../decisions/003-fts5-search.md).

---

## Pragmas

The application configures SQLite for performance and concurrent access:

```sql
PRAGMA journal_mode = WAL;          -- Write-Ahead Logging for concurrent reads
PRAGMA synchronous = NORMAL;        -- Balance between safety and speed
PRAGMA cache_size = -128000;        -- 128 MB page cache
PRAGMA temp_store = MEMORY;         -- Use RAM for temporary tables
PRAGMA mmap_size = 30000000;        -- Memory-mapped I/O for faster reads
```

These are applied by `utils/database.py:init_pragmas()` on every connection.
WAL mode is particularly important for the API server, which handles concurrent
read requests while the database may be updated by the data pipeline.

---

## Database Files

| File | Description |
|------|-------------|
| `dod_budget.sqlite` | Primary database file |
| `dod_budget.sqlite-wal` | Write-Ahead Log (created automatically in WAL mode) |
| `dod_budget.sqlite-shm` | Shared memory file (created automatically in WAL mode) |

The entire application state lives in `dod_budget.sqlite`. Back it up by
copying the file (see [Deployment](deployment.md) for backup procedures).

---

## Related Documentation

- [API Reference](api-reference.md) -- How the database is queried via the REST API
- [Architecture Overview](architecture.md) -- System design and data flow
- [Utilities Reference](utilities.md) -- Database helper functions in `utils/database.py`
- [Deployment](deployment.md) -- Database path configuration and backup procedures
- [Performance](performance.md) -- Database-level performance optimizations
