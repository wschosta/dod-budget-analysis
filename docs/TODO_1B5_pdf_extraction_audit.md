# Step 1.B5 — PDF Text Extraction Quality Audit

**Status:** Not started
**Type:** Research + Code modification (needs environment testing)
**Depends on:** Downloaded PDF files must exist locally

## Task

Review `pdfplumber` output for the most common PDF layouts. Identify tables
that extract poorly and implement targeted improvements or fallback strategies.

## Current State

- `ingest_pdf_file()` uses `pdfplumber` to extract text and tables page-by-page
- No quality metrics or validation on extracted content
- Some DoD PDFs use complex multi-column layouts that may extract poorly

## Agent Instructions

### Phase 1 — Audit (needs environment + downloaded files)
1. Pick 5-10 representative PDFs across different sources and exhibit types
2. Run `pdfplumber` extraction on each and compare output to the visual PDF
3. Score each: text quality (0-10), table extraction quality (0-10)
4. Document patterns that extract well vs. poorly
5. Save sample outputs to `tests/fixtures/pdf_extraction_samples/`

### Phase 2 — Improvements (AI-agent completable after audit)
1. For poorly-extracting layouts, try alternative strategies:
   - Adjust `pdfplumber` table extraction settings (explicit_vertical_lines, etc.)
   - Try `camelot` as a fallback for specific table layouts
   - Consider OCR (`pytesseract`) for scanned PDFs if any are found
2. Implement a `_extract_with_fallback()` function that tries the primary
   strategy first, then falls back

## Annotations

- **DATA PROCESSING:** Requires the `DoD_Budget_Documents/` directory to be
  populated with real PDF files
- **ENVIRONMENT TESTING:** Must run `pdfplumber` against real files to assess
  quality — cannot be done without the files present
- **TOKEN EFFICIENCY:** For the audit phase, run a small Python script that
  extracts and scores pages, then report the summary. Don't read full PDF
  content into the conversation context.
- Split into two sessions: audit first, then implement fixes based on findings
