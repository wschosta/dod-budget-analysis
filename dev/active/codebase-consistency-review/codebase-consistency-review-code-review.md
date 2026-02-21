# Codebase Consistency Review

**Scope:** api/, utils/, static/css/, static/js/, templates/
**Date:** 2026-02-20
**Reviewer:** Claude (claude-sonnet-4-6)

---

## Executive Summary

The codebase is generally well-structured and follows modern Python/JavaScript conventions. Most issues are low-to-medium severity and stem from gradual accretion over time rather than systemic architectural problems. The most impactful areas to address are: (1) the mixed `var`/`const`/`let` usage in JavaScript, (2) bare `except Exception: pass` blocks in api/routes/pe.py and api/routes/frontend.py that suppress errors silently, (3) inline `import re` statements scattered inside function bodies in utils/, and (4) hardcoded `#fff` color values in main.css that bypass the theming system.

---

## 1. Import Style Consistency

**Pattern:** All files should follow PEP 8 import grouping: stdlib, third-party, local.

### Issues Found

**IMPORTANT — Stdlib import appears after third-party imports in utils/config.py (lines 15-17 vs 379)**

`utils/config.py` imports `json` at line 17 (correctly grouped at module top) but then has a deferred `import os as _os` at line 379 — inside module-level code after a class definition — with a `# noqa: E402` comment to suppress the E402 lint warning.

```python
# utils/config.py lines 15-17 (correct top-of-file section)
from pathlib import Path
from typing import Dict, Optional, Any
import json

# ... ~362 lines of class definitions ...

# line 379 — deferred top-level import (non-standard)
import os as _os  # noqa: E402
```

The `_os` alias indicates this was added to avoid a name collision, but placing a stdlib import mid-file is confusing and requires a lint suppression comment. The clean fix is to import `os as _os` at the top of the file alongside the other stdlib imports.

**IMPORTANT — Inline `import re` inside function bodies (multiple files)**

The following files contain `import re` inside function bodies rather than at module level:

- `utils/config.py`: lines 315, 344, 367 (inside `ColumnMapping.normalize_header`, `FilePatterns.is_budget_document`, `FilePatterns.get_fiscal_year_from_filename`)
- `utils/formatting.py`: lines 179 and 419 (inside `highlight_terms` and `extract_snippet_highlighted`)

This is a performance concern — Python caches module imports but the lookup still happens on every call. More importantly it is inconsistent with the rest of the codebase where `re` is imported at module scope (e.g., `utils/database.py` line 17, `utils/search_parser.py` line 29). All `import re` calls should be lifted to module level.

```python
# Current (inconsistent) — utils/formatting.py line 179
def highlight_terms(text: str, terms: List[str], marker: str = ">>>") -> str:
    result = text
    for term in terms:
        import re   # <-- should be at module top
        pattern = re.compile(re.escape(term), re.IGNORECASE)
```

**MINOR — `utils/validation.py` deferred stdlib import at module body level (line 407)**

```python
# utils/validation.py line 407
import json as _json  # noqa: E402
```

Same pattern as `utils/config.py`. This is used to monkey-patch `ValidationResult` with a `to_json()` method. The import should move to module top; the monkey-patch can stay where it is.

**MINOR — `utils/http.py` import order: stdlib after third-party (lines 10-16)**

```python
import json                # stdlib
from pathlib import Path   # stdlib
from datetime import ...   # stdlib
from typing import ...     # stdlib
import requests            # third-party  <-- comes after stdlib, correct
from requests.adapters ...  # third-party
from urllib3 ...           # third-party
```

The ordering here is actually correct but `json` (stdlib) is separated from `Path`/`datetime`/`typing` by nothing — no blank line separates stdlib from third-party. This is minor but differs from the convention in `api/database.py` which correctly uses blank lines between groups.

---

## 2. Logging Patterns — print() Usage in Library Code

**Pattern:** The CLAUDE.md standard states "use `logging` module instead of `print()` in library code."

### Issues Found

**IMPORTANT — `utils/common.py` lines 124-125: `print()` in `get_connection()` error path**

```python
# utils/common.py lines 123-126
if not db_path.exists():
    print(f"ERROR: Database not found: {db_path}")
    print("Run 'python build_budget_db.py' first to build the database.")
    sys.exit(1)
```

`get_connection()` is a library function called by API code and scripts. Using `print()` and `sys.exit(1)` here is inappropriate for a library. The parallel function `create_connection()` in the same file (line 92) raises `FileNotFoundError` instead, which is the correct pattern. `get_connection()` appears to be a legacy compatibility shim but it is still exported from `utils/__init__.py`.

**IMPORTANT — `utils/http.py` line 267: `print()` in `CacheManager.put()` warning path**

```python
# utils/http.py line 267
except OSError as e:
    print(f"Warning: Failed to write cache file {cache_file}: {e}")
```

`CacheManager` is a library class. The warning should use `logging.getLogger(__name__).warning(...)` rather than `print()`.

**MINOR — `utils/progress.py` and `utils/formatting.py`: `print()` in display classes**

`TerminalProgressTracker`, `FileProgressTracker`, `TableFormatter.print_table()`, and `ReportFormatter.print_report()` all use `print()` directly. These classes are explicitly designed to write to stdout, so this is intentional and acceptable. However the class names (`TerminalProgressTracker`, `print_table`, `print_report`) make the intent clear. No change required here.

**Summary of files using `print()` in ways that conflict with the logging policy:**
- `utils/common.py` — `get_connection()` (error path) — should raise exception or use logger
- `utils/http.py` — `CacheManager.put()` (warning) — should use logger

---

## 3. Error Handling Patterns

**Pattern:** API routes should use `HTTPException` with appropriate status codes. `except Exception` with no logging and a bare `pass` hides bugs.

### Issues Found

**CRITICAL — Numerous bare `except Exception: pass` blocks in api/routes/pe.py and api/routes/frontend.py**

The following catch-all blocks silently suppress all exceptions including `KeyboardInterrupt` (though Python 3 separates that) and programming errors like `AttributeError`, `NameError`, or `TypeError`. When these fire during development or after a schema change, there is no log trace to debug with.

`api/routes/pe.py`:
- Line 290: `except Exception: pass` — enrichment description fetch
- Line 338: `except Exception: pass` — tag fetch
- Line 906: `except Exception: pass` — funding total query
- Line 930: `except Exception: pass` — (comment says "Table may not exist")

`api/routes/frontend.py`:
- Line 514: `except Exception: pass`
- Line 582: `except Exception: pass`
- Line 652: `except Exception: pass`
- Line 679: `except Exception: pass`

`api/routes/search.py`:
- Lines 345, 359, 373, 387, 401: five bare `except Exception: pass` blocks in the autocomplete/suggest helper

The correct pattern (demonstrated in `api/routes/search.py` lines 234-235 and 265-266) is:
```python
except Exception:
    logger.warning("PDF pages FTS query failed for q=%r", q, exc_info=True)
    rows = []
```

Bare passes are acceptable when the table is known to potentially not exist AND the fallback is a silent empty result — but even then, a `logger.debug(...)` call would make debugging significantly easier.

**IMPORTANT — `except Exception: pass` in api/routes/dashboard.py (lines 204, 222, 238, 262, 284)**

Five consecutive `except Exception: pass` blocks all annotated with comments like "# budget_type column may not exist" or "# Tables may not exist". These are more defensible since the dashboard is designed to be resilient to missing optional enrichment tables, but they should use `logger.debug()` at minimum.

**IMPORTANT — `api/routes/frontend.py` lines 608-609: catching HTTPException and re-raising a different one**

```python
# api/routes/frontend.py lines 603-609
except HTTPException:
    raise HTTPException(status_code=404, detail=f"Program {pe_number} not found")
```

This pattern swallows the original exception detail from the inner `HTTPException`. If the inner raise has a meaningful error message (e.g., the enrichment table message on line 603), that information is lost and replaced with the generic "not found" message. The `except HTTPException: raise` pattern should re-raise the original or at least inspect `exc.status_code` before deciding whether to replace it.

**MINOR — `api/routes/reference.py` uses `except Exception` as a fallback query strategy**

Lines 34 and 58 catch `Exception` when the reference table doesn't exist and fall back to querying `budget_lines` directly. This is a valid resilience pattern, but the exception type should be narrowed to `sqlite3.OperationalError` to avoid masking legitimate bugs.

---

## 4. Type Annotation Coverage

**Pattern:** All public functions and methods should have type annotations per CLAUDE.md.

### Issues Found

**IMPORTANT — `api/routes/frontend.py` lines 38-53: `register_error_handlers` takes untyped `app` parameter; inner handlers take untyped `exc` parameter**

```python
# api/routes/frontend.py line 38
def register_error_handlers(app) -> None:   # app has no type annotation
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):  # exc untyped
    @app.exception_handler(500)
    async def server_error_handler(request: Request, exc):  # exc untyped
```

`app` should be typed as `FastAPI` and `exc` should be typed as `Exception` (or more specifically `StarletteHTTPException` for the 404/500 handlers).

**IMPORTANT — `api/routes/dashboard.py` route handler return type is `dict` (bare, no generic)**

```python
# api/routes/dashboard.py line 32
) -> dict:
```

All PE route handlers in `api/routes/pe.py` also return `-> dict:` without a generic parameter. The consistent pattern used elsewhere is `dict[str, Any]` (as seen in `api/routes/frontend.py` helper functions). Routes returning untyped `dict` bypass FastAPI's response validation.

**IMPORTANT — `utils/validation.py` `_add_to_json` decorator and monkey-patch at lines 410-426 have no type annotations on the injected method**

The function `to_json` injected via monkey-patch has a docstring but no annotations matching the surrounding module style:

```python
# utils/validation.py lines 424-426
ValidationResult.to_json = lambda self, indent=2: _json.dumps(  # type: ignore
    self.to_dict(), indent=indent, default=str
)
```

The lambda has no type annotation and there is a dead code block above it (`_add_to_json` decorator at lines 410-420 is defined but never applied).

**MINOR — Several `utils/` functions use older `typing.Optional`, `typing.List`, `typing.Dict` instead of the modern built-in generics**

`utils/formatting.py` (line 15): `from typing import Optional, List, Dict, Any`
`utils/http.py` (line 13): `from typing import Optional, Dict, List, Any`
`utils/validation.py` (line 15): `from typing import List, Dict, Any, Callable, Optional`
`utils/manifest.py` (line 12): `from typing import Optional, Dict, List, Any`

These files use `Optional[str]`, `List[str]`, `Dict[str, Any]` in annotations throughout. The project already uses the modern syntax in many places (`str | None`, `list[str]`, `dict[str, Any]` — e.g., `utils/query.py`, `utils/strings.py`, `utils/cache.py`). The older typing imports should be migrated to the modern syntax for consistency. Since `requires-python >= 3.10` this is safe.

---

## 5. Docstring Consistency

**Pattern:** The codebase uses Google-style docstrings (Args:/Returns:/Raises: sections) throughout `utils/`. API route functions in `api/routes/` are inconsistent.

### Issues Found

**IMPORTANT — api/routes/pe.py route handler functions have minimal or no docstrings**

Most route handler functions in `api/routes/pe.py` have no docstring at all, e.g.:

```python
# api/routes/pe.py line 69
def get_top_changes(
    direction: str | None = Query(...),
    ...
) -> dict:
    # No docstring
    cache_key = ...
```

Contrast with `api/routes/search.py` which provides docstrings on route handlers, or `api/routes/aggregations.py` which has a complete module docstring explaining the endpoint semantics. The `api/routes/pe.py` file has module-level documentation but not per-route docstrings.

**MINOR — api/routes/dashboard.py route handler has a docstring, but private `_detect_fy_columns` helper does not use Args:/Returns: sections**

```python
# api/routes/dashboard.py line 17
def _detect_fy_columns(conn: sqlite3.Connection) -> tuple[str, str]:
    """Detect the best FY request and enacted column names dynamically."""
    # Single-line docstring — no Args:/Returns: sections
```

All `utils/` functions follow the multi-section Google style. Single-line docstrings are fine for simple functions but the `utils/` convention is to always include `Args:` and `Returns:` sections even for short functions. The API route helpers are inconsistent in this regard.

**MINOR — Dead code comment at the bottom of utils/config.py (lines 9-12) and utils/formatting.py (lines 9-12) and utils/validation.py (lines 9-12)**

All three files contain identical stale header sections:
```
──────────────────────────────────────────────────────────────────────────────
TODOs for this file
──────────────────────────────────────────────────────────────────────────────
```
followed by an empty section. These are boilerplate artifacts that were never filled in and add noise to the module docstrings.

---

## 6. Path Handling Consistency

**Pattern:** Use `Path` objects, not raw strings, for file paths per CLAUDE.md.

### Issues Found

**IMPORTANT — `utils/common.py` `get_connection()` uses `str(db_path)` to connect (line 128) while `create_connection()` in the same file also uses `str(db_path)` (line 100)**

Both functions convert `Path` to `str` for `sqlite3.connect()`. This is technically required since `sqlite3.connect()` does not accept `Path` objects directly in Python < 3.11. However, `api/database.py` already uses the URI string form `f"file:{self._db_path}?mode=ro"` (line 67) which also requires string conversion. The pattern is consistent but should be documented as the reason for the `str()` call.

**IMPORTANT — `api/app.py` uses `os.path.getsize(str(db_path))` instead of `Path.stat().st_size`**

```python
# api/app.py line 532
db_size = os.path.getsize(str(db_path))
```

The idiomatic `Path` approach is:
```python
db_size = db_path.stat().st_size
```

This is the only `os.path` call in the api/ directory; all other path operations correctly use `Path` methods.

**MINOR — `utils/http.py` `CacheManager.__init__` redundantly wraps an already-`Path` argument with `Path()` (line 199)**

```python
# utils/http.py line 199
self.cache_dir = Path(cache_dir)   # cache_dir is typed as Path, wrapping is redundant
```

The parameter is typed `cache_dir: Path` but wrapped again. This is harmless but inconsistent with the rest of the codebase.

---

## 7. Database Connection Patterns

**Pattern:** API routes should use `Depends(get_db)` from `api/database.py`. Utility scripts use `create_connection()` from `utils/common.py`.

### Issues Found

**IMPORTANT — Two parallel, slightly different connection functions exist in `utils/common.py`**

`create_connection()` (line 69) raises `FileNotFoundError` and applies WAL pragmas. `get_connection()` (line 110) calls `print()` and `sys.exit(1)`. Both are exported from `utils/__init__.py`. The `get_connection()` function is explicitly labeled a "legacy" shim in its docstring but it is still actively exported. This creates confusion about which to use in new code. `get_connection()` should be deprecated with a warning or removed.

**IMPORTANT — `api/app.py` health endpoints bypass the connection pool**

The `/health` and `/health/detailed` endpoints in `api/app.py` (lines 478, 518) open a direct `sqlite3.connect()` rather than using `get_db` or the connection pool:

```python
# api/app.py lines 476-481
try:
    conn = sqlite3.connect(str(db_path))   # bypasses pool
    count = conn.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0]
    conn.close()
    return {"status": "ok", ...}
```

This is a deliberate design choice to avoid blocking the pool for health checks, but it means the health check is not exercising the same code path as normal requests. A comment explaining this design decision would help, and the health check should at minimum apply `conn.row_factory = sqlite3.Row` for consistency.

**MINOR — `api/routes/dashboard.py` does not import `HTTPException` but still accesses potentially missing columns**

`dashboard.py` imports `APIRouter, Depends, Query` from fastapi but not `HTTPException`. All five `except Exception: pass` blocks silently absorb failures. If the endpoint should signal "no data available" rather than return zeros, it would need `HTTPException`. This is a design question, not a bug, but the omission is notable.

---

## 8. Response Model Consistency

**Pattern:** API endpoints should declare `response_model=` on `@router.get()` decorators and return type annotations should match the model.

### Issues Found

**IMPORTANT — Inconsistency between `response_model` declaration and actual return type in `api/routes/reference.py`**

Reference endpoints declare `response_model=list[ServiceOut]` etc. but return `JSONResponse` directly:

```python
# api/routes/reference.py lines 22-27
@router.get(
    "/services",
    response_model=list[ServiceOut],  # declares model
    summary="...",
)
def list_services(...) -> JSONResponse:   # returns raw JSONResponse
```

When a function returns `JSONResponse` directly, FastAPI bypasses Pydantic model validation entirely. The `response_model` annotation is effectively dead code here. The pattern should be either: return the raw data (`list[dict]`) and let FastAPI validate it via `response_model`, OR remove `response_model` and keep `JSONResponse`. The `api/routes/aggregations.py` endpoint correctly returns `AggregationResponse` (a Pydantic model), which is the preferred pattern.

**IMPORTANT — `api/routes/pe.py` and `api/routes/dashboard.py` route handlers return bare `dict` without a `response_model`**

Most PE endpoints return `-> dict:` with no `response_model=` on the decorator, so there is no schema validation or documentation generated. Compare to `api/routes/budget_lines.py` and `api/routes/search.py` which consistently use `response_model=PaginatedResponse` and `response_model=SearchResponse` respectively.

**IMPORTANT — `api/routes/dashboard.py` route handler returns `-> dict` but is annotated with `summary=` only**

```python
# api/routes/dashboard.py lines 25-32
@router.get("/summary", summary="Dashboard summary statistics")
def dashboard_summary(...) -> dict:
```

No `response_model`, so the OpenAPI schema for this endpoint shows an empty object. If the dashboard is a user-facing endpoint, consumers benefit from knowing the schema.

**MINOR — `api/routes/search.py` suggest endpoint uses `response_model=list[dict]` (line 304)**

```python
@router.get(..., response_model=list[dict], ...)
def suggest_search(...) -> list[dict]:
```

`list[dict]` is an untyped response model — FastAPI cannot validate or document the structure of each dict. A typed `SuggestionItem` model would be consistent with how `SearchResultItem` is used in the main search endpoint.

---

## 9. CSS Variable Usage

**Pattern:** All colors must use CSS custom properties (variables), no hardcoded hex values per CLAUDE.md.

### Issues Found

**IMPORTANT — `static/css/main.css` contains multiple hardcoded `#fff` and `#555` values outside the `:root` and `[data-theme="dark"]` blocks**

The following usages of hardcoded color values were found in rules that apply to all themes:

- Line 149: `.site-header { color: #fff; }` — should be a variable like `var(--header-text)` or at minimum reference the semantic token.
- Line 167: `.site-title { color: #fff; }` — same issue.
- Line 181: `.nav-links a { color: rgba(255,255,255,.85); }` — hardcoded white.
- Line 186: `.nav-links a:hover { color: #fff; }` — hardcoded white.
- Line 202: (button/form elements) `background: #fff;` — should be `var(--bg-surface)`.
- Line 416: `.btn-primary:hover { color: #fff; }` — hardcoded white.
- Line 475: `.col-toggle.active { color: #fff; }` — hardcoded white.
- Line 541: `.page-btn.active { color: #fff; }` — hardcoded white.
- Line 1049: `.print-header .print-meta { color: #555; }` — hardcoded gray (in print media query).
- Line 1071: print media query `background: #fff;` — may be intentional for print but should be documented.
- Lines 1650-1651: `.btn-primary { color: #fff; }` in dark mode — these exist in `[data-theme="dark"]` override block and are therefore intentional.

In the header/nav context, `#fff` is always correct since `--bg-header` is dark navy in both light and dark themes. However, the correct approach is to add a `--header-text-color: #fff` CSS variable to `:root` so the intent is semantic. The hardcoded usage at line 202 (`background: #fff`) outside the header is a genuine issue since dark mode overrides `--bg-surface` but those rules would not be overridden.

**IMPORTANT — `static/js/charts.js` line 407: hardcoded `color: '#fff'` in Chart.js treemap label config**

```javascript
// static/js/charts.js line 407
color: '#fff',
```

This is a Chart.js dataset option for treemap labels. It cannot use a CSS variable directly in a Chart.js config object. The correct pattern (used elsewhere in the codebase, e.g., `api/routes/frontend.py` in the doughnut chart) is to read the CSS variable at runtime:
```javascript
color: getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim() || '#fff'
```

---

## 10. JavaScript Patterns

**Pattern:** Files should consistently use `const`/`let` for block-scoped declarations, consistent quote style, consistent error handling, and the `"use strict"` directive.

### Issues Found

**IMPORTANT — Mixed `var`/`const`/`let` in app.js**

`app.js` mixes declaration keywords throughout the same file:

- Module-level constants use both `var` (line 16: `var THEME_KEY`) and `const` (line 52: `const COL_KEY`, line 53: `const PAGE_SIZE_KEY`), then back to `var` (line 54: `var AMT_FMT_KEY`).
- Inside `DOMContentLoaded`, there is `let debounceTimer = null` (line 848) and `const form = document.getElementById(...)` (line 849) mixed with `var` declarations in the enclosing function scope.
- The `restoreFiltersFromURL` function (line 202) uses `const` throughout, while `toggleFilterPanel` (line 173) uses `var` throughout.

The file declares `"use strict"` (line 12), so `var` hoisting behavior applies but can be confusing. All files should standardize on `const`/`let` throughout.

**IMPORTANT — `escapeHtml` function is defined locally inside an IIFE in dashboard.js (line 208) but a parallel `_escapeHtml` is defined in app.js (line 905)**

```javascript
// dashboard.js line 208
function escapeHtml(s) { ... }  // inside IIFE, not accessible outside

// app.js line 905
function _escapeHtml(s) { ... }  // module-level, accessible globally
```

These two functions have identical implementations but different names and scopes. `dashboard.js` also calls `escapeHtml` (line 180) from within its IIFE while `app.js` uses `_escapeHtml`. This duplication should be extracted to a shared utility or one should call the other.

**IMPORTANT — Event listener registration in app.js uses both `addEventListener` and inline `onclick` attributes (inconsistent)**

`app.js` correctly removes `onclick` from the download modal button and replaces it with `addEventListener` (line 876-878). But `renderSavedSearches()` at line 1044 injects HTML strings with `onclick="deleteSavedSearch(' + i + ')"` inline handlers, which:
- Cannot be removed individually.
- Are vulnerable to XSS if `i` were ever user-controlled (it is an array index here, so currently safe).
- Are inconsistent with the event delegation pattern used elsewhere.

The consistent pattern should use `data-*` attributes and event delegation.

**IMPORTANT — `dashboard.js` uses `async/await` at the top level (line 34), while `app.js` uses `.then()/.catch()` chains (line 367) — inconsistent async style**

```javascript
// dashboard.js line 34-41 — async/await pattern
(async function initDashboard() {
  var resp = await fetch("/api/v1/dashboard/summary");
  if (!resp.ok) throw new Error("HTTP " + resp.status);
  var data = await resp.json();
  ...
})();

// app.js line 689-706 — Promise chain pattern
fetch("/api/v1/metadata")
  .then(function(r) { return r.ok ? r.json() : null; })
  .then(function(data) { ... })
  .catch(function() { ... });
```

`program-detail.js` also uses `async/await`. One consistent style should be chosen. Given that `"use strict"` is used and the project targets modern browsers (no IE support indicated), `async/await` is preferred for readability.

**MINOR — `charts.js` uses single-quote strings (`'#2563eb'`) while `app.js` and `dashboard.js` use double-quote strings (`"#2563eb"`)**

All JS files should standardize on one quote style. The majority of the codebase uses double quotes; `charts.js` is the outlier.

**MINOR — `dark-mode.js` does not declare `"use strict"`**

```javascript
// dark-mode.js line 6
(function() {
  var saved = localStorage.getItem('dod_theme');
  ...
})();
```

All other JS files include `"use strict"`. This file is simple (3 lines of logic) but consistency requires the directive.

---

## Next Steps

The issues above are grouped by severity:

**Critical (address before next release):**
- The 5+ bare `except Exception: pass` blocks in `api/routes/pe.py` and 4+ in `api/routes/frontend.py` that silently suppress programming errors. Add at minimum `logger.debug("...", exc_info=True)` to each.

**Important (address in next sprint):**
1. Lift inline `import re` calls in `utils/config.py` and `utils/formatting.py` to module level.
2. Move the `import os as _os` in `utils/config.py` to the top-of-file imports block.
3. Replace `os.path.getsize(str(db_path))` with `db_path.stat().st_size` in `api/app.py`.
4. Replace `print()` calls in `utils/common.py` (get_connection) and `utils/http.py` (CacheManager.put) with `logging`.
5. Fix `reference.py` `response_model=` declarations to either use Pydantic validation or remove the dead annotation.
6. Add return type annotations to `api/routes/dashboard.py` route handler (`dict` → `dict[str, Any]`) and untype `app` parameter in `register_error_handlers`.
7. Standardize `var` → `const`/`let` in `app.js`.
8. Extract the duplicate `escapeHtml`/`_escapeHtml` to a shared module-level function.
9. Fix hardcoded `#fff` in `static/css/main.css` for non-header/non-print contexts (primarily line 202 `background: #fff`).
10. Replace Chart.js hardcoded `color: '#fff'` in `charts.js` line 407 with a CSS variable lookup.

**Minor (backlog):**
1. Migrate `utils/` typing imports from `Optional[str]` to `str | None`, `List[str]` to `list[str]`, etc.
2. Remove the stale "TODOs for this file" empty section from `utils/config.py`, `utils/formatting.py`, `utils/validation.py`.
3. Add `"use strict"` to `dark-mode.js`.
4. Standardize JS async style (`async/await` over `.then()` chains) across `app.js`.
5. Standardize JS string quotes to double quotes across all files.
6. Add `logger.debug()` calls to the five `except Exception: pass` blocks in `api/routes/dashboard.py`.
7. Narrow `except Exception` to `except sqlite3.OperationalError` in `api/routes/reference.py` fallback paths.
8. Add docstrings to PE route handler functions in `api/routes/pe.py`.
9. Deprecate or remove the legacy `get_connection()` function from `utils/common.py`.
10. Add `response_model=` for dashboard and PE endpoints to improve OpenAPI documentation.
