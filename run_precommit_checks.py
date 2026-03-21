#!/usr/bin/env python3
"""
Pre-commit check runner utility.

Provides PreCommitChecker — a lightweight harness for running a sequence of
boolean checks, collecting pass/fail/skip counts, and printing a summary.

Usage (standalone):
    python run_precommit_checks.py

Usage (library):
    from run_precommit_checks import PreCommitChecker
    checker = PreCommitChecker(verbose=True)
    checker.check("lint", lambda: subprocess.run(["ruff", "check", "."]).returncode == 0)
    checker.skip("gui", reason="no display")
    ok = checker.summary()
"""

import logging
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


class PreCommitChecker:
    """Run named boolean checks and accumulate pass/fail/skip counts.

    A check passes when its callable returns anything other than ``False``
    (including ``None``, ``True``, or any truthy value).  A check fails when
    the callable returns ``False`` *or* raises any exception.
    """

    def __init__(self, verbose: bool = False) -> None:
        self.verbose = verbose
        self.passed: int = 0
        self.failed: int = 0
        self.skipped: int = 0
        self._results: list[tuple[str, str, str]] = []  # (name, status, detail)

    # ------------------------------------------------------------------
    def check(self, name: str, fn: Callable) -> bool:
        """Run *fn* and record the result.

        Returns ``True`` if the check passed, ``False`` otherwise.
        """
        try:
            result = fn()
            passed = result is not False
        except Exception:
            passed = False
            detail = traceback.format_exc().strip().splitlines()[-1]
            self._results.append((name, "FAIL", detail))
            self.failed += 1
            if self.verbose:
                print(f"  FAIL  {name}  ({detail})")
            return False

        if passed:
            self.passed += 1
            self._results.append((name, "PASS", ""))
            if self.verbose:
                print(f"  PASS  {name}")
        else:
            self.failed += 1
            self._results.append((name, "FAIL", "returned False"))
            if self.verbose:
                print(f"  FAIL  {name}  (returned False)")
        return passed

    # ------------------------------------------------------------------
    def skip(self, name: str, reason: str = "") -> None:
        """Record a skipped check without running anything."""
        self.skipped += 1
        self._results.append((name, "SKIP", reason))
        if self.verbose:
            note = f"  ({reason})" if reason else ""
            print(f"  SKIP  {name}{note}")

    # ------------------------------------------------------------------
    def summary(self) -> bool:
        """Print a summary line and return ``True`` iff all checks passed."""
        total = self.passed + self.failed + self.skipped
        ok = self.failed == 0
        status = "OK" if ok else "FAIL"
        print(
            f"\n[{status}] {self.passed}/{total} passed, "
            f"{self.failed} failed, {self.skipped} skipped"
        )
        if not ok:
            print("Failed checks:")
            for name, st, detail in self._results:
                if st == "FAIL":
                    suffix = f": {detail}" if detail else ""
                    print(f"  - {name}{suffix}")
        return ok


# ---------------------------------------------------------------------------
# Standalone runner — mirrors the CLAUDE.md "Pre-PR Checklist"
# ---------------------------------------------------------------------------

def _run(cmd: list[str]) -> bool:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 and result.stdout:
        print(result.stdout[-2000:])
    if result.returncode != 0 and result.stderr:
        print(result.stderr[-2000:])
    return result.returncode == 0


def main() -> int:
    checker = PreCommitChecker(verbose=True)
    root = Path(__file__).resolve().parent

    print("Running pre-commit checks…\n")

    checker.check(
        "ruff",
        lambda: _run([
            sys.executable, "-m", "ruff", "check", str(root),
            "--select=E,W,F", "--ignore=E501",
            "--exclude=DoD_Budget_Documents",
        ]),
    )
    checker.check(
        "mypy",
        lambda: _run([
            sys.executable, "-m", "mypy",
            str(root / "api"), str(root / "utils"),
            "--ignore-missing-imports",
        ]),
    )
    checker.check(
        "pytest",
        lambda: _run([
            sys.executable, "-m", "pytest", str(root / "tests"),
            "--ignore=" + str(root / "tests/test_gui_tracker.py"),
            "--ignore=" + str(root / "tests/optimization_validation"),
            "-q", "--tb=short",
        ]),
    )

    return 0 if checker.summary() else 1


if __name__ == "__main__":
    sys.exit(main())
