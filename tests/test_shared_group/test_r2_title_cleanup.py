"""Tests for R-2 PDF sub-element title cleanup in utils/normalization.py."""

from utils.normalization import clean_r2_title, normalize_r2_project_code


class TestCleanR2Title:
    """Test clean_r2_title() for various dirty-title patterns."""

    def test_strip_trailing_amounts(self):
        code, title = clean_r2_title(
            "1662: F/A-18 Improvement 4,439.845 101.694 97.011 130.407 -"
        )
        assert code == "1662"
        assert title == "F/A-18 Improvement"

    def test_strip_trailing_amounts_with_stars(self):
        code, title = clean_r2_title("9999: Congressional Adds 55.043 13.514 0.000 0.000 -")
        assert code == "9999"
        assert title == "Congressional Adds"

    def test_e_prefix_normalization(self):
        code, title = clean_r2_title("E1662 F/A-18 Improvements")
        assert code == "1662"
        assert title == "F/A-18 Improvements"

    def test_space_separated_code(self):
        code, title = clean_r2_title("1662 F/A-18 Improvements")
        assert code == "1662"
        assert title == "F/A-18 Improvements"

    def test_colon_format_already_clean(self):
        code, title = clean_r2_title("1662: F/A-18 Improvement")
        assert code == "1662"
        assert title == "F/A-18 Improvement"

    def test_junk_total_pe(self):
        assert clean_r2_title("Total PE") == (None, None)

    def test_junk_total_pe_cost(self):
        assert clean_r2_title("Total PE Cost 46.872 **1.183") == (None, None)

    def test_junk_r1_shopping_list(self):
        assert clean_r2_title("R-1 SHOPPING LIST - Item No.") == (None, None)

    def test_junk_footnote(self):
        assert clean_r2_title("* IMDS FY 98 funds ($18.541 million)") == (None, None)

    def test_caliber_preserved(self):
        """2.75 is a caliber, not a dollar amount."""
        code, title = clean_r2_title("D549 2.75 Inch Anti-Air TD")
        assert code == "D549"
        assert title == "2.75 Inch Anti-Air TD"

    def test_weapon_designator_preserved(self):
        code, title = clean_r2_title("SM-6 Block III")
        assert code is None
        assert title == "SM-6 Block III"

    def test_empty_string(self):
        assert clean_r2_title("") == (None, None)

    def test_none_input(self):
        assert clean_r2_title("") == (None, None)

    def test_idempotent(self):
        """Calling twice on a clean title returns the same result."""
        code1, title1 = clean_r2_title("1662: F/A-18 Improvement")
        code2, title2 = clean_r2_title(f"{code1}: {title1}")
        assert code1 == code2
        assert title1 == title2


class TestNormalizeR2ProjectCode:
    def test_e_prefix(self):
        assert normalize_r2_project_code("E1662") == "1662"

    def test_plain_code(self):
        assert normalize_r2_project_code("1662") == "1662"

    def test_none(self):
        assert normalize_r2_project_code(None) is None

    def test_alpha_code(self):
        assert normalize_r2_project_code("ABC") == "ABC"

    def test_lowercase_e(self):
        assert normalize_r2_project_code("e62") == "62"
