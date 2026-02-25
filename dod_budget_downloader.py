"""
DoD Comptroller Budget Document Downloader

Downloads budget documents (PDFs, Excel files, ZIPs) from the DoD Comptroller
website and service-specific budget pages for selected fiscal years.

Sources:
  - comptroller  : Main DoD summary budget documents (comptroller.war.gov)
  - defense-wide : Defense Wide budget justification books (comptroller.war.gov)
  - army         : US Army budget materials (asafm.army.mil)
  - navy         : US Navy/Marine Corps budget materials (secnav.navy.mil)
  - navy-archive : US Navy archive alternate source (secnav.navy.mil/fmc/fmb)
  - airforce     : US Air Force & Space Force budget materials (saffm.hq.af.mil)

Requirements:
  pip install requests beautifulsoup4 playwright
  python -m playwright install chromium

Usage Examples
--------------
  python dod_budget_downloader.py                              # Interactive
  python dod_budget_downloader.py --years 2026                 # FY2026 comptroller
  python dod_budget_downloader.py --years 2026 --sources all   # FY2026 all sources
  python dod_budget_downloader.py --years 2026 --sources army navy
  python dod_budget_downloader.py --years 2026 --list          # Dry-run listing
  python dod_budget_downloader.py --years all --sources all    # Everything
  python dod_budget_downloader.py --no-gui                     # Terminal-only mode

---
Backward-compatible shim.

This module re-exports everything from the ``downloader`` package so that
existing imports (``from dod_budget_downloader import X``) continue to work
after the code was split into downloader/{sources,gui,manifest,core}.py.
"""

# Re-export all public names from the downloader package
from downloader import *  # noqa: F401, F403
from downloader import (  # explicit imports for static analysis tools
    # Shared utilities (re-exported for backward compat)
    main,
)

if __name__ == "__main__":
    main()
