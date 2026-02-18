"""
Canonical Schema Design — Steps 2.A1 through 2.A5

**Status:** Phase 2 Planning (Phase 1 currently in progress)

This module defines the production-quality relational schema for the DoD
budget database. The current build_budget_db.py uses a flat schema (one
budget_lines table, one pdf_pages table, one ingested_files table). This
redesign normalizes the data for proper querying and cross-referencing
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

DONE 2.A1-a  Core fact table budget_line_items DDL — see SCHEMA_DDL below.
DONE 2.A1-b  Fiscal-year strategy: normalized (separate rows) chosen — see note.
DONE 2.A2-a  services_agencies reference table + seed data.
DONE 2.A2-b  appropriation_titles reference table + seed data.
DONE 2.A2-c  exhibit_types reference table seeded from exhibit_catalog.
DONE 2.A2-d  budget_cycles reference table (5 rows).
DONE 2.A3-a  FTS strategy decision: SQLite FTS5 — see FTS_DECISION below.
DONE 2.A4-a  document_sources table DDL.
DONE 2.A4-b  pdf_content table DDL with FTS5 plan.
DONE 2.A5-a  Migration framework: schema_version table + migrate() function.
DONE 2.A5-b  002_fts5_indexes migration SQL.

TODO 2.B1-a [Complexity: HIGH] [Tokens: ~4000] [User: NO]
    Refactor build_budget_db.py to target the new normalized schema.
    Dependency: All 2.A* DDL is now written (schema_design.py).
    Steps: see schema_design.py notes above for column mappings.

TODO 2.B3-a [Complexity: MEDIUM] [Tokens: ~2000] [User: NO]
    Generate data-quality report (JSON) after each build.
    (validate_budget_data.py + refresh_data.py already create some reports;
    this TODO extends them to include row counts by service/FY/exhibit.)


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

import sqlite3
from pathlib import Path


# ── 2.A3-a  FTS Strategy Decision ─────────────────────────────────────────────
#
# FTS_DECISION: Use SQLite FTS5 (not FTS4, not external engine).
#
# Rationale:
#   • FTS5 is bundled with SQLite ≥ 3.9 (2015); no extra deps.
#   • Supports BM25 ranking (bm25() auxiliary function).
#   • Content tables: FTS5 can mirror an existing table via
#     content=<table> so the data is not duplicated on disk.
#   • Prefix queries, phrase queries, and column filters are supported.
#   • Trigram tokenizer (fts5_tokenize=trigram) available in SQLite ≥ 3.38
#     for substring search without LIKE; fall back to unicode61 for older.
#
# Rejected alternatives:
#   • FTS4: older, lacks BM25, no content tables.
#   • Whoosh / Tantivy: external deps, not portable.
#   • PostgreSQL pg_trgm: overkill — project uses SQLite for portability.
#
# Implementation plan (see 002_fts5_indexes migration):
#   CREATE VIRTUAL TABLE budget_lines_fts USING fts5(
#       account_title, budget_activity_title, sub_activity_title,
#       line_item_title, organization_name, pe_number,
#       content='budget_line_items', content_rowid='id',
#       tokenize='unicode61'
#   );
#   Sync triggers keep FTS in sync with budget_line_items on INSERT/UPDATE/DELETE.


# ── 2.A1-a  Core Fact Table DDL ───────────────────────────────────────────────
#
# Design note (2.A1-b): fiscal years are stored as SEPARATE ROWS rather than
# separate columns. Each row has one fiscal_year value (e.g. "2026") and one
# amount_value. This avoids the "add a column per year" migration problem.
# Trade-off: queries summing across years need GROUP BY or pivoting; this is
# acceptable given the query patterns in search_budget.py.

_DDL_001_CORE = """
-- ── Reference Tables ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS services_agencies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT    NOT NULL UNIQUE,   -- short code, e.g. "Army", "DISA"
    full_name   TEXT    NOT NULL,          -- official full name
    category    TEXT    NOT NULL           -- "military_dept", "defense_agency",
                                           -- "combatant_cmd", "osd_component"
);

CREATE TABLE IF NOT EXISTS appropriation_titles (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    code  TEXT    NOT NULL UNIQUE,  -- e.g. "PROC", "RDTE", "MILCON"
    title TEXT    NOT NULL,         -- e.g. "Procurement"
    color_of_money TEXT             -- "investment", "operation", "personnel"
);

CREATE TABLE IF NOT EXISTS exhibit_types (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT NOT NULL UNIQUE,  -- lowercase key, e.g. "p1", "r2"
    display_name TEXT NOT NULL,         -- e.g. "Procurement (P-1)"
    exhibit_class TEXT NOT NULL,        -- "summary" or "detail"
    description  TEXT
);

CREATE TABLE IF NOT EXISTS budget_cycles (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    code  TEXT NOT NULL UNIQUE,  -- "PB", "ENACTED", "CR", "AMENDED", "SUPPLEMENTAL"
    label TEXT NOT NULL          -- human-readable label
);

-- ── Core Fact Table ───────────────────────────────────────────────────────────
-- One row per (source_file, line_item, fiscal_year, budget_cycle).
-- FK columns reference the reference tables above; NULLs are allowed during
-- migration when reference table rows have not yet been populated.

CREATE TABLE IF NOT EXISTS budget_line_items (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Provenance
    source_file             TEXT    NOT NULL,
    sheet_name              TEXT,
    row_number              INTEGER,
    ingested_at             TEXT    DEFAULT (datetime('now')),

    -- Foreign keys to reference tables (NULL-tolerant during migration)
    service_id              INTEGER REFERENCES services_agencies(id),
    exhibit_type_id         INTEGER REFERENCES exhibit_types(id),
    budget_cycle_id         INTEGER REFERENCES budget_cycles(id),
    appropriation_id        INTEGER REFERENCES appropriation_titles(id),

    -- Denormalized strings kept for query convenience
    organization            TEXT,
    organization_name       TEXT,
    exhibit_type            TEXT,
    fiscal_year             TEXT,
    budget_cycle            TEXT,   -- "PB", "ENACTED", etc.

    -- Account / line identification
    account                 TEXT,
    account_title           TEXT,
    appropriation_code      TEXT,
    appropriation_title     TEXT,
    pe_number               TEXT,   -- Program Element, e.g. "0603000A"

    -- Budget activity hierarchy
    budget_activity         TEXT,
    budget_activity_title   TEXT,
    sub_activity            TEXT,
    sub_activity_title      TEXT,

    -- Line item
    line_item               TEXT,
    line_item_title         TEXT,
    classification          TEXT,   -- e.g. "UNCLASSIFIED"

    -- Monetary data (normalized)
    -- Fiscal-year strategy: one row per FY, so amount_value holds the single
    -- dollar figure for this row's fiscal_year.  amount_type distinguishes
    -- what kind of authority this represents.
    amount_value            REAL,
    amount_unit             TEXT    DEFAULT 'thousands',
    amount_type             TEXT    DEFAULT 'budget_authority',
    -- "budget_authority" (default), "authorization" (C-1), "outlay", "appropriation"

    currency_year           TEXT,   -- "then-year" or "constant"

    -- Quantity fields (procurement exhibits)
    quantity                REAL,

    -- Catch-all for service-specific columns not in canonical schema
    extra_fields            TEXT    -- JSON blob
);

CREATE INDEX IF NOT EXISTS idx_bli_service      ON budget_line_items(service_id);
CREATE INDEX IF NOT EXISTS idx_bli_exhibit      ON budget_line_items(exhibit_type_id);
CREATE INDEX IF NOT EXISTS idx_bli_fiscal_year  ON budget_line_items(fiscal_year);
CREATE INDEX IF NOT EXISTS idx_bli_pe_number    ON budget_line_items(pe_number);
CREATE INDEX IF NOT EXISTS idx_bli_source_file  ON budget_line_items(source_file);
"""


_DDL_001_SEEDS = """
-- ── Seed: services_agencies (2.A2-a) ─────────────────────────────────────────
INSERT OR IGNORE INTO services_agencies (code, full_name, category) VALUES
    ('Army',         'Department of the Army',                    'military_dept'),
    ('Navy',         'Department of the Navy',                    'military_dept'),
    ('Marine Corps', 'United States Marine Corps',                'military_dept'),
    ('Air Force',    'Department of the Air Force',               'military_dept'),
    ('Space Force',  'United States Space Force',                 'military_dept'),
    ('OSD',          'Office of the Secretary of Defense',        'osd_component'),
    ('Defense-Wide', 'Defense-Wide',                              'defense_agency'),
    ('DLA',          'Defense Logistics Agency',                  'defense_agency'),
    ('MDA',          'Missile Defense Agency',                    'defense_agency'),
    ('SOCOM',        'U.S. Special Operations Command',           'combatant_cmd'),
    ('DHA',          'Defense Health Agency',                     'defense_agency'),
    ('DISA',         'Defense Information Systems Agency',        'defense_agency'),
    ('NGB',          'National Guard Bureau',                     'osd_component'),
    ('Joint Staff',  'Joint Staff',                               'osd_component'),
    ('DARPA',        'Defense Advanced Research Projects Agency', 'defense_agency'),
    ('NSA',          'National Security Agency',                  'defense_agency'),
    ('DIA',          'Defense Intelligence Agency',               'defense_agency'),
    ('NRO',          'National Reconnaissance Office',            'defense_agency'),
    ('NGA',          'National Geospatial-Intelligence Agency',   'defense_agency'),
    ('DTRA',         'Defense Threat Reduction Agency',           'defense_agency'),
    ('DCSA',         'Defense Counterintelligence and Security Agency', 'defense_agency'),
    ('WHS',          'Washington Headquarters Services',          'osd_component');

-- ── Seed: appropriation_titles (2.A2-b) ──────────────────────────────────────
INSERT OR IGNORE INTO appropriation_titles (code, title, color_of_money) VALUES
    ('PROC',    'Procurement',                               'investment'),
    ('RDTE',    'Research, Development, Test & Evaluation',  'investment'),
    ('MILCON',  'Military Construction',                     'investment'),
    ('OMA',     'Operation & Maintenance',                   'operation'),
    ('MILPERS', 'Military Personnel',                        'personnel'),
    ('RFUND',   'Revolving & Management Funds',              'operation'),
    ('OTHER',   'Other',                                     NULL);

-- ── Seed: exhibit_types (2.A2-c) — keyed from EXHIBIT_CATALOG ────────────────
INSERT OR IGNORE INTO exhibit_types (code, display_name, exhibit_class, description) VALUES
    ('p1',  'Procurement (P-1)',                        'summary',
            'Summary procurement budget exhibit'),
    ('r1',  'RDT&E (R-1)',                              'summary',
            'Research, Development, Test & Evaluation summary'),
    ('o1',  'Operation & Maintenance (O-1)',            'summary',
            'Operation and Maintenance summary'),
    ('m1',  'Military Personnel (M-1)',                 'summary',
            'Military Personnel summary'),
    ('c1',  'Military Construction (C-1)',              'summary',
            'Military Construction and Family Housing summary'),
    ('rf1', 'Revolving Funds (RF-1)',                   'summary',
            'Revolving and Management Funds summary'),
    ('p1r', 'Procurement Reserves (P-1R)',              'summary',
            'Procurement summary for Reserve components'),
    ('p5',  'Procurement Detail (P-5)',                 'detail',
            'Procurement item detail justification'),
    ('r2',  'RDT&E PE Detail (R-2)',                    'detail',
            'Program Element detail budget justification'),
    ('r3',  'RDT&E Project Schedule (R-3)',             'detail',
            'R&D project schedule and contract information'),
    ('r4',  'RDT&E Budget Item Justification (R-4)',    'detail',
            'Budget item schedule detail for RDT&E programs');

-- ── Seed: budget_cycles (2.A2-d) ─────────────────────────────────────────────
INSERT OR IGNORE INTO budget_cycles (code, label) VALUES
    ('PB',            'President''s Budget'),
    ('ENACTED',       'Enacted Appropriation'),
    ('CR',            'Continuing Resolution'),
    ('AMENDED',       'Amended Budget Request'),
    ('SUPPLEMENTAL',  'Supplemental Appropriation');
"""


# ── 2.A4-a/b  Document & PDF Tables ───────────────────────────────────────────

_DDL_001_DOCS = """
-- ── Document Sources (2.A4-a) ─────────────────────────────────────────────────
-- Tracks every source file (Excel or PDF) that has been ingested.

CREATE TABLE IF NOT EXISTS document_sources (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file  TEXT    NOT NULL UNIQUE,
    file_hash    TEXT,               -- SHA-256 hex digest
    file_size    INTEGER,            -- bytes
    file_type    TEXT,               -- "xlsx", "pdf"
    service_id   INTEGER REFERENCES services_agencies(id),
    fiscal_year  TEXT,
    exhibit_code TEXT,               -- e.g. "p1", "r2"
    row_count    INTEGER,
    ingested_at  TEXT    DEFAULT (datetime('now'))
);

-- ── PDF Content (2.A4-b) ─────────────────────────────────────────────────────
-- Stores extracted text and tables from PDF documents.
-- FTS5 virtual table mirrors this via content= linkage (see migration 002).

CREATE TABLE IF NOT EXISTS pdf_content (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   INTEGER NOT NULL REFERENCES document_sources(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    content     TEXT,               -- raw extracted text
    tables      TEXT                -- JSON-encoded list of extracted tables
);

CREATE INDEX IF NOT EXISTS idx_pdf_source ON pdf_content(source_id);
"""


# ── 2.A5-a  Migration Framework ───────────────────────────────────────────────

_DDL_SCHEMA_VERSION = """
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL,
    description TEXT,
    applied_at  TEXT    DEFAULT (datetime('now'))
);
"""

# Migration SQL ordered by version number.
# Each entry: (version, description, sql)
_MIGRATIONS = [
    (
        1,
        "001_core_tables: reference tables + budget_line_items + document_sources",
        _DDL_001_CORE + _DDL_001_SEEDS + _DDL_001_DOCS,
    ),
    (
        2,
        "002_fts5_indexes: FTS5 virtual table + sync triggers for budget_line_items",
        # 2.A5-b: FTS5 content table mirrors budget_line_items; triggers keep it
        # in sync.  The content= option means FTS5 stores only the index, not the
        # text itself — saves disk space when the source table already exists.
        """
CREATE VIRTUAL TABLE IF NOT EXISTS budget_line_items_fts USING fts5(
    account_title,
    budget_activity_title,
    sub_activity_title,
    line_item_title,
    organization_name,
    pe_number,
    content='budget_line_items',
    content_rowid='id',
    tokenize='unicode61'
);

-- Sync trigger: INSERT
CREATE TRIGGER IF NOT EXISTS budget_line_items_fts_ai
AFTER INSERT ON budget_line_items BEGIN
    INSERT INTO budget_line_items_fts(
        rowid, account_title, budget_activity_title,
        sub_activity_title, line_item_title, organization_name, pe_number
    ) VALUES (
        new.id, new.account_title, new.budget_activity_title,
        new.sub_activity_title, new.line_item_title,
        new.organization_name, new.pe_number
    );
END;

-- Sync trigger: DELETE
CREATE TRIGGER IF NOT EXISTS budget_line_items_fts_ad
AFTER DELETE ON budget_line_items BEGIN
    INSERT INTO budget_line_items_fts(
        budget_line_items_fts, rowid, account_title, budget_activity_title,
        sub_activity_title, line_item_title, organization_name, pe_number
    ) VALUES (
        'delete', old.id, old.account_title, old.budget_activity_title,
        old.sub_activity_title, old.line_item_title,
        old.organization_name, old.pe_number
    );
END;

-- Sync trigger: UPDATE
CREATE TRIGGER IF NOT EXISTS budget_line_items_fts_au
AFTER UPDATE ON budget_line_items BEGIN
    INSERT INTO budget_line_items_fts(
        budget_line_items_fts, rowid, account_title, budget_activity_title,
        sub_activity_title, line_item_title, organization_name, pe_number
    ) VALUES (
        'delete', old.id, old.account_title, old.budget_activity_title,
        old.sub_activity_title, old.line_item_title,
        old.organization_name, old.pe_number
    );
    INSERT INTO budget_line_items_fts(
        rowid, account_title, budget_activity_title,
        sub_activity_title, line_item_title, organization_name, pe_number
    ) VALUES (
        new.id, new.account_title, new.budget_activity_title,
        new.sub_activity_title, new.line_item_title,
        new.organization_name, new.pe_number
    );
END;
        """,
    ),
]


def _current_version(conn: sqlite3.Connection) -> int:
    """Return the highest applied migration version (0 if none applied)."""
    try:
        row = conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        return row[0] or 0
    except sqlite3.OperationalError:
        # schema_version table doesn't exist yet
        return 0


def migrate(conn: sqlite3.Connection) -> int:
    """Apply all pending migrations in order.

    Returns the number of migrations applied.  Idempotent: already-applied
    migrations are skipped.  The schema_version table is created if absent.

    Args:
        conn: An open SQLite connection.

    Returns:
        Number of migrations applied in this call (0 if already up to date).
    """
    conn.execute(_DDL_SCHEMA_VERSION)
    conn.commit()

    current = _current_version(conn)
    applied = 0

    for version, description, sql in _MIGRATIONS:
        if version <= current:
            continue
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO schema_version (version, description) VALUES (?, ?)",
            (version, description),
        )
        conn.commit()
        applied += 1

    return applied


def create_normalized_db(db_path: Path) -> sqlite3.Connection:
    """Open (or create) a normalized-schema database and run all migrations.

    Args:
        db_path: Filesystem path for the SQLite file (created if absent).

    Returns:
        An open sqlite3.Connection with WAL mode and all migrations applied.
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    migrate(conn)
    return conn
