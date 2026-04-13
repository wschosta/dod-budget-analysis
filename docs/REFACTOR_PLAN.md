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

## What This Plan Does NOT Cover

These are separate follow-up tasks:

1. **Unify R-2 parsers**: `parse_r2_cost_block()` (keyword_r2) and
   `parse_r2_cost_table()` (pipeline/r2_pdf_extractor) parse the same data.
   Consolidating requires changing pipeline code and re-running the build.

2. **Extract org mapping**: `_ORG_FROM_PATH` (keyword_helpers) vs
   `_ORG_FROM_FILE` (r2_pdf_extractor) — overlapping but different scope.
   Could unify into `utils/organization.py`.

3. **Exhibit type constants**: `"r1"`, `"r2"`, `"r2_pdf"` appear as raw
   strings in 11+ locations. Could define in `keyword_helpers.py` or a
   shared constants module.

4. **`build_cache_table()` decomposition**: At 480 lines, it's still large
   after extraction. The R-2 merge pre-pass (~200 lines) could become its
   own function. Defer until the extraction is stable.

5. **Performance**: Levenshtein memoization, PDF mining computed column,
   explorer aggregation query — all independent of this restructure.

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
