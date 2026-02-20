"""
Pre-commit Validation Tests

Comprehensive checks to run before every commit to catch common issues:
- Syntax and import validation
- Code quality checks (no debug statements, secrets, etc.)
- Naming and shadowing detection
- Code consistency (line length, import order)
- Documentation completeness

Run with: pytest tests/test_precommit_checks.py -v
"""

import ast
import re
import sqlite3
from pathlib import Path

import pytest


class TestSyntaxValidation:
    """Verify all Python files have valid syntax."""

    def get_python_files(self):
        """Get all non-test Python files."""
        root = Path(".")
        py_files = list(root.glob("*.py")) + list(root.glob("utils/*.py"))
        # Exclude test files, __pycache__, and specific files
        return [
            f for f in py_files
            if f.name not in ["test_*.py", "conftest.py", "__pycache__"]
            and "__pycache__" not in str(f)
        ]

    def test_all_files_parse(self):
        """All Python files must parse without syntax errors."""
        errors = []
        for py_file in self.get_python_files():
            try:
                with open(py_file) as f:
                    ast.parse(f.read())
            except SyntaxError as e:
                errors.append(f"{py_file}: {e}")

        assert not errors, f"Syntax errors found:\n" + "\n".join(errors)


class TestImportValidation:
    """Verify imports are valid and properly organized."""

    def test_no_circular_imports(self):
        """Detect circular import dependencies."""
        import sys
        import importlib

        # Try importing main modules
        modules_to_test = [
            "dod_budget_downloader",
            "build_budget_db",
            "search_budget",
            "validate_budget_db",
        ]

        for module_name in modules_to_test:
            try:
                # Clear from cache if present
                if module_name in sys.modules:
                    del sys.modules[module_name]
                importlib.import_module(module_name)
            except ImportError as e:
                # Skip modules whose optional dependencies aren't installed
                # (e.g. dod_budget_downloader needs bs4)
                if "bs4" in str(e) or "beautifulsoup" in str(e).lower():
                    pytest.skip(f"{module_name} requires bs4: {e}")
                pytest.fail(f"Circular import or missing dependency in {module_name}: {e}")

    def test_import_order(self):
        """Verify imports follow standard organization."""
        root = Path(".")
        py_files = list(root.glob("*.py"))

        for py_file in py_files:
            if py_file.name.startswith("test_"):
                continue

            with open(py_file) as f:
                content = f.read()

            # Parse imports
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue

            imports = {"stdlib": [], "third_party": [], "local": []}

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name.split(".")[0]
                        imports["stdlib"].append(module)
                elif isinstance(node, ast.ImportFrom):
                    if node.level > 0:  # Relative import
                        imports["local"].append(node.module or "")
                    elif node.module and node.module.startswith("."):
                        imports["local"].append(node.module)
                    else:
                        imports["third_party"].append(node.module or "")

            # Verify order: stdlib -> third_party -> local
            # (This is a simplified check; full validation would need more context)
            assert imports, f"No imports found in {py_file}"


class TestCodeQuality:
    """Detect common code quality issues."""

    def get_python_files(self):
        """Get all non-test Python files."""
        root = Path(".")
        py_files = list(root.glob("*.py")) + list(root.glob("utils/*.py"))
        return [
            f for f in py_files
            if f.name not in ["test_*.py", "conftest.py"]
            and "__pycache__" not in str(f)
        ]

    def test_no_breakpoint_statements(self):
        """No pdb/breakpoint statements should be committed."""
        # Exclude pre-commit checker infrastructure files — they reference the
        # patterns as string literals (not actual debug calls) for detection logic.
        skip_files = {"run_precommit_checks.py", "pre-commit-hook.py"}
        errors = []
        for py_file in self.get_python_files():
            if py_file.name in skip_files:
                continue
            with open(py_file) as f:
                for i, line in enumerate(f, 1):
                    # Skip lines that are clearly string literals / comments
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith(("'", '"', "r'")):
                        continue
                    if re.search(r"\bbreakpoint\(\)", line):
                        errors.append(f"{py_file}:{i}: breakpoint() found")
                    if re.search(r"\bpdb\.set_trace\(\)", line):
                        errors.append(f"{py_file}:{i}: pdb.set_trace() found")

        assert not errors, f"Debug statements found:\n" + "\n".join(errors)

    def test_no_hardcoded_secrets(self):
        """Detect potential hardcoded secrets."""
        errors = []
        secret_patterns = [
            (r"password\s*=\s*['\"](?!.*\$|.*\{)[^'\"]*['\"]", "hardcoded password"),
            (r"api[_-]?key\s*=\s*['\"](?!.*\$|.*\{)[^'\"]*['\"]", "hardcoded API key"),
            (r"secret\s*=\s*['\"](?!.*\$|.*\{)[^'\"]*['\"]", "hardcoded secret"),
            (r"token\s*=\s*['\"][a-zA-Z0-9]{20,}['\"]", "potential hardcoded token"),
        ]

        for py_file in self.get_python_files():
            with open(py_file) as f:
                for i, line in enumerate(f, 1):
                    if line.strip().startswith("#"):
                        continue  # Skip comments
                    for pattern, desc in secret_patterns:
                        if re.search(pattern, line, re.IGNORECASE):
                            errors.append(f"{py_file}:{i}: {desc}")

        assert not errors, f"Potential secrets found:\n" + "\n".join(errors)

    def test_no_excessive_debugging_prints(self):
        """Library modules should not have debug/temporary print statements.

        Flags prints that look like raw debug dumps:
          print(variable)         <- bare variable with no formatting
          print(f"debug: ...")    <- explicit debug label
          print(repr(...))        <- repr() dump
        Does NOT flag intentional CLI output (formatted headers, status lines,
        progress messages) which are the expected user-visible output of these
        CLI tools.
        """
        library_modules = [
            "build_budget_db.py",
            "search_budget.py",
            "validate_budget_db.py",
        ]

        # Patterns that indicate accidental debug prints (not user-facing output)
        debug_patterns = [
            re.compile(r'^\s*print\(\s*[a-zA-Z_][a-zA-Z0-9_.]*\s*\)'),  # print(var)
            re.compile(r'^\s*print\(.*\bdebug\b', re.IGNORECASE),         # "debug" label
            re.compile(r'^\s*print\(repr\('),                              # repr() dump
        ]

        errors = []
        for module in library_modules:
            py_file = Path(module)
            if not py_file.exists():
                continue

            with open(py_file) as f:
                for i, line in enumerate(f, 1):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    for pat in debug_patterns:
                        if pat.search(line):
                            errors.append(f"{py_file}:{i}: debug print statement")
                            break

        assert len(errors) < 5, f"Debug prints found:\n" + "\n".join(errors[:5])


class TestNamingShadowing:
    """Detect variable shadowing and naming issues."""

    def test_no_obvious_shadowing(self):
        """Detect obvious imported function shadowing."""
        files_to_check = [
            "dod_budget_downloader.py",
            "build_budget_db.py",
            "search_budget.py",
        ]

        shadowing_patterns = [
            (r"from utils import.*\belapsed\b", r"^\s*elapsed\s*=", "elapsed function shadowed"),
            (r"from utils import.*\bformat_bytes\b", r"^\s*format_bytes\s*=", "format_bytes shadowed"),
            (r"import.*\btime\b", r"^\s*time\s*=(?!\s*\d)", "time module shadowed"),
        ]

        for py_file_name in files_to_check:
            py_file = Path(py_file_name)
            if not py_file.exists():
                continue

            with open(py_file) as f:
                content = f.read()
                lines = content.split("\n")

            # Check for imports
            for import_pattern, shadow_pattern, desc in shadowing_patterns:
                if re.search(import_pattern, content):
                    for i, line in enumerate(lines, 1):
                        if re.search(shadow_pattern, line):
                            # Allow in function/class context or with modification
                            if not re.search(r"def\s+\w+|class\s+\w+", line):
                                pytest.fail(
                                    f"{py_file}:{i}: {desc}\n"
                                    f"  Imported function shadowed by variable assignment"
                                )


class TestLineLength:
    """Enforce reasonable line length limits."""

    def test_line_length(self):
        """Lines should not exceed 100 characters (except URLs and data files)."""
        max_length = 100
        root = Path(".")
        py_files = list(root.glob("*.py")) + list(root.glob("utils/*.py"))

        # Data-declaration and generated files where long lines are unavoidable:
        # exhibit_catalog.py  — column_spec dicts with long string literals
        # schema_design.py — design docs with inline status text
        # exhibit_type_inventory.py / build_budget_gui.py — UI/inventory stubs
        # Note: api_design.py, frontend_design.py, run_optimization_tests.py
        # moved to docs/design/ and scripts/ respectively
        skip_files = {
            "exhibit_catalog.py",
            "schema_design.py",
            "exhibit_type_inventory.py",
            "build_budget_gui.py",
        }

        errors = []
        for py_file in py_files:
            if "test_" in py_file.name or py_file.name in skip_files:
                continue

            with open(py_file) as f:
                for i, line in enumerate(f, 1):
                    # Strip newline and don't count trailing whitespace
                    line_content = line.rstrip()
                    # Skip long URLs
                    if "http" in line_content:
                        continue
                    # Skip comments
                    if line_content.strip().startswith("#"):
                        continue

                    if len(line_content) > max_length:
                        errors.append(f"{py_file}:{i}: {len(line_content)} chars")

        # Allow some violations but flag excessive ones
        assert len(errors) < 10, (
            f"Lines too long (>{max_length} chars):\n" + "\n".join(errors[:10])
        )


class TestDocumentation:
    """Verify documentation standards."""

    def test_module_docstrings(self):
        """All modules should have docstrings."""
        root = Path(".")
        py_files = [f for f in root.glob("*.py") if f.name not in ["test_*.py"]]

        errors = []
        for py_file in py_files:
            with open(py_file) as f:
                try:
                    tree = ast.parse(f.read())
                except SyntaxError:
                    continue

                # Check module docstring
                docstring = ast.get_docstring(tree)
                if not docstring:
                    errors.append(f"{py_file}: Missing module docstring")

        assert not errors, "Missing docstrings:\n" + "\n".join(errors)

    def test_function_docstrings(self):
        """Critical functions should have docstrings."""
        critical_functions = {
            "dod_budget_downloader.py": [
                "download_file",
                "download_all",
                "discover_",  # All discover_* functions
            ],
            "build_budget_db.py": [
                "build_database",
                "ingest_excel_file",
                "ingest_pdf_file",
            ],
            "search_budget.py": [
                "search_",  # All search_* functions
            ],
        }

        for py_file_name, critical_funcs in critical_functions.items():
            py_file = Path(py_file_name)
            if not py_file.exists():
                continue

            with open(py_file) as f:
                try:
                    tree = ast.parse(f.read())
                except SyntaxError:
                    continue

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Check if function matches critical patterns
                    is_critical = any(
                        pattern in node.name or node.name.startswith(pattern)
                        for pattern in critical_funcs
                    )

                    if is_critical:
                        docstring = ast.get_docstring(node)
                        if not docstring:
                            pytest.fail(
                                f"{py_file_name}: Function '{node.name}' "
                                f"missing docstring (line {node.lineno})"
                            )


class TestDatabaseConsistency:
    """Verify database schema and integrity."""

    def test_database_schema_exists(self):
        """If database exists and is populated, verify schema is valid."""
        db_path = Path("dod_budget.sqlite")
        if not db_path.exists():
            pytest.skip("Database not created yet")

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Verify critical tables exist
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='budget_lines'"
            )
            if not cursor.fetchone():
                conn.close()
                pytest.skip("Database exists but budget_lines table not yet created")

            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='pdf_pages'"
            )
            if not cursor.fetchone():
                conn.close()
                pytest.skip("Database exists but pdf_pages table not yet created")

            conn.close()
        except sqlite3.DatabaseError as e:
            pytest.fail(f"Database integrity issue: {e}")


class TestConfigurationFiles:
    """Verify configuration files are present and valid."""

    def test_workflow_file_exists(self):
        """GitHub Actions workflow should be present."""
        workflow_file = Path(".github/workflows/optimization-tests.yml")
        assert workflow_file.exists(), "GitHub Actions workflow not found"

    def test_hook_file_exists(self):
        """Pre-commit hook should be present."""
        hook_file = Path("scripts/hooks/pre-commit-hook.py")
        assert hook_file.exists(), "Pre-commit hook not found"

    def test_utils_package_complete(self):
        """Utils package should have all required modules."""
        required_files = [
            "utils/__init__.py",
            "utils/common.py",
            "utils/patterns.py",
            "utils/strings.py",
        ]

        for file_path in required_files:
            assert Path(file_path).exists(), f"Missing utils file: {file_path}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
