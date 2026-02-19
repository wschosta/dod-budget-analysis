# DONE [Group: BEAR] BEAR-009: Docker lint-level validation tests — tests/test_bear_docker.py (20 tests)
# DoD Budget API — Dockerfile (Step 4.A1-a)
#
# Single-stage build (fast startup for development).
# For production with embedded data, see comments on multi-stage build (4.A2-a).
#
# Build:  docker build -t dod-budget .
# Run:    docker run -p 8000:8000 -v ./dod_budget.sqlite:/app/dod_budget.sqlite dod-budget
#
# Security note: run with --read-only --tmpfs /tmp for filesystem hardening.
# Security scan: trivy image dod-budget or snyk container test dod-budget

FROM python:3.12-slim

LABEL org.opencontainers.image.title="DoD Budget API"
LABEL org.opencontainers.image.description="REST API for DoD budget justification data"

# DOCKER-002: Security hardening env vars
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Install Python dependencies first (cached layer)
# DOCKER-002: Pin pip to avoid supply chain issues
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip==24.3.1 && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source (exclude test/dev files via .dockerignore)
COPY api/           api/
COPY utils/         utils/
# DOCKER-001: Add frontend templates and static assets
COPY templates/     templates/
COPY static/        static/
COPY schema_design.py       .
COPY exhibit_catalog.py     .
COPY validate_budget_data.py .
COPY validate_budget_db.py  .
COPY search_budget.py       .
COPY build_budget_db.py     .
COPY refresh_data.py        .

# Database mount point — override with -v at runtime or COPY in CI builds
# The health endpoint at /health returns 503 if the DB is absent.
ENV APP_DB_PATH=/app/dod_budget.sqlite

# Switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
