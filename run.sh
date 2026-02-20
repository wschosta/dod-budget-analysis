#!/usr/bin/env bash
# DoD Budget Explorer — launch the web GUI
#
# Usage:
#   ./run.sh                      # starts on http://localhost:8000
#   ./run.sh 9000                 # starts on http://localhost:9000
#   APP_DB_PATH=my.sqlite ./run.sh

set -euo pipefail
cd "$(dirname "$0")"

PORT="${1:-${APP_PORT:-8000}}"

echo "Starting DoD Budget Explorer on http://localhost:${PORT}"
echo "Database: ${APP_DB_PATH:-dod_budget.sqlite}"
echo ""

exec python -m uvicorn api.app:app --host 0.0.0.0 --port "$PORT" --reload --log-level info
