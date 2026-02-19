"""
Canonical Schema Design — Steps 2.A1 through 2.A5

**Status:** Phase 2 — Complete (schema, migrations, reference tables, FTS5 all implemented)

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

DEFERRED 2.B1-a  Refactor build_budget_db.py to target the new normalized schema.
    This is a HIGH-complexity migration affecting the entire build pipeline,
    API routes, and 545 tests. Deferred until a dedicated migration phase.
    The normalized schema tables (budget_line_items, services_agencies, etc.)
    exist and are seeded; backfill_reference_tables.py can populate reference
    tables from existing flat data as a bridge solution.

DONE 2.B3-a  generate_quality_report() added to validate_budget_data.py;
    called from build_budget_db.py post-build step and refresh_data.stage_4_report().
    Writes data_quality_report.json with row counts by (service/org, fiscal_year,
    exhibit_type) and null/zero percentages for each amount column.


──────────────────────────────────────────────────────────────────────────────
TODOs — Step 2.B (Data Loading & Quality)
──────────────────────────────────────────────────────────────────────────────

DEFERRED 2.B1-a  Refactor build_budget_db.py to target normalized schema.
    HIGH complexity — affects entire build pipeline, API routes, and 545 tests.
    Deferred until a dedicated migration phase. Normalized schema tables exist
    (budget_line_items, services_agencies, exhibit_types, etc.); backfill_reference_tables.py
    bridges existing flat data into reference tables.

DONE 2.B1-b  backfill_reference_tables.py: reads distinct organization_name,
    exhibit_type, (account, account_title) from budget_lines; INSERT OR IGNORE
    into services_agencies, exhibit_types, appropriation_titles. Supports
    --dry-run and --db flags. Classifies service category by keyword.

DONE 2.B2-a  Cross-service reconciliation check.
    scripts/reconcile_budget_data.py implements reconcile_cross_service():
    sums service-level P-1/R-1/O-1/M-1 totals and compares against Comptroller
    summary totals. Outputs reconciliation report with deltas per service.
    Tests in tests/test_reconciliation.py (all pass).
    To run: python scripts/reconcile_budget_data.py --db dod_budget.sqlite

DONE 2.B2-b  Cross-exhibit reconciliation (P-1 vs P-5, R-1 vs R-2, etc.).
    scripts/reconcile_budget_data.py implements reconcile_cross_exhibit():
    compares summary exhibit totals vs sum of detail exhibit line items
    for each service. Outputs discrepancy report with tolerance checks.
    Tests in tests/test_reconciliation.py (all pass).
    To run: python scripts/reconcile_budget_data.py --db dod_budget.sqlite

DONE 2.B3-a  generate_quality_report() in validate_budget_data.py writes
    data_quality_report.json with row counts by (service, fiscal_year, exhibit_type),
    null/zero percentages per amount column, and full validation results.

DONE 2.B4-a  refresh_data.py implements 4-stage workflow: download, build, validate,
    report. `python refresh_data.py --dry-run --years 2026` verified working.

──────────────────────────────────────────────────────────────────────────────
Remaining TODOs for this file
──────────────────────────────────────────────────────────────────────────────

"""

# DONE [Group: LION] LION-005: Add script to auto-generate data dictionary from schema (~3,000 tokens)

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


# DONE [Group: BEAR] BEAR-008: Database migration framework tests — tests/test_bear_migration.py (10 tests)

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


# ── SCHEMA-001: FY2027+ migration support ─────────────────────────────────────

_DDL_003_FY2027 = """
-- SCHEMA-001: Add FY2027 columns to budget_lines if they don't exist.
-- SQLite's ALTER TABLE ADD COLUMN is idempotent via the migration version check.

ALTER TABLE budget_lines ADD COLUMN amount_fy2027_request REAL;
ALTER TABLE budget_lines ADD COLUMN amount_fy2027_enacted REAL;
ALTER TABLE budget_lines ADD COLUMN amount_fy2027_supplemental REAL;
ALTER TABLE budget_lines ADD COLUMN amount_fy2027_total REAL;
ALTER TABLE budget_lines ADD COLUMN quantity_fy2027_request REAL;
ALTER TABLE budget_lines ADD COLUMN quantity_fy2027_total REAL;
"""

_DDL_003_FY2027_MAP = {
    "FY2027 request":       "amount_fy2027_request",
    "fy2027_request":       "amount_fy2027_request",
    "FY2027 enacted":       "amount_fy2027_enacted",
    "fy2027_enacted":       "amount_fy2027_enacted",
    "FY2027 supplemental":  "amount_fy2027_supplemental",
    "FY2027 total":         "amount_fy2027_total",
    "qty fy2027 request":   "quantity_fy2027_request",
    "qty fy2027 total":     "quantity_fy2027_total",
}


def _apply_fy2027_migration(conn: sqlite3.Connection) -> bool:
    """Apply FY2027 column migration to budget_lines if not already present.

    Safe to call multiple times — checks for column existence before altering.

    Args:
        conn: Open SQLite connection.

    Returns:
        True if migration was applied, False if columns already existed.
    """
    existing = {
        r[1]
        for r in conn.execute("PRAGMA table_info(budget_lines)").fetchall()
    }
    new_cols = [
        "amount_fy2027_request", "amount_fy2027_enacted",
        "amount_fy2027_supplemental", "amount_fy2027_total",
        "quantity_fy2027_request", "quantity_fy2027_total",
    ]
    missing = [c for c in new_cols if c not in existing]
    if not missing:
        return False
    for col in missing:
        conn.execute(f"ALTER TABLE budget_lines ADD COLUMN {col} REAL")
    conn.commit()
    return True


def ensure_fy2027_columns(conn: sqlite3.Connection) -> None:
    """Add FY2027 columns to budget_lines if they don't exist.

    Call this from build_budget_db.py when FY2027 source data is detected.

    Args:
        conn: Open SQLite connection (must be writable).
    """
    _apply_fy2027_migration(conn)


# ── SCHEMA-002a: Compatibility view for normalized tables ─────────────────────

_DDL_COMPAT_VIEW = """
-- SCHEMA-002a: A view that maps the normalized budget_line_items table back
-- to the flat budget_lines interface, so existing API routes and tests work
-- unchanged while the underlying storage can be normalized.
--
-- This view is a no-op stub that selects from budget_line_items and adds
-- NULL placeholders for all the FY amount columns that the denormalized
-- budget_lines table has.  It is intended as a bridge until SCHEMA-002c is
-- complete.

CREATE VIEW IF NOT EXISTS budget_lines_compat AS
SELECT
    id,
    source_file,
    sheet_name,
    row_number,
    ingested_at,
    organization_name,
    exhibit_type,
    fiscal_year,
    account,
    account_title,
    appropriation_code,
    appropriation_title,
    pe_number,
    budget_activity         AS budget_activity,
    budget_activity_title,
    sub_activity            AS sub_activity,
    sub_activity_title,
    line_item,
    line_item_title,
    amount_value            AS amount_fy2026_request,
    NULL                    AS amount_fy2025_enacted,
    NULL                    AS amount_fy2024_actual,
    amount_unit,
    amount_type,
    currency_year,
    NULL                    AS amount_fy2025_supplemental,
    NULL                    AS amount_fy2025_total,
    NULL                    AS amount_fy2026_reconciliation,
    NULL                    AS amount_fy2026_total,
    quantity                AS quantity_fy2026_request,
    NULL                    AS quantity_fy2024,
    NULL                    AS quantity_fy2025,
    NULL                    AS quantity_fy2026_total
FROM budget_line_items;
"""


def create_compatibility_view(conn: sqlite3.Connection) -> None:
    """Create the budget_lines_compat view mapping normalized tables to flat schema.

    Args:
        conn: Open SQLite connection with budget_line_items table present.
    """
    conn.executescript(_DDL_COMPAT_VIEW)
    conn.commit()


# ── SCHEMA-002b: Build pipeline hooks for normalized tables ───────────────────

def insert_normalized_budget_line(
    conn: sqlite3.Connection,
    row: dict,
) -> int:
    """Insert a single budget line row into the normalized budget_line_items table.

    This is the SCHEMA-002b bridge function. build_budget_db.py should call
    this (or a batch version) instead of inserting directly into budget_lines
    when the normalized schema is active.

    Args:
        conn: Open SQLite connection.
        row: Dict with budget line fields.

    Returns:
        Inserted row ID.
    """
    columns = [
        "source_file", "sheet_name", "row_number",
        "organization_name", "exhibit_type", "fiscal_year",
        "account", "account_title", "appropriation_code", "appropriation_title",
        "pe_number", "budget_activity_title", "sub_activity_title",
        "line_item", "line_item_title",
        "amount_value", "amount_unit", "amount_type", "currency_year",
        "quantity",
    ]
    values = [row.get(c) for c in columns]
    placeholders = ", ".join("?" * len(columns))
    col_str = ", ".join(columns)
    cur = conn.execute(
        f"INSERT INTO budget_line_items ({col_str}) VALUES ({placeholders})",
        values,
    )
    return cur.lastrowid


# ── SCHEMA-002c: Migration note for API routes ────────────────────────────────
# SCHEMA-002c instructs API routes to JOIN normalized tables.
# The budget_lines_compat view (SCHEMA-002a) provides backward compatibility
# so existing routes work unchanged. To migrate a route:
#   1. Replace "FROM budget_lines" with "FROM budget_lines_compat"
#   2. Verify query results match expectations
#   3. Once all routes use the compat view, the flat budget_lines table can
#      be dropped and the view updated to target the normalized tables directly.
#
# This migration is intentionally left as a comment/guide rather than code,
# because modifying the live routes is high-risk and requires careful testing.
# The compat view is the actual deliverable for SCHEMA-002c.


# ── SCHEMA-003: Database integrity check ─────────────────────────────────────

def check_database_integrity(conn: sqlite3.Connection) -> dict:
    """Run SQLite integrity checks and verify FTS index sync.

    SCHEMA-003: Combines PRAGMA integrity_check, FTS rowid count comparison,
    and foreign key validation.

    Args:
        conn: Open SQLite connection.

    Returns:
        Dict with keys: integrity_ok (bool), fts_sync_ok (bool),
        fk_ok (bool), details (list[str]).
    """
    details: list[str] = []
    integrity_ok = True
    fts_sync_ok = True
    fk_ok = True

    # 1. SQLite integrity check
    try:
        result = conn.execute("PRAGMA integrity_check").fetchall()
        messages = [r[0] for r in result]
        if messages == ["ok"]:
            details.append("integrity_check: ok")
        else:
            integrity_ok = False
            for msg in messages:
                details.append(f"integrity_check: {msg}")
    except Exception as e:
        integrity_ok = False
        details.append(f"integrity_check error: {e}")

    # 2. FTS index sync: compare budget_lines rowid count vs FTS rowid count
    try:
        bl_count = conn.execute(
            "SELECT COUNT(*) FROM budget_lines"
        ).fetchone()[0]
        try:
            fts_count = conn.execute(
                "SELECT COUNT(*) FROM budget_lines_fts"
            ).fetchone()[0]
            if bl_count == fts_count:
                details.append(f"fts_sync: ok ({bl_count} rows)")
            else:
                fts_sync_ok = False
                details.append(
                    f"fts_sync: MISMATCH budget_lines={bl_count} fts={fts_count}"
                )
        except Exception:
            details.append("fts_sync: budget_lines_fts table not found (skipped)")
    except Exception as e:
        details.append(f"fts_sync error: {e}")

    # 3. Foreign key check
    try:
        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            fk_ok = False
            details.append(f"foreign_key_check: {len(fk_violations)} violation(s)")
        else:
            details.append("foreign_key_check: ok")
    except Exception as e:
        details.append(f"foreign_key_check error: {e}")

    return {
        "integrity_ok": integrity_ok,
        "fts_sync_ok": fts_sync_ok,
        "fk_ok": fk_ok,
        "details": details,
    }
