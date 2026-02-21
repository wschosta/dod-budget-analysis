# Data Sources

Authoritative reference for every data source configured in `dod_budget_downloader.py`.
URL patterns, access methods, and file formats are extracted directly from the source
code constants.

All data in this database originates from publicly available U.S. government budget
justification documents. No login, FOIA request, or fee is required to access the
originals. The DoD Budget Explorer database is derived entirely from these publicly
posted files.

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

## Sources Overview

| Source ID | Organization | Site | Access Method |
|-----------|-------------|------|---------------|
| `comptroller` | DoD Comptroller (OUSD-C) | `comptroller.war.gov` | Direct HTTP |
| `defense-wide` | DoD Comptroller (Defense-Wide) | `comptroller.war.gov` | Direct HTTP |
| `army` | ASA(FM&C) -- U.S. Army | `asafm.army.mil` | Playwright browser |
| `navy` | SECNAV FM&C -- U.S. Navy | `secnav.navy.mil` | Playwright browser |
| `navy-archive` | SECNAV FM&C -- Navy Archive | `secnav.navy.mil` | Playwright browser |
| `airforce` | SAF/FMC -- Air Force / Space Force | `saffm.hq.af.mil` | Playwright browser |

---

## Source Details

### 1. `comptroller` -- DoD Comptroller

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
and returns a `{year: page_url}` dict. `discover_comptroller_files()` then
crawls each year's page for downloadable links.

**File types:** PDF, Excel (`.xlsx`, `.xls`), ZIP
**FY range:** FY2017--FY2026 verified (dynamically discovered from index page)

---

### 2. `defense-wide` -- Defense-Wide Budget Justification

**Organization:** DoD Comptroller (Defense-Wide section)
**Site:** `comptroller.war.gov`
**Discovery:** `discover_defense_wide_files()` -- crawls the justification sub-page
**Access method:** Direct HTTP
**WAF/Browser required:** No

**URL template:**
```
https://comptroller.war.gov/Budget-Materials/FY{fy}BudgetJustification/
```

**File types:** PDF (primary), Excel
**FY range:** FY2017--FY2026 verified (117--162 files per year)

---

### 3. `army` -- U.S. Army

**Organization:** ASA(FM&C) -- Army Financial Management & Comptroller
**Site:** `asafm.army.mil`
**Discovery:** `discover_army_files()` -- Playwright browser crawl
**Access method:** Playwright browser (`BROWSER_REQUIRED_SOURCES`)
**WAF/Browser required:** Yes -- government WAF blocks plain HTTP

**URL template:**
```
https://www.asafm.army.mil/Budget-Materials/
```

**File types:** Excel (exhibits: `p1_display.xlsx`, `r1.xlsx`, `o1_display.xlsx`, etc.),
PDF (justification books)
**FY range:** FY2019--FY2026 verified via browser (39 files for FY2026)

---

### 4. `navy` -- U.S. Navy / Marine Corps

**Organization:** SECNAV FM&C -- Office of the Secretary of the Navy
**Site:** `secnav.navy.mil`
**Discovery:** `discover_navy_files()` -- Playwright browser crawl
**Access method:** Playwright browser (`BROWSER_REQUIRED_SOURCES`)
**WAF/Browser required:** Yes

**URL template (current fiscal years):**
```
https://www.secnav.navy.mil/fmc/Pages/Fiscal-Year-{fy}.aspx
```

**File types:** PDF (justification books -- Navy + Marine Corps separately),
Excel (exhibits)
**FY range:** FY2017--FY2026 verified (36--49 files per year). FY2017--FY2021 use
alternate URL pattern (auto-fallback supported).

---

### 5. `navy-archive` -- U.S. Navy Archive

**Organization:** SECNAV FM&C
**Site:** `secnav.navy.mil`
**Discovery:** `discover_navy_archive_files()` -- Playwright browser crawl
**Access method:** Playwright browser (`BROWSER_REQUIRED_SOURCES`)
**WAF/Browser required:** Yes

**URL (static archive page):**
```
https://www.secnav.navy.mil/fmc/fmb/Pages/archive.aspx
```

Used to retrieve older fiscal years not available on the main FY index page.

**File types:** PDF, Excel
**FY range:** FY1997--FY2025 per archive page (575+ files)

---

### 6. `airforce` -- U.S. Air Force / Space Force

**Organization:** SAF/FMC -- Secretary of the Air Force Financial Management
**Site:** `saffm.hq.af.mil`
**Discovery:** `discover_airforce_files()` -- Playwright browser crawl
**Access method:** Playwright browser (`BROWSER_REQUIRED_SOURCES`)
**WAF/Browser required:** Yes

**URL template:**
```
https://www.saffm.hq.af.mil/FM-Resources/Budget/Air-Force-Presidents-Budget-FY{fy2}/
```

(`fy2` = two-digit fiscal year, e.g. `26` for FY 2026)

**File types:** PDF (Air Force + Space Force justification books), Excel (exhibits)
**FY range:** FY1997--FY2026 per site sidebar; Space Force separated FY2021+.

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

## Agencies NOT Currently in Downloader

These DoD component agencies were evaluated for separate budget materials
not already available on `comptroller.war.gov`:

| Agency | Own Budget Page? | Unique Materials? | Recommendation |
|--------|-----------------|-------------------|----------------|
| DLA (dla.mil) | No | AFRs only | Skip -- J-Books on comptroller |
| MDA (mda.mil) | **Yes** | Budget Booklets/Overviews | **Consider adding** -- unique summary docs |
| SOCOM (socom.mil) | Partial | Financial Statements only | Skip -- J-Books on comptroller |
| DHA (health.mil) | Partial | AFRs + Budget Execution Reports | Low priority -- execution reports are supplementary |
| DISA (disa.mil) | Yes | AFRs + overview info | Skip -- J-Books on comptroller |
| NGB (nationalguard.mil) | **Yes** | PB Request Summaries, Appropriations Analyses | **Consider adding** -- unique NGB-LL summaries |

**Key findings:**
- All six agencies' J-Books are already captured via the `defense-wide` source
- **MDA** publishes unique "Budget Booklet" summary PDFs at `mda.mil/news/budget_information.html`
- **NGB** publishes unique Legislative Liaison summaries at `nationalguard.mil/.../Important-Documents/`
- The other four agencies only publish AFRs or financial statements (different document type)

---

## Coverage Matrix

| Source | FY2017 | FY2018 | FY2019 | FY2020 | FY2021 | FY2022 | FY2023 | FY2024 | FY2025 | FY2026 |
|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| comptroller  | 71 | 61 | 35 | 35 | 36 | 55 | 33 | 52 | 43 | 25 |
| defense-wide | 162 | 151 | 149 | 151 | 148 | 153 | 157 | 152 | 115 | 117 |
| army         | ? | ? | Y | Y | Y | Y | Y | Y | Y | 39 |
| navy         | 49 | 41 | 42 | 38 | 37 | 37 | 37 | 36 | 36 | 36 |
| navy-archive | 49 | 41 | 43 | 39 | 37 | 37 | 37 | 36 | 36 | -- |
| airforce     | ? | ? | Y | Y | Y | Y | Y | Y | Y | 25 |

Legend:
- **Number** = verified file count from `--list` output
- **Y** = site has FY tab/page (confirmed via browser), file count not enumerated
- **?** = site has historical years listed but not individually verified
- **--** = not available from this source for that year
- Navy FY2017--2021 use alternate URL `/fmc/fmb/Pages/` (auto-fallback supported)
- Navy archive file counts from `secnav.navy.mil/fmc/fmb/Pages/archive.aspx`

### Notes

1. **Comptroller & defense-wide** work via direct HTTP (no browser needed).
   Full coverage FY2017--FY2026 confirmed.
2. **Army & Air Force** require non-headless Playwright (`headless=False`) due to WAF.
   Sites are active with budget materials confirmed for FY2019--FY2026 (Army) and
   FY1997--FY2026 (Air Force).
3. **Navy main page** works in headless mode for FY2022--FY2026 (36--37 files each).
   FY2017--FY2021 use a different URL pattern with automatic fallback.
4. **Navy archive** is a SharePoint list with files for FY1997--FY2025 (575+ total files).

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

## Failure Log Schema (`failed_downloads.json`)

When downloads fail, `dod_budget_downloader.py` writes a
`failed_downloads.json` in the output directory. Each entry has the
following fields:

```json
{
  "url":        "<string> -- original download URL",
  "dest":       "<string> -- intended local file path",
  "filename":   "<string> -- sanitized filename",
  "error":      "<string> -- exception message or 'magic-byte verification failed'",
  "source":     "<string> -- source ID (e.g. 'army')",
  "year":       "<string> -- fiscal year (e.g. '2026')",
  "use_browser": "<bool>  -- true if Playwright browser was required",
  "timestamp":  "<string> -- ISO 8601 UTC timestamp of failure"
}
```

Use `--retry-failures [PATH]` to re-attempt all entries in this file.

---

## Technical Notes

- **Downloadable extensions:** `.pdf`, `.xlsx`, `.xls`, `.zip`, `.csv`
- **Ignored hosts:** `dam.defense.gov`
- **Default output directory:** `DoD_Budget_Documents/`
- **Browser-required sources:** `army`, `navy`, `navy-archive`, `airforce` (government WAF blocks plain HTTP)
- **File integrity:** `_verify_download()` checks magic bytes after every download; corrupt files are deleted and retried
- **Failure log:** `failed_downloads.json` written to output dir; use `--retry-failures` to re-attempt

---

## Notes on Coverage

- **Historical years:** Comptroller and Defense-Wide tend to have documents back to
  FY2017 or earlier. Service sites (Army, Navy, Air Force) may have different historical
  depth. Older years may use different URL patterns.

- **Missing agencies:** The following agencies publish budget materials but are not
  yet directly sourced (they may appear under Defense-Wide):
  - Defense Logistics Agency (DLA)
  - Missile Defense Agency (MDA)
  - Defense Health Agency (DHA)
  - Defense Information Systems Agency (DISA)
  - Special Operations Command (SOCOM)

- **File types:** Most exhibits are published as `.xlsx`. PDFs are typically budget
  justification narratives. ZIP files may contain batches of exhibits that are
  automatically extracted after download.

---

See also [Exhibit Types](exhibit-types.md) for a catalog of document types, and
[Getting Started](getting-started.md) for download instructions.
