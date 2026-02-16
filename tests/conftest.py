"""
Pytest fixtures for DoD budget analysis tests — Step 1.C1

Provides reusable test fixtures: sample Excel files, sample PDFs, temporary
SQLite databases, and pre-loaded database connections.

──────────────────────────────────────────────────────────────────────────────
TODOs — fixture creation tasks
──────────────────────────────────────────────────────────────────────────────

TODO 1.C1-a: Create minimal Excel fixture for each summary exhibit type.
    For P-1, R-1, O-1, M-1, C-1, RF-1: use openpyxl to generate a small .xlsx
    file (2–3 sheets, 5–10 data rows each) with realistic headers and values.
    Store generated files in tests/fixtures/.  These must be deterministic
    (no randomness) so assertions are stable.
    Token-efficient tip: write a helper function create_exhibit_xlsx(exhibit_type,
    rows) that builds the workbook programmatically.  Call it once per exhibit
    type in a session-scoped fixture.

TODO 1.C1-b: Create minimal PDF fixtures.
    Generate 2–3 small PDFs using reportlab or fpdf2: one with extractable text,
    one with a table layout, and one with a mix.  Store in tests/fixtures/.
    Token-efficient tip: fpdf2 is lighter than reportlab — `pip install fpdf2`
    and use ~15 lines per fixture.

TODO 1.C1-c: Create a fixture that builds a pre-populated test database.
    Use the fixtures from 1.C1-a and 1.C1-b, run build_database() against them
    into a tmp_path SQLite file, and yield the connection.  Session-scoped so
    it's built once per test run.

TODO 1.C1-d: Create a fixture for a "known bad" Excel file.
    An .xlsx with intentionally broken formatting: missing header row, merged
    cells, extra blank columns, inconsistent column names.  Used to test error
    handling and graceful degradation in the parser.

TODO 1.C1-e: Add fixture requirements to requirements-dev.txt.
    Create requirements-dev.txt with: pytest, pytest-cov, fpdf2 (for PDF
    fixture generation), and any other test-only dependencies.
"""

import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# TODO: implement fixtures per TODOs above

@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory):
    """Return a temporary directory populated with test fixture files."""
    # TODO 1.C1-a, 1.C1-b: generate fixtures here
    d = tmp_path_factory.mktemp("budget_fixtures")
    return d


@pytest.fixture(scope="session")
def test_db(fixtures_dir):
    """Return a Path to a test SQLite database built from fixture files."""
    # TODO 1.C1-c: call build_database(fixtures_dir, db_path) and return db_path
    pass
