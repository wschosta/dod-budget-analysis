# Data Sources Reference

This document catalogs every data source used by the DoD Budget Explorer, including URL patterns, file formats, fiscal-year availability, and download requirements.

---

## Source Overview

| Source | URL Base | Method | FY Range | Files |
|--------|----------|--------|----------|-------|
| Comptroller | `comptroller.war.gov` | HTTP | FY1998-FY2026 | 869 |
| Defense-Wide | `comptroller.war.gov` | HTTP | FY2000-FY2026 | 3,977 |
| US Army | `asafm.army.mil` | Browser (Playwright) | FY1998-FY2026 | 870 |
| US Navy | `secnav.navy.mil` | Browser (Playwright) | FY2022-FY2026 | 182 |
| US Navy Archive | `secnav.navy.mil` | Browser + SharePoint API | FY1998-FY2026 | 1,097 |
| US Air Force | `saffm.hq.af.mil` | Browser (Playwright) | FY1998-FY2026 | 853 |

**Total: ~7,848 tracked files across 6 sources.**

---

## Sources

### 1. Comptroller (Budget Summary Exhibits)

The DoD Comptroller publishes summary-level budget exhibits covering all services.

- **Discovery URL:** `https://comptroller.war.gov/Budget-Materials/`
- **File URL pattern:** `https://comptroller.war.gov/Budget-Materials/FY{year}/...`
- **Download method:** HTTP (no browser required)
- **File formats:** XLSX, PDF
- **Exhibit types:** P-1, P-1R, R-1, O-1, M-1, C-1, RF-1
- **FY coverage:** FY1998-FY2026 (29 years, 869 files)
- **Notes:** Some older fiscal years only publish `_display.xlsx` variants. The pipeline retains display files when no base file exists in the same directory.

### 2. Defense-Wide (Budget Justification Detail)

Defense-Wide covers OSD, DARPA, MDA, DISA, DHA, and other defense agencies.

- **Discovery URL:** `https://comptroller.war.gov/Budget-Materials/FY{year}BudgetJustification/`
- **Download method:** HTTP (no browser required)
- **File formats:** PDF, XLSX
- **Exhibit types:** R-2, R-3, P-5, and agency-specific justification books
- **FY coverage:** FY2000-FY2026 (26 years, 3,977 files)
- **Notes:** Largest source by file count. Contains detailed PE-level justifications with narrative text used for enrichment (tags, descriptions, lineage).

### 3. US Army

- **Discovery URL:** `https://www.asafm.army.mil/Budget-Materials/`
- **Download method:** Browser-required (Playwright/Chromium). Site has WAF protection.
- **File formats:** PDF, XLSX
- **FY coverage:** FY1998-FY2026 (25 years, 870 files)
- **Notes:** Files discovered by filtering links matching `/{year}/` pattern. Requires Playwright with Chromium for WAF bypass.

### 4. US Navy

- **Discovery URL:** `https://www.secnav.navy.mil/fmc/Pages/Fiscal-Year-{year}.aspx`
- **Fallback URL (FY2017-2021):** `https://www.secnav.navy.mil/fmc/fmb/Pages/Fiscal-Year-{year}.aspx`
- **Download method:** Browser-required (Playwright/Chromium)
- **File formats:** PDF, XLSX
- **FY coverage:** FY2022-FY2026 (5 years, 182 files)
- **Notes:** Only recent fiscal years are available from the main Navy FMC site. Historical data is available via the Navy Archive source below.

### 5. US Navy Archive

- **Discovery URL:** `https://www.secnav.navy.mil/fmc/fmb/Pages/archive.aspx`
- **Download method:** Browser-required with SharePoint REST API
- **SharePoint List GUID:** `AE8ECF7F-2D4B-4077-8BE2-159CA7CEBBDF`
- **SharePoint site:** `https://www.secnav.navy.mil/fmc/fmb`
- **File formats:** PDF, XLSX
- **FY coverage:** FY1998-FY2026 (29 years, 1,097 files)
- **Notes:** Most comprehensive Navy source. Uses SharePoint REST API (`_api/web/lists(guid'...')/items`) with fallback to HTML link extraction if API is unavailable.

### 6. US Air Force / Space Force

- **Discovery URL:** `https://www.saffm.hq.af.mil/FM-Resources/Budget/Air-Force-Presidents-Budget-FY{yy}/`
- **Download method:** Browser-required (Playwright/Chromium)
- **File formats:** PDF, XLSX
- **FY coverage:** FY1998-FY2026 (29 years, 853 files)
- **Notes:** URL uses 2-digit fiscal year suffix (e.g., `FY26`). Discovery requires clicking "Expand All" to reveal nested file links. Includes Space Force budget materials for recent fiscal years.

---

## Exhibit Types

| Code | Full Name | Source Level | PE Numbers? |
|------|-----------|-------------|-------------|
| **R-1** | RDT&E Programs Summary | Comptroller | Yes (88.9%) |
| **R-2** | RDT&E PE Detail | Defense-Wide / Services | Yes |
| **P-1** | Procurement Programs Summary | Comptroller | No |
| **P-1R** | Procurement (Reserve Components) | Comptroller | No |
| **P-5** | Procurement Detail | Defense-Wide / Services | Yes |
| **O-1** | O&M Programs Summary | Comptroller | No |
| **M-1** | Military Personnel Summary | Comptroller | No |
| **C-1** | Military Construction | Comptroller | No |
| **RF-1** | Revolving Funds | Comptroller | No |
| **OGSI** | Overseas/Global Security & Intelligence | Comptroller | No |

**Note:** PE numbers are only available in R-1, R-2, and P-5 exhibits. Summary exhibits (P-1, O-1, M-1, C-1) use appropriation-level line items without PE identifiers. See [NOTICED_ISSUES #8/#53](../NOTICED_ISSUES.md) for details.

---

## File Formats

The downloader accepts these file extensions:

| Extension | Description |
|-----------|-------------|
| `.xlsx` | Modern Excel workbook (primary structured data source) |
| `.xls` | Legacy Excel workbook |
| `.pdf` | Budget justification documents (narrative text, R-2/R-3 detail) |
| `.csv` | Comma-separated data (rare) |
| `.zip` | Compressed archives containing the above formats |

---

## Known Coverage Gaps

| Gap | Explanation |
|-----|-------------|
| **FY2000-FY2009** | DoD budget documents for these years are not publicly available in structured digital format on government websites. |
| **FY2010-FY2011** | Minimal data (2-5 rows). Only partial exhibit files available. |
| **Navy FY1998-FY2021** | Available via Navy Archive source only (main Navy site covers FY2022+). |
| **DLA, SOCOM standalone** | Identified but not yet added as separate download sources. Budget data for these agencies is partially available through Defense-Wide justification books. |

---

## Download Pipeline

```
discover_fiscal_years()          # Find all available FY links
    |
    v
discover_{source}_files()        # Per-source file discovery
    |
    v
download_file() / download_with_browser()   # HTTP or Playwright
    |
    v
DoD_Budget_Documents/FY{year}/{source}/...  # Local storage
```

**CLI usage:**
```bash
python run_pipeline.py --skip-download    # Parse only (skip download)
python run_pipeline.py --rebuild          # Full rebuild from downloaded files
python run_pipeline.py --retry-failures   # Retry from failed_downloads.json
```

**Failure handling:** Failed downloads are logged to `failed_downloads.json` with URL, destination path, and browser-required flag. Use `--retry-failures` to re-attempt.

---

## Related Documentation

- [Pipeline Architecture](../../CLAUDE.md) - Build pipeline and database schema
- [API Reference](../../README.md) - REST API endpoints
- [NOTICED_ISSUES](../NOTICED_ISSUES.md) - Data quality issues and resolutions
