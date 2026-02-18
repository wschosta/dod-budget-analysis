"""
Unit tests for utils/strings.py, utils/validation.py, utils/patterns.py,
and utils/progress.py.

No database, network, or file I/O required.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.strings import safe_float, normalize_whitespace, sanitize_fts5_query
from utils.validation import (
    ValidationIssue,
    ValidationResult,
    ValidationRegistry,
    is_valid_fiscal_year,
    is_valid_amount,
    is_valid_organization,
    is_valid_exhibit_type,
)
from utils.patterns import (
    PE_NUMBER,
    FISCAL_YEAR,
    ACCOUNT_CODE_TITLE,
    WHITESPACE,
    CURRENCY_SYMBOLS,
    FTS5_SPECIAL_CHARS,
    DOWNLOADABLE_EXTENSIONS,
)


# ── safe_float ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("val, expected", [
    (None,    0.0),
    ("",      0.0),
    (" ",     0.0),
    (123,     123.0),
    (0,       0.0),
    (0.0,     0.0),
    (-5.5,    -5.5),
    ("-5.5",  -5.5),
    ("12.34", 12.34),
    ("abc",   0.0),
    (True,    1.0),   # bool is numeric subclass of int
])
def test_safe_float(val, expected):
    assert safe_float(val) == expected


def test_safe_float_currency_symbols():
    assert safe_float("$1,234.56") == 1234.56


def test_safe_float_comma_separated():
    assert safe_float("1,000,000") == 1_000_000.0


def test_safe_float_custom_default():
    assert safe_float(None, default=-1.0) == -1.0
    assert safe_float("bad", default=99.9) == 99.9


# ── normalize_whitespace ──────────────────────────────────────────────────────

def test_normalize_whitespace_multiple_spaces():
    assert normalize_whitespace("hello   world") == "hello world"


def test_normalize_whitespace_tabs():
    assert normalize_whitespace("col1\tcol2") == "col1 col2"


def test_normalize_whitespace_newlines():
    result = normalize_whitespace("Aircraft\nProcurement\n  Air Force")
    assert result == "Aircraft Procurement Air Force"


def test_normalize_whitespace_leading_trailing():
    assert normalize_whitespace("  hello  ") == "hello"


def test_normalize_whitespace_already_clean():
    assert normalize_whitespace("already clean") == "already clean"


def test_normalize_whitespace_empty():
    assert normalize_whitespace("") == ""


# ── sanitize_fts5_query ───────────────────────────────────────────────────────

def test_sanitize_fts5_query_simple():
    result = sanitize_fts5_query("missile defense")
    assert '"missile"' in result
    assert '"defense"' in result
    assert "OR" in result


def test_sanitize_fts5_query_strips_keywords():
    result = sanitize_fts5_query("missile AND defense OR NOT budget")
    # FTS5 boolean keywords are stripped
    assert '"AND"' not in result
    assert '"OR"' not in result
    assert '"NOT"' not in result
    assert '"missile"' in result


def test_sanitize_fts5_query_strips_special_chars():
    # FTS5 strips quote chars from input, then re-wraps each term in quotes
    result = sanitize_fts5_query('army "R&D"')
    # The outer quotes are stripped, terms are re-wrapped: '"army" OR "R&D"'
    assert '"army"' in result
    assert "OR" in result


def test_sanitize_fts5_query_empty():
    assert sanitize_fts5_query("") == ""


def test_sanitize_fts5_query_only_keywords():
    # Only FTS5 keywords → empty result
    result = sanitize_fts5_query("AND OR NOT")
    assert result == ""


def test_sanitize_fts5_query_wraps_in_quotes():
    result = sanitize_fts5_query("army")
    assert result == '"army"'


# ── ValidationIssue ───────────────────────────────────────────────────────────

def test_validation_issue_basic():
    issue = ValidationIssue("test_check", "error", "Something went wrong")
    assert issue.check_name == "test_check"
    assert issue.severity == "error"
    assert issue.detail == "Something went wrong"
    assert issue.count == 1
    assert issue.sample is None


def test_validation_issue_to_dict():
    issue = ValidationIssue("chk", "warning", "A warning", sample="bad_val", count=3)
    d = issue.to_dict()
    assert d["check"] == "chk"
    assert d["severity"] == "warning"
    assert d["detail"] == "A warning"
    assert d["sample"] == "bad_val"
    assert d["count"] == 3


def test_validation_issue_repr():
    issue = ValidationIssue("chk", "info", "detail")
    r = repr(issue)
    assert "chk" in r
    assert "info" in r


# ── ValidationResult ──────────────────────────────────────────────────────────

def test_validation_result_empty():
    vr = ValidationResult()
    assert vr.error_count() == 0
    assert vr.warning_count() == 0
    assert vr.info_count() == 0
    assert vr.is_valid() is True


def test_validation_result_add_error():
    vr = ValidationResult()
    vr.add_issue("chk", "error", "An error")
    assert vr.error_count() == 1
    assert vr.is_valid() is False


def test_validation_result_add_warning():
    vr = ValidationResult()
    vr.add_issue("chk", "warning", "A warning")
    assert vr.warning_count() == 1
    assert vr.is_valid() is True  # warnings don't fail validation


def test_validation_result_get_issues_by_severity():
    vr = ValidationResult()
    vr.add_issue("c1", "error", "err")
    vr.add_issue("c2", "warning", "warn")
    vr.add_issue("c3", "info", "info")
    errors = vr.get_issues_by_severity("error")
    assert len(errors) == 1
    assert errors[0].severity == "error"


def test_validation_result_mark_passed_failed():
    vr = ValidationResult()
    vr.mark_check_passed("pass_check")
    vr.mark_check_failed("fail_check")
    assert "pass_check" in vr.passed_checks
    assert "fail_check" in vr.failed_checks


def test_validation_result_summary_text():
    vr = ValidationResult()
    vr.add_issue("chk", "error", "err")
    vr.mark_check_failed("chk")
    text = vr.summary_text()
    assert "Errors: 1" in text
    assert "Validation Summary" in text


def test_validation_result_to_dict():
    vr = ValidationResult()
    vr.add_issue("chk", "warning", "warn")
    vr.mark_check_passed("ok")
    d = vr.to_dict()
    assert "issues" in d
    assert "summary" in d
    assert d["summary"]["warnings"] == 1


# ── ValidationRegistry ────────────────────────────────────────────────────────

def test_validation_registry_register_and_run():
    reg = ValidationRegistry()

    def my_check(conn):
        return []  # no issues

    reg.register("my_check", my_check)
    result = reg.run_all(conn=None)
    assert "my_check" in result.passed_checks


def test_validation_registry_run_check_with_issues():
    reg = ValidationRegistry()

    def bad_check(conn):
        return [ValidationIssue("bad_check", "error", "Found a problem")]

    reg.register("bad_check", bad_check)
    result = reg.run_all(conn=None)
    assert "bad_check" in result.failed_checks
    assert result.error_count() == 1


def test_validation_registry_skip_check():
    reg = ValidationRegistry()
    called = []

    def skipped_check(conn):
        called.append(True)
        return []

    reg.register("skip_me", skipped_check)
    result = reg.run_all(conn=None, skip_checks=["skip_me"])
    assert not called
    assert "skip_me" not in result.passed_checks
    assert "skip_me" not in result.failed_checks


def test_validation_registry_exception_handling():
    reg = ValidationRegistry()

    def broken_check(conn):
        raise RuntimeError("Unexpected failure")

    reg.register("broken", broken_check)
    result = reg.run_all(conn=None)
    assert "broken" in result.failed_checks
    assert result.error_count() == 1
    assert "exception" in result.issues[0].detail.lower()


# ── is_valid_fiscal_year ──────────────────────────────────────────────────────

@pytest.mark.parametrize("year, expected", [
    (2024, True),
    (2000, True),
    (2099, True),
    (1999, False),  # too old
    (2100, False),  # too new
    (0, False),
    ("2024", False),  # string not int
])
def test_is_valid_fiscal_year(year, expected):
    assert is_valid_fiscal_year(year) == expected


# ── is_valid_amount ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("value, expected", [
    (0,              True),
    (100,            True),
    (999_000_000_000, True),
    (-1,             False),  # negative
    (1_000_000_000_000, False),  # too large
    (True,           False),  # bool excluded
    ("100",          False),  # string
    (None,           False),
])
def test_is_valid_amount(value, expected):
    assert is_valid_amount(value) == expected


# ── is_valid_organization ─────────────────────────────────────────────────────

def test_is_valid_organization_basic():
    assert is_valid_organization("Army") is True


def test_is_valid_organization_empty():
    assert is_valid_organization("") is False
    assert is_valid_organization("   ") is False


def test_is_valid_organization_not_string():
    assert is_valid_organization(None) is False
    assert is_valid_organization(123) is False


def test_is_valid_organization_known_set():
    orgs = {"Army", "Navy", "Air Force"}
    assert is_valid_organization("Army", orgs) is True
    assert is_valid_organization("Marines", orgs) is False


# ── is_valid_exhibit_type ─────────────────────────────────────────────────────

@pytest.mark.parametrize("exhibit, known, expected", [
    ("p1",   None,           True),
    ("r1",   None,           True),
    ("m1",   None,           True),
    ("o1",   None,           True),
    ("c1",   None,           True),
    ("",     None,           False),
    ("toolong", None,        False),  # >3 chars
    (None,   None,           False),
    ("p1",   {"p1", "r1"},   True),
    ("zz",   {"p1", "r1"},   False),
])
def test_is_valid_exhibit_type(exhibit, known, expected):
    assert is_valid_exhibit_type(exhibit, known) == expected


# ── patterns ──────────────────────────────────────────────────────────────────

def test_pe_number_pattern_matches():
    assert PE_NUMBER.search("0602702E") is not None
    assert PE_NUMBER.search("0305116BB") is not None


def test_pe_number_pattern_no_match():
    assert PE_NUMBER.search("no pe here") is None
    assert PE_NUMBER.search("12345") is None


def test_fiscal_year_pattern():
    assert FISCAL_YEAR.search("FY2026") is not None
    assert FISCAL_YEAR.search("FY 2025") is not None
    assert FISCAL_YEAR.search("2024") is not None


def test_account_code_title_pattern():
    m = ACCOUNT_CODE_TITLE.match("2035 Aircraft Procurement, Army")
    assert m is not None
    assert m.group(1) == "2035"
    assert m.group(2) == "Aircraft Procurement, Army"


def test_account_code_title_no_match():
    assert ACCOUNT_CODE_TITLE.match("No Code Title") is None


def test_whitespace_pattern():
    assert WHITESPACE.sub(" ", "hello   world") == "hello world"


def test_currency_symbols_pattern():
    assert CURRENCY_SYMBOLS.sub("", "$1,234") == "1,234"
    assert CURRENCY_SYMBOLS.sub("", "£100") == "100"


def test_fts5_special_chars_pattern():
    result = FTS5_SPECIAL_CHARS.sub("", 'army "R&D" (budget)*')
    assert '"' not in result
    assert "(" not in result
    assert "*" not in result


def test_downloadable_extensions_pattern():
    assert DOWNLOADABLE_EXTENSIONS.search("file.pdf") is not None
    assert DOWNLOADABLE_EXTENSIONS.search("data.xlsx") is not None
    assert DOWNLOADABLE_EXTENSIONS.search("budget.xls") is not None
    assert DOWNLOADABLE_EXTENSIONS.search("report.txt") is None


# ── ProgressTracker (utils/progress.py) ──────────────────────────────────────

from utils.progress import (
    ProgressTracker,
    SilentProgressTracker,
    TerminalProgressTracker,
    FileProgressTracker,
)


def test_silent_tracker_basic():
    """SilentProgressTracker tracks state without printing."""
    t = SilentProgressTracker(total_items=10)
    t.mark_completed(3)
    t.mark_skipped(2)
    t.mark_failed(1)
    assert t.completed == 3
    assert t.skipped == 2
    assert t.failed == 1
    assert t.processed == 6
    assert t.remaining == 4


def test_silent_tracker_progress_fraction():
    t = SilentProgressTracker(total_items=4)
    t.mark_completed(2)
    assert t.progress_fraction == 0.5
    assert t.progress_percent == 50


def test_silent_tracker_zero_total():
    """Zero total_items should not cause division by zero."""
    t = SilentProgressTracker(total_items=0)
    assert t.progress_fraction == 0.0


def test_silent_tracker_over_total():
    """Fraction caps at 1.0 even if more than total processed."""
    t = SilentProgressTracker(total_items=5)
    t.mark_completed(10)
    assert t.progress_fraction == 1.0


def test_silent_tracker_finish():
    """finish() should not raise."""
    t = SilentProgressTracker(total_items=5)
    t.mark_completed(5)
    t.finish()  # should not raise


def test_terminal_tracker_format_bar():
    t = TerminalProgressTracker(total_items=10, show_every_n=1)
    t.mark_completed(5)
    bar = t._format_bar(width=10)
    assert bar.startswith("[")
    assert bar.endswith("]")
    assert "=" in bar


def test_terminal_tracker_format_elapsed_seconds():
    t = TerminalProgressTracker(total_items=5, show_every_n=1)
    # Elapsed is very short — should format as "0m 00s"
    elapsed = t._format_elapsed()
    assert "m" in elapsed
    assert "s" in elapsed


def test_terminal_tracker_format_summary():
    t = TerminalProgressTracker(total_items=10, show_every_n=1)
    t.mark_completed(3)
    t.mark_skipped(1)
    t.mark_failed(1)
    summary = t._format_summary()
    assert "3" in summary
    assert "skipped" in summary
    assert "failed" in summary


def test_file_tracker_bytes_accumulate():
    # Note: add_bytes() calls update() which relies on _format_bar() inherited
    # from TerminalProgressTracker — only test the byte-tracking state directly.
    t = FileProgressTracker(total_items=5)
    t.completed_bytes += 1024
    t.completed_bytes += 2048
    assert t.completed_bytes == 3072


def test_file_tracker_format_bytes_kb():
    t = FileProgressTracker(total_items=1)
    assert "KB" in t._format_bytes(512 * 1024)


def test_file_tracker_format_bytes_mb():
    t = FileProgressTracker(total_items=1)
    result = t._format_bytes(5 * 1024 * 1024)
    assert "MB" in result


def test_file_tracker_format_bytes_gb():
    t = FileProgressTracker(total_items=1)
    result = t._format_bytes(2 * 1024 * 1024 * 1024)
    assert "GB" in result


# ── database utilities (utils/database.py) ───────────────────────────────────

from utils.database import (
    init_pragmas,
    batch_insert,
    get_table_count,
    get_table_schema,
    table_exists,
    create_fts5_index,
    query_to_dicts,
    vacuum_database,
)


@pytest.fixture
def mem_conn():
    """In-memory SQLite connection for database util tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, value REAL)")
    conn.commit()
    yield conn
    conn.close()


def test_init_pragmas(tmp_path):
    """init_pragmas sets WAL journal mode and memory temp_store (on file DB)."""
    # WAL mode requires a file-based database (in-memory DBs use 'memory' mode)
    db = tmp_path / "pragma_test.db"
    conn = sqlite3.connect(str(db))
    init_pragmas(conn)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"
    temp = conn.execute("PRAGMA temp_store").fetchone()[0]
    assert temp == 2  # 2 = MEMORY
    conn.close()


def test_batch_insert_basic(mem_conn):
    rows = [(1, "alpha", 1.0), (2, "beta", 2.0), (3, "gamma", 3.0)]
    n = batch_insert(mem_conn, "INSERT INTO items (id, name, value) VALUES (?,?,?)", rows)
    assert n == 3
    assert mem_conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 3


def test_batch_insert_small_batches(mem_conn):
    rows = [(i, f"item{i}", float(i)) for i in range(1, 11)]
    n = batch_insert(mem_conn, "INSERT INTO items (id, name, value) VALUES (?,?,?)",
                     rows, batch_size=3)
    assert n == 10
    assert mem_conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 10


def test_batch_insert_empty(mem_conn):
    n = batch_insert(mem_conn, "INSERT INTO items (id, name, value) VALUES (?,?,?)", [])
    assert n == 0


def test_get_table_count_empty(mem_conn):
    assert get_table_count(mem_conn, "items") == 0


def test_get_table_count_with_rows(mem_conn):
    mem_conn.execute("INSERT INTO items (name, value) VALUES ('x', 1.0)")
    mem_conn.commit()
    assert get_table_count(mem_conn, "items") == 1


def test_get_table_schema(mem_conn):
    schema = get_table_schema(mem_conn, "items")
    names = [col["name"] for col in schema]
    assert "id" in names
    assert "name" in names
    assert "value" in names


def test_table_exists_true(mem_conn):
    assert table_exists(mem_conn, "items") is True


def test_table_exists_false(mem_conn):
    assert table_exists(mem_conn, "nonexistent_table") is False


def test_create_fts5_index(mem_conn):
    mem_conn.execute("INSERT INTO items (name, value) VALUES ('missile defense', 1.0)")
    mem_conn.commit()
    create_fts5_index(mem_conn, "items", "items_fts", ["name"], rebuild=True)
    # Verify FTS5 table exists
    assert table_exists(mem_conn, "items_fts") is True
    # Verify it can be searched
    result = mem_conn.execute(
        "SELECT rowid FROM items_fts WHERE items_fts MATCH 'missile'"
    ).fetchall()
    assert len(result) >= 1


def test_query_to_dicts(mem_conn):
    mem_conn.execute("INSERT INTO items (name, value) VALUES ('army', 42.0)")
    mem_conn.commit()
    rows = query_to_dicts(mem_conn, "SELECT name, value FROM items")
    assert len(rows) == 1
    assert rows[0]["name"] == "army"
    assert rows[0]["value"] == 42.0


def test_query_to_dicts_with_params(mem_conn):
    mem_conn.execute("INSERT INTO items (name, value) VALUES ('navy', 99.0)")
    mem_conn.commit()
    rows = query_to_dicts(mem_conn, "SELECT * FROM items WHERE name=?", ("navy",))
    assert len(rows) == 1
    assert rows[0]["name"] == "navy"


def test_vacuum_database(tmp_path):
    """vacuum_database should complete without error."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.commit()
    conn.close()
    vacuum_database(db_path)  # should not raise
