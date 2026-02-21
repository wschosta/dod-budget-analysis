"""
Tests for utils/validation.py — ValidationIssue, ValidationResult,
ValidationRegistry, and standalone validator functions.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.validation import (
    ValidationIssue,
    ValidationResult,
    ValidationRegistry,
    is_valid_fiscal_year,
    is_valid_amount,
    is_valid_organization,
    is_valid_exhibit_type,
)


class TestValidationIssue:
    def test_basic_creation(self):
        issue = ValidationIssue("check1", "error", "Something bad happened")
        assert issue.check_name == "check1"
        assert issue.severity == "error"
        assert issue.detail == "Something bad happened"
        assert issue.sample is None
        assert issue.count == 1

    def test_with_sample_and_count(self):
        issue = ValidationIssue("check2", "warning", "Bad row", sample=42, count=10)
        assert issue.sample == 42
        assert issue.count == 10

    def test_to_dict(self):
        issue = ValidationIssue("check1", "error", "detail", sample="abc", count=3)
        d = issue.to_dict()
        assert d["check"] == "check1"
        assert d["severity"] == "error"
        assert d["detail"] == "detail"
        assert d["sample"] == "abc"
        assert d["count"] == 3

    def test_to_dict_none_sample(self):
        issue = ValidationIssue("check1", "info", "ok")
        d = issue.to_dict()
        assert d["sample"] is None

    def test_repr(self):
        issue = ValidationIssue("chk", "warning", "x", count=5)
        r = repr(issue)
        assert "chk" in r
        assert "warning" in r
        assert "5" in r


class TestValidationResult:
    def test_empty_result(self):
        result = ValidationResult()
        assert result.is_valid()
        assert result.error_count() == 0
        assert result.warning_count() == 0
        assert result.info_count() == 0

    def test_add_issue(self):
        result = ValidationResult()
        result.add_issue("c1", "error", "bad")
        assert result.error_count() == 1
        assert not result.is_valid()

    def test_multiple_severities(self):
        result = ValidationResult()
        result.add_issue("c1", "error", "e1")
        result.add_issue("c2", "warning", "w1")
        result.add_issue("c3", "warning", "w2")
        result.add_issue("c4", "info", "i1")
        assert result.error_count() == 1
        assert result.warning_count() == 2
        assert result.info_count() == 1

    def test_get_issues_by_severity(self):
        result = ValidationResult()
        result.add_issue("c1", "error", "e1")
        result.add_issue("c2", "warning", "w1")
        errors = result.get_issues_by_severity("error")
        assert len(errors) == 1
        assert errors[0].detail == "e1"

    def test_mark_check_passed(self):
        result = ValidationResult()
        result.mark_check_passed("check_a")
        assert "check_a" in result.passed_checks

    def test_mark_check_failed(self):
        result = ValidationResult()
        result.mark_check_failed("check_b")
        assert "check_b" in result.failed_checks

    def test_is_valid_warnings_only(self):
        result = ValidationResult()
        result.add_issue("c1", "warning", "w1")
        assert result.is_valid()  # Only errors make it invalid

    def test_summary_text(self):
        result = ValidationResult()
        result.mark_check_passed("a")
        result.mark_check_failed("b")
        result.add_issue("b", "error", "fail")
        text = result.summary_text()
        assert "Passed Checks: 1" in text
        assert "Failed Checks: 1" in text
        assert "Errors: 1" in text

    def test_to_dict(self):
        result = ValidationResult()
        result.mark_check_passed("a")
        result.add_issue("b", "warning", "w")
        result.mark_check_failed("b")
        d = result.to_dict()
        assert d["summary"]["passed"] == 1
        assert d["summary"]["failed"] == 1
        assert d["summary"]["warnings"] == 1
        assert len(d["issues"]) == 1


class TestValidationRegistry:
    def test_register_and_run(self):
        registry = ValidationRegistry()
        conn = sqlite3.connect(":memory:")

        def passing_check(c):
            return []

        registry.register("pass_check", passing_check)
        result = registry.run_all(conn)
        assert "pass_check" in result.passed_checks
        conn.close()

    def test_failing_check(self):
        registry = ValidationRegistry()
        conn = sqlite3.connect(":memory:")

        def failing_check(c):
            return [ValidationIssue("fail_check", "error", "found a problem")]

        registry.register("fail_check", failing_check)
        result = registry.run_all(conn)
        assert "fail_check" in result.failed_checks
        assert result.error_count() == 1
        conn.close()

    def test_exception_in_check(self):
        registry = ValidationRegistry()
        conn = sqlite3.connect(":memory:")

        def broken_check(c):
            raise ValueError("unexpected error")

        registry.register("broken", broken_check)
        result = registry.run_all(conn)
        assert "broken" in result.failed_checks
        assert result.error_count() == 1
        assert "exception" in result.issues[0].detail.lower()
        conn.close()

    def test_skip_checks(self):
        registry = ValidationRegistry()
        conn = sqlite3.connect(":memory:")

        registry.register("run_me", lambda c: [])
        registry.register("skip_me", lambda c: [ValidationIssue("skip_me", "error", "x")])

        result = registry.run_all(conn, skip_checks=["skip_me"])
        assert "run_me" in result.passed_checks
        assert "skip_me" not in result.failed_checks
        assert result.error_count() == 0
        conn.close()

    def test_multiple_checks(self):
        registry = ValidationRegistry()
        conn = sqlite3.connect(":memory:")

        registry.register("a", lambda c: [])
        registry.register("b", lambda c: [ValidationIssue("b", "warning", "w")])
        registry.register("c", lambda c: [])

        result = registry.run_all(conn)
        assert len(result.passed_checks) == 2
        assert len(result.failed_checks) == 1
        conn.close()


class TestIsValidFiscalYear:
    @pytest.mark.parametrize("year", [1990, 1998, 2000, 2025, 2026, 2099])
    def test_valid_years(self, year):
        assert is_valid_fiscal_year(year)

    @pytest.mark.parametrize("year", [1989, 2100, 0, -1])
    def test_invalid_years(self, year):
        assert not is_valid_fiscal_year(year)

    def test_non_int(self):
        assert not is_valid_fiscal_year("2026")
        assert not is_valid_fiscal_year(2026.5)
        assert not is_valid_fiscal_year(None)


class TestIsValidAmount:
    def test_valid_amounts(self):
        assert is_valid_amount(0)
        assert is_valid_amount(100)
        assert is_valid_amount(999_000_000_000)
        assert is_valid_amount(0.01)

    def test_negative(self):
        assert not is_valid_amount(-1)
        assert not is_valid_amount(-0.01)

    def test_too_large(self):
        assert not is_valid_amount(999_000_000_001)

    def test_non_numeric(self):
        assert not is_valid_amount("100")
        assert not is_valid_amount(None)

    def test_bool_rejected(self):
        assert not is_valid_amount(True)
        assert not is_valid_amount(False)


class TestIsValidOrganization:
    def test_valid_string(self):
        assert is_valid_organization("Army")

    def test_empty_string(self):
        assert not is_valid_organization("")
        assert not is_valid_organization("   ")

    def test_non_string(self):
        assert not is_valid_organization(None)
        assert not is_valid_organization(42)

    def test_with_known_orgs(self):
        known = {"Army", "Navy"}
        assert is_valid_organization("Army", known)
        assert not is_valid_organization("Air Force", known)

    def test_without_known_orgs(self):
        assert is_valid_organization("AnyString")


class TestIsValidExhibitType:
    def test_valid_types(self):
        assert is_valid_exhibit_type("p1")
        assert is_valid_exhibit_type("r1")
        assert is_valid_exhibit_type("m1")

    def test_case_insensitive(self):
        assert is_valid_exhibit_type("P1")
        assert is_valid_exhibit_type("R1")

    def test_non_string(self):
        assert not is_valid_exhibit_type(None)
        assert not is_valid_exhibit_type(42)

    def test_too_long(self):
        assert not is_valid_exhibit_type("abcd")

    def test_empty(self):
        assert not is_valid_exhibit_type("")

    def test_with_known_exhibits(self):
        known = {"p1", "r1"}
        assert is_valid_exhibit_type("p1", known)
        assert not is_valid_exhibit_type("m1", known)

    def test_special_chars_rejected(self):
        assert not is_valid_exhibit_type("p!")
        assert not is_valid_exhibit_type("r-1")
