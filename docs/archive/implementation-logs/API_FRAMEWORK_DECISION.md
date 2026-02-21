# API Framework Decision Record — TODO 2.C1-a

**Decision:** Use **FastAPI** as the web framework for the DoD Budget Analysis REST API.

**Date:** 2026-02-18
**Status:** Approved

---

## Context

The DoD Budget Analysis project requires a REST API to expose the budget database for:
- Programmatic access (data export, integration with other systems)
- Powering the front-end web UI (search, filtering, visualization)
- Supporting reference data endpoints (services, exhibit types, fiscal years)

Three frameworks were evaluated: **FastAPI**, **Flask**, and **Litestar**.

---

## Evaluation Criteria

1. **Automatic OpenAPI Documentation** — Framework generates /docs endpoint with interactive schema
2. **Type Validation** — Built-in request/response validation with type hints
3. **Async Support** — Non-blocking database queries and concurrent requests
4. **Middleware Ecosystem** — Built-in error handling, CORS, logging
5. **Dependency Footprint** — Minimal dependencies to reduce deployment complexity
6. **Deployment Simplicity** — Can run as a single process with uvicorn

---

## Comparison Matrix

| Criterion | FastAPI | Flask | Litestar |
|-----------|---------|-------|----------|
| **OpenAPI Docs** | Auto-generated at /docs | Requires extension (Flasgger) | Auto-generated |
| **Type Validation** | Built-in (Pydantic) | Manual or marshmallow | Built-in (Pydantic) |
| **Async Support** | Native async/await | Limited (async routes exist but older design) | Native async/await |
| **Dependencies** | 5-6 core (uvicorn, pydantic, starlette) | 3-4 (werkzeug, jinja2) | 5-6 (uvicorn, pydantic) |
| **Learning Curve** | Moderate (modern Python patterns) | Very shallow (simple routing) | Moderate |
| **Query Performance** | Excellent (async, non-blocking) | Good (but sync by default) | Excellent (async) |

---

## Recommendation: FastAPI

### Rationale

**FastAPI is the optimal choice for this project because:**

1. **Auto-Documentation:** FastAPI generates a complete, interactive OpenAPI spec at `/api/v1/docs`
   without additional configuration. This satisfies TODO 3.C4-a (Generate OpenAPI documentation)
   automatically as an implementation side effect.

2. **Type Safety:** Pydantic validation models are defined once and used for both request validation
   and OpenAPI schema generation, eliminating redundancy.

3. **Async-First Design:** The budget database queries (full-text search, filtering, aggregations)
   will be non-blocking, allowing the API to handle many concurrent requests efficiently.

4. **Minimal Footprint:** FastAPI has fewer dependencies than a Flask + extension stack, simplifying
   deployment and reducing the attack surface.

5. **Modern Python:** Uses Python 3.7+ features (type hints, async/await) that align with current best practices.

6. **Production-Ready:** Widely used in production (Netflix, Uber, etc.) with mature ecosystem for
   testing (httpx/TestClient) and deployment (uvicorn, Docker).

### Why Not Flask?

- Flask's async support is newer and less integrated into the framework design.
- Manual validation + documentation generation adds boilerplate.
- Better suited for traditional server-rendered web apps than modern APIs.

### Why Not Litestar?

- Litestar is excellent (Starlette-based, like FastAPI) but newer and less mature.
- Smaller ecosystem relative to FastAPI.
- FastAPI is the more conservative choice for this project's timeline.

---

## Implementation Plan

1. **Add to requirements.txt:**
   ```
   fastapi>=0.104.0
   uvicorn[standard]>=0.24.0
   pydantic>=2.0.0
   ```

2. **Create API structure:**
   ```
   api/
     __init__.py
     app.py              # FastAPI application factory
     routes/
       search.py         # /api/v1/search endpoint
       budget_lines.py   # /api/v1/budget-lines endpoint
       aggregations.py   # /api/v1/aggregations endpoint
       download.py       # /api/v1/download endpoint
       reference.py      # /api/v1/reference/* endpoints
     models.py           # Pydantic request/response models
     database.py         # DB connection management
     middleware.py       # Error handling, logging, CORS
   ```

3. **Server Configuration:**
   - Run with: `uvicorn api.app:app --host 0.0.0.0 --port 8000`
   - Can be reverse-proxied by nginx for production deployments
   - Supports graceful shutdown and logging out of the box

4. **Testing:**
   - Use pytest + httpx (FastAPI's TestClient)
   - Test fixtures will be in `tests/conftest.py`
   - Mock database for unit tests, real database for integration tests

---

## Acceptance Criteria

- [ ] FastAPI and uvicorn added to `requirements.txt`
- [ ] `api/` directory structure created with stub files
- [ ] `api/app.py` contains FastAPI() application factory
- [ ] Basic "GET /health" endpoint returns {"status": "ok"}
- [ ] OpenAPI docs accessible at `/docs`

---

## References

- [FastAPI Official Documentation](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Uvicorn Server](https://www.uvicorn.org/)
