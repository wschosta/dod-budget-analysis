# Data Sources

Catalog of all DoD budget data sources configured in `dod_budget_downloader.py`.

> **Full reference:** See [DATA_SOURCES.md](../../DATA_SOURCES.md) in the project root for
> complete URL templates, JSON schema, file-integrity notes, and coverage matrix.

---

## Global Constants

| Constant | Value |
|----------|-------|
| `BASE_URL` | `https://comptroller.war.gov` |
| `BUDGET_MATERIALS_URL` | `https://comptroller.war.gov/Budget-Materials/` |
| `DOWNLOADABLE_EXTENSIONS` | `.pdf`, `.xlsx`, `.xls`, `.zip`, `.csv` |
| `IGNORED_HOSTS` | `dam.defense.gov` |
| `BROWSER_REQUIRED_SOURCES` | `army`, `navy`, `navy-archive`, `airforce` |

---

## Sources

| Source ID | Organization | Site | Access Method |
|-----------|-------------|------|---------------|
| `comptroller` | DoD Comptroller (OUSD-C) | `comptroller.war.gov` | Direct HTTP |
| `defense-wide` | DoD Comptroller (Defense-Wide) | `comptroller.war.gov` | Direct HTTP |
| `army` | ASA(FM&C) — U.S. Army | `asafm.army.mil` | Playwright browser |
| `navy` | SECNAV FM&C — U.S. Navy | `secnav.navy.mil` | Playwright browser |
| `navy-archive` | SECNAV FM&C — Navy Archive | `secnav.navy.mil` | Playwright browser |
| `airforce` | SAF/FMC — Air Force / Space Force | `saffm.hq.af.mil` | Playwright browser |

### `comptroller`

- **Base URL:** `https://comptroller.war.gov/Budget-Materials/`
- **Discovery:** `discover_fiscal_years()` crawls FY index; `discover_comptroller_files()` crawls each year's page
- **Formats:** PDF, Excel (`.xlsx`, `.xls`), ZIP
- **FY range:** Dynamically discovered (typically FY 2017–current)

### `defense-wide`

- **URL pattern:** `https://comptroller.war.gov/Budget-Materials/FY{fy}BudgetJustification/`
- **Discovery:** `discover_defense_wide_files()` — direct HTTP crawl
- **Formats:** PDF (primary), Excel
- **FY range:** FY 2017–current

### `army`

- **URL:** `https://www.asafm.army.mil/Budget-Materials/`
- **Discovery:** `discover_army_files()` — Playwright browser (WAF-protected)
- **Formats:** Excel exhibits (`p1_display.xlsx`, `r1.xlsx`, etc.), PDF justification books
- **FY range:** FY 2018–current

### `navy`

- **URL pattern:** `https://www.secnav.navy.mil/fmc/Pages/Fiscal-Year-{fy}.aspx`
- **Discovery:** `discover_navy_files()` — Playwright browser (WAF-protected)
- **Formats:** PDF (separate Navy + Marine Corps books), Excel exhibits
- **FY range:** FY 2019–current

### `navy-archive`

- **URL:** `https://www.secnav.navy.mil/fmc/fmb/Pages/archive.aspx`
- **Discovery:** `discover_navy_archive_files()` — Playwright browser
- **Formats:** PDF, Excel
- **FY range:** FY 2017–2018 (older years not on the main FY index)

### `airforce`

- **URL pattern:** `https://www.saffm.hq.af.mil/FM-Resources/Budget/Air-Force-Presidents-Budget-FY{fy2}/`
- **Discovery:** `discover_airforce_files()` — Playwright browser (WAF-protected)
- **Formats:** PDF (Air Force + Space Force justification books), Excel exhibits
- **FY range:** FY 2019–current (Space Force separated FY 2021+)

---

## Coverage Matrix

<!-- TODO [Step 1.A5-c]: Fill in after running downloader audit (Step 1.A1) -->
<!-- Values marked with ~ are unverified estimates; blank = not expected     -->

| Source | FY2017 | FY2018 | FY2019 | FY2020 | FY2021 | FY2022 | FY2023 | FY2024 | FY2025 | FY2026 |
|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| comptroller  | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ |
| defense-wide | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ |
| army         |   | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ |
| navy         |   |   | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ |
| navy-archive | ~ | ~ |   |   |   |   |   |   |   |   |
| airforce     |   |   | ~ | ~ | ~ | ~ | ~ | ~ | ~ | ~ |

---

## Technical Notes

- **Downloadable extensions:** `.pdf`, `.xlsx`, `.xls`, `.zip`, `.csv`
- **Ignored hosts:** `dam.defense.gov`
- **Default output directory:** `DoD_Budget_Documents/`
- **Browser-required sources:** `army`, `navy`, `navy-archive`, `airforce` (government WAF blocks plain HTTP)
- **File integrity:** `_verify_download()` checks magic bytes after every download; corrupt files are deleted and retried
- **Failure log:** `failed_downloads.json` written to output dir; use `--retry-failures` to re-attempt
- **Browser-required sources:** Army, Navy, Air Force (government WAF blocks plain HTTP)

---

## Notes on Coverage

- **Coverage matrix:** The matrix above shows nominal coverage. Actual file counts depend
  on network access to each source. Run `python dod_budget_downloader.py --list --years all
  --sources all` to populate actual counts.

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
