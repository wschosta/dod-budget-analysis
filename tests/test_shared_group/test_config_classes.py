"""
Tests for utils/config.py — Config, KnownValues, ColumnMapping, FilePatterns

Tests configuration class methods and known value lookups.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.config import (
    Config,
    DatabaseConfig,
    DownloadConfig,
    KnownValues,
    ColumnMapping,
    FilePatterns,
)


class TestConfig:
    def test_to_dict_empty(self):
        c = Config()
        assert c.to_dict() == {}

    def test_to_dict_with_attrs(self):
        c = Config()
        c.name = "test"
        c.value = 42
        d = c.to_dict()
        assert d == {"name": "test", "value": 42}

    def test_to_dict_skips_private(self):
        c = Config()
        c._private = "hidden"
        c.public = "visible"
        d = c.to_dict()
        assert "_private" not in d
        assert d["public"] == "visible"

    def test_from_dict(self):
        c = Config.from_dict({"x": 1, "y": "two"})
        assert c.x == 1
        assert c.y == "two"

    def test_from_dict_empty(self):
        c = Config.from_dict({})
        assert c.to_dict() == {}

    def test_save_and_load_json(self, tmp_path):
        c = Config()
        c.name = "test_config"
        c.count = 5
        path = tmp_path / "sub" / "config.json"
        c.save_json(path)
        assert path.exists()

        loaded = Config.load_json(path)
        assert loaded.name == "test_config"
        assert loaded.count == 5

    def test_load_json_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            Config.load_json(tmp_path / "nonexistent.json")

    def test_load_json_invalid(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json {{{")
        with pytest.raises(json.JSONDecodeError):
            Config.load_json(bad)


class TestDatabaseConfig:
    def test_defaults(self):
        dc = DatabaseConfig()
        assert dc.db_path == Path("dod_budget.sqlite")
        assert dc.wal_mode is True
        assert dc.batch_size == 1000

    def test_to_dict(self):
        dc = DatabaseConfig()
        d = dc.to_dict()
        assert "db_path" in d
        assert "wal_mode" in d


class TestDownloadConfig:
    def test_defaults(self):
        dl = DownloadConfig()
        assert dl.max_retries == 3
        assert dl.timeout_seconds == 30
        assert dl.cache_ttl_hours == 24


class TestKnownValues:
    def test_is_valid_org_known(self):
        assert KnownValues.is_valid_org("Army")
        assert KnownValues.is_valid_org("Navy")
        assert KnownValues.is_valid_org("Space Force")

    def test_is_valid_org_unknown(self):
        assert not KnownValues.is_valid_org("Unknown")
        assert not KnownValues.is_valid_org("")
        assert not KnownValues.is_valid_org("army")  # case-sensitive

    def test_is_valid_exhibit_type_known(self):
        assert KnownValues.is_valid_exhibit_type("p1")
        assert KnownValues.is_valid_exhibit_type("P1")  # case-insensitive
        assert KnownValues.is_valid_exhibit_type("r1")
        assert KnownValues.is_valid_exhibit_type("m1")
        assert KnownValues.is_valid_exhibit_type("c1")

    def test_is_valid_exhibit_type_unknown(self):
        assert not KnownValues.is_valid_exhibit_type("z9")
        assert not KnownValues.is_valid_exhibit_type("")

    def test_get_exhibit_description(self):
        desc = KnownValues.get_exhibit_description("p1")
        assert desc == "Procurement (P-1)"

    def test_get_exhibit_description_case_insensitive(self):
        desc = KnownValues.get_exhibit_description("R1")
        assert desc == "R&D (R-1)"

    def test_get_exhibit_description_unknown(self):
        assert KnownValues.get_exhibit_description("z9") is None

    def test_get_org_code_found(self):
        assert KnownValues.get_org_code("Army") == "A"
        assert KnownValues.get_org_code("Navy") == "N"
        assert KnownValues.get_org_code("Air Force") == "F"

    def test_get_org_code_not_found(self):
        assert KnownValues.get_org_code("Unknown") is None
        assert KnownValues.get_org_code("") is None

    def test_org_codes_cover_organizations(self):
        # Every org in ORG_CODES values should be in ORGANIZATIONS
        for name in KnownValues.ORG_CODES.values():
            assert name in KnownValues.ORGANIZATIONS


class TestColumnMapping:
    def test_get_mapping_m1(self):
        m = ColumnMapping.get_mapping("m1")
        assert "account" in m
        assert m["account"] == "account"

    def test_get_mapping_p1(self):
        m = ColumnMapping.get_mapping("p1")
        assert "unit_cost" in m
        assert "quantity" in m

    def test_get_mapping_p1r(self):
        # p1r should use same mapping as p1
        assert ColumnMapping.get_mapping("p1r") == ColumnMapping.get_mapping("p1")

    def test_get_mapping_case_insensitive(self):
        assert ColumnMapping.get_mapping("M1") == ColumnMapping.get_mapping("m1")

    def test_get_mapping_unknown(self):
        assert ColumnMapping.get_mapping("z9") == {}

    def test_normalize_header_basic(self):
        assert ColumnMapping.normalize_header("FY 2026 Request") == "fy 2026 request"

    def test_normalize_header_newlines(self):
        assert ColumnMapping.normalize_header("FY\n2026\nRequest") == "fy 2026 request"

    def test_normalize_header_multiple_spaces(self):
        assert ColumnMapping.normalize_header("FY   2026   Request") == "fy 2026 request"

    def test_normalize_header_empty(self):
        assert ColumnMapping.normalize_header("") == ""
        assert ColumnMapping.normalize_header(None) == ""


class TestFilePatterns:
    def test_is_budget_document_matches(self):
        assert FilePatterns.is_budget_document("Budget_Justification_2026.pdf")
        assert FilePatterns.is_budget_document("exhibit_p1_display.xlsx")
        assert FilePatterns.is_budget_document("RDT&E_summary.pdf")
        assert FilePatterns.is_budget_document("appropriation_act.pdf")

    def test_is_budget_document_rejects(self):
        assert not FilePatterns.is_budget_document("readme.txt")
        assert not FilePatterns.is_budget_document("random_file.xlsx")

    def test_get_fiscal_year_from_filename(self):
        assert FilePatterns.get_fiscal_year_from_filename("FY2026_budget.pdf") == 2026
        assert FilePatterns.get_fiscal_year_from_filename("army_p1_2025.xlsx") == 2025

    def test_get_fiscal_year_no_year(self):
        assert FilePatterns.get_fiscal_year_from_filename("budget.pdf") is None
        assert FilePatterns.get_fiscal_year_from_filename("FY99_old.pdf") is None
