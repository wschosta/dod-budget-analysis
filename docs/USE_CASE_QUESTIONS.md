# Database Use-Case Questions & Clarifications

**Date:** 2026-02-20
**Context:** After reviewing the codebase, LION improvements, API routes, and GUI data flows,
the following questions will help guide the next round of database and enrichment improvements.

---

## 1. PE Number as Primary Key: Scope & Granularity

The system currently treats a PE number (e.g., `0602702E`) as the primary unit of analysis.
However, in DoD budgets, a single PE can span multiple services, fiscal years, and exhibit types.

**Questions:**
- **1a.** Should the GUI allow comparing the *same PE across services*? For example, if PE `0602702E`
  appears in both Army and Defense-Wide budgets, should those be shown as distinct entries or merged?
- **1b.** Are there cases where users need to drill from a PE into its *R-2 project-level sub-elements*
  (R-2a lines)? The current schema captures budget_activity and sub_activity but doesn't explicitly
  model the R-2a project hierarchy.
- **1c.** How important is tracking PE number *changes across years*? (e.g., a PE that was `0602120A`
  in FY2025 but renumbered to `0602121A` in FY2026). Should the system attempt to detect and link these?

## 2. Fiscal Year Handling

The database stores FY in two formats depending on the table: `budget_lines.fiscal_year` uses
`"FY 2026"` while `pe_index.fiscal_years` stores `["2026"]` (JSON array of bare year strings).

**Questions:**
- **2a.** Should FY be standardized across all tables to one format? If so, which: `"FY 2026"`,
  `"2026"`, or both (with a canonical form)?
- **2b.** How many fiscal years should the system support simultaneously? Currently it handles
  FY2024-FY2026. When FY2027 data arrives, should FY2024 be archived/dropped, or should all
  historical years remain queryable?
- **2c.** For the comparison features, is the primary use case *FY-to-FY delta for the same PE*
  (e.g., "how did PE X's funding change from FY2025 enacted to FY2026 request")?

## 3. PDF Text & Narrative Extraction

Phase 2 of enrichment links PDF pages to PEs and extracts narrative text.

**Questions:**
- **3a.** How important is *section-level* extraction (e.g., "Accomplishments/Planned Programs",
  "Acquisition Strategy", "Mission Description") versus whole-page text? The current R-2/R-3
  section parser handles common headers but may miss non-standard formatting.
- **3b.** Should the system extract and store *tables from PDF pages* in a structured format,
  or is raw text sufficient? Currently `table_data` is stored as JSON but not linked to PE context.
- **3c.** Are there specific PDF exhibit types beyond R-2/R-3 that contain critical narrative
  content? (e.g., P-5 justification sheets, C-1 project descriptions)
- **3d.** How are users expected to *search* PDF content — free-text search, or filtered by
  PE + FY + section type? This affects whether we need FTS5 on `pe_descriptions` vs `pdf_pages`.

## 4. Tag Taxonomy & Classification

The enrichment pipeline generates tags from 25 keyword categories plus structured fields.

**Questions:**
- **4a.** Is the current tag taxonomy (hypersonic, cyber, space, ai-ml, c2, isr, etc.)
  sufficient for the intended analysis? Are there missing categories that analysts need?
  Some candidates: `quantum`, `microelectronics`, `5g-comms`, `arctic`, `indo-pacific`,
  `counter-terrorism`, `readiness`, `modernization`.
- **4b.** Should tags support a *hierarchy*? For example, `missile-defense` could be a parent
  of `ballistic-missile-defense` and `cruise-missile-defense`. The current flat taxonomy doesn't
  express these relationships.
- **4c.** Are there external classification systems (e.g., PPBE categories, Joint Capability Areas,
  JCIDS functional areas) that the tag system should align with?
- **4d.** Should users be able to *add custom tags* through the GUI, and if so, should those be
  persisted separately from system-generated tags?

## 5. Cross-PE Relationships & Lineage

Phase 4 detects cross-PE references in narrative text.

**Questions:**
- **5a.** Beyond explicit PE mentions and title matching, are there other relationship types
  that matter? For example: "PE X transitions technology to PE Y" (tech transition), or
  "PE X is the predecessor of PE Y" (program evolution).
- **5b.** How should the GUI display PE relationships — as a network graph, a lineage table,
  or both? This affects how much metadata (confidence, context snippets, relationship types)
  needs to be stored.
- **5c.** Should the system detect relationships *across services*? (e.g., Army research PE
  feeding into a joint program PE under Defense-Wide)

## 6. Data Completeness & Quality

**Questions:**
- **6a.** What is the minimum acceptable coverage for PE-to-PDF linking? Currently, not all
  PEs have corresponding R-2 PDFs. Is 80% coverage sufficient, or must every PE with RDTE
  funding have narrative text?
- **6b.** How should the system handle PEs that appear in summary exhibits (R-1, P-1) but
  not in detail exhibits (R-2, P-5)? Currently these get pe_index entries but no descriptions.
- **6c.** Should the system flag when a PE's funding changes significantly (>50%) between
  exhibits within the same FY (e.g., R-1 total doesn't match sum of R-2 amounts)?
- **6d.** Are there known data quality issues in the source Excel files that the ingestion
  should compensate for? (e.g., merged cells, inconsistent column headers across services,
  classification markings embedded in text)

## 7. API & GUI Feature Priorities

**Questions:**
- **7a.** The dashboard currently shows top programs by FY2026 request amount. Should it also
  show *biggest movers* (largest absolute or percentage changes year-over-year)?
- **7b.** Is there a need for *saved searches* or *watchlists* (e.g., "alert me when PE X
  changes across budget submissions")?
- **7c.** Should the CSV/export feature support *multi-PE comparison tables* (Spruill charts
  with multiple PEs side by side)?
- **7d.** Is there a requirement for *bulk operations* — e.g., "export all PEs tagged with
  'hypersonic' as a single report"?

## 8. Performance & Scale

**Questions:**
- **8a.** What is the expected database size? The current budget covers FY2024-2026. If historical
  data (FY2020-2023) is added, the database could grow 3-4x. Are there performance concerns?
- **8b.** How frequently is the database rebuilt? On each budget submission cycle (annually)?
  Or incrementally as amended submissions arrive?
- **8c.** Is concurrent multi-user access a requirement, or is this primarily a single-analyst tool?
  This affects whether SQLite is sufficient or a client-server database is needed.

## 9. Data Lineage & Auditability

**Questions:**
- **9a.** How important is tracing a specific number back to its source file, sheet, and row?
  The system stores `source_file` but the row-level provenance varies by exhibit type.
- **9b.** Should the system maintain a *change log* — e.g., "PE X's FY2026 request changed
  from $100M to $110M between the February and April submissions"?
- **9c.** Are there compliance or audit requirements that dictate how data provenance is tracked?

## 10. Integration & Downstream Use

**Questions:**
- **10a.** Will the database feed into any external tools or dashboards (e.g., Tableau, Power BI,
  or a shared data lake)? If so, what export format is preferred?
- **10b.** Is there an expectation that the system will ingest data from sources beyond the
  standard DoD budget submission PDFs and Excel files? (e.g., congressional markup documents,
  SAR reports, GAO findings)
- **10c.** Should the API support webhooks or notifications when new data is ingested or
  significant changes are detected?

---

*These questions are ordered by impact on database schema and ingestion pipeline design.
Questions 1-3 may require schema changes; questions 4-6 affect enrichment logic;
questions 7-10 primarily affect the API and GUI layers.*
