# Step 1.A1 — Audit Existing Downloader Coverage

**Status:** Not started
**Type:** Research + Documentation (multi-step)
**Depends on:** None

## Overview

Catalog every source `dod_budget_downloader.py` currently supports and identify
gaps in agency/service coverage.

---

## Sub-tasks

### 1.A1-a — Run coverage audit script
**Type:** ENVIRONMENT TESTING (requires network + downloader working)
**Estimated tokens:** ~500 output

1. Run `python dod_budget_downloader.py --list --years all --sources all`
2. Capture output to `coverage_audit_output.txt`
3. Write a standalone script (`scripts/coverage_audit.py`, ~40 lines) that
   parses the listing and produces a coverage matrix (source × FY × file count)
4. Save matrix to `docs/coverage_matrix.md`

**Token-efficient tip:** Pipe downloader output to a file, parse that file.

---

### 1.A1-b — Research missing DoD component sources
**Type:** Web research (AI-agent with web access)
**Estimated tokens:** ~800 output

Check whether these agencies publish budget materials at a distinct URL:

| Agency | Search pattern | Notes |
|--------|---------------|-------|
| Defense Logistics Agency (DLA) | `site:dla.mil budget justification` | |
| Missile Defense Agency (MDA) | `site:mda.mil budget justification` | Standalone exhibits? |
| SOCOM | `site:socom.mil budget` | |
| Defense Health Agency (DHA) | `site:health.mil budget` | |
| DISA | `site:disa.mil budget` | |
| National Guard Bureau | `site:nationalguard.mil budget` | |
| Marine Corps (standalone) | `site:hqmc.marines.mil budget` | Separate from Navy? |

For each found: document URL, file formats, whether WAF-protected, FY range.

**Output:** Update `docs/wiki/Data-Sources.md` with "## Agencies Not Yet Covered" section.

---

### 1.A1-c — Verify Defense-Wide J-Book completeness
**Type:** ENVIRONMENT TESTING (requires network)
**Estimated tokens:** ~400 output

1. Run `--list --years 2026 --sources defense-wide`
2. Compare file list against known J-Books (OUSD(C), DARPA, DTRA, MDA, WHS,
   OTE, DHA, DLA, DISA)
3. Document which J-Books are captured vs. missing

---

### 1.A1-d — Update documentation with audit findings
**Type:** AI-agent (documentation)
**Estimated tokens:** ~600 output
**Depends on:** 1.A1-a, 1.A1-b, 1.A1-c

1. Update `docs/wiki/Data-Sources.md` coverage matrix with actual file counts
2. Add "Known Gaps" section listing missing agencies/years
3. Update `docs/wiki/Methodology.md` data collection section with source list

---

## Annotations

- Sub-tasks 1.A1-a and 1.A1-c require network access
- Sub-task 1.A1-b requires web search capability
- Sub-task 1.A1-d is pure documentation (depends on a/b/c findings)
- Results feed into: 1.A5 (Document Data Sources), 1.A2 (Expand FY Coverage)
