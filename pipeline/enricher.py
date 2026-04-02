"""
Budget Database Enrichment Pipeline

Runs after build_budget_db.py to populate the enrichment tables:
  - pe_index              — canonical record per PE number across all years/exhibits
  - pe_descriptions       — links PE numbers to their PDF narrative pages
  - pe_tags               — auto-generated tags from structured fields, keywords, and optionally LLM
  - pe_lineage            — detected cross-PE references (project movement / lineage)
  - project_descriptions  — project-level decomposition of PE narrative text (Phase 5)

Usage:
    python enrich_budget_db.py                          # all phases, no LLM
    python enrich_budget_db.py --with-llm               # enable LLM tagging (needs API key)
    python enrich_budget_db.py --phases 1,2             # run only phases 1 and 2
    python enrich_budget_db.py --rebuild                # drop and rebuild enrichment tables
    python enrich_budget_db.py --db path/to/db.sqlite   # custom DB path

"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import sys
import threading
import time
from pathlib import Path

from utils import get_connection
from utils.patterns import PE_NUMBER, FISCAL_YEAR
from utils.pdf_sections import parse_narrative_sections, detect_project_boundaries

# Single top-of-file anthropic import (TODO-L3).
# Check _HAS_ANTHROPIC once at Phase 3 entry rather than per-batch.
_HAS_ANTHROPIC = False
try:
    import anthropic  # noqa: F401, E402
    _HAS_ANTHROPIC = True
except ImportError:
    anthropic = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("dod_budget.sqlite")

# Maximum characters to store for a PE narrative text block (no section headers).
_MAX_NARRATIVE_TEXT_CHARS = 4000

# ── Domain taxonomy for keyword tagging ───────────────────────────────────────
# Each entry: (tag_name, [search_terms_regex])
# Terms are matched case-insensitively as whole words against description text.

_TAXONOMY: list[tuple[str, list[str]]] = [
    ("hypersonic",        [r"hypersonic"]),
    ("cyber",             [r"cyber(?:security)?", r"cybersecurity"]),
    ("space",             [r"\bspace\b", r"satellite", r"orbital", r"launch\s+vehicle"]),
    ("ai-ml",             [r"\bai\b", r"artificial\s+intelligence", r"machine\s+learning",
                           r"deep\s+learning", r"neural\s+network"]),
    ("c2",                [r"command\s+and\s+control", r"\bC2\b", r"\bC3\b", r"\bC4ISR\b"]),
    ("isr",               [r"\bISR\b", r"intelligence.*surveillance.*reconnaissance",
                           r"reconnaissance"]),
    ("electronic-warfare", [
        r"electronic\s+warfare", r"\bEW\b", r"jamming", r"electronic\s+attack"]),
    ("missile-defense",   [r"missile\s+defense", r"\bBMD\b", r"ballistic\s+missile",
                           r"interceptor"]),
    ("directed-energy",   [r"directed\s+energy", r"\bDEW\b", r"high[- ]energy\s+laser",
                           r"\bHEL\b", r"high[- ]power\s+microwave"]),
    ("counter-uas",       [r"counter[- ]UAS", r"counter[- ]unmanned", r"\bcUAS\b",
                           r"drone\s+defeat"]),
    ("autonomy",          [r"autonom(?:ous|y)", r"unmanned\s+system", r"\bUAS\b",
                           r"\bUGV\b", r"\bUSV\b"]),
    ("nuclear",           [r"nuclear", r"\bICBM\b", r"\bSLBM\b", r"nuclear\s+deterren"]),
    ("shipbuilding",      [r"shipbuilding", r"\bDDG\b", r"\bSSN\b", r"\bSSBN\b",
                           r"surface\s+combatant", r"destroyer"]),
    ("aviation",          [r"aviation", r"aircraft", r"fighter", r"bomber", r"helicopter",
                           r"rotorcraft", r"\bF-35\b", r"\bB-21\b"]),
    ("ground-vehicle",    [r"ground\s+vehicle", r"\bABCT\b", r"armored", r"\bAPC\b",
                           r"Bradley", r"Stryker"]),
    ("logistics",         [r"logistics", r"sustainment", r"supply\s+chain", r"depot"]),
    ("training",          [r"\btraining\b", r"simulation", r"live[- ]virtual[- ]constructive",
                           r"\bLVC\b"]),
    ("communications",    [r"communications?", r"\bSATCOM\b", r"waveform", r"radio",
                           r"network"]),
    ("radar",             [r"\bradar\b", r"active\s+electronically\s+scanned",
                           r"\bAESA\b", r"phased\s+array"]),
    ("sensors",           [r"\bsensor", r"electro[- ]optical", r"\bEO/IR\b", r"infrared"]),
    ("software",          [r"\bsoftware\b", r"DevSecOps", r"software\s+defined"]),
    ("cloud",             [r"\bcloud\b", r"cloud\s+computing", r"cloud[- ]native"]),
    ("biodefense",        [r"biodefense", r"biological\s+threat", r"chem[- ]bio",
                           r"\bCBRN\b", r"bioagent"]),
    ("special-operations", [r"special\s+operations", r"\bSOF\b", r"\bSOCOM\b"]),
    ("munitions",         [r"munition", r"ammunition", r"\bJDAM\b", r"\bSDB\b",
                           r"precision\s+guided"]),
    ("missile",           [r"\bmissile\b", r"\bAIM-\d", r"\bAGM-\d", r"cruise\s+missile"]),
    ("quantum",           [r"quantum", r"post[- ]quantum", r"quantum\s+computing",
                           r"quantum\s+sensing"]),
    ("microelectronics",  [r"microelectronic", r"semiconductor", r"chip\s+fabricat",
                           r"integrated\s+circuit", r"\bASIC\b", r"\bFPGA\b"]),
    ("5g-comms",          [r"\b5G\b", r"fifth[- ]generation\s+(?:network|comm)",
                           r"open\s+RAN", r"\bO-RAN\b"]),
    ("counter-terrorism", [r"counter[- ]?terror", r"\bCT\b.*(?:mission|operation)",
                           r"counter[- ]?insurgency"]),
    ("arctic",            [r"arctic", r"polar\s+region", r"cold[- ]weather\s+operation"]),
    ("indo-pacific",      [r"indo[- ]pacific", r"\bPACOM\b", r"\bINDOPACOM\b",
                           r"Pacific\s+Deterrence"]),
    ("submarine",         [r"submarine", r"\bsub(?:surface)?\b.*(?:warfare|vehicle)",
                           r"undersea", r"torpedo"]),
    ("medical",           [r"medical\s+(?:research|readiness)", r"combat\s+casualty",
                           r"military\s+health", r"\bDHP\b"]),
]

# Pre-compile all taxonomy patterns
_COMPILED_TAXONOMY: list[tuple[str, list[re.Pattern]]] = [
    (tag, [re.compile(term, re.IGNORECASE) for term in terms])
    for tag, terms in _TAXONOMY
]

# ── Tier-2 taxonomy — broader signal, lower confidence (issue #54) ─────────────
# Confidence assigned in run_phase3(): 0.7 (budget_lines), 0.65 (PDF narrative).
# Standalone _tags_from_keywords() uses 0.7 for tier-2 terms.

_TAXONOMY_TIER2: list[tuple[str, list[str]]] = [
    ("jadc2",              [r"\bJADC2\b", r"joint\s+all[- ]domain\s+command",
                            r"all[- ]domain\s+(?:operations|battle)",
                            r"combined\s+joint\s+all[- ]domain"]),
    ("sigint",             [r"\bSIGINT\b", r"\bELINT\b", r"\bCOMINT\b", r"\bMASINT\b",
                            r"signals?\s+intelligence", r"signal\s+collection"]),
    ("geoint",             [r"\bGEOINT\b", r"geospatial\s+intelligence", r"\bNGA\b",
                            r"geospatial\s+(?:analysis|data|imagery)"]),
    ("pnt",                [r"\bPNT\b", r"positioning,?\s+navigation,?\s+and\s+timing",
                            r"\bGPS\b", r"\bGNSS\b", r"navigation\s+warfare",
                            r"anti[- ]jam(?:ming)?\s+(?:GPS|navigation)"]),
    ("iads",               [r"\bIADS\b", r"integrated\s+air\s+(?:and\s+missile\s+)?defense",
                            r"\bSHORAD\b", r"\bHIMAD\b", r"layered\s+air\s+defense"]),
    ("information-warfare", [r"information\s+warfare", r"information\s+operations",
                             r"\bIO\b.*(?:capability|operation|program)",
                             r"cognitive\s+(?:warfare|operations)",
                             r"influence\s+operations", r"military\s+deception",
                             r"\bMILDEC\b", r"psychological\s+operations", r"\bPSYOP\b"]),
    ("strategic-mobility", [r"strategic\s+(?:airlift|mobility|lift)",
                            r"\bairlift\b", r"aerial\s+refueling", r"air\s+refueling",
                            r"\btanker\b.*(?:aircraft|program|fleet)",
                            r"\bKC-46\b", r"\bKC-135\b", r"\bC-17\b", r"\bC-5\b"]),
    ("amphibious",         [r"amphibious\s+(?:warfare|operations|assault|ship)",
                            r"\bMEF\b", r"\bMEB\b", r"expeditionary\s+(?:force|operations)",
                            r"\bLHA\b", r"\bLHD\b", r"\bLPD\b", r"littoral\s+(?:combat|warfare)"]),
    ("force-protection",   [r"force\s+protection", r"\bATFP\b", r"anti[- ]terrorism",
                            r"physical\s+security", r"base\s+defense",
                            r"installation\s+security"]),
    ("readiness",          [r"\breadiness\b", r"operational\s+readiness",
                            r"mission\s+capable\s+rate", r"\bMCR\b",
                            r"full\s+mission\s+capable", r"\bFMC\b.*rate",
                            r"materiel\s+readiness"]),
    ("emp",                [r"\bEMP\b", r"electromagnetic\s+pulse",
                            r"EMP\s+(?:hardening|protection|survivability)",
                            r"transient\s+electromagnetic"]),
    ("cbrn",               [r"\bCBRN\b", r"\bCBRNE\b",
                            r"chemical[,/]?\s*biological[,/]?\s*radiological",
                            r"chem[- ]bio\s+(?:defense|threat)",
                            r"nuclear\s+(?:consequence|hazard|defense\s+program)",
                            r"decontamination"]),
    ("counter-intelligence", [r"counterintelligence", r"counter[- ]intelligence",
                              r"\bCI\b.*(?:program|investigation|operation)",
                              r"insider\s+threat", r"foreign\s+intelligence\s+threat"]),
    ("kill-chain",         [r"kill\s+chain", r"kill[- ]chain",
                            r"sensor[-\s]to[-\s]shooter", r"time[-\s]sensitive\s+targeting",
                            r"find,?\s*fix,?\s*track,?\s*target"]),
]

_COMPILED_TAXONOMY_TIER2: list[tuple[str, list[re.Pattern]]] = [
    (tag, [re.compile(term, re.IGNORECASE) for term in terms])
    for tag, terms in _TAXONOMY_TIER2
]

# ── Structured field → tag mappings ───────────────────────────────────────────

_BUDGET_ACTIVITY_TAGS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"6\.1|basic\s+research",           re.IGNORECASE), "basic-research"),
    (re.compile(r"6\.2|applied\s+research",         re.IGNORECASE), "applied-research"),
    (re.compile(r"6\.3|advanced\s+technology",  re.IGNORECASE), "advanced-technology-development"),
    (re.compile(r"6\.4|advanced\s+component",   re.IGNORECASE), "advanced-component-development"),
    (re.compile(r"6\.5|system\s+development",   re.IGNORECASE), "system-development-demonstration"),
    (re.compile(r"6\.6|rdt.*management",        re.IGNORECASE), "rdte-management-support"),
    (re.compile(r"6\.7|operational\s+system",   re.IGNORECASE), "operational-system-development"),
]

_APPROP_TAGS: dict[str, str] = {
    "rdte":      "rdte",
    "rdtae":     "rdte",
    "rdt&e":     "rdte",
    "research, development": "rdte",
    "research and development": "rdte",
    "procurement": "procurement",
    "operation and maintenance": "om",
    "operations and maintenance": "om",
    "milpers":   "milpers",
    "military personnel": "milpers",
    "military construction": "milcon",
    "milcon":    "milcon",
    "revolving": "revolving-fund",
}

_ORG_TAGS: dict[str, str] = {
    "army":        "army",
    "navy":        "navy",
    "marine":      "marine-corps",
    "air force":   "air-force",
    "air_force":   "air-force",
    "space force": "space-force",
    "space_force": "space-force",
    "defense-wide": "defense-wide",
    "defense wide": "defense-wide",
}

# ── Exhibit type → budget type mapping (for PDF-only PE inference) ────────────

_EXHIBIT_TO_BUDGET_TYPE: dict[str, str] = {
    "r1": "RDT&E", "r2": "RDT&E", "r3": "RDT&E", "r4": "RDT&E",
    "p1": "Procurement", "p1r": "Procurement", "p5": "Procurement",
    "o1": "O&M", "m1": "MilPers", "c1": "MilCon", "rf1": "Revolving",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_fy_from_path(source_file: str) -> str | None:
    """Extract fiscal year from a source file path string."""
    m = FISCAL_YEAR.search(source_file)
    if m:
        digits = re.search(r"(?:19|20)\d{2}", m.group(), re.IGNORECASE)
        return digits.group() if digits else None
    return None


# Regex to extract a PE title from PDF page text.
# Matches patterns like:
#   "PE 0602702F: Cool Program Title"
#   "PE 0602702F / Cool Program Title"
#   "Program Element 0602702F Cool Program Title"
_PE_TITLE_PATTERN = re.compile(
    r"(?:PE|Program\s+Element)\s+"
    r"([0-9]{7}[A-Z]{1,2})"
    r"\s*[:/\-–—]\s*"
    r"([A-Z][^\n]{5,80})",
    re.IGNORECASE,
)


def _extract_pe_title_from_text(pe_number: str, text: str) -> str | None:
    """Try to extract a display title for a PE from PDF page text.

    Searches for patterns like 'PE 0602702F: Title' or 'PE 0602702F / Title'.
    Returns the first matching title for the given PE number, or None.
    """
    for m in _PE_TITLE_PATTERN.finditer(text):
        if m.group(1).upper() == pe_number.upper():
            title = m.group(2).strip()
            # Clean up trailing punctuation and whitespace
            title = re.sub(r"[\s.,:;]+$", "", title)
            if title:
                return title
    return None


def _context_window(text: str, pos: int, window: int = 200) -> str:
    """Return up to `window` characters centred around position `pos`."""
    start = max(0, pos - window // 2)
    end = min(len(text), pos + window // 2)
    snippet = text[start:end].replace("\n", " ")
    return f"...{snippet}..." if start > 0 or end < len(text) else snippet


def _ensure_checkpoint_table(conn: sqlite3.Connection) -> None:
    """Create the enrichment checkpoints table if it does not exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _enrichment_checkpoints (
            phase      INTEGER PRIMARY KEY,
            last_rowid INTEGER NOT NULL,
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)


def _get_checkpoint(conn: sqlite3.Connection, phase: int) -> int:
    """Return the last-processed pe_descriptions rowid for a phase, or 0."""
    _ensure_checkpoint_table(conn)
    row = conn.execute(
        "SELECT last_rowid FROM _enrichment_checkpoints WHERE phase = ?",
        (phase,),
    ).fetchone()
    return row[0] if row else 0


def _save_checkpoint(conn: sqlite3.Connection, phase: int, last_rowid: int) -> None:
    """Save a checkpoint for a phase (call before conn.commit())."""
    _ensure_checkpoint_table(conn)
    conn.execute("""
        INSERT OR REPLACE INTO _enrichment_checkpoints (phase, last_rowid, updated_at)
        VALUES (?, ?, datetime('now'))
    """, (phase, last_rowid))


def _ensure_pe_index_source_column(conn: sqlite3.Connection) -> None:
    """Add the 'source' column to pe_index if it doesn't exist yet.

    Handles the upgrade path for databases created before PDF-only PE support.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(pe_index)").fetchall()}
    if "source" not in cols:
        conn.execute(
            "ALTER TABLE pe_index ADD COLUMN source TEXT NOT NULL DEFAULT 'budget_lines'"
        )
        conn.commit()
        logger.info("  Added 'source' column to pe_index (upgrade).")


def _log_progress(
    phase_name: str,
    completed: int,
    total: int,
    start_time: float,
) -> None:
    """Log a uniform progress line for an enrichment phase.

    Format:
        Phase X: {completed}/{total} ({pct:.1f}%) | Elapsed: {elapsed} | ETA: {eta} | {rate:.0f} items/s
    """
    if total <= 0:
        return
    elapsed = time.monotonic() - start_time
    pct = completed / total * 100
    rate = completed / elapsed if elapsed > 0 else 0
    eta_s = (total - completed) / rate if rate > 0 else 0

    def _fmt_time(s: float) -> str:
        if s < 60:
            return f"{s:.0f}s"
        m, s = divmod(s, 60)
        return f"{int(m)}m{int(s)}s"

    logger.info(
        "%s: %s/%s (%.1f%%) | Elapsed: %s | ETA: %s | %.0f items/s",
        phase_name,
        f"{completed:,}",
        f"{total:,}",
        pct,
        _fmt_time(elapsed),
        _fmt_time(eta_s),
        rate,
    )


def _drop_enrichment_tables(conn: sqlite3.Connection) -> None:
    # Drop FTS5 table first (depends on pe_descriptions content table)
    conn.execute("DROP TABLE IF EXISTS pe_descriptions_fts")
    conn.execute("DROP TABLE IF EXISTS _enrichment_checkpoints")
    for table in ("project_descriptions", "pe_lineage", "pe_tags", "pe_descriptions", "pe_index"):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    # Recreate the tables so enrichment phases can INSERT into them.
    # Import create_database's DDL for enrichment tables.
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pe_index (
            pe_number         TEXT PRIMARY KEY,
            display_title     TEXT,
            organization_name TEXT,
            budget_type       TEXT,
            fiscal_years      TEXT,
            exhibit_types     TEXT,
            source            TEXT NOT NULL DEFAULT 'budget_lines',
            updated_at        TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS pe_descriptions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number        TEXT NOT NULL,
            fiscal_year      TEXT,
            source_file      TEXT,
            page_start       INTEGER,
            page_end         INTEGER,
            section_header   TEXT,
            description_text TEXT,
            FOREIGN KEY (pe_number) REFERENCES pe_index(pe_number)
        );
        CREATE INDEX IF NOT EXISTS idx_pe_desc_pe ON pe_descriptions(pe_number);
        CREATE INDEX IF NOT EXISTS idx_pe_desc_fy ON pe_descriptions(fiscal_year);

        -- FTS5 for pe_descriptions enables fast topic search across
        -- PE narrative text without expensive LIKE scans.
        CREATE VIRTUAL TABLE IF NOT EXISTS pe_descriptions_fts USING fts5(
            pe_number,
            section_header,
            description_text,
            content='pe_descriptions',
            content_rowid='id'
        );
        -- Sync triggers
        CREATE TRIGGER IF NOT EXISTS pe_desc_fts_ai AFTER INSERT ON pe_descriptions BEGIN
            INSERT INTO pe_descriptions_fts(rowid, pe_number, section_header, description_text)
            VALUES (new.id, new.pe_number, new.section_header, new.description_text);
        END;
        CREATE TRIGGER IF NOT EXISTS pe_desc_fts_ad AFTER DELETE ON pe_descriptions BEGIN
            INSERT INTO pe_descriptions_fts(
                pe_descriptions_fts, rowid, pe_number,
                section_header, description_text
            ) VALUES (
                'delete', old.id, old.pe_number,
                old.section_header, old.description_text
            );
        END;
        CREATE TRIGGER IF NOT EXISTS pe_desc_fts_au AFTER UPDATE ON pe_descriptions BEGIN
            INSERT INTO pe_descriptions_fts(
                pe_descriptions_fts, rowid, pe_number,
                section_header, description_text
            ) VALUES (
                'delete', old.id, old.pe_number,
                old.section_header, old.description_text
            );
            INSERT INTO pe_descriptions_fts(rowid, pe_number, section_header, description_text)
            VALUES (new.id, new.pe_number, new.section_header, new.description_text);
        END;

        CREATE TABLE IF NOT EXISTS pe_tags (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number      TEXT NOT NULL,
            project_number TEXT,
            tag            TEXT NOT NULL,
            tag_source     TEXT NOT NULL,
            confidence     REAL DEFAULT 1.0,
            source_files   TEXT,
            UNIQUE(pe_number, project_number, tag, tag_source),
            FOREIGN KEY (pe_number) REFERENCES pe_index(pe_number)
        );
        CREATE INDEX IF NOT EXISTS idx_pe_tags_pe ON pe_tags(pe_number);
        CREATE INDEX IF NOT EXISTS idx_pe_tags_tag ON pe_tags(tag);
        CREATE INDEX IF NOT EXISTS idx_pe_tags_proj ON pe_tags(project_number);
        CREATE TABLE IF NOT EXISTS pe_lineage (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            source_pe        TEXT NOT NULL,
            referenced_pe    TEXT NOT NULL,
            fiscal_year      TEXT,
            source_file      TEXT,
            page_number      INTEGER,
            context_snippet  TEXT,
            link_type        TEXT NOT NULL,
            confidence       REAL DEFAULT 0.5,
            UNIQUE(source_pe, referenced_pe, link_type, fiscal_year),
            FOREIGN KEY (source_pe) REFERENCES pe_index(pe_number)
        );
        CREATE INDEX IF NOT EXISTS idx_pe_lineage_src ON pe_lineage(source_pe);
        CREATE INDEX IF NOT EXISTS idx_pe_lineage_ref ON pe_lineage(referenced_pe);

        CREATE TABLE IF NOT EXISTS project_descriptions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number        TEXT NOT NULL,
            project_number   TEXT,
            project_title    TEXT,
            fiscal_year      TEXT,
            section_header   TEXT NOT NULL,
            description_text TEXT NOT NULL,
            source_file      TEXT,
            page_start       INTEGER,
            page_end         INTEGER,
            created_at       TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_proj_desc_pe ON project_descriptions(pe_number);
        CREATE INDEX IF NOT EXISTS idx_proj_desc_proj ON project_descriptions(project_number);
        CREATE INDEX IF NOT EXISTS idx_proj_desc_fy ON project_descriptions(fiscal_year);
    """)
    logger.info("Dropped enrichment tables.")


# ── Phase 1: Build pe_index ───────────────────────────────────────────────────

def run_phase1(conn: sqlite3.Connection, stop_event: threading.Event | None = None) -> int:
    """Aggregate PE numbers from budget_lines and pdf_pe_numbers into pe_index.

    Pass 1: Index PEs from budget_lines (Excel data) with full metadata.
    Pass 2: Discover additional PEs from pdf_pe_numbers that are NOT already
             in pe_index, extracting metadata from PDF page text.
    """
    logger.info("[Phase 1] Building pe_index...")
    t0 = time.time()

    # Ensure pe_index has the 'source' column (upgrade path for older DBs)
    try:
        _ensure_pe_index_source_column(conn)
    except sqlite3.OperationalError:
        pass  # pe_index doesn't exist yet; will be created by _drop_enrichment_tables

    # ── Pass 1: budget_lines (Excel-sourced PEs) ─────────────────────────
    logger.info("  Pass 1: Querying budget_lines for distinct PE numbers...")
    rows = conn.execute("""
        WITH org_ranked AS (
            SELECT pe_number,
                   organization_name,
                   COUNT(*) AS cnt,
                   ROW_NUMBER() OVER (
                       PARTITION BY pe_number
                       ORDER BY COUNT(*) DESC
                   ) AS rn
            FROM budget_lines
            WHERE pe_number IS NOT NULL AND pe_number != ''
              AND organization_name IS NOT NULL
            GROUP BY pe_number, organization_name
        ),
        best_org AS (
            SELECT pe_number, organization_name FROM org_ranked WHERE rn = 1
        )
        SELECT
            b.pe_number,
            MAX(CASE WHEN b.line_item_title IS NOT NULL AND b.line_item_title != ''
                     THEN b.line_item_title END) AS display_title,
            bo.organization_name AS org_name,
            MAX(b.budget_type) AS budget_type,
            json_group_array(DISTINCT b.fiscal_year)
                FILTER (WHERE b.fiscal_year IS NOT NULL) AS fiscal_years,
            json_group_array(DISTINCT b.exhibit_type)
                FILTER (WHERE b.exhibit_type IS NOT NULL) AS exhibit_types
        FROM budget_lines b
        LEFT JOIN best_org bo ON bo.pe_number = b.pe_number
        WHERE b.pe_number IS NOT NULL AND b.pe_number != ''
        GROUP BY b.pe_number
    """).fetchall()

    pass1_count = 0
    if rows:
        if stop_event and stop_event.is_set():
            logger.info("  Phase 1 stopped before Pass 1 insert.")
            return 0

        conn.executemany("""
            INSERT OR REPLACE INTO pe_index
                (pe_number, display_title, organization_name, budget_type,
                 fiscal_years, exhibit_types, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'budget_lines', datetime('now'))
        """, [
            (r[0], r[1], r[2], r[3], r[4], r[5])
            for r in rows
        ])
        conn.commit()
        pass1_count = len(rows)
    logger.info("  Pass 1: Indexed %d PEs from budget_lines.", pass1_count)

    # ── Pass 2: pdf_pe_numbers (PDF-only PEs) ────────────────────────────
    # Discover PEs that appear in PDF documents but have no budget_lines rows.
    pass2_count = 0
    try:
        pdf_only_pes = conn.execute("""
            SELECT DISTINCT ppn.pe_number
            FROM pdf_pe_numbers ppn
            WHERE NOT EXISTS (
                SELECT 1 FROM pe_index pi WHERE pi.pe_number = ppn.pe_number
            )
        """).fetchall()
    except sqlite3.OperationalError:
        # pdf_pe_numbers table may not exist
        pdf_only_pes = []

    if pdf_only_pes:
        logger.info("  Pass 2: Found %d PDF-only PEs to index...", len(pdf_only_pes))

        if stop_event and stop_event.is_set():
            logger.info("  Phase 1 stopped before Pass 2.")
            return pass1_count

        pe_list = [row[0] for row in pdf_only_pes]

        # ── Bulk fetch: replace 5 queries per PE with 3 bulk queries ──────
        # 1) Page texts for title extraction (grouped by PE, limited per PE)
        pe_texts: dict[str, list[str]] = {pe: [] for pe in pe_list}
        try:
            text_rows = conn.execute("""
                SELECT ppn.pe_number, pp.page_text
                FROM pdf_pe_numbers ppn
                JOIN pdf_pages pp ON pp.id = ppn.pdf_page_id
                WHERE ppn.pe_number IN ({ph})
                  AND pp.page_text IS NOT NULL
            """.format(ph=",".join("?" for _ in pe_list)), pe_list).fetchall()
            for pe, text in text_rows:
                if len(pe_texts[pe]) < 10:
                    pe_texts[pe].append(text)
        except sqlite3.OperationalError:
            pass

        # 2) Org + exhibit type (most common per PE) in one grouped query
        pe_org: dict[str, str | None] = {pe: None for pe in pe_list}
        pe_exhibit: dict[str, str | None] = {pe: None for pe in pe_list}
        try:
            meta_rows = conn.execute("""
                SELECT ppn.pe_number,
                       pp.source_category,
                       pp.exhibit_type,
                       COUNT(*) AS cnt
                FROM pdf_pe_numbers ppn
                JOIN pdf_pages pp ON pp.id = ppn.pdf_page_id
                WHERE ppn.pe_number IN ({ph})
                GROUP BY ppn.pe_number, pp.source_category, pp.exhibit_type
                ORDER BY ppn.pe_number, cnt DESC
            """.format(ph=",".join("?" for _ in pe_list)), pe_list).fetchall()
            for pe, src_cat, et, cnt in meta_rows:
                if src_cat and pe_org[pe] is None:
                    pe_org[pe] = src_cat
                if et and pe_exhibit[pe] is None:
                    pe_exhibit[pe] = et
        except sqlite3.OperationalError:
            pass

        # 3) Fiscal years + distinct exhibit types per PE
        pe_fys: dict[str, list[str]] = {pe: [] for pe in pe_list}
        pe_ets: dict[str, list[str]] = {pe: [] for pe in pe_list}
        try:
            fy_rows = conn.execute("""
                SELECT ppn.pe_number, ppn.fiscal_year
                FROM pdf_pe_numbers ppn
                WHERE ppn.pe_number IN ({ph})
                  AND ppn.fiscal_year IS NOT NULL
                GROUP BY ppn.pe_number, ppn.fiscal_year
            """.format(ph=",".join("?" for _ in pe_list)), pe_list).fetchall()
            for pe, fy in fy_rows:
                pe_fys[pe].append(fy)
        except sqlite3.OperationalError:
            pass
        try:
            et_rows = conn.execute("""
                SELECT ppn.pe_number, pp.exhibit_type
                FROM pdf_pe_numbers ppn
                JOIN pdf_pages pp ON pp.id = ppn.pdf_page_id
                WHERE ppn.pe_number IN ({ph})
                  AND pp.exhibit_type IS NOT NULL
                GROUP BY ppn.pe_number, pp.exhibit_type
            """.format(ph=",".join("?" for _ in pe_list)), pe_list).fetchall()
            for pe, et in et_rows:
                pe_ets[pe].append(et)
        except sqlite3.OperationalError:
            pass

        # ── Build insert buffer from pre-fetched data ─────────────────────
        insert_buf: list[tuple] = []
        t0_pass2 = time.monotonic()
        for pass2_idx, pe in enumerate(pe_list):
            title = None
            for text in pe_texts[pe]:
                title = _extract_pe_title_from_text(pe, text)
                if title:
                    break

            org_name = pe_org[pe]

            budget_type = None
            top_exhibit = pe_exhibit[pe]
            if top_exhibit:
                budget_type = _EXHIBIT_TO_BUDGET_TYPE.get(
                    top_exhibit.lower(), None
                )

            fiscal_years_json = json.dumps(pe_fys[pe]) if pe_fys[pe] else "[]"
            exhibit_types_json = json.dumps(pe_ets[pe]) if pe_ets[pe] else "[]"

            insert_buf.append((
                pe, title, org_name, budget_type,
                fiscal_years_json, exhibit_types_json,
            ))

            if (pass2_idx + 1) % 200 == 0 or pass2_idx + 1 == len(pe_list):
                _log_progress("Phase 1 Pass 2", pass2_idx + 1, len(pe_list), t0_pass2)

        if insert_buf:
            conn.executemany("""
                INSERT OR IGNORE INTO pe_index
                    (pe_number, display_title, organization_name, budget_type,
                     fiscal_years, exhibit_types, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, 'pdf', datetime('now'))
            """, insert_buf)
            conn.commit()
            pass2_count = len(insert_buf)
        logger.info("  Pass 2: Indexed %d additional PEs from PDF documents.", pass2_count)
    else:
        logger.info("  Pass 2: No additional PDF-only PEs found.")

    total = pass1_count + pass2_count
    logger.info("[Phase 1] Total: %d PEs in pe_index (%.1fs).", total, time.time() - t0)
    return total


# ── Phase 2: Link PDFs to PEs ─────────────────────────────────────────────────

def run_phase2(conn: sqlite3.Connection, stop_event: threading.Event | None = None) -> int:
    """Scan pdf_pages text for PE number mentions and populate pe_descriptions."""
    logger.info("[Phase 2] Linking PDF pages to PE numbers...")

    # Build set of known PE numbers for fast membership test
    known_pes = {
        r[0] for r in conn.execute("SELECT pe_number FROM pe_index").fetchall()
    }
    if not known_pes:
        logger.info("pe_index is empty -- run Phase 1 first.")
        return 0

    # Get all source files already processed (for incremental runs)
    done_files = {
        r[0] for r in conn.execute(
            "SELECT DISTINCT source_file FROM pe_descriptions"
        ).fetchall()
    }

    # Get all distinct source files in pdf_pages
    pdf_files = conn.execute("""
        SELECT DISTINCT source_file FROM pdf_pages ORDER BY source_file
    """).fetchall()
    pdf_files = [r[0] for r in pdf_files if r[0] not in done_files]

    if not pdf_files:
        logger.info("All PDF files already processed -- nothing to do.")
        return 0

    logger.info("Processing %d PDF file(s)...", len(pdf_files))
    total_desc = 0
    insert_buf: list[tuple] = []
    t0_mono = time.monotonic()

    errors: list[str] = []
    for i, source_file in enumerate(pdf_files, 1):
        if stop_event and stop_event.is_set():
            logger.info("  Phase 2 stopped at file %d/%d.", i - 1, len(pdf_files))
            break
        try:
            fy = _extract_fy_from_path(source_file)

            pages = conn.execute("""
                SELECT page_number, page_text FROM pdf_pages
                WHERE source_file = ?
                ORDER BY page_number
            """, (source_file,)).fetchall()

            # Group consecutive pages that mention the same PE into runs
            # pe_number → (first_page, last_page, text_parts[])
            pe_runs: dict[str, dict] = {}

            for page_num, page_text in pages:
                if not page_text:
                    continue
                found = set(PE_NUMBER.findall(page_text))
                for pe in found:
                    if pe not in known_pes:
                        continue
                    if pe not in pe_runs:
                        pe_runs[pe] = {
                            "page_start": page_num,
                            "page_end": page_num,
                            "parts": [page_text],
                        }
                    else:
                        pe_runs[pe]["page_end"] = page_num
                        pe_runs[pe]["parts"].append(page_text)

            # For each PE run in this file, extract narrative sections
            for pe, run in pe_runs.items():
                run_text = "\n\n".join(run["parts"])
                sections = parse_narrative_sections(run_text)
                if sections:
                    for sec in sections:
                        insert_buf.append((
                            pe, fy, source_file,
                            run["page_start"], run["page_end"],
                            sec["header"], sec["text"],
                        ))
                else:
                    # No recognised section headers — store full text under blank header
                    text = run_text[:_MAX_NARRATIVE_TEXT_CHARS]
                    if text.strip():
                        insert_buf.append((
                            pe, fy, source_file,
                            run["page_start"], run["page_end"],
                            None, text,
                        ))
        except Exception as exc:
            errors.append(f"{source_file}: {exc}")
            logger.warning("Error processing %s: %s", source_file, exc)
            continue

        if insert_buf and (i % 50 == 0 or i == len(pdf_files)):
            conn.executemany("""
                INSERT INTO pe_descriptions
                    (pe_number, fiscal_year, source_file, page_start, page_end,
                     section_header, description_text)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, insert_buf)
            conn.commit()
            total_desc += len(insert_buf)
            insert_buf = []
            _log_progress("Phase 2", i, len(pdf_files), t0_mono)

    if insert_buf:
        conn.executemany("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end,
                 section_header, description_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, insert_buf)
        conn.commit()
        total_desc += len(insert_buf)

    if errors:
        logger.warning("%d file(s) had errors during Phase 2:", len(errors))
        for err in errors[:5]:
            logger.warning("  - %s", err)
        if len(errors) > 5:
            logger.warning("  ... and %d more", len(errors) - 5)

    # Rebuild pe_descriptions_fts index if the table exists.
    # The triggers keep it in sync for individual inserts, but a full
    # rebuild after bulk loading ensures the index is complete and
    # consistent (covers rows inserted before triggers were created).
    try:
        conn.execute("SELECT 1 FROM pe_descriptions_fts LIMIT 0")
        conn.execute("INSERT INTO pe_descriptions_fts(pe_descriptions_fts) VALUES('rebuild')")
        conn.commit()
        logger.info("  Rebuilt pe_descriptions_fts index.")
    except (sqlite3.OperationalError, sqlite3.DatabaseError):
        pass  # pe_descriptions_fts table doesn't exist yet

    logger.info("Done. %d description rows inserted.", total_desc)
    return total_desc


# ── Phase 3: Generate Tags ────────────────────────────────────────────────────

def _tags_from_keywords(pe_number: str, text: str) -> list[tuple]:
    """Match description text against predefined domain taxonomy.

    Checks tier-1 taxonomy (confidence 0.9) then tier-2 broader terms
    (confidence 0.7).  run_phase3() inlines equivalent loops with source-
    differentiated confidence (budget_lines vs PDF narrative).
    """
    tags: list[tuple] = []
    for tag, patterns in _COMPILED_TAXONOMY:
        for pat in patterns:
            if pat.search(text):
                tags.append((pe_number, tag, "keyword", 0.9))
                break
    for tag, patterns in _COMPILED_TAXONOMY_TIER2:
        for pat in patterns:
            if pat.search(text):
                tags.append((pe_number, tag, "keyword", 0.7))
                break
    return tags


def _tags_from_llm(
    pe_texts: dict[str, str],  # pe_number → description text
    model: str = "claude-haiku-4-5-20251001",
) -> dict[str, list[str]]:
    """Call Claude to generate tags for a batch of PE descriptions.

    Returns dict mapping pe_number → list of tag strings.
    Silently returns empty results on any error.
    """
    # _HAS_ANTHROPIC is checked once at Phase 3 entry; this is a safety fallback.
    if not _HAS_ANTHROPIC:
        return {}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set. Skipping LLM tags.")
        return {}

    client = anthropic.Anthropic(api_key=api_key)

    # Build a single prompt with all PEs in the batch
    pe_list = list(pe_texts.items())
    prompt_parts = []
    for pe_num, text in pe_list:
        excerpt = text[:1500].replace("\n", " ")
        prompt_parts.append(f'PE {pe_num}:\n"{excerpt}"')

    prompt = (
        "You are a DoD budget analyst. For each Program Element (PE) below, "
        "extract 3-8 concise capability tags that describe the program's "
        "technical domain and mission area. Use lowercase hyphenated tags "
        "(e.g. hypersonic, missile-defense, ai-ml, electronic-warfare).\n\n"
        "Return ONLY a JSON object mapping PE number to array of tag strings.\n"
        "Example: {\"0602120A\": [\"cyber\", \"software\", \"cloud\"]}\n\n"
        + "\n\n".join(prompt_parts)
    )

    try:
        msg = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        # Extract JSON object from response
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return {}
        return json.loads(m.group())
    except Exception as e:
        logger.warning("LLM call failed: %s", e)
        return {}


def run_phase3(conn: sqlite3.Connection, with_llm: bool = False,
               stop_event: threading.Event | None = None) -> int:
    """Generate tags for all PE numbers from multiple sources.

    LION-104: Also uses budget_lines text fields for keyword matching.
    LION-105: Differentiates confidence by tag source.
    LION-106: Tracks source_files for each tag.
    """
    logger.info("[Phase 3] Generating tags (LLM=%s)...", "yes" if with_llm else "no")

    # Check anthropic availability once at phase entry (TODO-L3)
    if with_llm and not _HAS_ANTHROPIC:
        logger.warning("--with-llm requested but anthropic package is not installed.")
        logger.warning("Install with: pip install anthropic")
        logger.warning("Falling back to rule-based tagging only.")
        with_llm = False

    pe_numbers = [
        r[0] for r in conn.execute("SELECT pe_number FROM pe_index").fetchall()
    ]
    if not pe_numbers:
        logger.info("pe_index is empty -- run Phase 1 first.")
        return 0

    # Skip PEs that already have tags (incremental)
    tagged = {
        r[0] for r in conn.execute(
            "SELECT DISTINCT pe_number FROM pe_tags"
        ).fetchall()
    }
    to_tag = [pe for pe in pe_numbers if pe not in tagged]
    if not to_tag:
        logger.info("All PEs already tagged -- nothing to do.")
        return 0

    logger.info("Tagging %d PE(s)...", len(to_tag))

    # --- Pre-load structured fields for all untagged PEs in one query ---
    # Also collect source_files for LION-106 provenance tracking.
    structured_fields: dict[str, tuple] = {}
    structured_sources: dict[str, list[str]] = {}
    placeholders = ",".join("?" * len(to_tag))
    for row in conn.execute(f"""
        SELECT pe_number,
               MAX(budget_activity_title) AS ba_title,
               MAX(appropriation_title)   AS approp_title,
               MAX(organization_name)     AS org_name
        FROM budget_lines
        WHERE pe_number IN ({placeholders})
        GROUP BY pe_number
    """, to_tag).fetchall():
        structured_fields[row[0]] = (row[1], row[2], row[3])

    # LION-106: Collect distinct source files per PE for provenance.
    # Use a subquery since json_group_array doesn't support DISTINCT.
    for row in conn.execute(f"""
        SELECT pe_number, json_group_array(source_file) AS src_files
        FROM (
            SELECT DISTINCT pe_number, source_file
            FROM budget_lines
            WHERE pe_number IN ({placeholders})
        )
        GROUP BY pe_number
    """, to_tag).fetchall():
        try:
            structured_sources[row[0]] = json.loads(row[1])
        except (json.JSONDecodeError, TypeError):
            structured_sources[row[0]] = []

    # --- LION-104: Pre-load budget_lines text fields for keyword matching ---
    # Concatenates line_item_title, budget_activity_title, and account_title
    # so PEs without PDF coverage still get keyword tags.
    bl_texts: dict[str, str] = {}
    for row in conn.execute(f"""
        SELECT pe_number, GROUP_CONCAT(combined_text, ' ') AS titles
        FROM (
            SELECT DISTINCT pe_number,
                   COALESCE(line_item_title, '') || ' ' ||
                   COALESCE(budget_activity_title, '') || ' ' ||
                   COALESCE(account_title, '') AS combined_text
            FROM budget_lines
            WHERE pe_number IN ({placeholders})
              AND (line_item_title IS NOT NULL
                   OR budget_activity_title IS NOT NULL
                   OR account_title IS NOT NULL)
        )
        GROUP BY pe_number
    """, to_tag).fetchall():
        bl_texts[row[0]] = row[1] or ""

    # --- Pre-load all description text for untagged PEs ---
    desc_texts: dict[str, list[str]] = {}
    desc_sources: dict[str, list[str]] = {}
    for row in conn.execute(f"""
        SELECT pe_number, description_text, source_file
        FROM pe_descriptions
        WHERE pe_number IN ({placeholders})
          AND description_text IS NOT NULL
    """, to_tag).fetchall():
        desc_texts.setdefault(row[0], []).append(row[1])
        desc_sources.setdefault(row[0], [])
        if row[2] and row[2] not in desc_sources[row[0]]:
            desc_sources[row[0]].append(row[2])

    # insert_buf: (pe_number, project_number, tag, tag_source, confidence, source_files_json)
    insert_buf: list[tuple] = []
    total_tags = 0

    # --- HAWK-2: Pre-load project-level text for project-level tagging ---
    # pe_number → [(project_number, text), ...]
    project_texts: dict[str, list[tuple[str, str]]] = {}
    try:
        for row in conn.execute(f"""
            SELECT pe_number, project_number, description_text
            FROM project_descriptions
            WHERE pe_number IN ({placeholders})
              AND project_number IS NOT NULL
              AND description_text IS NOT NULL
        """, to_tag).fetchall():
            project_texts.setdefault(row[0], []).append((row[1], row[2]))
    except sqlite3.OperationalError:
        pass  # project_descriptions table may not exist yet

    t0_mono = time.monotonic()
    for tag_idx, pe in enumerate(to_tag):
        if stop_event and stop_event.is_set():
            logger.info("  Phase 3 stopped at PE %d/%d.", tag_idx, len(to_tag))
            break

        # Progress every 100 PEs
        if tag_idx > 0 and tag_idx % 100 == 0:
            _log_progress("Phase 3", tag_idx, len(to_tag), t0_mono)

        # LION-106: Source files for this PE's structured tags
        pe_src_json = json.dumps(structured_sources.get(pe, []))

        # 3a: structured field tags — LION-105: confidence=1.0 (direct match)
        # These are PE-level (project_number=NULL)
        fields = structured_fields.get(pe)
        if fields:
            ba_title, approp_title, org_name = fields
            if ba_title:
                for pattern, tag in _BUDGET_ACTIVITY_TAGS:
                    if pattern.search(ba_title):
                        insert_buf.append((pe, None, tag, "structured", 1.0, pe_src_json))
                        break
            if approp_title:
                low = approp_title.lower()
                for key, tag in _APPROP_TAGS.items():
                    if key in low:
                        insert_buf.append((pe, None, tag, "structured", 1.0, pe_src_json))
                        break
            if org_name:
                low = org_name.lower()
                for key, tag in _ORG_TAGS.items():
                    if key in low:
                        insert_buf.append((pe, None, tag, "structured", 1.0, pe_src_json))
                        break

        # 3b: keyword tags from budget_lines text fields (PE-level)
        # LION-104: Use line_item_title etc. for PEs with or without PDF text
        # LION-105: confidence=0.9 tier-1, 0.7 tier-2 (field-level match)
        bl_text = bl_texts.get(pe, "")
        if bl_text:
            for tag, patterns in _COMPILED_TAXONOMY:
                for pat in patterns:
                    if pat.search(bl_text):
                        insert_buf.append((pe, None, tag, "keyword", 0.9, pe_src_json))
                        break
            for tag, patterns in _COMPILED_TAXONOMY_TIER2:
                for pat in patterns:
                    if pat.search(bl_text):
                        insert_buf.append((pe, None, tag, "keyword", 0.7, pe_src_json))
                        break

        # 3c: keyword tags from PDF narrative text (PE-level)
        # LION-105: confidence=0.8 tier-1, 0.65 tier-2 (narrative context, more noise)
        combined_desc = " ".join(desc_texts.get(pe, []))
        desc_src_json = json.dumps(desc_sources.get(pe, []))
        if combined_desc:
            for tag, patterns in _COMPILED_TAXONOMY:
                for pat in patterns:
                    if pat.search(combined_desc):
                        insert_buf.append((pe, None, tag, "keyword", 0.8, desc_src_json))
                        break
            for tag, patterns in _COMPILED_TAXONOMY_TIER2:
                for pat in patterns:
                    if pat.search(combined_desc):
                        insert_buf.append((pe, None, tag, "keyword", 0.65, desc_src_json))
                        break

        # HAWK-2: 3e: project-level keyword tags from project_descriptions
        # When project-level text is available, apply tags at the project level
        pe_projects = project_texts.get(pe, [])
        for proj_num, proj_text in pe_projects:
            for tag, patterns in _COMPILED_TAXONOMY:
                for pat in patterns:
                    if pat.search(proj_text):
                        insert_buf.append((pe, proj_num, tag, "keyword", 0.85, desc_src_json))
                        break
            for tag, patterns in _COMPILED_TAXONOMY_TIER2:
                for pat in patterns:
                    if pat.search(proj_text):
                        insert_buf.append((pe, proj_num, tag, "keyword", 0.65, desc_src_json))
                        break

        # TODO-L4: Per-PE debug logging for rule-based tagger diagnostics
        pe_tags_in_buf = [t for t in insert_buf if t[0] == pe]
        if pe_tags_in_buf:
            tag_names = [t[2] for t in pe_tags_in_buf]
            logger.debug("Rule-based tagger: PE %s matched tags %s", pe, tag_names)

    # Debug logging for rule-based tagger (TODO-L4)
    if insert_buf:
        # Count unique PEs with tags for diagnostic
        tagged_pes = {row[0] for row in insert_buf}
        logger.info(
            "  Rule-based tagger: %d tag rows for %d / %d PEs (sources: %s)",
            len(insert_buf),
            len(tagged_pes),
            len(to_tag),
            ", ".join(
                f"{src}={cnt}"
                for src, cnt in sorted(
                    {
                        row[3]: sum(1 for r in insert_buf if r[3] == row[3])
                        for row in insert_buf
                    }.items()
                )
            ),
        )
    else:
        logger.warning(
            "  Rule-based tagger: 0 tag rows for %d PEs. "
            "bl_texts populated: %d, desc_texts populated: %d, structured_fields populated: %d",
            len(to_tag),
            sum(1 for v in bl_texts.values() if v.strip()),
            sum(1 for v in desc_texts.values() if v),
            len(structured_fields),
        )

    # Flush structured + keyword tags
    if insert_buf:
        conn.executemany("""
            INSERT OR IGNORE INTO pe_tags
                (pe_number, project_number, tag, tag_source, confidence, source_files)
            VALUES (?, ?, ?, ?, ?, ?)
        """, insert_buf)
        conn.commit()
        total_tags += len(insert_buf)
        insert_buf = []

    # 3d: LLM tags (optional, in batches of 10)
    # LION-105: confidence=0.7 for LLM-generated tags
    if with_llm:
        logger.info("Running LLM tagging in batches of 10...")
        batch_size = 10
        for i in range(0, len(to_tag), batch_size):
            if stop_event and stop_event.is_set():
                logger.info("  Phase 3 LLM stopped at batch %d.", i // batch_size)
                break
            batch_pes = to_tag[i:i + batch_size]
            pe_texts: dict[str, str] = {}
            for pe in batch_pes:
                texts = desc_texts.get(pe, [])
                if texts:
                    pe_texts[pe] = texts[0]

            if pe_texts:
                llm_result = _tags_from_llm(pe_texts)
                for pe_num, tags in llm_result.items():
                    src_json = json.dumps(desc_sources.get(pe_num, []))
                    for tag in tags:
                        tag = tag.strip().lower().replace(" ", "-")
                        if tag:
                            insert_buf.append((pe_num, None, tag, "llm", 0.7, src_json))

            if insert_buf:
                conn.executemany("""
                    INSERT OR IGNORE INTO pe_tags
                        (pe_number, project_number, tag, tag_source, confidence, source_files)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, insert_buf)
                conn.commit()
                total_tags += len(insert_buf)
                insert_buf = []
            logger.info("[%d/%d] LLM batch done", min(i + batch_size, len(to_tag)), len(to_tag))
            time.sleep(0.5)

    logger.info("Done. %d tag rows inserted.", total_tags)
    return total_tags


# ── Phase 4: Detect Cross-PE Lineage ─────────────────────────────────────────

# Noise reduction constants for Phase 4 name matching (4b).
# See: https://github.com/.../issues/phase4-noise — name_match produces many
# false-positive links from tabular PE listing pages that mention dozens of
# programs in table format.  These filters reduce noise by ~85-95%.
_MIN_TEXT_FOR_NAME_MATCH = 200   # Skip name_match on very short text blocks
_MAX_PE_REFS_FOR_NAME_MATCH = 5  # Skip name_match if text contains >5 distinct PE refs (listing page)
_MAX_NAME_MATCHES_PER_ROW = 3    # Cap name_match links per description row
_MIN_TITLE_WORDS = 5             # Require at least 5 words in title for name matching


def run_phase4(conn: sqlite3.Connection, stop_event: threading.Event | None = None) -> int:
    """Scan description text for PE number cross-references and name matches.

    Uses rowid-based checkpointing so interrupted runs can resume from where
    they left off rather than re-scanning all pe_descriptions rows.

    Noise reduction strategies for name_match (4b):
      1. Skip name_match on text blocks shorter than _MIN_TEXT_FOR_NAME_MATCH chars
      2. Skip name_match on PE listing pages (>_MAX_PE_REFS_FOR_NAME_MATCH distinct PE refs)
      3. Cap name_match links per row at _MAX_NAME_MATCHES_PER_ROW
      4. Require at least _MIN_TITLE_WORDS words in title (up from 4)
      5. Dedup: skip name_match for PEs already found via explicit_pe_ref (4a)
    """
    logger.info("[Phase 4] Detecting cross-PE lineage...")

    known_pes = {
        r[0] for r in conn.execute("SELECT pe_number FROM pe_index").fetchall()
    }
    if not known_pes:
        logger.info("pe_index is empty -- run Phase 1 first.")
        return 0

    # ── Checkpoint-based resumption ──────────────────────────────────────
    checkpoint_rowid = _get_checkpoint(conn, 4)

    # Backward compatibility: if no checkpoint exists but pe_lineage already
    # has rows (from a run before checkpointing was added), fall back to the
    # legacy done_pairs mechanism for this run.  The checkpoint will be saved
    # at the end, so subsequent runs use the fast rowid path.
    use_done_pairs = False
    done_pairs: set[tuple[str, str | None]] = set()
    if checkpoint_rowid == 0:
        lineage_count = conn.execute("SELECT COUNT(*) FROM pe_lineage").fetchone()[0]
        if lineage_count > 0:
            use_done_pairs = True
            done_pairs = {
                (r[0], r[1]) for r in conn.execute(
                    "SELECT DISTINCT source_pe, source_file FROM pe_lineage"
                ).fetchall()
            }
            logger.info(
                "  No checkpoint found — using done_pairs (%s pairs) for backward compat.",
                f"{len(done_pairs):,}",
            )

    if checkpoint_rowid > 0:
        logger.info("  Resuming from checkpoint (rowid > %s)", f"{checkpoint_rowid:,}")

    # Build title index for name matching (phase 4b)
    # Only titles with >= _MIN_TITLE_WORDS words are useful to avoid false positives.
    # Each entry includes lowercase keyword tokens for a fast pre-filter:
    # skip the expensive regex unless ALL keywords appear in the text.
    # This eliminates ~95% of regex calls (most titles don't match most texts).
    title_index: list[tuple[str, tuple[str, ...], re.Pattern]] = []
    for row in conn.execute(
        "SELECT pe_number, display_title FROM pe_index WHERE display_title IS NOT NULL"
    ).fetchall():
        pe, title = row
        words = title.split()
        if len(words) >= _MIN_TITLE_WORDS:
            match_words = words[:_MIN_TITLE_WORDS]
            phrase = r"\s+".join(re.escape(w) for w in match_words)
            # Pre-filter keywords: the first N words, lowered, for fast 'in' check
            keywords = tuple(w.lower() for w in match_words)
            title_index.append((pe, keywords, re.compile(phrase, re.IGNORECASE)))

    insert_buf: list[tuple] = []
    total = 0
    CHUNK = 500  # rows per DB fetch to bound memory use

    # Get remaining row count for progress reporting
    desc_remaining = conn.execute(
        "SELECT COUNT(*) FROM pe_descriptions WHERE description_text IS NOT NULL AND rowid > ?",
        (checkpoint_rowid,),
    ).fetchone()[0]
    desc_total_all = conn.execute(
        "SELECT COUNT(*) FROM pe_descriptions WHERE description_text IS NOT NULL"
    ).fetchone()[0]

    if checkpoint_rowid > 0 and desc_remaining < desc_total_all:
        logger.info(
            "  Previously processed: %s — remaining: %s",
            f"{desc_total_all - desc_remaining:,}", f"{desc_remaining:,}",
        )

    if desc_remaining == 0 and not use_done_pairs:
        logger.info("All description rows already processed (checkpoint up to date).")
    else:
        logger.info(
            "Scanning %s description rows against %d PEs and %d title patterns...",
            f"{desc_remaining:,}", len(known_pes), len(title_index),
        )

    # Stream pe_descriptions in chunks, ordered by rowid for deterministic
    # checkpoint resumption.  Only fetch rows beyond the saved checkpoint.
    cur = conn.execute("""
        SELECT rowid, pe_number, fiscal_year, source_file, page_start, description_text
        FROM pe_descriptions
        WHERE description_text IS NOT NULL AND rowid > ?
        ORDER BY rowid
    """, (checkpoint_rowid,))

    rows_processed = 0
    skipped = 0
    chunk_max_rowid = checkpoint_rowid
    t0_mono = time.monotonic()
    while True:
        if stop_event and stop_event.is_set():
            logger.info("  Phase 4 stopped at row %s.", f"{rows_processed:,}")
            # Flush pending inserts + save checkpoint before stopping
            if insert_buf:
                conn.executemany("""
                    INSERT OR IGNORE INTO pe_lineage
                        (source_pe, referenced_pe, fiscal_year, source_file,
                         page_number, context_snippet, link_type, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, insert_buf)
                total += len(insert_buf)
                insert_buf = []
            if chunk_max_rowid > checkpoint_rowid:
                _save_checkpoint(conn, 4, chunk_max_rowid)
            conn.commit()
            break

        chunk = cur.fetchmany(CHUNK)
        if not chunk:
            break

        for rowid, pe_num, fy, source_file, page_start, text in chunk:
            chunk_max_rowid = rowid  # ordered by rowid, so last = max

            if use_done_pairs and (pe_num, source_file) in done_pairs:
                skipped += 1
                continue

            # 4a: Explicit PE number references
            # Collect explicit refs for dedup against name_match (strategy 5)
            explicit_refs: set[str] = set()
            for m in PE_NUMBER.finditer(text):
                ref_pe = m.group()
                if ref_pe == pe_num:
                    continue
                if ref_pe not in known_pes:
                    continue
                explicit_refs.add(ref_pe)
                snippet = _context_window(text, m.start())
                insert_buf.append((
                    pe_num, ref_pe, fy, source_file, page_start,
                    snippet, "explicit_pe_ref", 0.95,
                ))

            # 4b: Program name matching (with keyword pre-filter + noise reduction)
            #
            # Noise reduction strategies applied here:
            #   Strategy 1: Skip name_match on very short text blocks
            #   Strategy 2: Skip if text is a PE listing page (many PE refs)
            #   Strategy 3: Cap name_match links per row
            #   Strategy 5: Dedup — skip PEs already found via explicit_pe_ref

            # Strategy 1: minimum text length for name matching
            if len(text) < _MIN_TEXT_FOR_NAME_MATCH:
                continue  # skip 4b entirely for this row — text too short

            # Strategy 2: PE density filter — listing pages mention many PEs
            if len(explicit_refs) > _MAX_PE_REFS_FOR_NAME_MATCH:
                continue  # skip 4b — this is likely a summary/listing page

            text_lower = text.lower()
            name_match_count = 0
            for ref_pe, keywords, pattern in title_index:
                if ref_pe == pe_num:
                    continue
                # Strategy 5: skip name_match for PEs already found via 4a
                if ref_pe in explicit_refs:
                    continue
                # Strategy 3: cap name_match links per row
                if name_match_count >= _MAX_NAME_MATCHES_PER_ROW:
                    break
                # Fast pre-filter: skip regex unless all keywords appear
                if not all(kw in text_lower for kw in keywords):
                    continue
                name_m = pattern.search(text)
                if name_m:
                    snippet = _context_window(text, name_m.start())
                    insert_buf.append((
                        pe_num, ref_pe, fy, source_file, page_start,
                        snippet, "name_match", 0.6,
                    ))
                    name_match_count += 1

        rows_processed += len(chunk)

        # Flush insert buffer and save checkpoint atomically
        if insert_buf:
            conn.executemany("""
                INSERT OR IGNORE INTO pe_lineage
                    (source_pe, referenced_pe, fiscal_year, source_file,
                     page_number, context_snippet, link_type, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, insert_buf)
            total += len(insert_buf)
            insert_buf = []
        _save_checkpoint(conn, 4, chunk_max_rowid)
        conn.commit()

        # Progress every 10,000 rows
        if rows_processed % 10_000 < CHUNK:
            _log_progress("Phase 4", rows_processed, desc_remaining, t0_mono)

    if skipped:
        logger.info("Skipped %s already-processed (PE, file) pairs.", f"{skipped:,}")

    # 4c: Extract cross-references from budget_lines.extra_fields JSON.
    # LION-102 stores additional_pe_numbers in extra_fields for rows where
    # multiple PE numbers were found in the same cell.
    xref_count = 0
    try:
        xref_rows = conn.execute("""
            SELECT pe_number, extra_fields, source_file, fiscal_year
            FROM budget_lines
            WHERE extra_fields IS NOT NULL AND pe_number IS NOT NULL
        """).fetchall()
    except sqlite3.OperationalError:
        xref_rows = []

    for primary_pe, extra_json, src_file, fy in xref_rows:
        try:
            data = json.loads(extra_json)
        except (json.JSONDecodeError, TypeError):
            continue
        additional = data.get("additional_pe_numbers", [])
        for ref_pe in additional:
            if ref_pe == primary_pe or ref_pe not in known_pes:
                continue
            insert_buf.append((
                primary_pe, ref_pe, fy, src_file, None,
                "Co-occurrence in budget line extra_fields",
                "excel_co_occurrence", 0.85,
            ))

    if insert_buf:
        try:
            conn.executemany("""
                INSERT OR IGNORE INTO pe_lineage
                    (source_pe, referenced_pe, fiscal_year, source_file,
                     page_number, context_snippet, link_type, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, insert_buf)
            conn.commit()
            xref_count = len(insert_buf)
            total += xref_count
        except Exception as exc:
            logger.warning("Error inserting Excel cross-references: %s", exc)

    if xref_count:
        logger.info("4c: %d Excel co-occurrence links added.", xref_count)
    logger.info("Done. %d lineage rows inserted.", total)
    return total


# ── Phase 5: Project-Level Narrative Decomposition ────────────────────────────

def run_phase5(conn: sqlite3.Connection, stop_event: threading.Event | None = None) -> int:
    """Decompose PE descriptions into project-level sections.

    Iterates pe_descriptions, uses detect_project_boundaries() to find
    project-level text within R-2 narrative content, then parses each
    project's text through parse_narrative_sections().  Results are
    stored in the project_descriptions table.

    When project boundaries cannot be detected, the PE-level text is
    stored with project_number=NULL as a fallback.

    Uses rowid-based checkpointing so interrupted runs can resume.
    """
    logger.info("[Phase 5] Decomposing PE descriptions into project-level sections...")

    # Ensure project_descriptions table exists (may not exist if --rebuild was not used)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS project_descriptions (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number        TEXT NOT NULL,
            project_number   TEXT,
            project_title    TEXT,
            fiscal_year      TEXT,
            section_header   TEXT NOT NULL,
            description_text TEXT NOT NULL,
            source_file      TEXT,
            page_start       INTEGER,
            page_end         INTEGER,
            created_at       TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_proj_desc_pe ON project_descriptions(pe_number);
        CREATE INDEX IF NOT EXISTS idx_proj_desc_proj ON project_descriptions(project_number);
        CREATE INDEX IF NOT EXISTS idx_proj_desc_fy ON project_descriptions(fiscal_year);
    """)

    # Check if we have any pe_descriptions to process
    desc_count_all = conn.execute("SELECT COUNT(*) FROM pe_descriptions").fetchone()[0]
    if desc_count_all == 0:
        logger.info("pe_descriptions is empty -- run Phase 2 first.")
        return 0

    # ── Checkpoint-based resumption ──────────────────────────────────────
    checkpoint_rowid = _get_checkpoint(conn, 5)

    if checkpoint_rowid > 0:
        logger.info("  Resuming from checkpoint (rowid > %s)", f"{checkpoint_rowid:,}")

    # Backward compatibility: keep done_files as secondary skip check
    done_files = {
        r[0] for r in conn.execute(
            "SELECT DISTINCT source_file FROM project_descriptions WHERE source_file IS NOT NULL"
        ).fetchall()
    }

    # Count remaining rows for progress
    desc_remaining = conn.execute(
        "SELECT COUNT(*) FROM pe_descriptions WHERE description_text IS NOT NULL AND rowid > ?",
        (checkpoint_rowid,),
    ).fetchone()[0]

    if desc_remaining == 0:
        logger.info("All description rows already processed (checkpoint up to date).")
    else:
        if checkpoint_rowid > 0:
            logger.info(
                "  Previously processed: %s — remaining: %s",
                f"{desc_count_all - desc_remaining:,}", f"{desc_remaining:,}",
            )
        logger.info("  Scanning %s description rows for project boundaries...", f"{desc_remaining:,}")

    CHUNK = 500
    cur = conn.execute("""
        SELECT rowid, pe_number, fiscal_year, source_file, page_start, page_end,
               section_header, description_text
        FROM pe_descriptions
        WHERE description_text IS NOT NULL AND rowid > ?
        ORDER BY rowid
    """, (checkpoint_rowid,))

    insert_buf: list[tuple] = []
    total_rows = 0
    pe_level_fallback = 0
    rows_processed = 0
    chunk_max_rowid = checkpoint_rowid
    t0_mono = time.monotonic()

    while True:
        if stop_event and stop_event.is_set():
            logger.info("  Phase 5 stopped at row %s.", f"{rows_processed:,}")
            # Flush pending inserts + save checkpoint before stopping
            if insert_buf:
                conn.executemany("""
                    INSERT INTO project_descriptions
                        (pe_number, project_number, project_title, fiscal_year,
                         section_header, description_text, source_file,
                         page_start, page_end)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, insert_buf)
                total_rows += len(insert_buf)
                insert_buf = []
            if chunk_max_rowid > checkpoint_rowid:
                _save_checkpoint(conn, 5, chunk_max_rowid)
            conn.commit()
            break

        chunk = cur.fetchmany(CHUNK)
        if not chunk:
            break

        for rowid, pe_num, fy, source_file, page_start, page_end, section_header, desc_text in chunk:
            chunk_max_rowid = rowid  # ordered by rowid, so last = max

            if source_file and source_file in done_files:
                continue

            # Attempt project-level decomposition
            projects = detect_project_boundaries(desc_text)

            if projects:
                # Parse each project's text into narrative sections
                for proj in projects:
                    sections = parse_narrative_sections(proj["text"])
                    if sections:
                        for sec in sections:
                            insert_buf.append((
                                pe_num, proj["project_number"], proj["project_title"],
                                fy, sec["header"], sec["text"],
                                source_file, page_start, page_end,
                            ))
                    else:
                        # No sub-sections found — store the project text as-is
                        text = proj["text"][:4000]
                        if text.strip():
                            insert_buf.append((
                                pe_num, proj["project_number"], proj["project_title"],
                                fy, section_header or "Project Description", text,
                                source_file, page_start, page_end,
                            ))
            else:
                # PE-level fallback: no project boundaries detected
                sections = parse_narrative_sections(desc_text)
                if sections:
                    for sec in sections:
                        insert_buf.append((
                            pe_num, None, None,
                            fy, sec["header"], sec["text"],
                            source_file, page_start, page_end,
                        ))
                else:
                    # Store as single PE-level entry
                    text = desc_text[:4000]
                    if text.strip():
                        insert_buf.append((
                            pe_num, None, None,
                            fy, section_header or "Description", text,
                            source_file, page_start, page_end,
                        ))
                pe_level_fallback += 1

        rows_processed += len(chunk)

        # Flush buffer and save checkpoint atomically
        if insert_buf:
            conn.executemany("""
                INSERT INTO project_descriptions
                    (pe_number, project_number, project_title, fiscal_year,
                     section_header, description_text, source_file,
                     page_start, page_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, insert_buf)
            total_rows += len(insert_buf)
            insert_buf = []
        _save_checkpoint(conn, 5, chunk_max_rowid)
        conn.commit()

        # Progress every 10,000 rows
        if rows_processed % 10_000 < CHUNK and desc_remaining > 0:
            _log_progress("Phase 5", rows_processed, desc_remaining, t0_mono)

    if insert_buf:
        conn.executemany("""
            INSERT INTO project_descriptions
                (pe_number, project_number, project_title, fiscal_year,
                 section_header, description_text, source_file,
                 page_start, page_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, insert_buf)
        _save_checkpoint(conn, 5, chunk_max_rowid)
        conn.commit()
        total_rows += len(insert_buf)

    proj_rows = conn.execute(
        "SELECT COUNT(*) FROM project_descriptions WHERE project_number IS NOT NULL"
    ).fetchone()[0]
    logger.info(
        "Done. %d project_descriptions rows inserted (%d project-level, %d PE-level fallback).",
        total_rows, proj_rows, pe_level_fallback,
    )
    return total_rows


# ── Orchestrator ──────────────────────────────────────────────────────────────

def enrich(
    db_path: Path,
    phases: set[int],
    with_llm: bool = False,
    rebuild: bool = False,
    stop_event: threading.Event | None = None,
) -> dict:
    """Run enrichment phases and return a structured summary.

    Returns a dict with keys:
        phases_run   — list of phase numbers that executed
        phases_skipped — list of {phase, reason} for phases that did nothing
        phase_results — dict mapping phase number to rows-inserted count
        table_counts — dict mapping table name to final row count
        stopped_after — phase number if gracefully stopped, else None
    """
    if not db_path.exists():
        logger.error("Database not found: %s", db_path)
        logger.error("Run 'python build_budget_db.py' first.")
        sys.exit(1)

    conn = get_connection(db_path)
    # init_pragmas already applied by get_connection; add bulk overrides
    conn.execute("PRAGMA cache_size=-262144")      # 256MB cache (overrides 64MB)
    conn.execute("PRAGMA mmap_size=536870912")     # 512MB mmap
    conn.execute("PRAGMA wal_autocheckpoint=0")    # manual checkpoint at end

    if rebuild:
        logger.info("--rebuild: dropping enrichment tables...")
        _drop_enrichment_tables(conn)

    t0 = time.time()
    logger.info("Enriching database: %s", db_path)
    logger.info("Phases: %s", sorted(phases))

    # Track what each phase accomplished
    phase_results: dict[int, int] = {}
    phases_skipped: list[dict[str, str | int]] = []
    stopped_after: int | None = None

    _phase_runners = {
        1: lambda: run_phase1(conn, stop_event=stop_event),
        2: lambda: run_phase2(conn, stop_event=stop_event),
        3: lambda: run_phase3(conn, with_llm=with_llm, stop_event=stop_event),
        4: lambda: run_phase4(conn, stop_event=stop_event),
        5: lambda: run_phase5(conn, stop_event=stop_event),
    }

    for phase_num in sorted(_phase_runners):
        if phase_num not in phases:
            phases_skipped.append({"phase": phase_num, "reason": "not selected"})
            continue

        result = _phase_runners[phase_num]()
        phase_results[phase_num] = result if isinstance(result, int) else 0

        # A return of 0 from a phase that was requested means it had nothing to do
        if result == 0 and phase_num in phases:
            phases_skipped.append({"phase": phase_num, "reason": "nothing to do (empty input or already done)"})

        if stop_event and stop_event.is_set():
            logger.info("Enrichment stopped gracefully after Phase %d", phase_num)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
            stopped_after = phase_num
            return {
                "phases_run": list(phase_results.keys()),
                "phases_skipped": phases_skipped,
                "phase_results": phase_results,
                "table_counts": {},
                "stopped_after": stopped_after,
            }

    elapsed = time.time() - t0
    logger.info("Enrichment complete in %.1fs", elapsed)
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # Summary counts
    table_counts: dict[str, int] = {}
    for table in ("pe_index", "pe_descriptions", "pe_tags", "pe_lineage", "project_descriptions"):
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            logger.info("  %s: %s rows", table, f"{n:,}")
            table_counts[table] = n
        except sqlite3.OperationalError:
            logger.info("  %s: (table not found)", table)
            table_counts[table] = 0

    conn.close()

    return {
        "phases_run": list(phase_results.keys()),
        "phases_skipped": phases_skipped,
        "phase_results": phase_results,
        "table_counts": table_counts,
        "stopped_after": None,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(
        description="Enrich the DoD budget database with PE index, tags, and lineage."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                        help="Path to SQLite database (default: dod_budget.sqlite)")
    parser.add_argument("--with-llm", action="store_true",
                        help="Enable LLM-based tagging (requires ANTHROPIC_API_KEY)")
    parser.add_argument("--phases", default="1,2,3,4,5",
                        help="Comma-separated phases to run (default: 1,2,3,4,5)")
    parser.add_argument("--rebuild", action="store_true",
                        help="Drop and rebuild all enrichment tables")
    args = parser.parse_args()

    try:
        phases = {int(p.strip()) for p in args.phases.split(",")}
    except ValueError:
        logger.error("--phases must be comma-separated integers, e.g. '1,2,3'")
        sys.exit(1)

    enrich(args.db, phases, with_llm=args.with_llm, rebuild=args.rebuild)


if __name__ == "__main__":
    main()
