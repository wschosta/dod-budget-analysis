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
        # ── Tier 1: Bare exhibit type keys ──
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
        # ── Tier 1: Full filenames with exhibit codes ──
        ("p1_display.xlsx", "summary"),
        ("r2_navy.xlsx", "detail"),
        ("p5_army.xlsx", "detail"),
        ("r1_display.pdf", "summary"),
        ("rf1_display.xlsx", "summary"),
        # ── Tier 1: Case insensitive ──
        ("P1_Display.xlsx", "summary"),
        ("R2_Detail.pdf", "detail"),
        # ── Tier 2: Procurement → detail ──
        ("aircraft.pdf", "detail"),
        ("acft_army.pdf", "detail"),
        ("acft_fy_2022_pb_aircraft_procurement_army.pdf", "detail"),
        ("missiles.pdf", "detail"),
        ("msls_army.pdf", "detail"),
        ("missle.pdf", "detail"),
        ("ammo.pdf", "detail"),
        ("ammunition.pdf", "detail"),
        ("wtcv.pdf", "detail"),
        ("weapons and tracked combat vehicles.pdf", "detail"),
        ("opa1.pdf", "detail"),
        ("opa2.pdf", "detail"),
        ("opa34.pdf", "detail"),
        ("opa_ba_1_fy_2022_pb_other_procurement.pdf", "detail"),
        ("opn_ba1_book.pdf", "detail"),
        ("apn_ba5_book.pdf", "detail"),
        ("scn_book.pdf", "detail"),
        ("panmc_book.pdf", "detail"),
        ("pmc_book.pdf", "detail"),
        ("fy26 air force aircraft procurement vol i.pdf", "detail"),
        ("fy26 air force missile procurement.pdf", "detail"),
        ("sup-pf-opa1.pdf", "detail"),
        ("shipbuilding plan.pdf", "detail"),
        # ── Tier 2: O&M → summary ──
        ("oma-v1.pdf", "summary"),
        ("oma-v2.pdf", "summary"),
        ("oma_vol_1.pdf", "summary"),
        ("omar.pdf", "summary"),
        ("omar_vol_1_fy_2022_pb.pdf", "summary"),
        ("omng.pdf", "summary"),
        ("omng_vol_1.pdf", "summary"),
        ("omnr_book.pdf", "summary"),
        ("ommc_book.pdf", "summary"),
        ("ommc_vol2_book.pdf", "summary"),
        ("ommcr_book.pdf", "summary"),
        ("omn_book.pdf", "summary"),
        ("awcf.pdf", "summary"),
        ("awcf_fy_2022_pb.pdf", "summary"),
        ("nwcf_book.pdf", "summary"),
        ("afwcf 22pb congressional.pdf", "summary"),
        ("army working capital fund.pdf", "summary"),
        ("fy26 air force operations and maintenance vol i.pdf", "summary"),
        ("fy26 air force working capital fund.pdf", "summary"),
        ("CAAF_OP-5.pdf", "summary"),
        ("OIG_OP-5.pdf", "summary"),
        ("op-32a_summary_exhibit.pdf", "summary"),
        ("oco-oma.pdf", "summary"),
        # ── Tier 2: Military Personnel → summary ──
        ("mpa.pdf", "summary"),
        ("mpa_fy_2022.pdf", "summary"),
        ("ngpa.pdf", "summary"),
        ("rpa.pdf", "summary"),
        ("mpn_book.pdf", "summary"),
        ("mpmc_book.pdf", "summary"),
        ("rpmc_book.pdf", "summary"),
        ("rpn_book.pdf", "summary"),
        ("mpaf_fy22.pdf", "summary"),
        ("fy26 air force milpers.pdf", "summary"),
        ("military personnel army volume 1.pdf", "summary"),
        ("reserve personnel army volume 1.pdf", "summary"),
        ("national guard personnel army volume 1.pdf", "summary"),
        # ── Tier 2: MILCON → detail ──
        ("mca.pdf", "detail"),
        ("mca-afh-hoa.pdf", "detail"),
        ("mcar.pdf", "detail"),
        ("mcar_fy_2022_pb.pdf", "detail"),
        ("mcng.pdf", "detail"),
        ("mcon_book.pdf", "detail"),
        ("fy26 air force milcon.pdf", "detail"),
        ("military construction defense-wide.pdf", "detail"),
        ("brac_book.pdf", "detail"),
        ("brac2005.pdf", "detail"),
        ("brac95.pdf", "detail"),
        ("brac_fy_2022_pb.pdf", "detail"),
        ("base realignment and closure account.pdf", "detail"),
        ("family housing.pdf", "detail"),
        ("afh.pdf", "detail"),
        ("fh.pdf", "detail"),
        ("hoa.pdf", "detail"),
        ("nsip_cover_page.pdf", "detail"),
        # ── Tier 2: RDT&E → detail ──
        ("rdte_ba_1_fy_2022_pb.pdf", "detail"),
        ("rdten_ba1-3_book.pdf", "detail"),
        ("fy26 space force research and development test and evaluation.pdf", "detail"),
        ("vol1.pdf", "detail"),
        ("vol_1-budget_activity_1.pdf", "detail"),
        ("vol5a.pdf", "detail"),
        ("volume_2.pdf", "detail"),
        # ── Tier 2: Defense-Wide Procurement → detail ──
        ("PROC_CBDP_PB_2026.pdf", "detail"),
        ("PROC_SOCOM_PB_2025.pdf", "detail"),
        ("PROC_DLA_PB_2026.pdf", "detail"),
        ("PROC_MDA_VOL2B_PB_2026.pdf", "detail"),
        ("PB_2026_PDW_VOL_1.pdf", "detail"),
        # Multi-year procurement
        ("CH53K_NAVY_MYP_1-4.pdf", "detail"),
        ("GMLRS_ARMY_MYP_1-4.pdf", "detail"),
        ("AMRAAM_AIR_FORCE_MYP_1.pdf", "detail"),
        # ── Tier 2: Defense-Wide O&M → summary ──
        ("OM_Volume1_Part1.pdf", "summary"),
        ("OM_Volume1_Part_2.pdf", "summary"),
        ("PB-15.pdf", "summary"),
        ("PB-24.pdf", "summary"),
        ("PB-28.pdf", "summary"),
        ("PB-31Q.pdf", "summary"),
        ("PB-61.pdf", "summary"),
        ("ENV-30.pdf", "summary"),
        ("PB_2026_DWWCF_Operating_and_Capital_Budget_Estimates.pdf", "summary"),
        ("DoD_Revolving_Funds_J-Book_FY2026.pdf", "summary"),
        ("DeCA_PB26_J-Book.pdf", "summary"),
        ("00-DHP_Vols_I_and_II_PB26.pdf", "summary"),
        ("Service_Support.pdf", "summary"),
        ("FY2026_OM_Overview.pdf", "summary"),
        # ── Tier 2: Defense-Wide MILCON → detail ──
        ("Military_Construction_Defense-Wide_Consolidated.pdf", "detail"),
        ("FY2026_BRAC_Overview.pdf", "detail"),
        ("PB_26_DW_FH_FHIF.pdf", "detail"),
        ("fy26_NATO_Security_Investment_Program.pdf", "detail"),
        # ── Should remain "other" ──
        ("readme.txt", "other"),
        ("budget_summary.xlsx", "other"),
        ("unknown", "other"),
        ("overview.pdf", "other"),
        ("pbhl.pdf", "other"),
        ("1-cover.pdf", "other"),
        ("green_book.pdf", "other"),
        ("2-Table_of_Contents.pdf", "other"),
        ("3-Total_State_Listing.pdf", "other"),
        ("FY2026_Budget_Request.pdf", "other"),
        ("FY2026_PPBE_Reform_Activities.pdf", "other"),
    ])
    def test_classification(self, input_val, expected):
        assert classify_exhibit_category(input_val) == expected

    def test_p1r_classified_as_summary_not_detail(self):
        """p1r should be summary, not confused with r1."""
        assert classify_exhibit_category("p1r_reserves.xlsx") == "summary"

    def test_exhibit_type_takes_priority_over_appropriation(self):
        """Tier 1 exhibit codes should take priority over Tier 2 patterns.

        A file like 'r2_procurement_detail.pdf' has both 'r2' (exhibit code)
        and 'procurement' (appropriation pattern). The exhibit code should win.
        """
        # Both should be detail, but for different reasons
        assert classify_exhibit_category("r2_procurement_detail.pdf") == "detail"
        # p1 is summary even though 'procurement' pattern would suggest detail
        assert classify_exhibit_category("p1_procurement.xlsx") == "summary"

    def test_abbreviations_followed_by_underscore(self):
        """Abbreviations like apn_, scn_, mcon_ should be recognized.

        Regression test: \b word boundaries fail between abbreviations and
        underscores because _ is a word character in regex.
        """
        assert classify_exhibit_category("apn_ba5_book.pdf") == "detail"
        assert classify_exhibit_category("scn_book.pdf") == "detail"
        assert classify_exhibit_category("mcon_book.pdf") == "detail"
        assert classify_exhibit_category("mpmc_book.pdf") == "summary"
        assert classify_exhibit_category("nwcf_book.pdf") == "summary"

    def test_abbreviations_followed_by_digits(self):
        """Abbreviations like brac2005 should be recognized.

        Regression test: \b fails between abbreviation and digit.
        """
        assert classify_exhibit_category("brac2005.pdf") == "detail"
        assert classify_exhibit_category("brac95.pdf") == "detail"
        assert classify_exhibit_category("opa34.pdf") == "detail"

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

    def test_appropriation_based_classification(self, tmp_path):
        """Files with descriptive names should be classified by appropriation type."""
        fy_dir = tmp_path / "FY2026"
        army = fy_dir / "US_Army"
        army.mkdir(parents=True)
        # Procurement files → detail
        (army / "aircraft.pdf").write_text("procurement")
        (army / "missiles.pdf").write_text("procurement")
        (army / "ammo.pdf").write_text("procurement")
        (army / "wtcv.pdf").write_text("procurement")
        # O&M files → summary
        (army / "oma-v1.pdf").write_text("om")
        (army / "omar.pdf").write_text("om")
        (army / "awcf.pdf").write_text("om")
        # Milpers files → summary
        (army / "mpa.pdf").write_text("milpers")
        # MILCON files → detail
        (army / "mcar.pdf").write_text("milcon")
        # RDT&E files → detail
        (army / "vol1.pdf").write_text("rdte")
        # Other
        (army / "overview.pdf").write_text("other")

        stats = migrate_fy_directory(fy_dir, dry_run=False)
        assert stats["moved"] == 11
        assert stats["errors"] == 0

        # Verify procurement → detail
        assert (fy_dir / "PB" / "US_Army" / "detail" / "aircraft.pdf").exists()
        assert (fy_dir / "PB" / "US_Army" / "detail" / "missiles.pdf").exists()
        assert (fy_dir / "PB" / "US_Army" / "detail" / "ammo.pdf").exists()
        assert (fy_dir / "PB" / "US_Army" / "detail" / "wtcv.pdf").exists()
        # O&M → summary
        assert (fy_dir / "PB" / "US_Army" / "summary" / "oma-v1.pdf").exists()
        assert (fy_dir / "PB" / "US_Army" / "summary" / "omar.pdf").exists()
        assert (fy_dir / "PB" / "US_Army" / "summary" / "awcf.pdf").exists()
        # Milpers → summary
        assert (fy_dir / "PB" / "US_Army" / "summary" / "mpa.pdf").exists()
        # MILCON → detail
        assert (fy_dir / "PB" / "US_Army" / "detail" / "mcar.pdf").exists()
        # RDT&E → detail
        assert (fy_dir / "PB" / "US_Army" / "detail" / "vol1.pdf").exists()
        # Other
        assert (fy_dir / "PB" / "US_Army" / "other" / "overview.pdf").exists()

    def test_navy_book_classification(self, tmp_path):
        """Navy _book.pdf files should be properly classified."""
        fy_dir = tmp_path / "FY2026"
        navy = fy_dir / "US_Navy"
        navy.mkdir(parents=True)
        (navy / "apn_ba5_book.pdf").write_text("procurement")
        (navy / "opn_ba1_book.pdf").write_text("procurement")
        (navy / "scn_book.pdf").write_text("procurement")
        (navy / "mpn_book.pdf").write_text("milpers")
        (navy / "ommc_book.pdf").write_text("om")
        (navy / "nwcf_book.pdf").write_text("om")
        (navy / "mcon_book.pdf").write_text("milcon")
        (navy / "rdten_ba4_book.pdf").write_text("rdte")

        stats = migrate_fy_directory(fy_dir, dry_run=False)
        assert stats["moved"] == 8
        assert stats["errors"] == 0

        assert (fy_dir / "PB" / "US_Navy" / "detail" / "apn_ba5_book.pdf").exists()
        assert (fy_dir / "PB" / "US_Navy" / "detail" / "opn_ba1_book.pdf").exists()
        assert (fy_dir / "PB" / "US_Navy" / "detail" / "scn_book.pdf").exists()
        assert (fy_dir / "PB" / "US_Navy" / "summary" / "mpn_book.pdf").exists()
        assert (fy_dir / "PB" / "US_Navy" / "summary" / "ommc_book.pdf").exists()
        assert (fy_dir / "PB" / "US_Navy" / "summary" / "nwcf_book.pdf").exists()
        assert (fy_dir / "PB" / "US_Navy" / "detail" / "mcon_book.pdf").exists()
        assert (fy_dir / "PB" / "US_Navy" / "detail" / "rdten_ba4_book.pdf").exists()


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


# ── Navy appropriation → exhibit type detection (builder.py) ─────────────────

class TestNavyExhibitTypeDetection:
    """Tests for Navy appropriation abbreviation → exhibit type mapping.

    Navy documents use abbreviation-based filenames (APN, RDTEN, OMN, etc.)
    instead of standard exhibit codes (p1, r2, m1).  The three-tier detection
    strategy maps these to the correct exhibit types.
    """

    @pytest.fixture(autouse=True)
    def _import_detect(self):
        from pipeline.builder import (
            _detect_exhibit_type,
            _detect_pdf_exhibit_type,
            NAVY_APPROPRIATION_TO_EXHIBIT,
        )
        self._detect = _detect_exhibit_type
        self._detect_pdf = _detect_pdf_exhibit_type
        self._mapping = NAVY_APPROPRIATION_TO_EXHIBIT

    # ── Procurement → p5 ──

    @pytest.mark.parametrize("filename", [
        "APN_BA1-4_Book.pdf", "APN_BA5_Book.pdf", "APN_BA6-7_Book.pdf",
        "apn_ba1-4_book.xlsx",
    ])
    def test_apn_maps_to_p5(self, filename):
        assert self._detect(filename) == "p5"

    @pytest.mark.parametrize("filename", [
        "WPN_Book.pdf", "wpn_book.xlsx",
    ])
    def test_wpn_maps_to_p5(self, filename):
        assert self._detect(filename) == "p5"

    @pytest.mark.parametrize("filename", [
        "SCN_Book.pdf", "scn_book.xlsx",
    ])
    def test_scn_maps_to_p5(self, filename):
        assert self._detect(filename) == "p5"

    @pytest.mark.parametrize("filename", [
        "OPN_BA1_Book.pdf", "OPN_BA2_Book.pdf", "OPN_BA3_Book.pdf",
        "OPN_BA4_Book.pdf", "OPN_BA5-8_Book.pdf",
    ])
    def test_opn_maps_to_p5(self, filename):
        assert self._detect(filename) == "p5"

    def test_pmc_maps_to_p5(self):
        assert self._detect("PMC_Book.pdf") == "p5"

    def test_panmc_maps_to_p5(self):
        assert self._detect("PANMC_Book.pdf") == "p5"

    # ── O&M → o1 ──

    @pytest.mark.parametrize("filename", [
        "OMN_Book.pdf", "OMN_Vol2_Book.pdf", "omn_book.xlsx",
    ])
    def test_omn_maps_to_o1(self, filename):
        assert self._detect(filename) == "o1"

    @pytest.mark.parametrize("filename", [
        "OMMC_Book.pdf", "OMMC_Vol2_Book.pdf",
    ])
    def test_ommc_maps_to_o1(self, filename):
        assert self._detect(filename) == "o1"

    def test_omnr_maps_to_o1(self):
        assert self._detect("OMNR_Book.pdf") == "o1"

    def test_ommcr_maps_to_o1(self):
        assert self._detect("OMMCR_Book.pdf") == "o1"

    def test_nwcf_maps_to_o1(self):
        assert self._detect("NWCF_Book.pdf") == "o1"

    # ── Military Personnel → m1 ──

    @pytest.mark.parametrize("filename", [
        "MPN_Book.pdf", "MPMC_Book.pdf", "RPN_Book.pdf", "RPMC_Book.pdf",
    ])
    def test_milpers_maps_to_m1(self, filename):
        assert self._detect(filename) == "m1"

    # ── RDT&E → r2 ──

    @pytest.mark.parametrize("filename", [
        "RDTEN_BA1-3_Book.pdf", "RDTEN_BA4_Book.pdf", "RDTEN_BA5_Book.pdf",
        "RDTEN_BA6_Book.pdf", "RDTEN_BA7-8_Book.pdf",
    ])
    def test_rdten_maps_to_r2(self, filename):
        assert self._detect(filename) == "r2"

    # ── Military Construction → c1 ──

    @pytest.mark.parametrize("filename", [
        "MCON_Book.pdf", "MCNR_Book.pdf", "BRAC_Book.pdf",
    ])
    def test_milcon_maps_to_c1(self, filename):
        assert self._detect(filename) == "c1"

    # ── PDF function consistency ──

    @pytest.mark.parametrize("filename, expected", [
        ("APN_BA1-4_Book.pdf", "p5"),
        ("RDTEN_BA5_Book.pdf", "r2"),
        ("OMN_Book.pdf", "o1"),
        ("MPN_Book.pdf", "m1"),
        ("MCON_Book.pdf", "c1"),
    ])
    def test_pdf_detection_matches_excel(self, filename, expected):
        """_detect_pdf_exhibit_type returns same results as _detect_exhibit_type."""
        assert self._detect_pdf(filename) == expected

    # ── Standard codes still take priority ──

    def test_standard_code_beats_abbreviation(self):
        """A file with both a standard code and abbreviation uses the code."""
        # Hypothetical file that contains both 'r2' and 'apn'
        assert self._detect("r2_apn_combined.pdf") == "r2"

    # ── Longer abbreviations match first ──

    def test_ommcr_before_ommc(self):
        """'ommcr' (longer) should match before 'ommc' (shorter)."""
        assert self._detect("ommcr_book.pdf") == "o1"
        assert self._detect("ommc_book.pdf") == "o1"

    def test_panmc_before_pmc(self):
        """'panmc' (longer) should match before 'pmc' (shorter)."""
        assert self._detect("panmc_book.pdf") == "p5"

    # ── No false positives ──

    def test_unrelated_files_remain_unknown(self):
        assert self._detect("random_file.xlsx") == "unknown"
        assert self._detect("budget_summary.pdf") == "unknown"
        assert self._detect("1-cover.pdf") == "unknown"


class TestDefenseWideProcExhibitType:
    """Tests for Defense-Wide PROC_{agency} → p5 mapping."""

    @pytest.fixture(autouse=True)
    def _import_detect(self):
        from pipeline.builder import _detect_exhibit_type, _detect_pdf_exhibit_type
        self._detect = _detect_exhibit_type
        self._detect_pdf = _detect_pdf_exhibit_type

    @pytest.mark.parametrize("filename", [
        "PROC_CBDP_PB_2026.pdf",
        "PROC_SOCOM_PB_2025.pdf",
        "PROC_DLA_PB_2026.pdf",
        "PROC_MDA_VOL2B_PB_2026.pdf",
        "PROC_CYBERCOM_PB_2026.pdf",
        "PROC_OSD_PB_2026.pdf",
    ])
    def test_defense_wide_proc_maps_to_p5(self, filename):
        assert self._detect(filename) == "p5"
        assert self._detect_pdf(filename) == "p5"


class TestDownloaderMetadataExhibitType:
    """Tests that downloader/metadata.py is consistent with builder.py."""

    @pytest.fixture(autouse=True)
    def _import_detect(self):
        from downloader.metadata import detect_exhibit_type_from_filename
        self._detect = detect_exhibit_type_from_filename

    @pytest.mark.parametrize("filename, expected", [
        # Navy abbreviations
        ("APN_BA1-4_Book.pdf", "p5"),
        ("RDTEN_BA1-3_Book.pdf", "r2"),
        ("OMN_Book.pdf", "o1"),
        ("MPN_Book.pdf", "m1"),
        ("MCON_Book.pdf", "c1"),
        ("WPN_Book.pdf", "p5"),
        ("NWCF_Book.pdf", "o1"),
        # Defense-Wide PROC
        ("PROC_SOCOM_PB_2025.pdf", "p5"),
        # Standard codes still work
        ("p1_display.xlsx", "p1"),
        ("r2_navy.xlsx", "r2"),
        # Unknown stays unknown
        ("random_file.pdf", "unknown"),
    ])
    def test_metadata_detection(self, filename, expected):
        assert self._detect(filename) == expected
