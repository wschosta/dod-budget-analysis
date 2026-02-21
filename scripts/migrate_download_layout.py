#!/usr/bin/env python3
"""
Migrate Download Folder Layout
==============================

Moves existing downloaded files from the old flat layout to the new
nested layout that encodes budget cycle and exhibit category:

  Old:  DoD_Budget_Documents/FY2026/Comptroller/p1_display.xlsx
  New:  DoD_Budget_Documents/FY2026/PB/Comptroller/summary/p1_display.xlsx

Usage:
    python scripts/migrate_download_layout.py --docs-dir DoD_Budget_Documents
    python scripts/migrate_download_layout.py --docs-dir DoD_Budget_Documents --dry-run
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# Allow running from the repo root or scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.config import classify_exhibit_category


# Budget cycle keywords for detection.  Default to "PB" for existing files
# (all files downloaded before this migration were President's Budget files).
_KNOWN_BUDGET_CYCLES = {"PB", "ENACTED", "NDAA", "SUPPLEMENTAL", "AMENDMENT", "APPROPRIATION"}

DEFAULT_CYCLE = "PB"


def _is_already_migrated(fy_dir: Path) -> bool:
    """Check whether a FY directory already uses the new layout.

    Returns True if any immediate child directory name matches a known
    budget cycle, indicating the new layout is (at least partially) in use.
    """
    for child in fy_dir.iterdir():
        if child.is_dir() and child.name.upper() in _KNOWN_BUDGET_CYCLES:
            return True
    return False


def _classify_file(filename: str) -> str:
    """Return the exhibit category sub-folder for a file.

    Uses the shared classify_exhibit_category() from utils.config.
    """
    return classify_exhibit_category(filename)


def migrate_fy_directory(
    fy_dir: Path,
    dry_run: bool = False,
    budget_cycle: str = DEFAULT_CYCLE,
) -> dict[str, int]:
    """Migrate a single FY directory from old to new layout.

    Old: FY{year}/{source}/<files>
    New: FY{year}/{cycle}/{source}/{category}/<files>

    Args:
        fy_dir: Path to the FY directory (e.g. DoD_Budget_Documents/FY2026).
        dry_run: If True, print what would happen without moving files.
        budget_cycle: Budget cycle to assign (default "PB").

    Returns:
        Dict with keys: moved, skipped, errors.
    """
    stats = {"moved": 0, "skipped": 0, "errors": 0}

    for source_dir in sorted(fy_dir.iterdir()):
        if not source_dir.is_dir():
            continue
        # Skip directories that are already budget-cycle dirs
        if source_dir.name.upper() in _KNOWN_BUDGET_CYCLES:
            continue

        source_name = source_dir.name
        for file_path in sorted(source_dir.rglob("*")):
            if not file_path.is_file():
                continue

            # Determine the exhibit category for this file
            category = _classify_file(file_path.name)

            # Build the new destination path
            # Preserve any sub-path below the source dir (e.g. extracted ZIPs)
            rel_to_source = file_path.relative_to(source_dir)
            if len(rel_to_source.parts) > 1:
                # File is in a subdirectory of the source — preserve it
                new_dest = (
                    fy_dir / budget_cycle / source_name / category
                    / Path(*rel_to_source.parts)
                )
            else:
                new_dest = (
                    fy_dir / budget_cycle / source_name / category
                    / file_path.name
                )

            if new_dest.exists():
                if dry_run:
                    print(f"  SKIP (exists): {file_path} -> {new_dest}")
                stats["skipped"] += 1
                continue

            if dry_run:
                print(f"  MOVE: {file_path} -> {new_dest}")
                stats["moved"] += 1
            else:
                try:
                    new_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(file_path), str(new_dest))
                    stats["moved"] += 1
                except Exception as exc:
                    print(f"  ERROR moving {file_path}: {exc}", file=sys.stderr)
                    stats["errors"] += 1

    # Clean up empty directories (only when actually moving files)
    if not dry_run:
        _cleanup_empty_dirs(fy_dir)

    return stats


def _cleanup_empty_dirs(root: Path) -> int:
    """Remove empty directories under root (bottom-up). Returns count removed.

    Tolerates PermissionError (e.g. OneDrive-locked directories on Windows).
    """
    removed = 0
    for dirpath in sorted(root.rglob("*"), reverse=True):
        if dirpath.is_dir() and not any(dirpath.iterdir()):
            try:
                dirpath.rmdir()
                removed += 1
            except PermissionError:
                pass  # OneDrive or antivirus lock; harmless
    return removed


def migrate_all(
    docs_dir: Path,
    dry_run: bool = False,
    budget_cycle: str = DEFAULT_CYCLE,
) -> dict[str, int]:
    """Migrate all FY directories under docs_dir.

    Args:
        docs_dir: Root documents directory (e.g. DoD_Budget_Documents/).
        dry_run: If True, print what would happen without moving files.
        budget_cycle: Default budget cycle to assign.

    Returns:
        Aggregate stats dict.
    """
    totals = {"moved": 0, "skipped": 0, "errors": 0}

    if not docs_dir.exists():
        print(f"Error: {docs_dir} does not exist.", file=sys.stderr)
        return totals

    fy_dirs = sorted(
        d for d in docs_dir.iterdir()
        if d.is_dir() and d.name.startswith("FY")
    )

    if not fy_dirs:
        print(f"No FY directories found in {docs_dir}.")
        return totals

    for fy_dir in fy_dirs:
        if _is_already_migrated(fy_dir):
            print(f"\n{fy_dir.name}: Already migrated (budget cycle dir detected), skipping.")
            continue

        print(f"\n{fy_dir.name}: Migrating...")
        stats = migrate_fy_directory(fy_dir, dry_run=dry_run, budget_cycle=budget_cycle)
        for key in totals:
            totals[key] += stats[key]
        print(f"  {stats['moved']} moved, {stats['skipped']} skipped, {stats['errors']} errors")

    return totals


def main():
    parser = argparse.ArgumentParser(
        description="Migrate download folder layout to include budget cycle and exhibit category.",
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=Path("DoD_Budget_Documents"),
        help="Root documents directory (default: DoD_Budget_Documents/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be moved without actually moving files.",
    )
    parser.add_argument(
        "--budget-cycle",
        default=DEFAULT_CYCLE,
        help="Budget cycle to assign to migrated files (default: PB).",
    )
    args = parser.parse_args()

    mode = "DRY RUN" if args.dry_run else "LIVE"
    print(f"Download Layout Migration ({mode})")
    print(f"  Docs dir: {args.docs_dir}")
    print(f"  Budget cycle: {args.budget_cycle}")
    print("=" * 60)

    totals = migrate_all(
        docs_dir=args.docs_dir,
        dry_run=args.dry_run,
        budget_cycle=args.budget_cycle,
    )

    print(f"\n{'=' * 60}")
    print(f"Total: {totals['moved']} moved, {totals['skipped']} skipped, "
          f"{totals['errors']} errors")

    if not args.dry_run and totals["moved"] > 0:
        print("\nMigration complete. You should now rebuild the database:")
        print("  python run_pipeline.py --rebuild")

    return 0 if totals["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
