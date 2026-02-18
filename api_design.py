"""
API Layer Design — Step 2.C

**Status:** IMPLEMENTED (Phase 2 API complete)

DONE 2.C1-a  FastAPI chosen; decision record in api/app.py docstring.
             fastapi>=0.109 + uvicorn[standard]>=0.25 added to requirements.txt.
DONE 2.C2-a  API_SPECIFICATION.yaml defines full endpoint contract.
DONE 2.C7-a  api/ package created: api/__init__.py, api/app.py, api/database.py,
             api/models.py, api/routes/{__init__,search,budget_lines,
             aggregations,reference,download}.py
             create_app(db_path) factory with lifespan, /health, /docs.
DONE 2.C3-a  GET /api/v1/search — FTS5 across budget lines + PDF pages.
DONE 2.C3-b  GET /api/v1/budget-lines — filterable, sortable, paginated list;
             GET /api/v1/budget-lines/{id} — single item detail.
DONE 2.C3-c  GET /api/v1/aggregations — GROUP BY with SUM(amount_*).
DONE 2.C3-d  GET /api/v1/reference/services, /exhibit-types, /fiscal-years
             with Cache-Control: max-age=3600.
DONE 2.C4-a  GET /api/v1/download?fmt=csv|json — StreamingResponse,
             no full-result memory load.
DONE 2.C5-a  api/models.py: Pydantic models for all request/response types.
DONE 2.C5-b  Error handlers in api/app.py: returns JSON for 400/404/500,
             never HTML tracebacks.

TODO 2.C6-a [Complexity: MEDIUM] [Tokens: ~4000] [User: NO]
    Write API tests using pytest + httpx (FastAPI TestClient).
    Dependency: Requires fastapi + httpx installed (added to requirements.txt).
    Steps:
      1. Create tests/test_api.py
      2. Wire test_db_excel_only fixture to FastAPI app via TestClient
      3. Test each endpoint: happy path, empty results, invalid params,
         pagination edge cases, CSV/JSON export correctness
    Success: All 7+ endpoints tested; pytest passes.
"""
