"""
Manifest management for the DoD Budget Downloader.

Tracks download status, file hashes, and enables incremental updates
via the manifest.json file written alongside downloaded documents.
"""

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path


# In-memory manifest; written to disk by write_manifest() / update_manifest_entry()
_manifest: dict = {}
_manifest_path: Path | None = None
_manifest_lock = threading.Lock()


def _compute_sha256(file_path: Path) -> str:
    """Compute the SHA-256 hex digest of a file.

    Reads in 64 KB chunks to avoid loading large files into memory.
    Implements TODO 1.A3-b.
    """
    h = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest_ok_urls(manifest_path: Path, since_date: str | None = None) -> set[str]:
    """Return the set of URLs that were successfully downloaded and are up-to-date.

    Used by --since to skip files that don't need re-downloading.

    Args:
        manifest_path: Path to an existing manifest.json.
        since_date:    ISO date string "YYYY-MM-DD".  If given, only entries
                       downloaded *on or after* that date are considered current.
                       If None, all entries with status='ok' are considered current.

    Returns:
        Set of URL strings that should be skipped (already current).
    """
    if not manifest_path.exists():
        return set()
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            data = json.load(fh)
        files = data.get("files", {})
    except (json.JSONDecodeError, OSError):
        return set()

    cutoff = None
    if since_date:
        try:
            from datetime import date as _date
            cutoff = _date.fromisoformat(since_date)
        except ValueError:
            pass

    ok_urls: set[str] = set()
    for url, entry in files.items():
        if entry.get("status") != "ok":
            continue
        if cutoff is not None:
            downloaded_at = entry.get("downloaded_at")
            if not downloaded_at:
                continue  # No timestamp -- treat as stale
            try:
                from datetime import date as _date
                dl_date = _date.fromisoformat(downloaded_at[:10])
                if dl_date < cutoff:
                    continue  # Downloaded before the cutoff -- re-download
            except ValueError:
                continue
        ok_urls.add(url)

    return ok_urls


def write_manifest(output_dir: Path, all_files: dict, manifest_path: Path) -> None:
    """Write an initial manifest.json listing all files to be downloaded.

    Each entry records: url, expected_filename, source, fiscal_year, extension.
    After downloading, call update_manifest_entry() to add status/size/hash.
    Implements TODO 1.A3-a.
    """
    global _manifest, _manifest_path
    _manifest_path = manifest_path

    entries: dict[str, dict] = {}
    for year, sources in all_files.items():
        for source_label, files in sources.items():
            for f in files:
                key = f["url"]
                entries[key] = {
                    "url": f["url"],
                    "filename": f["filename"],
                    "source": source_label,
                    "fiscal_year": year,
                    "extension": f.get("extension", ""),
                    "status": "pending",
                    "file_size": None,
                    "sha256": None,
                    "downloaded_at": None,
                }

    _manifest = entries
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(
            {"generated_at": datetime.now(timezone.utc).isoformat(), "files": entries},
            fh, indent=2)


def update_manifest_entry(url: str, status: str, file_size: int,
                          file_hash: str | None) -> None:
    """Update a manifest entry after a download attempt.

    Writes the updated manifest to disk immediately so it survives crashes.
    Thread-safe: serialised via ``_manifest_lock``.
    Implements TODO 1.A3-a / 1.A3-b.
    """
    global _manifest, _manifest_path
    with _manifest_lock:
        if not _manifest_path or url not in _manifest:
            return
        _manifest[url].update({
            "status": status,
            "file_size": file_size,
            "sha256": file_hash,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            with open(_manifest_path, "w", encoding="utf-8") as fh:
                json.dump(
                    {"generated_at": _manifest.get("_meta_generated_at", ""),
                     "files": _manifest},
                    fh, indent=2,
                )
        except OSError:
            pass  # Non-fatal: manifest update failures don't block downloads
