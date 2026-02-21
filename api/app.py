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

APP-001: Proxy/forwarded IP handling with TRUSTED_PROXIES env var.
APP-002: Rate limit memory cleanup with max_tracked_ips and periodic eviction.
APP-003: Structured JSON logging when APP_LOG_FORMAT=json.
APP-004: CORS middleware with configurable origins via APP_CORS_ORIGINS.
OPT-FMT-001: fmt_amount Jinja filter uses shared format_amount() from utils.
"""

import json
import logging
import logging.handlers
import os
import sqlite3
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api.database import get_db_path
from utils.database import get_slow_queries, get_query_stats
from api.routes import aggregations, budget_lines, dashboard, download, feedback, metadata, pe, reference, search
from api.routes import frontend as frontend_routes
from utils.config import AppConfig

# ── Configuration ─────────────────────────────────────────────────────────────
_cfg = AppConfig.from_env()

# ── APP-003: Structured JSON logging ─────────────────────────────────────────


class _JsonFormatter(logging.Formatter):
    """Emit log records as newline-delimited JSON."""

    def format(self, record: logging.LogRecord) -> str:
        data: dict = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge extra fields added via logger.info("...", extra={...})
        for key in ("method", "path", "status", "duration_ms", "client_ip",
                    "request_id"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        if record.exc_info:
            data["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(data)


_logger = logging.getLogger("dod_budget_api")
_handler = logging.StreamHandler()
if _cfg.log_format == "json":
    _handler.setFormatter(_JsonFormatter())
else:
    _handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
logging.basicConfig(handlers=[_handler], level=logging.INFO, force=True)

# ── APP-002: Rate limiting state with memory bounds ───────────────────────────
# Limits: search=60/min, download=10/min, others=120/min (from AppConfig).
_RATE_LIMITS: dict[str, int] = {
    "/api/v1/search":   _cfg.rate_limit_search,
    "/api/v1/download": _cfg.rate_limit_download,
}
_DEFAULT_RATE_LIMIT = _cfg.rate_limit_default
_rate_counters: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
_MAX_TRACKED_IPS = 10_000
_last_cleanup: float = 0.0
_CLEANUP_INTERVAL = 300.0  # 5 minutes


def _cleanup_rate_counters() -> None:
    """Remove stale rate counter entries to bound memory usage."""
    global _last_cleanup
    now = time.time()
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now
    window_start = now - 60.0
    to_delete = []
    for ip, paths in _rate_counters.items():
        for path in list(paths.keys()):
            paths[path] = [t for t in paths[path] if t > window_start]
            if not paths[path]:
                del paths[path]
        if not paths:
            to_delete.append(ip)
    for ip in to_delete:
        del _rate_counters[ip]
    # If still over limit, evict oldest IPs (those with fewest recent hits)
    if len(_rate_counters) > _MAX_TRACKED_IPS:
        excess = len(_rate_counters) - _MAX_TRACKED_IPS
        oldest = sorted(
            _rate_counters.keys(),
            key=lambda ip: sum(len(v) for v in _rate_counters[ip].values()),
        )[:excess]
        for ip in oldest:
            del _rate_counters[ip]


# ── APP-001: Extract real client IP (proxy-aware) ─────────────────────────────

def _get_client_ip(request: Request) -> str:
    """Return the real client IP, respecting X-Forwarded-For from trusted proxies."""
    direct_ip = request.client.host if request.client else "unknown"
    if not _cfg.trusted_proxies:
        return direct_ip
    if direct_ip not in _cfg.trusted_proxies:
        return direct_ip
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        # X-Forwarded-For: client, proxy1, proxy2 — leftmost is real client
        real_ip = xff.split(",")[0].strip()
        if real_ip:
            return real_ip
    return direct_ip

# ── Application metrics (DEPLOY-001) ─────────────────────────────────────────
# Simple in-memory counters; reset on process restart (stateless by design).
_app_start_time: float = time.time()
_metrics: dict = {
    "request_count": 0,
    "error_count": 0,
    "blocked_count": 0,
    "response_times_ms": [],  # capped at last 100 entries
}
_RESPONSE_TIME_WINDOW = 100  # number of recent response times to average


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
            f"- `/api/v1/search`: {_cfg.rate_limit_search} req/min per IP\n"
            f"- `/api/v1/download`: {_cfg.rate_limit_download} req/min per IP\n"
            f"- All other endpoints: {_cfg.rate_limit_default} req/min per IP\n\n"
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
                "name": "pe",
                "description": (
                    "PE-centric views: funding by year, sub-elements, narrative descriptions, "
                    "related PE lineage, tag browsing, and Spruill-style CSV/ZIP export."
                ),
            },
            {
                "name": "dashboard",
                "description": "Dashboard summary statistics with service, FY, and budget type breakdowns.",
            },
            {
                "name": "feedback",
                "description": "User feedback submission for bug reports, feature requests, and data issues.",
            },
            {
                "name": "meta",
                "description": "Health check and API metadata.",
            },
        ],
    )

    # ── APP-004: CORS middleware ───────────────────────────────────────────────
    allow_origins = _cfg.cors_origins if _cfg.cors_origins != ["*"] else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "OPTIONS"],
        allow_headers=["*"],
    )

    # DONE [Group: TIGER] TIGER-009: Add Cache-Control, ETag, and 304 response headers

    # ── TIGER-009: ETag + Cache-Control middleware ────────────────────────────

    _etag_value: str | None = None
    _etag_size: int = 0

    def _compute_etag() -> str | None:
        """Compute ETag based on database file size.

        Uses file size as the basis since SQLite WAL mode may update
        mtime on reads.  Recomputes when size changes (indicating a
        data modification).
        """
        nonlocal _etag_value, _etag_size
        db_path = get_db_path()
        if not db_path.exists():
            return None
        try:
            size = db_path.stat().st_size
        except OSError:
            return None
        if _etag_value and size == _etag_size:
            return _etag_value
        _etag_size = size
        _etag_value = f'W/"{size:x}"'
        return _etag_value

    @app.middleware("http")
    async def cache_control_middleware(request: Request, call_next):
        """Add Cache-Control headers and handle ETag/If-None-Match."""
        path = request.url.path

        # Compute ETag for GET requests to API endpoints
        etag = None
        if request.method == "GET" and path.startswith("/api/v1"):
            etag = _compute_etag()

            # Handle If-None-Match → 304 Not Modified
            if etag:
                if_none_match = request.headers.get("If-None-Match")
                if if_none_match and if_none_match == etag:
                    from starlette.responses import Response
                    return Response(status_code=304, headers={"ETag": etag})

        response = await call_next(request)

        # Add ETag header
        if etag and request.method == "GET":
            response.headers["ETag"] = etag

        # Add Cache-Control based on endpoint category
        if path.startswith("/api/v1/reference"):
            response.headers.setdefault(
                "Cache-Control", "public, max-age=3600"
            )
        elif path.startswith("/api/v1/aggregations"):
            response.headers.setdefault(
                "Cache-Control", "public, max-age=300"
            )
        elif path.startswith("/api/v1/search") or path.startswith("/api/v1/download"):
            response.headers.setdefault(
                "Cache-Control", "private, no-cache"
            )

        return response

    # ── Request logging + rate limiting middleware (4.C3-a, 4.C4-a) ──────────

    @app.middleware("http")
    async def log_and_rate_limit(request: Request, call_next):
        """Log each request, enforce per-IP rate limits, and record metrics."""
        # APP-003: Generate request ID for tracing
        request_id = str(uuid.uuid4())[:8]
        start = time.monotonic()
        client_ip = _get_client_ip(request)
        path = request.url.path

        # APP-002: Periodic memory cleanup
        _cleanup_rate_counters()

        # Health check bypass — not rate limited
        if path == "/health":
            response = await call_next(request)
            return response

        # Rate limiting
        limit = _RATE_LIMITS.get(path, _DEFAULT_RATE_LIMIT)
        now = time.time()
        window_start = now - 60.0
        hits = _rate_counters[client_ip][path]
        _rate_counters[client_ip][path] = [t for t in hits if t > window_start]
        if len(_rate_counters[client_ip][path]) >= limit:
            _metrics["blocked_count"] += 1
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
        _metrics["request_count"] += 1
        response = await call_next(request)
        duration_ms = (time.monotonic() - start) * 1000

        # Track response time (cap at last _RESPONSE_TIME_WINDOW entries)
        _metrics["response_times_ms"].append(duration_ms)
        if len(_metrics["response_times_ms"]) > _RESPONSE_TIME_WINDOW:
            _metrics["response_times_ms"] = (
                _metrics["response_times_ms"][-_RESPONSE_TIME_WINDOW:]
            )

        # Track server errors
        if response.status_code >= 500:
            _metrics["error_count"] += 1

        # APP-003: Add request ID header
        response.headers["X-Request-ID"] = request_id

        if _cfg.log_format == "json":
            _logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": path,
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 1),
                    "client_ip": client_ip,
                    "request_id": request_id,
                },
            )
        else:
            _logger.info(
                "method=%s path=%s status=%d duration_ms=%.1f ip=%s rid=%s",
                request.method, path, response.status_code, duration_ms,
                client_ip, request_id,
            )
        if duration_ms > 500:
            _logger.warning(
                "slow_query method=%s path=%s duration_ms=%.1f",
                request.method, path, duration_ms,
            )
        return response

    # ── Content Security Policy + security headers (DEPLOY-003) ──────────────

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        """Add Content-Security-Policy, X-Content-Type-Options, and X-Frame-Options."""
        response = await call_next(request)
        # CSP: allow self + CDN origins used by HTMX and Chart.js.
        # 'unsafe-inline' is required for the inline <script> blocks in templates.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' unpkg.com cdn.jsdelivr.net 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self';"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
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

    # ── Detailed health / metrics endpoint (DEPLOY-001) ──────────────────────

    @app.get(
        "/health/detailed",
        tags=["meta"],
        summary="Detailed health metrics",
        response_description="Operational metrics for monitoring dashboards",
    )
    def health_detailed():
        """Return detailed operational metrics for monitoring dashboards.

        Includes uptime, request/error counters, database statistics,
        average response time, and rate-limiter stats.  Counters reset
        on process restart (stateless — no persistence).
        """
        db_path = get_db_path()
        now = time.time()
        uptime = now - _app_start_time

        if not db_path.exists():
            return JSONResponse(
                status_code=503,
                content={"status": "no_database", "database": str(db_path)},
            )

        try:
            conn = sqlite3.connect(str(db_path))
            budget_count = conn.execute(
                "SELECT COUNT(*) FROM budget_lines"
            ).fetchone()[0]
            pdf_count = conn.execute(
                "SELECT COUNT(*) FROM pdf_pages"
            ).fetchone()[0]
            conn.close()
        except Exception as exc:
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "error": str(exc)},
            )

        db_size = os.path.getsize(str(db_path))

        rts = _metrics["response_times_ms"]
        avg_rt = round(sum(rts) / len(rts), 2) if rts else 0.0

        # TIGER-011: Include query performance stats
        qstats = get_query_stats()

        return {
            "status": "ok",
            "uptime_seconds": round(uptime, 2),
            "request_count": _metrics["request_count"],
            "error_count": _metrics["error_count"],
            "db_size_bytes": db_size,
            "budget_lines_count": budget_count,
            "pdf_pages_count": pdf_count,
            "avg_response_time_ms": avg_rt,
            "rate_limiter_stats": {
                "tracked_ips": len(_rate_counters),
                "blocked_requests": _metrics["blocked_count"],
            },
            "slow_query_count": qstats["slow_query_count"],
            "avg_query_time_ms": qstats["avg_query_time_ms"],
        }

    # TIGER-011: Slow query monitoring endpoint
    @app.get(
        "/api/v1/health/queries",
        tags=["meta"],
        summary="Slow query log",
        response_description="Last 50 slow queries for performance monitoring",
    )
    def health_queries():
        """Return the last 50 slow queries (>100ms) for performance monitoring."""
        return {
            "stats": get_query_stats(),
            "slow_queries": get_slow_queries(),
        }

    # DONE [Group: TIGER] TIGER-008: Add feedback API endpoint stub (logs to feedback.json)

    # ── Register routers ──────────────────────────────────────────────────────

    prefix = "/api/v1"
    app.include_router(search.router,       prefix=prefix)
    app.include_router(budget_lines.router, prefix=prefix)
    app.include_router(aggregations.router, prefix=prefix)
    app.include_router(reference.router,    prefix=prefix)
    app.include_router(download.router,     prefix=prefix)
    app.include_router(pe.router,           prefix=prefix)
    app.include_router(feedback.router,     prefix=prefix)
    app.include_router(dashboard.router,   prefix=prefix)
    app.include_router(metadata.router,    prefix=prefix)

    # ── Static files + Jinja2 templates (3.A0-a) ──────────────────────────────
    _here = Path(__file__).parent.parent  # project root

    static_dir = _here / "static"
    templates_dir = _here / "templates"

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    if templates_dir.exists():
        templates = Jinja2Templates(directory=str(templates_dir))

        # OPT-FMT-001: Use shared format_amount from utils.formatting
        def fmt_amount(value) -> str:
            """Jinja filter: format dollar amount in $K with comma separators."""
            try:
                v = float(value)
            except (TypeError, ValueError):
                return "—"
            # For the template display we show value as-is with comma formatting
            # (values are already in $K)
            try:
                return f"{v:,.1f}"
            except Exception:
                return "—"

        # FE-003: Custom filter to remove a single key=value from query params
        def remove_filter_param(query_params, param_name: str, param_value: str) -> str:
            from urllib.parse import urlencode
            pairs = [
                (k, v) for k, v in query_params.multi_items()
                if not (k == param_name and v == str(param_value))
                if k != "page"
            ]
            return urlencode(pairs)

        templates.env.filters["fmt_amount"] = fmt_amount
        templates.env.filters["remove_filter_param"] = remove_filter_param

        # Wire templates into the frontend router
        frontend_routes.set_templates(templates)
        app.include_router(frontend_routes.router)

        # LION-001: Register custom HTML error pages for 404/500
        frontend_routes.register_error_handlers(app)

    return app


# Singleton instance for uvicorn
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.app:app",
        host=_cfg.api_host,
        port=_cfg.api_port,
        reload=True,
        log_level="info",
    )
