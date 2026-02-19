"""
DEPLOY-002: SQLite database backup script.

Uses the sqlite3 online backup API (Connection.backup()) to produce a
consistent snapshot of the database while it is potentially being written
to by the running API server.  This avoids file-copy corruption that can
occur if the WAL journal is active.

Usage:
    python scripts/backup_db.py                      # backup with defaults
    python scripts/backup_db.py --db /data/budget.sqlite --dest /backups
    python scripts/backup_db.py --keep 7             # retain last 7 backups

Backup filename format: dod_budget_YYYYMMDD_HHMMSS.sqlite
"""

# TODO [Group: BEAR] BEAR-005: Create scripts/smoke_test.py — deployment verification (~2,000 tokens)

import argparse
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

_logger = logging.getLogger("backup_db")
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
)

# ── Default paths ─────────────────────────────────────────────────────────────

_DEFAULT_DB = Path(os.environ.get("APP_DB_PATH", "dod_budget.sqlite"))
_DEFAULT_DEST = Path(os.environ.get("BACKUP_DIR", "backups"))

# Pattern that backup filenames must match for pruning
_BACKUP_RE = re.compile(r"^dod_budget_\d{8}_\d{6}\.sqlite$")


# ── Core functions ────────────────────────────────────────────────────────────

def backup_database(src: Path, dest_dir: Path) -> Path:
    """Create a consistent timestamped backup of *src* in *dest_dir*.

    Uses the sqlite3 online backup API so the source database is not locked
    and WAL frames are included in the snapshot.

    Args:
        src: Path to the source SQLite database file.
        dest_dir: Directory where the backup file will be written.

    Returns:
        Path to the newly created backup file.

    Raises:
        FileNotFoundError: If *src* does not exist.
        OSError: If *dest_dir* cannot be created.
    """
    if not src.exists():
        raise FileNotFoundError(f"Source database not found: {src}")

    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"dod_budget_{timestamp}.sqlite"
    backup_path = dest_dir / backup_name

    _logger.info("Starting backup: %s -> %s", src, backup_path)

    # sqlite3.connect().backup() performs an online backup that handles
    # concurrent writes and WAL mode correctly.
    src_conn = sqlite3.connect(str(src))
    dst_conn = sqlite3.connect(str(backup_path))
    try:
        src_conn.backup(dst_conn, pages=100)
    finally:
        dst_conn.close()
        src_conn.close()

    size_kb = backup_path.stat().st_size // 1024
    _logger.info("Backup complete: %s (%d KB)", backup_path, size_kb)
    return backup_path


def prune_old_backups(dest_dir: Path, keep: int) -> list[Path]:
    """Remove old backups so that only the *keep* most-recent are retained.

    Only files matching the ``dod_budget_YYYYMMDD_HHMMSS.sqlite`` pattern
    are considered; other files in *dest_dir* are left untouched.

    Args:
        dest_dir: Directory containing backup files.
        keep: Number of most-recent backups to retain.  Must be >= 1.

    Returns:
        List of deleted backup paths.
    """
    if keep < 1:
        raise ValueError(f"--keep must be >= 1, got {keep}")

    backups = sorted(
        [f for f in dest_dir.iterdir() if _BACKUP_RE.match(f.name)],
        key=lambda p: p.name,  # lexicographic = chronological for our filename
    )

    to_delete = backups[:-keep] if len(backups) > keep else []
    for path in to_delete:
        _logger.info("Pruning old backup: %s", path)
        path.unlink()

    if to_delete:
        _logger.info("Pruned %d old backup(s); %d retained", len(to_delete), keep)
    return to_delete


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a timestamped SQLite backup using the online backup API.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=_DEFAULT_DB,
        help="Path to the source SQLite database.",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=_DEFAULT_DEST,
        help="Directory where backup files are written.",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Retain only the N most-recent backups; delete older ones. "
            "0 means keep all backups (no pruning)."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the backup script.

    Returns:
        0 on success, 1 on error.
    """
    args = _build_parser().parse_args(argv)

    try:
        backup_path = backup_database(src=args.db, dest_dir=args.dest)
    except FileNotFoundError as exc:
        _logger.error("%s", exc)
        return 1
    except OSError as exc:
        _logger.error("Backup failed: %s", exc)
        return 1

    if args.keep > 0:
        try:
            prune_old_backups(dest_dir=args.dest, keep=args.keep)
        except ValueError as exc:
            _logger.error("%s", exc)
            return 1

    _logger.info("Done. Backup saved to: %s", backup_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
