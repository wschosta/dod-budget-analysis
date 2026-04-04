"""Clean page-break artifacts from pe_projects narrative text
and extract PE-level mission descriptions per FY.

Page-break artifacts look like:
    PE 0101113F: B-52 Squadrons
    UNCLASSIFIED
    Exhibit R-2A, RDT&E Project Justification: PB 2024 Air Force Date: March 2023
    Appropriation/Budget Activity R-1 Program Element (Number/Name) Project (Number/Name)
    3600 / 7 PE 0101113F / B-52 Squadrons 671810 / B-52 AEHF Integration
    B. Accomplishments/Planned Programs ($ in Millions) FY 2022 FY 2023 FY 2024

These are headers that repeat when the R-2A exhibit spans multiple pages.

Also extracts PE-level descriptions from pe_descriptions into a
pe_mission_descriptions table for use in the consolidated detail view.
"""

import logging
import re
import sqlite3
import sys
from pathlib import Path

from utils.strings import clean_narrative  # noqa: F401  (re-exported for callers)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "dod_budget_work.sqlite"


# ── PE-level Mission Description extraction ───────────────────────────────

_MISSION_DESC_START = re.compile(
    r"A\.\s*Mission\s+Description\s+and\s+Budget\s+Item\s+Justification\s*\n?",
    re.IGNORECASE,
)
_SECTION_B_START = re.compile(
    r"\n\s*B\.\s*(?:Accomplishments|Program\s+Change)",
    re.IGNORECASE,
)


def extract_mission_description(full_text: str) -> str | None:
    """Extract the first 'A. Mission Description' section from concatenated PE text."""
    m = _MISSION_DESC_START.search(full_text)
    if not m:
        return None

    start = m.end()
    # Find end: next "B. Accomplishments" or "B. Program Change" section
    end_m = _SECTION_B_START.search(full_text, start)
    if end_m:
        desc = full_text[start : end_m.start()]
    else:
        # Take up to 2000 chars
        desc = full_text[start : start + 2000]

    desc = desc.strip()
    if len(desc) < 20:
        return None

    # Clean up the description
    desc = clean_narrative(desc)
    return desc if desc else None


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH
    log.info("Database: %s", db_path)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # ── Step 1: Clean pe_projects narrative text ──
    log.info("\n=== Cleaning pe_projects narrative text ===")
    rows = conn.execute(
        "SELECT id, narrative_text FROM pe_projects WHERE narrative_text IS NOT NULL"
    ).fetchall()

    cleaned = 0
    for row in rows:
        original = row["narrative_text"]
        result = clean_narrative(original)
        if result != original:
            conn.execute(
                "UPDATE pe_projects SET narrative_text = ? WHERE id = ?",
                (result, row["id"]),
            )
            cleaned += 1

    conn.commit()
    log.info("Cleaned %d / %d narrative texts", cleaned, len(rows))

    # ── Step 2: Create pe_mission_descriptions table ──
    log.info("\n=== Extracting PE-level mission descriptions ===")
    conn.execute("DROP TABLE IF EXISTS pe_mission_descriptions")
    conn.execute("""
        CREATE TABLE pe_mission_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pe_number TEXT NOT NULL,
            fiscal_year INTEGER NOT NULL,
            description_text TEXT NOT NULL,
            UNIQUE(pe_number, fiscal_year)
        )
    """)

    # Fetch ALL pe_descriptions in one query, sorted for grouping
    log.info("Fetching pe_descriptions (single query)...")
    all_descs = conn.execute("""
        SELECT pe_number, fiscal_year, description_text
        FROM pe_descriptions
        WHERE description_text IS NOT NULL
        ORDER BY pe_number, fiscal_year, page_start, id
    """).fetchall()
    log.info("Loaded %d rows, grouping by PE/FY...", len(all_descs))

    # Group pages by (pe_number, fiscal_year) in memory
    from itertools import groupby

    extracted = 0
    pe_fy_count = 0
    for (pe, fy), group in groupby(all_descs, key=lambda r: (r["pe_number"], r["fiscal_year"])):
        pe_fy_count += 1
        full_text = "\n\n".join(r["description_text"] for r in group)

        desc = extract_mission_description(full_text)
        if desc:
            try:
                conn.execute(
                    """INSERT OR REPLACE INTO pe_mission_descriptions
                       (pe_number, fiscal_year, description_text)
                       VALUES (?, ?, ?)""",
                    (pe, int(fy), desc),
                )
                extracted += 1
            except Exception as e:
                log.warning("Failed to insert %s FY%s: %s", pe, fy, e)

        if pe_fy_count % 5000 == 0:
            log.info("  Processed %d PE/FY combos...", pe_fy_count)

    conn.commit()

    total_pes = conn.execute(
        "SELECT COUNT(DISTINCT pe_number) FROM pe_mission_descriptions"
    ).fetchone()[0]
    log.info(
        "Extracted %d mission descriptions across %d PEs", extracted, total_pes
    )

    # Show sample
    sample = conn.execute(
        """SELECT pe_number, fiscal_year, substr(description_text, 1, 120) as preview
           FROM pe_mission_descriptions
           ORDER BY pe_number, fiscal_year DESC
           LIMIT 5"""
    ).fetchall()
    log.info("\nSample:")
    for s in sample:
        log.info("  %s FY%s: %s...", s[0], s[1], s[2])

    conn.close()
    log.info("\nDone.")


if __name__ == "__main__":
    main()
