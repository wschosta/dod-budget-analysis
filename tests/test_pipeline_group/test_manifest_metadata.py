"""
Unit tests for downloader/metadata.py detection functions.

Tests exhibit type detection, category classification, budget cycle detection,
and source-to-service mapping.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from downloader.metadata import (
    detect_exhibit_type_from_filename,
    classify_exhibit_category,
    detect_budget_cycle,
    map_source_to_service,
    enrich_file_metadata,
    SUMMARY_EXHIBIT_KEYS,
    DETAIL_EXHIBIT_KEYS,
)


# ── detect_exhibit_type_from_filename ────────────────────────────────────────

class TestDetectExhibitType:
    """Tests for detect_exhibit_type_from_filename()."""

    @pytest.mark.parametrize("filename, expected", [
        ("p1_display.xlsx", "p1"),
        ("P1_Display.xlsx", "p1"),
        ("p1r_display.xlsx", "p1r"),
        ("p5_army.xlsx", "p5"),
        ("r1_display.xlsx", "r1"),
        ("r2_display.xlsx", "r2"),
        ("r3_navy.xlsx", "r3"),
        ("r4_airforce.xlsx", "r4"),
        ("o1_display.xlsx", "o1"),
        ("m1_display.xlsx", "m1"),
        ("c1_display.xlsx", "c1"),
        ("rf1_display.xlsx", "rf1"),
    ])
    def test_known_exhibit_types(self, filename, expected):
        assert detect_exhibit_type_from_filename(filename) == expected

    def test_unknown_type(self):
        assert detect_exhibit_type_from_filename("budget_summary.xlsx") == "unknown"

    def test_pdf_extension(self):
        assert detect_exhibit_type_from_filename("r2_navy.pdf") == "r2"

    def test_p1r_before_p1(self):
        """Ensure p1r matches before p1 (longer match first)."""
        assert detect_exhibit_type_from_filename("p1r_reserves.xlsx") == "p1r"


# ── classify_exhibit_category ────────────────────────────────────────────────

class TestClassifyExhibitCategory:
    """Tests for classify_exhibit_category()."""

    @pytest.mark.parametrize("exhibit_type, expected", [
        ("p1", "summary"),
        ("r1", "summary"),
        ("o1", "summary"),
        ("m1", "summary"),
        ("c1", "summary"),
        ("rf1", "summary"),
        ("p1r", "summary"),
    ])
    def test_summary_types(self, exhibit_type, expected):
        assert classify_exhibit_category(exhibit_type) == expected

    @pytest.mark.parametrize("exhibit_type, expected", [
        ("p5", "detail"),
        ("r2", "detail"),
        ("r3", "detail"),
        ("r4", "detail"),
    ])
    def test_detail_types(self, exhibit_type, expected):
        assert classify_exhibit_category(exhibit_type) == expected

    def test_unknown_is_other(self):
        assert classify_exhibit_category("unknown") == "other"

    def test_case_insensitive(self):
        assert classify_exhibit_category("P1") == "summary"
        assert classify_exhibit_category("R2") == "detail"


# ── detect_budget_cycle ──────────────────────────────────────────────────────

class TestDetectBudgetCycle:
    """Tests for detect_budget_cycle()."""

    def test_default_is_pb(self):
        assert detect_budget_cycle("Army", "https://example.com/file.xlsx") == "pb"

    def test_enacted_in_url(self):
        assert detect_budget_cycle(
            "Army", "https://example.com/enacted/file.xlsx"
        ) == "enacted"

    def test_ndaa_in_link_text(self):
        assert detect_budget_cycle(
            "Army", "https://example.com/file.xlsx", "FY2026 NDAA"
        ) == "ndaa"

    def test_supplemental_in_url(self):
        assert detect_budget_cycle(
            "Army", "https://example.com/supplemental/file.xlsx"
        ) == "supplemental"

    def test_amendment_in_link_text(self):
        assert detect_budget_cycle(
            "Army", "", "Budget Amendment FY2026"
        ) == "amendment"

    def test_pb_keyword_in_url(self):
        assert detect_budget_cycle(
            "Army", "https://example.com/pb/2026/file.xlsx"
        ) == "pb"


# ── map_source_to_service ────────────────────────────────────────────────────

class TestMapSourceToService:
    """Tests for map_source_to_service()."""

    @pytest.mark.parametrize("source_label, expected", [
        ("US Army", "Army"),
        ("Army", "Army"),
        ("US Navy", "Navy"),
        ("Navy", "Navy"),
        ("US Air Force", "Air Force"),
        ("Air Force", "Air Force"),
        ("airforce", "Air Force"),
        ("Defense-Wide", "Defense-Wide"),
    ])
    def test_known_sources(self, source_label, expected):
        assert map_source_to_service(source_label) == expected

    def test_comptroller_with_army_prefix(self):
        """Comptroller files with 'a' prefix → Army."""
        result = map_source_to_service("Comptroller", "ap1_display.xlsx")
        assert result == "Army"

    def test_comptroller_with_navy_prefix(self):
        result = map_source_to_service("Comptroller", "np1_display.xlsx")
        assert result == "Navy"

    def test_comptroller_with_airforce_prefix(self):
        result = map_source_to_service("Comptroller", "fp1_display.xlsx")
        assert result == "Air Force"

    def test_comptroller_no_prefix(self):
        """Comptroller files without service prefix → 'Comptroller'."""
        result = map_source_to_service("Comptroller", "p1_display.xlsx")
        assert result == "Comptroller"

    def test_case_insensitive(self):
        assert map_source_to_service("us army") == "Army"

    def test_unknown_source(self):
        result = map_source_to_service("Unknown Organization")
        assert result is None


# ── enrich_file_metadata ─────────────────────────────────────────────────────

class TestEnrichFileMetadata:
    """Tests for enrich_file_metadata() convenience function."""

    def test_basic_enrichment(self):
        result = enrich_file_metadata(
            filename="p1_display.xlsx",
            url="https://example.com/pb/2026/p1_display.xlsx",
            source_label="US Army",
            link_text="P-1 Budget",
        )
        assert result["exhibit_type"] == "p1"
        assert result["exhibit_category"] == "summary"
        assert result["budget_cycle"] == "pb"
        assert result["service_org"] == "Army"
        assert result["link_text"] == "P-1 Budget"

    def test_detail_exhibit(self):
        result = enrich_file_metadata(
            filename="r2_detail.pdf",
            source_label="Navy",
        )
        assert result["exhibit_type"] == "r2"
        assert result["exhibit_category"] == "detail"
        assert result["service_org"] == "Navy"

    def test_unknown_file(self):
        result = enrich_file_metadata(
            filename="readme.txt",
            source_label="Unknown",
        )
        assert result["exhibit_type"] == "unknown"
        assert result["exhibit_category"] == "other"


# ── Constants consistency ────────────────────────────────────────────────────

class TestConstants:
    """Verify constant sets are consistent."""

    def test_summary_and_detail_disjoint(self):
        assert SUMMARY_EXHIBIT_KEYS & DETAIL_EXHIBIT_KEYS == frozenset()

    def test_summary_includes_p1(self):
        assert "p1" in SUMMARY_EXHIBIT_KEYS

    def test_detail_includes_r2(self):
        assert "r2" in DETAIL_EXHIBIT_KEYS

    def test_all_known_types_classified(self):
        """Every known exhibit type is either summary or detail."""
        all_types = SUMMARY_EXHIBIT_KEYS | DETAIL_EXHIBIT_KEYS
        expected = {"p1", "p1r", "r1", "o1", "m1", "c1", "rf1", "p5", "r2", "r3", "r4"}
        assert all_types == expected
