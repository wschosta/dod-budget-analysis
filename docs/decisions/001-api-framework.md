# ADR-001: FastAPI as API Framework

**Date:** 2026-02-18
**Status:** Accepted
**Deciders:** Project team

## Context

The DoD Budget Analysis project requires a REST API to:
- Provide programmatic access to budget data (search, filter, export)
- Power the web UI (HTMX-driven search, filtering, visualization)
- Serve reference data endpoints (services, exhibit types, fiscal years)
- Generate interactive API documentation automatically

Three frameworks were evaluated: **FastAPI**, **Flask**, and **Litestar**.

## Decision

Use **FastAPI** as the web framework for the REST API.

## Evaluation

| Criterion | FastAPI | Flask | Litestar |
|-----------|---------|-------|----------|
| **OpenAPI Docs** | Auto-generated at /docs | Requires extension (Flasgger) | Auto-generated |
| **Type Validation** | Built-in (Pydantic v2) | Manual or marshmallow | Built-in (Pydantic) |
| **Async Support** | Native async/await | Limited | Native async/await |
| **Dependencies** | 5-6 core | 3-4 | 5-6 |
| **Learning Curve** | Moderate | Shallow | Moderate |
| **Ecosystem Maturity** | Excellent | Excellent | Growing |

## Rationale

1. **Auto-Documentation** — FastAPI generates a complete, interactive OpenAPI spec at `/docs` without additional configuration, satisfying API documentation requirements as a side effect of development.

2. **Type Safety** — Pydantic v2 models are defined once and used for both request validation and OpenAPI schema generation, eliminating redundancy.

3. **Async-First Design** — Budget database queries (full-text search, filtering, aggregations) run without blocking, allowing efficient concurrent request handling.

4. **Minimal Footprint** — Fewer dependencies than a Flask + extensions stack, simplifying deployment and reducing attack surface.

5. **Modern Python** — Uses type hints and async/await patterns that align with current best practices.

6. **Production Proven** — Widely used in production (Netflix, Uber, Microsoft) with mature testing (TestClient) and deployment (uvicorn, Docker) ecosystem.

### Why Not Flask?

- Async support is newer and less integrated into the framework design.
- Manual validation + documentation generation adds boilerplate.
- Better suited for traditional server-rendered apps than modern APIs.

### Why Not Litestar?

- Newer and less mature ecosystem than FastAPI.
- FastAPI is the more conservative choice for the project timeline.
- Both are Starlette-based with similar performance characteristics.

## Implementation

The API is structured as:

```
api/
├── app.py           # App factory, middleware, rate limiting, health endpoints
├── database.py      # DB path resolution, connection pool, get_db() dependency
├── models.py        # Pydantic request/response models
└── routes/          # One file per router group
    ├── aggregations.py
    ├── budget_lines.py
    ├── dashboard.py
    ├── download.py
    ├── feedback.py
    ├── frontend.py
    ├── metadata.py
    ├── pe.py
    ├── reference.py
    └── search.py
```

Server runs via: `uvicorn api.app:app --host 0.0.0.0 --port 8000`

## Consequences

- **Positive:** Interactive API docs at `/docs` and `/redoc` with zero additional work.
- **Positive:** Type-safe request/response validation catches errors early.
- **Positive:** Single Python process serves both API and frontend (Jinja2 templates).
- **Negative:** Slightly steeper learning curve than Flask for new contributors.
- **Negative:** Async patterns require care with SQLite (which is synchronous).

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Pydantic v2 Documentation](https://docs.pydantic.dev/)
- [Uvicorn Server](https://www.uvicorn.org/)
