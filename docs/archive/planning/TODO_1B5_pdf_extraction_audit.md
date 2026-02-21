# Step 1.B5 — PDF Text Extraction Quality Audit

**Status:** Not started
**Type:** Research + Code modification (ENVIRONMENT TESTING required)
**Depends on:** Downloaded PDF files in `DoD_Budget_Documents/`

## Overview

Assess pdfplumber extraction quality across different PDF layouts and
implement targeted improvements for poorly-extracting documents.

---

## Sub-tasks

### 1.B5-a — Write PDF quality audit script
**Type:** AI-agent (script creation)
**Estimated tokens:** ~600 output

Write `scripts/pdf_quality_audit.py` (~60 lines) that:
1. Walks `DoD_Budget_Documents/` for `.pdf` files
2. For each PDF: extract text with pdfplumber, compute quality metrics:
   - Text length per page (flag if < 50 chars = likely image/scan)
   - Non-ASCII character ratio (flag if > 10%)
   - Table detection count
3. Output summary report to `docs/pdf_audit_report.md`
4. Group results by source/exhibit type

**Token-efficient tip:** Process in batches, only report summaries.

---

### 1.B5-b — Run audit and document findings
**Type:** ENVIRONMENT TESTING (requires downloaded PDFs)
**Estimated tokens:** ~500 output

1. Run `scripts/pdf_quality_audit.py`
2. Manually inspect 5-10 worst-scoring pages
3. Categorize issues: garbled text, missed tables, OCR needed, layout problems
4. Document in `docs/pdf_audit_report.md`

---

### 1.B5-c — Improve table extraction settings
**Type:** AI-agent (code modification)
**Estimated tokens:** ~600 output
**Depends on:** 1.B5-b (need to know which layouts fail)

For pages where `extract_tables()` fails:
1. Try alternative `table_settings`:
   - `{"vertical_strategy": "text", "horizontal_strategy": "text"}`
   - Custom line tolerances
2. Implement `_extract_tables_with_fallback(page)` that tries primary → alternate
3. Log which strategy succeeded for debugging

**File:** `build_budget_db.py` — modify `ingest_pdf_file()`

---

### 1.B5-d — Extract structured data from narrative sections
**Type:** AI-agent (code modification)
**Estimated tokens:** ~800 output
**Depends on:** 1.B5-b (lower priority)

R-2/R-3 exhibits contain program descriptions and milestones:
1. Detect section headers (bold text, larger font) in PDF text
2. Capture header + associated text blocks as structured entries
3. Store in `pdf_pages.table_data` as JSON with section labels

**File:** `build_budget_db.py` — modify `ingest_pdf_file()`

---

### 1.B5-e — Fix ingested_files INSERT bug
**Type:** AI-agent (bug fix)
**Estimated tokens:** ~200 output

The INSERT for `ingested_files` provides 6 values but the table has 8 columns
(line ~600 in build_budget_db.py). Fix to include all required columns.

**File:** `build_budget_db.py` — ~line 600

---

### 1.B5-f — Update methodology wiki page
**Type:** AI-agent (documentation)
**Estimated tokens:** ~400 output
**Depends on:** 1.B5-b

Update `docs/wiki/Methodology.md`:
1. Document PDF extraction approach (pdfplumber + fallbacks)
2. Document known quality limitations by source/layout
3. Add link to `docs/pdf_audit_report.md`

---

## Annotations

- 1.B5-a can be written without downloaded files (just the script)
- 1.B5-b requires running against real PDFs
- 1.B5-c and 1.B5-d depend on audit findings
- 1.B5-e is a standalone bug fix — do anytime
- TOKEN EFFICIENCY: Audit script runs locally, only summary enters context
