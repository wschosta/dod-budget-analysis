#!/usr/bin/env python3
"""axe-core accessibility audit against a running instance (Roadmap 3.A7 / G4).

Audits every page route for WCAG 2.1 AA violations in both colour schemes.
Both matter: the palette inverts between themes, so a control can pass in one
and fail in the other. That is exactly how the primary button was found sitting
at 2.25:1 in dark mode while passing in light.

Requires a browser automation stack that is *not* in requirements-dev.txt,
since it is only needed for this audit:

    pip install axe-core-python
    python -m playwright install chromium

Usage:
    uvicorn api.app:app --port 8000 &
    python scripts/accessibility_audit.py --base-url http://127.0.0.1:8000

Exits non-zero if any violation is found, so it can gate a release.
"""

from __future__ import annotations

import argparse
import json
import sys

PAGES = ["/", "/about", "/programs", "/dashboard", "/charts", "/consolidated", "/spruill"]
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
_IMPACT_ORDER = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3}


def audit(base_url: str, theme: str, pages: list[str], executable_path: str | None) -> dict:
    """Run axe against every page in one colour scheme, returning grouped violations."""
    from axe_core_python.sync_playwright import Axe
    from playwright.sync_api import sync_playwright

    axe = Axe()
    findings: dict[tuple[str, str], dict] = {}

    with sync_playwright() as p:
        launch_kwargs = {"executable_path": executable_path} if executable_path else {}
        browser = p.chromium.launch(**launch_kwargs)
        page = browser.new_context(color_scheme=theme).new_page()
        for path in pages:
            page.goto(base_url.rstrip("/") + path, wait_until="networkidle")
            page.wait_for_timeout(700)  # let deferred chart/HTMX content settle
            result = axe.run(page, options={"runOnly": {"type": "tag", "values": TAGS}})
            for violation in result["violations"]:
                key = (violation["id"], violation["impact"])
                entry = findings.setdefault(
                    key, {"help": violation["help"], "url": violation["helpUrl"], "hits": []}
                )
                for node in violation["nodes"]:
                    entry["hits"].append({"page": path, "target": node["target"]})
        browser.close()

    return findings


def report(theme: str, findings: dict) -> None:
    """Print a human-readable summary, most severe first."""
    print(f"\n{'=' * 78}\n  axe-core WCAG 2.1 AA — theme={theme}\n{'=' * 78}")
    if not findings:
        print("  No violations.")
        return
    for (rule, impact), data in sorted(
        findings.items(), key=lambda kv: _IMPACT_ORDER.get(kv[0][1], 9)
    ):
        pages = sorted({h["page"] for h in data["hits"]})
        print(f"\n[{(impact or 'unknown').upper()}] {rule} — {len(data['hits'])} node(s)")
        print(f"  {data['help']}")
        print(f"  pages: {', '.join(pages)}")
        print(f"  {data['url']}")
        for hit in data["hits"][:5]:
            print(f"    - {hit['page']}  {hit['target']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--themes",
        default="light,dark",
        help="Comma-separated colour schemes to audit (default: light,dark)",
    )
    parser.add_argument(
        "--pages",
        default=",".join(PAGES),
        help="Comma-separated page paths to audit",
    )
    parser.add_argument(
        "--executable-path",
        default=None,
        help="Chromium binary, when the bundled Playwright build is unavailable",
    )
    parser.add_argument("--json-out", default=None, help="Write raw findings here")
    args = parser.parse_args()

    pages = [p.strip() for p in args.pages.split(",") if p.strip()]
    all_findings, total = {}, 0
    for theme in (t.strip() for t in args.themes.split(",") if t.strip()):
        findings = audit(args.base_url, theme, pages, args.executable_path)
        report(theme, findings)
        total += sum(len(d["hits"]) for d in findings.values())
        all_findings[theme] = {f"{r}|{i}": d for (r, i), d in findings.items()}

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(all_findings, fh, indent=2)

    print(f"\n{'=' * 78}\n  Total violations: {total}\n{'=' * 78}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
