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

──────────────────────────────────────────────────────────────────────────────
TODOs for this file
──────────────────────────────────────────────────────────────────────────────

TODO 4.C4-b / APP-001 [Group: TIGER] [Complexity: MEDIUM] [Tokens: ~2000] [User: NO]
    Improve rate limiter to handle proxy/forwarded IPs.
    Currently client_ip = request.client.host, which returns the proxy IP
    when behind a reverse proxy (Nginx, Cloudflare, etc.). Steps:
      1. Read X-Forwarded-For header if present (trusted proxies only)
      2. Add TRUSTED_PROXIES env var to configure which IPs to trust
      3. Fall back to request.client.host if no proxy header
      4. Add rate limit bypass for health check endpoint
    Acceptance: Rate limiting works correctly behind a reverse proxy.

TODO 4.C4-c / APP-002 [Group: TIGER] [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Add rate limit memory cleanup to prevent unbounded memory growth.
    _rate_counters dict grows indefinitely as new IPs make requests.
    Steps:
      1. Add periodic cleanup: every 5 minutes, remove entries where all
         timestamps are older than 60 seconds
      2. Use a background task or middleware counter to trigger cleanup
      3. Add max_tracked_ips limit (e.g., 10000) — evict oldest on overflow
    Acceptance: Rate limiter memory bounded; no growth after days of traffic.

TODO 4.C3-b / APP-003 [Group: TIGER] [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Add structured JSON logging for production deployments.
    Currently logging uses text format which is hard to parse in log
    aggregation tools (ELK, Datadog, CloudWatch). Steps:
      1. Add JSON formatter class that outputs log records as JSON
      2. Enable JSON logging when APP_LOG_FORMAT=json env var is set
      3. Include fields: timestamp, level, logger, method, path, status,
         duration_ms, client_ip, request_id
      4. Add X-Request-ID header generation for request tracing
    Acceptance: APP_LOG_FORMAT=json produces newline-delimited JSON logs.

TODO APP-004 [Group: TIGER] [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Add CORS middleware for API consumers.
    External clients (JavaScript apps, Jupyter notebooks) need CORS headers
    to call the API from different origins. Steps:
      1. Add FastAPI CORSMiddleware with configurable allowed origins
      2. Default: allow all origins for public data API
      3. Add APP_CORS_ORIGINS env var for restrictive deployments
    Acceptance: Browser JS from external domains can call /api/v1/ endpoints.
"""

import logging
import sqlite3
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api.database import get_db_path
from api.routes import aggregations, budget_lines, download, reference, search
from api.routes import frontend as frontend_routes

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
        description=(
            "## DoD Budget Explorer API\n\n"
            "Provides programmatic access to Department of Defense budget justification "
            "data extracted from publicly posted XLSX and PDF documents.\n\n"
            "### Key concepts\n"
            "- **Amounts** are in **thousands of dollars ($K)** unless `amount_unit` says otherwise.\n"
            "- **Fiscal year** runs October 1 – September 30 "
            "(e.g., FY2026 = Oct 2025 – Sep 2026).\n"
            "- **Exhibit types**: R-2 (RDT&E programs), P-5 (procurement), "
            "O-1 (O&M), P-1/R-1 (summary rolls), C-1 (construction), "
            "M-1 (military personnel).\n"
            "- **FTS5 search** uses SQLite full-text search with BM25 ranking "
            "across all line item titles, descriptions, and PDF page text.\n\n"
            "### Rate limits\n"
            "- `/api/v1/search`: 60 req/min per IP\n"
            "- `/api/v1/download`: 10 req/min per IP\n"
            "- All other endpoints: 120 req/min per IP\n\n"
            "Returns `429 Too Many Requests` with `Retry-After: 60` when exceeded.\n\n"
            "### Data freshness\n"
            "Data is refreshed weekly via GitHub Actions from official DoD "
            "Comptroller and service budget office sites."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        contact={
            "name": "DoD Budget Explorer",
            "url": "https://github.com/wschosta/dod-budget-analysis",
        },
        license_info={
            "name": "Public Domain (government data)",
            "url": "https://creativecommons.org/publicdomain/zero/1.0/",
        },
        openapi_tags=[
            {
                "name": "search",
                "description": "Full-text search across budget lines and PDF pages.",
            },
            {
                "name": "budget-lines",
                "description": (
                    "List, filter, sort, and retrieve individual budget line items. "
                    "All amounts are in $K (thousands of dollars)."
                ),
            },
            {
                "name": "aggregations",
                "description": "GROUP BY summaries for charts and dashboards.",
            },
            {
                "name": "reference",
                "description": "Reference lists: services, exhibit types, fiscal years.",
            },
            {
                "name": "download",
                "description": "Bulk export of filtered budget lines as CSV or NDJSON.",
            },
            {
                "name": "meta",
                "description": "Health check and API metadata.",
            },
        ],
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

    # ── Static files + Jinja2 templates (3.A0-a) ──────────────────────────────
    _here = Path(__file__).parent.parent  # project root

    static_dir = _here / "static"
    templates_dir = _here / "templates"

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    if templates_dir.exists():
        templates = Jinja2Templates(directory=str(templates_dir))

        # Custom filter: format dollar amounts (in $K) with comma separators
        def fmt_amount(value) -> str:
            try:
                return f"{float(value):,.1f}"
            except (TypeError, ValueError):
                return "—"

        templates.env.filters["fmt_amount"] = fmt_amount

        # Wire templates into the frontend router
        frontend_routes.set_templates(templates)
        app.include_router(frontend_routes.router)

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
