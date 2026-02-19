"""
Budget Database Enrichment Pipeline

Runs after build_budget_db.py to populate the enrichment tables:
  - pe_index        — canonical record per PE number across all years/exhibits
  - pe_descriptions — links PE numbers to their PDF narrative pages
  - pe_tags         — auto-generated tags from structured fields, keywords, and optionally LLM
  - pe_lineage      — detected cross-PE references (project movement / lineage)

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
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

from utils import get_connection
from utils.patterns import PE_NUMBER, FISCAL_YEAR
from utils.pdf_sections import parse_narrative_sections

DEFAULT_DB_PATH = Path("dod_budget.sqlite")

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
]

# Pre-compile all taxonomy patterns
_COMPILED_TAXONOMY: list[tuple[str, list[re.Pattern]]] = [
    (tag, [re.compile(term, re.IGNORECASE) for term in terms])
    for tag, terms in _TAXONOMY
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
    "research":  "rdte",
    "procurement": "procurement",
    "operation": "om",
    "maintenance": "om",
    "milpers":   "milpers",
    "military personnel": "milpers",
    "construction": "milcon",
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_fy_from_path(source_file: str) -> str | None:
    """Extract fiscal year from a source file path string."""
    m = FISCAL_YEAR.search(source_file)
    if m:
        digits = re.search(r"20\d{2}", m.group(), re.IGNORECASE)
        return digits.group() if digits else None
    return None


def _context_window(text: str, pos: int, window: int = 200) -> str:
    """Return up to `window` characters centred around position `pos`."""
    start = max(0, pos - window // 2)
    end = min(len(text), pos + window // 2)
    snippet = text[start:end].replace("\n", " ")
    return f"...{snippet}..." if start > 0 or end < len(text) else snippet


def _drop_enrichment_tables(conn: sqlite3.Connection) -> None:
    for table in ("pe_lineage", "pe_tags", "pe_descriptions", "pe_index"):
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    print(f"  Dropped enrichment tables.")


# ── Phase 1: Build pe_index ───────────────────────────────────────────────────

def run_phase1(conn: sqlite3.Connection) -> int:
    """Aggregate all distinct PE numbers from budget_lines into pe_index."""
    print("\n  [Phase 1] Building pe_index from budget_lines...")

    # Use a single aggregation pass to get all fields including most-common org.
    # The correlated subquery was replaced with a pre-aggregated CTE to avoid
    # one COUNT(*) per PE row (which scaled O(N*M) with thousands of PE numbers).
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

    if not rows:
        print("  No PE numbers found in budget_lines — skipping.")
        return 0

    conn.executemany("""
        INSERT OR REPLACE INTO pe_index
            (pe_number, display_title, organization_name, budget_type,
             fiscal_years, exhibit_types, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
    """, [
        (r[0], r[1], r[2], r[3], r[4], r[5])
        for r in rows
    ])
    conn.commit()
    print(f"  Indexed {len(rows)} PE numbers.")
    return len(rows)


# ── Phase 2: Link PDFs to PEs ─────────────────────────────────────────────────

def run_phase2(conn: sqlite3.Connection) -> int:
    """Scan pdf_pages text for PE number mentions and populate pe_descriptions."""
    print("\n  [Phase 2] Linking PDF pages to PE numbers...")

    # Build set of known PE numbers for fast membership test
    known_pes = {
        r[0] for r in conn.execute("SELECT pe_number FROM pe_index").fetchall()
    }
    if not known_pes:
        print("  pe_index is empty — run Phase 1 first.")
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
        print("  All PDF files already processed — nothing to do.")
        return 0

    print(f"  Processing {len(pdf_files)} PDF file(s)...")
    total_desc = 0
    insert_buf: list[tuple] = []

    for i, source_file in enumerate(pdf_files, 1):
        fy = _extract_fy_from_path(source_file)

        pages = conn.execute("""
            SELECT page_number, page_text FROM pdf_pages
            WHERE source_file = ?
            ORDER BY page_number
        """, (source_file,)).fetchall()

        # Group consecutive pages that mention the same PE into runs
        # pe_number → (first_page, last_page, accumulated_text, sections)
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
                        "text": page_text,
                    }
                else:
                    pe_runs[pe]["page_end"] = page_num
                    pe_runs[pe]["text"] += "\n\n" + page_text

        # For each PE run in this file, extract narrative sections
        for pe, run in pe_runs.items():
            sections = parse_narrative_sections(run["text"])
            if sections:
                for sec in sections:
                    insert_buf.append((
                        pe, fy, source_file,
                        run["page_start"], run["page_end"],
                        sec["header"], sec["text"],
                    ))
            else:
                # No recognised section headers — store full text under blank header
                text = run["text"][:4000]  # cap at 4KB
                if text.strip():
                    insert_buf.append((
                        pe, fy, source_file,
                        run["page_start"], run["page_end"],
                        None, text,
                    ))

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
            print(f"  [{i}/{len(pdf_files)}] {total_desc} description rows so far...")

    if insert_buf:
        conn.executemany("""
            INSERT INTO pe_descriptions
                (pe_number, fiscal_year, source_file, page_start, page_end,
                 section_header, description_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, insert_buf)
        conn.commit()
        total_desc += len(insert_buf)

    print(f"  Done. {total_desc} description rows inserted.")
    return total_desc


# ── Phase 3: Generate Tags ────────────────────────────────────────────────────

def _tags_from_structured(pe_number: str, conn: sqlite3.Connection) -> list[tuple]:
    """Generate tags from structured budget_lines fields for a PE."""
    tags: list[tuple] = []

    row = conn.execute("""
        SELECT budget_activity_title, appropriation_title, organization_name
        FROM budget_lines
        WHERE pe_number = ?
        LIMIT 1
    """, (pe_number,)).fetchone()
    if not row:
        return tags

    ba_title, approp_title, org_name = row

    # Budget activity → RDT&E phase tag
    if ba_title:
        for pattern, tag in _BUDGET_ACTIVITY_TAGS:
            if pattern.search(ba_title):
                tags.append((pe_number, tag, "structured", 1.0))
                break

    # Appropriation → budget category tag
    if approp_title:
        low = approp_title.lower()
        for key, tag in _APPROP_TAGS.items():
            if key in low:
                tags.append((pe_number, tag, "structured", 1.0))
                break

    # Organization → service tag
    if org_name:
        low = org_name.lower()
        for key, tag in _ORG_TAGS.items():
            if key in low:
                tags.append((pe_number, tag, "structured", 1.0))
                break

    return tags


def _tags_from_keywords(pe_number: str, text: str) -> list[tuple]:
    """Match description text against predefined domain taxonomy."""
    tags: list[tuple] = []
    for tag, patterns in _COMPILED_TAXONOMY:
        for pat in patterns:
            if pat.search(text):
                tags.append((pe_number, tag, "keyword", 1.0))
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
    try:
        import anthropic
    except ImportError:
        print("  WARNING: anthropic package not installed. Skipping LLM tags.")
        print("           Run: pip install anthropic")
        return {}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  WARNING: ANTHROPIC_API_KEY not set. Skipping LLM tags.")
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
        print(f"  WARNING: LLM call failed: {e}")
        return {}


def run_phase3(conn: sqlite3.Connection, with_llm: bool = False) -> int:
    """Generate tags for all PE numbers from multiple sources."""
    print(f"\n  [Phase 3] Generating tags (LLM={'yes' if with_llm else 'no'})...")

    pe_numbers = [
        r[0] for r in conn.execute("SELECT pe_number FROM pe_index").fetchall()
    ]
    if not pe_numbers:
        print("  pe_index is empty — run Phase 1 first.")
        return 0

    # Skip PEs that already have tags (incremental)
    tagged = {
        r[0] for r in conn.execute(
            "SELECT DISTINCT pe_number FROM pe_tags"
        ).fetchall()
    }
    to_tag = [pe for pe in pe_numbers if pe not in tagged]
    if not to_tag:
        print("  All PEs already tagged — nothing to do.")
        return 0

    print(f"  Tagging {len(to_tag)} PE(s)...")

    # --- Pre-load structured fields for all untagged PEs in one query ---
    # Replaces N individual SELECT LIMIT 1 queries (one per PE) with a
    # single GROUP BY aggregation pass.
    structured_fields: dict[str, tuple] = {}
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

    # --- Pre-load all description text for untagged PEs in one query ---
    # Replaces N individual SELECT queries (one per PE) with a single pass.
    desc_texts: dict[str, list[str]] = {}
    for row in conn.execute(f"""
        SELECT pe_number, description_text
        FROM pe_descriptions
        WHERE pe_number IN ({placeholders})
          AND description_text IS NOT NULL
    """, to_tag).fetchall():
        desc_texts.setdefault(row[0], []).append(row[1])

    insert_buf: list[tuple] = []
    total_tags = 0

    for pe in to_tag:
        # 3a: structured field tags (from pre-loaded dict, no DB query)
        fields = structured_fields.get(pe)
        if fields:
            ba_title, approp_title, org_name = fields
            if ba_title:
                for pattern, tag in _BUDGET_ACTIVITY_TAGS:
                    if pattern.search(ba_title):
                        insert_buf.append((pe, tag, "structured", 1.0))
                        break
            if approp_title:
                low = approp_title.lower()
                for key, tag in _APPROP_TAGS.items():
                    if key in low:
                        insert_buf.append((pe, tag, "structured", 1.0))
                        break
            if org_name:
                low = org_name.lower()
                for key, tag in _ORG_TAGS.items():
                    if key in low:
                        insert_buf.append((pe, tag, "structured", 1.0))
                        break

        # 3b: keyword/taxonomy tags from pre-loaded description text
        combined_text = " ".join(desc_texts.get(pe, []))
        if combined_text:
            insert_buf.extend(_tags_from_keywords(pe, combined_text))

    # Flush structured + keyword tags
    if insert_buf:
        conn.executemany("""
            INSERT OR IGNORE INTO pe_tags (pe_number, tag, tag_source, confidence)
            VALUES (?, ?, ?, ?)
        """, insert_buf)
        conn.commit()
        total_tags += len(insert_buf)
        insert_buf = []

    # 3c: LLM tags (optional, in batches of 10)
    if with_llm:
        print(f"  Running LLM tagging in batches of 10...")
        batch_size = 10
        for i in range(0, len(to_tag), batch_size):
            batch_pes = to_tag[i:i + batch_size]
            # Collect text from pre-loaded desc_texts — no DB queries
            pe_texts: dict[str, str] = {}
            for pe in batch_pes:
                texts = desc_texts.get(pe, [])
                if texts:
                    pe_texts[pe] = texts[0]  # first description segment

            if pe_texts:
                llm_result = _tags_from_llm(pe_texts)
                for pe_num, tags in llm_result.items():
                    for tag in tags:
                        tag = tag.strip().lower().replace(" ", "-")
                        if tag:
                            insert_buf.append((pe_num, tag, "llm", 0.8))

            if insert_buf:
                conn.executemany("""
                    INSERT OR IGNORE INTO pe_tags
                        (pe_number, tag, tag_source, confidence)
                    VALUES (?, ?, ?, ?)
                """, insert_buf)
                conn.commit()
                total_tags += len(insert_buf)
                insert_buf = []
            print(f"  [{min(i + batch_size, len(to_tag))}/{len(to_tag)}] LLM batch done")
            time.sleep(0.5)  # gentle rate limiting

    print(f"  Done. {total_tags} tag rows inserted.")
    return total_tags


# ── Phase 4: Detect Cross-PE Lineage ─────────────────────────────────────────

def run_phase4(conn: sqlite3.Connection) -> int:
    """Scan description text for PE number cross-references and name matches."""
    print("\n  [Phase 4] Detecting cross-PE lineage...")

    known_pes = {
        r[0] for r in conn.execute("SELECT pe_number FROM pe_index").fetchall()
    }
    if not known_pes:
        print("  pe_index is empty — run Phase 1 first.")
        return 0

    # Skip already-processed (pe_number, source_file) pairs
    done_pairs = {
        (r[0], r[1]) for r in conn.execute(
            "SELECT DISTINCT source_pe, source_file FROM pe_lineage"
        ).fetchall()
    }

    # Build title index for name matching (phase 4b)
    # Only titles with >= 4 words are useful to avoid false positives
    title_index: list[tuple[str, re.Pattern]] = []
    for row in conn.execute(
        "SELECT pe_number, display_title FROM pe_index WHERE display_title IS NOT NULL"
    ).fetchall():
        pe, title = row
        words = title.split()
        if len(words) >= 4:
            phrase = r"\s+".join(re.escape(w) for w in words[:4])
            title_index.append((pe, re.compile(phrase, re.IGNORECASE)))

    insert_buf: list[tuple] = []
    total = 0
    CHUNK = 500  # rows per DB fetch to bound memory use

    # Stream pe_descriptions in chunks instead of fetchall() to avoid loading
    # potentially hundreds of MB of text into RAM at once.
    cur = conn.execute("""
        SELECT pe_number, fiscal_year, source_file, page_start, description_text
        FROM pe_descriptions
        WHERE description_text IS NOT NULL
    """)

    while True:
        chunk = cur.fetchmany(CHUNK)
        if not chunk:
            break

        for pe_num, fy, source_file, page_start, text in chunk:
            if (pe_num, source_file) in done_pairs:
                continue

            # 4a: Explicit PE number references
            for m in PE_NUMBER.finditer(text):
                ref_pe = m.group()
                if ref_pe == pe_num:
                    continue
                if ref_pe not in known_pes:
                    continue
                snippet = _context_window(text, m.start())
                insert_buf.append((
                    pe_num, ref_pe, fy, source_file, page_start,
                    snippet, "explicit_pe_ref", 0.95,
                ))

            # 4b: Program name matching
            for ref_pe, pattern in title_index:
                if ref_pe == pe_num:
                    continue
                m = pattern.search(text)
                if m:
                    snippet = _context_window(text, m.start())
                    insert_buf.append((
                        pe_num, ref_pe, fy, source_file, page_start,
                        snippet, "name_match", 0.6,
                    ))

        # Flush insert buffer every chunk to keep memory bounded
        if insert_buf:
            conn.executemany("""
                INSERT INTO pe_lineage
                    (source_pe, referenced_pe, fiscal_year, source_file,
                     page_number, context_snippet, link_type, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, insert_buf)
            conn.commit()
            total += len(insert_buf)
            insert_buf = []

    print(f"  Done. {total} lineage rows inserted.")
    return total


# ── Orchestrator ──────────────────────────────────────────────────────────────

def enrich(
    db_path: Path,
    phases: set[int],
    with_llm: bool = False,
    rebuild: bool = False,
) -> None:
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}")
        print("Run 'python build_budget_db.py' first.")
        sys.exit(1)

    conn = get_connection(db_path)

    # Performance PRAGMAs for bulk enrichment operations
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-262144")      # 256MB cache
    conn.execute("PRAGMA mmap_size=536870912")     # 512MB mmap
    conn.execute("PRAGMA wal_autocheckpoint=0")    # manual checkpoint at end

    if rebuild:
        print("  --rebuild: dropping enrichment tables...")
        _drop_enrichment_tables(conn)

    t0 = time.time()
    print(f"\nEnriching database: {db_path}")
    print(f"Phases: {sorted(phases)}")

    if 1 in phases:
        run_phase1(conn)
    if 2 in phases:
        run_phase2(conn)
    if 3 in phases:
        run_phase3(conn, with_llm=with_llm)
    if 4 in phases:
        run_phase4(conn)

    elapsed = time.time() - t0
    print(f"\nEnrichment complete in {elapsed:.1f}s")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # Summary counts
    for table in ("pe_index", "pe_descriptions", "pe_tags", "pe_lineage"):
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table}: {n:,} rows")
        except Exception:
            print(f"  {table}: (table not found)")

    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich the DoD budget database with PE index, tags, and lineage."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                        help="Path to SQLite database (default: dod_budget.sqlite)")
    parser.add_argument("--with-llm", action="store_true",
                        help="Enable LLM-based tagging (requires ANTHROPIC_API_KEY)")
    parser.add_argument("--phases", default="1,2,3,4",
                        help="Comma-separated phases to run (default: 1,2,3,4)")
    parser.add_argument("--rebuild", action="store_true",
                        help="Drop and rebuild all enrichment tables")
    args = parser.parse_args()

    try:
        phases = {int(p.strip()) for p in args.phases.split(",")}
    except ValueError:
        print("ERROR: --phases must be comma-separated integers, e.g. '1,2,3'")
        sys.exit(1)

    enrich(args.db, phases, with_llm=args.with_llm, rebuild=args.rebuild)


if __name__ == "__main__":
    main()
