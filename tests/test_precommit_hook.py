"""
Tests for .pre-commit-hook.py — pre-commit hook functions

Tests syntax checking, code quality, security scanning, and file checks.
Avoids actually running optimization tests or importing full modules.
"""
import sys
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import the hook module using importlib since it starts with a dot
import importlib.util
_hook_path = Path(__file__).resolve().parent.parent / ".pre-commit-hook.py"
_spec = importlib.util.spec_from_file_location("precommit_hook", str(_hook_path))
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


class TestCheckSyntax:
    def test_valid_python(self, tmp_path, monkeypatch):
        # Create a valid Python file
        (tmp_path / "good.py").write_text("x = 1\n")
        monkeypatch.chdir(tmp_path)
        assert hook.check_syntax() is True

    def test_syntax_error(self, tmp_path, monkeypatch):
        (tmp_path / "bad.py").write_text("def broken(\n")
        monkeypatch.chdir(tmp_path)
        assert hook.check_syntax() is False

    def test_skips_test_files(self, tmp_path, monkeypatch):
        # test_ files should be skipped
        (tmp_path / "test_something.py").write_text("def broken(\n")
        (tmp_path / "good.py").write_text("x = 1\n")
        monkeypatch.chdir(tmp_path)
        assert hook.check_syntax() is True


class TestCheckCodeQuality:
    def test_no_debug_statements(self, tmp_path, monkeypatch):
        (tmp_path / "clean.py").write_text("x = 1\nprint(x)\n")
        monkeypatch.chdir(tmp_path)
        assert hook.check_code_quality() is True

    def test_breakpoint_detected(self, tmp_path, monkeypatch):
        (tmp_path / "debug.py").write_text("x = 1\nbreakpoint()\n")
        monkeypatch.chdir(tmp_path)
        assert hook.check_code_quality() is False

    def test_pdb_detected(self, tmp_path, monkeypatch):
        (tmp_path / "debug.py").write_text("import pdb\npdb.set_trace()\n")
        monkeypatch.chdir(tmp_path)
        assert hook.check_code_quality() is False


class TestCheckSecurity:
    def test_clean_code(self, tmp_path, monkeypatch):
        (tmp_path / "safe.py").write_text("x = 1\n")
        monkeypatch.chdir(tmp_path)
        assert hook.check_security() is True

    def test_hardcoded_password(self, tmp_path, monkeypatch):
        (tmp_path / "bad.py").write_text('password = "hunter2"\n')
        monkeypatch.chdir(tmp_path)
        assert hook.check_security() is False

    def test_comments_skipped(self, tmp_path, monkeypatch):
        (tmp_path / "safe.py").write_text('# password = "hunter2"\n')
        monkeypatch.chdir(tmp_path)
        assert hook.check_security() is True


class TestCheckDatabaseSchema:
    def test_no_database(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert hook.check_database_schema() is True  # Skipped

    def test_valid_database(self, tmp_path, monkeypatch):
        db_path = tmp_path / "dod_budget.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE budget_lines (id INTEGER PRIMARY KEY)")
        conn.execute("CREATE TABLE pdf_pages (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        monkeypatch.chdir(tmp_path)
        assert hook.check_database_schema() is True

    def test_missing_tables(self, tmp_path, monkeypatch):
        db_path = tmp_path / "dod_budget.sqlite"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE other_table (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        monkeypatch.chdir(tmp_path)
        assert hook.check_database_schema() is False


class TestCheckRequiredFiles:
    def test_all_present(self, tmp_path, monkeypatch):
        for f in ["requirements.txt", "README.md", ".gitignore"]:
            (tmp_path / f).write_text("content")
        monkeypatch.chdir(tmp_path)
        assert hook.check_required_files() is True

    def test_missing_file(self, tmp_path, monkeypatch):
        (tmp_path / "requirements.txt").write_text("content")
        monkeypatch.chdir(tmp_path)
        assert hook.check_required_files() is False


class TestRunOptimizationTests:
    def test_success(self):
        mock_result = MagicMock(returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            assert hook.run_optimization_tests() is True

    def test_failure(self):
        mock_result = MagicMock(returncode=1)
        with patch("subprocess.run", return_value=mock_result):
            assert hook.run_optimization_tests() is False
