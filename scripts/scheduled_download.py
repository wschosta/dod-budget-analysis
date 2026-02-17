# TODO [Step 1.A4a]: Implement scheduled download pipeline script.
#
# This script wraps dod_budget_downloader.py for unattended/scheduled execution.
#
# Planned behavior:
#   - Run downloader with --years all --sources all --no-gui
#   - Capture stdout/stderr to a timestamped log file
#   - Exit with non-zero status on any failures
#   - Optionally write download manifest to {output_dir}/manifest.json
#
# Usage:
#   python scripts/scheduled_download.py [--output DoD_Budget_Documents]
#
# See docs/TODO_1A4_automate_download_scheduling.md for full specification.
