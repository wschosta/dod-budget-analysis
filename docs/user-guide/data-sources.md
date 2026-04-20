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

## Program Element (PE) Number Structure

A Program Element is the DoD's atomic budgeting unit — the identifier that links RDT&E funding, narrative descriptions, and lineage across fiscal years. PE numbers follow a fixed positional format defined by [DoD 7045.7-H (FYDP Structure Handbook)](https://acqnotes.com/acqnote/acquisitions/program-element-pe).

**Format:** 7 digits + 1–3-character alphanumeric suffix (8–10 total characters).

| Position | Length | Meaning |
|----------|--------|---------|
| 1–2 | 2 digits | **Major Force Program (MFP)** — e.g. `01` Strategic Forces, `02` General Purpose Forces, `06` RDT&E, `07` Central Supply & Maintenance, `08` Training, `09` Admin & Assoc. |
| 3 | 1 digit | **Budget Activity (BA)** — for MFP 06 (RDT&E): `1` Basic Research, `2` Applied Research, `3` Advanced Technology Development, `4` Advanced Component Development & Prototypes, `5` System Development & Demonstration, `6` RDT&E Management Support, `7` Operational System Development. |
| 4–7 | 4 digits | **Unique identifier** within the (MFP, BA) group. |
| 8+ | 1–3 chars | **Service / Agency suffix** (see table below). |

### Service / Agency Suffix

The trailing letter(s) identify the owning service or defense agency. Standard suffixes are 1–2 letters; Defense-Wide sub-components use a letter-digit-letter form (e.g. `D8Z`).

| Suffix | Agency / Service |
|--------|------------------|
| `A` | Army |
| `N` | Navy |
| `M` | Marine Corps |
| `F` | Air Force |
| `SF` | Space Force (newer — created 2019; some `F`-suffixed PEs were rebranded to `SF` over time) |
| `D` | Office of the Secretary of Defense (OSD) / Defense-Wide (also used as the first letter of `D#X` sub-codes) |
| `E` | DARPA (Defense Advanced Research Projects Agency) |
| `K` | DISA (Defense Information Systems Agency) |
| `C` | Chemical / Biological Defense (CBDP); also appears on some historical rollups |
| `D8X`, `D8W`, `D8Z`, … | Defense-Wide sub-components (first letter `D` = OSD/Def-Wide; middle digit + trailing letter identify the specific agency like MDA, DLA, DHA) |

**Parser note:** `utils/patterns.py` defines `PE_SUFFIX_PATTERN = r'(?:[A-Z]{1,2}|[A-Z]\d[A-Z])'` to match both standard and Defense-Wide forms. When validating org-code assignments, compare the **first letter of the suffix** to the organization code — for `0603183D8Z` the service/agency letter is `D`, not `Z`.

**Example decompositions:**

- `0602702E` → MFP `06` (RDT&E), BA `2` (Applied Research), ID `702`, suffix `E` (DARPA)
- `0801273F` → MFP `08` (Training), BA `0` + ID `1273`, suffix `F` (Air Force)
- `0603183D8Z` → MFP `06` (RDT&E), BA `3` (Advanced Tech Dev), ID `183`, suffix `D8Z` (Defense-Wide sub-component)

**Legacy parser artifacts:** FY2005–FY2010 Comptroller summary Excel files occasionally had column misalignment that leaked numeric codes (`2`, `92`, `9999999`) or single letters that don't match the PE suffix into `organization_name`. `scripts/repair_database.py` step 14 nulls these. See [NOTICED_ISSUES #66](../NOTICED_ISSUES.md#66-legacy-parser-org-code-misalignment).

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
python scripts/run_pipeline.py --skip-download    # Parse only (skip download)
python scripts/run_pipeline.py --rebuild          # Full rebuild from downloaded files
python scripts/run_pipeline.py --retry-failures   # Retry from failed_downloads.json
```

**Failure handling:** Failed downloads are logged to `failed_downloads.json` with URL, destination path, and browser-required flag. Use `--retry-failures` to re-attempt.

---

## Related Documentation

- [Pipeline Architecture](../../CLAUDE.md) - Build pipeline and database schema
- [API Reference](../../README.md) - REST API endpoints
- [NOTICED_ISSUES](../NOTICED_ISSUES.md) - Data quality issues and resolutions
