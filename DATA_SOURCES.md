# DoD Budget Data Sources

> Reference document for every URL pattern, document type, and fiscal-year
> availability used by `dod_budget_downloader.py`.

<!-- TODO 1.A5-a: Fill in each section below from live testing results.
     Most of the raw information is in dod_budget_downloader.py's
     SERVICE_PAGE_TEMPLATES and discover_*_files() functions — extract,
     verify, and format here. -->

---

## Currently Supported Sources

### 1. Comptroller (Main DoD Summary)

| Field | Value |
|-------|-------|
| **Base URL** | `https://comptroller.war.gov/Budget-Materials/` |
| **URL pattern per FY** | Dynamic — discovered via links on the Budget Materials page |
| **File types** | PDF, XLSX, ZIP |
| **FY coverage confirmed** | <!-- TODO: fill from 1.A2-a results --> |
| **Access method** | HTTP (requests) — no WAF issues observed |
| **Notes** | Main entry point. Lists fiscal year links; each FY page links to downloadable documents. |

### 2. Defense-Wide (Budget Justification Books)

| Field | Value |
|-------|-------|
| **Base URL** | `https://comptroller.war.gov/Budget-Materials/FY{fy}BudgetJustification/` |
| **URL pattern per FY** | Replace `{fy}` with 4-digit year (e.g., `2026`) |
| **File types** | PDF, XLSX |
| **FY coverage confirmed** | <!-- TODO: fill from 1.A2-a results --> |
| **Access method** | HTTP (requests) |
| **Notes** | Contains individual agency J-Books. <!-- TODO 1.A1-c: verify completeness --> |

### 3. US Army

| Field | Value |
|-------|-------|
| **Base URL** | `https://www.asafm.army.mil/Budget-Materials/` |
| **URL pattern per FY** | Single page; FY is filtered by URL path containing `/{year}/` |
| **File types** | PDF, XLSX |
| **FY coverage confirmed** | <!-- TODO: fill from 1.A2-c results --> |
| **Access method** | Browser required (Playwright) — WAF/bot protection |
| **Notes** | Requires "Expand All" not needed; uses URL text_filter for year. |

### 4. US Navy / Marine Corps

| Field | Value |
|-------|-------|
| **Base URL** | `https://www.secnav.navy.mil/fmc/Pages/Fiscal-Year-{fy}.aspx` |
| **URL pattern per FY** | Replace `{fy}` with 4-digit year |
| **File types** | PDF, XLSX |
| **FY coverage confirmed** | <!-- TODO: fill from 1.A2-c results --> |
| **Access method** | HTTP (requests) |
| **Notes** | Separate page per FY. |

### 5. US Air Force / Space Force

| Field | Value |
|-------|-------|
| **Base URL** | `https://www.saffm.hq.af.mil/FM-Resources/Budget/Air-Force-Presidents-Budget-FY{fy2}/` |
| **URL pattern per FY** | Replace `{fy2}` with 2-digit year (e.g., `26`) |
| **File types** | PDF, XLSX |
| **FY coverage confirmed** | <!-- TODO: fill from 1.A2-c results --> |
| **Access method** | Browser required (Playwright) — WAF/bot protection |
| **Notes** | Uses "Expand All" button on page. Filters by `FY{fy2}` in link URL. |

---

## Potential Additional Sources

<!-- TODO 1.A1-b: Investigate each of these. For any that have their own
     budget materials page, add a full entry above and a new discover_*_files()
     function in dod_budget_downloader.py. -->

| Agency | Possible URL | Status |
|--------|-------------|--------|
| Defense Logistics Agency (DLA) | `dla.mil` | Not investigated |
| Missile Defense Agency (MDA) | `mda.mil` | Not investigated |
| US Special Operations Command (SOCOM) | `socom.mil` | Not investigated |
| Defense Health Agency (DHA) | `health.mil` | Not investigated |
| Defense Information Systems Agency (DISA) | `disa.mil` | Not investigated |
| National Guard Bureau | `nationalguard.mil` | Not investigated |

---

## File Type Reference

| Extension | Description | Typical Content |
|-----------|-------------|-----------------|
| `.xlsx` | Excel workbook | Budget exhibit data (P-1, R-1, O-1, etc.) — primary structured data source |
| `.pdf` | PDF document | Narrative justifications (R-2, R-3, R-4), summary exhibits, J-Books |
| `.zip` | ZIP archive | Bundled collections of Excel and/or PDF files |
| `.xls` | Legacy Excel | Older fiscal year data in pre-2007 Excel format |
| `.csv` | Comma-separated values | Rare; occasionally used for supplemental data |

---

## Fiscal Year Coverage Matrix

<!-- TODO 1.A2-a: Fill this matrix after running the audit.
     Run: python dod_budget_downloader.py --list --years all --sources all
     and tabulate which (source, FY) combinations produce files. -->

| FY | Comptroller | Defense-Wide | Army | Navy | Air Force |
|----|:-----------:|:------------:|:----:|:----:|:---------:|
| 2026 | | | | | |
| 2025 | | | | | |
| 2024 | | | | | |
| 2023 | | | | | |
| 2022 | | | | | |
| 2021 | | | | | |
| 2020 | | | | | |
| 2019 | | | | | |
| 2018 | | | | | |
| 2017 | | | | | |
