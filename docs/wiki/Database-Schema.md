# Database Schema

<!-- TODO [Steps 2.A1–2.A5]: Expand after the production schema is finalized.
     The current schema below reflects the development/prototype structure
     from build_budget_db.py. -->

Documentation of the SQLite database schema used by the DoD Budget Analysis
tool. The database is created by `build_budget_db.py` and queried by
`search_budget.py` and `validate_budget_db.py`.

---

## Entity Relationship Overview

```
ingested_files  ──┐
                  ├──>  budget_lines  ──>  budget_lines_fts (FTS5)
data_sources    ──┘
                  ├──>  pdf_pages     ──>  pdf_pages_fts (FTS5)
```

- **`budget_lines`** — Structured data extracted from Excel exhibits
- **`pdf_pages`** — Full-text content extracted from PDF documents
- **`ingested_files`** — Metadata tracking which files have been processed
- **`data_sources`** — Registry of download sources and freshness info

---

## Tables

### `budget_lines`

Primary table for structured budget data. Each row is a single line item
extracted from an Excel exhibit. See the [Data Dictionary](Data-Dictionary.md)
for complete field definitions.

- **Primary key:** `id` (auto-increment)
- **27 columns** covering identification, organizational hierarchy, dollar
  amounts, quantities, and metadata

### `budget_lines_fts`

FTS5 virtual table for full-text search over budget line items. Indexed
fields: `account_title`, `budget_activity_title`, `sub_activity_title`,
`line_item_title`, `organization_name`.

Kept in sync via `AFTER INSERT` / `AFTER DELETE` triggers.

### `pdf_pages`

Page-level text and table data extracted from PDF documents.

- **Primary key:** `id` (auto-increment)
- Contains raw text, table detection flag, and extracted table JSON

### `pdf_pages_fts`

FTS5 virtual table for full-text search over PDF content. Indexed fields:
`page_text`, `source_file`, `table_data`.

### `ingested_files`

Tracks which files have been processed for incremental update support.

- **Primary key:** `file_path`
- Records file size, modification time, ingestion timestamp, row count, and
  status (`ok` or error description)

### `data_sources`

Registry of download sources for provenance tracking.

- **Primary key:** `source_id`
- Tracks source name, URL, fiscal year, freshness, and file counts

---

## Indexes

<!-- TODO: Document indexes after performance optimization (Step 4.C4). -->

Currently the schema relies on FTS5 indexes for text search and SQLite's
implicit primary key indexes. Additional indexes may be added as query
patterns emerge.

---

## Full-Text Search

The database uses SQLite FTS5 for full-text search with two virtual tables:

- **`budget_lines_fts`** — Searches across budget line item titles and
  organization names
- **`pdf_pages_fts`** — Searches across PDF page text and table data

Both are content-synced with their source tables via triggers.

---

## Pragmas

```sql
PRAGMA journal_mode = WAL;       -- Write-Ahead Logging for concurrent reads
PRAGMA synchronous = NORMAL;     -- Balance between safety and speed
```

---

## Migrations

<!-- TODO [Step 2.A5]: Document migration strategy (Alembic or versioned SQL scripts). -->

Currently the schema is created inline in `build_budget_db.py`'s
`create_database()` function. A formal migration system will be added in
Phase 2.
