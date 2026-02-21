"""
Tests for downloader.core.deduplicate_across_sources().

Covers cross-source dedup (Pass 1), disk-based dedup (Pass 2),
case insensitivity, per-year isolation, mutation semantics, and stats.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import copy
from unittest.mock import patch

import pytest

from downloader.core import deduplicate_across_sources


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file(name: str, url: str = "", link_text: str = "") -> dict:
    """Build a minimal file dict suitable for deduplicate_across_sources."""
    return {"filename": name, "url": url, "name": link_text}


# ---------------------------------------------------------------------------
# Pass 1: cross-source dedup within discovery results
# ---------------------------------------------------------------------------


class TestCrossSourceDedup:
    """Tests for Pass 1 — in-memory cross-source deduplication."""

    def test_no_duplicates(self):
        """Different filenames across sources should all be kept."""
        all_files = {
            "2026": {
                "navy": [_file("APN_BA1.pdf")],
                "navy-archive": [_file("WPN_BA2.pdf")],
            }
        }
        stats = deduplicate_across_sources(all_files)

        assert stats == {"removed": 0, "disk_dedup": 0}
        assert len(all_files["2026"]["navy"]) == 1
        assert len(all_files["2026"]["navy-archive"]) == 1

    def test_duplicate_removed_from_second_source(self):
        """Same filename in two sources — first source wins, second is dropped."""
        all_files = {
            "2026": {
                "navy": [_file("APN_BA1-4_Book.pdf")],
                "navy-archive": [_file("APN_BA1-4_Book.pdf")],
            }
        }
        stats = deduplicate_across_sources(all_files)

        assert stats["removed"] == 1
        assert len(all_files["2026"]["navy"]) == 1
        assert len(all_files["2026"]["navy-archive"]) == 0

    def test_case_insensitive(self):
        """'File.pdf' and 'file.pdf' should be treated as duplicates."""
        all_files = {
            "2026": {
                "source_a": [_file("Report.PDF")],
                "source_b": [_file("report.pdf")],
            }
        }
        stats = deduplicate_across_sources(all_files)

        assert stats["removed"] == 1
        assert len(all_files["2026"]["source_a"]) == 1
        assert len(all_files["2026"]["source_b"]) == 0

    def test_multiple_duplicates_in_one_source(self):
        """Multiple files in second source that collide with first source."""
        all_files = {
            "2025": {
                "army": [_file("a.xlsx"), _file("b.xlsx")],
                "comptroller": [_file("a.xlsx"), _file("b.xlsx"), _file("c.xlsx")],
            }
        }
        stats = deduplicate_across_sources(all_files)

        assert stats["removed"] == 2
        assert len(all_files["2025"]["army"]) == 2
        # comptroller keeps only c.xlsx
        assert len(all_files["2025"]["comptroller"]) == 1
        assert all_files["2025"]["comptroller"][0]["filename"] == "c.xlsx"

    def test_three_sources_first_wins(self):
        """With three sources, only the first occurrence is kept."""
        all_files = {
            "2026": {
                "alpha": [_file("shared.pdf")],
                "beta": [_file("shared.pdf")],
                "gamma": [_file("shared.pdf")],
            }
        }
        stats = deduplicate_across_sources(all_files)

        assert stats["removed"] == 2
        assert len(all_files["2026"]["alpha"]) == 1
        assert len(all_files["2026"]["beta"]) == 0
        assert len(all_files["2026"]["gamma"]) == 0


class TestPerYearIsolation:
    """Dedup is per-year — the same filename in different FYs is NOT a dup."""

    def test_same_filename_different_years_kept(self):
        all_files = {
            "2025": {
                "navy": [_file("APN_BA1.pdf")],
            },
            "2026": {
                "navy-archive": [_file("APN_BA1.pdf")],
            },
        }
        stats = deduplicate_across_sources(all_files)

        assert stats["removed"] == 0
        assert len(all_files["2025"]["navy"]) == 1
        assert len(all_files["2026"]["navy-archive"]) == 1


# ---------------------------------------------------------------------------
# Pass 2: disk-based dedup
# ---------------------------------------------------------------------------


class TestDiskDedup:
    """Tests for Pass 2 — disk-based cross-source deduplication."""

    def _create_disk_file(self, tmp_path: Path, year: str, budget_cycle: str,
                          source_label: str, exhibit_cat: str, filename: str):
        """Create a file on disk at the expected directory structure."""
        safe_label = source_label.replace(" ", "_")
        dest = tmp_path / f"FY{year}" / budget_cycle / safe_label / exhibit_cat / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("content")
        return dest

    @patch("downloader.core.detect_budget_cycle", return_value="pb")
    @patch("downloader.core.classify_exhibit_category", return_value="other")
    def test_disk_dedup_removes_cross_source_file(
        self, mock_classify, mock_cycle, tmp_path
    ):
        """File exists on disk under a different source -> removed from discovery."""
        # Put a file on disk under "navy" source
        self._create_disk_file(tmp_path, "2026", "PB", "navy", "other", "APN_BA1.pdf")

        # Discovery has the same file under "navy-archive"
        all_files = {
            "2026": {
                "navy-archive": [_file("APN_BA1.pdf")],
            }
        }
        stats = deduplicate_across_sources(all_files, output_dir=tmp_path)

        assert stats["disk_dedup"] == 1
        assert len(all_files["2026"]["navy-archive"]) == 0

    @patch("downloader.core.detect_budget_cycle", return_value="pb")
    @patch("downloader.core.classify_exhibit_category", return_value="other")
    def test_disk_dedup_keeps_own_source(
        self, mock_classify, mock_cycle, tmp_path
    ):
        """File exists on disk under THIS source -> kept (not a cross-source dup)."""
        # Put a file on disk under "navy-archive" source (same source as discovery)
        self._create_disk_file(
            tmp_path, "2026", "PB", "navy-archive", "other", "APN_BA1.pdf"
        )

        all_files = {
            "2026": {
                "navy-archive": [_file("APN_BA1.pdf")],
            }
        }
        stats = deduplicate_across_sources(all_files, output_dir=tmp_path)

        assert stats["disk_dedup"] == 0
        assert len(all_files["2026"]["navy-archive"]) == 1

    @patch("downloader.core.detect_budget_cycle", return_value="pb")
    @patch("downloader.core.classify_exhibit_category", return_value="other")
    def test_disk_dedup_no_fy_dir(self, mock_classify, mock_cycle, tmp_path):
        """If the FY directory does not exist on disk, Pass 2 is a no-op."""
        # Do NOT create FY2026 dir on disk
        all_files = {
            "2026": {
                "navy": [_file("APN_BA1.pdf")],
            }
        }
        stats = deduplicate_across_sources(all_files, output_dir=tmp_path)

        assert stats["disk_dedup"] == 0
        assert len(all_files["2026"]["navy"]) == 1

    @patch("downloader.core.detect_budget_cycle", return_value="pb")
    @patch("downloader.core.classify_exhibit_category", return_value="other")
    def test_disk_dedup_case_insensitive(
        self, mock_classify, mock_cycle, tmp_path
    ):
        """Disk dedup is case-insensitive on filenames."""
        # Put uppercase filename on disk under "army"
        self._create_disk_file(tmp_path, "2025", "PB", "army", "other", "REPORT.PDF")

        # Discovery has lowercase under a different source
        all_files = {
            "2025": {
                "comptroller": [_file("report.pdf")],
            }
        }
        stats = deduplicate_across_sources(all_files, output_dir=tmp_path)

        assert stats["disk_dedup"] == 1
        assert len(all_files["2025"]["comptroller"]) == 0

    @patch("downloader.core.detect_budget_cycle", return_value="pb")
    @patch("downloader.core.classify_exhibit_category", return_value="other")
    def test_disk_dedup_new_file_kept(
        self, mock_classify, mock_cycle, tmp_path
    ):
        """A file NOT on disk at all should be kept."""
        # Create the FY dir but no matching files
        (tmp_path / "FY2026").mkdir(parents=True)

        all_files = {
            "2026": {
                "navy": [_file("brand_new.pdf")],
            }
        }
        stats = deduplicate_across_sources(all_files, output_dir=tmp_path)

        assert stats["disk_dedup"] == 0
        assert len(all_files["2026"]["navy"]) == 1


# ---------------------------------------------------------------------------
# Combined Pass 1 + Pass 2
# ---------------------------------------------------------------------------


class TestCombinedPasses:
    """Tests where both Pass 1 and Pass 2 dedup fire."""

    @patch("downloader.core.detect_budget_cycle", return_value="pb")
    @patch("downloader.core.classify_exhibit_category", return_value="other")
    def test_both_passes_combined(self, mock_classify, mock_cycle, tmp_path):
        """Pass 1 removes in-memory dups, Pass 2 removes disk dups."""
        # Put a file on disk under "army" source
        dest = tmp_path / "FY2026" / "PB" / "army" / "other" / "on_disk.pdf"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("content")

        all_files = {
            "2026": {
                "army": [_file("shared.pdf"), _file("unique_army.pdf")],
                "navy": [
                    _file("shared.pdf"),  # dup of army (Pass 1)
                    _file("on_disk.pdf"),  # exists on disk under army (Pass 2)
                    _file("unique_navy.pdf"),
                ],
            }
        }
        stats = deduplicate_across_sources(all_files, output_dir=tmp_path)

        assert stats["removed"] == 1  # shared.pdf removed from navy in Pass 1
        assert stats["disk_dedup"] == 1  # on_disk.pdf removed from navy in Pass 2
        assert len(all_files["2026"]["army"]) == 2
        # navy should only have unique_navy.pdf
        assert len(all_files["2026"]["navy"]) == 1
        assert all_files["2026"]["navy"][0]["filename"] == "unique_navy.pdf"


# ---------------------------------------------------------------------------
# Return stats
# ---------------------------------------------------------------------------


class TestReturnStats:
    """Verify the returned stats dict has the correct counts."""

    def test_stats_keys(self):
        """Stats dict always has 'removed' and 'disk_dedup' keys."""
        stats = deduplicate_across_sources({})
        assert "removed" in stats
        assert "disk_dedup" in stats

    def test_stats_zero_when_no_work(self):
        all_files = {
            "2026": {
                "army": [_file("a.pdf")],
                "navy": [_file("b.pdf")],
            }
        }
        stats = deduplicate_across_sources(all_files)
        assert stats == {"removed": 0, "disk_dedup": 0}

    def test_stats_count_accuracy(self):
        """Three duplicates should give removed == 3."""
        all_files = {
            "2026": {
                "src1": [_file("a.pdf"), _file("b.pdf")],
                "src2": [_file("a.pdf"), _file("b.pdf")],
                "src3": [_file("a.pdf")],
            }
        }
        stats = deduplicate_across_sources(all_files)
        assert stats["removed"] == 3  # a.pdf x2, b.pdf x1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_all_files(self):
        """Empty input dict should not crash and return zero stats."""
        stats = deduplicate_across_sources({})
        assert stats == {"removed": 0, "disk_dedup": 0}

    def test_empty_sources_for_year(self):
        """Year with no sources should not crash."""
        all_files = {"2026": {}}
        stats = deduplicate_across_sources(all_files)
        assert stats == {"removed": 0, "disk_dedup": 0}

    def test_empty_file_list_for_source(self):
        """Source with empty file list should not crash."""
        all_files = {"2026": {"navy": []}}
        stats = deduplicate_across_sources(all_files)
        assert stats == {"removed": 0, "disk_dedup": 0}

    def test_single_source_no_dedup(self):
        """A single source should never have cross-source dups."""
        all_files = {
            "2026": {
                "army": [_file("a.pdf"), _file("b.pdf"), _file("c.pdf")],
            }
        }
        stats = deduplicate_across_sources(all_files)
        assert stats["removed"] == 0
        assert len(all_files["2026"]["army"]) == 3


# ---------------------------------------------------------------------------
# Mutation semantics
# ---------------------------------------------------------------------------


class TestMutatesInPlace:
    """Verify the function mutates the input dict rather than returning a copy."""

    def test_input_dict_is_mutated(self):
        """The original dict should be modified after dedup."""
        all_files = {
            "2026": {
                "navy": [_file("dup.pdf")],
                "navy-archive": [_file("dup.pdf")],
            }
        }
        original_ref = all_files
        deduplicate_across_sources(all_files)

        # Same object reference
        assert all_files is original_ref
        # But its contents are changed
        assert len(all_files["2026"]["navy-archive"]) == 0

    def test_unrelated_sources_unchanged(self):
        """Sources with no dups should keep their file lists intact."""
        all_files = {
            "2026": {
                "navy": [_file("dup.pdf"), _file("unique_navy.pdf")],
                "navy-archive": [_file("dup.pdf")],
                "army": [_file("army_only.pdf")],
            }
        }
        before_army = copy.deepcopy(all_files["2026"]["army"])
        deduplicate_across_sources(all_files)

        assert all_files["2026"]["army"] == before_army
        assert len(all_files["2026"]["navy"]) == 2  # navy keeps both


# ---------------------------------------------------------------------------
# Output_dir=None (default) — Pass 2 skipped
# ---------------------------------------------------------------------------


class TestOutputDirNone:
    """When output_dir is None, Pass 2 (disk dedup) should be completely skipped."""

    def test_no_disk_dedup_without_output_dir(self):
        """disk_dedup should stay 0 even if there could be disk dups."""
        all_files = {
            "2026": {
                "navy": [_file("APN_BA1.pdf")],
            }
        }
        stats = deduplicate_across_sources(all_files, output_dir=None)
        assert stats["disk_dedup"] == 0
