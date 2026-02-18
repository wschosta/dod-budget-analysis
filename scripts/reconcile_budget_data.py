#!/usr/bin/env python3
"""
Budget Data Reconciliation — Steps 2.B2-a and 2.B2-b

Cross-checks budget data for internal consistency:

  2.B2-a  Cross-service reconciliation:
          For each fiscal year, sum service-level P-1 totals and compare
          against the Comptroller summary P-1 total.

  2.B2-b  Cross-exhibit reconciliation:
          For each service+FY, compare summary exhibit totals (P-1, R-1)
          against the sum of their detail exhibits (P-5, R-2).

Outputs a Markdown report and optional JSON to docs/reconciliation_report.md.

Usage:
    python scripts/reconcile_budget_data.py
    python scripts/reconcile_budget_data.py --db path/to/dod_budget.sqlite
    python scripts/reconcile_budget_data.py --tolerance 0.5
    python scripts/reconcile_budget_data.py --json
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DEFAULT_DB_PATH = Path("dod_budget.sqlite")
DEFAULT_OUTPUT = Path("docs/reconciliation_report.md")
DEFAULT_TOLERANCE_PCT = 1.0  # 1% tolerance for rounding differences

# Amount columns to reconcile (request year is the primary comparison)
AMOUNT_COLUMNS = [
    ("amount_fy2024_actual", "FY2024 Actual"),
    ("amount_fy2025_enacted", "FY2025 Enacted"),
    ("amount_fy2026_request", "FY2026 Request"),
]

# Summary-to-detail exhibit pairings
EXHIBIT_PAIRS = [
    {
        "summary": "p1",
        "detail": "p5",
        "label": "Procurement (P-1 vs P-5)",
    },
    {
        "summary": "r1",
        "detail": "r2",
        "label": "RDT&E (R-1 vs R-2)",
    },
]


def _get_service_totals(
    conn: sqlite3.Connection,
    exhibit_type: str,
    amount_col: str,
) -> dict[str, float]:
    """Sum amount_col by organization_name for a given exhibit type.

    Returns dict mapping organization_name -> total.
    """
    cur = conn.execute(
        f"""
        SELECT organization_name, SUM({amount_col}) AS total
        FROM budget_lines
        WHERE exhibit_type = ?
          AND organization_name IS NOT NULL
          AND organization_name != ''
          AND {amount_col} IS NOT NULL
        GROUP BY organization_name
        ORDER BY organization_name
        """,
        (exhibit_type,),
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def _get_comptroller_total(
    conn: sqlite3.Connection,
    exhibit_type: str,
    amount_col: str,
) -> float | None:
    """Get the Comptroller summary total for an exhibit type.

    The Comptroller category aggregates all services, so its total should
    match the sum of individual service totals.
    """
    cur = conn.execute(
        f"""
        SELECT SUM({amount_col}) AS total
        FROM budget_lines
        WHERE exhibit_type = ?
          AND (
            organization_name LIKE '%Comptroller%'
            OR source_file LIKE '%Comptroller%'
            OR source_file LIKE '%comptroller%'
          )
          AND {amount_col} IS NOT NULL
        """,
        (exhibit_type,),
    )
    row = cur.fetchone()
    return row[0] if row and row[0] is not None else None


def reconcile_cross_service(
    conn: sqlite3.Connection,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
) -> list[dict]:
    """2.B2-a: Cross-service reconciliation for each exhibit+amount column.

    Compares the sum of all service-level totals against the Comptroller
    summary total.  Reports the delta and whether it exceeds tolerance.

    Returns list of reconciliation result dicts.
    """
    results = []

    for exhibit_type in ["p1", "r1", "o1", "m1"]:
        for amount_col, col_label in AMOUNT_COLUMNS:
            service_totals = _get_service_totals(
                conn, exhibit_type, amount_col
            )
            if not service_totals:
                continue

            # Exclude Comptroller rows from the service sum (they are the
            # aggregate we're comparing against)
            service_sum = sum(
                v
                for k, v in service_totals.items()
                if "comptroller" not in k.lower()
            )

            comptroller_total = _get_comptroller_total(
                conn, exhibit_type, amount_col
            )

            if comptroller_total is not None and comptroller_total != 0:
                delta = service_sum - comptroller_total
                delta_pct = abs(delta) / abs(comptroller_total) * 100
                within_tolerance = delta_pct <= tolerance_pct
            else:
                delta = None
                delta_pct = None
                within_tolerance = None

            results.append({
                "check": "cross_service",
                "exhibit_type": exhibit_type,
                "amount_column": col_label,
                "service_sum": round(service_sum, 2),
                "comptroller_total": (
                    round(comptroller_total, 2)
                    if comptroller_total is not None
                    else None
                ),
                "delta": round(delta, 2) if delta is not None else None,
                "delta_pct": (
                    round(delta_pct, 2) if delta_pct is not None else None
                ),
                "within_tolerance": within_tolerance,
                "services": {
                    k: round(v, 2) for k, v in service_totals.items()
                },
            })

    return results


def reconcile_cross_exhibit(
    conn: sqlite3.Connection,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
) -> list[dict]:
    """2.B2-b: Cross-exhibit reconciliation (summary vs detail).

    For each service+FY, compares P-1 totals vs sum(P-5) and R-1 vs sum(R-2).

    Returns list of reconciliation result dicts.
    """
    results = []

    for pair in EXHIBIT_PAIRS:
        summary_type = pair["summary"]
        detail_type = pair["detail"]
        label = pair["label"]

        for amount_col, col_label in AMOUNT_COLUMNS:
            # Get summary totals by org
            summary_totals = _get_service_totals(
                conn, summary_type, amount_col
            )
            # Get detail totals by org
            detail_totals = _get_service_totals(
                conn, detail_type, amount_col
            )

            # Compare for each org that has both summary and detail data
            all_orgs = set(summary_totals.keys()) | set(detail_totals.keys())
            for org in sorted(all_orgs):
                s_total = summary_totals.get(org)
                d_total = detail_totals.get(org)

                if s_total is None or d_total is None:
                    # One side missing — still report it
                    results.append({
                        "check": "cross_exhibit",
                        "label": label,
                        "organization": org,
                        "amount_column": col_label,
                        "summary_total": (
                            round(s_total, 2) if s_total is not None else None
                        ),
                        "detail_total": (
                            round(d_total, 2) if d_total is not None else None
                        ),
                        "delta": None,
                        "delta_pct": None,
                        "within_tolerance": None,
                        "note": "missing "
                        + ("detail" if d_total is None else "summary")
                        + " data",
                    })
                    continue

                delta = s_total - d_total
                base = abs(s_total) if s_total != 0 else 1.0
                delta_pct = abs(delta) / base * 100
                within_tolerance = delta_pct <= tolerance_pct

                results.append({
                    "check": "cross_exhibit",
                    "label": label,
                    "organization": org,
                    "amount_column": col_label,
                    "summary_total": round(s_total, 2),
                    "detail_total": round(d_total, 2),
                    "delta": round(delta, 2),
                    "delta_pct": round(delta_pct, 2),
                    "within_tolerance": within_tolerance,
                    "note": None,
                })

    return results


def generate_report(
    cross_service: list[dict],
    cross_exhibit: list[dict],
    tolerance_pct: float,
) -> str:
    """Generate a Markdown reconciliation report."""
    lines = [
        "# Budget Data Reconciliation Report",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Tolerance: {tolerance_pct}%",
        "",
        "---",
        "",
    ]

    # ── 2.B2-a: Cross-Service ────────────────────────────────────────────────
    lines.extend([
        "## Cross-Service Reconciliation (2.B2-a)",
        "",
        "Compares the sum of individual service P-1/R-1/O-1/M-1 totals "
        "against the Comptroller summary total for the same exhibit type.",
        "",
    ])

    if not cross_service:
        lines.append("_No data available for cross-service reconciliation._")
        lines.append("")
    else:
        lines.extend([
            "| Exhibit | Amount Column | Service Sum | Comptroller | "
            "Delta | Delta % | Status |",
            "|---------|--------------|------------:|------------:|"
            "------:|--------:|--------|",
        ])
        for r in cross_service:
            status = (
                "OK"
                if r["within_tolerance"]
                else ("MISMATCH" if r["within_tolerance"] is False else "N/A")
            )
            s_sum = f"{r['service_sum']:,.0f}" if r["service_sum"] else "—"
            c_tot = (
                f"{r['comptroller_total']:,.0f}"
                if r["comptroller_total"] is not None
                else "—"
            )
            delta = (
                f"{r['delta']:,.0f}" if r["delta"] is not None else "—"
            )
            dpct = (
                f"{r['delta_pct']:.2f}%"
                if r["delta_pct"] is not None
                else "—"
            )
            lines.append(
                f"| {r['exhibit_type'].upper()} | {r['amount_column']} | "
                f"{s_sum} | {c_tot} | {delta} | {dpct} | {status} |"
            )
        lines.append("")

    # ── 2.B2-b: Cross-Exhibit ────────────────────────────────────────────────
    lines.extend([
        "## Cross-Exhibit Reconciliation (2.B2-b)",
        "",
        "Compares summary exhibit totals against the sum of corresponding "
        "detail exhibit line items for each service.",
        "",
    ])

    if not cross_exhibit:
        lines.append("_No data available for cross-exhibit reconciliation._")
        lines.append("")
    else:
        lines.extend([
            "| Pair | Organization | Amount Column | Summary | Detail | "
            "Delta | Delta % | Status |",
            "|------|-------------|--------------|--------:|-------:|"
            "------:|--------:|--------|",
        ])
        for r in cross_exhibit:
            status = (
                "OK"
                if r["within_tolerance"]
                else (
                    "MISMATCH"
                    if r["within_tolerance"] is False
                    else (r.get("note") or "N/A")
                )
            )
            s_tot = (
                f"{r['summary_total']:,.0f}"
                if r["summary_total"] is not None
                else "—"
            )
            d_tot = (
                f"{r['detail_total']:,.0f}"
                if r["detail_total"] is not None
                else "—"
            )
            delta = (
                f"{r['delta']:,.0f}" if r["delta"] is not None else "—"
            )
            dpct = (
                f"{r['delta_pct']:.2f}%"
                if r["delta_pct"] is not None
                else "—"
            )
            org = r["organization"]
            if len(org) > 30:
                org = org[:27] + "..."
            lines.append(
                f"| {r['label']} | {org} | {r['amount_column']} | "
                f"{s_tot} | {d_tot} | {delta} | {dpct} | {status} |"
            )
        lines.append("")

    # ── Summary ──────────────────────────────────────────────────────────────
    total_checks = len(cross_service) + len(cross_exhibit)
    ok = sum(
        1
        for r in cross_service + cross_exhibit
        if r.get("within_tolerance") is True
    )
    mismatches = sum(
        1
        for r in cross_service + cross_exhibit
        if r.get("within_tolerance") is False
    )
    na = total_checks - ok - mismatches

    lines.extend([
        "## Summary",
        "",
        f"- **Total checks:** {total_checks}",
        f"- **Within tolerance:** {ok}",
        f"- **Mismatches:** {mismatches}",
        f"- **Insufficient data:** {na}",
        "",
        "---",
        "",
        "## Notes",
        "",
        "- Amounts are in thousands of dollars unless otherwise noted.",
        "- Deltas may arise from rounding, exhibit scope differences, "
        "or classified line items excluded from public exhibits.",
        "- A 'missing detail' note means no detail exhibit rows were found "
        "for that service, which is expected when detail exhibits haven't "
        "been ingested yet.",
    ])

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Reconcile budget data across services and exhibits"
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
        help=f"Output report path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_TOLERANCE_PCT,
        help=f"Tolerance percentage for delta (default: {DEFAULT_TOLERANCE_PCT}%%)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="output_json",
        help="Also write a JSON report",
    )
    args = parser.parse_args()

    if not args.db.exists():
        print(f"ERROR: Database not found: {args.db}", file=sys.stderr)
        print("Run 'python build_budget_db.py' first.", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(args.db))

    print(f"Running cross-service reconciliation (2.B2-a)...")
    cross_service = reconcile_cross_service(conn, args.tolerance)
    print(f"  {len(cross_service)} checks completed.")

    print(f"Running cross-exhibit reconciliation (2.B2-b)...")
    cross_exhibit = reconcile_cross_exhibit(conn, args.tolerance)
    print(f"  {len(cross_exhibit)} checks completed.")

    conn.close()

    report = generate_report(cross_service, cross_exhibit, args.tolerance)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report)
    print(f"\nReport written to {args.output}")

    if args.output_json:
        json_path = args.output.with_suffix(".json")
        data = {
            "timestamp": datetime.now().isoformat(),
            "tolerance_pct": args.tolerance,
            "cross_service": cross_service,
            "cross_exhibit": cross_exhibit,
        }
        json_path.write_text(json.dumps(data, indent=2, default=str))
        print(f"JSON report written to {json_path}")

    # Console summary
    total = len(cross_service) + len(cross_exhibit)
    mismatches = sum(
        1
        for r in cross_service + cross_exhibit
        if r.get("within_tolerance") is False
    )
    print(f"\nTotal: {total} checks, {mismatches} mismatch(es)")


if __name__ == "__main__":
    main()
