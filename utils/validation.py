"""Data validation utilities for DoD budget tools.

Provides reusable functions for:
- Validating budget data types and ranges
- Running validation check registries
- Formatting validation issues
- Type checking and coercion

──────────────────────────────────────────────────────────────────────────────
TODOs for this file
──────────────────────────────────────────────────────────────────────────────

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
    """Check if year is a valid fiscal year (1990-2099).

    The lower bound accommodates Navy archive historical data (FY1998+).

    Args:
        year: Year to validate

    Returns:
        True if valid fiscal year, False otherwise
    """
    return isinstance(year, int) and 1990 <= year <= 2099


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


# ── VAL-001: Cross-exhibit consistency validation ─────────────────────────────

def check_summary_detail_consistency(
    conn: sqlite3.Connection,
    tolerance: float = 0.05,
) -> list["ValidationIssue"]:
    """Validate that summary exhibit totals match sum of detail exhibit lines.

    For each service+fiscal_year, compares:
    - P-1 total vs sum of P-5 amounts
    - R-1 total vs sum of R-2 amounts

    Args:
        conn: SQLite connection.
        tolerance: Acceptable relative difference (default 5%).

    Returns:
        List of ValidationIssue warnings for significant discrepancies.
    """
    issues: list[ValidationIssue] = []

    exhibit_pairs = [
        ("p1", "p5", "Procurement P-1 vs P-5"),
        ("r1", "r2", "RDT&E R-1 vs R-2"),
    ]

    for summary_type, detail_type, label in exhibit_pairs:
        try:
            # Get summary exhibit totals by service + fiscal_year
            summary_rows = conn.execute("""
                SELECT organization_name, fiscal_year,
                       SUM(COALESCE(amount_fy2026_request,
                                    amount_fy2025_enacted,
                                    amount_fy2024_actual, 0)) AS total
                FROM budget_lines
                WHERE LOWER(exhibit_type) = ?
                GROUP BY organization_name, fiscal_year
            """, (summary_type,)).fetchall()

            # Get detail exhibit totals by service + fiscal_year
            detail_rows = conn.execute("""
                SELECT organization_name, fiscal_year,
                       SUM(COALESCE(amount_fy2026_request,
                                    amount_fy2025_enacted,
                                    amount_fy2024_actual, 0)) AS total
                FROM budget_lines
                WHERE LOWER(exhibit_type) = ?
                GROUP BY organization_name, fiscal_year
            """, (detail_type,)).fetchall()

            detail_map = {
                (r["organization_name"], r["fiscal_year"]): r["total"]
                for r in detail_rows
            }

            for row in summary_rows:
                key = (row["organization_name"], row["fiscal_year"])
                detail_total = detail_map.get(key)
                if detail_total is None:
                    continue
                summary_total = row["total"] or 0
                if summary_total == 0:
                    continue
                diff = abs(summary_total - detail_total) / abs(summary_total)
                if diff > tolerance:
                    issues.append(ValidationIssue(
                        check_name="summary_detail_consistency",
                        severity="warning",
                        detail=(
                            f"{label}: {key[0]} FY={key[1]} "
                            f"summary={summary_total:,.0f} "
                            f"detail={detail_total:,.0f} "
                            f"diff={diff:.1%}"
                        ),
                        sample=key,
                        count=1,
                    ))
        except Exception as e:
            issues.append(ValidationIssue(
                check_name="summary_detail_consistency",
                severity="warning",
                detail=f"Could not run {label} check: {e}",
            ))

    return issues


# ── VAL-002: Year-over-year outlier detection ─────────────────────────────────

def check_yoy_outliers(
    conn: sqlite3.Connection,
    threshold: float = 0.5,
) -> list["ValidationIssue"]:
    """Flag budget lines with unusual year-over-year changes.

    Checks where |FY2026_request - FY2025_enacted| / FY2025_enacted > threshold.

    Args:
        conn: SQLite connection.
        threshold: Relative change threshold (default 50%).

    Returns:
        List of ValidationIssue warnings for outlier rows.
    """
    issues: list[ValidationIssue] = []
    try:
        rows = conn.execute("""
            SELECT id, source_file, exhibit_type, organization_name,
                   line_item_title, pe_number,
                   amount_fy2025_enacted, amount_fy2026_request,
                   ABS(amount_fy2026_request - amount_fy2025_enacted)
                       / ABS(amount_fy2025_enacted) AS delta_pct
            FROM budget_lines
            WHERE amount_fy2025_enacted IS NOT NULL
              AND amount_fy2025_enacted != 0
              AND amount_fy2026_request IS NOT NULL
              AND ABS(amount_fy2026_request - amount_fy2025_enacted)
                  / ABS(amount_fy2025_enacted) > ?
            ORDER BY delta_pct DESC
            LIMIT 500
        """, (threshold,)).fetchall()

        if rows:
            issues.append(ValidationIssue(
                check_name="yoy_outliers",
                severity="warning",
                detail=(
                    f"{len(rows)} budget line(s) changed by >{threshold:.0%} "
                    "from FY2025 enacted to FY2026 request"
                ),
                sample=dict(rows[0]) if rows else None,
                count=len(rows),
            ))
    except Exception as e:
        issues.append(ValidationIssue(
            check_name="yoy_outliers",
            severity="warning",
            detail=f"Could not run YoY outlier check: {e}",
        ))
    return issues


# ── VAL-003: JSON export for ValidationResult ─────────────────────────────────

import json as _json  # noqa: E402


def _add_to_json(cls):
    """Add to_json() method to ValidationResult."""
    def to_json(self, indent: int = 2) -> str:
        """Serialize validation results to JSON string.

        Returns:
            JSON string with checks, issues, and summary sections.
        """
        return _json.dumps(self.to_dict(), indent=indent, default=str)
    cls.to_json = to_json
    return cls


# Monkey-patch ValidationResult with to_json()
ValidationResult.to_json = lambda self, indent=2: _json.dumps(  # type: ignore
    self.to_dict(), indent=indent, default=str
)
