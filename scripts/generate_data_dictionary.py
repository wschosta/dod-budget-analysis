#!/usr/bin/env python3
"""
LION-005: Auto-generate data dictionary from the SQLite schema.

Connects to the DoD budget database (or falls back to schema_design.py DDL)
and generates a markdown document describing every table and column.

Usage:
    python scripts/generate_data_dictionary.py > docs/data_dictionary.md
    python scripts/generate_data_dictionary.py --check   # CI mode: exit 1 if stale
    python scripts/generate_data_dictionary.py --db path/to/dod_budget.sqlite
"""

import argparse
import os
import sqlite3
import sys
import textwrap
from pathlib import Path

# ── Field descriptions ────────────────────────────────────────────────────────
# Human-written descriptions for every known column across all tables.

FIELD_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "budget_lines": {
        "id": "Auto-increment primary key.",
        "source_file": "Filename of the XLSX or PDF the row was extracted from.",
        "sheet_name": "Excel worksheet name within the source file.",
        "exhibit_type": "Budget exhibit type code (e.g. p1, r1, r2, p5, o1).",
        "fiscal_year": "Fiscal year label, e.g. 'FY 2026'. DoD fiscal year runs Oct 1 - Sep 30.",
        "account": "Appropriation account code.",
        "account_title": "Human-readable account/appropriation title.",
        "organization": "Short organization code.",
        "organization_name": "Full name of the military service or defense agency.",
        "budget_activity": "Budget activity number within the appropriation.",
        "budget_activity_title": "Human-readable budget activity name.",
        "sub_activity": "Sub-activity number.",
        "sub_activity_title": "Sub-activity name.",
        "line_item": "Line item identifier within the budget activity.",
        "line_item_title": "Human-readable line item or program name.",
        "pe_number": "Program Element number (e.g. 0604131A). Unique R&D program ID.",
        "appropriation_code": "Color-of-money code: PROC, RDTE, OMA, MILCON, MILPERS, RFUND, OTHER.",
        "appropriation_title": "Full appropriation title.",
        "currency_year": "'then-year' or 'constant' dollar basis.",
        "amount_unit": "Monetary unit. Default: 'thousands' ($K).",
        "amount_type": "Type of budget authority: budget_authority, authorization, outlay.",
        "budget_type": "Budget document type.",
        "amount_fy2024_actual": "FY2024 actual expenditure in $K.",
        "amount_fy2025_enacted": "FY2025 enacted amount in $K.",
        "amount_fy2025_supplemental": "FY2025 supplemental amount in $K.",
        "amount_fy2025_total": "FY2025 total (enacted + supplemental) in $K.",
        "amount_fy2026_request": "FY2026 President's Budget request in $K.",
        "amount_fy2026_reconciliation": "FY2026 reconciliation adjustments in $K.",
        "amount_fy2026_total": "FY2026 total (request + reconciliation) in $K.",
        "quantity_fy2024": "Procurement quantity for FY2024.",
        "quantity_fy2025": "Procurement quantity for FY2025.",
        "quantity_fy2026_request": "Procurement quantity requested for FY2026.",
        "quantity_fy2026_total": "Total procurement quantity for FY2026.",
        "classification": "Security classification (e.g. UNCLASSIFIED).",
        "extra_fields": "JSON blob for service-specific columns not in the canonical schema.",
    },
    "services_agencies": {
        "id": "Auto-increment primary key.",
        "code": "Short code (e.g. 'Army', 'DISA'). Used as the filter value in the UI.",
        "full_name": "Official full name of the organization.",
        "category": "Organization category: military_dept, defense_agency, combatant_cmd, osd_component.",
    },
    "exhibit_types": {
        "id": "Auto-increment primary key.",
        "code": "Lowercase exhibit code (e.g. 'p1', 'r2').",
        "display_name": "Human-readable name (e.g. 'Procurement (P-1)').",
        "exhibit_class": "'summary' or 'detail'.",
        "description": "Brief description of what this exhibit covers.",
    },
    "appropriation_titles": {
        "id": "Auto-increment primary key.",
        "code": "Appropriation code (e.g. PROC, RDTE, OMA).",
        "title": "Full appropriation title.",
        "color_of_money": "Category: investment, operation, or personnel.",
    },
    "pdf_pages": {
        "id": "Auto-increment primary key.",
        "source_file": "Filename of the PDF the page was extracted from.",
        "source_category": "Category/folder the PDF belongs to.",
        "page_number": "1-based page number within the PDF.",
        "page_text": "Extracted text content of the page.",
        "has_tables": "1 if tables were detected on this page, 0 otherwise.",
        "table_data": "JSON-encoded table data extracted from the page.",
    },
    "ingested_files": {
        "id": "Auto-increment primary key.",
        "file_path": "Path to the ingested file.",
        "file_type": "File type: xlsx, pdf, csv.",
        "row_count": "Number of rows extracted from this file.",
        "ingested_at": "ISO 8601 timestamp of when the file was ingested.",
        "status": "Ingestion status: success, error, skipped.",
    },
}

# ── Caveats section ──────────────────────────────────────────────────────────

CAVEATS = """\
## Data Quality Caveats

- **Monetary units**: All dollar amounts in `budget_lines` are in **thousands of dollars ($K)** unless the `amount_unit` column says otherwise. Divide by 1,000 to get millions.
- **Fiscal year convention**: The DoD fiscal year runs October 1 through September 30. FY2026 = Oct 1, 2025 - Sep 30, 2026.
- **PDF extraction accuracy**: Text extracted from PDF budget documents may contain OCR errors or formatting artifacts. Excel-sourced data is generally more reliable.
- **Amount reconciliation**: Totals may not reconcile exactly across summary (P-1, R-1) and detail (P-5, R-2) exhibits due to rounding, classified programs, or data extraction gaps.
- **Classified programs**: Some program elements contain placeholder or redacted values. These rows exist in the database but may show zero or null amounts.
- **PE number normalization**: Program Element numbers may appear with or without leading zeros. The database preserves the format as it appears in the source document.
- **Supplemental appropriations**: FY2025 supplemental amounts are tracked separately from enacted amounts. The `amount_fy2025_total` column is the sum of enacted + supplemental.
- **Null values**: A null amount does not mean zero - it means the value was not present in the source data for that fiscal year column.
"""


def get_db_path(override: str | None = None) -> Path:
    """Resolve the database path."""
    if override:
        return Path(override)
    env = os.environ.get("APP_DB_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent / "dod_budget.sqlite"


def get_table_info(conn: sqlite3.Connection, table_name: str) -> list[dict]:
    """Get column info for a table using PRAGMA table_info."""
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [
        {
            "cid": r[0],
            "name": r[1],
            "type": r[2] or "TEXT",
            "notnull": bool(r[3]),
            "default": r[4],
            "pk": bool(r[5]),
        }
        for r in rows
    ]


def get_all_tables(conn: sqlite3.Connection) -> list[str]:
    """List all non-virtual, non-internal tables."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%_fts%' "
        "AND name NOT LIKE 'schema_version' "
        "ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def generate_markdown(conn: sqlite3.Connection) -> str:
    """Generate the full data dictionary markdown."""
    lines: list[str] = []
    lines.append("# Data Dictionary")
    lines.append("")
    lines.append("Auto-generated from the database schema by `scripts/generate_data_dictionary.py`.")
    lines.append("Do not edit manually — re-run the script to update.")
    lines.append("")
    lines.append("---")
    lines.append("")

    tables = get_all_tables(conn)

    # Table of contents
    lines.append("## Tables")
    lines.append("")
    for tbl in tables:
        lines.append(f"- [{tbl}](#{tbl})")
    lines.append("")

    # Each table
    for tbl in tables:
        columns = get_table_info(conn, tbl)
        descs = FIELD_DESCRIPTIONS.get(tbl, {})

        lines.append(f"## {tbl}")
        lines.append("")
        lines.append("| Column | Type | Nullable | Description |")
        lines.append("|--------|------|----------|-------------|")

        for col in columns:
            nullable = "No" if col["notnull"] or col["pk"] else "Yes"
            desc = descs.get(col["name"], "")
            pk_note = " **PK**" if col["pk"] else ""
            default_note = f" Default: `{col['default']}`" if col["default"] else ""
            full_desc = f"{desc}{pk_note}{default_note}".strip()
            lines.append(
                f"| `{col['name']}` | {col['type']} | {nullable} | {full_desc} |"
            )

        lines.append("")

    # Caveats
    lines.append(CAVEATS)

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate data dictionary from schema")
    parser.add_argument("--db", help="Path to SQLite database")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Compare generated output to existing file; exit non-zero if different",
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent.parent / "docs" / "data_dictionary.md"),
        help="Output file path (default: docs/data_dictionary.md)",
    )
    args = parser.parse_args()

    db_path = get_db_path(args.db)

    if not db_path.exists():
        print(f"Warning: Database not found at {db_path}", file=sys.stderr)
        print("Creating schema from schema_design.py DDL...", file=sys.stderr)
        conn = sqlite3.connect(":memory:")
        # Import DDL from schema_design
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        try:
            from schema_design import _DDL_001_CORE, _DDL_001_SEEDS
            conn.executescript(_DDL_001_CORE)
            conn.executescript(_DDL_001_SEEDS)
        except ImportError:
            print("Error: Cannot import schema_design.py", file=sys.stderr)
            sys.exit(1)
    else:
        conn = sqlite3.connect(str(db_path))

    generated = generate_markdown(conn)
    conn.close()

    if args.check:
        output_path = Path(args.output)
        if not output_path.exists():
            print(f"FAIL: {output_path} does not exist", file=sys.stderr)
            sys.exit(1)
        existing = output_path.read_text()
        if existing.strip() == generated.strip():
            print("OK: data dictionary is up to date")
            sys.exit(0)
        else:
            print(f"FAIL: {output_path} is out of date. Re-run:", file=sys.stderr)
            print(f"  python scripts/generate_data_dictionary.py", file=sys.stderr)
            sys.exit(1)
    else:
        print(generated)


if __name__ == "__main__":
    main()
