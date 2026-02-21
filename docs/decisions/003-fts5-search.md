# ADR-003: SQLite FTS5 for Full-Text Search

**Date:** 2026-02-18
**Status:** Accepted
**Deciders:** Project team

## Context

The DoD Budget Analysis database needs full-text search to allow users to find budget line items and PDF document content by keyword. The search must support:
- Keyword queries across budget line item titles and descriptions
- PDF document text search
- BM25 relevance ranking
- Phrase search (exact match for multi-word queries)
- Combined search with structured filters (fiscal year, service, exhibit type)

Three approaches were evaluated:
1. **SQLite FTS5** — Built-in full-text search extension
2. **PostgreSQL with tsvector/tsquery** — Requires migrating from SQLite
3. **External search engine** (Meilisearch, Elasticsearch) — Separate service

## Decision

Use **SQLite FTS5** for full-text search, with content-synced virtual tables and BM25 ranking.

## Rationale

1. **Zero Additional Infrastructure** — FTS5 is built into SQLite. No separate search service to deploy, configure, or maintain. The entire application remains a single SQLite file + Python process.

2. **Data Locality** — Search indexes live in the same database file as the source data. No synchronization lag between the data store and the search index.

3. **Sufficient for Scale** — The dataset (tens of thousands of budget lines, hundreds of thousands of PDF pages) is well within SQLite FTS5's performance envelope. Queries return in single-digit milliseconds.

4. **BM25 Ranking** — FTS5 includes built-in BM25 relevance scoring, providing good result quality without custom ranking logic.

5. **Operational Simplicity** — Deployment requires only copying a single `.sqlite` file. No Elasticsearch cluster, no PostgreSQL instance, no network dependencies.

### Why Not PostgreSQL?

- Would require migrating the entire database layer from SQLite to PostgreSQL.
- Adds infrastructure complexity (separate database service, connection management).
- Overkill for the current dataset size and query patterns.
- PostgreSQL's `tsvector`/`tsquery` is more powerful but not needed here.

### Why Not Meilisearch/Elasticsearch?

- Adds a separate service to deploy and maintain.
- Requires data synchronization between SQLite and the search engine.
- Introduces network latency for search queries.
- The dataset is small enough that SQLite FTS5 performs well.

## Implementation

### Virtual Tables

Two FTS5 content-synced virtual tables:

| FTS Table | Source Table | Indexed Columns |
|-----------|-------------|-----------------|
| `budget_lines_fts` | `budget_lines` | account_title, budget_activity_title, sub_activity_title, line_item_title, organization_name |
| `pdf_pages_fts` | `pdf_pages` | page_text, source_file, table_data |

### Sync Mechanism

Content-synced via `AFTER INSERT` / `AFTER UPDATE` / `AFTER DELETE` triggers on the source tables. During bulk inserts, triggers are temporarily dropped and replaced with a batch `INSERT INTO ... SELECT FROM` rebuild for performance (30-40% faster).

### Query Pattern

```sql
SELECT bl.*, bts.rank
FROM budget_lines bl
JOIN budget_lines_fts bts ON bl.id = bts.rowid
WHERE budget_lines_fts MATCH '"missile defense"'
ORDER BY bts.rank;
```

### Input Sanitization

User search input is sanitized via `sanitize_fts5_query()` in `utils/strings.py`, which strips FTS5 operator characters and wraps terms in double quotes to prevent injection.

## Consequences

- **Positive:** Zero infrastructure overhead. Single-file database includes search indexes.
- **Positive:** Millisecond query times for the current dataset size.
- **Positive:** BM25 ranking provides relevant results out of the box.
- **Positive:** Atomic updates — search index is always consistent with source data.
- **Negative:** FTS5 lacks advanced features like typo tolerance, faceted search, and synonyms.
- **Negative:** Performance may degrade if the dataset grows to millions of rows.
- **Negative:** No built-in highlighting (implemented manually in `utils/formatting.py`).

### When to Reconsider

Migrate to an external search engine if:
- Dataset grows beyond 1M+ budget lines or 10M+ PDF pages
- Users require typo tolerance, synonym expansion, or faceted search
- Multi-user write concurrency becomes a bottleneck
- The application moves to PostgreSQL for other reasons

## References

- [SQLite FTS5 Documentation](https://www.sqlite.org/fts5.html)
- [BM25 Ranking in FTS5](https://www.sqlite.org/fts5.html#the_bm25_function)
