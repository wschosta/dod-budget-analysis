"""
API Layer Design — Step 2.C

**Status:** Phase 2 Planning (Phase 1 currently in progress)

Plans and TODOs for the REST API that will expose the budget database for
programmatic access and power the front-end. This file documents the detailed
design and task breakdown for API implementation in Phase 2.

──────────────────────────────────────────────────────────────────────────────
Phase 2 Tasks — Step 2.C (API Layer)
──────────────────────────────────────────────────────────────────────────────

TODO 2.C1-a: Choose web framework and document the decision.
    Evaluate: FastAPI vs Flask vs Litestar.
    Criteria: automatic OpenAPI docs, async support, type validation,
    middleware ecosystem, deployment simplicity.
    Recommendation: FastAPI — auto-generates OpenAPI spec, Pydantic validation,
    async, and small dependency footprint.  Write a 20-line decision record.
    Token-efficient tip: this is prose, not code.  Just write the rationale
    and add FastAPI + uvicorn to requirements.txt.

TODO 2.C2-a: Design the API endpoint contract.
    Define the following endpoints (method, path, query params, response shape):

    GET /api/v1/search?q=<text>&limit=&offset=
        Full-text search across budget lines and PDF text.
        Response: { results: [...], total: int, query: str }

    GET /api/v1/budget-lines?fiscal_year=&service=&appropriation=&pe=&exhibit_type=&sort=&limit=&offset=
        Structured query with filters.  All filters optional, combinable.
        Response: { data: [...], total: int, filters_applied: {...} }

    GET /api/v1/aggregations?group_by=<service|year|appropriation>&fiscal_year=&service=
        Aggregated totals grouped by a dimension.
        Response: { data: [{ group: str, total_thousands: int }], filters: {...} }

    GET /api/v1/budget-lines/{id}
        Single line item detail with full metadata.
        Response: { ...all fields... , source_document: {...}, related: [...] }

    GET /api/v1/download?<same filters as budget-lines>&format=csv|json
        Export filtered results.  Stream for large result sets.
        Response: streaming CSV or JSON file.

    GET /api/v1/reference/services
    GET /api/v1/reference/exhibit-types
    GET /api/v1/reference/fiscal-years
        Reference data for populating filter dropdowns.
        Response: { data: [{ id, code, name }] }

    Write this as a YAML or Python dict spec.  ~60 lines.

TODO 2.C3-a: Implement GET /api/v1/search endpoint.
    Accept q (required), limit (default 20, max 100), offset (default 0).
    Use FTS5 MATCH query against budget_lines_fts and pdf_pages_fts.
    Return unified results with snippet highlighting.
    Token-efficient tip: build on the existing search_budget.py query functions
    — wrap them in a FastAPI route.  ~40 lines.

TODO 2.C3-b: Implement GET /api/v1/budget-lines endpoint.
    Accept optional filters: fiscal_year (list), service (list),
    appropriation (list), pe_number (str), exhibit_type (list).
    Build SQL WHERE clause dynamically from provided filters.
    Add sort (column + direction) and pagination (limit/offset).
    ~60 lines.

TODO 2.C3-c: Implement GET /api/v1/aggregations endpoint.
    Accept group_by (required, one of: service, fiscal_year, appropriation,
    exhibit_type) plus optional filters.
    Return GROUP BY + SUM(amount_thousands) results.
    ~30 lines.

TODO 2.C3-d: Implement reference data endpoints.
    Three simple endpoints that query the reference tables and return all rows.
    Cache-friendly (these change rarely).
    ~20 lines total.

TODO 2.C4-a: Implement GET /api/v1/download endpoint.
    Accept the same filters as /budget-lines plus format=csv|json.
    For CSV: use StreamingResponse with csv.writer writing to a generator.
    For JSON: use StreamingResponse with ijson-style line-delimited output.
    Add Content-Disposition header for browser download.
    Token-efficient tip: FastAPI StreamingResponse + a generator that yields
    chunks from the database cursor.  ~50 lines.

TODO 2.C5-a: Add Pydantic models for request validation and response schemas.
    Define: SearchParams, BudgetLineFilters, AggregationParams,
    BudgetLineResponse, SearchResult, AggregationResult.
    These also drive the auto-generated OpenAPI docs.
    ~60 lines of model definitions.

TODO 2.C5-b: Add error handling middleware.
    Catch common errors (invalid params, DB not found, query timeout) and
    return structured JSON error responses with appropriate HTTP status codes.
    ~30 lines.

TODO 2.C6-a: Write API tests using pytest + httpx (FastAPI TestClient).
    Test each endpoint: happy path, empty results, invalid params, pagination
    edge cases, and CSV/JSON export format correctness.
    Dependency: test_db fixture from conftest.py, plus FastAPI app wired to it.
    ~100 lines across multiple test functions.
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
