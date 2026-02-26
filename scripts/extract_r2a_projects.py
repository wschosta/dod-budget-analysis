"""Extract R-2A sub-project data from pe_descriptions into a structured table.

Parses the "Exhibit R-2A, RDT&E Project Justification" text blocks that appear
in pe_descriptions to extract project numbers, titles, FY amounts (from the
Subtotals line), and narrative text.

Usage:
    python scripts/extract_r2a_projects.py [--db PATH] [--dry-run]
"""

import argparse
import json
import logging
import re
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Regex patterns for R-2A text ─────────────────────────────────────────────

# Modern format (FY2012+):
#   PE 0101113F / B-52 Squadrons  675048 / 1760 INTERNAL WEAPONS BAY UPGRADE
# The PE line followed by project number/title.
_PROJECT_MODERN = re.compile(
    r"PE\s+(\w+)\s*/\s*[^\n]+"          # PE number / PE title
    r"\s+(\d{4,7})\s*/\s*"              # project number (4-7 digits)
    r"([^\n]+)",                          # project title (rest of line)
    re.IGNORECASE,
)

# Older format (pre-2012):
#   PE 0305220F: GLOBAL HAWK 675144: Global Hawk
_PROJECT_OLDER = re.compile(
    r"PE\s+(\w+)\s*:\s*\S[^\n]*?"       # PE number: PE TITLE
    r"\s+(\d{4,7})\s*:\s*"              # project number:
    r"([^\n]+)",                          # project title
    re.IGNORECASE,
)

# Alternative older: just "PE XXXXX  PROJNUM / Title" without slashes for PE
_PROJECT_ALT = re.compile(
    r"PE\s+(\w+)\s+[A-Z][^\n]*?"        # PE number  PE TITLE
    r"\s+(\d{4,7})\s*/\s*"              # project number /
    r"([^\n]+)",                          # project title
    re.IGNORECASE,
)

# FY column header line:
#   B. Accomplishments/Planned Programs ($ in Millions)  FY 2022  FY 2023  FY 2024
# Second line may have:  FY 2020  FY 2021  Base  OCO  Total
_FY_HEADER = re.compile(
    r"Accomplishments/Planned Programs\s*\(\$\s*in\s*Millions\)\s*(.*?)(?:\n|$)",
    re.IGNORECASE,
)

# Extract individual FY years from the header area (two lines)
_FY_YEAR = re.compile(r"FY\s*(\d{4})")

# Subtotals line:
#   Accomplishments/Planned Programs Subtotals  28.870  15.164  0.000  -  0.000
_SUBTOTALS = re.compile(
    r"(?:Accomplishments/Planned Programs\s+)?Subtotals\s+([\d.\-\s]+?)(?:\n|$)",
    re.IGNORECASE,
)

# Submission FY from "Exhibit R-2A, RDT&E Project Justification: PB YYYY"
_SUBMISSION_FY = re.compile(
    r"Exhibit R-2A.*?PB\s+(\d{4})",
    re.IGNORECASE,
)


def _parse_amounts(amount_str: str) -> list[float | None]:
    """Parse space-separated amounts like '28.870 15.164 0.000 - 0.000'."""
    parts = amount_str.strip().split()
    result = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if p == "-" or p == "—" or p == "–":
            result.append(0.0)
        else:
            try:
                result.append(float(p))
            except ValueError:
                # Skip non-numeric tokens
                continue
    return result


def _extract_fy_columns(text: str) -> list[str]:
    """Extract the FY column labels from the Accomplishments header area.

    The header spans two lines like:
        B. Accomplishments/Planned Programs ($ in Millions)  FY 2024  FY 2024  FY 2024
                                                             FY 2022  FY 2023  Base OCO Total

    We want the second line's FY years (the actual data columns), not the
    repeated budget-year on the first line. If the second line has distinct
    FY years, use those; otherwise fall back to the first line.
    """
    match = _FY_HEADER.search(text)
    if not match:
        return []

    # Get the header line and the next line
    start = match.start()
    lines = text[start:start + 300].split("\n")[:3]
    header_text = "\n".join(lines)

    fys = _FY_YEAR.findall(header_text)
    if not fys:
        return []

    # The pattern is usually: first line has the budget year repeated 3x,
    # second line has prior_fy, current_fy, then "Base OCO Total".
    # We want the unique FYs in order of appearance.
    # Deduplicate while preserving order.
    seen = set()
    unique = []
    for fy in fys:
        if fy not in seen:
            seen.add(fy)
            unique.append(fy)

    return unique


def _extract_narrative(text: str) -> str:
    """Extract narrative text between 'B. Accomplishments' header and Subtotals."""
    # Find the section B header
    b_match = re.search(
        r"B\.\s*Accomplishments/Planned Programs\s*\(\$\s*in\s*Millions\)[^\n]*\n"
        r"[^\n]*\n",  # Skip the FY column header lines
        text,
        re.IGNORECASE,
    )
    sub_match = _SUBTOTALS.search(text)

    if b_match and sub_match and sub_match.start() > b_match.end():
        narrative = text[b_match.end():sub_match.start()].strip()
        # Clean up page breaks and exhibit headers from narrative
        narrative = re.sub(
            r"(?:UNCLASSIFIED|CLASSIFIED).*?(?:R-1 Line|Page \d+ of \d+)[^\n]*\n?",
            "",
            narrative,
            flags=re.DOTALL,
        )
        return narrative.strip()
    return ""


def extract_project(text: str, pe_number_hint: str) -> dict | None:
    """Extract a single project record from an R-2A description text block.

    Returns a dict with keys: pe_number, project_number, project_title,
    submission_fy, fy_columns, amounts, narrative_text.
    Returns None if no project could be parsed.
    """
    # Try to find the project header
    proj_match = _PROJECT_MODERN.search(text)
    if not proj_match:
        proj_match = _PROJECT_OLDER.search(text)
    if not proj_match:
        proj_match = _PROJECT_ALT.search(text)
    if not proj_match:
        return None

    pe_num = proj_match.group(1).strip()
    project_num = proj_match.group(2).strip()
    project_title = proj_match.group(3).strip()

    # Clean up project title: remove trailing exhibit info
    project_title = re.sub(r"\s*(?:UNCLASSIFIED|CLASSIFIED).*$", "", project_title)
    project_title = project_title.strip().rstrip(".")

    # If extracted PE doesn't match the hint, skip (wrong match)
    if pe_number_hint and pe_num.upper() != pe_number_hint.upper():
        return None

    # Extract submission FY
    fy_match = _SUBMISSION_FY.search(text)
    submission_fy = fy_match.group(1) if fy_match else None

    # Extract FY columns
    fy_columns = _extract_fy_columns(text)

    # Extract subtotal amounts
    sub_match = _SUBTOTALS.search(text)
    amounts = _parse_amounts(sub_match.group(1)) if sub_match else []

    # Extract narrative
    narrative = _extract_narrative(text)

    return {
        "pe_number": pe_num,
        "project_number": project_num,
        "project_title": project_title,
        "submission_fy": submission_fy,
        "fy_columns": fy_columns,
        "amounts": amounts,
        "narrative_text": narrative,
    }


def create_table(conn: sqlite3.Connection) -> None:
    """Create pe_projects table."""
    conn.executescript("""
        DROP TABLE IF EXISTS pe_projects;
        CREATE TABLE pe_projects (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            line_item_id      INTEGER REFERENCES line_items(id),
            pe_number         TEXT NOT NULL,
            project_number    TEXT NOT NULL,
            project_title     TEXT,
            fiscal_year       TEXT,
            fy_columns        TEXT,
            amounts           TEXT,
            narrative_text    TEXT,
            source_desc_id    INTEGER,
            UNIQUE(pe_number, project_number, fiscal_year)
        );
        CREATE INDEX IF NOT EXISTS idx_pe_projects_pe ON pe_projects(pe_number);
        CREATE INDEX IF NOT EXISTS idx_pe_projects_li ON pe_projects(line_item_id);
    """)


def _extract_project_number(text: str) -> str | None:
    """Extract just the project number from an R-2A block header."""
    for pat in (_PROJECT_MODERN, _PROJECT_OLDER, _PROJECT_ALT):
        m = pat.search(text)
        if m:
            return m.group(2).strip()
    return None


def _split_projects_from_combined(text: str, pe_number: str) -> list[dict]:
    """Split combined text into per-project blocks and extract each one.

    R-2A text for a PE+FY contains multiple projects. Each project may span
    multiple pages (each page starts with an 'Exhibit R-2A' header). We split
    on those boundaries, group consecutive blocks by project number, concatenate
    each group, then parse the combined text.
    """
    # Split on 'Exhibit R-2A' markers (each page starts a new block)
    parts = re.split(r"(?=Exhibit R-2A)", text, flags=re.IGNORECASE)
    r2a_parts = [p for p in parts if "Exhibit R-2A" in p or "exhibit r-2a" in p.lower()]

    if not r2a_parts:
        return []

    # Group consecutive blocks by project number
    grouped: list[list[str]] = []
    prev_proj = None
    for part in r2a_parts:
        proj_num = _extract_project_number(part)
        if proj_num and proj_num == prev_proj:
            # Same project continues — append to current group
            grouped[-1].append(part)
        else:
            # New project — start a new group
            grouped.append([part])
            prev_proj = proj_num

    # Parse each grouped project
    results = []
    for group in grouped:
        combined_block = "\n\n".join(group)
        result = extract_project(combined_block, pe_number)
        if result:
            results.append(result)
    return results


def extract_all(db_path: Path, dry_run: bool = False) -> None:
    """Extract R-2A project data from pe_descriptions.

    Groups all description rows by (pe_number, fiscal_year), concatenates them
    in id order (to handle page breaks), then parses projects from the combined
    text.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Build line_items lookup for linking
    li_lookup: dict[str, int] = {}
    try:
        for row in conn.execute("SELECT id, pe_number FROM line_items"):
            li_lookup[row["pe_number"]] = row["id"]
    except sqlite3.OperationalError:
        logger.warning("line_items table not found — projects won't be linked")

    # Fetch ALL description rows for PEs that have R-2A data.
    # We need adjacent rows (which may not themselves contain 'Exhibit R-2A')
    # to reconstruct text that spans page breaks.
    logger.info("Querying pe_descriptions — finding PEs with R-2A data...")

    # First find which (pe_number, fiscal_year) combos have R-2A text
    pe_fy_pairs = conn.execute("""
        SELECT DISTINCT pe_number, fiscal_year
        FROM pe_descriptions
        WHERE description_text LIKE '%Exhibit R-2A%'
    """).fetchall()
    logger.info(f"Found {len(pe_fy_pairs):,} (PE, FY) groups with R-2A data")

    # Now fetch all description rows for those groups, ordered by id
    logger.info("Fetching full description text for those groups...")
    groups: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for pe, fy in pe_fy_pairs:
        rows = conn.execute("""
            SELECT id, description_text
            FROM pe_descriptions
            WHERE pe_number = ? AND fiscal_year = ?
            ORDER BY id
        """, (pe, fy)).fetchall()
        groups[(pe, fy)] = [(r["id"], r["description_text"] or "") for r in rows]

    logger.info(f"Total groups to process: {len(groups):,}")

    if not dry_run:
        create_table(conn)

    extracted = 0
    dupes = 0
    groups_with_projects = 0
    pe_set: set[str] = set()
    proj_set: set[str] = set()
    batch: list[tuple] = []

    for idx, ((pe_number, fy), desc_rows) in enumerate(groups.items()):
        # Concatenate all description texts for this PE+FY
        combined = "\n\n".join(text for _, text in desc_rows)
        first_desc_id = desc_rows[0][0]

        # Split and parse projects from the combined text
        results = _split_projects_from_combined(combined, pe_number)

        if not results:
            continue

        groups_with_projects += 1
        li_id = li_lookup.get(pe_number)

        for result in results:
            proj_key = f"{result['pe_number']}:{result['project_number']}"
            pe_set.add(result["pe_number"])
            proj_set.add(proj_key)

            batch.append((
                li_id,
                result["pe_number"],
                result["project_number"],
                result["project_title"],
                result["submission_fy"] or fy,
                json.dumps(result["fy_columns"]) if result["fy_columns"] else None,
                json.dumps(result["amounts"]) if result["amounts"] else None,
                result["narrative_text"] or None,
                first_desc_id,
            ))
            extracted += 1

        if (idx + 1) % 2000 == 0:
            logger.info(f"  Processed {idx + 1:,} / {len(groups):,} groups...")

    if not dry_run and batch:
        logger.info(f"Inserting {len(batch):,} project records...")
        for rec in batch:
            try:
                conn.execute("""
                    INSERT INTO pe_projects
                        (line_item_id, pe_number, project_number, project_title,
                         fiscal_year, fy_columns, amounts, narrative_text, source_desc_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, rec)
            except sqlite3.IntegrityError:
                dupes += 1
        conn.commit()

    # Final stats
    if not dry_run:
        actual = conn.execute("SELECT COUNT(*) FROM pe_projects").fetchone()[0]
        with_amounts = conn.execute(
            "SELECT COUNT(*) FROM pe_projects WHERE amounts IS NOT NULL AND amounts != '[]'"
        ).fetchone()[0]
    else:
        actual = extracted - dupes
        with_amounts = 0

    logger.info("=" * 60)
    logger.info(f"(PE, FY) groups:        {len(groups):,}")
    logger.info(f"Groups with projects:   {groups_with_projects:,}")
    logger.info(f"Projects extracted:     {extracted:,}")
    logger.info(f"Duplicates skipped:     {dupes:,}")
    logger.info(f"Unique PEs with data:   {len(pe_set):,}")
    logger.info(f"Unique project keys:    {len(proj_set):,}")
    if not dry_run:
        logger.info(f"pe_projects rows:       {actual:,}")
        logger.info(f"  with amounts:         {with_amounts:,} ({100*with_amounts/max(actual,1):.1f}%)")

    # Sample output
    if not dry_run:
        logger.info("\n--- Sample: PE 0101113F projects ---")
        sample = conn.execute("""
            SELECT project_number, project_title, fiscal_year, amounts
            FROM pe_projects
            WHERE pe_number = '0101113F'
            ORDER BY project_number, fiscal_year DESC
        """).fetchall()
        for s in sample[:20]:
            amt = s[3] or "[]"
            logger.info(f"  {s[0]}: {s[1]} (FY{s[2]}) amounts={amt}")

    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract R-2A sub-project data")
    parser.add_argument(
        "--db", type=Path,
        default=Path(__file__).resolve().parents[1] / "dod_budget_work.sqlite",
        help="Path to the SQLite database",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse without writing")
    args = parser.parse_args()

    if not args.db.exists():
        logger.error(f"Database not found: {args.db}")
        sys.exit(1)

    extract_all(args.db, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
