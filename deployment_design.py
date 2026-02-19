"""
Deployment & Operations Design — Steps 4.A, 4.B, 4.C

**Status:** Phase 4 Planning (Phases 1-3 must be complete first)

Plans and TODOs for containerization, CI/CD, deployment, and monitoring.

──────────────────────────────────────────────────────────────────────────────
TODOs — Step 4.A (Containerization & Infrastructure)
──────────────────────────────────────────────────────────────────────────────

DONE 4.A1-a  Dockerfile: python:3.12-slim, non-root appuser, HEALTHCHECK,
    COPY requirements.txt + pip install, COPY api/ utils/ templates/ static/ *.py,
    ENV APP_DB_PATH, EXPOSE 8000, CMD uvicorn 2-worker.

DONE 4.A1-b  docker-compose.yml: web service ports 8000:8000, volume mounts for
    dod_budget.sqlite (ro) and api/ utils/ for hot-reload, healthcheck.

DONE 4.A2-a  Dockerfile.multistage: 2-stage build.
    Stage 1 (builder): python:3.12 full + Playwright Chromium + poppler-utils;
    runs build_budget_db.py to produce dod_budget.sqlite.
    Stage 2 (runtime): python:3.12-slim, copies only sqlite + app code from builder;
    runtime image ~150MB vs ~2GB for builder.

TODO 4.A3-a [Group: OH MY] [Complexity: MEDIUM] [Tokens: ~2000] [User: YES — needs cloud account]
    Choose hosting platform and document decision.
    Steps:
      1. Evaluate: Railway, Fly.io, Render, AWS ECS, DigitalOcean App Platform
      2. Criteria: cost (free tier?), SQLite support (persistent disk),
         auto-deploy from GitHub, custom domain, HTTPS
      3. Recommendation: Fly.io or Railway (both support persistent volumes
         for SQLite; free tier available; auto-deploy from GitHub)
      4. Write decision record
    Success: Platform chosen; account created; test deploy done.


──────────────────────────────────────────────────────────────────────────────
TODOs — Step 4.B (CI/CD Pipeline)
──────────────────────────────────────────────────────────────────────────────

DONE 4.B1-a  .github/workflows/ci.yml: matrix Python 3.11/3.12, checkout + pip install
    + ruff lint + pytest (ignoring test_gui_tracker.py) + upload artifact.
DONE 4.B3-a  .github/workflows/refresh-data.yml: weekly cron + manual dispatch,
    playwright install, refresh_data.py, upload db artifact, step summary.

TODO 4.B2-a [Group: OH MY] [Complexity: MEDIUM] [Tokens: ~2000] [User: YES — needs secrets]
    Create GitHub Actions deploy workflow (.github/workflows/deploy.yml).
    Steps:
      1. Trigger on: push to main (after CI passes)
      2. Build Docker image and push to registry (GHCR or platform-native)
      3. Deploy to chosen platform (Fly.io/Railway CLI)
      4. Run smoke test against deployed URL
    Dependency: TODO 4.A3-a (platform choice) must be done first.
    Success: Merging to main auto-deploys within minutes.


──────────────────────────────────────────────────────────────────────────────
TODOs — Step 4.C (Monitoring, Domain & Launch)
──────────────────────────────────────────────────────────────────────────────

TODO 4.C1-a [Group: OH MY] [Complexity: LOW] [Tokens: ~1000] [User: YES — needs domain]
    Configure custom domain + HTTPS.
    Steps:
      1. Register domain (e.g., dodbudget.org or similar)
      2. Configure DNS to point to hosting platform
      3. Enable HTTPS (most platforms provide free TLS via Let's Encrypt)
    Success: App accessible at https://custom-domain.com.

DONE 4.C2-a  GET /health endpoint in api/app.py: returns {status, database, budget_lines}
    or 503 if DB absent/degraded.
DONE 4.C3-a  HTTP middleware in api/app.py: structured access logging (method/path/
    status/duration_ms/ip) + slow-query warnings (>500ms).
DONE 4.C4-a  Rate limiting middleware in api/app.py: fixed-window per-IP counter,
    search=60/min, download=10/min, others=120/min; returns 429 + Retry-After.

DONE 4.C5-a  docs/deployment.md (~147 lines): prerequisites, quick start,
    Docker deploy, docker-compose, data updates, env vars (APP_DB_PATH),
    database backup, rollback, health check, secrets management.

TODO 4.C6-a [Group: OH MY] [Complexity: LOW] [Tokens: ~1500] [User: YES — needs community review]
    Prepare for public launch.
    Steps:
      1. Review README for public-facing accuracy
      2. Add CONTRIBUTING.md with guidelines
      3. Add LICENSE file (recommend MIT or public domain for gov data)
      4. Create GitHub release with changelog
      5. Submit to relevant data/policy communities for feedback
    Success: Repository is public, documented, and discoverable.


──────────────────────────────────────────────────────────────────────────────
Additional Phase 4 TODOs — Monitoring, Security, Operations
──────────────────────────────────────────────────────────────────────────────

TODO 4.C7-a / DEPLOY-001 [Group: BEAR] [Complexity: MEDIUM] [Tokens: ~2500] [User: NO]
    Add application monitoring with health metrics endpoint.
    Currently /health only checks DB existence. Expand to include operational
    metrics useful for monitoring dashboards. Steps:
      1. Add GET /health/detailed endpoint returning:
         - uptime_seconds, request_count, error_count
         - db_size_bytes, budget_lines_count, pdf_pages_count
         - avg_response_time_ms (last 100 requests)
         - rate_limiter_stats (tracked IPs, blocked requests)
      2. Track metrics using a simple in-memory counter dict
      3. Reset counters on restart (stateless — no persistence needed)
      4. Format output compatible with Prometheus exposition format (optional)
    Acceptance: /health/detailed returns operational metrics JSON.

TODO 4.C7-b / DEPLOY-002 [Group: BEAR] [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Add database backup script for automated deployments.
    SQLite files can be corrupted if copied while being written. Steps:
      1. Create scripts/backup_db.py using sqlite3 .backup() API
      2. Generate timestamped backup: dod_budget_YYYYMMDD_HHMMSS.sqlite
      3. Add --keep N flag to retain only last N backups
      4. Add to docker-compose as a periodic service or cron job
    Acceptance: Backup produces consistent snapshot; old backups pruned.

TODO 4.C8-a / DEPLOY-003 [Group: BEAR] [Complexity: LOW] [Tokens: ~1500] [User: NO]
    Add Content Security Policy (CSP) headers.
    Steps:
      1. Add CSP middleware in api/app.py
      2. Allow: self for scripts/styles, unpkg.com + cdn.jsdelivr.net for
         HTMX and Chart.js CDN, data: for inline SVGs
      3. Block: inline scripts/styles (unless nonce-based)
      4. Add X-Content-Type-Options: nosniff
      5. Add X-Frame-Options: DENY
    Acceptance: CSP header present on all responses; no console violations.

TODO 4.B4-a / DEPLOY-004 [Group: BEAR] [Complexity: MEDIUM] [Tokens: ~2000] [User: NO]
    Add staging environment configuration.
    Steps:
      1. Create docker-compose.staging.yml with production-like settings
      2. Add APP_ENV=staging environment variable support
      3. In staging: disable debug mode, enable JSON logging, stricter rate limits
      4. Add smoke test script that validates all endpoints return 200
    Acceptance: Staging environment mirrors production config.

TODO 4.C6-b / DEPLOY-005 [Group: BEAR] [Complexity: LOW] [Tokens: ~2000] [User: NO]
    Write CONTRIBUTING.md with development guidelines.
    Steps:
      1. Prerequisites: Python 3.10+, requirements-dev.txt
      2. Development setup: clone, pip install, build test DB
      3. Code standards: black formatting, ruff linting, type hints
      4. Testing: how to run tests, write new tests, use fixtures
      5. PR process: branch naming, commit message format, review checklist
      6. Architecture overview: data flow diagram, module responsibilities
    Acceptance: New contributors can set up and contribute within 30 minutes.
"""

# No implementation code — this is a planning document.
# Deployment artifacts will be created as individual files:
#   Dockerfile
#   docker-compose.yml
#   .dockerignore
#   .github/workflows/ci.yml
#   .github/workflows/deploy.yml
#   .github/workflows/refresh-data.yml
