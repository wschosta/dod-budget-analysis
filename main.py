#!/usr/bin/env python3
"""
DoD Budget Explorer — launch the web GUI.

Usage:
    python main.py                          # http://localhost:8000
    python main.py --port 9000              # http://localhost:9000
    python main.py --host 127.0.0.1         # bind to localhost only
    python main.py --db /path/to/budget.sqlite
    python main.py --reload                 # auto-reload on code changes
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch the DoD Budget Explorer web interface.",
    )
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="Bind address (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("APP_PORT", "8000")),
        help="Port to listen on (default: 8000 or APP_PORT env var)",
    )
    parser.add_argument(
        "--db", type=Path, default=None,
        help="Path to SQLite database (default: dod_budget.sqlite or APP_DB_PATH env var)",
    )
    parser.add_argument(
        "--reload", action="store_true",
        help="Enable auto-reload on file changes (development mode)",
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="Don't open a browser window automatically",
    )
    args = parser.parse_args()

    # Set DB path env var if provided via CLI
    if args.db is not None:
        os.environ["APP_DB_PATH"] = str(args.db)

    db_path = Path(os.getenv("APP_DB_PATH", "dod_budget.sqlite"))
    if not db_path.exists():
        print(f"Warning: Database not found at {db_path}")
        print("  Run 'python run_pipeline.py' first to build the database,")
        print("  or pass --db /path/to/your/database.sqlite")
        print()

    try:
        import uvicorn
    except ImportError:
        print("Error: uvicorn is not installed.")
        print("  pip install uvicorn[standard]")
        sys.exit(1)

    url = f"http://{'localhost' if args.host == '0.0.0.0' else args.host}:{args.port}"
    print(f"Starting DoD Budget Explorer at {url}")
    print(f"Database: {db_path}")
    print()

    if not args.no_browser:
        # Open browser after a short delay to let the server start
        import threading
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()

    uvicorn.run(
        "api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
