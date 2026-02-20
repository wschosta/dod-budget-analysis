"""
Download Manifest Management — Step 1.A3-a

Handles generation, tracking, and validation of downloaded files via JSON manifests.
Enables incremental downloads, corruption detection, and reproducible builds.
"""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any


class ManifestEntry:
    """Represents a single file in the download manifest."""

    def __init__(
        self,
        url: str,
        filename: str,
        source: str,
        fiscal_year: str,
        extension: str,
        file_size: Optional[int] = None,
        sha256_hash: Optional[str] = None,
        status: str = "pending",
    ):
        self.url = url
        self.filename = filename
        self.source = source
        self.fiscal_year = fiscal_year
        self.extension = extension
        self.file_size = file_size
        self.sha256_hash = sha256_hash
        self.status = status  # pending, skipped, ok, corrupted, error

    def to_dict(self) -> Dict[str, Any]:
        """Convert entry to dictionary for JSON serialization."""
        return {
            "url": self.url,
            "filename": self.filename,
            "source": self.source,
            "fiscal_year": self.fiscal_year,
            "extension": self.extension,
            "file_size": self.file_size,
            "sha256_hash": self.sha256_hash,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ManifestEntry":
        """Create entry from dictionary."""
        return cls(
            url=data["url"],
            filename=data["filename"],
            source=data["source"],
            fiscal_year=data["fiscal_year"],
            extension=data["extension"],
            file_size=data.get("file_size"),
            sha256_hash=data.get("sha256_hash"),
            status=data.get("status", "pending"),
        )


class Manifest:
    """Manages download manifest files."""

    def __init__(self, output_dir: Path = Path("DoD_Budget_Documents")):
        self.output_dir = Path(output_dir)
        self.manifest_path = self.output_dir / "manifest.json"
        self.entries: List[ManifestEntry] = []

    def add_entry(self, entry: ManifestEntry):
        """Add a file entry to the manifest."""
        self.entries.append(entry)

    def add_file(
        self,
        url: str,
        filename: str,
        source: str,
        fiscal_year: str,
        extension: str,
    ):
        """Convenience method to add a file entry."""
        entry = ManifestEntry(
            url=url,
            filename=filename,
            source=source,
            fiscal_year=fiscal_year,
            extension=extension,
        )
        self.add_entry(entry)

    def load(self) -> bool:
        """Load manifest from file. Returns True if file exists and is valid."""
        if not self.manifest_path.exists():
            return False

        try:
            with open(self.manifest_path, "r") as f:
                data = json.load(f)
            self.entries = [ManifestEntry.from_dict(e) for e in data.get("files", [])]
            return True
        except (json.JSONDecodeError, KeyError):
            return False

    def save(self):
        """Save manifest to file."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "generated_at": datetime.now().isoformat(),
            "total_files": len(self.entries),
            "files": [e.to_dict() for e in self.entries],
        }

        with open(self.manifest_path, "w") as f:
            json.dump(data, f, indent=2)

    def update_entry_status(
        self,
        filename: str,
        status: str,
        file_size: Optional[int] = None,
        sha256_hash: Optional[str] = None,
    ):
        """Update the status and hash of a downloaded file."""
        for entry in self.entries:
            if entry.filename == filename:
                entry.status = status
                if file_size is not None:
                    entry.file_size = file_size
                if sha256_hash is not None:
                    entry.sha256_hash = sha256_hash
                return True
        return False

    def get_pending_files(self) -> List[ManifestEntry]:
        """Get list of files that haven't been downloaded yet."""
        return [e for e in self.entries if e.status == "pending"]

    def get_files_by_source(self, source: str) -> List[ManifestEntry]:
        """Get all files from a specific source."""
        return [e for e in self.entries if e.source == source]

    def get_files_by_year(self, fiscal_year: str) -> List[ManifestEntry]:
        """Get all files from a specific fiscal year."""
        return [e for e in self.entries if e.fiscal_year == fiscal_year]

    def verify_file(self, file_path: Path) -> bool:
        """Verify a file matches its manifest entry hash."""
        filename = file_path.name

        # Find entry
        entry = None
        for e in self.entries:
            if e.filename == filename:
                entry = e
                break

        if not entry or not entry.sha256_hash:
            return False  # No hash to verify against

        # Compute file hash
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    sha256_hash.update(chunk)
        except IOError:
            return False

        return sha256_hash.hexdigest() == entry.sha256_hash

    def summary(self) -> Dict[str, Any]:
        """Generate summary statistics."""
        total = len(self.entries)
        by_status: dict[str, int] = {}
        by_source: dict[str, int] = {}

        for entry in self.entries:
            by_status[entry.status] = by_status.get(entry.status, 0) + 1
            by_source[entry.source] = by_source.get(entry.source, 0) + 1

        return {
            "total_files": total,
            "by_status": by_status,
            "by_source": by_source,
            "total_size_bytes": sum(e.file_size or 0 for e in self.entries),
        }


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()
