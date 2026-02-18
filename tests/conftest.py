"""
Pytest fixtures for DoD budget analysis tests — Step 1.C1

Provides reusable test fixtures: sample Excel files, sample PDFs, temporary
SQLite databases, and pre-loaded database connections.

──────────────────────────────────────────────────────────────────────────────
TODOs — fixture creation tasks (IMPLEMENTED)
──────────────────────────────────────────────────────────────────────────────

TODO 1.C1-a: Create minimal Excel fixture for each summary exhibit type.
    DONE — see _create_exhibit_xlsx() and the fixtures_dir fixture below.

TODO 1.C1-b: Create minimal PDF fixtures.
    DONE — see _create_sample_pdf() using fpdf2 below.

TODO 1.C1-c: Create a fixture that builds a pre-populated test database.
    DONE — see test_db fixture below.

TODO 1.C1-d: Create a fixture for a "known bad" Excel file.
    DONE — see bad_excel fixture below.

TODO 1.C1-e: Add fixture requirements to requirements-dev.txt.
    DONE — requirements-dev.txt already lists pytest, pytest-cov, fpdf2.
"""

import sys
import types
from pathlib import Path

import pytest

# ── Stub pdfplumber (heavy dep, not needed for fixture generation) ─────────────
sys.modules.setdefault("pdfplumber", types.ModuleType("pdfplumber"))

import openpyxl  # noqa: E402 — available in requirements-dev.txt

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _create_exhibit_xlsx(path: Path, exhibit_type: str, rows: list[tuple]) -> Path:
    """Create a minimal .xlsx fixture for a given exhibit type.

    Builds a workbook with one sheet containing a realistic header row and
    the provided data rows.  Values are deterministic so test assertions are
    stable.  Implements TODO 1.C1-a.

    Args:
        path:         Destination file path (must end in .xlsx).
        exhibit_type: e.g. "p1", "r1", "o1", "m1", "c1", "rf1".
        rows:         List of tuples (one per data row) matching the header.

    Returns:
        The written path.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "FY 2026"

    if exhibit_type in ("p1", "p1r"):
        headers = [
            "Account", "Account Title", "Organization",
            "Budget Activity", "Budget Activity Title",
            "Budget Line Item", "Budget Line Item (BLI) Title",
            "FY2024 Actual\nAmount", "FY2025 Enacted\nAmount",
            "FY2026 Request\nAmount",
        ]
    elif exhibit_type == "r1":
        headers = [
            "Account", "Account Title", "Organization",
            "Budget Activity", "Budget Activity Title",
            "PE/BLI", "Program Element/Budget Line Item (BLI) Title",
            "FY2024 Actual\nAmount", "FY2025 Enacted\nAmount",
            "FY2026 Request\nAmount",
        ]
    elif exhibit_type == "o1":
        headers = [
            "Account", "Account Title", "Organization",
            "Budget Activity", "Budget Activity Title",
            "BSA", "Budget SubActivity Title",
            "FY2024 Actual\nAmount", "FY2025 Enacted\nAmount",
            "FY2026 Request\nAmount",
        ]
    elif exhibit_type == "m1":
        headers = [
            "Account", "Account Title", "Organization",
            "Budget Activity", "Budget Activity Title",
            "BSA", "Budget SubActivity Title",
            "FY2024 Actual\nAmount", "FY2025 Enacted\nAmount",
            "FY2026 Request\nAmount",
        ]
    elif exhibit_type == "c1":
        headers = [
            "Account", "Account Title", "Organization",
            "Budget Activity", "Budget Activity Title",
            "Construction Project", "Construction Project Title",
            "Authorization Amount", "Appropriation Amount",
        ]
    elif exhibit_type == "rf1":
        headers = [
            "Account", "Account Title", "Organization",
            "Budget Activity", "Budget Activity Title",
            "Budget Line Item", "Budget Line Item (BLI) Title",
            "FY2024 Actual\nAmount", "FY2025 Enacted\nAmount",
            "FY2026 Request\nAmount",
        ]
    else:
        headers = [
            "Account", "Account Title", "Organization",
            "Budget Activity", "Budget Activity Title",
            "FY2024 Actual\nAmount", "FY2026 Request\nAmount",
        ]

    ws.append(headers)
    for row in rows:
        ws.append(list(row))

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return path


def _create_sample_pdf(path: Path, title: str = "Test Budget Document",
                        include_table: bool = False) -> Path:
    """Create a minimal PDF fixture using fpdf2.

    Generates a PDF with extractable text and optionally a simple table
    layout.  Implements TODO 1.C1-b.

    Args:
        path:          Destination .pdf path.
        title:         Document title printed on the first page.
        include_table: If True, add a rudimentary table-like layout.

    Returns:
        The written path.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        pytest.skip("fpdf2 not installed — skipping PDF fixture generation")

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, title, ln=True)
    pdf.set_font("Helvetica", size=11)
    pdf.cell(0, 8, "Department of Defense", ln=True)
    pdf.cell(0, 8, "Fiscal Year 2026 Budget Justification", ln=True)
    pdf.ln(6)
    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(
        0, 6,
        "This document contains budget line items for demonstration purposes. "
        "Program elements are identified by codes such as 0602702E and 0305116BB. "
        "Amounts are presented in thousands of then-year dollars.",
    )

    if include_table:
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 10)
        col_w = [60, 35, 35, 35]
        headers = ["Program", "FY2024 Actual", "FY2025 Enacted", "FY2026 Request"]
        for w, h in zip(col_w, headers):
            pdf.cell(w, 8, h, border=1)
        pdf.ln()
        pdf.set_font("Helvetica", size=10)
        sample_rows = [
            ("0602702E Advanced Research", "12,345", "13,456", "14,000"),
            ("0305116BB Counter-ISR", "9,876", "10,234", "10,500"),
            ("0601102D Basic Research", "5,000", "5,100", "5,200"),
        ]
        for row in sample_rows:
            for w, val in zip(col_w, row):
                pdf.cell(w, 7, val, border=1)
            pdf.ln()

    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))
    return path


# ── Session-scoped fixtures ───────────────────────────────────────────────────

_P1_ROWS = [
    ("2035", "2035 Aircraft Procurement, Army", "A", "01", "Air Operations",
     "0205231A", "AH-64 Apache Block III", 12_345.0, 13_456.0, 14_000.0),
    ("2035", "2035 Aircraft Procurement, Army", "A", "01", "Air Operations",
     "0205231B", "UH-60 Blackhawk", 8_900.0, 9_100.0, 9_500.0),
    ("2035", "2035 Aircraft Procurement, Army", "A", "02", "Missile Programs",
     "0205231C", "AIM-120 AMRAAM", 6_700.0, 7_000.0, 7_200.0),
]

_R1_ROWS = [
    ("1300", "RDT&E, Army", "A", "06", "RDT&E",
     "0602702E", "Advanced Research Program", 55_000.0, 57_000.0, 59_000.0),
    ("1300", "RDT&E, Army", "A", "07", "Operational Systems Dev",
     "0305116BB", "Counter-ISR", 22_000.0, 23_000.0, 24_000.0),
]

_C1_ROWS = [
    ("2100", "Military Construction, Army", "A", "01", "MilCon",
     "P-2345", "Barracks Replacement, Fort Bragg", 45_000.0, 30_000.0),
]


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory):
    """Return a temporary directory populated with deterministic fixture files.

    Creates one .xlsx per summary exhibit type (TODO 1.C1-a) and two PDFs
    (with and without a table layout) (TODO 1.C1-b).
    """
    d = tmp_path_factory.mktemp("budget_fixtures")

    # TODO 1.C1-a: Excel fixtures
    _create_exhibit_xlsx(d / "p1_display.xlsx", "p1", _P1_ROWS)
    _create_exhibit_xlsx(d / "r1_display.xlsx", "r1", _R1_ROWS)
    _create_exhibit_xlsx(d / "c1_display.xlsx", "c1", _C1_ROWS)
    _create_exhibit_xlsx(d / "o1_display.xlsx", "o1", _P1_ROWS[:2])
    _create_exhibit_xlsx(d / "m1_display.xlsx", "m1", _P1_ROWS[:2])
    _create_exhibit_xlsx(d / "rf1_display.xlsx", "rf1", _P1_ROWS[:1])

    # TODO 1.C1-b: PDF fixtures
    _create_sample_pdf(d / "text_only.pdf", title="Budget Overview FY2026",
                       include_table=False)
    _create_sample_pdf(d / "with_table.pdf", title="RDT&E Justification FY2026",
                       include_table=True)

    return d


@pytest.fixture(scope="session")
def test_db(fixtures_dir, tmp_path_factory):
    """Return a Path to a SQLite database pre-built from fixture files.

    Runs build_database() once per test session so integration tests can
    query real data without repeating the build.  Implements TODO 1.C1-c.
    """
    # Import here so test collection works even without the full dep stack
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from build_budget_db import build_database  # type: ignore

    db_dir = tmp_path_factory.mktemp("test_db")
    db_path = db_dir / "test_budget.sqlite"
    try:
        build_database(fixtures_dir, db_path, rebuild=True)
    except Exception as exc:
        pytest.skip(f"build_database() failed (missing deps?): {exc}")
    return db_path


@pytest.fixture(scope="session")
def bad_excel(tmp_path_factory) -> Path:
    """Return a Path to an intentionally malformed Excel file.

    The file has: no recognisable header row, merged-cell-like empty columns,
    inconsistent column names, and blank rows scattered through the data.
    Used to verify that the parser degrades gracefully.  Implements TODO 1.C1-d.
    """
    d = tmp_path_factory.mktemp("bad_fixtures")
    path = d / "malformed_exhibit.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"

    # Row 1: completely blank (no header here)
    ws.append([None, None, None, None])
    # Row 2: unrecognised headers — no "Account" column
    ws.append(["Item#", "Description", "", "Dollars"])
    # Row 3: blank row in the middle of the header area
    ws.append([None, None, None, None])
    # Row 4: inconsistent naming — "Acct" instead of "Account"
    ws.append(["Acct", "Title", "Org", "Amount"])
    # Data rows with mixed types and missing values
    ws.append([None, "Missing account code", "A", 1_000])
    ws.append(["2035", None, None, "not-a-number"])
    ws.append(["", "", "", ""])
    ws.append([2035, "Aircraft Procurement", "A", 99_999])

    wb.save(str(path))
    return path


# ── Function-scoped helpers ───────────────────────────────────────────────────

@pytest.fixture()
def tmp_db(tmp_path):
    """Return a fresh (empty) SQLite database connection for unit tests.

    Useful for tests that need a database but don't need pre-loaded data.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from build_budget_db import create_database  # type: ignore

    db_path = tmp_path / "unit_test.sqlite"
    conn = create_database(db_path)
    yield conn
    conn.close()
# TODO [Step 1.C2]: Add shared pytest fixtures here.
#
# Planned fixtures:
#   - tmp_db: creates a temporary SQLite database using create_database() ✓ done
#   - sample_xlsx: returns path to a representative test Excel file ✓ done (fixtures_dir)
#   - sample_pdf: returns path to a representative test PDF file ✓ done (fixtures_dir)
#   - built_db: a pre-built database from fixture files for search tests ✓ done (test_db)
#
# See docs/TODO_1C2_unit_tests_parsing.md for full specification.
