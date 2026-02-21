"""
Unit tests for the shared exhibit classification constants and functions
in utils/config.py, and the download layout migration script.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from utils.config import (
    SUMMARY_EXHIBIT_KEYS,
    DETAIL_EXHIBIT_KEYS,
    classify_exhibit_category,
)
from scripts.migrate_download_layout import (
    _classify_file,
    _is_already_migrated,
    migrate_fy_directory,
    migrate_all,
    _cleanup_empty_dirs,
)


# ── classify_exhibit_category (utils/config.py) ─────────────────────────────

class TestClassifyExhibitCategory:
    """Tests for the shared classify_exhibit_category()."""

    @pytest.mark.parametrize("input_val, expected", [
        # Bare exhibit type keys
        ("p1", "summary"),
        ("r1", "summary"),
        ("o1", "summary"),
        ("m1", "summary"),
        ("c1", "summary"),
        ("rf1", "summary"),
        ("p1r", "summary"),
        ("p5", "detail"),
        ("r2", "detail"),
        ("r3", "detail"),
        ("r4", "detail"),
        # Full filenames
        ("p1_display.xlsx", "summary"),
        ("r2_navy.xlsx", "detail"),
        ("p5_army.xlsx", "detail"),
        ("r1_display.pdf", "summary"),
        ("rf1_display.xlsx", "summary"),
        # Case insensitive
        ("P1_Display.xlsx", "summary"),
        ("R2_Detail.pdf", "detail"),
        # Unknown
        ("readme.txt", "other"),
        ("budget_summary.xlsx", "other"),
        ("unknown", "other"),
    ])
    def test_classification(self, input_val, expected):
        assert classify_exhibit_category(input_val) == expected

    def test_p1r_classified_as_summary_not_detail(self):
        """p1r should be summary, not confused with r1."""
        assert classify_exhibit_category("p1r_reserves.xlsx") == "summary"

    def test_constants_disjoint(self):
        """Summary and detail sets must not overlap."""
        assert SUMMARY_EXHIBIT_KEYS & DETAIL_EXHIBIT_KEYS == frozenset()

    def test_constants_are_frozensets(self):
        assert isinstance(SUMMARY_EXHIBIT_KEYS, frozenset)
        assert isinstance(DETAIL_EXHIBIT_KEYS, frozenset)


# ── Migration script functions ───────────────────────────────────────────────

class TestClassifyFile:
    """Tests for _classify_file() in the migration script."""

    def test_summary_file(self):
        assert _classify_file("p1_display.xlsx") == "summary"

    def test_detail_file(self):
        assert _classify_file("r2_navy.xlsx") == "detail"

    def test_other_file(self):
        assert _classify_file("readme.txt") == "other"


class TestIsAlreadyMigrated:
    """Tests for _is_already_migrated()."""

    def test_old_layout(self, tmp_path):
        """Old layout (FY/source/) → not migrated."""
        fy_dir = tmp_path / "FY2026"
        (fy_dir / "Comptroller").mkdir(parents=True)
        (fy_dir / "US_Army").mkdir(parents=True)
        assert _is_already_migrated(fy_dir) is False

    def test_new_layout(self, tmp_path):
        """New layout (FY/PB/source/) → already migrated."""
        fy_dir = tmp_path / "FY2026"
        (fy_dir / "PB" / "Comptroller").mkdir(parents=True)
        assert _is_already_migrated(fy_dir) is True

    def test_mixed_layout(self, tmp_path):
        """If PB directory exists alongside old dirs, consider migrated."""
        fy_dir = tmp_path / "FY2026"
        (fy_dir / "PB").mkdir(parents=True)
        (fy_dir / "Comptroller").mkdir(parents=True)
        assert _is_already_migrated(fy_dir) is True


class TestMigrateFyDirectory:
    """Tests for migrate_fy_directory()."""

    def _setup_old_layout(self, root: Path) -> Path:
        """Create a representative old-layout FY directory."""
        fy_dir = root / "FY2026"
        comp = fy_dir / "Comptroller"
        comp.mkdir(parents=True)
        (comp / "p1_display.xlsx").write_text("summary file")
        (comp / "r2_navy.xlsx").write_text("detail file")
        (comp / "readme.txt").write_text("other file")

        army = fy_dir / "US_Army"
        army.mkdir(parents=True)
        (army / "p5_army.xlsx").write_text("detail file")
        (army / "o1_army.xlsx").write_text("summary file")

        return fy_dir

    def test_dry_run_moves_nothing(self, tmp_path):
        fy_dir = self._setup_old_layout(tmp_path)
        stats = migrate_fy_directory(fy_dir, dry_run=True)

        # Files should still be in old locations
        assert (fy_dir / "Comptroller" / "p1_display.xlsx").exists()
        assert stats["moved"] == 5
        assert stats["errors"] == 0

    def test_live_migration(self, tmp_path):
        fy_dir = self._setup_old_layout(tmp_path)
        stats = migrate_fy_directory(fy_dir, dry_run=False)

        # Old files should be gone (dirs cleaned up)
        assert not (fy_dir / "Comptroller" / "p1_display.xlsx").exists()

        # New layout should exist
        assert (fy_dir / "PB" / "Comptroller" / "summary" / "p1_display.xlsx").exists()
        assert (fy_dir / "PB" / "Comptroller" / "detail" / "r2_navy.xlsx").exists()
        assert (fy_dir / "PB" / "Comptroller" / "other" / "readme.txt").exists()
        assert (fy_dir / "PB" / "US_Army" / "detail" / "p5_army.xlsx").exists()
        assert (fy_dir / "PB" / "US_Army" / "summary" / "o1_army.xlsx").exists()

        assert stats["moved"] == 5
        assert stats["errors"] == 0

    def test_skips_existing_files(self, tmp_path):
        """Files already at the destination are skipped."""
        fy_dir = self._setup_old_layout(tmp_path)

        # Pre-create a destination file
        dest = fy_dir / "PB" / "Comptroller" / "summary" / "p1_display.xlsx"
        dest.parent.mkdir(parents=True)
        dest.write_text("already here")

        stats = migrate_fy_directory(fy_dir, dry_run=False)
        assert stats["skipped"] == 1
        assert stats["moved"] == 4

        # Pre-existing file should be untouched
        assert dest.read_text() == "already here"

    def test_custom_budget_cycle(self, tmp_path):
        """Can specify a non-default budget cycle."""
        fy_dir = tmp_path / "FY2025"
        comp = fy_dir / "Comptroller"
        comp.mkdir(parents=True)
        (comp / "p1_display.xlsx").write_text("data")

        migrate_fy_directory(fy_dir, budget_cycle="ENACTED")
        assert (fy_dir / "ENACTED" / "Comptroller" / "summary" / "p1_display.xlsx").exists()

    def test_preserves_subdirectories(self, tmp_path):
        """Files in extracted ZIP subdirectories are preserved."""
        fy_dir = tmp_path / "FY2026"
        comp = fy_dir / "Comptroller"
        subdir = comp / "extracted_zip"
        subdir.mkdir(parents=True)
        (subdir / "r2_data.xlsx").write_text("nested detail file")

        migrate_fy_directory(fy_dir, dry_run=False)
        new_path = fy_dir / "PB" / "Comptroller" / "detail" / "extracted_zip" / "r2_data.xlsx"
        assert new_path.exists()

    def test_skips_budget_cycle_dirs(self, tmp_path):
        """Should not try to migrate dirs that look like budget cycles."""
        fy_dir = tmp_path / "FY2026"
        # Create a "PB" directory (already-new layout)
        (fy_dir / "PB" / "Comptroller" / "summary").mkdir(parents=True)
        (fy_dir / "PB" / "Comptroller" / "summary" / "p1.xlsx").write_text("x")

        stats = migrate_fy_directory(fy_dir, dry_run=False)
        # Nothing should move — PB is recognized as a cycle dir and skipped
        assert stats["moved"] == 0


class TestMigrateAll:
    """Tests for migrate_all()."""

    def test_migrates_multiple_fy_dirs(self, tmp_path):
        for year in ["FY2025", "FY2026"]:
            comp = tmp_path / year / "Comptroller"
            comp.mkdir(parents=True)
            (comp / "p1_display.xlsx").write_text("data")

        totals = migrate_all(tmp_path, dry_run=False)
        assert totals["moved"] == 2
        assert (tmp_path / "FY2025" / "PB" / "Comptroller" / "summary" / "p1_display.xlsx").exists()
        assert (tmp_path / "FY2026" / "PB" / "Comptroller" / "summary" / "p1_display.xlsx").exists()

    def test_skips_already_migrated(self, tmp_path):
        """Already-migrated FY dirs are left alone."""
        fy_dir = tmp_path / "FY2026"
        (fy_dir / "PB" / "Comptroller" / "summary").mkdir(parents=True)
        (fy_dir / "PB" / "Comptroller" / "summary" / "p1.xlsx").write_text("x")

        totals = migrate_all(tmp_path, dry_run=False)
        assert totals["moved"] == 0

    def test_nonexistent_dir(self, tmp_path):
        totals = migrate_all(tmp_path / "does_not_exist")
        assert totals["moved"] == 0

    def test_no_fy_dirs(self, tmp_path):
        (tmp_path / "random_dir").mkdir()
        totals = migrate_all(tmp_path)
        assert totals["moved"] == 0


class TestCleanupEmptyDirs:
    """Tests for _cleanup_empty_dirs()."""

    def test_removes_empty_nested_dirs(self, tmp_path):
        (tmp_path / "a" / "b" / "c").mkdir(parents=True)
        removed = _cleanup_empty_dirs(tmp_path)
        assert removed == 3
        # Only root should remain
        assert tmp_path.exists()
        assert not (tmp_path / "a").exists()

    def test_keeps_dirs_with_files(self, tmp_path):
        (tmp_path / "keep" / "sub").mkdir(parents=True)
        (tmp_path / "keep" / "sub" / "file.txt").write_text("data")
        (tmp_path / "remove").mkdir()
        removed = _cleanup_empty_dirs(tmp_path)
        assert removed == 1  # Only "remove" dir
        assert (tmp_path / "keep" / "sub" / "file.txt").exists()
