# DoD Budget API — Dockerfile (Step 4.A1-a)
#
# Single-stage build (fast startup for development).
# For production with embedded data, see comments on multi-stage build (4.A2-a).
#
# Build:  docker build -t dod-budget .
# Run:    docker run -p 8000:8000 -v ./dod_budget.sqlite:/app/dod_budget.sqlite dod-budget
#
# ──────────────────────────────────────────────────────────────────────────────
# Dockerfile TODOs
# ──────────────────────────────────────────────────────────────────────────────
#
# TODO DOCKER-001 [Group: BEAR] [Complexity: LOW] [Tokens: ~1000] [User: NO]
#     Add templates/ and static/ directories to COPY instructions.
#     Currently the Dockerfile copies API and utility code but NOT the
#     templates/ and static/ directories needed for the frontend.
#     Steps:
#       1. Add: COPY templates/ templates/
#       2. Add: COPY static/ static/
#       3. Also copy schema_design.py (needed for migrations)
#       4. Verify: docker build && docker run && curl localhost:8000/
#     Acceptance: Docker container serves frontend pages at /.
#
# TODO DOCKER-002 [Group: BEAR] [Complexity: LOW] [Tokens: ~1000] [User: NO]
#     Add production security hardening.
#     Steps:
#       1. Add --no-install-recommends to apt-get (if any apt-get added later)
#       2. Add PYTHONDONTWRITEBYTECODE=1 and PYTHONUNBUFFERED=1 env vars
#       3. Pin pip version in RUN pip install
#       4. Add read-only filesystem: --read-only flag note in docs
#       5. Add security scan step note (trivy, snyk)
#     Acceptance: Dockerfile follows Docker security best practices.

FROM python:3.12-slim

LABEL org.opencontainers.image.title="DoD Budget API"
LABEL org.opencontainers.image.description="REST API for DoD budget justification data"

# Non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source (exclude test/dev files via .dockerignore)
COPY api/           api/
COPY utils/         utils/
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
