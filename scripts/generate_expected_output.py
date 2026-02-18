#!/usr/bin/env python3
"""
Generate Expected Output for Test Fixtures — Step 1.C1

Creates synthetic .xlsx fixture files in tests/fixtures/ and generates
corresponding expected-output JSON files in tests/fixtures/expected/.

The JSON files document the expected parse results for each fixture file,
enabling integration tests to verify that ingest logic produces correct output
without relying on the full build pipeline.

Usage:
    python scripts/generate_expected_output.py
    python scripts/generate_expected_output.py --output-dir tests/fixtures
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

# ── Fixture Definitions ──────────────────────────────────────────────────────
# Each fixture has: filename, exhibit_type, headers, rows, and expected fields.

FIXTURES = [
    {
        "filename": "army_p1_fy2026.xlsx",
        "exhibit_type": "p1",
        "service": "Army",
        "headers": [
            "Account", "Account Title", "Organization",
            "Budget Activity", "Budget Activity Title",
            "Budget Line Item", "Budget Line Item (BLI) Title",
            "FY2024 Actual\nAmount", "FY2025 Enacted\nAmount",
            "FY2026 Request\nAmount",
        ],
        "rows": [
            ("2035", "2035 Aircraft Procurement, Army", "A", "01",
             "Air Operations", "0205231A", "AH-64 Apache Block III",
             12345.0, 13456.0, 14000.0),
            ("2035", "2035 Aircraft Procurement, Army", "A", "01",
             "Air Operations", "0205231B", "UH-60 Blackhawk",
             8900.0, 9100.0, 9500.0),
            ("2035", "2035 Aircraft Procurement, Army", "A", "02",
             "Missile Programs", "0205231C", "AIM-120 AMRAAM",
             6700.0, 7000.0, 7200.0),
        ],
        "expected": {
            "exhibit_type": "p1",
            "row_count": 3,
            "columns_detected": [
                "account", "account_title", "organization",
                "budget_activity", "budget_activity_title",
                "line_item", "line_item_title",
                "amount_fy2024_actual", "amount_fy2025_enacted",
                "amount_fy2026_request",
            ],
            "sample_values": {
                "account": "2035",
                "line_item": "0205231A",
                "amount_fy2026_request": 14000.0,
            },
        },
    },
    {
        "filename": "navy_r1_fy2026.xlsx",
        "exhibit_type": "r1",
        "service": "Navy",
        "headers": [
            "Account", "Account Title", "Organization",
            "Budget Activity", "Budget Activity Title",
            "PE/BLI", "Program Element/Budget Line Item (BLI) Title",
            "FY2024 Actual\nAmount", "FY2025 Enacted\nAmount",
            "FY2026 Request\nAmount",
        ],
        "rows": [
            ("1319", "RDT&E, Navy", "N", "06", "Basic Research",
             "0601103N", "University Research Initiatives",
             45000.0, 47000.0, 48500.0),
            ("1319", "RDT&E, Navy", "N", "07", "Applied Research",
             "0602234N", "Materials Technology",
             32000.0, 33500.0, 35000.0),
        ],
        "expected": {
            "exhibit_type": "r1",
            "row_count": 2,
            "columns_detected": [
                "account", "account_title", "organization",
                "budget_activity", "budget_activity_title",
                "line_item", "line_item_title",
                "amount_fy2024_actual", "amount_fy2025_enacted",
                "amount_fy2026_request",
            ],
            "sample_values": {
                "account": "1319",
                "line_item": "0601103N",
                "amount_fy2026_request": 48500.0,
            },
        },
    },
    {
        "filename": "army_p5_fy2026.xlsx",
        "exhibit_type": "p5",
        "service": "Army",
        "headers": [
            "Account", "Program Element", "Line Item", "Item Title",
            "Unit of Measure",
            "Prior Year Quantity", "Current Year Quantity", "Estimate Quantity",
            "Prior Year Unit Cost", "Current Year Unit Cost",
            "Estimate Unit Cost", "Justification",
        ],
        "rows": [
            ("2035", "0205231A", "LIN-001", "AH-64 Apache Block III",
             "Each", 12, 14, 15, 55000.0, 56500.0, 58000.0,
             "Full-rate production continues."),
            ("2035", "0205231B", "LIN-002", "UH-60 Blackhawk M-Model",
             "Each", 8, 10, 11, 18000.0, 18500.0, 19000.0,
             "Replaces aging L-model fleet."),
        ],
        "expected": {
            "exhibit_type": "p5",
            "row_count": 2,
            "columns_detected": [
                "program_element", "line_item_number", "line_item_title",
                "unit", "prior_year_qty", "estimate_qty",
                "prior_year_unit_cost", "estimate_unit_cost",
                "justification",
            ],
            "sample_values": {
                "line_item_number": "LIN-001",
                "unit": "Each",
                "estimate_unit_cost": 58000.0,
            },
        },
    },
    {
        "filename": "army_r2_fy2026.xlsx",
        "exhibit_type": "r2",
        "service": "Army",
        "headers": [
            "Account", "PE", "Sub-Element", "Title",
            "Prior Year", "Current Year", "Estimate",
            "Metric", "Planned Achievement",
        ],
        "rows": [
            ("1300", "0602702E", "A", "Advanced Materials Research",
             12000.0, 13500.0, 14000.0,
             "TRL Level", "Achieve TRL-4 for candidate materials"),
            ("1300", "0602702E", "B", "Computational Modeling",
             5000.0, 5500.0, 5800.0,
             "Simulation Fidelity", "High-fidelity model validated"),
        ],
        "expected": {
            "exhibit_type": "r2",
            "row_count": 2,
            "columns_detected": [
                "program_element", "sub_element", "title",
                "prior_year_amount", "current_year_amount",
                "estimate_amount", "planned_achievement",
            ],
            "sample_values": {
                "program_element": "0602702E",
                "sub_element": "A",
                "estimate_amount": 14000.0,
            },
        },
    },
]


def create_fixture_xlsx(fixture: dict, output_dir: Path) -> Path:
    """Create an .xlsx file from a fixture definition."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "FY 2026"

    ws.append(fixture["headers"])
    for row in fixture["rows"]:
        ws.append(list(row))

    path = output_dir / fixture["filename"]
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return path


def create_expected_json(fixture: dict, output_dir: Path) -> Path:
    """Write the expected parse output JSON for a fixture."""
    expected_dir = output_dir / "expected"
    expected_dir.mkdir(parents=True, exist_ok=True)

    json_name = Path(fixture["filename"]).stem + "_expected.json"
    path = expected_dir / json_name

    data = {
        "source_file": fixture["filename"],
        "exhibit_type": fixture["exhibit_type"],
        "service": fixture["service"],
        **fixture["expected"],
    }
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path


def main():
    parser = argparse.ArgumentParser(
        description="Generate test fixture files and expected output JSON"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=FIXTURES_DIR,
        help=f"Output directory (default: {FIXTURES_DIR})",
    )
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating fixtures in {output_dir}/")
    for fixture in FIXTURES:
        xlsx_path = create_fixture_xlsx(fixture, output_dir)
        json_path = create_expected_json(fixture, output_dir)
        print(f"  {xlsx_path.name} -> {json_path.relative_to(output_dir)}")

    print(f"\nGenerated {len(FIXTURES)} fixture files with expected output.")
    print(f"  .xlsx files: {output_dir}/")
    print(f"  .json files: {output_dir}/expected/")


if __name__ == "__main__":
    main()
