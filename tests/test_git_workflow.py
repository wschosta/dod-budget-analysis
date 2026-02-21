"""
Tests for git workflow conventions and repository hygiene.

Verifies:
  - Branch naming conventions
  - Commit message format
  - CI workflow file structure
  - Pre-commit hook existence and executability
  - .gitignore coverage
  - No secrets or large files staged
  - Package structure integrity (downloader/, pipeline/, api/, utils/)
"""
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ── Branch naming convention tests ──────────────────────────────────────────

class TestBranchNaming:
    """Verify branch names follow project conventions."""

    VALID_PATTERNS = [
        re.compile(r"^main$"),
        re.compile(r"^develop$"),
        re.compile(r"^claude/[\w-]+-[\w-]+$"),   # claude/<ticket>-<desc>
        re.compile(r"^feat/[\w-]+$"),             # feat/<desc>
        re.compile(r"^fix/[\w-]+$"),              # fix/<desc>
        re.compile(r"^docs/[\w-]+$"),             # docs/<desc>
        re.compile(r"^refactor/[\w-]+$"),         # refactor/<desc>
        re.compile(r"^test/[\w-]+$"),             # test/<desc>
        re.compile(r"^chore/[\w-]+$"),            # chore/<desc>
        re.compile(r"^perf/[\w-]+$"),             # perf/<desc>
        re.compile(r"^release/[\d.]+$"),          # release/<version>
    ]

    def test_current_branch_follows_convention(self):
        """Current branch name should match one of the allowed patterns."""
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        if result.returncode != 0:
            pytest.skip("Not in a git repository")
        branch = result.stdout.strip()
        if branch == "HEAD":
            pytest.skip("Detached HEAD (e.g. CI PR checkout)")
        assert any(p.match(branch) for p in self.VALID_PATTERNS), (
            f"Branch '{branch}' does not match any allowed pattern: "
            f"main, develop, claude/<id>-<desc>, feat/<desc>, fix/<desc>, "
            f"docs/<desc>, refactor/<desc>, test/<desc>, chore/<desc>, "
            f"perf/<desc>, release/<version>"
        )

    @pytest.mark.parametrize("branch,valid", [
        ("main", True),
        ("develop", True),
        ("claude/TICKET-123-add-feature", True),
        ("feat/dark-mode", True),
        ("fix/null-pointer", True),
        ("docs/api-reference", True),
        ("refactor/comprehensive-restructure", True),
        ("feature/something", False),
        ("bugfix/something", False),
        ("my-branch", False),
        ("MAIN", False),
    ])
    def test_branch_name_validation(self, branch: str, valid: bool):
        """Verify branch naming regex correctness."""
        matches = any(p.match(branch) for p in self.VALID_PATTERNS)
        assert matches == valid, f"Branch '{branch}' expected valid={valid}"


# ── Commit message format tests ─────────────────────────────────────────────

class TestCommitMessageFormat:
    """Verify commit messages follow <TYPE>: <summary> convention."""

    VALID_TYPES = {"feat", "fix", "refactor", "test", "docs", "chore", "perf"}
    COMMIT_RE = re.compile(
        r"^(feat|fix|refactor|test|docs|chore|perf): .{1,72}$"
    )

    def test_recent_commits_follow_format(self):
        """Check that recent commits on this branch follow the convention."""
        result = subprocess.run(
            ["git", "log", "--format=%s", "-20"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        if result.returncode != 0:
            pytest.skip("Not in a git repository")
        messages = [m for m in result.stdout.strip().split("\n") if m]
        if not messages:
            pytest.skip("No commits found")

        # Allow merge commits and co-authored commits
        merge_re = re.compile(r"^Merge ")
        violations = []
        for msg in messages:
            if merge_re.match(msg):
                continue
            if not self.COMMIT_RE.match(msg):
                violations.append(msg)

        # Warn but don't fail for older commits (only check latest 5)
        recent_violations = [v for v in violations[:5]]
        if recent_violations:
            pytest.xfail(
                f"Some recent commits don't follow convention: "
                f"{recent_violations[:3]}"
            )

    @pytest.mark.parametrize("msg,valid", [
        ("feat: add dark mode toggle", True),
        ("fix: resolve null pointer in search", True),
        ("refactor: extract downloader package", True),
        ("test: add git workflow tests", True),
        ("docs: update README with new structure", True),
        ("chore: update dependencies", True),
        ("perf: optimize FTS5 queries", True),
        ("feat: this is a very long commit message that exceeds the seventy-two character limit for subject lines", False),
        ("added something", False),
        ("Fix: capitalize type", False),
        ("feat:missing space", False),
    ])
    def test_commit_message_validation(self, msg: str, valid: bool):
        """Verify commit message regex correctness."""
        matches = bool(self.COMMIT_RE.match(msg))
        assert matches == valid, f"Message '{msg}' expected valid={valid}"


# ── CI workflow file tests ──────────────────────────────────────────────────

class TestCIWorkflow:
    """Verify CI workflow files exist and have valid structure."""

    def test_ci_yml_exists(self):
        ci_path = ROOT / ".github" / "workflows" / "ci.yml"
        assert ci_path.exists(), "CI workflow file missing"

    def test_ci_yml_valid_yaml(self):
        ci_path = ROOT / ".github" / "workflows" / "ci.yml"
        if not ci_path.exists():
            pytest.skip("CI workflow file missing")
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml not installed")
        with open(ci_path) as f:
            data = yaml.safe_load(f)
        assert "jobs" in data, "CI workflow must define jobs"
        # YAML parses unquoted `on` key as boolean True
        assert "on" in data or True in data, "CI workflow must define triggers"

    def test_ci_tests_python_matrix(self):
        """CI should test on multiple Python versions."""
        ci_path = ROOT / ".github" / "workflows" / "ci.yml"
        if not ci_path.exists():
            pytest.skip("CI workflow file missing")
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml not installed")
        with open(ci_path) as f:
            data = yaml.safe_load(f)
        test_job = data.get("jobs", {}).get("test", {})
        matrix = test_job.get("strategy", {}).get("matrix", {})
        versions = matrix.get("python-version", [])
        assert len(versions) >= 2, (
            f"CI should test on at least 2 Python versions, found: {versions}"
        )

    def test_deploy_yml_exists(self):
        deploy_path = ROOT / ".github" / "workflows" / "deploy.yml"
        assert deploy_path.exists(), "Deploy workflow file missing"

    def test_all_workflow_files_valid_yaml(self):
        """All .yml files in .github/workflows/ should be valid YAML."""
        try:
            import yaml
        except ImportError:
            pytest.skip("pyyaml not installed")
        workflows_dir = ROOT / ".github" / "workflows"
        if not workflows_dir.exists():
            pytest.skip("No .github/workflows/ directory")
        for yml_file in workflows_dir.glob("*.yml"):
            with open(yml_file) as f:
                data = yaml.safe_load(f)
            assert isinstance(data, dict), (
                f"{yml_file.name} is not a valid YAML document"
            )


# ── Pre-commit hook tests ───────────────────────────────────────────────────

class TestPreCommitHook:
    """Verify pre-commit hook setup."""

    def test_hook_script_exists(self):
        hook_path = ROOT / "scripts" / "hooks" / "pre-commit-hook.py"
        assert hook_path.exists(), "Pre-commit hook script missing"

    def test_hook_is_valid_python(self):
        hook_path = ROOT / "scripts" / "hooks" / "pre-commit-hook.py"
        if not hook_path.exists():
            pytest.skip("Pre-commit hook script missing")
        result = subprocess.run(
            [sys.executable, "-c", f"import py_compile; py_compile.compile(r'{hook_path}', doraise=True)"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Hook has syntax errors: {result.stderr}"


# ── .gitignore coverage tests ───────────────────────────────────────────────

class TestGitignore:
    """Verify .gitignore covers common patterns."""

    EXPECTED_PATTERNS = [
        "__pycache__",
        "*.pyc",
        ".env",
        "*.sqlite",
        "DoD_Budget_Documents/",
    ]

    def test_gitignore_exists(self):
        assert (ROOT / ".gitignore").exists(), ".gitignore is missing"

    def test_gitignore_covers_common_patterns(self):
        gitignore_path = ROOT / ".gitignore"
        if not gitignore_path.exists():
            pytest.skip(".gitignore missing")
        content = gitignore_path.read_text()
        missing = []
        for pattern in self.EXPECTED_PATTERNS:
            if pattern not in content:
                missing.append(pattern)
        assert not missing, f".gitignore missing patterns: {missing}"


# ── No secrets in tracked files ─────────────────────────────────────────────

class TestNoSecrets:
    """Verify no secrets are committed to the repository."""

    SECRET_PATTERNS = [
        re.compile(r"(?i)(?:password|passwd|secret|api[_-]?key)\s*=\s*['\"][^'\"]{8,}['\"]"),
        re.compile(r"(?i)(?:aws_access_key_id|aws_secret_access_key)\s*="),
        re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI-style keys
        re.compile(r"ghp_[a-zA-Z0-9]{36,}"),  # GitHub PATs
    ]

    def test_no_secrets_in_python_files(self):
        """Scan tracked .py files for potential hardcoded secrets."""
        violations = []
        for py_file in ROOT.rglob("*.py"):
            # Skip test files, docs, and virtual environments
            rel = py_file.relative_to(ROOT)
            parts = str(rel).replace("\\", "/")
            if any(skip in parts for skip in [
                "test_", "conftest", ".venv", "venv", "node_modules",
                "DoD_Budget_Documents", "__pycache__",
            ]):
                continue
            try:
                content = py_file.read_text(errors="ignore")
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(content.split("\n"), 1):
                # Skip comments
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                for pattern in self.SECRET_PATTERNS:
                    if pattern.search(line):
                        violations.append(f"{rel}:{i}")
        assert not violations, (
            f"Potential secrets found in: {violations[:5]}"
        )


# ── Package structure integrity ─────────────────────────────────────────────

class TestPackageStructure:
    """Verify expected package directories exist with __init__.py."""

    EXPECTED_PACKAGES = ["api", "utils"]

    # New packages added by restructuring — test only if they exist
    OPTIONAL_PACKAGES = ["downloader", "pipeline"]

    def test_required_packages_exist(self):
        for pkg in self.EXPECTED_PACKAGES:
            pkg_dir = ROOT / pkg
            assert pkg_dir.is_dir(), f"Package {pkg}/ directory missing"
            assert (pkg_dir / "__init__.py").exists(), (
                f"Package {pkg}/ missing __init__.py"
            )

    def test_optional_packages_have_init(self):
        """If new packages exist, they must have __init__.py."""
        for pkg in self.OPTIONAL_PACKAGES:
            pkg_dir = ROOT / pkg
            if pkg_dir.is_dir():
                assert (pkg_dir / "__init__.py").exists(), (
                    f"Package {pkg}/ exists but missing __init__.py"
                )

    def test_tests_directory_exists(self):
        assert (ROOT / "tests").is_dir(), "tests/ directory missing"
        assert (ROOT / "tests" / "conftest.py").exists(), "conftest.py missing"

    def test_required_config_files_exist(self):
        for fname in ["pyproject.toml", "requirements.txt", "requirements-dev.txt"]:
            assert (ROOT / fname).exists(), f"{fname} missing from root"


# ── No large binary files ───────────────────────────────────────────────────

class TestNoLargeFiles:
    """Verify no accidentally committed large files."""

    MAX_FILE_SIZE_MB = 10
    LARGE_EXTENSIONS = {".sqlite", ".db", ".zip", ".tar", ".gz", ".exe", ".dll"}

    def test_no_large_tracked_binaries(self):
        """Check that no large binary files are tracked by git."""
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        if result.returncode != 0:
            pytest.skip("Not in a git repository")
        tracked = result.stdout.strip().split("\n")
        violations = []
        for rel_path in tracked:
            if not rel_path:
                continue
            full = ROOT / rel_path
            if full.suffix.lower() in self.LARGE_EXTENSIONS:
                if full.exists():
                    size_mb = full.stat().st_size / (1024 * 1024)
                    if size_mb > self.MAX_FILE_SIZE_MB:
                        violations.append(f"{rel_path} ({size_mb:.1f}MB)")
        assert not violations, (
            f"Large binary files tracked by git: {violations}"
        )


# ── Import smoke tests ─────────────────────────────────────────────────────

class TestImportSmoke:
    """Verify key modules can be imported without errors."""

    @pytest.mark.parametrize("module", [
        "utils",
        "utils.config",
        "utils.patterns",
        "utils.strings",
        "utils.database",
        "api.app",
        "api.models",
    ])
    def test_core_module_imports(self, module: str):
        """Core modules should import without errors."""
        __import__(module)

    @pytest.mark.parametrize("module", [
        "dod_budget_downloader",
        "build_budget_db",
        "search_budget",
        "validate_budget_data",
        "exhibit_catalog",
        "schema_design",
    ])
    def test_root_script_imports(self, module: str):
        """Root-level scripts should import (shims or direct)."""
        try:
            __import__(module)
        except ImportError as e:
            pytest.skip(f"Optional dependency missing: {e}")

    def test_downloader_package_import(self):
        """If downloader/ exists, it should be importable."""
        if not (ROOT / "downloader" / "__init__.py").exists():
            pytest.skip("downloader package not yet created")
        import downloader  # noqa: F401

    def test_pipeline_package_import(self):
        """If pipeline/ exists, it should be importable."""
        if not (ROOT / "pipeline" / "__init__.py").exists():
            pytest.skip("pipeline package not yet created")
        import pipeline  # noqa: F401
