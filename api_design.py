"""
API Layer Design — Step 2.C

**Status:** Phase 2 Planning (Phase 1 currently in progress)

Plans and TODOs for the REST API that will expose the budget database for
programmatic access and power the front-end. This file documents the detailed
design and task breakdown for API implementation in Phase 2.

──────────────────────────────────────────────────────────────────────────────
Phase 2 Tasks — Step 2.C (API Layer)
──────────────────────────────────────────────────────────────────────────────

TODO 2.C1-a [Complexity: LOW] [Tokens: ~1000] [User: NO]
    Choose web framework and document the decision.
    Steps:
      1. Write 20-line decision record: FastAPI vs Flask vs Litestar
      2. Criteria: auto OpenAPI docs, async, Pydantic validation, deployment
      3. Recommendation: FastAPI (best OpenAPI + Pydantic + async support)
      4. Add `fastapi>=0.109` and `uvicorn[standard]>=0.25` to requirements.txt
    Success: Decision documented; dependencies added.

TODO 2.C2-a [Complexity: LOW] [Tokens: ~500] [User: NO]
    DONE — API_SPECIFICATION.yaml already defines the full endpoint contract.
    Verify completeness: /search, /budget-lines, /aggregations,
    /budget-lines/{id}, /download, /reference/* (7 endpoints total).
    Success: Spec reviewed and confirmed complete.

TODO 2.C7-a [Complexity: MEDIUM] [Tokens: ~2000] [User: NO]
    Create api/ package structure with FastAPI app factory.
    This is a prerequisite for all 2.C3-* through 2.C5-* TODOs.
    Steps:
      1. Create api/__init__.py, api/app.py, api/database.py
      2. Create api/routes/ directory with __init__.py
      3. In api/app.py: create_app(db_path) factory function
      4. Add DB connection lifecycle (startup/shutdown events)
      5. Add `if __name__`: run with uvicorn for development
    Success: `python -m api.app` starts server; GET /docs shows OpenAPI spec.

TODO 2.C3-a [Complexity: MEDIUM] [Tokens: ~2500] [User: NO]
    Implement GET /api/v1/search endpoint.
    Dependency: TODO 2.C7-a (app structure) must exist.
    Steps:
      1. Create api/routes/search.py
      2. Accept q (required), limit (default 20, max 100), offset (default 0)
      3. Reuse FTS5 MATCH logic from search_budget.py
      4. Return unified results with snippet highlighting
    Success: GET /api/v1/search?q=procurement returns highlighted results.

TODO 2.C3-b [Complexity: MEDIUM] [Tokens: ~3000] [User: NO]
    Implement GET /api/v1/budget-lines endpoint.
    Steps:
      1. Create api/routes/budget_lines.py
      2. Accept optional filters: fiscal_year, service, appropriation,
         pe_number, exhibit_type (all as lists for multi-select)
      3. Build SQL WHERE clause dynamically with parameterized queries
      4. Add sort (column + direction) and pagination (limit/offset)
      5. Also handle GET /api/v1/budget-lines/{id} for single item
    Success: Filtered queries return correct paginated JSON results.

TODO 2.C3-c [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Implement GET /api/v1/aggregations endpoint.
    Steps:
      1. Create api/routes/aggregations.py
      2. Accept group_by (required: service|fiscal_year|appropriation|
         exhibit_type) plus optional filters
      3. Return GROUP BY + SUM(amount_thousands) results
    Success: group_by=service returns per-service budget totals.

TODO 2.C3-d [Complexity: LOW] [Tokens: ~1000] [User: NO]
    Implement 3 reference data endpoints (for UI dropdowns).
    Steps:
      1. Create api/routes/reference.py
      2. GET /reference/services, /reference/exhibit-types, /reference/fiscal-years
      3. Query reference tables; return all rows
      4. Add Cache-Control: max-age=3600 headers
    Success: All 3 endpoints return JSON arrays for dropdown population.

TODO 2.C4-a [Complexity: MEDIUM] [Tokens: ~2500] [User: NO]
    Implement GET /api/v1/download endpoint (CSV/JSON export).
    Steps:
      1. Create api/routes/download.py
      2. Accept same filters as budget-lines + format=csv|json
      3. CSV: StreamingResponse with csv.writer generator
      4. JSON: StreamingResponse with line-delimited JSON
      5. Add Content-Disposition header for browser download
    Success: Large result sets stream without memory issues.

TODO 2.C5-a [Complexity: MEDIUM] [Tokens: ~2500] [User: NO]
    Add Pydantic models for request/response validation.
    Steps:
      1. Create api/models.py
      2. Define: SearchParams, BudgetLineFilters, AggregationParams,
         BudgetLineResponse, SearchResult, AggregationResult
      3. Add Field() descriptions for auto-generated OpenAPI docs
      4. Add example values for /docs interactive testing
    Success: All endpoints use typed models; /docs shows rich examples.

TODO 2.C5-b [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Add error handling middleware.
    Steps:
      1. In api/app.py, add exception handlers:
         - 400 → Pydantic ValidationError (invalid params)
         - 404 → DB not found or item not found
         - 408 → query timeout
         - 500 → unexpected server errors
      2. Return structured JSON: {error, detail, status_code}
    Success: All error cases return JSON, not HTML stack traces.

TODO 2.C6-a [Complexity: MEDIUM] [Tokens: ~4000] [User: NO]
    Write API tests using pytest + httpx (FastAPI TestClient).
    Dependency: Requires all 2.C3-* through 2.C5-* TODOs done.
    Steps:
      1. Create tests/test_api.py
      2. Wire test_db fixture to FastAPI app via TestClient
      3. Test each endpoint: happy path, empty results, invalid params,
         pagination edge cases, CSV/JSON export correctness
    Success: All 7+ endpoints tested; pytest passes.
"""

# Placeholder — API implementation will go in api/ directory
# Suggested structure:
#   api/
#     __init__.py
#     app.py          — FastAPI application factory
#     routes/
#       search.py     — /search endpoint
#       budget_lines.py — /budget-lines endpoint
#       aggregations.py — /aggregations endpoint
#       download.py   — /download endpoint
#       reference.py  — /reference/* endpoints
#     models.py       — Pydantic request/response models
#     database.py     — DB connection management
