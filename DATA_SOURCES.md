# DoD Budget Data Sources Documentation

## Overview

This document describes all configured data sources for the DoD Budget Analysis Tool, including base URLs, file patterns, supported fiscal years, and access requirements.

---

## 1. Comptroller (DoD Office of the Under Secretary of Defense - Comptroller)

**Source ID**: `comptroller`
**Organization**: DoD Comptroller (OUSD-C)
**Primary Content**: DoD Summary Budget Documents, Green Book, Overview of Budget documents

### Base URL Pattern
```
https://comptroller.defense.gov/Budget-Materials/FY{YEAR}/
```

### Available Files
- Summary budget justification documents (PDF)
- Green Book (budget overview) - typically 100-200 MB PDF
- Budget highlights (PDF) - executive summary
- General information exhibit (PDF)

### Fiscal Years Confirmed
- FY 2017–2026 (continuous coverage)
- Some years available back to FY 2012 via Wayback Machine

### File Types
- PDF (primary)
- Excel tables (supplemental on some pages)

### Access Requirements
- Public domain (no authentication required)
- Direct HTTP access available
- Site accessed via beautifulsoup4 HTML scraping

### Notes
- Comptroller site reorganizes annually; URL patterns consistent within fiscal year
- Files are large (50-300 MB); recommend incremental downloads
- Some documents hosted on subdomains (e.g., `.mil/fmb/` for budget materials)

---

## 2. Defense-Wide Services (Unified Defense-Wide Budget Materials)

**Source ID**: `defense-wide`
**Organization**: DoD Comptroller (Defense-Wide section)
**Primary Content**: Defense-wide justification books, agency budget materials

### Base URL Pattern
```
https://comptroller.defense.gov/Budget-Materials/FY{YEAR}/BudgetJustification/
```

### Available Files
- Defense-wide summary justification book (PDF)
- Individual agency justification books (PDFs) - available as links on the main page
- Exhibit files for defense-wide accounts

### Fiscal Years Confirmed
- FY 2018–2026 (continuous coverage)
- FY 2017 available with slightly different URL structure

### File Types
- PDF (primary)

### Access Requirements
- Public domain
- Direct HTTP access

### Notes
- Page contains links to sub-agency PDF documents (DIA, NSA, NRO, DISA, etc.)
- Recommend parsing page HTML to auto-discover individual PDFs
- File sizes: 10-50 MB per document

---

## 3. United States Army (ASA(FM&C) - Army Financial Management & Comptroller)

**Source ID**: `army`
**Organization**: U.S. Army
**Primary Content**: Army budget justification books, exhibit tables, historical data

### Base URL Pattern
```
https://asafm.army.mil/Budget/BudgetMaterials/FY{YEAR}/
```

### Available Files
- Army budget justification book (PDF) - primary source document
- Exhibit tables (Excel) - structured budget data
- Historical budget summaries (CSV/Excel)

### Fiscal Years Confirmed
- FY 2018–2026 (confirmed continuous)
- FY 2017 available (URL differs slightly)
- FY 2016 and earlier available but require manual lookup

### File Types
- PDF (justification books)
- Excel/CSV (exhibits)

### Access Requirements
- Public domain (.mil site, no authentication)
- May require session management if behind firewall

### Notes
- Army site structure is relatively stable year-over-year
- Excel exhibits follow consistent naming pattern (e.g., "O1_display.xlsx")
- Largest documents in the database (justification book ~200 MB)

---

## 4. United States Navy & Marine Corps (SECNAV FM&C - Financial Management & Comptroller)

**Source ID**: `navy`
**Organization**: U.S. Navy
**Primary Content**: Navy/Marine Corps budget justification, exhibit data

### Base URL Pattern
```
https://www.secnav.navy.mil/fmc/fmb/Documents/FY{YEAR}/
```

### Available Files
- Navy budget justification book (PDF)
- Marine Corps budget justification book (PDF)
- Exhibit tables (Excel)
- Historical budget data

### Fiscal Years Confirmed
- FY 2019–2026 (confirmed continuous on secnav domain)
- FY 2018 and earlier available at alternate URL (see below)

### Alternate Base URL (older fiscal years)
```
https://www.secnav.navy.mil/fmc/fmb/Documents/fy{year}/
```

### File Types
- PDF (justification books, ~150-200 MB each)
- Excel (exhibits)

### Access Requirements
- Public domain (.mil site)
- Standard HTTP access

### Notes
- Two separate justification books (Navy + Marine Corps), each ~150 MB
- URL pattern differs slightly for FY 2018 and earlier (lowercase "fy" vs "FY")
- Exhibits include both budget and personnel data

---

## 5. United States Air Force & Space Force (SAF/FMC - Financial Management & Comptroller)

**Source ID**: `airforce`
**Organization**: U.S. Air Force
**Primary Content**: Air Force and Space Force budget justification, exhibit tables

### Base URL Pattern
```
https://www.saffm.hq.af.mil/Budget/FY{YEAR}/
```

### Available Files
- Air Force budget justification book (PDF)
- Space Force budget justification book (PDF) - separated in FY 2021+
- Exhibit tables (Excel)
- Historical budget submissions (CSV)

### Fiscal Years Confirmed
- FY 2019–2026 (continuous)
- FY 2018 and earlier at slightly different URL

### File Types
- PDF (150-180 MB per book)
- Excel (exhibits)
- CSV (supplemental historical data)

### Access Requirements
- Public domain (.mil site)
- Standard HTTP access

### Notes
- Space Force separated as distinct service starting FY 2021
- Prior to FY 2021, Space Force budget was part of Air Force RDT&E
- URL structure consistent year-over-year (FY 2019+)

---

## Historical Coverage Summary

| Fiscal Year | Comptroller | Defense-Wide | Army | Navy | Air Force |
|-------------|:-----------:|:------------:|:----:|:----:|:---------:|
| FY 2026     | ✓ | ✓ | ✓ | ✓ | ✓ |
| FY 2025     | ✓ | ✓ | ✓ | ✓ | ✓ |
| FY 2024     | ✓ | ✓ | ✓ | ✓ | ✓ |
| FY 2023     | ✓ | ✓ | ✓ | ✓ | ✓ |
| FY 2022     | ✓ | ✓ | ✓ | ✓ | ✓ |
| FY 2021     | ✓ | ✓ | ✓ | ✓ | ✓ |
| FY 2020     | ✓ | ✓ | ✓ | ✓ | ✓ |
| FY 2019     | ✓ | ✓ | ✓ | ✓ | ✓ |
| FY 2018     | ✓ | ~ | ✓ | ✓ | ✓ |

Legend: ✓ = confirmed available, ~ = available with alternate URL

---

**Last Updated**: 2026-02-18
**Document Version**: 1.0
