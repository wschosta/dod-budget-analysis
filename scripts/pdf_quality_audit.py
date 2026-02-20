#!/usr/bin/env python3
"""
PDF Extraction Quality Audit — Step 1.B5-a

Queries the pdf_pages table in a populated dod_budget.sqlite database and
identifies pages with poor extraction quality.  Quality indicators:

  - High ratio of non-ASCII characters (garbled text from bad encoding)
  - Whitespace-only or near-empty lines (layout artifacts)
  - Very short page text (possible extraction failure)
  - Pages with tables flagged but no table_data content

Outputs a Markdown report to docs/pdf_quality_audit.md.

Usage:
    python scripts/pdf_quality_audit.py
    python scripts/pdf_quality_audit.py --db path/to/dod_budget.sqlite
    python scripts/pdf_quality_audit.py --output docs/pdf_quality_audit.md
"""

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_DB_PATH = Path("dod_budget.sqlite")
DEFAULT_OUTPUT = Path("docs/pdf_quality_audit.md")

# Thresholds for quality flags
NON_ASCII_RATIO_THRESHOLD = 0.15  # >15% non-ASCII chars = suspect
WHITESPACE_LINE_RATIO_THRESHOLD = 0.50  # >50% whitespace-only lines
MIN_PAGE_TEXT_LENGTH = 20  # fewer chars = likely extraction failure
EMPTY_TABLE_FLAG = True  # has_tables=1 but no table_data


def _non_ascii_ratio(text: str) -> float:
    """Return the fraction of non-ASCII characters in text."""
    if not text:
        return 0.0
    non_ascii = sum(1 for c in text if ord(c) > 127)
    return non_ascii / len(text)


def _whitespace_line_ratio(text: str) -> float:
    """Return the fraction of lines that are whitespace-only."""
    if not text:
        return 1.0
    lines = text.split("\n")
    if not lines:
        return 1.0
    ws_lines = sum(1 for ln in lines if not ln.strip())
    return ws_lines / len(lines)


def _classify_source_file(source_file: str) -> str:
    """Extract a service/category label from the source file path."""
    lower = source_file.lower()
    for label, keywords in [
        ("Army", ["army", "us_army"]),
        ("Navy", ["navy"]),
        ("Air Force", ["air_force", "airforce"]),
        ("Space Force", ["space_force", "spaceforce"]),
        ("Marine Corps", ["marine_corps", "marines"]),
        ("Defense-Wide", ["defense_wide", "defense-wide"]),
        ("Comptroller", ["comptroller"]),
    ]:
        if any(kw in lower for kw in keywords):
            return label
    return "Other"


def audit_pdf_quality(db_path: Path) -> dict:
    """Run quality checks against the pdf_pages table.

    Returns a dict with keys:
      - total_pages: int
      - flagged_pages: list of dicts with quality issue details
      - summary_by_issue: dict of issue_type -> count
      - summary_by_source: dict of source_category -> count of flagged pages
    """
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        print("Run 'python build_budget_db.py' first.", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    total_pages = conn.execute("SELECT COUNT(*) FROM pdf_pages").fetchone()[0]
    if total_pages == 0:
        conn.close()
        return {
            "total_pages": 0,
            "flagged_pages": [],
            "summary_by_issue": {},
            "summary_by_source": {},
        }

    flagged = []
    issue_counts = defaultdict(int)
    source_counts = defaultdict(int)

    # Fetch all pages — for very large DBs this could be batched, but
    # typical DoD budget DBs have <50k PDF pages which fits in memory.
    rows = conn.execute("""
        SELECT id, source_file, page_number, page_text, has_tables, table_data
        FROM pdf_pages
    """).fetchall()

    for row in rows:
        page_text = row["page_text"] or ""
        issues = []

        # Check 1: High non-ASCII ratio
        na_ratio = _non_ascii_ratio(page_text)
        if na_ratio > NON_ASCII_RATIO_THRESHOLD:
            issues.append(f"non_ascii_ratio={na_ratio:.2f}")
            issue_counts["high_non_ascii"] += 1

        # Check 2: Whitespace-heavy content
        ws_ratio = _whitespace_line_ratio(page_text)
        if ws_ratio > WHITESPACE_LINE_RATIO_THRESHOLD:
            issues.append(f"whitespace_line_ratio={ws_ratio:.2f}")
            issue_counts["whitespace_heavy"] += 1

        # Check 3: Very short page text
        if len(page_text.strip()) < MIN_PAGE_TEXT_LENGTH:
            issues.append(f"text_length={len(page_text.strip())}")
            issue_counts["very_short_text"] += 1

        # Check 4: Tables flagged but no table data
        has_tables = row["has_tables"]
        table_data = row["table_data"] or ""
        if has_tables and not table_data.strip():
            issues.append("has_tables=1 but empty table_data")
            issue_counts["empty_table_data"] += 1

        if issues:
            source_cat = _classify_source_file(row["source_file"])
            source_counts[source_cat] += 1
            flagged.append({
                "id": row["id"],
                "source_file": row["source_file"],
                "page_number": row["page_number"],
                "text_length": len(page_text),
                "issues": issues,
                "source_category": source_cat,
            })

    conn.close()

    return {
        "total_pages": total_pages,
        "flagged_pages": flagged,
        "summary_by_issue": dict(issue_counts),
        "summary_by_source": dict(source_counts),
    }


def generate_report(audit_result: dict) -> str:
    """Generate a Markdown quality audit report."""
    total = audit_result["total_pages"]
    flagged = audit_result["flagged_pages"]
    by_issue = audit_result["summary_by_issue"]
    by_source = audit_result["summary_by_source"]

    pct = (len(flagged) / total * 100) if total else 0

    lines = [
        "# PDF Extraction Quality Audit Report",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"- **Total PDF pages scanned:** {total:,}",
        f"- **Pages with quality issues:** {len(flagged):,} ({pct:.1f}%)",
        "",
    ]

    if not flagged:
        lines.append("No quality issues detected.")
        return "\n".join(lines) + "\n"

    # Issue type breakdown
    lines.extend([
        "## Issues by Type",
        "",
        "| Issue | Count | Description |",
        "|-------|------:|-------------|",
    ])
    issue_descriptions = {
        "high_non_ascii": "Pages with >15% non-ASCII characters (garbled text)",
        "whitespace_heavy": "Pages with >50% whitespace-only lines",
        "very_short_text": "Pages with fewer than 20 characters extracted",
        "empty_table_data": "Pages flagged as having tables but no data extracted",
    }
    for issue, count in sorted(by_issue.items(), key=lambda x: -x[1]):
        desc = issue_descriptions.get(issue, issue)
        lines.append(f"| `{issue}` | {count:,} | {desc} |")

    lines.append("")

    # Source category breakdown
    lines.extend([
        "## Issues by Source Category",
        "",
        "| Category | Flagged Pages |",
        "|----------|-------------:|",
    ])
    for cat, count in sorted(by_source.items(), key=lambda x: -x[1]):
        lines.append(f"| {cat} | {count:,} |")

    lines.append("")

    # Worst offenders (top 30)
    lines.extend([
        "## Flagged Pages (top 50)",
        "",
        "| Source File | Page | Text Len | Issues |",
        "|------------|-----:|---------:|--------|",
    ])
    for entry in flagged[:50]:
        src = entry["source_file"]
        # Truncate long paths
        if len(src) > 60:
            src = "..." + src[-57:]
        pg = entry["page_number"]
        tl = entry["text_length"]
        iss = "; ".join(entry["issues"])
        lines.append(f"| `{src}` | {pg} | {tl:,} | {iss} |")

    if len(flagged) > 50:
        lines.append(f"| _(+{len(flagged) - 50} more)_ | | | |")

    lines.extend([
        "",
        "---",
        "",
        "## Recommendations",
        "",
        "1. **High non-ASCII ratio:** Check if source PDFs use non-standard "
        "encodings or contain scanned images. Consider OCR preprocessing.",
        "2. **Whitespace-heavy:** These pages may contain mostly graphical "
        "content (charts, diagrams). Consider flagging as non-tabular.",
        "3. **Very short text:** Likely cover pages, separator pages, or "
        "extraction failures. Verify source PDF is not corrupted.",
        "4. **Empty table data:** Table detection fired but extraction failed. "
        "Review pdfplumber strategy settings for these layouts.",
    ])

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Audit PDF extraction quality in the budget database"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output Markdown report path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Also write a JSON report alongside the Markdown",
    )
    args = parser.parse_args()

    print(f"Auditing PDF quality in {args.db}...")
    result = audit_pdf_quality(args.db)

    report = generate_report(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report)
    print(f"Report written to {args.output}")

    if args.output_json:
        json_path = args.output.with_suffix(".json")
        json_path.write_text(json.dumps(result, indent=2, default=str))
        print(f"JSON report written to {json_path}")

    # Console summary
    total = result["total_pages"]
    flagged = len(result["flagged_pages"])
    print(f"\nSummary: {flagged} of {total} pages flagged ({flagged/total*100:.1f}%)"
          if total else "\nNo PDF pages found in database.")
    for issue, count in sorted(result["summary_by_issue"].items(),
                               key=lambda x: -x[1]):
        print(f"  {issue}: {count}")


if __name__ == "__main__":
    main()
