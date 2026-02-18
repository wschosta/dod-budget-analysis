"""Data validation utilities for DoD budget tools.

Provides reusable functions for:
- Validating budget data types and ranges
- Running validation check registries
- Formatting validation issues
- Type checking and coercion
"""

from typing import List, Dict, Any, Callable, Optional
import sqlite3


class ValidationIssue:
    """Represents a single validation issue found during checks."""

    def __init__(self, check_name: str, severity: str, detail: str,
                 sample: Optional[Any] = None, count: int = 1):
        """Initialize a validation issue.

        Args:
            check_name: Name of the check that found this issue
            severity: Issue severity ('error', 'warning', 'info')
            detail: Human-readable description of the issue
            sample: Example value that triggered the issue
            count: Number of affected rows/records
        """
        self.check_name = check_name
        self.severity = severity
        self.detail = detail
        self.sample = sample
        self.count = count

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "check": self.check_name,
            "severity": self.severity,
            "detail": self.detail,
            "sample": str(self.sample) if self.sample else None,
            "count": self.count,
        }

    def __repr__(self) -> str:
        return (f"ValidationIssue(check={self.check_name}, severity={self.severity}, "
                f"count={self.count})")


class ValidationResult:
    """Collects and reports on validation check results."""

    def __init__(self):
        """Initialize empty validation result."""
        self.issues: List[ValidationIssue] = []
        self.passed_checks: List[str] = []
        self.failed_checks: List[str] = []

    def add_issue(self, check_name: str, severity: str, detail: str,
                 sample: Optional[Any] = None, count: int = 1) -> None:
        """Add a validation issue.

        Args:
            check_name: Name of the check that found this issue
            severity: Issue severity ('error', 'warning', 'info')
            detail: Human-readable description
            sample: Example value that triggered the issue
            count: Number of affected rows/records
        """
        issue = ValidationIssue(check_name, severity, detail, sample, count)
        self.issues.append(issue)

    def mark_check_passed(self, check_name: str) -> None:
        """Mark a check as passed."""
        self.passed_checks.append(check_name)

    def mark_check_failed(self, check_name: str) -> None:
        """Mark a check as failed."""
        self.failed_checks.append(check_name)

    def get_issues_by_severity(self, severity: str) -> List[ValidationIssue]:
        """Get all issues of a specific severity.

        Args:
            severity: 'error', 'warning', or 'info'

        Returns:
            List of issues matching the severity
        """
        return [i for i in self.issues if i.severity == severity]

    def error_count(self) -> int:
        """Get total number of error-level issues."""
        return len(self.get_issues_by_severity("error"))

    def warning_count(self) -> int:
        """Get total number of warning-level issues."""
        return len(self.get_issues_by_severity("warning"))

    def info_count(self) -> int:
        """Get total number of info-level issues."""
        return len(self.get_issues_by_severity("info"))

    def is_valid(self) -> bool:
        """Check if validation passed (no errors)."""
        return self.error_count() == 0

    def summary_text(self) -> str:
        """Generate human-readable validation summary."""
        lines = []
        lines.append("Validation Summary:")
        lines.append(f"  Passed Checks: {len(self.passed_checks)}")
        lines.append(f"  Failed Checks: {len(self.failed_checks)}")
        lines.append(f"  Issues: {len(self.issues)}")
        lines.append(f"    - Errors: {self.error_count()}")
        lines.append(f"    - Warnings: {self.warning_count()}")
        lines.append(f"    - Info: {self.info_count()}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "issues": [i.to_dict() for i in self.issues],
            "summary": {
                "total_checks": len(self.passed_checks) + len(self.failed_checks),
                "passed": len(self.passed_checks),
                "failed": len(self.failed_checks),
                "issues": len(self.issues),
                "errors": self.error_count(),
                "warnings": self.warning_count(),
                "info": self.info_count(),
            }
        }


class ValidationRegistry:
    """Manages a collection of validation check functions."""

    def __init__(self):
        """Initialize empty registry."""
        self.checks: Dict[str, Callable] = {}

    def register(self, name: str, check_fn: Callable) -> None:
        """Register a validation check function.

        Args:
            name: Human-readable check name
            check_fn: Function that returns List[ValidationIssue]
        """
        self.checks[name] = check_fn

    def run_all(self, conn: sqlite3.Connection,
               skip_checks: Optional[List[str]] = None) -> ValidationResult:
        """Run all registered checks.

        Args:
            conn: SQLite connection to validate
            skip_checks: List of check names to skip

        Returns:
            ValidationResult with all issues found
        """
        skip = skip_checks or []
        result = ValidationResult()

        for check_name, check_fn in self.checks.items():
            if check_name in skip:
                continue

            try:
                issues = check_fn(conn)
                if issues:
                    for issue in issues:
                        result.add_issue(issue.check_name, issue.severity,
                                       issue.detail, issue.sample, issue.count)
                    result.mark_check_failed(check_name)
                else:
                    result.mark_check_passed(check_name)
            except Exception as e:
                result.add_issue(
                    check_name, "error",
                    f"Check raised exception: {str(e)[:100]}"
                )
                result.mark_check_failed(check_name)

        return result


def is_valid_fiscal_year(year: int) -> bool:
    """Check if year is a valid fiscal year (2000-2099).

    Args:
        year: Year to validate

    Returns:
        True if valid fiscal year, False otherwise
    """
    return isinstance(year, int) and 2000 <= year <= 2099


def is_valid_amount(value: float) -> bool:
    """Check if value is a valid budget amount.

    Valid amounts are non-negative numbers up to 999 billion.

    Args:
        value: Amount to validate

    Returns:
        True if valid amount, False otherwise
    """
    if not isinstance(value, (int, float)):
        return False
    if isinstance(value, bool):  # bool is subclass of int
        return False
    return 0 <= value <= 999_000_000_000


def is_valid_organization(org: str, known_orgs: Optional[set] = None) -> bool:
    """Check if organization name is valid.

    Args:
        org: Organization name to validate
        known_orgs: Optional set of known valid organization names

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(org, str):
        return False
    if not org.strip():
        return False
    if known_orgs:
        return org in known_orgs
    return True


def is_valid_exhibit_type(exhibit: str, known_exhibits: Optional[set] = None) -> bool:
    """Check if exhibit type is valid.

    Args:
        exhibit: Exhibit type code to validate (e.g., 'm1', 'o1')
        known_exhibits: Optional set of known valid exhibit types

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(exhibit, str):
        return False
    exhibit = exhibit.lower()
    if known_exhibits:
        return exhibit in known_exhibits
    # Generic validation: 1-3 alphanumeric chars
    return 1 <= len(exhibit) <= 3 and exhibit.isalnum()
