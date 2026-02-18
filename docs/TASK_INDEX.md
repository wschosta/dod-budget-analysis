# Task Index — Phase 0 & Phase 1

Master index of all TODO tasks for Phase 0 and Phase 1. Each task is designed
to be independently completable by an AI agent in a single session unless
otherwise noted.

## Legend

| Annotation | Meaning |
|------------|---------|
| **AI-agent** | Can be completed by an AI agent without external dependencies |
| **DATA PROCESSING** | Requires downloaded budget files in `DoD_Budget_Documents/` |
| **ENVIRONMENT TESTING** | Requires running code against live services or local data |
| **USER INTERVENTION** | Needs a human decision before or during execution |

---

## Phase 0 — Project Description & Documentation

| Step | Task | Type | TODO File | Skeleton File(s) |
|------|------|------|-----------|-------------------|
| 0.A1 | Merge ROADMAP into README | AI-agent ✅ **Complete** | [TODO](TODO_0A1_merge_roadmap_into_readme.md) | `README.md` (modify) |
| 0.A2 | Create wiki skeleton | AI-agent ✅ **Complete** | [TODO](TODO_0A2_create_wiki_skeleton.md) | `docs/wiki/*.md` (created) |

---

## Phase 1.A — Source Coverage & Download Pipeline

| Step | Task | Type | TODO File | Skeleton File(s) |
|------|------|------|-----------|-------------------|
| 1.A1 | Audit downloader coverage | AI-agent + web research | [TODO](TODO_1A1_audit_downloader_coverage.md) | — |
| 1.A2 | Expand fiscal-year coverage | ENVIRONMENT TESTING | [TODO](TODO_1A2_expand_fiscal_year_coverage.md) | — |
| 1.A3 | Harden download reliability | AI-agent (3 sub-tasks) + ENVIRONMENT TESTING (1 sub-task) | [TODO](TODO_1A3_harden_download_reliability.md) | — |
| 1.A4 | Automate download scheduling | AI-agent ✅ **Complete** | [TODO](TODO_1A4_automate_download_scheduling.md) | `scripts/scheduled_download.py`, `.github/workflows/download.yml` |
| 1.A5 | Document all data sources | AI-agent | [TODO](TODO_1A5_document_data_sources.md) | `docs/wiki/Data-Sources.md` |
| 1.A6 | Retry failed downloads | AI-agent (3 sub-tasks: failure log, CLI flag, GUI polish) | [TODO](TODO_1A6_retry_failed_downloads.md) | — |

---

## Phase 1.B — Parsing & Normalization

| Step | Task | Type | TODO File | Skeleton File(s) |
|------|------|------|-----------|-------------------|
| 1.B1 | Catalog all exhibit types | DATA PROCESSING | [TODO](TODO_1B1_catalog_exhibit_types.md) | `docs/wiki/Exhibit-Types.md` |
| 1.B2 | Standardize column mappings | AI-agent + DATA PROCESSING | [TODO](TODO_1B2_standardize_column_mappings.md) | — |
| 1.B3 | Normalize monetary values | DATA PROCESSING (decisions resolved: thousands canonical, display toggle to millions) | [TODO](TODO_1B3_normalize_monetary_values.md) | — |
| 1.B4 | Extract PE/line-item metadata | AI-agent + DATA PROCESSING | [TODO](TODO_1B4_extract_pe_metadata.md) | — |
| 1.B5 | PDF extraction quality audit | ENVIRONMENT TESTING | [TODO](TODO_1B5_pdf_extraction_audit.md) | — |
| 1.B6 | Build validation suite | AI-agent ✅ **Complete** | [TODO](TODO_1B6_build_validation_suite.md) | `validate_budget_db.py` |

---

## Phase 1.C — Data Pipeline Testing

| Step | Task | Type | TODO File | Skeleton File(s) |
|------|------|------|-----------|-------------------|
| 1.C1 | Create test fixtures | DATA PROCESSING + USER INTERVENTION | [TODO](TODO_1C1_create_test_fixtures.md) | `tests/fixtures/` |
| 1.C2 | Unit tests for parsing | AI-agent | [TODO](TODO_1C2_unit_tests_parsing.md) | `tests/test_parsing.py`, `tests/conftest.py` |
| 1.C3 | Integration test: E2E pipeline | AI-agent (needs fixtures) | [TODO](TODO_1C3_integration_test_e2e.md) | `tests/test_e2e_pipeline.py` |

---

## Recommended Execution Order

Tasks that can be done **immediately** (no dependencies, no data needed):

1. ~~**0.A1** — Merge ROADMAP into README~~ ✅ Complete
2. ~~**0.A2** — Wiki skeleton (already created, just needs review)~~ ✅ Complete
3. ~~**1.B6** — Validation suite (works against existing DB schema)~~ ✅ Complete
4. **1.C2** — Unit tests for `_detect_exhibit_type`, `_safe_float`, `_map_columns`
   (tests against source code, no data files needed)
5. **1.A5** — Document data sources (from reading current code)

Tasks that need **downloaded data**:

6. **1.A1** — Audit coverage (web research)
7. **1.A2** — Fiscal year coverage (network access)
8. **1.B1** — Catalog exhibit types (needs Excel files)
9. **1.B2** — Standardize column mappings (needs 1.B1)
10. **1.C1** — Create test fixtures (needs downloaded files)

Tasks with **user decisions now resolved**:

11. **1.A4** — Scheduling: manual trigger via `workflow_dispatch`, manifest as artifact
12. **1.B3** — Monetary normalization: store in thousands, display toggle to millions
13. **1.B3b** — Add `--unit thousands|millions` toggle to `search_budget.py`
