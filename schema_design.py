"""
Canonical Schema Design — Steps 2.A1 through 2.A5

This module will define the production-quality relational schema for the DoD
budget database.  The current build_budget_db.py uses a flat schema (one
budget_lines table, one pdf_pages table, one ingested_files table).  This
redesign normalizes the data for proper querying and cross-referencing.

Current schema (build_budget_db.py):
    budget_lines: source_file, sheet_name, fiscal_year, exhibit_type, category,
        organization_name, account, account_title, budget_activity,
        budget_activity_title, line_item, line_item_title,
        amount_previous_fy, amount_current_fy, amount_budget_year, row_number
    pdf_pages: source_file, page_number, content, tables
    ingested_files: source_file, file_hash, file_size, file_type, row_count,
        ingested_at

──────────────────────────────────────────────────────────────────────────────
TODOs — Step 2.A (Schema Design)
──────────────────────────────────────────────────────────────────────────────

TODO 2.A1-a: Design the core fact table (budget_line_items).
    Columns: id, fiscal_year_id (FK), service_id (FK), appropriation_id (FK),
    budget_activity_code, budget_activity_title, pe_number, line_item_number,
    line_item_title, exhibit_type_id (FK), amount_type (enum: BA/Appn/Outlay),
    amount_thousands (integer), currency_year, budget_cycle (PB/enacted/amended),
    source_document_id (FK), row_hash (for dedup).
    Token-efficient tip: write the CREATE TABLE as SQL, not ORM — we can add
    SQLAlchemy models later.  ~30 lines of DDL.

TODO 2.A1-b: Design fiscal year handling.
    Decide: do we store prior-year, current-year, and budget-year amounts as
    separate rows (normalized) or separate columns (denormalized)?
    Recommendation for the TODO: write both schemas as SQL, add a comment
    block listing pros/cons of each, and pick one.  ~20 lines.

TODO 2.A2-a: Create reference table — services_agencies.
    Columns: id, code (e.g., "ARMY"), name (e.g., "Department of the Army"),
    abbreviation, parent_id (for sub-agencies under a military department).
    Seed data: Army, Navy, Marine Corps, Air Force, Space Force, OSD,
    Defense-Wide agencies, Joint Staff, etc.
    Token-efficient tip: write as a single INSERT with VALUES list.  ~30 rows.

TODO 2.A2-b: Create reference table — appropriation_titles.
    Columns: id, code, title, service_id (FK), description.
    Seed data derived from exhibit files: "Procurement", "RDT&E",
    "Military Construction", "O&M", "Military Personnel", etc.
    Token-efficient tip: enumerate ~20 major appropriation categories; details
    can be backfilled from actual data during loading.

TODO 2.A2-c: Create reference table — exhibit_types.
    Columns: id, code (e.g., "P-1"), name, description, is_summary (bool).
    Seed data: the 7+ types from EXHIBIT_TYPES in build_budget_db.py plus any
    additions from exhibit_catalog.py.

TODO 2.A2-d: Create reference table — budget_cycles.
    Columns: id, code, name.  Values: "PB" (President's Budget), "ENACTED",
    "CR" (Continuing Resolution), "AMENDED", "SUPPLEMENTAL".

TODO 2.A3-a: Evaluate FTS strategy and document the decision.
    Write a decision record (as a comment block in this file) evaluating:
    1. SQLite FTS5 — zero deployment complexity, good for single-node
    2. PostgreSQL tsvector — better ranking, built-in if we move to Postgres
    3. Meilisearch/Typesense — best UX but adds an external service
    Score each on: deployment complexity, query quality, maintenance burden,
    and scale ceiling.  Recommend one for initial deployment.
    Token-efficient tip: this is a ~40-line prose block, no code needed.

TODO 2.A4-a: Design document_sources table.
    Columns: id, file_path, original_url, file_hash, file_size_bytes,
    file_type (xlsx/pdf/csv), fiscal_year, service_id (FK), exhibit_type_id (FK),
    download_date, ingested_at, row_count, status (enum: ok/error/skipped).
    This replaces the current ingested_files table with richer metadata.

TODO 2.A4-b: Design pdf_content table.
    Columns: id, document_source_id (FK), page_number, raw_text,
    extracted_tables (JSON), has_useful_content (bool), ocr_needed (bool).
    Index: FTS5 on raw_text.

TODO 2.A5-a: Set up migration framework.
    Create a migrations/ directory.  Write 001_initial_schema.sql containing
    all CREATE TABLE statements from the TODOs above.  Add a
    schema_version table (version int, applied_at timestamp) and a small
    Python function migrate(db_path) that applies unapplied migrations in order.
    Token-efficient tip: don't use Alembic yet — a simple numbered-SQL-files
    approach is sufficient and avoids adding SQLAlchemy as a dependency.
    ~60 lines of Python + ~80 lines of SQL.

TODO 2.A5-b: Write migration 002 for FTS5 virtual tables.
    After the base tables are created, add FTS5 virtual tables and triggers
    to keep them in sync.  Separate migration so FTS can be rebuilt independently.


──────────────────────────────────────────────────────────────────────────────
TODOs — Step 2.B (Data Loading & Quality)
──────────────────────────────────────────────────────────────────────────────

TODO 2.B1-a: Refactor build_budget_db.py to target the new schema.
    Replace the flat INSERT into budget_lines with lookups into reference tables
    (get-or-create pattern for services, appropriations, exhibit types) and
    INSERT into the normalized budget_line_items table.
    Dependency: TODO 2.A1-a and 2.A2-* must be done first.
    Token-efficient tip: change ingest_excel_file() — the rest of the pipeline
    stays the same.  ~50 lines changed.

TODO 2.B1-b: Backfill reference tables from existing data.
    Write a one-time script that reads the current flat budget_lines table,
    extracts unique service names, appropriations, exhibit types, and populates
    the reference tables.  This bootstraps the lookup tables from real data.
    ~40 lines.

TODO 2.B2-a: Cross-service reconciliation — design the check.
    For each fiscal year, compare: sum of all service-level P-1 exhibits vs.
    the Comptroller summary P-1 total.  Output a reconciliation report with
    service-level and aggregate deltas.
    Token-efficient tip: this is a single SQL query with GROUP BY and a
    comparison to a known total.  ~25 lines including the report output.

TODO 2.B2-b: Cross-exhibit reconciliation.
    Verify that P-1 procurement totals by service match the sum of P-5 detail
    line items for the same service and FY.  Same for R-1 vs. R-2, O-1 vs. O-1
    detail.  Output discrepancies.

TODO 2.B3-a: Generate data-quality report after each load.
    After build_database() completes, emit a JSON report with:
    - Row counts by (service, fiscal_year, exhibit_type)
    - Null/zero percentages for amount columns
    - Any validation warnings from validate_budget_data.py
    Write to data_quality_report.json.
    Dependency: validate_budget_data.py TODOs should be mostly done.

TODO 2.B4-a: Script the data refresh workflow.
    Write a single refresh_data.sh (or .py) that:
    1. Runs dod_budget_downloader.py for the target FY
    2. Runs build_budget_db.py (incremental mode)
    3. Runs validate_budget_data.py
    4. Generates the data quality report
    5. Prints a summary to stdout
    Token-efficient tip: this is a ~30-line shell script or Python subprocess
    wrapper.  No complex logic.
"""

# Placeholder — schema DDL will be written here or in migrations/
