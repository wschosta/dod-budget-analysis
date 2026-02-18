# Data Sources

Catalog of all DoD budget data sources used by the downloader (`dod_budget_downloader.py`).

> **Current Status:** Phase 1.A, Step 1.A5 — In Progress. Full coverage matrix needs completion.
> See [DATA_SOURCES.md](../../DATA_SOURCES.md) in the root for detailed TODO items.

---

## Comptroller (comptroller.war.gov)

- **Base URL:** `https://comptroller.war.gov/Budget-Materials/`
- **Content:** Defense-wide summary exhibits, rollup documents
- **Formats:** Excel (`.xlsx`), PDF (`.pdf`)
- **Discovery:** Automatic link crawling from budget materials index
- **Access method:** Direct HTTP requests

## Defense-Wide

- **URL pattern:** `https://comptroller.war.gov/Budget-Materials/FY{fy}BudgetJustification/`
- **Content:** Defense-wide agency justification books
- **Formats:** Excel (`.xlsx`), PDF (`.pdf`)
- **Discovery:** Automatic link crawling per fiscal year
- **Access method:** Direct HTTP requests

## US Army (asafm.army.mil)

- **URL pattern:** `https://www.asafm.army.mil/Budget-Materials/`
- **Content:** Army budget justification exhibits
- **Formats:** Excel (`.xlsx`), PDF (`.pdf`)
- **Discovery:** Browser-based link extraction (WAF-protected)
- **Access method:** Playwright browser (`BROWSER_REQUIRED_SOURCES`)

## US Navy (secnav.navy.mil)

- **URL pattern:** `https://www.secnav.navy.mil/fmc/Pages/Fiscal-Year-{fy}.aspx`
- **Alternate source:** `https://www.secnav.navy.mil/fmc/fmb/Pages/archive.aspx`
- **Content:** Navy and Marine Corps budget exhibits
- **Formats:** Excel (`.xlsx`), PDF (`.pdf`)
- **Discovery:** Browser-based link extraction (WAF-protected)
- **Access method:** Playwright browser (`BROWSER_REQUIRED_SOURCES`)

## US Air Force / Space Force (saffm.hq.af.mil)

- **URL pattern:** `https://www.saffm.hq.af.mil/FM-Resources/Budget/Air-Force-Presidents-Budget-FY{fy2}/`
- **Content:** Air Force and Space Force budget exhibits
- **Formats:** Excel (`.xlsx`), PDF (`.pdf`)
- **Discovery:** Browser-based link extraction (WAF-protected)
- **Access method:** Playwright browser (`BROWSER_REQUIRED_SOURCES`)

---

## Coverage Matrix

<!-- TODO [Step 1.A5]: Fill in after running the downloader against each source
     and recording discovered file counts per fiscal year. -->

| Source | FY2017 | FY2018 | FY2019 | FY2020 | FY2021 | FY2022 | FY2023 | FY2024 | FY2025 | FY2026 |
|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| Comptroller | | | | | | | | | | |
| Defense-Wide | | | | | | | | | | |
| Army | | | | | | | | | | |
| Navy | | | | | | | | | | |
| Air Force | | | | | | | | | | |

---

## Technical Notes

- **Downloadable extensions:** `.pdf`, `.xlsx`, `.xls`, `.zip`, `.csv`
- **Ignored hosts:** `dam.defense.gov`
- **Default output directory:** `DoD_Budget_Documents/`
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
