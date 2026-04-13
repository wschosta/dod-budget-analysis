# Refactor Plan: Split `keyword_search.py` (2,500 lines)

**Status**: Proposed  
**Created**: 2026-04-13  
**Motivation**: `api/routes/keyword_search.py` is a 2,500-line module mixing SQL helpers,
PDF parsing, XLSX generation, cache building, and normalization. It should be split into
focused modules with clear boundaries.

---

## Current State

```
api/routes/keyword_search.py  (2,500 lines, 33 functions)
├── SQL / JSON helpers          lines 57-80      (3 functions,   ~25 lines)
├── Cache DDL                   lines 83-110     (1 function,    ~30 lines)
├── Budget normalization        lines 115-142    (2 functions,   ~30 lines)
├── Keyword matching            lines 145-170    (1 function,    ~20 lines)
├── PE discovery queries        lines 174-237    (1 function,    ~65 lines)
├── Description helpers         lines 242-335    (4 functions,   ~95 lines)
├── R-2 PDF parsing             lines 340-545    (1 function,   ~205 lines)
├── R-2 time-series consolidate lines 546-600    (1 function,    ~55 lines)
├── PDF sub-element mining      lines 604-705    (1 function,   ~100 lines)
├── Cross-PE lineage            lines 708-765    (2 functions,   ~60 lines)
├── Query helpers               lines 771-900    (5 functions,  ~130 lines)
├── XLSX styles                 lines 912-945    (2 functions,   ~35 lines)
├── XLSX helpers                lines 951-1043   (4 functions,   ~95 lines)
├── XLSX builder                lines 1045-1320  (1 function,   ~275 lines)
├── XLSX summary sheets         lines 1324-1540  (1+1 function, ~220 lines)
├── XLSX about + matrix         lines 1542-1705  (2 functions,  ~165 lines)
├── R-1 stub enrichment         lines 1710-1825  (2 functions,  ~115 lines)
├── Cache insert helpers        lines 1828-1935  (2 functions,  ~110 lines)
├── Org backfill                lines 1937-1985  (1 function,    ~50 lines)
├── Cache builder orchestrator  lines 1990-2468  (1 function,   ~480 lines)
└── ensure_cache                lines 2470-2500  (1 function,    ~30 lines)
```

## Target State

Split into 3 new modules + a slimmed-down orchestrator:

```
api/routes/keyword_search.py          ~850 lines  (orchestrator + query layer)
api/routes/keyword_xlsx.py            ~800 lines  (XLSX generation)
api/routes/keyword_r2.py              ~550 lines  (R-2 PDF parsing + mining)
api/routes/keyword_helpers.py         ~300 lines  (shared constants, SQL, normalization)
```

---

## Module 1: `keyword_helpers.py` (~300 lines)

**Purpose**: Shared constants, SQL utilities, normalization, and keyword matching
used by all other keyword modules.

### Move these functions here:

| Function | Current lines | Notes |
|---|---|---|
| `_in_clause()` | 57-60 | Make public: `in_clause()` |
| `_like_clauses()` | 63-68 | Make public: `like_clauses()` |
| `_safe_json_list()` | 70-78 | Make public: `safe_json_list()` |
| `cache_ddl()` | 83-110 | |
| `normalize_budget_activity()` | 115-122 | |
| `color_of_money()` | 124-142 | |
| `find_matched_keywords()` | 145-170 | |
| `_is_garbage_description()` | 317-335 | Make public: `is_garbage_description()` |

### Move these constants here:

| Constant | Current lines |
|---|---|
| `SEARCH_COLS` | 24 |
| `FY_START`, `FY_END` | 26-27 |
| `BA_CANONICAL` | 34-42 |
| `_ORG_FROM_PATH` | 44-52 |
| `_LEVENSHTEIN_THRESHOLD` | 53 |
| `_SKIP_RAW_TITLES` | 58-59 |

### Imports needed:
```python
import json, re, sqlite3
from utils.normalization import R2_JUNK_TITLES
from utils.patterns import PE_NUMBER_STRICT_CI, PE_SUFFIX_PATTERN
```

### Exports (public API):
```python
# Constants
FY_START, FY_END, SEARCH_COLS, BA_CANONICAL

# Functions
in_clause, like_clauses, safe_json_list, cache_ddl,
normalize_budget_activity, color_of_money,
find_matched_keywords, is_garbage_description
```

---

## Module 2: `keyword_r2.py` (~550 lines)

**Purpose**: R-2 PDF parsing, time-series consolidation, sub-element mining,
cross-PE lineage detection, and R-1 stub enrichment.

### Move these functions here:

| Function | Current lines | Notes |
|---|---|---|
| `parse_r2_cost_block()` | 340-545 | The big parser (205 lines) |
| `consolidate_r2_timeseries()` | 546-600 | |
| `mine_pdf_subelements()` | 604-705 | |
| `normalize_program_name()` | 708-712 | |
| `annotate_cross_pe_lineages()` | 715-765 | |
| `_extract_r1_titles_for_stubs()` | 1710-1825 | |
| `_aggregate_r2_funding_into_r1_stubs()` | 1793-1825 | |

### Imports needed:
```python
import re, sqlite3, logging
from api.routes.keyword_helpers import (
    FY_START, in_clause, find_matched_keywords, _PE_TITLE_RE,
)
from utils.normalization import clean_r2_title, normalize_r2_project_code
from utils.strings import clean_narrative
```

### Exports:
```python
parse_r2_cost_block, consolidate_r2_timeseries,
mine_pdf_subelements, annotate_cross_pe_lineages,
extract_r1_titles_for_stubs, aggregate_r2_funding_into_r1_stubs
```

### Future consolidation opportunity:
`parse_r2_cost_block()` here and `parse_r2_cost_table()` in
`pipeline/r2_pdf_extractor.py` parse the same R-2 COST blocks with different
output formats. A future pass could unify them behind a shared low-level parser,
with each caller formatting the output as needed. Not in scope for this refactor
because it crosses the API/pipeline boundary.

---

## Module 3: `keyword_xlsx.py` (~800 lines)

**Purpose**: Everything related to XLSX workbook generation. Pure presentation
layer with no database queries or cache-building logic.

### Move these functions here:

| Function | Current lines | Notes |
|---|---|---|
| `xlsx_base_styles()` | 912-928 | |
| `_col_letter()` | 945-948 | |
| `_write_merged_fy_headers()` | 951-976 | |
| `_set_fy_column_widths()` | 979-998 | |
| `_apply_fy_conditional_formatting()` | 1000-1043 | |
| `build_keyword_xlsx()` | 1045-1320 | Main entry point (275 lines) |
| `_build_xlsx_summary()` | 1324-1540 | Includes nested `_write_summary_sheet` |
| `_build_xlsx_about_sheet()` | 1542-1635 | |
| `_build_keyword_matrix()` | 1637-1705 | |

### Move these constants here:

| Constant | Current lines |
|---|---|
| `_HIDDEN_LOOKUP_COL` | 54 |
| `_SPILL_MAX_ROW` | 55 |
| `_COL_WIDTH_DEFAULTS` | 932-942 |

### Imports needed:
```python
import io, re, time
from typing import Any
from api.routes.keyword_helpers import safe_json_list, xlsx_base_styles
```

### Exports:
```python
build_keyword_xlsx, xlsx_base_styles
```

### Key property:
This module has **zero database dependencies** — it takes pre-built data
structures (items, desc_by_pe_fy, fy_desc_kws) and returns `bytes`.
This makes it independently testable.

---

## Module 4: `keyword_search.py` (remains, ~850 lines)

**Purpose**: Cache orchestrator — PE discovery, pivot queries, R-2 merge logic,
cache table population. This is the "business logic" core.

### Keeps these functions:

| Function | Current lines | Notes |
|---|---|---|
| `collect_matching_pe_numbers_split()` | 174-237 | PE discovery |
| `get_description_map()` | 242-278 | |
| `get_desc_keyword_map()` | 280-315 | |
| `lookup_cache_description()` | 771-812 | |
| `apply_filters()` | 813-828 | |
| `cache_rows_to_dicts()` | 831-857 | |
| `load_per_fy_descriptions()` | 859-908 | |
| `_insert_cache_rows()` | 1828-1885 | |
| `_insert_stub_pes()` | 1891-1935 | |
| `_backfill_organization()` | 1937-1985 | |
| `build_cache_table()` | 1990-2468 | Main orchestrator (480 lines) |
| `ensure_cache()` | 2470-2500 | |

### New imports:
```python
from api.routes.keyword_helpers import (
    FY_START, FY_END, SEARCH_COLS, BA_CANONICAL,
    in_clause, like_clauses, cache_ddl,
    normalize_budget_activity, color_of_money,
    find_matched_keywords, is_garbage_description,
    _ORG_FROM_PATH, _SKIP_RAW_TITLES,
)
from api.routes.keyword_r2 import (
    mine_pdf_subelements, annotate_cross_pe_lineages,
    extract_r1_titles_for_stubs, aggregate_r2_funding_into_r1_stubs,
)
```

### Re-exports for backward compatibility:
```python
# explorer.py and tests import these from keyword_search — keep re-exporting
from api.routes.keyword_helpers import FY_START, FY_END, find_matched_keywords
from api.routes.keyword_xlsx import build_keyword_xlsx
```

---

## Dependency Graph (post-refactor)

```
keyword_helpers.py          (leaf — no intra-package deps)
       ▲
       │
keyword_r2.py               (depends on helpers)
       ▲
       │
keyword_search.py           (depends on helpers + r2)
       ▲
       │
keyword_xlsx.py             (depends on helpers only)
       ▲
       │
explorer.py                 (depends on search + xlsx)
```

No circular dependencies. Each module can be tested independently.

---

## External Import Changes

### `api/routes/explorer.py`
```python
# Before:
from api.routes.keyword_search import (
    FY_END, FY_START, build_cache_table,
    build_keyword_xlsx, cache_rows_to_dicts,
    load_per_fy_descriptions, lookup_cache_description,
)

# After (unchanged — re-exports preserve this):
from api.routes.keyword_search import (
    FY_END, FY_START, build_cache_table,
    build_keyword_xlsx, cache_rows_to_dicts,
    load_per_fy_descriptions, lookup_cache_description,
)

# The inline import also stays working:
from api.routes.keyword_search import find_matched_keywords
```

### Test files
All test imports (`from api.routes.keyword_search import ...`) continue working
via re-exports. No test changes required.

---

## Execution Order

### Step 1: Create `keyword_helpers.py` (lowest risk)
- Move constants and pure functions (no DB calls)
- Add re-exports in `keyword_search.py`
- Run tests

### Step 2: Create `keyword_xlsx.py` (clean extraction)
- Move all XLSX functions (they form a self-contained cluster)
- Add re-export of `build_keyword_xlsx` in `keyword_search.py`
- Run tests

### Step 3: Create `keyword_r2.py` (moderate risk)
- Move R-2 parsing, mining, lineage, and R-1 stub functions
- These have more cross-references so double-check imports
- Run tests

### Step 4: Clean up `keyword_search.py`
- Remove dead imports
- Verify re-exports are complete
- Run full suite + lint + mypy

### Step 5: Verify no circular imports
```bash
python -c "from api.routes.keyword_search import build_cache_table"
python -c "from api.routes.keyword_xlsx import build_keyword_xlsx"
python -c "from api.routes.keyword_r2 import mine_pdf_subelements"
python -c "from api.routes.keyword_helpers import FY_START"
```

---

## Phase 2: Unify R-2 Cost Table Parsers

Two functions parse the same R-2 COST block data with different approaches
and different output formats. They should share a single low-level parser.

### The Two Parsers

#### `parse_r2_cost_block()` — keyword_search.py:340-545 (205 lines)
- **Called by**: `mine_pdf_subelements()` (on-demand, per keyword search)
- **Input**: `(page_text, source_file, fiscal_year)`
- **Output**: `list[dict]` with `pe_number, project_code, project_title,
  source_file, fiscal_year, fy_amounts: {fyXXXX: amount_in_K}, description_text`
- **Also extracts**: Section A (Mission Description) + Section B (Accomplishments)
  narrative text per project
- **FY header parsing**: Regex token scanning, maps "Total" → budget_year
- **Amount parsing**: `[\d,]+\.\d{3}` regex, inline in main loop
- **Title cleanup**: Calls `clean_r2_title()` from utils/normalization
- **Skips**: Hardcoded `startswith()` checks (not shared constants)

#### `parse_r2_cost_table()` — pipeline/r2_pdf_extractor.py:315-455 (140 lines)
- **Called by**: `extract_r2_from_pdfs()` (pipeline build, batch over all pages)
- **Input**: `(text)` only
- **Output**: `dict | None` with `pe_number, approp_code, unit_multiplier,
  fy_amounts: {label: [(fy_year, amount|None), ...]}, budget_activity,
  budget_activity_title, appropriation_title`
- **Does NOT extract**: narrative descriptions
- **FY header parsing**: Compiled regexes (`_FY_4DIGIT_RE`, `_FY_2DIGIT_RE`,
  `_BARE_YEAR_RE`) with 2-digit year support and wider header scan area
- **Amount parsing**: Right-to-left token scanner with `_parse_amount()` helper
  and `_NULL_AMOUNT_TOKENS` (handles "Continuing", "TBD", "--", etc.)
- **Title cleanup**: Calls `clean_r2_title()` post-parse in the caller
- **Skips**: `SKIP_LINE_LABELS` + `SKIP_LABEL_PREFIXES` (shared constants)
- **Also extracts**: BA/appropriation from page header via `parse_r2_header_metadata()`

### What Overlaps vs. What Diverges

| Capability | `parse_r2_cost_block` | `parse_r2_cost_table` |
|---|---|---|
| PE number extraction | `_PE_TITLE_RE` (PE + title) | `_PE_RE` (PE only) |
| COST header detection | Hardcoded `"COST" in line and "Millions" in line` | `_COST_HEADER_RE` regex (handles Thousands, $'s) |
| FY column parsing | Simple token scan | 3-stage regex (4-digit, 2-digit, bare year) |
| Amount parsing | `[\d,]+\.\d{3}` regex, left-to-right | Right-to-left token scanner with null handling |
| Unit multiplier | Hardcoded ×1000 (assumes Millions) | Detects Millions vs Thousands |
| Null amounts | Skips `"-"` only | `_NULL_AMOUNT_TOKENS` (-, --, TBD, Continuing, etc.) |
| Skip rows | Hardcoded `startswith()` checks | `SKIP_LINE_LABELS` + `SKIP_LABEL_PREFIXES` |
| Description extraction | Yes (Section A + B) | No |
| BA/Appropriation | No | Yes (via `parse_r2_header_metadata`) |
| Org inference | No (done by caller) | No (done by caller) |

**Bottom line**: `parse_r2_cost_table` is strictly more robust on the table-parsing
side (better FY detection, null handling, unit detection). `parse_r2_cost_block`
is the only one that extracts narrative descriptions.

### Unification Strategy

Create a shared low-level parser that both callers use, with description
extraction as an opt-in layer.

#### New shared module: `pipeline/r2_cost_parser.py`

```
pipeline/r2_cost_parser.py  (~250 lines)
├── Constants (moved from r2_pdf_extractor)
│   ├── _COST_HEADER_RE
│   ├── _FY_4DIGIT_RE, _FY_2DIGIT_RE, _BARE_YEAR_RE
│   ├── _NULL_AMOUNT_TOKENS
│   ├── SKIP_LINE_LABELS, SKIP_LABEL_PREFIXES
│   └── _parse_amount()
│
├── parse_r2_cost_table(text)  →  dict | None     (moved from r2_pdf_extractor)
│   Returns: pe_number, unit_multiplier, fy_labels, rows: [(label, [(fy, amount)])]
│   Pure text parsing — no DB, no org inference, no description extraction
│
└── parse_r2_header_metadata(text)  →  dict        (moved from r2_pdf_extractor)
    Returns: budget_activity, budget_activity_title, appropriation_title
```

#### Updated callers

**`pipeline/r2_pdf_extractor.py`** (pipeline build):
```python
from pipeline.r2_cost_parser import parse_r2_cost_table, parse_r2_header_metadata
# No changes to extract_r2_from_pdfs() — it already calls parse_r2_cost_table()
# Just moves the function to the shared module
```

**`api/routes/keyword_r2.py`** (or keyword_search.py until Phase 1 is done):
- Delete `parse_r2_cost_block()` entirely (205 lines)
- Replace `mine_pdf_subelements()` internals to call the shared parser:

```python
from pipeline.r2_cost_parser import parse_r2_cost_table

def mine_pdf_subelements(...):
    for r in rows:
        source_file, page_number, page_text, fiscal_year = r
        result = parse_r2_cost_table(page_text)
        if not result:
            continue
        pe = result["pe_number"]
        mult = result["unit_multiplier"]

        for label, fy_pairs in result["fy_amounts"].items():
            # Convert to the format mine_pdf_subelements expects
            fy_amounts = {}
            for fy_year, amount in fy_pairs:
                if amount is not None:
                    fy_amounts[f"fy{fy_year}"] = amount * mult
            if not fy_amounts:
                continue

            items.append({
                "pe_number": pe,
                "project_code": ...,  # from clean_r2_title(label)
                "project_title": ...,
                "source_file": source_file,
                "fiscal_year": fiscal_year,
                "fy_amounts": fy_amounts,
                "description_text": "",  # filled by _extract_descriptions() below
            })

    # Description extraction stays as a separate post-pass
    _extract_descriptions(items, page_texts)
```

#### Description extraction becomes a standalone function

The Section A / Section B narrative extraction (keyword_search.py:480-538)
moves to a new function:

```python
def extract_r2_descriptions(
    page_text: str,
    projects: list[dict],
) -> None:
    """Extract Section A/B descriptions and attach to project dicts (in-place)."""
    # Section A: Mission Description (shared across all projects)
    # Section B: per-project Accomplishments
    # Existing logic from parse_r2_cost_block lines 480-538
```

This function is only called by `mine_pdf_subelements` (the explorer path),
not by the pipeline build (which stores descriptions separately via enricher.py).

### Execution Order

#### Step 1: Create `pipeline/r2_cost_parser.py`
- Move `parse_r2_cost_table`, `parse_r2_header_metadata`, and all their
  constants/helpers from `pipeline/r2_pdf_extractor.py`
- Add re-exports in `r2_pdf_extractor.py` for backward compat
- Run tests (especially `test_r2_pdf_extractor.py`)

#### Step 2: Update `r2_pdf_extractor.py` to import from shared module
- Replace local definitions with imports
- Keep `extract_r2_from_pdfs()`, `infer_org()`, and CLI in r2_pdf_extractor
- Run tests

#### Step 3: Rewrite `parse_r2_cost_block()` to use shared parser
- Delete the 205-line function
- Update `mine_pdf_subelements()` to call `parse_r2_cost_table()`
  + adapter code to convert output format
- Extract description logic into `extract_r2_descriptions()`
- Run tests (especially `test_explorer_xlsx.py`, `test_explorer_pe_search.py`)

#### Step 4: Delete dead code
- Remove old constants from keyword_search that are now in r2_cost_parser
  (hardcoded skip checks, amount regex, etc.)
- Run full suite

### What Stays Separate

| Concern | Location | Reason |
|---|---|---|
| `infer_org()` + org mappings | `r2_pdf_extractor.py` | Pipeline-specific, uses file path patterns unique to the download layout |
| `_ORG_FROM_PATH` | `keyword_search.py` | API-side fallback, simpler mapping (6 entries vs 50) |
| `consolidate_r2_timeseries()` | `keyword_search.py` / `keyword_r2.py` | Only used by explorer cache builder, not pipeline |
| `extract_r2_from_pdfs()` + CLI | `r2_pdf_extractor.py` | Pipeline entry point, handles DB writes |

### Risk Assessment

| Risk | Mitigation |
|---|---|
| Pipeline build regression | Run `extract_r2_from_pdfs` with `--dry-run` before and after; compare row counts |
| Explorer cache differences | Rebuild a cache with known keywords; diff the row counts and amounts |
| Description extraction regression | `mine_pdf_subelements` tests already cover this path |
| Import cycle pipeline↔api | `r2_cost_parser` is in `pipeline/`, imported by both — no cycle |

### Net effect

- Delete ~205 lines (`parse_r2_cost_block`)
- Create ~250 lines (`pipeline/r2_cost_parser.py`, mostly moved code)
- Add ~30 lines adapter code in `mine_pdf_subelements`
- **Net**: ~175 fewer lines, single source of truth for R-2 table parsing,
  and the explorer gets the pipeline's more robust parser (2-digit FY support,
  Thousands unit detection, null amount handling) for free.

---

## Phase 3: Consolidate Organization Mapping

Organization name inference is spread across 4 locations with overlapping
but inconsistent mappings.

### Current state

| Location | What | Entries | Used by |
|---|---|---|---|
| `utils/normalization.py` `ORG_NORMALIZE` | Code → canonical name (A → Army, DARPA → DARPA) | 78 | `pipeline/builder.py`, `pipeline/db_validator.py`, `scripts/repair_database.py` |
| `utils/normalization.py` `_ORG_ALIASES_LOWER` | Lowercase + historical renames (dss → DCSA, tma → DHA) | 82 | `pipeline/validator.py` |
| `pipeline/r2_pdf_extractor.py` `_ORG_FROM_FILE` | Filename fragment → org (RDTE_DARPA → DARPA) | 50 | `extract_r2_from_pdfs`, `scripts/repair_database.py` |
| `api/routes/keyword_search.py` `_ORG_FROM_PATH` | Filename fragment → org (US_Army → Army) | 6 | `_backfill_organization()` |

Plus `r2_pdf_extractor.py` has 3 more layers:
- `_AGENCY_NAME_MAP` (28 entries) — full agency names from R-2 headers
- `_R2_AGENCY_RE` + `_OLDER_AGENCY_RE` — regexes for header text
- `_DEPT_FROM_TEXT` (10 entries) — substring fallback for department names
- `infer_org()` — orchestrator function using all of the above

### Problem

- `_ORG_FROM_PATH` (keyword_search) is a strict subset of `_ORG_FROM_FILE`
  (r2_pdf_extractor). Both are `(fragment, org)` tuples searched against
  source_file paths.
- `_backfill_organization()` in keyword_search reimplements a simpler version
  of the same path-scanning logic that `infer_org()` does.
- If a new agency is added to one list, it's easy to miss the other.

### Target: `utils/organization.py`

```python
"""Centralized organization name inference and normalization."""

# Re-export the code→name map (already in utils/normalization.py — don't move)
from utils.normalization import ORG_NORMALIZE, normalize_org_name, normalize_org_loose

# Filename fragment → org (superset of both _ORG_FROM_FILE and _ORG_FROM_PATH)
ORG_FROM_FILE: list[tuple[str, str]] = [...]  # 50 entries from r2_pdf_extractor

# Full agency name → org code (from R-2 page headers)
AGENCY_NAME_MAP: dict[str, str] = {...}  # 28 entries from r2_pdf_extractor

# Regex patterns for R-2 header agency extraction
R2_AGENCY_RE = re.compile(...)
OLDER_AGENCY_RE = re.compile(...)

# Substring fallback patterns
DEPT_FROM_TEXT: list[tuple[str, str]] = [...]

def infer_org_from_path(source_file: str) -> str | None:
    """Infer org from source_file path fragments. Fast, high confidence."""

def infer_org(source_file: str, page_text: str | None = None) -> str | None:
    """Full org inference: path first, then page header text, then substring."""
```

### Execution

1. Create `utils/organization.py` with the unified mappings and `infer_org()`
2. Update `r2_pdf_extractor.py`: delete local mappings, import from `utils/organization`
3. Update `keyword_search.py` `_backfill_organization()`: replace `_ORG_FROM_PATH`
   loop with `infer_org_from_path()` call
4. Update `scripts/repair_database.py`: import `infer_org` from `utils/organization`
   instead of from `r2_pdf_extractor`
5. Delete `_ORG_FROM_PATH` from `keyword_search.py`

### Net effect

- Delete ~6 lines (`_ORG_FROM_PATH`)
- Delete ~120 lines from `r2_pdf_extractor.py` (mappings + `infer_org`)
- Create ~150 lines in `utils/organization.py` (mostly moved code)
- Single source of truth for all org inference

---

## Phase 4: Exhibit Type Constants

Raw strings `"r1"`, `"r2"`, `"r2_pdf"` appear in 30+ locations across the
codebase. Most are comparison checks (`== "r1"`, `in ("r2", "r2_pdf")`).

### Current usage (non-test, non-pipeline-builder)

**`api/routes/keyword_search.py`** — 11 occurrences:
- Lines 1188, 1368, 2216, 2218, 2272, 2300 (×2), 2327, 2400, 2433, 1924

**`api/routes/explorer.py`** — 2 occurrences:
- Lines 452, 593

**`pipeline/r2_pdf_extractor.py`** — 1 occurrence:
- Line 552 (`"r2_pdf"`)

**`pipeline/builder.py`** — 10+ occurrences (exhibit type definitions, the
canonical source — these stay as string literals since they define the mapping)

**`pipeline/enricher.py`**, **`utils/config.py`** — a few each

### Approach: Constants in `utils/config.py`

`utils/config.py` already defines `CORE_SUMMARY_TYPES` and `DETAIL_EXHIBIT_KEYS`
with these same strings. Add named constants alongside them:

```python
# utils/config.py  (add near existing exhibit type sets)

# Exhibit type constants for comparison checks
EXHIBIT_R1 = "r1"
EXHIBIT_R2 = "r2"
EXHIBIT_R2_PDF = "r2_pdf"
EXHIBIT_R3 = "r3"
EXHIBIT_R4 = "r4"
EXHIBIT_P1 = "p1"
EXHIBIT_O1 = "o1"

# Grouped sets (already exist, just reference the new constants)
R2_TYPES = frozenset({EXHIBIT_R2, EXHIBIT_R2_PDF})
RDT_E_TYPES = frozenset({EXHIBIT_R1, EXHIBIT_R2, EXHIBIT_R2_PDF, EXHIBIT_R3, EXHIBIT_R4})
```

### Scope

Only update the **api/** layer and **keyword_search** code. The pipeline
code (`builder.py`, `exhibit_catalog.py`) uses these strings in exhibit
type definitions and column mappings where string literals are appropriate.

### Example changes

```python
# Before:
if row.get("exhibit_type") == "r1":
if r.get("exhibit_type") in ("r2", "r2_pdf"):

# After:
from utils.config import EXHIBIT_R1, R2_TYPES
if row.get("exhibit_type") == EXHIBIT_R1:
if r.get("exhibit_type") in R2_TYPES:
```

### Execution

1. Add constants + `R2_TYPES` set to `utils/config.py`
2. Update `api/routes/keyword_search.py` (11 occurrences)
3. Update `api/routes/explorer.py` (2 occurrences)
4. Run tests — purely mechanical, no logic changes

### Net effect

Zero line count change, but eliminates a class of typo bugs (e.g., `"r2pdf"`
vs `"r2_pdf"`) and makes exhibit types greppable/refactorable.

---

## Phase 5: Performance Optimizations

These are independent of the structural refactoring and can be done in any
order. Ordered by estimated impact.

### 5a. Batch INSERT in cache builder (DONE)

**Status**: Already implemented in this branch.

Switched `_insert_cache_rows` from per-row `conn.execute()` to
`conn.executemany()`. Estimated 4-10x speedup on cache builds with
5,000+ rows.

### 5b. Levenshtein memoization in R-2 merge

**File**: `keyword_search.py:2340-2345` (inside `build_cache_table`)
**Impact**: HIGH for large keyword sets (500+ R-2 rows)

The fuzzy merge loop calls `_levenshtein_distance(title, ex_title)` inside
an O(n²) nested loop per (PE, project_code) group. With 10 rows per group
and 50 groups, that's ~2,500 calls. Titles repeat across fiscal years so
many calls are redundant.

**Fix**: Add a per-build memo dict:
```python
_lev_cache: dict[tuple[str, str], int] = {}

# In the inner loop:
key = (title, ex_title) if title <= ex_title else (ex_title, title)
if key not in _lev_cache:
    _lev_cache[key] = _levenshtein_distance(title, ex_title)
dist = _lev_cache[key]
```

Also gate the Levenshtein call behind a length-similarity pre-check — if
the two strings differ in length by more than the threshold allows, skip:
```python
if abs(len(title) - len(ex_title)) > max(len(title), len(ex_title)) * _LEVENSHTEIN_THRESHOLD:
    continue  # impossible to be within threshold
```

**Estimated saving**: 50-70% fewer Levenshtein calls, ~1-2s on large builds.

### 5c. PDF mining: add `is_r2_cost` computed column

**File**: `keyword_search.py:628-639` (`mine_pdf_subelements` query)
**Impact**: MEDIUM-HIGH for large databases (100k+ pdf_pages)

The current query does triple `LIKE '%...%'` on the `page_text` column,
which forces a full table scan on every keyword search build.

**Fix** (schema change — requires pipeline rebuild):
```sql
-- In pipeline/schema.py, add to pdf_pages:
ALTER TABLE pdf_pages ADD COLUMN is_r2_cost BOOLEAN DEFAULT 0;
CREATE INDEX idx_pdf_pages_r2_cost ON pdf_pages(is_r2_cost, fiscal_year);

-- Populated during builder.py or as a post-build step:
UPDATE pdf_pages SET is_r2_cost = 1
WHERE (page_text LIKE '%Exhibit R-2,%' OR page_text LIKE '%Exhibit R-2A%')
  AND page_text LIKE '%COST%Millions%'
  AND source_file LIKE '%detail%';
```

Then the mining query becomes:
```sql
SELECT source_file, page_number, page_text, fiscal_year
FROM pdf_pages
WHERE is_r2_cost = 1 AND fiscal_year >= ?
ORDER BY fiscal_year DESC, source_file, page_number
```

**Estimated saving**: 2-5s per keyword search build (index scan vs full scan).

**Prerequisite**: Database rebuild (already happens when pipeline changes land).

### 5d. Explorer summary: aggregate query instead of full row load

**File**: `explorer.py:430-480` (`get_explorer_data`)
**Impact**: MEDIUM for large caches (10k+ rows)

Currently loads ALL cache rows into Python to build a PE-level summary.
Could use a SQL aggregate query instead:

```sql
SELECT
    pe_number,
    MAX(CASE WHEN exhibit_type = 'r1' THEN line_item_title END) AS pe_title,
    MAX(organization_name) AS service,
    COUNT(*) AS total_sub_elements,
    SUM(CASE WHEN matched_keywords_row != '[]' THEN 1 ELSE 0 END) AS matching
FROM {cache_table}
GROUP BY pe_number
ORDER BY pe_number
```

Active years can be computed with a separate lightweight query:
```sql
SELECT DISTINCT 'fy' || col FROM (
    SELECT CASE WHEN fy2015 IS NOT NULL THEN 2015 END AS col
    UNION ALL SELECT CASE WHEN fy2016 IS NOT NULL THEN 2016 END
    ...
) WHERE col IS NOT NULL
```

**Estimated saving**: 300-500ms per explorer page load on 10k-row caches.
Removes the need to parse JSON for every row just to count matches.

### 5e. JSON parse caching in `cache_rows_to_dicts` (DONE)

**Status**: Already implemented in this branch.

Added a per-call `json_cache` dict that deduplicates `json.loads()` calls
for `matched_keywords_row` and `matched_keywords_desc` columns, since many
rows share identical keyword lists.

---

## Phasing Summary

| Phase | What | Depends on | Est. lines saved |
|---|---|---|---|
| **1** | Split keyword_search.py → 4 modules | — | 0 (reorganization) |
| **2** | Unify R-2 parsers | Phase 1 (keyword_r2 exists) | ~175 |
| **3** | Consolidate org mapping | Phase 2 (infer_org moves) | ~25 |
| **4** | Exhibit type constants | Phase 1 (keyword_helpers exists) | 0 (safety) |
| **5a-e** | Performance | Independent | varies |

Phases 1-4 are sequential. Phase 5 items are independent of each other
and of Phases 1-4 (except 5c requires a pipeline rebuild).

---

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Circular imports | Dependency graph is acyclic by design; helpers is a leaf |
| Broken external imports | Re-exports in keyword_search.py preserve all existing import paths |
| Merge conflicts with other branches | Each step is one file creation + one file edit; small diffs |
| Runtime import order | No module-level side effects; all functions are lazy |

## Success Criteria

- [ ] All 2900+ tests pass after each step
- [ ] `ruff check` clean
- [ ] `mypy api/ utils/ --ignore-missing-imports` no new errors
- [ ] `keyword_search.py` under 900 lines
- [ ] No circular imports
- [ ] No test file changes needed (re-exports cover all)
