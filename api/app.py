"""
FastAPI application factory (Step 2.C7-a).

Usage:
    python -m api.app                    # Dev server on port 8000
    APP_DB_PATH=/data/dod.sqlite python -m api.app

OpenAPI docs available at http://localhost:8000/docs after starting.

2.C1-a Decision record:
    Framework chosen: FastAPI
    Rationale:
      - Auto-generates OpenAPI 3.1 schema at /docs and /openapi.json
      - Pydantic v2 validation on request/response models
      - Native async; plays well with uvicorn/anyio
      - Dependency injection via Depends() keeps routes testable
      - More structured than Flask for this data-access pattern
    Alternatives rejected:
      - Flask: no auto-OpenAPI; must add flask-restx or apispec manually
      - Litestar: excellent but newer ecosystem; fewer resources
    Dependencies added to requirements.txt: fastapi>=0.109, uvicorn[standard]>=0.25
"""

import logging
import sqlite3
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.database import get_db_path
from api.routes import aggregations, budget_lines, download, reference, search

# ── Request logging (4.C3-a) ─────────────────────────────────────────────────
_logger = logging.getLogger("dod_budget_api")
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    level=logging.INFO,
)

# ── Rate limiting state (4.C4-a) ─────────────────────────────────────────────
# Simple fixed-window per-IP rate limiter (no Redis needed for single-process).
# Limits: search=60/min, download=10/min, others=120/min.
_RATE_LIMITS: dict[str, int] = {
    "/api/v1/search":   60,
    "/api/v1/download": 10,
}
_DEFAULT_RATE_LIMIT = 120          # requests per minute for all other endpoints
_rate_counters: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validate database path on startup (Step 2.C7-a lifecycle)."""
    db_path = get_db_path()
    if not db_path.exists():
        import warnings
        warnings.warn(
            f"Database not found at {db_path}. "
            "Run 'python build_budget_db.py' first.",
            stacklevel=2,
        )
    yield


def create_app(db_path: Path | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        db_path: Override the database path (useful for testing).

    Returns:
        Configured FastAPI application instance.
    """
    if db_path is not None:
        import api.database as _db_mod
        _db_mod._DB_PATH = db_path

    app = FastAPI(
        title="DoD Budget API",
        summary="REST API for searching and analyzing DoD budget justification data.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── Request logging + rate limiting middleware (4.C3-a, 4.C4-a) ──────────

    @app.middleware("http")
    async def log_and_rate_limit(request: Request, call_next):
        """Log each request and enforce per-IP rate limits."""
        start = time.monotonic()
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path

        # Rate limiting
        limit = _RATE_LIMITS.get(path, _DEFAULT_RATE_LIMIT)
        now = time.time()
        window_start = now - 60.0
        hits = _rate_counters[client_ip][path]
        # Prune timestamps outside the window
        _rate_counters[client_ip][path] = [t for t in hits if t > window_start]
        if len(_rate_counters[client_ip][path]) >= limit:
            _logger.warning(
                "rate_limited ip=%s path=%s limit=%d", client_ip, path, limit
            )
            return JSONResponse(
                status_code=429,
                content={"error": "Too many requests", "status_code": 429},
                headers={"Retry-After": "60"},
            )
        _rate_counters[client_ip][path].append(now)

        # Dispatch and log
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000
        _logger.info(
            "method=%s path=%s status=%d duration_ms=%.1f ip=%s",
            request.method, path, response.status_code, duration_ms, client_ip,
        )
        if duration_ms > 500:
            _logger.warning(
                "slow_query method=%s path=%s duration_ms=%.1f",
                request.method, path, duration_ms,
            )
        return response

    # ── Error handling middleware (2.C5-b) ────────────────────────────────────

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        """Catch unhandled exceptions and return JSON instead of HTML traceback."""
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "detail": str(exc),
                "status_code": 500,
            },
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=400,
            content={"error": "Bad request", "detail": str(exc), "status_code": 400},
        )

    # ── Health check ──────────────────────────────────────────────────────────

    @app.get("/health", tags=["meta"], summary="Health check")
    def health():
        """Return 200 OK if the API is running and can reach the database."""
        db_path = get_db_path()
        db_ok = db_path.exists()
        if db_ok:
            try:
                conn = sqlite3.connect(str(db_path))
                count = conn.execute("SELECT COUNT(*) FROM budget_lines").fetchone()[0]
                conn.close()
                return {"status": "ok", "database": str(db_path), "budget_lines": count}
            except Exception as e:
                return JSONResponse(
                    status_code=503,
                    content={"status": "degraded", "error": str(e)},
                )
        return JSONResponse(
            status_code=503,
            content={"status": "no_database", "database": str(db_path)},
        )

    # ── Register routers ──────────────────────────────────────────────────────

    prefix = "/api/v1"
    app.include_router(search.router,       prefix=prefix)
    app.include_router(budget_lines.router, prefix=prefix)
    app.include_router(aggregations.router, prefix=prefix)
    app.include_router(reference.router,    prefix=prefix)
    app.include_router(download.router,     prefix=prefix)

    return app


# Singleton instance for uvicorn
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
