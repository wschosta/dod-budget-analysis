"""
Tests for download manifest management — utils/manifest.py

Covers ManifestEntry serialization, Manifest CRUD operations, file
verification, and JSON persistence.
"""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.manifest import Manifest, ManifestEntry, compute_file_hash


# ── ManifestEntry tests ──────────────────────────────────────────────────────

class TestManifestEntry:
    def test_init_defaults(self):
        entry = ManifestEntry(
            url="https://example.com/p1.xlsx",
            filename="p1.xlsx",
            source="army",
            fiscal_year="2026",
            extension=".xlsx",
        )
        assert entry.status == "pending"
        assert entry.file_size is None
        assert entry.sha256_hash is None

    def test_to_dict(self):
        entry = ManifestEntry(
            url="https://example.com/p1.xlsx",
            filename="p1.xlsx",
            source="army",
            fiscal_year="2026",
            extension=".xlsx",
            file_size=1024,
            sha256_hash="abc123",
            status="ok",
        )
        d = entry.to_dict()
        assert d["url"] == "https://example.com/p1.xlsx"
        assert d["filename"] == "p1.xlsx"
        assert d["source"] == "army"
        assert d["fiscal_year"] == "2026"
        assert d["extension"] == ".xlsx"
        assert d["file_size"] == 1024
        assert d["sha256_hash"] == "abc123"
        assert d["status"] == "ok"

    def test_from_dict(self):
        data = {
            "url": "https://example.com/r1.pdf",
            "filename": "r1.pdf",
            "source": "navy",
            "fiscal_year": "2025",
            "extension": ".pdf",
            "file_size": 2048,
            "sha256_hash": "def456",
            "status": "ok",
        }
        entry = ManifestEntry.from_dict(data)
        assert entry.url == data["url"]
        assert entry.filename == data["filename"]
        assert entry.file_size == 2048
        assert entry.sha256_hash == "def456"

    def test_from_dict_defaults(self):
        """Missing optional fields get default values."""
        data = {
            "url": "https://example.com/file.xlsx",
            "filename": "file.xlsx",
            "source": "army",
            "fiscal_year": "2026",
            "extension": ".xlsx",
        }
        entry = ManifestEntry.from_dict(data)
        assert entry.file_size is None
        assert entry.sha256_hash is None
        assert entry.status == "pending"

    def test_roundtrip(self):
        """to_dict -> from_dict preserves all fields."""
        original = ManifestEntry(
            url="https://example.com/p1.xlsx",
            filename="p1.xlsx",
            source="army",
            fiscal_year="2026",
            extension=".xlsx",
            file_size=4096,
            sha256_hash="deadbeef",
            status="corrupted",
        )
        restored = ManifestEntry.from_dict(original.to_dict())
        assert restored.url == original.url
        assert restored.filename == original.filename
        assert restored.file_size == original.file_size
        assert restored.sha256_hash == original.sha256_hash
        assert restored.status == original.status


# ── Manifest tests ───────────────────────────────────────────────────────────

class TestManifestAddAndQuery:
    def test_add_entry(self, tmp_path):
        m = Manifest(output_dir=tmp_path)
        entry = ManifestEntry("url", "file.xlsx", "army", "2026", ".xlsx")
        m.add_entry(entry)
        assert len(m.entries) == 1

    def test_add_file_convenience(self, tmp_path):
        m = Manifest(output_dir=tmp_path)
        m.add_file("url", "file.xlsx", "army", "2026", ".xlsx")
        assert len(m.entries) == 1
        assert m.entries[0].filename == "file.xlsx"

    def test_get_pending_files(self, tmp_path):
        m = Manifest(output_dir=tmp_path)
        m.add_file("url1", "a.xlsx", "army", "2026", ".xlsx")
        m.add_file("url2", "b.xlsx", "navy", "2026", ".xlsx")
        m.entries[0].status = "ok"

        pending = m.get_pending_files()
        assert len(pending) == 1
        assert pending[0].filename == "b.xlsx"

    def test_get_files_by_source(self, tmp_path):
        m = Manifest(output_dir=tmp_path)
        m.add_file("url1", "a.xlsx", "army", "2026", ".xlsx")
        m.add_file("url2", "b.xlsx", "navy", "2026", ".xlsx")
        m.add_file("url3", "c.xlsx", "army", "2025", ".xlsx")

        army_files = m.get_files_by_source("army")
        assert len(army_files) == 2
        assert all(f.source == "army" for f in army_files)

    def test_get_files_by_year(self, tmp_path):
        m = Manifest(output_dir=tmp_path)
        m.add_file("url1", "a.xlsx", "army", "2026", ".xlsx")
        m.add_file("url2", "b.xlsx", "navy", "2025", ".xlsx")

        fy26 = m.get_files_by_year("2026")
        assert len(fy26) == 1
        assert fy26[0].fiscal_year == "2026"


class TestManifestUpdateStatus:
    def test_update_existing_entry(self, tmp_path):
        m = Manifest(output_dir=tmp_path)
        m.add_file("url", "file.xlsx", "army", "2026", ".xlsx")

        result = m.update_entry_status("file.xlsx", "ok",
                                       file_size=1024, sha256_hash="abc")
        assert result is True
        assert m.entries[0].status == "ok"
        assert m.entries[0].file_size == 1024
        assert m.entries[0].sha256_hash == "abc"

    def test_update_nonexistent_returns_false(self, tmp_path):
        m = Manifest(output_dir=tmp_path)
        result = m.update_entry_status("missing.xlsx", "ok")
        assert result is False

    def test_partial_update(self, tmp_path):
        """Updating only status preserves existing file_size/hash."""
        m = Manifest(output_dir=tmp_path)
        m.add_file("url", "file.xlsx", "army", "2026", ".xlsx")
        m.entries[0].file_size = 999

        m.update_entry_status("file.xlsx", "error")
        assert m.entries[0].status == "error"
        assert m.entries[0].file_size == 999  # preserved


class TestManifestPersistence:
    def test_save_and_load(self, tmp_path):
        """Save to JSON and load back preserves entries."""
        m = Manifest(output_dir=tmp_path)
        m.add_file("url1", "a.xlsx", "army", "2026", ".xlsx")
        m.add_file("url2", "b.pdf", "navy", "2025", ".pdf")
        m.entries[0].status = "ok"
        m.entries[0].file_size = 1024
        m.save()

        m2 = Manifest(output_dir=tmp_path)
        loaded = m2.load()
        assert loaded is True
        assert len(m2.entries) == 2
        assert m2.entries[0].filename == "a.xlsx"
        assert m2.entries[0].status == "ok"
        assert m2.entries[0].file_size == 1024

    def test_load_nonexistent_returns_false(self, tmp_path):
        m = Manifest(output_dir=tmp_path)
        assert m.load() is False

    def test_load_invalid_json_returns_false(self, tmp_path):
        tmp_path.mkdir(exist_ok=True)
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("not valid json {{}")

        m = Manifest(output_dir=tmp_path)
        assert m.load() is False

    def test_save_creates_directory(self, tmp_path):
        nested = tmp_path / "deep" / "nested"
        m = Manifest(output_dir=nested)
        m.add_file("url", "file.xlsx", "army", "2026", ".xlsx")
        m.save()
        assert (nested / "manifest.json").exists()

    def test_saved_json_structure(self, tmp_path):
        m = Manifest(output_dir=tmp_path)
        m.add_file("url", "file.xlsx", "army", "2026", ".xlsx")
        m.save()

        data = json.loads((tmp_path / "manifest.json").read_text())
        assert "generated_at" in data
        assert "total_files" in data
        assert data["total_files"] == 1
        assert "files" in data
        assert len(data["files"]) == 1


class TestManifestVerifyFile:
    def test_verify_matching_hash(self, tmp_path):
        content = b"test file content for verification"
        file_path = tmp_path / "verified.xlsx"
        file_path.write_bytes(content)
        expected_hash = hashlib.sha256(content).hexdigest()

        m = Manifest(output_dir=tmp_path)
        m.add_file("url", "verified.xlsx", "army", "2026", ".xlsx")
        m.update_entry_status("verified.xlsx", "ok",
                              sha256_hash=expected_hash)

        assert m.verify_file(file_path) is True

    def test_verify_mismatched_hash(self, tmp_path):
        file_path = tmp_path / "tampered.xlsx"
        file_path.write_bytes(b"actual content")

        m = Manifest(output_dir=tmp_path)
        m.add_file("url", "tampered.xlsx", "army", "2026", ".xlsx")
        m.update_entry_status("tampered.xlsx", "ok",
                              sha256_hash="0000000000000000")

        assert m.verify_file(file_path) is False

    def test_verify_missing_entry(self, tmp_path):
        file_path = tmp_path / "unknown.xlsx"
        file_path.write_bytes(b"data")

        m = Manifest(output_dir=tmp_path)
        assert m.verify_file(file_path) is False

    def test_verify_no_hash_stored(self, tmp_path):
        file_path = tmp_path / "nohash.xlsx"
        file_path.write_bytes(b"data")

        m = Manifest(output_dir=tmp_path)
        m.add_file("url", "nohash.xlsx", "army", "2026", ".xlsx")
        # No hash set — verify should return False
        assert m.verify_file(file_path) is False

    def test_verify_missing_file(self, tmp_path):
        m = Manifest(output_dir=tmp_path)
        m.add_file("url", "deleted.xlsx", "army", "2026", ".xlsx")
        m.update_entry_status("deleted.xlsx", "ok", sha256_hash="abc")

        # File doesn't exist on disk
        assert m.verify_file(tmp_path / "deleted.xlsx") is False


class TestManifestSummary:
    def test_empty_manifest(self, tmp_path):
        m = Manifest(output_dir=tmp_path)
        s = m.summary()
        assert s["total_files"] == 0
        assert s["by_status"] == {}
        assert s["by_source"] == {}
        assert s["total_size_bytes"] == 0

    def test_summary_counts(self, tmp_path):
        m = Manifest(output_dir=tmp_path)
        m.add_file("url1", "a.xlsx", "army", "2026", ".xlsx")
        m.add_file("url2", "b.xlsx", "navy", "2026", ".xlsx")
        m.add_file("url3", "c.xlsx", "army", "2025", ".xlsx")
        m.entries[0].status = "ok"
        m.entries[0].file_size = 1000
        m.entries[1].status = "ok"
        m.entries[1].file_size = 2000

        s = m.summary()
        assert s["total_files"] == 3
        assert s["by_status"]["ok"] == 2
        assert s["by_status"]["pending"] == 1
        assert s["by_source"]["army"] == 2
        assert s["by_source"]["navy"] == 1
        assert s["total_size_bytes"] == 3000

    def test_summary_null_sizes(self, tmp_path):
        m = Manifest(output_dir=tmp_path)
        m.add_file("url", "file.xlsx", "army", "2026", ".xlsx")
        s = m.summary()
        assert s["total_size_bytes"] == 0  # None treated as 0
