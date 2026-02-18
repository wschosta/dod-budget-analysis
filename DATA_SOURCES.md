# DoD Budget Data Sources

Authoritative reference for every data source configured in
`dod_budget_downloader.py`.  URL patterns, access methods, and file
formats are extracted directly from the source code constants.

---

## Global Constants

```python
BASE_URL                = "https://comptroller.war.gov"
BUDGET_MATERIALS_URL    = "https://comptroller.war.gov/Budget-Materials/"
DOWNLOADABLE_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".zip", ".csv"}
IGNORED_HOSTS           = {"dam.defense.gov"}
ALL_SOURCES             = ["comptroller", "defense-wide", "army",
                           "navy", "navy-archive", "airforce"]
BROWSER_REQUIRED_SOURCES = {"army", "navy", "navy-archive", "airforce"}
```

---

## Sources

### 1. `comptroller` — DoD Comptroller

**Organization:** Office of the Under Secretary of Defense (Comptroller)
**Site:** `comptroller.war.gov`
**Discovery:** Auto-crawling of fiscal-year index from `BUDGET_MATERIALS_URL`
**Access method:** Direct HTTP (`requests` + BeautifulSoup)
**WAF/Browser required:** No

**Base URL (fiscal-year index):**
```
https://comptroller.war.gov/Budget-Materials/
```

`discover_fiscal_years()` fetches this page, finds all four-digit year links,
and returns a `{year: page_url}` dict.  `discover_comptroller_files()` then
crawls each year's page for downloadable links.

**File types:** PDF, Excel (`.xlsx`, `.xls`), ZIP
**FY range:** Dynamically discovered from the index page (typically FY 2017–current)
<!-- TODO: verify actual earliest year after running 1.A1 audit -->

---

### 2. `defense-wide` — Defense-Wide Budget Justification

**Organization:** DoD Comptroller (Defense-Wide section)
**Site:** `comptroller.war.gov`
**Discovery:** `discover_defense_wide_files()` — crawls the justification sub-page
**Access method:** Direct HTTP
**WAF/Browser required:** No

**URL template:**
```
https://comptroller.war.gov/Budget-Materials/FY{fy}BudgetJustification/
```

**File types:** PDF (primary), Excel
**FY range:** FY 2017–current  <!-- TODO: verify after audit -->

---

### 3. `army` — U.S. Army

**Organization:** ASA(FM&C) — Army Financial Management & Comptroller
**Site:** `asafm.army.mil`
**Discovery:** `discover_army_files()` — Playwright browser crawl
**Access method:** Playwright browser (`BROWSER_REQUIRED_SOURCES`)
**WAF/Browser required:** Yes — government WAF blocks plain HTTP

**URL template:**
```
https://www.asafm.army.mil/Budget-Materials/
```

**File types:** Excel (exhibits: `p1_display.xlsx`, `r1.xlsx`, `o1_display.xlsx`, etc.),
PDF (justification books)
**FY range:** FY 2018–current  <!-- TODO: verify after audit -->

---

### 4. `navy` — U.S. Navy / Marine Corps

**Organization:** SECNAV FM&C — Office of the Secretary of the Navy
**Site:** `secnav.navy.mil`
**Discovery:** `discover_navy_files()` — Playwright browser crawl
**Access method:** Playwright browser (`BROWSER_REQUIRED_SOURCES`)
**WAF/Browser required:** Yes

**URL template (current fiscal years):**
```
https://www.secnav.navy.mil/fmc/Pages/Fiscal-Year-{fy}.aspx
```

**File types:** PDF (justification books — Navy + Marine Corps separately),
Excel (exhibits)
**FY range:** FY 2019–current  <!-- TODO: verify after audit -->

---

### 5. `navy-archive` — U.S. Navy Archive

**Organization:** SECNAV FM&C
**Site:** `secnav.navy.mil`
**Discovery:** `discover_navy_archive_files()` — Playwright browser crawl
**Access method:** Playwright browser (`BROWSER_REQUIRED_SOURCES`)
**WAF/Browser required:** Yes

**URL (static archive page):**
```
https://www.secnav.navy.mil/fmc/fmb/Pages/archive.aspx
```

Used to retrieve older fiscal years not available on the main FY index page.

**File types:** PDF, Excel
**FY range:** FY 2017–2018 (older fiscal years)  <!-- TODO: verify after audit -->

---

### 6. `airforce` — U.S. Air Force / Space Force

**Organization:** SAF/FMC — Secretary of the Air Force Financial Management
**Site:** `saffm.hq.af.mil`
**Discovery:** `discover_airforce_files()` — Playwright browser crawl
**Access method:** Playwright browser (`BROWSER_REQUIRED_SOURCES`)
**WAF/Browser required:** Yes

**URL template:**
```
https://www.saffm.hq.af.mil/FM-Resources/Budget/Air-Force-Presidents-Budget-FY{fy2}/
```

(`fy2` = two-digit fiscal year, e.g. `26` for FY 2026)

**File types:** PDF (Air Force + Space Force justification books), Excel (exhibits)
**FY range:** FY 2019–current  <!-- TODO: verify; Space Force separated FY 2021+ -->

---

## SOURCE_DISCOVERERS Mapping

```python
SOURCE_DISCOVERERS = {
    "defense-wide": discover_defense_wide_files,
    "army":         discover_army_files,
    "navy":         discover_navy_files,
    "navy-archive": discover_navy_archive_files,
    "airforce":     discover_airforce_files,
}
# comptroller uses discover_comptroller_files() called via discover_fiscal_years()
```

---

## Failure Log Schema (`failed_downloads.json`)

When downloads fail, `dod_budget_downloader.py` writes a
`failed_downloads.json` in the output directory.  Each entry has the
following fields:

```json
{
  "url":        "<string> — original download URL",
  "dest":       "<string> — intended local file path",
  "filename":   "<string> — sanitized filename",
  "error":      "<string> — exception message or 'magic-byte verification failed'",
  "source":     "<string> — source ID (e.g. 'army')",
  "year":       "<string> — fiscal year (e.g. '2026')",
  "use_browser": "<bool>  — true if Playwright browser was required",
  "timestamp":  "<string> — ISO 8601 UTC timestamp of failure"
}
```

Use `--retry-failures [PATH]` to re-attempt all entries in this file.

---

## File Integrity Verification

After every download, `_verify_download()` checks the first 4 bytes of
the saved file against known magic-byte signatures:

| Extension | Expected bytes | Format |
|-----------|---------------|--------|
| `.pdf`    | `%PDF`        | PDF |
| `.xlsx`, `.xlsm`, `.zip`, `.docx`, `.pptx` | `PK\x03\x04` | ZIP / Office Open XML |
| `.xls`    | `\xD0\xCF\x11\xE0` | OLE2 Compound Document |

Files that fail verification (e.g., HTML error pages served as PDF) are
deleted and retried.

---

## Coverage Matrix

<!-- TODO [Step 1.A5-c]: Fill in after running audit (Step 1.A1) -->
<!-- Values marked with ~ are unverified estimates                  -->

| Source | FY2017 | FY2018 | FY2019 | FY2020 | FY2021 | FY2022 | FY2023 | FY2024 | FY2025 | FY2026 |
|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| comptroller  | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ |
| defense-wide | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ |
| army         |   | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ |
| navy         |   |   | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ |
| navy-archive | ~ | ~ |   |   |   |   |   |   |   |   |
| airforce     |   |   | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ |

Legend: ~ = expected available but unverified, blank = not expected

---

**Last Updated:** 2026-02-18 (from source code — Step 1.A5-a)
**See also:** [docs/wiki/Data-Sources.md](docs/wiki/Data-Sources.md)
