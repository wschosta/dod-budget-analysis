"""
Canonical Schema Design — Steps 2.A1 through 2.A5

**Status:** Phase 2 Planning (Phase 1 currently in progress)

This module will define the production-quality relational schema for the DoD
budget database. The current build_budget_db.py uses a flat schema (one
budget_lines table, one pdf_pages table, one ingested_files table). This
redesign will normalize the data for proper querying and cross-referencing
in Phase 2.

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

TODO 2.A1-a [Complexity: MEDIUM] [Tokens: ~2500] [User: NO]
    Design the core fact table (budget_line_items) as SQL DDL.
    Columns: id, fiscal_year_id (FK), service_id (FK), appropriation_id (FK),
    budget_activity_code, budget_activity_title, pe_number, line_item_number,
    line_item_title, exhibit_type_id (FK), amount_type (enum: BA/Appn/Outlay),
    amount_thousands (integer), currency_year, budget_cycle (PB/enacted/amended),
    source_document_id (FK), row_hash (for dedup).
    Steps:
      1. Write CREATE TABLE budget_line_items as SQL (~30 lines DDL)
      2. Add composite indexes for: (fiscal_year_id, service_id),
         (pe_number), (exhibit_type_id, fiscal_year_id)
      3. Add CHECK constraints for amount_type enum values
    Success: DDL runs without error; schema supports all Phase 1 data fields.

TODO 2.A1-b [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Design fiscal year handling — normalized vs. denormalized.
    Steps:
      1. Write both schemas as SQL DDL (separate rows vs. separate columns)
      2. Add pros/cons comment block for each approach
      3. Pick one approach; document rationale
    Recommendation: normalized (separate rows) — easier aggregation.
    Success: Clear decision documented with chosen DDL.

TODO 2.A2-a [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Create reference table — services_agencies + seed data (~15 rows).
    Steps:
      1. Write CREATE TABLE (id, code, name, abbreviation, parent_id)
      2. Write INSERT VALUES for: Army, Navy, USMC, Air Force, Space Force,
         OSD, DLA, MDA, SOCOM, DHA, DISA, NGB, Joint Staff, etc.
    Success: Table created with all known DoD components.

TODO 2.A2-b [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Create reference table — appropriation_titles + seed data (~20 rows).
    Steps:
      1. Write CREATE TABLE (id, code, title, service_id FK, description)
      2. Enumerate: Procurement, RDT&E, MilCon, O&M, Military Personnel, etc.
    Success: Table covers all appropriation categories found in exhibit data.

TODO 2.A2-c [Complexity: LOW] [Tokens: ~1000] [User: NO]
    Create reference table — exhibit_types + seed data.
    Steps:
      1. Write CREATE TABLE (id, code, name, description, is_summary)
      2. Seed from exhibit_catalog.EXHIBIT_CATALOG (10+ types)
    Success: All exhibit types from catalog have reference table entries.

TODO 2.A2-d [Complexity: LOW] [Tokens: ~500] [User: NO]
    Create reference table — budget_cycles (5 rows).
    Steps:
      1. Write CREATE TABLE (id, code, name)
      2. INSERT: PB, ENACTED, CR, AMENDED, SUPPLEMENTAL
    Success: Table exists with 5 rows.

TODO 2.A3-a [Complexity: LOW] [Tokens: ~2000] [User: NO]
    Evaluate FTS strategy and document the decision.
    Steps:
      1. Score SQLite FTS5, PostgreSQL tsvector, Meilisearch/Typesense
      2. Criteria: deployment complexity, query quality, maintenance, scale
      3. Write ~40-line decision record as comment block in this file
    Recommendation: SQLite FTS5 for V1 (zero added infrastructure).
    Success: Decision documented with scoring matrix.

TODO 2.A4-a [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Design document_sources table (enhanced ingested_files).
    Steps:
      1. Write CREATE TABLE: id, file_path, original_url, file_hash,
         file_size_bytes, file_type, fiscal_year, service_id FK,
         exhibit_type_id FK, download_date, ingested_at, row_count, status
    Success: DDL covers all provenance metadata.

TODO 2.A4-b [Complexity: LOW] [Tokens: ~1000] [User: NO]
    Design pdf_content table (enhanced pdf_pages).
    Steps:
      1. Write CREATE TABLE: id, document_source_id FK, page_number,
         raw_text, extracted_tables JSON, has_useful_content, ocr_needed
      2. Plan FTS5 virtual table for raw_text
    Success: DDL supports rich PDF metadata.

TODO 2.A5-a [Complexity: HIGH] [Tokens: ~5000] [User: NO]
    Set up migration framework with numbered SQL files.
    Steps:
      1. Create migrations/ directory
      2. Write 001_initial_schema.sql (~80 lines) with all tables above
      3. Add schema_version table (version int, applied_at timestamp)
      4. Write migrate(db_path) function (~60 lines Python) that reads
         migrations/*.sql, compares to schema_version, applies in order
      5. No Alembic/SQLAlchemy — keep it simple
    Success: migrate() creates full schema from scratch or applies deltas.

TODO 2.A5-b [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Write migration 002 for FTS5 virtual tables + sync triggers.
    Steps:
      1. Write 002_fts5_indexes.sql with CREATE VIRTUAL TABLE statements
      2. Add INSERT/UPDATE/DELETE triggers to keep FTS in sync
    Success: FTS5 tables auto-sync; can be rebuilt independently.


──────────────────────────────────────────────────────────────────────────────
TODOs — Step 2.B (Data Loading & Quality)
──────────────────────────────────────────────────────────────────────────────

TODO 2.B1-a [Complexity: HIGH] [Tokens: ~4000] [User: NO]
    Refactor build_budget_db.py to target the new normalized schema.
    Dependency: TODO 2.A1-a and 2.A2-* must be done first.
    Steps:
      1. In ingest_excel_file(), replace flat INSERT into budget_lines
         with get-or-create lookups into reference tables
      2. INSERT into normalized budget_line_items table
      3. Keep rest of pipeline (discovery, PDF, FTS) unchanged
      4. Run test_pipeline.py to verify no regressions
    Success: Database uses normalized schema; all existing tests pass.

TODO 2.B1-b [Complexity: MEDIUM] [Tokens: ~2000] [User: NO]
    Backfill reference tables from existing flat data.
    Steps:
      1. Write one-time script (~40 lines) that reads budget_lines
      2. Extract unique: organization_name → services, exhibit_type → exhibit_types,
         account/account_title → appropriation_titles
      3. INSERT IGNORE into reference tables
    Success: Reference tables populated from real data.

TODO 2.B2-a [Complexity: MEDIUM] [Tokens: ~2000] [User: YES — needs real data]
    Cross-service reconciliation check.
    Steps:
      1. SQL: For each FY, sum service-level P-1 totals
      2. Compare against Comptroller summary P-1 total
      3. Output reconciliation report with deltas per service
    Success: Discrepancies documented; within expected tolerance.

TODO 2.B2-b [Complexity: MEDIUM] [Tokens: ~2000] [User: YES — needs real data]
    Cross-exhibit reconciliation (P-1 vs P-5, R-1 vs R-2, etc.).
    Steps:
      1. For each service+FY: compare P-1 total vs sum(P-5 details)
      2. Same for R-1 vs R-2, O-1 vs O-1 detail
      3. Output discrepancy report
    Success: Summary-vs-detail deltas within expected tolerance.

TODO 2.B3-a [Complexity: MEDIUM] [Tokens: ~2000] [User: NO]
    Generate data-quality report (JSON) after each load.
    Steps:
      1. After build_database() completes, gather row counts by
         (service, fiscal_year, exhibit_type)
      2. Compute null/zero percentages for amount columns
      3. Include validation warnings from validate_budget_data.py
      4. Write to data_quality_report.json
    Success: JSON report generated automatically after each build.

TODO 2.B4-a [Complexity: LOW] [Tokens: ~500] [User: NO]
    DONE — refresh_data.py already implements this workflow.
    Verify refresh_data.py calls the correct scripts and works end-to-end.
    Steps:
      1. Review refresh_data.py stages match this spec
      2. Run `python refresh_data.py --dry-run --years 2026` to verify
    Success: Dry-run completes with all 4 stages reported.
"""

# Placeholder — schema DDL will be written here or in migrations/
